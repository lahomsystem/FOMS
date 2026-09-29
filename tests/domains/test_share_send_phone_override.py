"""보내기 창 '번호 바꾸기'(사용자 결정 Q5-②) — 발송 라우트의 선택 본문 ``to_phone``.

* ``send-alimtalk``·``send-sms`` 가 ``to_phone`` 을 받으면 기존 번호 정규화·검증 규칙
  (``ka.extract_valid_phone``)으로 검사해 **이번 발송에만** 쓴다. 주문 번호는 바뀌지 않는다.
* 이벤트 payload 에는 ``to_phone_override: true`` 만 — 번호 원문은 어디에도 저장하지 않는다
  (감사 detail 은 지금처럼 마스킹).
* 틀리면 400 ``INVALID_PHONE`` 이고 이벤트·outbox 가 생기지 않는다.
* ``to_phone`` 이 없거나 null·빈 문자열이면 지금과 같다(주문 고객 번호, 없으면 400 no_valid_phone).
"""
from __future__ import annotations

import datetime
import json

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from foms.services.orders.drawing_customer_send import INVALID_PHONE, resolve_send_phone
from models import AccessLog, DomainSideEffectOutbox, Order, OrderEvent, User

_ENV_KEYS = ('SOLAPI_PF_ID_HAUD', 'SOLAPI_TEMPLATE_SHARE_ID_HAUD', 'SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD',
             'SOLAPI_SENDER_PHONE_HAUD', 'SOLAPI_SENDER_PHONE', 'SOLAPI_SENDER_FALLBACK_HAUD')
OVERRIDE = "010-9876-5432"
OVERRIDE_DIGITS = "01098765432"


def test_resolve_send_phone_rules():
    sd = {"parties": {"customer": {"phone": "010-2473-6730"}}}
    assert resolve_send_phone(sd, {}) == ("01024736730", False, None)
    assert resolve_send_phone(sd, {"to_phone": None}) == ("01024736730", False, None)
    assert resolve_send_phone(sd, {"to_phone": ""}) == ("01024736730", False, None)
    assert resolve_send_phone(sd, {"to_phone": OVERRIDE}) == (OVERRIDE_DIGITS, True, None)
    assert resolve_send_phone(sd, {"to_phone": "02-123-4567"}) == (None, False, INVALID_PHONE)
    assert resolve_send_phone(sd, {"to_phone": 1098765432}) == (None, False, INVALID_PHONE)
    assert resolve_send_phone({}, {}) == (None, False, "no_valid_phone")
    assert resolve_send_phone({}, {"to_phone": OVERRIDE}) == (OVERRIDE_DIGITS, True, None)
    assert INVALID_PHONE == "INVALID_PHONE"


@pytest.fixture
def stubs(monkeypatch):
    calls = []
    monkeypatch.setattr(ka, "_solapi_send", lambda **k: calls.append(("ata", k)) or "ATA-1")

    def _text(*, to, from_, text):
        calls.append(("sms", {"to": to, "from_": from_, "text": text}))
        return "SMS-1"

    monkeypatch.setattr(ka, "_solapi_send_text", _text)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")
    monkeypatch.setenv("SOLAPI_TEMPLATE_SHARE_ID_HAUD", "TPL-HAUD")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    return calls


_SEQ = {"n": 0}


def _setup(client, phone="010-2473-6730"):
    _SEQ["n"] += 1
    order = Order(received_date=datetime.date(2026, 9, 19), customer_name="번호고객", phone=phone,
                  address="Seoul", product="가구", status="ERPORDER", is_erp_order=True,
                  structured_data={"parties": {"customer": {"name": "번호고객", "phone": phone}},
                                   "drawing_transfer_history": [{"action": "TRANSFER", "at": "2026-09-20 01:00:00"}]})
    user = User(username=f"ph_u{_SEQ['n']}", password=generate_password_hash("pw"), role="STAFF", team="CS",
                name="번호", is_active=True)
    db_session.add_all([order, user])
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, "STAFF"
    row, token = osvc.create_share_token(db_session, order.id, "drawing")
    db_session.commit()
    return order.id, row.id, token


def _events(oid):
    db_session.expire_all()
    return db_session.query(OrderEvent).filter(OrderEvent.order_id == oid).all()


@pytest.mark.parametrize("path,kind", [("send-alimtalk", "ata"), ("send-sms", "sms")])
def test_override_used_for_this_send_only(client, stubs, path, kind):
    oid, sid, token = _setup(client)
    res = client.post(f"/api/share/{path}/{sid}", json={"token": token, "to_phone": OVERRIDE})
    assert res.status_code == 200, res.get_json()
    assert stubs[-1][0] == kind and stubs[-1][1]["to"] == OVERRIDE_DIGITS
    ev = _events(oid)[-1]
    assert ev.payload["to_phone_override"] is True
    dumped = json.dumps(ev.payload, ensure_ascii=False)
    assert OVERRIDE_DIGITS not in dumped and OVERRIDE not in dumped
    db_session.expire_all()
    order = db_session.get(Order, oid)
    assert order.structured_data["parties"]["customer"]["phone"] == "010-2473-6730"


def test_override_not_stored_in_outbox_or_audit(client, stubs):
    oid, sid, token = _setup(client)
    assert client.post(f"/api/share/send-alimtalk/{sid}", json={"token": token, "to_phone": OVERRIDE}).status_code == 200
    db_session.expire_all()
    for row in db_session.query(DomainSideEffectOutbox).all():
        assert OVERRIDE_DIGITS not in json.dumps(row.payload or {}, ensure_ascii=False)
    for log in db_session.query(AccessLog).all():
        blob = json.dumps({"a": log.additional_data, "d": log.detail}, ensure_ascii=False, default=str)
        assert OVERRIDE_DIGITS not in blob


@pytest.mark.parametrize("path", ["send-alimtalk", "send-sms"])
@pytest.mark.parametrize("bad", ["02-123-4567", "abc", 1098765432])
def test_invalid_override_is_400_and_no_event(client, stubs, path, bad):
    oid, sid, token = _setup(client)
    res = client.post(f"/api/share/{path}/{sid}", json={"token": token, "to_phone": bad})
    assert res.status_code == 400
    body = res.get_json()
    assert body["success"] is False and body["error"] == "INVALID_PHONE"
    assert _events(oid) == []
    assert stubs == []


@pytest.mark.parametrize("path", ["send-alimtalk", "send-sms"])
def test_no_override_keeps_today(client, stubs, path):
    oid, sid, token = _setup(client)
    res = client.post(f"/api/share/{path}/{sid}", json={"token": token})
    assert res.status_code == 200
    assert stubs[-1][1]["to"] == "01024736730"
    assert "to_phone_override" not in _events(oid)[-1].payload


def test_override_rescues_order_without_valid_phone(client, stubs):
    oid, sid, token = _setup(client, phone="")
    assert client.post(f"/api/share/send-alimtalk/{sid}", json={"token": token}).status_code == 400
    res = client.post(f"/api/share/send-alimtalk/{sid}", json={"token": token, "to_phone": OVERRIDE})
    assert res.status_code == 200, res.get_json()
    assert stubs[-1][1]["to"] == OVERRIDE_DIGITS
