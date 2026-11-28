"""[수정 제작] 고르기 — 화면 · 알람 거는 줄 · 원문 계약(설계서 2026-11-28 흐름 셋 §2-2 · §2-11).

쓰기 · 판정은 ``test_production_rework_pick_1128.py``(준비물도 거기 것을 같이 쓴다 — 500줄 래칫으로 나눴다).

* 작업 시트: 제작 완료 단계 · 반장 · 관리자 화면에만 고르기 창(도면 줄 · 공정 넷). 반장에게 남의 공장 도면은 안 골라진다.
* Node: [수정 제작] → 고르기 창 → [다음] → 지금 사유 창 + 한 줄 → 사유 + 고른 것을 같은 주소로 한 번 → 다시 받은 화면 상태 줄에 알림.
* 알람 거는 줄(``orders.py``): 수정 제작 · 보류 걸기 · 풀기 · 불량 + 보류를 푸는 길 셋 — 커밋 전 note · 커밋 바로 뒤 flush, 되감은 길은 flush 없음.

되돌리면 실패: 파트 계정 화면에 창이 실림 · 0개인데 [다음]이 눌림 · 고른 것이 몸에 안 실림 · 공용 사유 창 파일이 바뀜 · flush 가 커밋 전.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import scoped_session

from foms.services.production import floor_alarm
from tests.domains.test_production_rework_pick_1128 import PARTS, _all_done, _complete, _no_drawing_done, _rework
from tests.domains.test_production_rework_pick_1128 import people  # noqa: F401  # 준비물(fixture)
from tests.support.production_factory_seed import TABLET, mixed_order, set_cookies
from tests.support.production_part_claim_seed import login, make_order, patch_sd

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_rework_pick_node_checks.js"
REWORK_JS = "static/js/production/foms-production-sheet-rework.js"
SHEETS_JS = "static/js/foms/tablet-domain-sheets.js"
REASON_JS = "static/js/foms/foms-reason-sheet.js"
PICK_HTML = "templates/production/partials/sheet_rework_pick.html"
REWORK_PIN = "20261128a"


# --------------------------------------------------------------------------- #
# 1. 알람 거는 줄(설계서 §2-11) — 커밋 전 note · 커밋 바로 뒤 flush, 되감은 길은 flush 없음
# --------------------------------------------------------------------------- #
@pytest.fixture
def alarm(monkeypatch):
    calls: list = []

    def opened(db) -> bool:  # 요청 세션은 scoped_session 이다(``get_db``) — 그 안의 진짜 세션에 묻는다
        return (db() if isinstance(db, scoped_session) else db).in_transaction()

    def note(db, kind, order_id, actor, **material):  # 커밋 전 = 그 요청의 tx 가 열려 있다
        calls.append(("note", kind, int(order_id), getattr(actor, "name", None), material, opened(db)))

    def flush(db):  # 커밋 바로 뒤 = 열린 tx 가 없다
        calls.append(("flush", opened(db)))

    monkeypatch.setattr(floor_alarm, "note", note)
    monkeypatch.setattr(floor_alarm, "flush", flush)
    return calls


def _kinds(calls: list) -> list:
    return [c[1] if c[0] == "note" else "flush" for c in calls]


def test_수정_제작_보류_불량이_알람을_건다(client, people, alarm) -> None:
    login(client, people["admin"])
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, people["cut"])
    assert _complete(client, seed.id).status_code == 200
    patch_sd(seed.id, hold={"active": True, "reason": "자재", "at": None, "by_name": "박반장"})
    del alarm[:]

    assert _rework(client, seed.id).status_code == 409 and _rework(client, seed.id, release_hold=True).status_code == 400
    assert alarm == [("note", "hold_released", seed.id, "정관리", {}, True)]  # 되감은 길 — flush 없음(주머니는 알람 모듈 몫)
    del alarm[:]
    assert _rework(client, seed.id, keys=[seed.keys[2], seed.keys[0]], release_hold=True).status_code == 200
    assert _kinds(alarm) == ["hold_released", "rework", "flush"]
    assert alarm[1][2:5] == (seed.id, "정관리", {"drawing_keys": [seed.keys[0], seed.keys[2]], "factories": [1, 2]})
    assert alarm[2] == ("flush", False)  # 커밋 바로 뒤 — 쓸 것이 남아 있지 않다
    del alarm[:]

    hold = lambda active, reason="": client.post(f"/api/orders/{seed.id}/production/hold", json={"active": active, "reason": reason})  # noqa: E731
    assert hold(True, "자재 기다림").status_code == 200
    assert hold(True, "또").status_code == 409  # 이미 보류 — 거절은 알람 없음
    assert hold(False).status_code == 200
    assert [(c[1], c[4]) if c[0] == "note" else "flush" for c in alarm] == [
        ("hold", {"reason": "자재 기다림"}), "flush", ("hold_released", {"reason": ""}), "flush"]
    del alarm[:]

    assert client.post(f"/api/orders/{seed.id}/production/defect", json={"reason": "모르는 값"}).status_code == 400
    assert client.post(f"/api/orders/{seed.id}/production/defect", json={"reason": "파손"}).status_code == 200
    assert [(c[1], c[4]) if c[0] == "note" else "flush" for c in alarm] == [("defect", {"label": "파손"}), "flush"]

    plain = _no_drawing_done(client, steps_done=PARTS)
    del alarm[:]  # 준비물의 [제작 완료]도 커밋 뒤 flush 를 부른다(complete_order) — 그 뒤부터 센다
    assert _rework(client, plain.id, steps=["cut"]).status_code == 200
    assert alarm[0][1:5] == ("rework", plain.id, "정관리", {"steps": ["cut"], "factories": [1]}) and _kinds(alarm) == ["rework", "flush"]


def test_보류를_푸는_다른_길도_알람을_건다(client, people, alarm) -> None:
    login(client, people["lead"])
    waiting = make_order(1, run=False)
    patch_sd(waiting.id, hold={"active": True, "reason": "자재", "at": None, "by_name": "박반장"})
    assert client.post(f"/api/orders/{waiting.id}/production/start", json={}).status_code == 409
    assert alarm == []
    assert client.post(f"/api/orders/{waiting.id}/production/start", json={"release_hold": True}).status_code == 200
    assert _kinds(alarm) == ["hold_released", "flush"]
    del alarm[:]

    patch_sd(waiting.id, hold={"active": True, "reason": "자재", "at": None, "by_name": "박반장"})
    assert client.post(f"/api/orders/{waiting.id}/production/cancel", json={}).status_code == 200  # 제작 시작 취소가 보류도 푼다
    assert _kinds(alarm) == ["hold_released", "flush"]
    del alarm[:]
    assert client.post(f"/api/orders/{waiting.id}/production/start", json={}).status_code == 200  # 보류가 없으면 풀림 알람도 없다
    assert _kinds(alarm) == ["flush"]


# --------------------------------------------------------------------------- #
# 2. 화면 — 고르기 창 조각 · 재료 · 스크립트
# --------------------------------------------------------------------------- #
def _sheet(client, oid: int) -> str:
    set_cookies(client, TABLET)
    resp = client.get(f"/erp/production/sheet/{oid}")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _pick_box(page: str) -> str:
    start = page.index('data-foms-rework-pick="')
    return page[page.rindex("<div", 0, start):page.index("</section>", start)]


def test_작업_시트에_도면_고르기_창이_실린다(client, people) -> None:
    login(client, people["admin"])
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, people["cut"])
    assert _complete(client, seed.id).status_code == 200

    login(client, people["lead"])
    page = _sheet(client, seed.id)
    assert page.count('data-foms-rework-pick="drawings"') == 1 and f"foms-production-sheet-rework.js?v={REWORK_PIN}" in page
    box = _pick_box(page)
    assert "hidden aria-hidden=\"true\"" in box.split(">", 1)[0]
    assert ">다시 만들 도면을 골라 주세요</h2>" in box
    assert [m for m in re.findall(r"<b>(도면 \d/\d)</b>", box)] == ["도면 1/3", "도면 2/3", "도면 3/3"]
    rows = re.findall(r"<button [^>]*data-foms-rework-item=\"[^\"]+\"[^>]*>", box)
    assert len(rows) == 3 and all('aria-pressed="false"' in r for r in rows)
    assert [re.search(r'data-foms-rework-item="([^"]+)"', r).group(1) for r in rows] == list(seed.keys)
    assert [re.search(r'data-foms-rework-word="([^"]+)"', r).group(1) for r in rows] == ["1", "2", "3"]
    assert ["aria-disabled" in r for r in rows] == [False, False, True]  # 반장에게 남의 공장 도면은 안 골라진다
    assert 'is-locked' in rows[2] and 'data-foms-rework-why="2공장에서 작업하는 도면이에요."' in rows[2]
    assert box.count('foms-fac foms-fac--1">1공장</em>') == 2 and box.count('foms-fac foms-fac--2">2공장</em>') == 1
    assert re.search(r"<button [^>]*data-foms-rework-next disabled>다음</button>", box)
    assert re.search(r"<button [^>]*data-foms-rework-close>닫기</button>", box)
    assert ">다시 만들 도면이 없으면 [완료 취소]를 눌러 주세요.</p>" in box
    assert "카드" not in re.sub(r"<[^>]+>", "", box)

    login(client, people["admin"])  # 관리자는 두 공장 다 고른다
    assert "aria-disabled" not in _pick_box(_sheet(client, seed.id))


def test_도면_없는_주문은_공정_고르기_창이고_그_밖_화면에는_없다(client, people) -> None:
    login(client, people["lead"])
    seed = _no_drawing_done(client, steps_done=PARTS)
    box = _pick_box(_sheet(client, seed.id))
    assert 'data-foms-rework-pick="steps"' in box and ">다시 할 공정을 골라 주세요</h2>" in box
    assert re.findall(r'data-foms-rework-item="(\w+)" data-foms-rework-word="([^"]+)"', box) == [
        ("cut", "재단"), ("edge", "엣지"), ("assemble", "조립"), ("inspect", "검수")]
    assert ">다시 할 공정이 없으면 [완료 취소]를 눌러 주세요.</p>" in box and "<img" not in box

    making = make_order(2)  # 제작 중 — 단추가 없으니 창도 없다(알림을 보일 스크립트만)
    page = _sheet(client, making.id)
    assert "data-foms-rework-pick" not in page and "foms-production-sheet-rework.js" in page
    login(client, people["cut"])  # 파트 계정 — [수정 제작] 단추 · 창 · 스크립트 모두 없다
    page = _sheet(client, seed.id)
    assert "data-foms-rework-pick" not in page and "foms-production-sheet-rework.js" not in page
    assert 'data-tablet-sheet-action="production-rework"' not in page


def _run_node(tmp_path, page: str, want: dict) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    path = tmp_path / "page.html"
    path.write_text(page, encoding="utf-8")
    want = {"scripts": [REASON_JS, REWORK_JS, SHEETS_JS], **want}
    proc = subprocess.run([node, str(NODE_CHECK), str(path), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


def test_고르기_창은_고른_것을_사유_창_몸에_얹어_한_번_보낸다_Node(client, people, tmp_path) -> None:
    login(client, people["admin"])
    seed = mixed_order(3, f2=(2,))
    _all_done(seed, people["cut"])
    assert _complete(client, seed.id).status_code == 200
    login(client, people["lead"])
    _run_node(tmp_path, _sheet(client, seed.id), {
        "order_id": seed.id, "kind": "drawings", "pick": [seed.keys[1], seed.keys[0]],
        "locked": {"key": seed.keys[2], "why": "2공장에서 작업하는 도면이에요."},
        "note": "도면 1 · 2번(2장)을 다시 만들어요. 재단 · 엣지 · 조립 · 검수가 모두 미정으로 돌아가요.",
        "post": {"keys": [seed.keys[0], seed.keys[1]]}, "message": "수정 제작을 시작했어요. 도면 2장을 다시 만들어요."})

    plain = _no_drawing_done(client, steps_done=PARTS)
    _run_node(tmp_path, _sheet(client, plain.id), {
        "order_id": plain.id, "kind": "steps", "pick": ["inspect", "assemble"], "locked": None,
        "note": "조립 · 검수를 다시 해요. 그 공정만 미완료로 돌아가요.",
        "post": {"steps": ["assemble", "inspect"]}, "message": "수정 제작을 시작했어요. 조립 · 검수를 다시 해요."})


# --------------------------------------------------------------------------- #
# 3. 원문 계약 — 새 파일은 요청을 안 보내고, 공용 사유 창은 생산 호출만 바뀐다
# --------------------------------------------------------------------------- #
def test_files_contract() -> None:
    read = lambda rel: (ROOT / rel).read_text(encoding="utf-8")  # noqa: E731
    js = read(REWORK_JS)
    assert "fetch(" not in js and "XMLHttpRequest" not in js and len(js.splitlines()) < 300
    assert "window.FomsSheetRework = { ask: ask, note: note, done: done };" in js
    assert "' 다시 해요. 그 공정만 미완료로 돌아가요.'" in js and "가 모두 미정으로 돌아가요.'" in js
    sheets = read(SHEETS_JS)
    assert "if (!pick || !pick.ask(btn, reason)) reason();" in sheets and "if (pick) pick.note(note);" in sheets
    assert 'title: "수정 제작으로 되돌릴까요?",' in sheets and 'detailLabel: "수정 제작 사유(안 적어도 돼요)",' in sheets  # 11-28 고친 글 그대로
    assert 'window.FomsSheetRework.done(orderId, data.message);' in sheets
    for rel in (REASON_JS, "templates/partials/shared/foms_reason_sheet.html"):  # 공용 사유 창은 다른 화면도 쓴다 — 안 바꾼다
        assert "rework" not in read(rel), rel
    for rel in (REWORK_JS, PICK_HTML):
        text = re.sub(r"/\*.*?\*/|\{#.*?#\}|//[^\n]*", "", read(rel), flags=re.S)
        assert "카드" not in text, rel
    sheet = read("templates/production/sheet.html")
    assert sheet.count("{% include 'production/partials/sheet_rework_pick.html' %}") == 1
    assert f"foms-production-sheet-rework.js') }}}}?v={REWORK_PIN}" in sheet
    for rel in ("foms/services/production/rework_sheets.py", "foms/services/production/part_progress.py", "foms/services/production/steps.py",
                "foms/services/production_sheet_view.py"):
        assert len(read(rel).splitlines()) < 500, rel
    css = read("static/css/contexts/production/sheet.css")
    for rule in re.findall(r"^\.fpp-rwk[^{]*\{[^}]*\}", css, flags=re.M):
        for size in re.findall(r"font-size:\s*([^;]+);", rule):
            assert re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", size.strip()), rule
