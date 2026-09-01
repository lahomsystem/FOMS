"""SIDEFX ``GEOCODE`` handler + 지오코딩 판정 SSOT 계약 (domain lane).

운영 outbox 에 ``GEOCODE`` PENDING 이 쌓여 있는데 소비할 handler 가 없어 delivery 를 켜면
전부 DEAD 가 되던 구멍을 막는 packet 의 domain-lane 증거다(실 PostgreSQL 다중 커밋 증거는
``tests/postgres/test_sidefx_geocode_handler.py``).

* 판정·저장 SSOT :func:`foms.services.geocode_helpers.apply_geocode_to_order` —
  주소 없음/해시 일치 skip/변환 성공/변환 실패 4갈래. RQ 태스크와 handler 가 같은 함수를
  쓴다(로직 2벌 금지).
* handler — 주문 삭제됨·payload 에 order_id 없음은 **성공 종료**(DEAD 로 쌓지 않는다),
  세션 미attach 는 fail-closed, 재전달은 외부 변환 호출 0회(멱등).

외부 카카오 API 는 호출하지 않는다(변환기 주입/monkeypatch).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.geocode_delivery_handler import (
    GeocodeDeliveryError,
    handle_geocode,
)
from foms.services.geocode_helpers import (
    GEOCODE_OUTCOME_FAILED,
    GEOCODE_OUTCOME_NO_ADDRESS,
    GEOCODE_OUTCOME_SKIPPED,
    GEOCODE_OUTCOME_SUCCESS,
    apply_geocode_to_order,
    compute_address_hash,
)
from foms.services.order_geocode_outbox import enqueue_order_address_geocode
from models import DomainSideEffectOutbox, Order

_ADDRESS = "서울시 강남구 테헤란로 1"
_NOW = datetime.datetime(2026, 8, 31, 3, 0, 0)


class _Converter:
    """호출 주소를 기록하는 가짜 주소 변환기(외부 API 호출 없음)."""

    def __init__(self, lat=37.5, lng=127.0):
        self.lat = lat
        self.lng = lng
        self.calls: list[str] = []

    def convert_address(self, address):
        self.calls.append(address)
        return self.lat, self.lng, "fake"


def _stub_order(**over):
    """지오코드 컬럼만 가진 Order 스텁."""
    base = dict(
        id=1, address=_ADDRESS, lat=None, lng=None,
        geocode_status=None, geocoded_at=None, address_hash=None,
        is_erp_order=False, structured_data=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# 1. 판정 SSOT — apply_geocode_to_order
# --------------------------------------------------------------------------- #
def test_apply_writes_coords_and_hash_on_success():
    """변환 성공 → lat/lng/success/geocoded_at/address_hash 를 모두 기록한다."""
    order = _stub_order()
    conv = _Converter()

    outcome = apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert outcome == GEOCODE_OUTCOME_SUCCESS
    assert (order.lat, order.lng) == (37.5, 127.0)
    assert order.geocode_status == "success"
    assert order.geocoded_at == _NOW
    assert order.address_hash == compute_address_hash(_ADDRESS)
    assert conv.calls == [_ADDRESS]


def test_apply_skips_when_hash_matches_and_coords_present():
    """해시 일치 + 좌표 존재 → 외부 변환 호출 0회(멱등 재전달의 근거)."""
    order = _stub_order(lat=37.5, lng=127.0, address_hash=compute_address_hash(_ADDRESS),
                        geocode_status="success", geocoded_at=_NOW)
    conv = _Converter()

    outcome = apply_geocode_to_order(order, converter=conv,
                                     now=_NOW + datetime.timedelta(hours=1))

    assert outcome == GEOCODE_OUTCOME_SKIPPED
    assert conv.calls == []
    assert order.geocoded_at == _NOW  # 아무것도 다시 쓰지 않는다


def test_apply_records_address_error_when_conversion_returns_no_coords():
    """주소 오류 → 좌표 비우고 address_error + 시도 시각 기록(예외 아님 = 재시도 대상 아님).

    사유를 안 돌려주는 구형 변환기 대역은 실패를 permanent 로 본다(GEO-FAILKIND-01 폴백).
    """
    order = _stub_order(lat=1.0, lng=2.0)
    conv = _Converter(lat=None, lng=None)

    outcome = apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert outcome == GEOCODE_OUTCOME_FAILED
    assert order.lat is None and order.lng is None
    assert order.geocode_status == "address_error"
    assert order.geocoded_at == _NOW
    assert order.address_hash == compute_address_hash(_ADDRESS)


def test_apply_marks_empty_address_error_without_calling_converter():
    """주소가 비면 변환기를 부르지 않고 address_error 로 종료한다."""
    order = _stub_order(address="")
    conv = _Converter()

    outcome = apply_geocode_to_order(order, converter=conv, now=_NOW)

    assert outcome == GEOCODE_OUTCOME_NO_ADDRESS
    assert conv.calls == []
    assert order.geocode_status == "address_error"
    assert order.geocoded_at == _NOW


# --------------------------------------------------------------------------- #
# 2. handler — 세션 계약 / 안전 종료 / 멱등
# --------------------------------------------------------------------------- #
def _make_order(address: str = _ADDRESS) -> Order:
    order = Order(received_date="2026-08-31", customer_name="홍길동",
                  phone="010-0000-0000", address=address, product="침대")
    db_session.add(order)
    db_session.commit()
    return order


def _enqueue(order: Order, *, address: str = _ADDRESS) -> DomainSideEffectOutbox:
    row = enqueue_order_address_geocode(db_session, order, address=address,
                                        actor_user_id=None)
    db_session.commit()
    return row


@pytest.fixture
def converter(monkeypatch):
    """handler 가 만드는 실 변환기를 가짜로 교체한다(카카오 호출 금지)."""
    fake = _Converter()
    monkeypatch.setattr(
        "foms.services.common.address_converter.FOMSAddressConverter",
        lambda *a, **kw: fake,
    )
    return fake


def test_handler_geocodes_order_and_leaves_commit_to_worker(app, converter):
    """handler 는 주문 좌표를 채우되 자기 commit 을 하지 않는다(worker tx 소유)."""
    order = _make_order()
    row = _enqueue(order)

    handle_geocode(row)

    assert (order.lat, order.lng) == (37.5, 127.0)
    assert order.geocode_status == "success"
    db_session.commit()  # 커밋은 caller(worker) 소유
    assert db_session.get(Order, order.id).geocode_status == "success"


def test_handler_is_idempotent_on_redelivery(app, converter):
    """같은 행이 재전달돼도 외부 변환은 1회뿐(해시+좌표 일치 skip)."""
    order = _make_order()
    row = _enqueue(order)

    handle_geocode(row)
    db_session.commit()
    handle_geocode(row)
    db_session.commit()

    assert converter.calls == [_ADDRESS]


def test_handler_skips_deleted_order_without_raising(app, converter):
    """주문이 이미 삭제됐으면 성공 종료한다(재시도해도 돌아오지 않음 — DEAD 금지)."""
    order = _make_order()
    row = _enqueue(order)
    db_session.delete(order)
    db_session.commit()

    handle_geocode(row)  # 예외 없음

    assert converter.calls == []


def test_handler_skips_payload_without_order_id(app, converter):
    """payload 에 order_id 가 없으면 안전 skip(재시도 대상 아님)."""
    order = _make_order()
    row = _enqueue(order)
    row.payload = {"address": _ADDRESS}
    db_session.commit()

    handle_geocode(row)

    assert converter.calls == []


def test_handler_marks_address_error_when_address_not_found(app, monkeypatch):
    """주소 오류는 예외가 아니라 address_error 기록(같은 주소 10회 재호출 방지)."""
    fake = _Converter(lat=None, lng=None)
    monkeypatch.setattr(
        "foms.services.common.address_converter.FOMSAddressConverter",
        lambda *a, **kw: fake,
    )
    order = _make_order()
    row = _enqueue(order)

    handle_geocode(row)
    db_session.commit()

    assert fake.calls == [_ADDRESS]
    assert db_session.get(Order, order.id).geocode_status == "address_error"


def test_handler_fails_closed_when_row_detached(app, converter):
    """세션에 attach 되지 않은 행은 fail-closed(worker 가 재시도)."""
    detached = DomainSideEffectOutbox(
        source_domain="ORDER_EVENT", order_event_id=1, effect_type="GEOCODE",
        payload={"order_id": 1}, status="PROCESSING", attempts=1,
    )

    with pytest.raises(GeocodeDeliveryError):
        handle_geocode(detached)
