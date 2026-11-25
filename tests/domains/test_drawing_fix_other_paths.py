"""생산 넘어간 주문의 도면 수정 D2 — 다른 보내는 두 곳(사장님 "두 곳 모두 되게 만들기", 2026-11-25 지휘 L · M).

* L ERP 대시보드 [도면 전달] 창: 파일 + ``replace_target_key`` 꼴 본문 그대로 생산 단계 규칙(메모 400 → 파일 고르기 400 → 작업된 도면
  409 → ack 200, 교체 대상은 안 씀) · 그 밖 단계는 전과 같음(대조). 창 JS(erp-dashboard-drawing-fix.js + 공용 조각)는 R1 로 단계를 묻고
  생산 단계일 때만 칸을 켠다 — 고름은 파일마다 · 같은 도면 두 번 못 고름 · 확인 글은 '바뀐 도면' 줄(대조: 그 밖 단계는 아무것도 안 켬).
* M 태블릿 갤러리 '시트 전달'(transfer-pending): 생산 단계 메모 400 → 409 → ack 200 · 그 밖 단계 대조. 관리 시트 조각은 생산 단계에서
  메모 칸 · '바뀐 도면' 줄(서버 전달과 같은 계산) · 막는 까닭(서버와 같은 판정) · 도면팀 누구나 단추. JS 는 메모 없으면 안 보냄 ·
  확인 한 번 · 409 → 확인 창 → ack · 서버 글은 시트 안 칸(alert 없음).
이름은 모두 지어낸 값이다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from tests.support.drawing_fix_transfer_seed import (  # noqa: F401  quiet · team = 시험 준비물
    key,
    last_transfer,
    login,
    make_order,
    manual_key,
    names,
    patch,
    put_mark,
    quiet,
    sd_of,
    seed_pending,
    team,
)

ROOT = Path(__file__).resolve().parents[2]
JS = [ROOT / p for p in ("static/js/drawing/drawing-fix-send.js", "static/js/drawing/drawing-fix-picks.js",
                         "static/js/orders/dashboard/erp-dashboard-drawing-fix.js", "static/js/foms/tablet-drawing-gallery.js")]
NOTE_MSG = "공장에 남길 메모를 적어 주세요."
HOTFIX = "생산·시공 단계라 영업 확인 없이 바로 최종 도면이 되고 생산팀에 알림이 갑니다. 전달 취소로 되돌릴 수 없습니다."


def _code(res) -> str | None:
    return ((res.get_json() or {}).get("data") or {}).get("code")


def _run(scenario: str) -> dict:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    proc = subprocess.run([node, str(ROOT / "tests/domains/drawing_fix_paths_runner.js"), *map(str, JS), scenario],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --- L 서버 길(대시보드 창 본문 꼴) ------------------------------------------------------


def _dash(client, oid: int, *, note: str, pick: str | None, **extra):
    """ERP 대시보드 [도면 전달] 창이 보내는 꼴 — 올린 파일 + 교체 대상 한 장 + 수정본 표지."""
    upload = {"key": manual_key(oid, "dash"), "filename": "dash.pdf", **({"replace_of": pick} if pick else {})}
    return client.post(f"/api/orders/{oid}/transfer-drawing", json={
        "note": note, "files": [upload], "is_retransfer": True, "replace_target_key": key(oid, "s2"),
        "replace_target_number": 3, **extra})


def test_dashboard_body_goes_through_the_production_rules(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    put_mark(oid, key(oid, "s1"), "cut", "DONE", sheet_id="s1")
    login(client, team.other)                                          # 담당 아닌 도면팀
    assert _code(_dash(client, oid, note="", pick=None)) == "NOTE_REQUIRED"
    assert _code(_dash(client, oid, note="손잡이", pick=None)) == "PICK_TARGET"
    res = _dash(client, oid, note="손잡이", pick=key(oid, "s1"))
    assert res.status_code == 409 and [w["ident"] for w in res.get_json()["data"]["warnings"]] == ["sheet:s1"]
    res = _dash(client, oid, note="손잡이", pick=key(oid, "s1"), ack_worked=["sheet:s1"])
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert names(sd) == ["s0.png", "dash.pdf", "s2.png"]                # 교체 대상(도면 3)은 안 씀
    assert last_transfer(sd)["replace_target_keys"] is None


def test_control_dashboard_body_in_the_drawing_stage_is_unchanged(client, quiet, team):
    oid = make_order(stage="DRAWING", assignees=(team.drawer.id,))
    login(client, team.drawer)
    res = _dash(client, oid, note="", pick=None)
    assert res.status_code == 200, res.get_json()
    sd = sd_of(oid)
    assert sd["drawing_status"] == "TRANSFERRED" and names(sd) == ["s0.png", "s1.png", "dash.pdf"]
    assert "changed" not in last_transfer(sd)


# --- M 서버 길(태블릿 '시트 전달' = transfer-pending) ---------------------------------------


def _sheet_send(client, oid: int, **body):
    seed_pending(oid, "s1")
    return client.post(f"/api/orders/{oid}/drawing-wizard/transfer-pending", json=body)


def test_tablet_sheet_send_goes_through_the_production_rules(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,))
    put_mark(oid, key(oid, "s1"), "edge", "NEED", name="박엣지", sheet_id="s1")
    login(client, team.other)
    assert _code(_sheet_send(client, oid, note="")) == "NOTE_REQUIRED"
    assert _code(_sheet_send(client, oid, note="문짝")) == "WORKED_DRAWING"
    res = _sheet_send(client, oid, note="문짝", ack_worked=["sheet:s1"])
    assert res.status_code == 200, res.get_json()
    assert names(sd_of(oid)) == ["s0.png", "s1-v2.png", "s2.png"]


def test_control_tablet_sheet_send_in_the_drawing_stage_is_unchanged(client, quiet, team):
    oid = make_order(stage="DRAWING", assignees=(team.drawer.id,))
    login(client, team.drawer)
    res = _sheet_send(client, oid, note="")
    assert res.status_code == 200, res.get_json()
    assert sd_of(oid)["drawing_status"] == "TRANSFERRED"


# --- M 관리 시트 조각 -------------------------------------------------------------------


def _sheet(client, oid: int) -> BeautifulSoup:
    res = client.get(f"/erp/drawing-workbench/tablet-sheet/{oid}")
    assert res.status_code == 200
    return BeautifulSoup(res.get_data(as_text=True), "html.parser")


def test_tablet_sheet_in_production_shows_memo_changed_line_and_opens_to_drawing_team(client, quiet, team):
    oid = make_order(assignees=())                                     # 담당 없음
    seed_pending(oid, "s1")
    login(client, team.other)
    soup = _sheet(client, oid)
    box = soup.select_one("[data-foms-drawing-fix-box]")
    assert box is not None and box.select_one(".dfx-changed").get_text(strip=True) == "바뀐 도면: 도면 2 (고침)"
    assert "전달 메모" in box.get_text() and "꼭 적기" in box.get_text() and box.select_one("[data-foms-drawing-fix-note]")
    assert box.select_one("[data-foms-drawing-fix-error]").get_text(strip=True) == NOTE_MSG
    btn = soup.select_one("[data-foms-drawing-transfer]")
    assert btn is not None and btn.has_attr("data-foms-drawing-fix") and btn["data-foms-fix-sheets"] == "s1"
    assert not btn.has_attr("disabled") and "style=" not in str(box)


def test_tablet_sheet_blocks_like_the_server_when_a_factory_request_is_open(client, quiet, team):
    oid = make_order(assignees=(team.drawer.id,), extra={"drawing_fix": {"requests": [
        {"id": "fr_1", "from": "factory", "targets": ["sheet:s2"], "numbers": [3], "state": "open"}]}})
    seed_pending(oid, "s1")
    login(client, team.drawer)
    soup = _sheet(client, oid)
    assert soup.select_one("[data-foms-drawing-transfer]").has_attr("disabled")
    assert soup.select_one("#dw-sheet-transfer-reason").get_text(strip=True) == \
        "공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요."


@pytest.mark.parametrize("stage", ["DRAWING", "CONFIRM"])
def test_control_tablet_sheet_in_other_stages_is_unchanged(client, quiet, team, stage):
    oid = make_order(stage=stage, assignees=(team.drawer.id,))
    seed_pending(oid, "s1")
    login(client, team.other)                                          # 담당 아닌 도면팀 — 지금처럼 "담당자만"
    soup = _sheet(client, oid)
    assert soup.select_one("[data-foms-drawing-fix-box]") is None and soup.select_one("[data-foms-drawing-transfer]") is None
    assert "담당자만 전달할 수 있어요" in soup.get_text()
    login(client, team.drawer)
    btn = _sheet(client, oid).select_one("[data-foms-drawing-transfer]")
    assert btn is not None and not btn.has_attr("data-foms-drawing-fix")


# --- L · M 화면 JS(node) ----------------------------------------------------------------


def test_dashboard_window_turns_the_rules_on_only_for_production_orders():
    out = _run("dash_hotfix")
    assert out["opened"] and out["active"] and out["onlyShown"] == [True, True] and out["replaceHidden"] and out["picksShown"]
    assert out["noteCheck"] == NOTE_MSG and out["noteErrorShown"] is True
    assert out["secondRowFirstOff"] is True and out["pickCheck"] == "바꿀 도면을 골라 주세요." and out["readyCheck"] == ""
    assert [f["replace_of"] for f in out["attached"]] == ["k/d1.png", "NEW"]
    assert out["changed"] == "바뀐 도면: 도면 2 (고침)" and out["confirms"] == [f"바뀐 도면: 도면 2 (고침)\n\n{HOTFIX}"]
    plain = _run("dash_plain")                                         # 대조: 그 밖 단계는 아무것도 안 켬
    assert not plain["active"] and plain["onlyShown"] == [False, False] and not plain["replaceHidden"] and not plain["picksShown"]


def test_tablet_sheet_send_needs_memo_asks_once_and_keeps_messages_in_the_sheet():
    no_memo = _run("tablet_no_memo")
    assert no_memo["calls"] == [] and no_memo["errorShown"] and no_memo["focused"]
    sent = _run("tablet_send")
    posts = [c["body"] for c in sent["calls"] if c["method"] == "POST"]
    assert [p["ack_worked"] for p in posts] == [[], ["sheet:s1"]] and all(p["note"] == "문짝 손잡이 위치" for p in posts)
    assert len(sent["dialogs"]) == 1 and sent["reloaded"] is True and sent["alerts"] == []
    refused = _run("tablet_refused")
    assert refused["message"] == "공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요." and refused["alerts"] == []
