"""도면 고치는 중에는 [제작 완료] · [N공장 완료]도 막는다(사장님 2026-11-25 "제작 완료도 막기").

보류(``HOLD_ACTIVE``)가 막는 제작 완료 길마다 같은 자리 · 같은 꼴 — 거절 code ``DRAWING_REVISING`` · 글은 도면 한 장 누름 · 공정 칸과 같은
``REVISING_MESSAGE``(새 글 없음). 막히면 단계 · 버전 · 이벤트 · 회차 · 공장 표지 · 보류가 그대로(아무것도 안 씀).

- ``POST …/production/complete``(작업 시트 · 옆 시트 · 옛 보드 · 칸반 · PC 창 "제작 완료할까요?" · 도면 판 "제작 완료할까요?"가 모두
  부른다): 보류 바로 뒤. ``release_hold`` 여도 막히면 보류를 풀지 않는다. 관리자 ``admin_override``(사유)는 보류처럼 뚫는다(게이트 이름
  ``DRAWING_REVISING`` · 타임라인 "도면 고치는 중").
- ``POST …/production/factory-done``(공장 단추 · 도면 판 "2공장 제작 완료할까요?"): 보류 바로 뒤 — 마지막 공장(= 주문 제작 완료)도.
  관리자 뚫기 길은 보류처럼 없다.
- 검수 카드 완료 뒤 "제작 완료할까요?" · "N공장 제작 완료할까요?"(``order_ready`` · ``factory_ready``)는 보류처럼 묻지 않는다.
- 취소 쪽은 보류와 같다: [제작 취소] · [완료 취소] · [N공장 완료 취소]는 된다.

되돌리면 실패: 도면 고치는 중 제작 완료가 200 · 공장 표지가 써짐 · 보류가 풀림 · 취소가 막힘 · 관리자 뚫기 기록에 게이트가 없음.
대조군: 새 도면이 온 주문(CONFIRMED)은 그대로 완료된다. 날짜는 쓰지 않는다(시공일 없는 준비물).
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.order_event_display import translate_admin_override_gates
from foms.services.orders.admin_override import ADMIN_OVERRIDE_EVENT, GATE_CODES, GATE_DRAWING_REVISING
from foms.services.production.factory_home import factory_ready
from foms.services.production.part_mark_gates import DRAWING_REVISING, HOLD_MESSAGE, REVISING_MESSAGE
from foms.services.production.part_mark_write import order_ready
from models import Order, OrderEvent, ProductionRun
from tests.support.production_factory_seed import factory_user, mixed_order, put_mark, set_factory_done
from tests.support.production_part_claim_seed import fresh, login, make_order
from tests.support.production_steps_seed import inspected_steps, mark_order_inspected

PARTS = ("cut", "edge", "assemble", "inspect")
REASON = "시험 — 도면 고치는 중 건너뜀"


def _patch(oid: int, *, status: str | None = None, hold: bool = False) -> None:
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    if status is not None:
        sd["drawing_status"] = status
    if hold:
        sd.setdefault("production", {})["hold"] = {"active": True, "reason": "자재 기다림"}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def _snapshot(oid: int) -> tuple:
    order = fresh(oid)
    sd = order.structured_data or {}
    events = db_session.query(OrderEvent).filter_by(order_id=oid).count()
    runs = db_session.query(ProductionRun).filter_by(order_id=oid, is_current=True).count()
    production = sd.get("production") or {}
    return (order.erp_stage_code, int(order.mutation_version or 0), events, runs, production.get("factory_done"),
            (production.get("hold") or {}).get("active"))


def _ready_order(*, status: str | None = "RETURNED", hold: bool = False) -> int:
    """생산 단계 · 공정 4칸 모두 끝(검수까지) · 확정 도면 2장 — 도면 상태만 바꾼다."""
    seed = make_order(2)
    mark_order_inspected(seed.id)
    _patch(seed.id, status=status, hold=hold)
    return seed.id


def _complete(client, oid: int, body: dict | None = None):
    return client.post(f"/api/orders/{oid}/production/complete", json=body or {})


def _factory(client, oid: int, factory: int, done: bool = True):
    return client.post(f"/api/orders/{oid}/production/factory-done", json={"factory": factory, "done": done})


@pytest.fixture
def boss():
    return factory_user("가짜반장", lead=True)


@pytest.mark.parametrize("status", ["RETURNED", "TRANSFERRED"])
def test_complete_is_refused_while_revising_without_any_write(client, boss, status):
    oid = _ready_order(status=status)
    login(client, boss)
    before = _snapshot(oid)
    res = _complete(client, oid)
    body = res.get_json()
    assert res.status_code == 409 and body["success"] is False
    assert (body["code"], body["message"]) == (DRAWING_REVISING, REVISING_MESSAGE)
    assert _snapshot(oid) == before  # 단계 · 버전 · 이벤트 · 회차 그대로
    _patch(oid, status="CONFIRMED")  # 대조군: 새 도면이 오면 된다
    assert _complete(client, oid).status_code == 200 and fresh(oid).erp_stage_code == "CONSTRUCTION"


def test_same_place_as_hold_hold_first_and_release_hold_does_not_release(client, boss):
    held = _ready_order(status=None, hold=True)
    login(client, boss)
    assert _complete(client, held).get_json()["code"] == "HOLD_ACTIVE"  # 같은 자리의 보류 문(지금 그대로)
    both = _ready_order(status="RETURNED", hold=True)
    assert _complete(client, both).get_json()["code"] == "HOLD_ACTIVE"  # 차례 = 보류가 먼저(도면 한 장 누름과 같다)
    before = _snapshot(both)
    res = _complete(client, both, {"release_hold": True})  # 보류를 풀며 완료 — 도면 고치는 중이면 아무것도 안 쓴다
    assert res.status_code == 409 and res.get_json()["code"] == DRAWING_REVISING
    assert _snapshot(both) == before and before[-1] is True  # 보류도 그대로


def test_admin_override_punches_it_like_hold_and_records_the_gate(client):
    admin = factory_user("가짜관리", role="ADMIN", team="CS")
    login(client, admin)
    oid = _ready_order()
    res = _complete(client, oid)
    assert res.status_code == 409 and res.get_json()["code"] == DRAWING_REVISING  # 관리자도 사유 없이는 막힌다(보류와 같다)
    res = _complete(client, oid, {"admin_override": True, "override_reason": REASON})
    assert res.status_code == 200 and fresh(oid).erp_stage_code == "CONSTRUCTION"
    used = db_session.query(OrderEvent).filter_by(order_id=oid, event_type=ADMIN_OVERRIDE_EVENT).all()
    assert len(used) == 1 and used[0].payload["gates"] == [DRAWING_REVISING] and used[0].payload["reason"] == REASON
    assert GATE_DRAWING_REVISING == DRAWING_REVISING and GATE_DRAWING_REVISING in GATE_CODES
    assert translate_admin_override_gates({"gates": [DRAWING_REVISING]}) == "도면 고치는 중"  # 화면에 이미 있는 말
    held = _ready_order(status=None, hold=True)  # 대조군: 보류도 같은 길로 뚫린다
    assert _complete(client, held, {"admin_override": True, "override_reason": REASON}).status_code == 200
    login(client, factory_user("가짜매니저", role="MANAGER"))  # 관리자가 아니면 사유를 실어도 못 뚫는다(지금 규칙)
    other = _ready_order()
    assert _complete(client, other, {"admin_override": True, "override_reason": REASON}).status_code == 403


def test_factory_done_is_refused_like_hold_including_the_last_factory(client):
    insp1, insp2 = factory_user("가짜검수", part="inspect"), factory_user("가짜검수이", factory=2, part="inspect")
    seed = mixed_order(3, f2=(2,))
    for j in range(3):
        for part in PARTS:
            put_mark(seed, j, part, "DONE", insp1)
    _patch(seed.id, status="RETURNED")
    login(client, insp2)
    before = _snapshot(seed.id)
    res = _factory(client, seed.id, 2)
    body = res.get_json()
    assert res.status_code == 409 and (body["data"]["code"], body["error"]) == (DRAWING_REVISING, REVISING_MESSAGE)
    assert _snapshot(seed.id) == before and before[4] is None  # 표지 안 씀
    set_factory_done(seed.id, 2, [seed.keys[2]])  # 2공장은 이미 완료 → 1공장이 마지막(= 주문 제작 완료)
    login(client, insp1)
    before = _snapshot(seed.id)
    res = _factory(client, seed.id, 1)
    assert res.status_code == 409 and res.get_json()["data"]["code"] == DRAWING_REVISING and _snapshot(seed.id) == before
    _patch(seed.id, status=None, hold=True)  # 같은 자리의 보류 문 — 보류가 먼저
    assert _factory(client, seed.id, 1).get_json()["error"] == HOLD_MESSAGE
    _patch(seed.id, status="CONFIRMED")  # 대조군
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    sd["production"]["hold"] = {"active": False}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    assert _factory(client, seed.id, 1).status_code == 200 and fresh(seed.id).erp_stage_code == "CONSTRUCTION"


def test_cancels_still_work_while_revising_like_hold(client, boss):
    """[제작 취소] · [완료 취소] · [N공장 완료 취소] — 보류 중에 되는 길은 도면 고치는 중에도 된다(보류와 같은 규칙)."""
    login(client, boss)
    for hold in (True, False):
        oid = _ready_order(status=None if hold else "RETURNED", hold=hold)
        assert client.post(f"/api/orders/{oid}/production/cancel", json={}).status_code == 200, hold
    done = _ready_order(status="CONFIRMED")
    assert _complete(client, done).status_code == 200
    _patch(done, status="RETURNED")  # 제작 완료 뒤 도면 고치는 중
    assert client.post(f"/api/orders/{done}/production/uncomplete", json={}).status_code == 200
    assert fresh(done).erp_stage_code == "PRODUCTION"
    seed = mixed_order(3, f2=(2,))
    set_factory_done(seed.id, 2, [seed.keys[2]])
    _patch(seed.id, status="RETURNED")
    login(client, factory_user("가짜반장이", factory=2, lead=True))
    res = _factory(client, seed.id, 2, done=False)
    assert res.status_code == 200 and _snapshot(seed.id)[4] is None


def test_card_prompts_do_not_ask_while_revising_like_hold():
    """검수 카드 완료 뒤 "제작 완료할까요?" · "2공장 제작 완료할까요?" — 보류처럼 묻지 않는다(판정 = 제작 완료 API 와 같은 술어)."""
    user = SimpleNamespace(id=1, name="가짜", role="ADMIN", team="CS", production_part=None, production_lead=None,
                           production_factory=None)
    req = SimpleNamespace(part="inspect", order_id=7)
    steps = inspected_steps()

    def order(extra, hold=False):
        production = {"steps": steps, **({"hold": {"active": True}} if hold else {})}
        return Order(id=7, status="PRODUCTION", erp_stage_code="PRODUCTION", is_erp_order=True,
                     structured_data={"workflow": {"stage": "PRODUCTION"}, "production": production, **extra})  # 저장 안 함

    assert order_ready(order({}), [], user, req, "DONE") == {"order_id": 7}  # 대조군: 막히지 않으면 묻는다
    assert order_ready(order({"drawing_status": "RETURNED"}), [], user, req, "DONE") is None
    assert order_ready(order({"drawing_status": "TRANSFERRED"}), [], user, req, "DONE") is None
    assert order_ready(order({}, hold=True), [], user, req, "DONE") is None  # 보류와 같다
    entry = {"key": "k"}
    assert factory_ready({}, entry, [], user, order_id=7, part="inspect", target="DONE", stage="PRODUCTION", hold=True) is None
