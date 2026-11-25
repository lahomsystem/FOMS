"""도면 고치는 중에는 공정 칸 통째 작업도 막는다(사장님 2026-11-25 "보류처럼 막기").

보류를 막는 문이 있는 곳마다 같이 — 같은 자리 · 같은 방식 · 같은 차례(보류가 먼저). 거절 code ``DRAWING_REVISING`` · 글은 도면 한 장
누름과 같은 ``REVISING_MESSAGE``(새 글 없음). 켜기(작업 완료)만 막고 끄기(작업 취소)는 된다(보류와 같다 — ``ALLOWED_WHILE_BLOCKED``).
막히면 칸 · 버전 · 이벤트 그대로. 관리자도 같다(공정 칸 길에는 관리자 뚫기가 없다 — 보류와 같음).
화면: PC 도면별 창 [모두 완료 처리] 안 보임 · '내 공정' 줄 · 판 · PC 줄 [<공정> 완료] 대신 "도면 고치는 중"(보류 "보류" 자리와 같은 꼴),
'끝내면 다음은' · 처음 고른 줄에서 건너뜀. 작업 시트 · 폰 공정 시트는 보류처럼 서버 거절 글을 그대로 보인다.

되돌리면 실패: 도면 고치는 중 켜기가 200 · 끄기가 409 · PC ``all`` 참 · '내 공정'에 [끝]이 남음. 대조군: 새 도면이 온 주문은 다시 된다.
"""
from __future__ import annotations

import re
import time

import pytest

from db import db_session
from foms.services.production.home_step_panel import attach_step_panels
from foms.services.production.part_mark_gates import (
    DRAWING_REVISING,
    HOLD_ACTIVE,
    HOLD_MESSAGE,
    REVISING_MESSAGE,
    order_gate,
    step_cell_gate,
)
from foms.services.production.pc_sheet import build_part_sheet
from models import Order
from tests.domains.test_production_hold_blocks_hand_check import STEPS, _state
from tests.domains.test_production_pc_sheet import _login, _order, _user
from tests.support.production_home_step_panel_seed import HOME, TABLET, add_order, get_html, login, pane_html, queue_html

SD = {"drawing_current_files": [{"key": "k1"}], "production": {"steps": []}}


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _revise(order_id: int, status: str = "RETURNED") -> None:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    order.structured_data = {**order.structured_data, "drawing_status": status}
    db_session.commit()


@pytest.mark.parametrize("sd, on, off_card", [
    ({**SD, "production": {"steps": [], "hold": {"active": True}}}, (HOLD_ACTIVE, HOLD_MESSAGE), "HOLD_ACTIVE"),
    ({**SD, "drawing_status": "RETURNED"}, (DRAWING_REVISING, REVISING_MESSAGE), "DRAWING_REVISING"),
    ({**SD, "drawing_status": "TRANSFERRED"}, (DRAWING_REVISING, REVISING_MESSAGE), "DRAWING_REVISING"),
    ({**SD, "drawing_status": "RETURNED", "production": {"steps": [], "hold": {"active": True}}}, (HOLD_ACTIVE, HOLD_MESSAGE), "HOLD_ACTIVE"),
], ids=["hold", "returned", "transferred", "both-hold-first"])
def test_step_cell_gate_is_the_same_table_as_the_card_gate(sd, on, off_card):
    gate = step_cell_gate(sd, [], "cut", True)
    assert (gate.status, gate.code, gate.message) == (409, *on)
    assert order_gate(sd, "done").code == off_card  # 도면 한 장 누름과 같은 차례 · 같은 코드
    assert step_cell_gate(sd, [], "cut", False) is None and order_gate(sd, "undo") is None  # 끄기 · 완료 취소는 된다
    assert step_cell_gate({**SD, "drawing_status": "CONFIRMED"}, [], "cut", True) is None  # 대조군: 새 도면이 옴


@pytest.mark.parametrize("who", ["반장", "관리자"])
def test_turning_on_while_revising_is_refused_without_write_and_turning_off_works(client, who):
    oid = _order("가짜고침", 2, done=("edge",)).id
    _revise(oid)
    user = _user("반장") if who == "반장" else _user("정관리", role="ADMIN", team="CS")
    _login(client, user, {"foms_ptr": "coarse"})
    before = _state(oid)
    res = client.post(STEPS.format(oid), json={"key": "cut", "done": True})
    body = res.get_json()
    assert res.status_code == 409 and body["data"]["code"] == DRAWING_REVISING and body["error"] == REVISING_MESSAGE
    assert _state(oid) == before  # 칸 · 버전 · 이벤트 그대로
    res = client.post(STEPS.format(oid), json={"key": "edge", "done": False})  # 작업 취소는 된다(보류와 같다)
    assert res.status_code == 200 and _state(oid)[0]["edge"] is False
    _revise(oid, "CONFIRMED")  # 새 도면이 오면 다시 된다
    assert client.post(STEPS.format(oid), json={"key": "cut", "done": True}).status_code == 200


def test_pc_sheet_hides_all_while_revising_but_keeps_turn_off():
    assert build_part_sheet(SD | {"drawing_current_files": [{"key": "a"}, {"key": "b"}]}, [], "cut", hold_active=False)["all"] is True
    sd = {"drawing_current_files": [{"key": "a"}, {"key": "b"}], "drawing_status": "RETURNED",
          "production": {"steps": [{"key": "edge", "label": "엣지", "done": True, "at": None, "by_name": "박반장", "via": "sheet"}]}}
    assert build_part_sheet(sd, [], "cut", hold_active=False)["all"] is False
    assert build_part_sheet(sd, [], "edge", hold_active=False)["hand_off"] is True  # [모두 완료 취소]는 남는다(끄기는 된다)


def test_pc_sheet_api_while_revising_has_no_all(client, cohort):
    order = _order("가짜창", 2)
    _revise(order.id)
    _login(client, _user("정관리", role="ADMIN", team="CS"))
    data = client.get(f"/api/production/part-sheet?order_id={order.id}&part=cut").get_json()["data"]
    assert data["all"] is False and data["can_write"] is True


def test_my_steps_rows_panel_and_pc_rows_show_the_reason_instead_of_finish(client, cohort):
    first = add_order("가짜고침줄", 1)
    _revise(first.id)
    free = add_order("가짜다음줄", 2)
    login(client)  # 반장
    client.set_cookie("foms_ptr", "coarse", domain="localhost")
    phone = queue_html(get_html(client, HOME + "?tab=steps"), "cut")  # 판 없는 꼴(폰 · 세로)
    row = phone.split(f'data-foms-home-qrow="{first.id}"', 1)[1].split('data-foms-home-qrow="', 1)[0]
    assert '<span class="fph-qr__hold">도면 고치는 중</span>' in row and "data-foms-home-step-done" not in row
    assert f'<div class="fph-qr is-revise" data-foms-home-qrow="{first.id}">' in phone  # 보류 줄처럼 흐림(2026-11-25 검토)
    assert f'is-revise" data-foms-home-qrow="{free.id}"' not in phone  # 대조군: 막히지 않은 줄은 흐리지 않는다
    assert f'data-foms-home-step-done data-order-id="{free.id}"' in phone  # 대조군: 막히지 않은 줄은 [끝]
    for key, value in TABLET.items():
        client.set_cookie(key, value, domain="localhost")
    html = get_html(client, HOME + "?tab=steps")
    assert 'data-foms-step-pane="%d"' % free.id in html and 'data-foms-step-pane="%d"' % first.id not in html  # 처음 고른 줄 = 막히지 않은 줄
    pane = pane_html(get_html(client, f"{HOME}?tab=steps&order={first.id}"), first.id)
    assert f'<div class="fph-sp__hold"><b><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>도면 고치는 중</b><span>{REVISING_MESSAGE}</span></div>' in pane  # 보류와 같은 멈춤 그림
    assert f'<section class="fph-sp is-revise" data-foms-step-pane="{first.id}"' in get_html(client, f"{HOME}?tab=steps&order={first.id}")
    assert "data-foms-step-finish" not in pane
    for key, value in {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}.items():
        client.set_cookie(key, value, domain="localhost")
    client.set_cookie("foms_prod_edit", str(int(time.time())), domain="localhost", path="/erp/production")  # [고치기] 켬(2시간 안)
    pc = get_html(client, HOME + "?tab=steps")
    pc_row = pc.split(f'data-foms-home-qrow="{first.id}"', 1)[1].split('data-foms-home-qrow="', 1)[0]
    assert '<span class="fpc-hold">도면 고치는 중</span>' in pc_row and "data-foms-home-step-done" not in pc_row
    assert re.search(rf'<div class="fpc-q[^"]* is-revise[^"]*" data-foms-home-qrow="{first.id}"', pc)  # PC 줄도 보류(is-hold)와 같은 자리에 표지
    assert f'data-foms-home-step-done data-order-id="{free.id}"' in pc  # 대조군: [고치기] 켬이라 막히지 않은 줄은 [끝]


def test_next_and_first_pick_skip_revising_rows_like_hold():
    revise = {"id": 1, "revise_block": {"text": "도면 고치는 중"}, "structured_data": {}}
    hold = {"id": 2, "hold_active": True, "structured_data": {}}
    ok = {"id": 3, "structured_data": {}, "customer_name": "가짜"}
    queues = {"queues": [{"key": "cut", "label": "재단", "rows": [revise, hold, ok]}]}
    attach_step_panels(queues, None)
    assert queues["queues"][0]["selected_id"] == 3
    queues = {"queues": [{"key": "cut", "label": "재단", "rows": [ok, revise, hold]}]}
    attach_step_panels(queues, None)
    assert queues["queues"][0]["panels"][0]["next_id"] is None  # 뒤가 모두 막혔으면 '다음' 없음


def test_revising_rows_look_like_held_rows_and_do_not_come_next():
    """보류에만 붙던 모양 · 줄 차이를 도면 고치는 중에도(2026-11-25 검토 — 사장님 "보류처럼"): 줄 흐림(같은 규칙) · '곧 올 것'에서 빠짐."""
    from foms.services.production_home_read_model import production_home_step_queues

    css = (__import__("pathlib").Path(__file__).resolve().parents[2] / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-qr.is-hold, .fph-qr.is-revise { opacity: .7; }" in css
    steps = [{"key": k, "label": k, "done": False, "now": k == "cut"} for k in ("cut", "edge", "assemble", "inspect")]

    def row(i, **extra):
        return {"id": i, "home_view": "prod", "home_has_run": True, "raw_stage": "PRODUCTION", "home_steps": steps,
                "structured_data": {"production": {"steps": steps}, **extra.pop("sd", {})}, **extra}

    rows = [row(1), row(2, hold_active=True), row(3, sd={"drawing_status": "RETURNED"})]
    queues = production_home_step_queues(rows)
    cut, edge = queues["queues"][0], queues["queues"][1]
    assert [r["id"] for r in cut["rows"]] == [1, 2, 3] and cut["rows"][2]["revise_block"]["text"] == "도면 고치는 중"
    assert [r["id"] for r in edge["incoming"]] == [1]  # 보류 · 도면 고치는 중은 멈춰 있어 다음 공정으로 오지 않는다
