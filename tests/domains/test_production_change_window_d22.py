"""변경 알림 기준선 D22(사용자 2026-11-11 "제작 대기 뒤 바뀐 것만").

주문이 생산(제작 대기)으로 넘어온 **뒤에** 바뀐 것만 '바뀜'으로 띄운다. 고객 컨펌을 기다리는 동안의 시공일 변경 ·
도면 재전달은 생산 단계로 넘어온 뒤에는 띄우지 않는다. 아직 컨펌 단계인 주문은 전과 같다.
규칙은 ``compute_window_start`` 한 곳 — 생산 첫 화면 · 생산 보드 · 작업 시트가 같이 쓴다.

단계 진입 이벤트는 경로마다 종류가 다르다(``STAGE_CHANGED`` 일반·일괄 · ``STAGE_OVERRIDE`` 강제 ·
``CUSTOMER_CONFIRMED`` 컨펌 끝 · ``PRODUCTION_STARTED`` 컨펌에서 바로 제작 시작) — 전부 진입으로 센다.
"""

from __future__ import annotations

import datetime
import uuid

from db import db_session
from foms.services.orders.order_transition_service import transition_order
from foms.services.production_change_alerts import collect_production_change_alerts, compute_window_start
from models import Order, OrderEvent, User

_T0 = datetime.datetime(2026, 11, 1, 0, 0, 0)  # 도면 → 컨펌 (파이프라인 진입)
_UID = 7
_H = "a" * 64


def _t(hours: int) -> datetime.datetime:
    return _T0 + datetime.timedelta(hours=hours)


def _make_order(stage: str = "PRODUCTION", sd: dict | None = None) -> Order:
    order = Order(
        received_date="2026-11-01", customer_name="기준선 고객", phone="010-1111-2222", address="Seoul",
        product="붙박이장", status=stage, manager_name="담당", is_erp_order=True,
        structured_data=sd if sd is not None else {"workflow": {"stage": stage}},
        erp_stage_code=stage, erp_stage_updated_at=_T0,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _ev(order: Order, event_type: str, payload: dict, at: datetime.datetime, uid: int | None = None) -> None:
    db_session.add(OrderEvent(order_id=order.id, event_type=event_type, payload=payload, created_at=at,
                              created_by_user_id=uid))
    db_session.commit()


def _to_confirm(order: Order) -> None:
    _ev(order, "STAGE_CHANGED", {"from": "DRAWING", "to": "CONFIRM"}, _T0)


def _to_production(order: Order, at: datetime.datetime, event_type: str = "CUSTOMER_CONFIRMED") -> None:
    _ev(order, event_type, {"command": "CUSTOMER_CONFIRM", "from": "CONFIRM", "to": "PRODUCTION"}, at)


def _cons_change(order: Order, at: datetime.datetime, to: str = "2026-11-20") -> None:
    _ev(order, "CONSTRUCTION_DATE_CHANGED", {"from": "2026-11-15", "to": to}, at)


def _alerts(order: Order, uid: int | None = _UID) -> dict:
    return collect_production_change_alerts(db_session, [order], uid)[order.id]


def _labels(items: list[dict]) -> list[str]:
    return [i["label"] for i in items]


def test_a_컨펌_때_시공일_변경은_생산_진입_뒤_안_보인다(app) -> None:
    order = _make_order()
    _to_confirm(order)
    _cons_change(order, _t(1))
    _to_production(order, _t(2))
    got = _alerts(order)
    assert got == {"alerts": [], "history": []}
    events = db_session.query(OrderEvent).filter_by(order_id=order.id).all()
    assert compute_window_start(order, events, _UID) == _t(2)


def test_b_생산_진입_뒤_시공일_변경은_보인다(app) -> None:
    order = _make_order()
    _to_confirm(order)
    _to_production(order, _t(2))
    _cons_change(order, _t(3))
    assert _labels(_alerts(order)["alerts"]) == ["시공일 변경"]


def test_c_컨펌_때_확인했어요_뒤_컨펌_중_변경도_생산_진입_뒤_안_보인다(app) -> None:
    order = _make_order()
    _to_confirm(order)
    _ev(order, "PRODUCTION_CHANGE_ACK", {}, _t(1), uid=_UID)
    _cons_change(order, _t(2))
    _to_production(order, _t(3))
    assert _alerts(order)["alerts"] == []
    assert _alerts(order, None)["alerts"] == []  # 확인 안 누른 사람도 같다


def test_d_아직_컨펌_단계인_주문은_전과_같이_보인다(app) -> None:
    order = _make_order(stage="CONFIRM")
    _to_confirm(order)
    _cons_change(order, _t(1))
    assert _labels(_alerts(order)["alerts"]) == ["시공일 변경"]


def test_d2_생산에서_컨펌으로_되돌린_주문도_컨펌_때_변경이_보인다(app) -> None:
    order = _make_order(stage="CONFIRM")
    _to_confirm(order)
    _cons_change(order, _t(1), to="2026-11-21")
    _to_production(order, _t(2))
    _ev(order, "STAGE_OVERRIDE", {"from": "PRODUCTION", "to": "CONFIRM", "mode": "regress"}, _t(3))
    _cons_change(order, _t(4))
    assert len(_alerts(order)["alerts"]) == 2  # 바닥선 없음 — 옛 기준선(파이프라인 진입) 그대로


def test_e_도면_재전달도_컨펌_때는_안_보이고_진입_뒤는_보인다(app) -> None:
    sd = {
        "workflow": {"stage": "PRODUCTION"},
        "drawing_transfer_history": [
            {"action": "TRANSFER", "transferred_at": _t(1).strftime("%Y-%m-%d %H:%M:%S"), "note": "컨펌 중"},
            {"action": "TRANSFER", "transferred_at": _t(3).strftime("%Y-%m-%d %H:%M:%S"), "note": "생산 중"},
        ],
    }
    order = _make_order(sd=sd)
    _to_confirm(order)
    _to_production(order, _t(2))
    got = _alerts(order)
    assert [i["detail"] for i in got["alerts"]] == ["생산 중"]
    assert [i["detail"] for i in got["history"]] == ["생산 중"]


def test_f_생산_진입_뒤_확인했어요는_그_뒤_변경만_남긴다(app) -> None:
    order = _make_order()
    _to_confirm(order)
    _to_production(order, _t(1))
    _cons_change(order, _t(2), to="2026-11-21")
    _ev(order, "PRODUCTION_CHANGE_ACK", {}, _t(3), uid=_UID)
    _cons_change(order, _t(4))
    got = _alerts(order)
    assert [i["to_md"] for i in got["alerts"]] == ["11/20"]
    assert [i["to_md"] for i in got["history"]] == ["11/21", "11/20"]  # 상설 이력은 진입 뒤 전부


def test_진입_이벤트_종류마다_바닥선이_선다(app) -> None:
    for event_type, payload in (
        ("STAGE_CHANGED", {"from": "고객컨펌", "to": "PRODUCTION", "bulk": True}),
        ("STAGE_OVERRIDE", {"from": "CONFIRM", "to": "CONSTRUCTION", "mode": "advance"}),
        ("PRODUCTION_STARTED", {"command": "PRODUCTION_START", "from": "CONFIRM", "to": "PRODUCTION"}),
    ):
        order = _make_order(stage="CONSTRUCTION" if payload["to"] == "CONSTRUCTION" else "PRODUCTION")
        _to_confirm(order)
        _cons_change(order, _t(1))
        _ev(order, event_type, payload, _t(2))
        assert _alerts(order)["alerts"] == [], event_type


def test_생산_안쪽_이동은_바닥선을_옮기지_않는다(app) -> None:
    order = _make_order(stage="PRODUCTION")
    _to_confirm(order)
    _to_production(order, _t(1))
    _cons_change(order, _t(2))
    # 제작 시작(run 만, 단계 그대로) · 제작 완료 · 완료 취소(시공 → 생산)
    _ev(order, "PRODUCTION_STARTED", {"from": "PRODUCTION", "to": "PRODUCTION", "run_started": True}, _t(3))
    _ev(order, "STAGE_CHANGED", {"from": "PRODUCTION", "to": "CONSTRUCTION"}, _t(4))
    _ev(order, "STAGE_CHANGED", {"from": "CONSTRUCTION", "to": "PRODUCTION"}, _t(5))
    assert _labels(_alerts(order)["alerts"]) == ["시공일 변경"]


def test_정본_엔진_컨펌_끝_전이가_남기는_이벤트로_바닥선이_선다(app) -> None:
    """엔진(``CUSTOMER_CONFIRM``)이 실제로 남기는 이벤트 종류·payload 값으로 — 지어낸 payload 가 아니다."""
    actor = User(username=f"d22_{uuid.uuid4().hex[:8]}", password="pw-not-committed", name="작업자",
                 role="STAFF", team="CS", is_active=True)
    db_session.add(actor)
    db_session.commit()
    order = _make_order(stage="CONFIRM")
    _to_confirm(order)
    _cons_change(order, _t(1))
    transition_order(
        db_session, command_id="CUSTOMER_CONFIRM", order_id=order.id, actor_user_id=actor.id,
        expected_from="CONFIRM", target_value="PRODUCTION", scope_hash=_H, request_hash=_H,
        drawing_gate_waived=True, now=_t(2),
    )
    db_session.commit()
    db_session.refresh(order)
    ev = db_session.query(OrderEvent).filter_by(order_id=order.id, event_type="CUSTOMER_CONFIRMED").one()
    assert (ev.payload["from"], ev.payload["to"]) == ("CONFIRM", "PRODUCTION")
    assert order.erp_stage_code == "PRODUCTION"
    assert _alerts(order)["alerts"] == []
    _cons_change(order, _t(3))
    assert _labels(_alerts(order)["alerts"]) == ["시공일 변경"]
