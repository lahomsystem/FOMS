"""logistics/hold overlay 전이 계약 (STATE-OVERLAY-01, SSOT §2.2·§2.2.1·§5.2).

active logistics/hold writer 와 production/tablet hold control 을 role-gated 전이 command
(HOLD_ORDER/RELEASE_HOLD/SET_LOGISTICS_STATUS)로 정본화한 뒤 overlay 계약을 고정한다:

* overlay 전이(hold ON/OFF, logistics)는 자기 축만 바꾸고 **main stage(erp_stage_code/
  workflow.stage)는 불변**이다(overlay 는 orthogonal). legacy ``order.status`` 는 projection
  규칙(DELETED>ON_HOLD>AS>logistics>main)상 파생될 뿐 main 축이 아니다.
* 전이는 order_transition_service 를 경유해 mutation_version++·idempotency receipt·legacy
  ``OrderEvent`` parity·같은 tx outbox 를 원자 기록한다(audit outcome same tx).
* **role-gated**: 권한 없는 팀은 403 이고 DB 변화 0(version/event/receipt/outbox 0).
* **wrong-stage**: 비인접 overlay 전이(예: 보류 아님에서 release)는 409 이고 DB 변화 0.
* **replay**: same idempotency_key 재요청은 전이 1회(version/event 중복 0).
* **typed only**: logistics 엔드포인트는 물류 enum 만 받고 generic status/delete/AS 값은 거부한다
  (전이 엔진이 InvalidTransition). overlay 전이는 delete/AS/construction 축을 건드리지 않는다.

fixture 패턴은 test_state_prod.py 를 준용한다(SQLite domain lane; PG dev env 도 동일 계약,
DSN 은 env-only). transition_order 의 FOR UPDATE 는 SQLite 에서 no-op 이다.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.state_axes import read_state_axes
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    OrderMutationReceipt,
    User,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
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


def _make_order(stage_code: str = "PRODUCTION", *, structured_data: dict | None = None) -> Order:
    sd = {"workflow": {"stage": stage_code}}
    if structured_data:
        sd = {**sd, **structured_data}
        sd.setdefault("workflow", {})["stage"] = stage_code
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="오버레이 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status=stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data=sd,
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _counts(order_id: int) -> dict:
    """전이 부산물 카운트(DB-0 검증용): event/receipt/outbox."""
    return {
        "events": db_session.query(OrderEvent).filter_by(order_id=order_id).count(),
        "receipts": db_session.query(OrderMutationReceipt).count(),
        "outbox": db_session.query(DomainSideEffectOutbox).count(),
    }


# --------------------------------------------------------------------------- #
# 1. HOLD overlay 전이 — 축 변경 + main 불변 + same-tx audit
# --------------------------------------------------------------------------- #
def test_hold_overlay_transition_keeps_main_and_records_same_tx(client):
    """HOLD_ORDER: hold 축 HELD, main(erp_stage_code/workflow.stage) 불변, version++/receipt/event/outbox 1."""
    _login(client, _make_user("ov_hold", role="STAFF", team="PRODUCTION"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True, "reason": "자재"})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    axes = read_state_axes(saved)
    assert axes.hold == "HELD"  # overlay 축만 변경
    assert saved.erp_stage_code == "PRODUCTION"  # main 불변
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"  # main 불변
    assert saved.mutation_version == 2  # 전이 1회 bump
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="ORDER_HELD").count() == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_HOLD_ORDER").count() == 1
    assert db_session.query(DomainSideEffectOutbox).filter_by(effect_type="HOLD_NOTIFICATION").count() == 1


def test_hold_overlay_does_not_touch_delete_or_as_axes(client):
    """overlay hold 는 delete/AS/construction 축을 건드리지 않는다(orthogonal, 혼합 금지)."""
    _login(client, _make_user("ov_hold_orth", role="ADMIN"))
    order_id = _make_order("PRODUCTION").id
    before = read_state_axes(db_session.get(Order, order_id))

    client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})

    db_session.expire_all()
    after = read_state_axes(db_session.get(Order, order_id))
    assert after.hold == "HELD"
    assert (after.as_status, after.deleted, after.construction) == (
        before.as_status, before.deleted, before.construction
    )  # delete/AS/construction 불변
    assert after.main == before.main  # main 불변


def test_release_hold_returns_axis_to_none(client):
    """RELEASE_HOLD: HELD→NONE, ORDER_HOLD_RELEASED, main 불변."""
    _login(client, _make_user("ov_rel", role="ADMIN"))
    order_id = _make_order("PRODUCTION").id
    client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})

    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": False})
    assert resp.status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert read_state_axes(saved).hold == "NONE"
    assert saved.erp_stage_code == "PRODUCTION"
    assert db_session.query(OrderEvent).filter_by(
        order_id=order_id, event_type="ORDER_HOLD_RELEASED"
    ).count() == 1


# --------------------------------------------------------------------------- #
# 2. role-gated — 권한 없는 팀은 403, DB 변화 0
# --------------------------------------------------------------------------- #
def test_hold_unauthorized_team_denied_db_zero(client):
    """DRAWING 팀 → hold 403, 전이/event/receipt/outbox 0(상태 불변)."""
    _login(client, _make_user("ov_hold_draw", role="STAFF", team="DRAWING"))
    order_id = _make_order("PRODUCTION").id
    before = _counts(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": True})
    assert resp.status_code == 403

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1  # bump 없음
    assert read_state_axes(saved).hold == "NONE"
    assert _counts(order_id) == before  # DB 변화 0


def test_logistics_unauthorized_team_denied_db_zero(client):
    """DRAWING 팀 → logistics 403, 전이/event/receipt/outbox 0."""
    _login(client, _make_user("ov_log_draw", role="STAFF", team="DRAWING"))
    order_id = _make_order("MEASURE").id
    before = _counts(order_id)

    resp = client.post(f"/api/orders/{order_id}/logistics", json={"status": "MEASURED"})
    assert resp.status_code == 403

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1
    assert read_state_axes(saved).logistics == "NONE"
    assert _counts(order_id) == before


# --------------------------------------------------------------------------- #
# 3. wrong-stage — 비인접 overlay 전이는 409, DB 변화 0
# --------------------------------------------------------------------------- #
def test_release_on_unheld_order_conflicts_db_zero(client):
    """보류 아님에서 release → 409(STAGE_CONFLICT), 전이/event 0."""
    _login(client, _make_user("ov_wrongstage", role="ADMIN"))
    order_id = _make_order("PRODUCTION").id
    before = _counts(order_id)

    resp = client.post(f"/api/orders/{order_id}/production/hold", json={"active": False})
    assert resp.status_code == 409

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1
    assert _counts(order_id) == before


# --------------------------------------------------------------------------- #
# 4. replay — same idempotency_key 는 전이 1회
# --------------------------------------------------------------------------- #
def test_hold_replay_transitions_once(client):
    """같은 key hold 재요청 → version 1회 bump, ORDER_HELD 1건."""
    _login(client, _make_user("ov_hold_idem", role="ADMIN"))
    order_id = _make_order("PRODUCTION").id
    body = {"active": True, "idempotency_key": "ov-hold-key-1"}

    assert client.post(f"/api/orders/{order_id}/production/hold", json=body).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/hold", json=body).status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 2
    assert db_session.query(OrderEvent).filter_by(order_id=order_id, event_type="ORDER_HELD").count() == 1


def test_logistics_replay_transitions_once(client):
    """같은 key logistics 재요청 → version 1회 bump, LOGISTICS_STATUS_CHANGED 1건."""
    _login(client, _make_user("ov_log_idem", role="STAFF", team="SHIPMENT"))
    order_id = _make_order("MEASURE").id
    body = {"status": "MEASURED", "idempotency_key": "ov-log-key-1"}

    assert client.post(f"/api/orders/{order_id}/logistics", json=body).status_code == 200
    assert client.post(f"/api/orders/{order_id}/logistics", json=body).status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 2
    assert db_session.query(OrderEvent).filter_by(
        order_id=order_id, event_type="LOGISTICS_STATUS_CHANGED"
    ).count() == 1


# --------------------------------------------------------------------------- #
# 5. LOGISTICS overlay 전이 — 축 변경 + main 불변 + same-tx audit
# --------------------------------------------------------------------------- #
def test_logistics_overlay_transition_keeps_main(client):
    """SET_LOGISTICS_STATUS: logistics 축 MEASURED, main 불변, version++/receipt/event/outbox 1."""
    _login(client, _make_user("ov_log", role="STAFF", team="SHIPMENT"))
    order_id = _make_order("MEASURE").id

    resp = client.post(f"/api/orders/{order_id}/logistics", json={"status": "MEASURED"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["logistics_status"] == "MEASURED"

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert read_state_axes(saved).logistics == "MEASURED"
    assert saved.structured_data["shipment"]["logistics_status"] == "MEASURED"
    assert saved.erp_stage_code == "MEASURE"  # main 불변
    assert saved.structured_data["workflow"]["stage"] == "MEASURE"  # main 불변
    assert saved.mutation_version == 2
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="STATE_SET_LOGISTICS_STATUS").count() == 1
    assert db_session.query(DomainSideEffectOutbox).filter_by(effect_type="LOGISTICS_NOTIFICATION").count() == 1


def test_logistics_does_not_touch_hold_delete_as(client):
    """logistics 전이는 hold/delete/AS/construction 축을 건드리지 않는다(orthogonal)."""
    _login(client, _make_user("ov_log_orth", role="ADMIN"))
    order_id = _make_order("MEASURE").id
    before = read_state_axes(db_session.get(Order, order_id))

    client.post(f"/api/orders/{order_id}/logistics", json={"status": "SCHEDULED"})

    db_session.expire_all()
    after = read_state_axes(db_session.get(Order, order_id))
    assert after.logistics == "SCHEDULED"
    assert (after.hold, after.as_status, after.deleted, after.construction, after.main) == (
        before.hold, before.as_status, before.deleted, before.construction, before.main
    )


# --------------------------------------------------------------------------- #
# 6. typed only — generic status/delete/AS 값은 logistics 엔드포인트가 거부(DB 0)
# --------------------------------------------------------------------------- #
def test_logistics_rejects_non_logistics_value_db_zero(client):
    """물류 enum 밖 값(main stage/DELETED 등) → 409, 전이/event 0(generic/delete/AS 혼합 불가)."""
    _login(client, _make_user("ov_log_typed", role="ADMIN"))
    order_id = _make_order("MEASURE").id
    before = _counts(order_id)

    for bad in ("PRODUCTION", "DELETED", "AS_RECEIVED", "ON_HOLD"):
        resp = client.post(f"/api/orders/{order_id}/logistics", json={"status": bad})
        assert resp.status_code in (409, 422), (bad, resp.status_code)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1  # 어떤 값도 전이 안 됨
    assert read_state_axes(saved).logistics == "NONE"
    assert _counts(order_id) == before


def test_logistics_missing_status_returns_400(client):
    """status 누락/빈 값 → 400."""
    _login(client, _make_user("ov_log_empty", role="ADMIN"))
    order_id = _make_order("MEASURE").id
    assert client.post(f"/api/orders/{order_id}/logistics", json={}).status_code == 400
    assert client.post(f"/api/orders/{order_id}/logistics", json={"status": "  "}).status_code == 400
