"""도면이 여러 장인 주문은 공정 칸으로 한꺼번에 완료하지 못한다(사장님 2026-11-27 "도면 두 장 이상이면 막기" · "각 도면을 체크하면서
완료하는 게 맞다").

규칙: 확정 도면(주문 전체 — 2공장 장 포함, 확인 창 "도면 n장"과 같은 ``current_keys``)이 2장 이상인 주문의 공정 칸 **켜기**는 누구든(반장 ·
관리자 포함) 409 ``STEP_PER_SHEET`` · 글 "도면이 여러 장인 주문이에요. 도면 화면에서 한 장씩 완료해 주세요." · 쓰기 · 이벤트 · 감사 · 버전 0.
문 차례 = 권한(403) → 공장(403 OTHER_FACTORY) → 보류 → 도면 고치는 중 → 카드를 쓴 파트(PART_USES_CARDS) → **여러 장** → 카드로 끝낸 칸 끄기.
끄기 · 이미 켜진 칸 · 도면 → 공정 칸 동기화(한 장씩 완료하면 마지막 장에서 칸이 켜짐)는 그대로. 도면 0 · 1장 주문은 지금 그대로(대조군).
화면 셋: 작업 시트 공정 칸(요청 0 · 칸 아래 글) · '남은 공정' 판 [<공정> 완료] 자리(도면 칸 쓴 파트와 같은 막힘 칸 "재단 0/3 · 3장 미완료") ·
PC 도면 목록 창 [모두 완료 처리] 없음(도면마다 [완료 처리]는 그대로).

되돌리면 실패: 3장 주문 켜기가 200 · 관리자만 뚫림 · 끄기가 막힘 · 마지막 장 완료로 칸이 안 켜짐 · 작업 시트가 확인 창부터 띄우거나
요청을 보냄 · 판에 [재단 완료]가 남음 · PC 창에 [모두 완료 처리]가 남음. 이름은 지어낸 값.

같은 날 뒤 결정(사장님 2026-11-27 "도면이 주, 작업 시트는 보기" — test_production_steps_view_only_1127): 문턱이 **1장 이상**으로 넓어졌다 —
1장 주문도 409(옛 대조군 "1장 주문은 지금처럼 켜짐"은 409 단언으로, 대조군은 도면 0장 주문으로 옮겼다). 글도 장 수에 맞게 한 글
"도면이 있는 주문은 도면 화면에서 완료해 주세요."로. 작업 시트 공정 칸은 도면 있는 주문이면 체크 칸 대신 보기 줄이라, 여기 화면 시험은 보기 줄
누름(요청 0) · 손 체크 칸 끄기 · 낡은 화면(체크 칸 + 서버 자료 per_sheet) · 도면 0장 칸을 본다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from html import unescape
from pathlib import Path

import pytest

from db import db_session
from foms.services.production.part_mark_gates import (
    DRAWING_REVISING,
    HOLD_ACTIVE,
    PART_USES_CARDS,
    STEP_PER_SHEET,
    STEP_SET_BY_CARDS,
    step_cell_gate,
)
from foms.services.production.part_progress import STEP_PER_SHEET_MESSAGE, WHOLE_STEP_MAX_SHEETS, per_sheet_only, step_api_extras
from foms.services.production.pc_sheet import build_part_sheet
from models import ProductionPartMark, SecurityLog
from tests.support.production_factory_seed import factory_user, mixed_order, put_mark
from tests.support.production_home_step_panel_seed import HOME, TABLET, add_order, get_html, pane_html, set_cookies
from tests.support.production_home_step_panel_seed import login as home_login
from tests.support.production_part_claim_seed import check_step, code, events, finish, fresh, login, make_order, make_user, step
from tests.support.production_steps_read import steps_read

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_per_sheet_only_node_checks.js"
MSG = "도면이 있는 주문은 도면 화면에서 완료해 주세요."
PARTS = ("cut", "edge", "assemble", "inspect")


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _audits(oid: int) -> int:
    db_session.expire_all()
    return db_session.query(SecurityLog).filter_by(target_id=oid, action="PRODUCTION_STEP_CHECKED").count()


def _snapshot(oid: int) -> tuple:
    order = fresh(oid)
    return (order.mutation_version, json.dumps(order.structured_data, sort_keys=True), len(events(oid, "PRODUCTION_STEP_CHECKED")),
            _audits(oid), db_session.query(ProductionPartMark).filter_by(order_id=oid).count())


# --------------------------------------------------------------------------- #
# 판정 한 곳
# --------------------------------------------------------------------------- #
def test_rule_and_words_are_one_place():
    assert STEP_PER_SHEET_MESSAGE == MSG and WHOLE_STEP_MAX_SHEETS == 0  # 11-27 뒤 결정 — 1장 이상
    sd = lambda n: {"drawing_current_files": [{"key": f"k{j}"} for j in range(n)], "production": {"steps": []}}  # noqa: E731
    assert [per_sheet_only(sd(n)) for n in (0, 1, 2, 5)] == [False, True, True, True]
    for n in (1, 2, 5):
        gate = step_cell_gate(sd(n), [], "cut", True)
        assert (gate.status, gate.code, gate.message, gate.extra) == (409, STEP_PER_SHEET, MSG, {"part": "cut", "left": n, "total": n})
        assert step_cell_gate(sd(n), [], "cut", False) is None  # 끄기는 된다
        assert step_api_extras(sd(n), [])["per_sheet"] == MSG
    for n in (0,):  # 대조군 — 도면 0장
        assert step_cell_gate(sd(n), [], "cut", True) is None and "per_sheet" not in step_api_extras(sd(n), [])


def test_gate_order_hold_revising_and_cards_come_first():
    base = {"drawing_current_files": [{"key": "k0"}, {"key": "k1"}, {"key": "k2"}], "production": {"steps": []}}
    assert step_cell_gate({**base, "production": {"steps": [], "hold": {"active": True}}}, [], "cut", True).code == HOLD_ACTIVE
    assert step_cell_gate({**base, "drawing_status": "RETURNED"}, [], "cut", True).code == DRAWING_REVISING
    card = type("M", (), {"part": "cut", "drawing_key": "k0", "state": "DONE"})()
    gate = step_cell_gate(base, [card], "cut", True)
    assert gate.code == PART_USES_CARDS and gate.extra["left"] == 2  # 지금 글("도면 2장이 미완료예요 …") 그대로
    all_done = [type("M", (), {"part": "cut", "drawing_key": f"k{j}", "state": "DONE"})() for j in range(3)]
    on = {**base, "production": {"steps": [{"key": "cut", "done": True, "via": "part_marks"}]}}
    assert step_cell_gate(on, all_done, "cut", False).code == STEP_SET_BY_CARDS  # 카드로 끝낸 칸 끄기 = 지금 그대로


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("who", ["lead", "admin"])
@pytest.mark.parametrize("n", [1, 2, 3])
def test_turning_on_a_multi_sheet_order_is_refused_for_everyone_without_any_write(client, who, n):
    seed = make_order(n)
    login(client, make_user("가짜반장", lead=True) if who == "lead" else make_user("가짜관리", role="ADMIN", team="CS"))
    for part in PARTS:
        before = _snapshot(seed.id)
        res = check_step(client, seed.id, part, True)
        assert res.status_code == 409, res.get_json()
        assert res.get_json() == {"success": False, "data": {"code": STEP_PER_SHEET, "part": part, "left": n, "total": n}, "error": MSG}
        assert _snapshot(seed.id) == before  # 칸 · 버전 · 이벤트 · 감사 · 표시 줄 그대로
    got = steps_read(client, seed.id)
    assert got["per_sheet"] == MSG and got["sheets"] == n


@pytest.mark.parametrize("n", [0])  # 옛 [1] 은 위 409 시험으로(11-27 뒤 결정)
def test_control_zero_or_one_sheet_turns_on_and_off_like_today(client, n):
    seed = make_order(n)
    login(client, make_user("가짜반장", lead=True))
    before = fresh(seed.id).mutation_version
    on = check_step(client, seed.id, "cut", True)
    assert on.status_code == 200 and step(seed.id, "cut")["done"] is True and step(seed.id, "cut")["via"] == "sheet"
    assert "per_sheet" not in on.get_json()["data"] and fresh(seed.id).mutation_version == before + 1
    assert [e.payload["done"] for e in events(seed.id, "PRODUCTION_STEP_CHECKED")] == [True] and _audits(seed.id) == 1
    assert check_step(client, seed.id, "cut", False).status_code == 200 and step(seed.id, "cut")["done"] is False


def test_turning_off_still_works_and_cells_already_on_stay_on(client):
    seed = make_order(3, steps_done=("cut", "edge"))
    login(client, make_user("가짜관리", role="ADMIN", team="CS"))
    assert code(check_step(client, seed.id, "edge", True)) == STEP_PER_SHEET and step(seed.id, "edge")["done"] is True  # 켜진 칸 그대로
    off = check_step(client, seed.id, "cut", False)
    assert off.status_code == 200 and step(seed.id, "cut")["done"] is False
    assert off.get_json()["data"]["per_sheet"] == MSG  # 작업 시트가 다음 누름을 요청 없이 막는 자료
    assert code(check_step(client, seed.id, "cut", True)) == STEP_PER_SHEET  # 끈 뒤 다시 켜기는 막힘


def test_finishing_sheet_by_sheet_turns_the_cell_on_at_the_last_sheet(client):
    """도면 → 공정 칸 반영은 이 문을 타지 않는다 — 한 장씩 완료하면 마지막 장에서 칸이 켜진다(``via: part_marks``)."""
    seed = make_order(3)
    login(client, make_user("가짜재단", part="cut"))
    for j in range(3):
        res = finish(client, seed, j, "cut")
        assert res.status_code == 200, res.get_json()
        assert step(seed.id, "cut")["done"] is (j == 2)
    assert step(seed.id, "cut")["via"] == "part_marks"
    assert [e.payload["done"] for e in events(seed.id, "PRODUCTION_STEP_CHECKED")] == [True]
    login(client, make_user("가짜반장", lead=True))  # 카드로 끝낸 칸 끄기 = 지금 그대로(카드에서 취소)
    assert code(check_step(client, seed.id, "cut", False)) == STEP_SET_BY_CARDS


def test_factory_and_hold_doors_still_come_first(client):
    only2 = mixed_order(2, f2=(0, 1))
    login(client, factory_user("일공장반장", lead=True))
    assert check_step(client, only2.id, "cut", True).status_code == 403  # 공장 문이 먼저(OTHER_FACTORY)
    mixed = mixed_order(3, f2=(2,))
    assert code(check_step(client, mixed.id, "cut", True)) == STEP_PER_SHEET  # 섞인 주문(2공장 장 포함 3장)
    held = make_order(3, extra={})
    order = fresh(held.id)
    order.structured_data = {**order.structured_data, "production": {**order.structured_data["production"],
                                                                      "hold": {"active": True, "reason": "자재"}}}
    db_session.commit()
    login(client, make_user("가짜반장", lead=True))
    assert code(check_step(client, held.id, "cut", True)) == HOLD_ACTIVE  # 보류 글이 먼저


# --------------------------------------------------------------------------- #
# 화면 ① 작업 시트 공정 칸
# --------------------------------------------------------------------------- #
def _sheet_parts(page: str) -> dict:
    raw = page.split('aria-label="공정"', 1)[1].split('data-foms-sheet-parts="', 1)[1].split('"', 1)[0]
    return json.loads(unescape(raw))


def _node(tmp_path, page: str, want: dict) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    path = tmp_path / f"{want['mode']}.html"
    path.write_text(page, encoding="utf-8")
    proc = subprocess.run([node, str(NODE_CHECK), str(path), json.dumps(want, ensure_ascii=False)], capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(ROOT))
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr


def test_work_sheet_shows_the_reason_without_dialog_or_request_and_turn_off_is_unchanged(client, cohort, tmp_path):
    many = make_order(3, steps_done=("edge",))
    one = make_order(1)
    zero = make_order(0)
    login(client, make_user("가짜반장", lead=True))
    set_cookies(client, TABLET)
    page = get_html(client, f"/erp/production/sheet/{many.id}")
    assert _sheet_parts(page)["per_sheet"] == MSG and _sheet_parts(page)["sheets"] == 3
    assert 'data-foms-sheet-stepmsg role="status" hidden' in page and page.count("data-foms-sheet-confirm hidden") == 1
    _node(tmp_path, page, {"key": "cut", "mode": "view"})  # 꺼진 파트 = 보기 줄(누름 = 요청 0 · 창 0)
    _node(tmp_path, page, {"key": "edge", "mode": "off"})  # 손으로 켜 둔 칸 끄기 = 지금 그대로(묻지 않고 POST)
    one_page = get_html(client, f"/erp/production/sheet/{one.id}")
    assert _sheet_parts(one_page)["per_sheet"] == MSG  # 1장 주문도(11-27 뒤 결정)
    _node(tmp_path, one_page, {"key": "cut", "mode": "view"})
    zero_page = get_html(client, f"/erp/production/sheet/{zero.id}")
    assert "per_sheet" not in _sheet_parts(zero_page)  # 대조군 — 도면 0장 자료 그대로
    _node(tmp_path, zero_page, {"key": "cut", "mode": "zero"})
    _node(tmp_path, zero_page, {"key": "edge", "mode": "stale", "msg": MSG})  # 낡은 화면(체크 칸 + 새 자료) = 칸 아래 서버 글 · 요청 0


def test_work_sheet_js_contract():
    parts = (ROOT / "static/js/production/foms-production-sheet-parts.js").read_text(encoding="utf-8")
    assert "if (info && info.per_sheet && !(part && part.uses_cards) && stepMsg(page, info.per_sheet))" in parts  # 서버 글 그대로 · 글 칸 없는 화면은 서버가 답한다
    assert "code !== 'STEP_PER_SHEET'" in parts  # 낡은 화면에서 보낸 켜기의 409 도 칸 아래 글로
    assert MSG not in parts  # 글은 서버 한 곳
    for rel in ("templates/production/sheet.html",):  # 칸반 본문(옆 시트 셋)은 2026-11-27 옛 보드와 함께 지움
        assert "foms-production-sheet-parts.js') }}?v=20261128e" in (ROOT / rel).read_text(encoding="utf-8"), rel
    assert (ROOT / "templates/production/partials/home_scripts.html").read_text(encoding="utf-8").count(
        "foms-production-sheet-parts.js') }}?v=20261128e") == 2
    assert len(parts.splitlines()) <= 300


# --------------------------------------------------------------------------- #
# 화면 ② '남은 공정' 판 · 줄
# --------------------------------------------------------------------------- #
def test_my_steps_panel_and_rows_show_the_same_block_as_card_parts(client, cohort):
    many = add_order("가짜여러장", 1, pngs=3)
    one = add_order("가짜한장", 2, pngs=0)  # 대조군 — 도면 0장(11-27 뒤 결정: 1장 주문도 막힘)
    used = add_order("가짜카드집", 3, pngs=3)
    db_session.add(ProductionPartMark(order_id=used.id, drawing_key=used.structured_data["drawing_current_files"][0]["key"],
                                      part="cut", state="DONE", done_by_name="김재단"))
    db_session.commit()
    home_login(client)  # 반장
    set_cookies(client, TABLET)
    html = get_html(client, HOME + "?tab=steps")
    assert f'data-foms-step-pane="{one.id}"' in html and f'data-foms-step-pane="{many.id}"' not in html  # 처음 고른 줄 = 막히지 않은 줄
    href = f"/erp/production/home?tab=parts&amp;part=cut&amp;order={many.id}"
    pane = pane_html(get_html(client, HOME + f"?tab=steps&order={many.id}"), many.id)
    assert "data-foms-step-finish" not in pane and "data-foms-sheet-parts" not in pane
    assert f'<a class="fph-sp__hold is-cards" href="{href}" data-foms-step-cards><b>재단 0/3 · 3장 미완료</b><span>{MSG}</span></a>' in pane
    row = html.split(f'data-foms-home-qrow="{many.id}"', 1)[1].split('data-foms-home-qrow="', 1)[0]
    assert '<span class="fph-qr__holdtag is-cards">재단 0/3 · 3장 미완료</span>' in row  # 줄 쪽 노란 표 — 같은 규칙
    assert f'<a class="fph-qr__hold is-cards" href="{href}" data-foms-step-cards title="{MSG}">재단 0/3 · 3장 미완료</a>' in row
    assert "data-foms-home-step-done" not in row
    used_pane = pane_html(get_html(client, HOME + f"?tab=steps&order={used.id}"), used.id)
    assert "<b>재단 1/3 · 2장 미완료</b><span>도면 2장이 미완료예요." in used_pane  # 카드를 쓴 파트 = 지금 글 그대로(먼저)
    one_pane = pane_html(html, one.id)  # 대조군 — 도면 0장 = [재단 완료](묻지 않음 — 확인 창 자료 없음)
    assert (f'data-foms-step-finish data-order-id="{one.id}" data-step-key="cut" data-step-label="재단"' in one_pane
            and "data-foms-sheet-parts" not in one_pane and ">재단 완료</button>" in one_pane)
    refused = check_step(client, many.id, "cut", True)
    assert refused.status_code == 409 and refused.get_json()["error"] in pane  # 판 글 = 서버 거절 글 그대로


# --------------------------------------------------------------------------- #
# 화면 ③ PC 도면 목록 창
# --------------------------------------------------------------------------- #
def test_pc_window_hides_check_all_for_multi_sheet_orders_and_keeps_per_sheet_buttons(client, cohort):
    sd = lambda n: {"drawing_current_files": [{"key": f"k{j}"} for j in range(n)], "production": {"steps": []}}  # noqa: E731
    for n in (1, 2, 4):  # 11-27 뒤 결정 — 1장 주문도 없음(창은 도면 1장 이상일 때만 열리니 [모두 완료 처리]는 늘 없다)
        data = build_part_sheet(sd(n), [], "cut", hold_active=False)
        assert data["all"] is False and [r["act"] for r in data["rows"]] == ["check"] * n  # 도면마다 [완료 처리] 그대로
    many, one = make_order(3), make_order(1)
    login(client, make_user("가짜관리", role="ADMIN", team="CS"))
    got = {s.id: client.get(f"/api/production/part-sheet?order_id={s.id}&part=edge").get_json()["data"] for s in (many, one)}
    assert got[many.id]["all"] is False and got[many.id]["can_write"] is True
    assert {r["act"] for r in got[many.id]["rows"]} == {"check"} and got[one.id]["all"] is False
    put_mark(many, 0, "edge", "DONE", factory_user("김엣지", part="edge"))  # 도면마다 [완료 처리]는 그대로 — 한 장 완료
    assert check_step(client, many.id, "edge", True).status_code == 409 and step(many.id, "edge")["done"] is False
