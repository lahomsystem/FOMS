"""상태 다축 전이 엔진 계약 (STATE-CORE-00, SSOT §2.2·§2.2.1·§2.3).

``order_transition_service.transition_order`` 가 상태 변경의 유일한 경로로서 다음을
원자적으로 보장하는지 domain 라인(SQLite)에서 고정한다:

* expected-from axis mismatch → 전이 거부(actual 불변).
* 정상 전이 → target axis 반영·mutation_version++·receipt 생성·legacy ``OrderEvent`` parity.
* If-Match(mutation_version) stale → 409(``RevisionConflictError``), 상태 불변.
* side-effect 가 전이와 **같은 tx** outbox 에 enqueue(성공 commit 시 존재, 전이 rollback 시 없음).
* registry 미등록 command → 명시적 거부(silent no-op 금지).
* orthogonality: logistics/hold 전이는 main stage 를 건드리지 않는다.
* idempotency replay → 전이/event/outbox 재수행 없이 저장된 응답 반환.

실 PostgreSQL 다중 커밋 FOR UPDATE 경합은 ``tests/postgres/test_order_transition_service.py``
(PGTEST-00 lane)에서 별도로 고정한다. endpoint 이관은 하류(STATE-PROD-01 등) 몫이라 이
테스트는 route 를 호출하지 않고 엔진 계약만 검증한다.
"""
from __future__ import annotations

import uuid

import pytest

from db import Base, db_session, engine
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    InvalidTransitionError,
    StageConflictError,
    UnknownTransitionCommandError,
    get_command,
    transition_order,
)
from foms.services.orders.revision import RevisionConflictError
from models import DomainSideEffectOutbox, Order, OrderEvent, OrderMutationReceipt, User

_H = "a" * 64  # sha256-hex placeholder


@pytest.fixture
def db(app):
    """app 픽스처가 만든 테이블 위에서 도는 세션(테스트 간 스키마 격리)."""
    Base.metadata.create_all(bind=engine)
    yield db_session
    db_session.rollback()


def _make_actor() -> User:
    u = User(username=f"actor_{uuid.uuid4().hex[:10]}", password="pw-not-committed",
             name="작업자", role="STAFF", team="CS", is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


def _make_order(stage: str = "RECEIVED", **kw) -> Order:
    o = Order(received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
              address="서울", product="침대", is_erp_order=True, status=stage,
              erp_stage_code=stage, structured_data={"workflow": {"stage": stage}})
    for k, v in kw.items():
        setattr(o, k, v)
    db_session.add(o)
    db_session.commit()
    return o


def _outbox_for(effect_type: str):
    return db_session.query(DomainSideEffectOutbox).filter_by(effect_type=effect_type).all()


# --------------------------------------------------------------------------- #
# 1. 정상 전이 — target axis 반영 + version++ + receipt + OrderEvent parity + outbox
# --------------------------------------------------------------------------- #
def test_normal_transition_applies_axis_version_receipt_event(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")
    assert order.mutation_version == 1

    result = transition_order(
        db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
        actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
        expected_version=1, scope_hash=_H, request_hash=_H,
    )
    db.commit()

    assert result.replayed is False
    assert result.axes_before.main == "RECEIVED"
    assert result.axes_after.main == "MEASURE"

    db.refresh(order)
    # target axis 반영: canonical path + indexed mirror + legacy projection.
    assert order.structured_data["workflow"]["stage"] == "MEASURE"
    assert order.erp_stage_code == "MEASURE"
    assert order.status == "MEASURE"
    # mutation_version++.
    assert order.mutation_version == 2

    # receipt 생성(REV-00 helper).
    receipt = (db.query(OrderMutationReceipt)
               .filter_by(read_receipt_id=result.mutation.read_receipt_id).one())
    assert receipt.actor_user_id == actor.id
    assert receipt.policy_id == "STATE_REQUEST_MEASUREMENT"
    assert receipt.resulting_versions == {str(order.id): 2}

    # legacy OrderEvent parity: registry event_type + before/after payload.
    events = db.query(OrderEvent).filter_by(order_id=order.id).all()
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "MEASUREMENT_REQUESTED"
    assert ev.payload["from"] == "RECEIVED" and ev.payload["to"] == "MEASURE"
    assert ev.payload["command"] == "REQUEST_MEASUREMENT"
    assert result.event_id == ev.id

    # 같은 tx outbox 행: ORDER_EVENT source, event FK, effect_type.
    outbox = _outbox_for("STAGE_NOTIFICATION")
    assert len(outbox) == 1
    assert outbox[0].source_domain == "ORDER_EVENT"
    assert outbox[0].order_event_id == ev.id
    assert outbox[0].id == result.outbox_id


# --------------------------------------------------------------------------- #
# 2. expected-from mismatch → 거부, actual 불변
# --------------------------------------------------------------------------- #
def test_expected_from_mismatch_rejected_actual_unchanged(db):
    actor = _make_actor()
    order = _make_order("MEASURE")  # 실제 main=MEASURE

    with pytest.raises(StageConflictError) as ei:
        transition_order(
            db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
            actor_user_id=actor.id, expected_from="RECEIVED",  # actual 과 불일치
            target_value="MEASURE", scope_hash=_H, request_hash=_H,
        )
    db.rollback()
    assert ei.value.actual == "MEASURE" and ei.value.expected == "RECEIVED"

    db.refresh(order)
    assert order.structured_data["workflow"]["stage"] == "MEASURE"
    assert order.mutation_version == 1  # bump 없음
    assert db.query(OrderEvent).filter_by(order_id=order.id).count() == 0
    assert _outbox_for("STAGE_NOTIFICATION") == []
    assert db.query(OrderMutationReceipt).filter_by(actor_user_id=actor.id).count() == 0


# --------------------------------------------------------------------------- #
# 3. If-Match(mutation_version) stale → 409, 상태 불변
# --------------------------------------------------------------------------- #
def test_stale_if_match_conflict_no_change(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")  # version 1

    with pytest.raises(RevisionConflictError) as ei:
        transition_order(
            db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
            actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
            expected_version=99,  # stale
            scope_hash=_H, request_hash=_H,
        )
    db.rollback()
    assert ei.value.current_versions == {order.id: 1}

    db.refresh(order)
    assert order.structured_data["workflow"]["stage"] == "RECEIVED"
    assert order.mutation_version == 1
    assert db.query(OrderEvent).filter_by(order_id=order.id).count() == 0
    assert _outbox_for("STAGE_NOTIFICATION") == []


# --------------------------------------------------------------------------- #
# 4. 전이 원자성 — rollback 시 outbox 도 사라진다(같은 tx)
# --------------------------------------------------------------------------- #
def test_transition_and_outbox_atomic_rollback(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")

    result = transition_order(
        db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
        actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
        scope_hash=_H, request_hash=_H,
    )
    # flush 됨(id 존재) 하지만 아직 commit 전.
    assert result.outbox_id is not None
    assert _outbox_for("STAGE_NOTIFICATION")  # 세션 안에서는 보임

    db.rollback()  # 전이 tx rollback → 전이·event·outbox 전부 사라짐

    db.refresh(order)
    assert order.structured_data["workflow"]["stage"] == "RECEIVED"
    assert order.mutation_version == 1
    assert db.query(OrderEvent).filter_by(order_id=order.id).count() == 0
    assert _outbox_for("STAGE_NOTIFICATION") == []


# --------------------------------------------------------------------------- #
# 5. registry 미등록 command → 명시적 거부
# --------------------------------------------------------------------------- #
def test_unregistered_command_rejected(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")

    with pytest.raises(UnknownTransitionCommandError):
        transition_order(
            db, command_id="BOGUS_COMMAND", order_id=order.id,
            actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
            scope_hash=_H, request_hash=_H,
        )
    db.rollback()
    assert db.query(OrderMutationReceipt).count() == 0


def test_target_outside_registry_to_values_rejected(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")
    with pytest.raises(InvalidTransitionError):
        transition_order(
            db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
            actor_user_id=actor.id, expected_from="RECEIVED",
            target_value="PRODUCTION",  # to_values=("MEASURE",) 밖
            scope_hash=_H, request_hash=_H,
        )
    db.rollback()


def test_non_adjacent_without_override_rejected(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")
    # COMPLETE_MEASUREMENT 은 from=("MEASURE",)만 — RECEIVED 에서는 비인접.
    with pytest.raises(InvalidTransitionError):
        transition_order(
            db, command_id="COMPLETE_MEASUREMENT", order_id=order.id,
            actor_user_id=actor.id, expected_from="RECEIVED", target_value="DRAWING",
            scope_hash=_H, request_hash=_H,
        )
    db.rollback()


# --------------------------------------------------------------------------- #
# 6. orthogonality — logistics/hold 전이는 main stage 불변
# --------------------------------------------------------------------------- #
def test_logistics_transition_preserves_main_stage(db):
    actor = _make_actor()
    order = _make_order("PRODUCTION")

    result = transition_order(
        db, command_id="SET_LOGISTICS_STATUS", order_id=order.id,
        actor_user_id=actor.id, expected_from="NONE", target_value="MEASURED",
        scope_hash=_H, request_hash=_H,
    )
    db.commit()

    db.refresh(order)
    assert order.structured_data["shipment"]["logistics_status"] == "MEASURED"
    assert order.structured_data["workflow"]["stage"] == "PRODUCTION"  # main 불변
    assert result.axes_after.main == "PRODUCTION"
    assert result.axes_after.logistics == "MEASURED"
    # legacy projection: logistics overlay 가 status 를 덮되 stage 는 보존.
    assert order.status == "MEASURED"


def test_hold_transition_preserves_main_stage(db):
    actor = _make_actor()
    order = _make_order("PRODUCTION")

    transition_order(
        db, command_id="HOLD_ORDER", order_id=order.id,
        actor_user_id=actor.id, expected_from="NONE", target_value="HELD",
        reason="자재 지연", scope_hash=_H, request_hash=_H,
    )
    db.commit()

    db.refresh(order)
    assert order.structured_data["workflow"]["hold"]["active"] is True
    assert order.structured_data["workflow"]["stage"] == "PRODUCTION"  # main 불변
    assert order.status == "ON_HOLD"  # hold overlay 우선


# --------------------------------------------------------------------------- #
# 7. idempotency replay — 전이/event/outbox 재수행 없음
# --------------------------------------------------------------------------- #
def test_idempotency_replay_no_duplicate_effect(db):
    actor = _make_actor()
    order = _make_order("RECEIVED")
    key = str(uuid.uuid4())

    r1 = transition_order(
        db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
        actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
        idempotency_key=key, scope_hash=_H, request_hash=_H,
    )
    db.commit()
    assert r1.replayed is False

    r2 = transition_order(
        db, command_id="REQUEST_MEASUREMENT", order_id=order.id,
        actor_user_id=actor.id, expected_from="RECEIVED", target_value="MEASURE",
        idempotency_key=key, scope_hash=_H, request_hash=_H,
    )
    db.commit()
    assert r2.replayed is True
    assert r2.mutation.body == r1.mutation.body

    db.refresh(order)
    assert order.mutation_version == 2  # 한 번만 bump
    assert db.query(OrderEvent).filter_by(order_id=order.id).count() == 1
    assert len(_outbox_for("STAGE_NOTIFICATION")) == 1


# --------------------------------------------------------------------------- #
# 8. registry 무결성
# --------------------------------------------------------------------------- #
def test_registry_lookup_and_membership():
    cmd = get_command("REQUEST_MEASUREMENT")
    assert cmd.axis == "MAIN" and cmd.to_values == ("MEASURE",)
    assert set(COMMAND_REGISTRY) >= {
        "REQUEST_MEASUREMENT", "COMPLETE_MEASUREMENT", "SET_LOGISTICS_STATUS",
        "HOLD_ORDER", "RELEASE_HOLD",
    }
