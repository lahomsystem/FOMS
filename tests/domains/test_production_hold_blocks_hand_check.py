"""보류 중에는 공정 칸 통째 체크도 막는다(사장님 2026-11-24 "보류 중에는 통째 체크도 막기").

도면 한 장 누름(``order_gate`` 409 ``HOLD_ACTIVE``)과 같은 규칙 · 같은 글을 공정 칸 손 체크 길(``POST …/production/steps``)에도.
켜기만 막고 끄기(체크 해제)는 보류 중에도 된다(도면 쪽 ``ALLOWED_WHILE_BLOCKED`` 와 같은 뜻). 막히면 쓰기 · 이벤트 · 버전 변화 없음.
닿는 자리: 작업 시트(태블릿 · PC) 공정 칸 · '내 공정' [끝] · 옆 시트 · PC 도면 목록 창 [모두 체크] — 모두 같은 공정 API 를 쓴다.
PC 목록 창은 서버 값 ``all`` 이 보류면 거짓(단추 안 보임). '도면 고치는 중'도 2026-11-25 부터 같다(test_production_revising_blocks_steps.py).

되돌리면 실패: 보류 주문 켜기가 200 · 끄기가 409 · PC ``all`` 참. 대조군: 보류 아닌 주문 · 보류를 푼 주문은 그대로 켜진다.
"""
from __future__ import annotations

import pytest

from db import db_session
from foms.services.production.part_mark_gates import HOLD_ACTIVE, HOLD_MESSAGE, step_cell_gate
from foms.services.production.pc_sheet import build_part_sheet
from models import Order, OrderEvent
from tests.domains.test_production_pc_sheet import _login, _order, _user

STEPS = "/api/orders/{}/production/steps"


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _state(order_id: int) -> tuple[dict, int, int]:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    steps = {s["key"]: s["done"] for s in order.structured_data["production"]["steps"]}
    events = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="PRODUCTION_STEP_CHECKED").count()
    return steps, int(order.mutation_version or 0), events


def _hold(order_id: int, active: bool) -> None:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    sd = dict(order.structured_data)
    sd["production"] = dict(sd["production"], hold={"active": active, "reason": "자재 기다림" if active else ""})
    order.structured_data = sd
    db_session.commit()


def test_gate_refuses_turning_on_while_on_hold_with_the_card_message():
    sd = {"drawing_current_files": [{"key": "k1"}], "production": {"hold": {"active": True}, "steps": []}}
    gate = step_cell_gate(sd, [], "cut", True)
    assert (gate.status, gate.code, gate.message) == (409, HOLD_ACTIVE, HOLD_MESSAGE)
    assert HOLD_MESSAGE == "보류된 주문이라 지금은 못 눌러요. 보류가 풀리면 다시 돼요."
    assert step_cell_gate(sd, [], "cut", False) is None  # 끄기는 된다
    assert step_cell_gate({**sd, "production": {"steps": []}}, [], "cut", True) is None  # 대조군: 보류 아님
    revising = {**sd, "production": {"steps": []}, "drawing_status": "RETURNED"}
    assert step_cell_gate(revising, [], "cut", True).code == "DRAWING_REVISING"  # 도면 고치는 중도 보류처럼(사장님 2026-11-25)


def test_hand_check_on_held_order_is_refused_without_write(client):
    oid = _order("오세린", 2, hold="자재 기다림").id
    _login(client, _user("반장"), {"foms_ptr": "coarse"})
    before = _state(oid)
    res = client.post(STEPS.format(oid), json={"key": "cut", "done": True})
    body = res.get_json()
    assert res.status_code == 409 and body["data"]["code"] == HOLD_ACTIVE and body["error"] == HOLD_MESSAGE
    assert body["success"] is False
    assert _state(oid) == before  # 칸 · 버전 · 이벤트 그대로


def test_uncheck_still_works_while_on_hold_and_check_works_after_release(client):
    oid = _order("남궁하늘", 1, done=("cut",), hold="자재 기다림").id  # 도면 1장(여러 장은 켜기 자체가 막힘 — 사장님 2026-11-27)
    _login(client, _user("반장"), {"foms_ptr": "coarse"})
    res = client.post(STEPS.format(oid), json={"key": "cut", "done": False})
    assert res.status_code == 200 and res.get_json()["success"] is True
    steps, _version, events = _state(oid)
    assert steps["cut"] is False and events == 1
    assert client.post(STEPS.format(oid), json={"key": "cut", "done": True}).status_code == 409
    _hold(oid, False)  # 보류 풀면 다시 된다
    res = client.post(STEPS.format(oid), json={"key": "cut", "done": True})
    assert res.status_code == 200 and _state(oid)[0]["cut"] is True


def test_order_not_on_hold_is_unchanged(client):
    oid = _order("황보민재", 1).id  # 도면 1장(여러 장은 켜기 자체가 막힘 — 사장님 2026-11-27)
    _login(client, _user("반장"), {"foms_ptr": "coarse"})
    res = client.post(STEPS.format(oid), json={"key": "edge", "done": True})
    assert res.status_code == 200 and _state(oid)[0]["edge"] is True


def test_admin_is_refused_too(client):
    oid = _order("제갈하늘", 2, hold="자재 기다림").id
    _login(client, _user("정관리", role="ADMIN", team="CS"), {"foms_ptr": "coarse"})
    res = client.post(STEPS.format(oid), json={"key": "inspect", "done": True})
    assert res.status_code == 409 and res.get_json()["data"]["code"] == HOLD_ACTIVE


def test_pc_sheet_hides_check_all_on_held_order():
    sd = {"drawing_current_files": [{"key": "k1"}], "production": {"steps": []}}  # 도면 1장(여러 장은 늘 거짓 — 사장님 2026-11-27)
    assert build_part_sheet(sd, [], "cut", hold_active=False)["all"] is True  # 대조군
    held = build_part_sheet(sd, [], "cut", hold_active=True)
    assert held["all"] is False
    assert held["hand_off"] is False  # 손 체크한 칸이 없으니 해제 단추도 없음(있으면 그대로 — 끄기는 된다)


def test_pc_sheet_api_on_held_order_has_no_check_all(client, cohort):
    order = _order("윤하린", 2, hold="자재 기다림")
    _login(client, _user("정관리", role="ADMIN", team="CS"))
    data = client.get(f"/api/production/part-sheet?order_id={order.id}&part=cut").get_json()["data"]
    assert data["all"] is False and data["can_write"] is True
