"""SIDEFX ``ALIMTALK_SEND`` handler 계약 (domain lane).

저장 경로가 예약한 PENDING 행을 handler 가 소비한다. Solapi 는 monkeypatch.
커밋은 caller(워커) 소유 — handler 는 이력을 세션에만 남긴다.
"""
from __future__ import annotations

import copy
import datetime

import pytest

from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services.alimtalk_delivery_handler import (
    AlimtalkDeliveryError,
    handle_alimtalk_send,
)
from models import DomainSideEffectOutbox, Order, OrderEvent

_MEASURE_SD = {
    "parties": {"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                "orderer": {"name": "라홈시스템"}},
    "schedule": {"measurement": {"date": "2026-08-14", "time": "3시 30분"}},
}


def _sd() -> dict:
    return copy.deepcopy(_MEASURE_SD)


@pytest.fixture
def solapi_env(monkeypatch):
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    monkeypatch.setenv("SOLAPI_PF_ID_LAHOM", "PF-LAHOM")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_LAHOM", "TPL-LAHOM")
    monkeypatch.setenv("FOMS_ALIMTALK_AUTO_ENABLED", "1")


@pytest.fixture
def stub_solapi_ok(monkeypatch):
    calls: list[dict] = []

    def _fake(**kwargs) -> str:
        calls.append(kwargs)
        return "MSG-1"

    monkeypatch.setattr(ka, "_solapi_send", _fake)
    return calls


def _mk_order() -> Order:
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name="임다슬",
        phone="010-2473-6730",
        address="Seoul",
        product="가구",
        status="ERPORDER",
        is_erp_order=True,
        structured_data=_sd(),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _reserve(order: Order) -> DomainSideEffectOutbox:
    ka.maybe_send_measure_alimtalk(order.id)
    db_session.expire_all()
    return db_session.query(DomainSideEffectOutbox).one()


def test_handler_sends_and_promotes_anchor(app, solapi_env, stub_solapi_ok):
    """handler 는 Solapi 를 부르고 앵커 이벤트를 SENT 로 올리되 자기 commit 은 하지 않는다."""
    order = _mk_order()
    row = _reserve(order)

    handle_alimtalk_send(row)
    assert stub_solapi_ok[0]["to"] == "01024736730"
    db_session.commit()

    db_session.expire_all()
    history = (db_session.get(Order, order.id).structured_data or {}).get("alimtalk_measurement")
    assert history["message_id"] == "MSG-1" and history["error"] is None
    events = db_session.query(OrderEvent).filter_by(order_id=order.id).all()
    assert [e.event_type for e in events] == ["ALIMTALK_SENT"]
    assert db_session.get(DomainSideEffectOutbox, row.id).status == "PENDING"


def test_handler_is_idempotent_on_redelivery(app, solapi_env, stub_solapi_ok):
    """성공 이력이 있으면 재전달에서 Solapi 0회."""
    order = _mk_order()
    row = _reserve(order)
    handle_alimtalk_send(row)
    db_session.commit()
    handle_alimtalk_send(row)
    db_session.commit()
    assert len(stub_solapi_ok) == 1


def test_handler_raises_on_network_so_worker_retries(app, solapi_env, monkeypatch):
    """네트워크 실패는 이력 FAILED + 예외(outbox 는 워커가 PENDING 유지)."""
    def _boom(**kwargs):
        raise ConnectionError("timeout")

    monkeypatch.setattr(ka, "_solapi_send", _boom)
    order = _mk_order()
    row = _reserve(order)

    with pytest.raises(AlimtalkDeliveryError):
        handle_alimtalk_send(row)
    db_session.commit()

    db_session.expire_all()
    history = (db_session.get(Order, order.id).structured_data or {}).get("alimtalk_measurement")
    assert history["error"] == "network"
    assert db_session.get(DomainSideEffectOutbox, row.id).status == "PENDING"


def test_handler_skips_gone_order(app, solapi_env, stub_solapi_ok):
    """payload 주문 id 가 없으면 예외 없이 종료(DEAD 로 쌓지 않음)."""
    order = _mk_order()
    row = _reserve(order)
    row.payload = {"order_id": 9_999_999}
    handle_alimtalk_send(row)
    assert stub_solapi_ok == []


def test_handler_permanent_error_does_not_raise(app, solapi_env, monkeypatch):
    """템플릿 불일치는 재시도해도 같으므로 예외 없이 종료(워커가 DONE)."""
    def _boom(**kwargs):
        raise Exception("template variable mismatch")

    monkeypatch.setattr(ka, "_solapi_send", _boom)
    order = _mk_order()
    row = _reserve(order)
    handle_alimtalk_send(row)
    db_session.commit()
    db_session.expire_all()
    history = (db_session.get(Order, order.id).structured_data or {}).get("alimtalk_measurement")
    assert history["error"] == "template_mismatch"


def test_handler_not_attached_fails_closed(app):
    """세션 미attach 행은 fail-closed."""
    row = DomainSideEffectOutbox(
        source_domain="ADDRESS_LEARNING",
        address_learning_request_id=1,
        effect_type="ALIMTALK_SEND",
        payload={"order_id": 1},
        status="PENDING",
    )
    with pytest.raises(AlimtalkDeliveryError):
        handle_alimtalk_send(row)
