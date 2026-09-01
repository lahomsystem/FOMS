"""SIDEFX ``GEOCODE`` delivery handler PostgreSQL 계약 테스트 (PGTEST 레인).

운영 outbox 에 ``GEOCODE`` PENDING 이 쌓여 있는데 소비할 handler 가 없었다 — delivery 를
켜면 ``NoHandlerError`` 로 10회 재시도 뒤 전부 DEAD 가 된다. 이 스위트는 새 handler 를
**실제 worker 경로**(:func:`run_delivery_once` 의 claim → dispatch → finalize → commit)로
고정한다:

* 정상 변환 — 좌표/상태/해시가 저장되고 outbox 행은 DONE(재시도 0).
* 이미 좌표 있음 — 외부 변환 호출 0회(멱등), DONE.
* 주문 삭제됨 — 예외 없이 DONE(재시도해도 돌아오지 않는 일을 DEAD 로 쌓지 않는다).
* 변환 실패 — ``geocode_status='failed'`` 기록 + DONE(같은 주소 10회 재호출 금지).
* 재전달 멱등 — 같은 행을 PENDING 으로 되돌려 다시 배달해도 외부 호출은 늘지 않는다.

외부 카카오 API 는 부르지 않는다(:class:`FOMSAddressConverter` monkeypatch). ``order_id``
는 실제 행에서만 얻는다(없는 FK id 금지). ``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가
lane 을 skip 한다(SQLite 대체 증거는 ``tests/domains/test_geocode_delivery_handler.py``).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.geocode_delivery_handler import handle_geocode
from foms.services.order_geocode_outbox import enqueue_order_address_geocode
from foms.services.sidefx_worker import (
    clear_handlers,
    register_handler,
    run_delivery_once,
)
from models import DomainSideEffectOutbox, Order

_ADDRESS = "서울시 강남구 테헤란로 1"


class _Converter:
    """호출 주소를 기록하는 가짜 주소 변환기(외부 API 호출 없음)."""

    def __init__(self, lat=37.5012, lng=127.0396):
        self.lat = lat
        self.lng = lng
        self.calls: list[str] = []

    def convert_address(self, address):
        self.calls.append(address)
        return self.lat, self.lng, "fake"


@pytest.fixture
def converter(monkeypatch):
    """공용 판정 함수가 만드는 실 변환기를 recording fake 로 교체한다."""
    fake = _Converter()
    monkeypatch.setattr(
        "foms.services.common.address_converter.FOMSAddressConverter",
        lambda *a, **kw: fake,
    )
    return fake


@pytest.fixture
def failing_converter(monkeypatch):
    """좌표를 못 찾는 변환기(주소 자체가 틀린 건 재현)."""
    fake = _Converter(lat=None, lng=None)
    monkeypatch.setattr(
        "foms.services.common.address_converter.FOMSAddressConverter",
        lambda *a, **kw: fake,
    )
    return fake


@pytest.fixture(autouse=True)
def _handler_registry():
    """GEOCODE handler 를 등록하고 테스트 후 registry 를 비운다(격리)."""
    clear_handlers()
    register_handler("GEOCODE", handle_geocode, replace=True)
    yield
    clear_handlers()


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _quiesce(pg_engine) -> None:
    """다른 테스트가 남긴 PENDING/PROCESSING/DEAD outbox 를 recent DONE 으로 중립화한다."""
    now = now_utc_naive()
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE domain_side_effect_outbox "
                "SET status='DONE', completed_at=:now, dead_at=NULL, "
                "    lease_owner_hash=NULL, lease_token=NULL, lease_expires_at=NULL "
                "WHERE status IN ('PENDING','PROCESSING','DEAD')"
            ),
            {"now": now},
        )


def _make_order(session, *, address: str = _ADDRESS, **over) -> Order:
    """실 Order 행 1개를 커밋하고 반환한다(없는 FK id 금지)."""
    order = Order(received_date="2026-08-31", customer_name="홍길동",
                  phone="010-0000-0000", address=address, product="침대")
    for k, v in over.items():
        setattr(order, k, v)
    session.add(order)
    session.commit()
    return order


def _enqueue(session, order: Order, *, address: str = _ADDRESS) -> int:
    """실 producer 로 GEOCODE outbox 행을 예약하고 id 를 반환한다."""
    row = enqueue_order_address_geocode(session, order, address=address, actor_user_id=None)
    session.commit()
    return row.id


def _deliver(pg_engine) -> dict:
    return run_delivery_once(
        pg_engine, owner_hash="g" * 64, lease_token_fn=lambda: str(uuid.uuid4()))


# --------------------------------------------------------------------------- #
# 1. 정상 변환 — 좌표 저장 + DONE
# --------------------------------------------------------------------------- #
def test_delivery_geocodes_order_and_marks_done(pg_engine, converter):
    """PENDING GEOCODE → 좌표/상태/해시 저장, outbox DONE(재시도·DEAD 0)."""
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        order_id = order.id
        row_id = _enqueue(s, order)
    finally:
        s.close()

    result = _deliver(pg_engine)

    assert result["dead"] == 0 and result["retried"] == 0
    s = _session(pg_engine)
    try:
        row = s.get(DomainSideEffectOutbox, row_id)
        assert row.status == "DONE" and row.completed_at is not None
        stored = s.get(Order, order_id)
        assert (stored.lat, stored.lng) == (37.5012, 127.0396)
        assert stored.geocode_status == "success"
        assert stored.geocoded_at is not None and stored.address_hash
    finally:
        s.close()
    assert converter.calls == [_ADDRESS]


# --------------------------------------------------------------------------- #
# 2. 이미 좌표 있음 — 외부 호출 0회
# --------------------------------------------------------------------------- #
def test_delivery_skips_when_coordinates_are_current(pg_engine, converter):
    """해시 일치 + 좌표 존재면 외부 변환 없이 DONE(좌표 그대로)."""
    from foms.services.geocode_helpers import compute_address_hash

    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        order = _make_order(s, lat=1.25, lng=2.5, geocode_status="success",
                            address_hash=compute_address_hash(_ADDRESS))
        order_id = order.id
        row_id = _enqueue(s, order)
    finally:
        s.close()

    _deliver(pg_engine)

    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
        stored = s.get(Order, order_id)
        assert (stored.lat, stored.lng) == (1.25, 2.5)
    finally:
        s.close()
    assert converter.calls == []


# --------------------------------------------------------------------------- #
# 3. 주문 삭제됨 — 성공 종료(DEAD 금지)
# --------------------------------------------------------------------------- #
def test_delivery_marks_done_when_order_was_deleted(pg_engine, converter):
    """주문이 삭제된 뒤 배달돼도 DONE — 재시도/DEAD 로 쌓이지 않는다.

    ``order_events`` 는 FK 없는 감사 원장(auditlife_00)이라 주문 삭제 뒤에도 남는다 —
    outbox anchor 는 유효하고 payload 의 주문만 사라진 실제 상황을 그대로 만든다.
    """
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        row_id = _enqueue(s, order)
        s.delete(order)
        s.commit()
    finally:
        s.close()

    result = _deliver(pg_engine)

    assert result["dead"] == 0 and result["retried"] == 0
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
    finally:
        s.close()
    assert converter.calls == []


# --------------------------------------------------------------------------- #
# 4. 주소 오류 — address_error 기록 + DONE
# --------------------------------------------------------------------------- #
def test_delivery_records_address_error_without_retry(pg_engine, failing_converter):
    """주소를 못 찾으면 ``geocode_status='address_error'`` 를 남기고 DONE(재호출 폭주 방지).

    사유를 안 돌려주는 변환기 대역은 실패를 permanent 로 본다(GEO-FAILKIND-01 폴백).
    일시 오류는 반대로 예외를 올려 재시도된다 —
    :func:`test_transient_failure_is_retried_not_recorded` 가 그 축을 잠근다.
    """
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        order_id = order.id
        row_id = _enqueue(s, order)
    finally:
        s.close()

    result = _deliver(pg_engine)

    assert result["dead"] == 0 and result["retried"] == 0
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
        stored = s.get(Order, order_id)
        assert stored.geocode_status == "address_error"
        assert stored.lat is None and stored.lng is None
        assert stored.geocoded_at is not None  # 실패 시각 — 재큐 백오프의 기준
    finally:
        s.close()
    assert failing_converter.calls == [_ADDRESS]


def test_transient_failure_is_retried_not_recorded(pg_engine, monkeypatch):
    """음성 대조군: 일시 오류는 굳히지 않고 outbox 재시도로 돌린다.

    2026-09-01 사고의 자리다 — 이 축이 없으면 네트워크 사고가 "주소오류"로 굳는다.
    handler 가 예외를 올리므로 tx 가 롤백되고, 주문 상태는 손대기 전 그대로여야 한다.
    """
    from foms.services.geocode_retry import FAILURE_TRANSIENT

    class _TransientConverter:
        def __init__(self):
            self.calls: list[str] = []

        def convert_address_with_reason(self, address):
            self.calls.append(address)
            return None, None, "일시 오류", FAILURE_TRANSIENT

    fake = _TransientConverter()
    monkeypatch.setattr(
        "foms.services.common.address_converter.FOMSAddressConverter",
        lambda *a, **kw: fake,
    )

    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        order_id = order.id
        row_id = _enqueue(s, order)
    finally:
        s.close()

    result = _deliver(pg_engine)

    assert result["dead"] == 0
    assert result["retried"] == 1, "일시 오류는 재시도 대상이어야 한다"
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status != "DONE"
        stored = s.get(Order, order_id)
        assert stored.geocode_status != "address_error"
        assert stored.geocode_status != "failed"
    finally:
        s.close()
    assert fake.calls == [_ADDRESS]


# --------------------------------------------------------------------------- #
# 5. 재전달 멱등
# --------------------------------------------------------------------------- #
def test_redelivery_is_idempotent(pg_engine, converter):
    """같은 행을 PENDING 으로 되돌려 다시 배달해도 외부 변환은 1회뿐."""
    _quiesce(pg_engine)
    s = _session(pg_engine)
    try:
        order = _make_order(s)
        order_id = order.id
        row_id = _enqueue(s, order)
    finally:
        s.close()

    _deliver(pg_engine)

    s = _session(pg_engine)
    try:  # worker 재시작/lease 회수로 같은 행이 다시 배달되는 상황
        row = s.get(DomainSideEffectOutbox, row_id)
        row.status = "PENDING"
        row.completed_at = None
        row.available_at = now_utc_naive()
        s.commit()
    finally:
        s.close()

    _deliver(pg_engine)

    assert converter.calls == [_ADDRESS]  # 두 번째 배달은 외부 호출 0회
    s = _session(pg_engine)
    try:
        assert s.get(DomainSideEffectOutbox, row_id).status == "DONE"
        stored = s.get(Order, order_id)
        assert (stored.lat, stored.lng) == (37.5012, 127.0396)
    finally:
        s.close()
