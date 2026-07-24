"""생산 보류 토글 API 계약 (POST /api/orders/<id>/production/hold).

STATE-OVERLAY-01: 옛 표시-전용 배지에서 **canonical HOLD_ORDER/RELEASE_HOLD 전이**로 정본화.
active=True→HOLD_ORDER(NONE→HELD), active=False→RELEASE_HOLD(HELD→NONE)를
order_transition_service 로 실행한다. 따라서 이 route 계약은 canonical 로 강화된다:

- hold ON: canonical ``workflow.hold.active=True`` + legacy projection ``order.status='ON_HOLD'``
  + main stage(``erp_stage_code``/``workflow.stage``) 불변 + mutation_version++ + idempotency
  receipt(STATE_HOLD_ORDER) + legacy ``OrderEvent`` ``ORDER_HELD`` + 같은 tx outbox
  ``HOLD_NOTIFICATION``, 그리고 전이기 dual-write 로 ``production.hold`` 배지 미러.
- hold OFF: ``workflow.hold.active=False`` + status 가 main 으로 복귀 + ``ORDER_HOLD_RELEASED``.
- 멱등: **token(idempotency_key) 기반** — same key 재요청은 전이 1회(replay). 같은 방향을
  key 없이 재호출하면 전이 엔진이 409(상태 불변)로 거부한다(옛 state-기반 멱등을 대체).
- 권한: PRODUCTION_EDIT(ADMIN·CS/SALES/PRODUCTION 허용, DRAWING 403).
- 잘못된 payload(active 비-bool) 400, 없는 주문 404.

fixture 패턴은 test_state_prod.py 를 준용한다(SQLite domain lane; PG dev env 도 동일 계약).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    User,
)


def _make_user(username: str, *, role: str = "STAFF", team: str | None = None) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username} 이름",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order() -> Order:
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="보류 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="PRODUCTION",
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "PRODUCTION"}},
        erp_stage_code="PRODUCTION",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_hold_activate_is_canonical_transition(client):
    """hold ON: canonical workflow.hold + status→ON_HOLD 투영, main 불변, version++/receipt/event/outbox."""
    user = _make_user("hold_admin", role="ADMIN")
    user_name = user.name
    _login(client, user)
    order_id = _make_order().id

    resp = client.post(
        f"/api/orders/{order_id}/production/hold",
        json={"active": True, "reason": "자재 입고 지연"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    hold = data["data"]["hold"]
    assert hold["active"] is True
    assert hold["reason"] == "자재 입고 지연"
    assert hold["at"]
    assert hold["by_name"] == user_name

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    # canonical overlay 축 소유 + main stage 불변.
    assert saved.structured_data["workflow"]["hold"]["active"] is True
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"  # main 불변
    assert saved.erp_stage_code == "PRODUCTION"  # main 불변
    # legacy projection(ON_HOLD>logistics>main)상 HELD 동안 status=ON_HOLD.
    assert saved.status == "ON_HOLD"
    # 전이기 dual-write: production.hold 배지 미러(STATE-PROD 게이트·칸반 보존).
    assert saved.structured_data["production"]["hold"]["active"] is True
    # 전이 엔진이 mutation_version 을 1회 bump(1→2).
    assert saved.mutation_version == 2

    # legacy OrderEvent parity: ORDER_HELD 1건(옛 PRODUCTION_HOLD_TOGGLED 대체).
    held = db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="ORDER_HELD").all()
    assert len(held) == 1
    assert held[0].payload["command"] == "HOLD_ORDER"
    assert held[0].payload["to"] == "HELD"
    # receipt(REV-00) 1건 + 같은 tx outbox(HOLD_NOTIFICATION) 1건.
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_HOLD_ORDER").count() == 1
    outbox = db_session.query(DomainSideEffectOutbox).filter_by(effect_type="HOLD_NOTIFICATION").all()
    assert len(outbox) == 1 and outbox[0].source_domain == "ORDER_EVENT"
    assert outbox[0].order_event_id == held[0].id


def test_hold_release_returns_status_to_main(client):
    """hold OFF: workflow.hold 해제 + status 가 main 으로 복귀 + ORDER_HOLD_RELEASED, 배지 미러 해제."""
    user = _make_user("hold_admin2", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "x"})
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": False})
    assert resp.status_code == 200
    hold = resp.get_json()["data"]["hold"]
    assert hold["active"] is False
    assert hold["reason"] == ""
    assert hold["at"] is None
    assert hold["by_name"] is None

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["workflow"]["hold"]["active"] is False
    assert saved.structured_data["production"]["hold"]["active"] is False
    assert saved.status == "PRODUCTION"  # HELD 해제 → main 으로 복귀
    assert saved.erp_stage_code == "PRODUCTION"  # main 내내 불변
    released = db_session.query(OrderEvent).filter_by(
        order_id=order_id, event_type="ORDER_HOLD_RELEASED"
    ).all()
    assert len(released) == 1
    assert saved.mutation_version == 3  # hold(1→2) + release(2→3)


def test_hold_same_key_replays_once(client):
    """token 기반 멱등: same idempotency_key 재요청 → 전이 1회(version/event 중복 0)."""
    user = _make_user("hold_admin3", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id
    body = {"active": True, "reason": "a", "idempotency_key": "hold-replay-0001"}

    r1 = client.post(f"/api/orders/{order_id}/production/hold", json=body)
    r2 = client.post(f"/api/orders/{order_id}/production/hold", json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.get_json()["data"]["hold"]["active"] is True

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 2  # 단 1회 bump
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="ORDER_HELD").count() == 1


def test_hold_reactivate_without_key_conflicts(client):
    """같은 방향(active=True) key 없이 재호출 → 409(이미 HELD, 상태 불변). 옛 state-멱등 대체."""
    user = _make_user("hold_admin3b", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id

    r1 = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "a"})
    assert r1.status_code == 200
    r2 = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "b"})
    assert r2.status_code == 409
    assert r2.get_json()["success"] is False

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 2  # 두 번째는 전이 없음(불변)
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="ORDER_HELD").count() == 1


def test_production_team_allowed(client):
    user = _make_user("hold_prod", role="STAFF", team="PRODUCTION")
    _login(client, user)
    order_id = _make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_drawing_team_forbidden(client):
    user = _make_user("hold_draw", role="STAFF", team="DRAWING")
    _login(client, user)
    order_id = _make_order().id
    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_invalid_active_returns_400(client):
    user = _make_user("hold_admin4", role="ADMIN")
    _login(client, user)
    order_id = _make_order().id
    # active 누락
    r1 = client.post(f"/api/orders/{order_id}/production/hold", json={"reason": "x"})
    assert r1.status_code == 400
    # active 비-bool
    r2 = client.post(f"/api/orders/{order_id}/production/hold", json={"active": "yes"})
    assert r2.status_code == 400


def test_missing_order_returns_404(client):
    user = _make_user("hold_admin5", role="ADMIN")
    _login(client, user)
    resp = client.post("/api/orders/999999/production/hold", json={"active": True})
    assert resp.status_code == 404
    assert resp.get_json()["success"] is False


def test_canonical_hold_event_recorded(client):
    """canonical ORDER_HELD 이벤트 1건 + payload(axis/reason) 기록, 옛 표시 이벤트는 미emit."""
    user = _make_user("hold_admin6", role="ADMIN")
    user_id = user.id
    _login(client, user)
    order_id = _make_order().id

    client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "z"})
    events = (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "ORDER_HELD")
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["axis"] == "HOLD"
    assert events[0].payload["reason"] == "z"
    assert events[0].created_by_user_id == user_id
    # 옛 표시-전용 이벤트는 이 route 에서 더 이상 emit 하지 않는다(canonical 로 대체).
    assert db_session.query(OrderEvent).filter_by(
        order_id=order_id, event_type="PRODUCTION_HOLD_TOGGLED"
    ).count() == 0
