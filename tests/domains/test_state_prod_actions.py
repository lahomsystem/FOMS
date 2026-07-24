"""생산 step/defect/change-ack 정본화 계약 (STATE-PROD-ACTIONS-01, SSOT §5.2).

* step/defect: execute_order_mutation(REV-00) 경유로 Order.mutation_version++ 와 legacy
  OrderEvent(PRODUCTION_STEP_CHECKED / PRODUCTION_DEFECT_REPORTED)를 한 tx 에 원자 기록.
* production change-ack: **Order 불변**(mutation_version bump 없음)·receipt+event 만 기록·
  같은 token 재요청은 event 0(idempotent). token 없으면 매 요청 event(기존 동작 보존).
* start/complete 무혼합: step/defect/ack 는 workflow.stage/erp_stage_code/status 를 전이시키지
  않고 전이 event(PRODUCTION_STARTED/COMPLETED)도 남기지 않는다.

fixture/클라이언트 패턴은 test_state_prod.py 를 준용한다(SQLite domain lane; execute_order_mutation
의 FOR UPDATE 는 SQLite 에서 no-op, 실 PostgreSQL 경합은 PGTEST-00 lane). PG dev env 에서 실행
시에도 동일 계약이 성립한다(DSN 은 env-only).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderMutationReceipt, User


def _make_user(username: str, *, role: str = "STAFF", team: str | None = "PRODUCTION") -> User:
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


def _make_order(stage_code: str = "PRODUCTION", *, deleted_at: str | None = None) -> Order:
    order = Order(
        received_date=date.today().isoformat(),
        customer_name="액션 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="DELETED" if deleted_at else stage_code,
        manager_name="Bob",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code}},
        erp_stage_code=stage_code,
        deleted_at=deleted_at,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _events(order_id: int, event_type: str) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .all()
    )


# --------------------------------------------------------------------------- #
# 1. step — version++ + event 1 (one tx)
# --------------------------------------------------------------------------- #
def test_step_check_bumps_version_and_records_event(client):
    """스텝 체크 → Order.mutation_version 1→2, PRODUCTION_STEP_CHECKED 1건, 무전이."""
    _login(client, _make_user("spa_step"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert next(s for s in data["data"]["steps"] if s["key"] == "cut")["done"] is True
    assert data["data"]["done_count"] == 1 and data["data"]["total"] == 5

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 2  # 1 → 2 (단 1회 bump)
    assert next(s for s in saved.structured_data["production"]["steps"] if s["key"] == "cut")["done"] is True
    evs = _events(order_id, "PRODUCTION_STEP_CHECKED")
    assert len(evs) == 1 and evs[0].payload["key"] == "cut" and evs[0].payload["done"] is True
    # 무혼합: stage 전이 없음.
    assert saved.erp_stage_code == "PRODUCTION" and saved.status == "PRODUCTION"


def test_step_toggle_twice_bumps_each_time(client):
    """토큰 없는 재토글은 매번 version++·event(dedupe 안 함): 1→3, event 2건."""
    _login(client, _make_user("spa_step2"))
    order_id = _make_order("PRODUCTION").id

    client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": True})
    resp = client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": False})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["done_count"] == 0

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 3  # 두 번 bump
    assert len(_events(order_id, "PRODUCTION_STEP_CHECKED")) == 2


def test_step_invalid_payload_no_bump(client):
    """검증 실패(잘못된 key/done)는 mutation 진입 전 400 — version/event 불변."""
    _login(client, _make_user("spa_step3"))
    order_id = _make_order("PRODUCTION").id

    assert client.post(f"/api/orders/{order_id}/production/steps", json={"key": "bogus", "done": True}).status_code == 400
    assert client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": "yes"}).status_code == 400

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1
    assert len(_events(order_id, "PRODUCTION_STEP_CHECKED")) == 0


# --------------------------------------------------------------------------- #
# 2. defect — version++ + event 1 (one tx)
# --------------------------------------------------------------------------- #
def test_defect_report_bumps_version_and_records_event(client):
    """불량 보고 → Order.mutation_version 1→2, PRODUCTION_DEFECT_REPORTED 1건, 무전이."""
    _login(client, _make_user("spa_defect"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/defect", json={"reason": "자재 불량"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"]["latest"]["reason"] == "자재 불량" and data["data"]["total"] == 1

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 2
    assert saved.structured_data["production"]["defects"][-1]["reason"] == "자재 불량"
    assert len(_events(order_id, "PRODUCTION_DEFECT_REPORTED")) == 1
    assert saved.erp_stage_code == "PRODUCTION"  # 무전이


def test_defect_invalid_reason_no_bump(client):
    """화이트리스트 밖 사유는 400 — version/event/defects 불변."""
    _login(client, _make_user("spa_defect2"))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/defect", json={"reason": "존재하지 않는 사유"})
    assert resp.status_code == 400

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1
    assert "defects" not in (saved.structured_data.get("production") or {})
    assert len(_events(order_id, "PRODUCTION_DEFECT_REPORTED")) == 0


# --------------------------------------------------------------------------- #
# 3. change-ack — Order 불변, receipt+event, same token event 0
# --------------------------------------------------------------------------- #
def test_change_ack_is_order_immutable_receipt_and_event(client):
    """ack(token 有) → Order.mutation_version 불변(1), event 1건 + receipt 1건."""
    _login(client, _make_user("spa_ack", role="ADMIN", team=None))
    order_id = _make_order("PRODUCTION").id

    resp = client.post(f"/api/orders/{order_id}/production/change-ack", json={"idempotency_key": "ack-key-1"})
    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "data": {"order_id": order_id}}

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1  # Order 불변 — bump 없음
    assert saved.structured_data == {"workflow": {"stage": "PRODUCTION"}}  # sd 무변경
    assert len(_events(order_id, "PRODUCTION_CHANGE_ACK")) == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="PRODUCTION_CHANGE_ACK").count() == 1


def test_change_ack_same_token_is_idempotent_event_zero(client):
    """같은 token 재요청 → event 0(총 1건 유지), version 불변, receipt 1건."""
    _login(client, _make_user("spa_ack2", role="ADMIN", team=None))
    order_id = _make_order("PRODUCTION").id
    body = {"idempotency_key": "ack-key-dup"}

    r1 = client.post(f"/api/orders/{order_id}/production/change-ack", json=body)
    r2 = client.post(f"/api/orders/{order_id}/production/change-ack", json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.get_json() == r2.get_json()

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.mutation_version == 1
    assert len(_events(order_id, "PRODUCTION_CHANGE_ACK")) == 1  # same token → 재기록 0
    assert db_session.query(OrderMutationReceipt).filter_by(idempotency_key="ack-key-dup").count() == 1


def test_change_ack_without_token_records_each_time(client):
    """token 없으면 dedupe 안 함(기존 동작) — 매 요청 event, receipt 미기록."""
    _login(client, _make_user("spa_ack3", role="ADMIN", team=None))
    order_id = _make_order("PRODUCTION").id

    client.post(f"/api/orders/{order_id}/production/change-ack")
    client.post(f"/api/orders/{order_id}/production/change-ack")

    db_session.expire_all()
    assert len(_events(order_id, "PRODUCTION_CHANGE_ACK")) == 2
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id="PRODUCTION_CHANGE_ACK").count() == 0


def test_change_ack_allowed_on_deleted_order_with_marker(client):
    """삭제(묘비) 주문 ack 허용 + deleted_at 마커, Order 불변."""
    _login(client, _make_user("spa_ack4", role="ADMIN", team=None))
    order_id = _make_order("생산", deleted_at="2026-07-20 12:00:00").id

    resp = client.post(f"/api/orders/{order_id}/production/change-ack", json={"idempotency_key": "ack-del-1"})
    assert resp.status_code == 200

    db_session.expire_all()
    ev = _events(order_id, "PRODUCTION_CHANGE_ACK")
    assert len(ev) == 1 and ev[0].payload["deleted_at"] == "2026-07-20 12:00:00"
    assert db_session.get(Order, order_id).mutation_version == 1


# --------------------------------------------------------------------------- #
# 4. 무혼합 — step/defect/ack 는 start/complete 전이를 트리거하지 않는다
# --------------------------------------------------------------------------- #
def test_actions_do_not_transition_stage_or_emit_transition_events(client):
    """step+defect+ack 후에도 stage/status 불변, 전이 event 0(start/complete 무혼합)."""
    _login(client, _make_user("spa_mix"))
    order_id = _make_order("PRODUCTION").id

    assert client.post(f"/api/orders/{order_id}/production/steps", json={"key": "cut", "done": True}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/defect", json={"reason": "파손"}).status_code == 200
    assert client.post(f"/api/orders/{order_id}/production/change-ack", json={"idempotency_key": "m1"}).status_code == 200

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.erp_stage_code == "PRODUCTION" and saved.status == "PRODUCTION"
    assert saved.structured_data["workflow"]["stage"] == "PRODUCTION"
    assert len(_events(order_id, "PRODUCTION_STARTED")) == 0
    assert len(_events(order_id, "PRODUCTION_COMPLETED")) == 0
