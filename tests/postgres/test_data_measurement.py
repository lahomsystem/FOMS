"""DATA-MEASUREMENT-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

measurement/regional 저장의 정본 계약을 실 PostgreSQL 로 고정한다:

* typed field registry — regional 6-bool 은 불리언만(임의 타입 거부), measurement projection
  필드는 manager/phone/address 만.
* address/manager/phone projection(raw 보존) + unrelated-path 불변(무관 sd 섹션 불변).
* geocode outbox — 주소 변경은 GEOCODE side-effect 1 + ADDRESS_CHANGED event 1 을 예약하고
  order.lat 을 즉시 지오코드하지 않는다(postcommit 직접 지오코드 0).
* address-learning child — audit(누가/언제) child 행 + ADDRESS_LEARNING outbox, rate 창
  상한 초과 시 거부(무제한 all-STAFF 쓰기 거부).
* version/receipt/event(REV-00) + If-Match stale 409.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다(dev DSN env-only,
비밀번호 커밋 0).
"""
from __future__ import annotations

import copy

import pytest

from foms.services.datetime_kst import now_utc_naive
from foms.services.address_learning_requests import (
    AddressLearningRateLimited,
    ADDRESS_LEARNING_APPLY_EFFECT,
    _RATE_MAX,
    record_address_learning_request,
)
from foms.services.order_geocode import reset_order_geocode_on_address_change
from foms.services.order_geocode_outbox import (
    ADDRESS_CHANGED_EVENT,
    GEOCODE_EFFECT_TYPE,
    enqueue_order_address_geocode,
)
from foms.services.orders.revision import RevisionConflictError, execute_order_mutation
from foms.api.orders.regional import REGIONAL_ALLOWED_FIELDS, _coerce_checklist_bool
from foms.api.measurement.routes import MEASUREMENT_UPDATE_FIELDS
from models import (
    AddressLearningRequest,
    DomainSideEffectOutbox,
    Order,
    OrderEvent,
    User,
)


def _order(session, **over) -> Order:
    base = dict(
        received_date="2026-07-27",
        customer_name="홍길동",
        phone="010-0000-0000",
        address="서울",
        product="침대",
        status="MEASURE",
        is_erp_order=True,
        is_regional=True,
    )
    base.update(over)
    o = Order(**base)
    session.add(o)
    session.flush()
    return o


def _user(session) -> User:
    u = User(username=f"u_{now_utc_naive().timestamp()}", password="x",
             role="STAFF", team="CS", name="검침원", is_active=True)
    session.add(u)
    session.flush()
    return u


# --------------------------------------------------------------------------- #
# 1. typed field registry
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [{"x": 1}, [1], None, object()])
def test_regional_checklist_rejects_non_bool_types(bad):
    """체크리스트 값은 불리언으로만 강제된다(임의 타입 거부)."""
    with pytest.raises(ValueError):
        _coerce_checklist_bool(bad)


@pytest.mark.parametrize("value,expected", [
    (True, True), (False, False), (1, True), (0, False),
    ("true", True), ("1", True), ("no", False), ("", False),
])
def test_regional_checklist_bool_coercion(value, expected):
    assert _coerce_checklist_bool(value) is expected


def test_typed_field_registries_are_closed_sets():
    """regional 은 정확히 6-bool, measurement projection 은 manager/phone/address 만."""
    assert len(REGIONAL_ALLOWED_FIELDS) == 6
    assert set(REGIONAL_ALLOWED_FIELDS) == {
        "measurement_completed", "regional_sales_order_upload",
        "regional_blueprint_sent", "regional_order_upload",
        "regional_cargo_sent", "regional_construction_info_sent",
    }
    assert MEASUREMENT_UPDATE_FIELDS == frozenset({"manager", "phone", "address"})


# --------------------------------------------------------------------------- #
# 2. geocode outbox (no postcommit direct geocode)
# --------------------------------------------------------------------------- #
def test_address_change_enqueues_geocode_outbox_without_direct_geocode(pg_session):
    """주소 변경은 GEOCODE outbox 1 + ADDRESS_CHANGED event 1 을 예약하고 좌표를 즉시
    지오코드하지 않는다(order.lat 은 pending 그대로 None)."""
    user = _user(pg_session)
    order = _order(pg_session, lat=37.5, lng=127.0, geocode_status="success")

    reset_order_geocode_on_address_change(order, "부산 해운대구 1")
    row = enqueue_order_address_geocode(
        pg_session, order, address="부산 해운대구 1", actor_user_id=user.id
    )
    pg_session.flush()

    # 좌표는 지오코드되지 않고 pending 으로 초기화만 됨(postcommit 직접 지오코드 0).
    assert order.lat is None and order.lng is None
    assert order.geocode_status == "pending"

    geocode_rows = (
        pg_session.query(DomainSideEffectOutbox)
        .filter(DomainSideEffectOutbox.effect_type == GEOCODE_EFFECT_TYPE,
                DomainSideEffectOutbox.order_event_id == row.order_event_id)
        .all()
    )
    assert len(geocode_rows) == 1
    assert geocode_rows[0].source_domain == "ORDER_EVENT"
    assert geocode_rows[0].status == "PENDING"

    events = (
        pg_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id,
                OrderEvent.event_type == ADDRESS_CHANGED_EVENT)
        .all()
    )
    assert len(events) == 1


# --------------------------------------------------------------------------- #
# 3. projection + unrelated-path invariant via REV-00
# --------------------------------------------------------------------------- #
def test_manager_projection_preserves_unrelated_sd_and_bumps_version(pg_session):
    """manager projection 은 parties.manager 만 바꾸고 무관 sd 섹션은 불변, version bump +
    receipt + event 를 남긴다."""
    user = _user(pg_session)
    order = _order(pg_session, structured_data={
        "parties": {"manager": {"name": "Alice"}, "customer": {"name": "C"}},
        "items": [{"product_name": "장", "raw": "KEEP"}],
        "site": {"address_full": "서울 원주소"},
    })
    v0 = order.mutation_version

    def _mutate(sess, orders):
        o = orders[0]
        sd = copy.deepcopy(o.structured_data or {})
        sd.setdefault("parties", {}).setdefault("manager", {})["name"] = "Mango"
        o.structured_data = sd
        o.manager_name = "Mango"
        sess.add(OrderEvent(order_id=o.id, event_type="MEASUREMENT_FIELD_UPDATED",
                            payload={"field": "manager"}, created_by_user_id=user.id))
        return {o.id: ["ORDERS_INDEX"]}

    out = execute_order_mutation(
        pg_session, actor_user_id=user.id, policy_id="ERP_EDIT",
        order_ids=[order.id], scope_hash="s", request_hash="r", mutation=_mutate,
    )
    pg_session.flush()

    assert order.manager_name == "Mango"
    assert order.structured_data["parties"]["manager"]["name"] == "Mango"
    # unrelated-path invariant: items/site/customer 불변(raw 보존).
    assert order.structured_data["items"] == [{"product_name": "장", "raw": "KEEP"}]
    assert order.structured_data["site"] == {"address_full": "서울 원주소"}
    assert order.structured_data["parties"]["customer"] == {"name": "C"}
    assert order.mutation_version == v0 + 1
    assert out.read_receipt_id
    assert out.body["resources"][0]["resulting_version"] == v0 + 1


def test_if_match_stale_raises_conflict(pg_session):
    """stale If-Match(mutation_version 불일치)는 RevisionConflictError(409)."""
    user = _user(pg_session)
    order = _order(pg_session)
    stale = (order.mutation_version or 1) + 5

    def _mutate(sess, orders):
        return {orders[0].id: []}

    with pytest.raises(RevisionConflictError) as exc:
        execute_order_mutation(
            pg_session, actor_user_id=user.id, policy_id="ERP_EDIT",
            order_ids=[order.id], expected_versions={order.id: stale},
            scope_hash="s", request_hash="r", mutation=_mutate,
        )
    assert exc.value.status_code == 409


# --------------------------------------------------------------------------- #
# 4. address-learning child policy/rate/audit
# --------------------------------------------------------------------------- #
def test_address_learning_child_records_audit_and_outbox(pg_session):
    """학습 요청은 audit child 행 + ADDRESS_LEARNING outbox 를 만든다."""
    user = _user(pg_session)
    row = record_address_learning_request(
        pg_session,
        original_address="서울 틀린주소",
        corrected_address="서울 강남구 테헤란로 1",
        lat=37.5, lng=127.0,
        requested_by_user_id=user.id,
    )
    pg_session.flush()

    child = pg_session.query(AddressLearningRequest).filter(
        AddressLearningRequest.id == row.id).one()
    assert child.requested_by_user_id == user.id  # audit: 누가
    assert child.created_at is not None            # audit: 언제
    assert child.corrected_address == "서울 강남구 테헤란로 1"

    outbox = pg_session.query(DomainSideEffectOutbox).filter(
        DomainSideEffectOutbox.effect_type == ADDRESS_LEARNING_APPLY_EFFECT,
        DomainSideEffectOutbox.address_learning_request_id == row.id,
    ).all()
    assert len(outbox) == 1
    assert outbox[0].source_domain == "ADDRESS_LEARNING"


def test_address_learning_rate_limit_rejects_unbounded_writes(pg_session):
    """사용자별 rate 창 상한 초과 시 거부(무제한 all-STAFF 쓰기 거부)."""
    user = _user(pg_session)
    now = now_utc_naive()
    # 상한까지 직접 seed(같은 창).
    for i in range(_RATE_MAX):
        pg_session.add(AddressLearningRequest(
            original_address=f"o{i}", corrected_address=f"c{i}",
            requested_by_user_id=user.id, created_at=now,
        ))
    pg_session.flush()

    with pytest.raises(AddressLearningRateLimited):
        record_address_learning_request(
            pg_session,
            original_address="한 건 더",
            corrected_address="넘침",
            lat=None, lng=None,
            requested_by_user_id=user.id,
            now=now,
        )


def test_address_learning_empty_inputs_rejected(pg_session):
    """빈 원/교정 주소는 거부."""
    from foms.services.address_learning_requests import AddressLearningError

    with pytest.raises(AddressLearningError):
        record_address_learning_request(
            pg_session, original_address="  ", corrected_address="x",
            lat=None, lng=None, requested_by_user_id=None,
        )
