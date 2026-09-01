"""관리자 "손님에게 못 간 안내" 화면 계약 (2026-09-01 사용자 요청).

알림톡·문자가 손님에게 안 나갔을 때 사람이 볼 화면이 FOMS 안에 하나도 없었다. 운영
outbox 에 실패가 쌓여도 개발자가 CLI 를 쳐야만 보였다. 이 화면이 그 구멍을 닫는다.

여기서 고정하는 것:

1. **``in_flight`` 앵커는 실패가 아니다.** 자동 경로는 보내기 *전에*
   ``ALIMTALK_FAILED(error='in_flight')`` 를 먼저 만들고 성공 시 ``ALIMTALK_SENT`` 로
   승격한다. 그대로 세면 **정상 발송 중인 건이 실패로 뜬다**.
2. 손님에게 나가는 세 경로(실측 예약 안내·공유 알림톡·공유 문자)를 **모두** 모은다.
3. **"다시 시도 중"과 "최종 실패"를 가른다.** 재시도 중인 건을 실패로 보여주면 직원이
   수동으로 또 눌러 손님이 두 통 받는다.
4. 받는 번호는 가리지 않는다(관리자 전용 화면 — 사용자 지시).
5. ADMIN 전용.
"""

from __future__ import annotations

import datetime

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import DomainSideEffectOutbox, Order, OrderEvent, User

_PATH = "/admin/alimtalk-failures"


def _user(username: str, role: str = "ADMIN") -> int:
    user = User(username=username, password=generate_password_hash("pw"), role=role,
                name=f"{username}-name", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    fresh = db_session.get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = fresh.id
        sess["username"] = fresh.username
        sess["role"] = fresh.role


def _order(name: str = "임다슬", phone: str = "010-2473-6730") -> Order:
    order = Order(
        received_date=datetime.date(2026, 9, 1), customer_name=name, phone=phone,
        address="Seoul", product="가구", status="ERPORDER", is_erp_order=True,
        structured_data={"parties": {"customer": {"name": name, "phone": phone}}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _event(order_id: int, event_type: str, payload: dict) -> OrderEvent:
    event = OrderEvent(order_id=order_id, event_type=event_type, payload=payload,
                       created_at=datetime.datetime(2026, 9, 1, 1, 0, 0))
    db_session.add(event)
    db_session.commit()
    return event


def _render(app, username: str, role: str = "ADMIN", query: str = "") -> str:
    admin_id = _user(username, role)
    client = app.test_client()
    _login(client, admin_id)
    resp = client.get(_PATH + query)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def test_in_flight_anchor_is_not_a_failure(app):
    """발송 진행 중 앵커가 실패 목록에 새면 정상 건이 실패로 보인다."""
    with app.app_context():
        order = _order("발송중고객")
        _event(order.id, "ALIMTALK_FAILED",
               {"error": "in_flight", "dedupe_key": "alimtalk:measure:1:2026-09-05:"})
        body = _render(app, "adm_inflight")
        assert "발송중고객" not in body


def test_sent_event_is_not_listed(app):
    with app.app_context():
        order = _order("성공고객")
        _event(order.id, "ALIMTALK_SENT", {"error": None, "message_id": "M1"})
        body = _render(app, "adm_sent")
        assert "성공고객" not in body


def test_measure_failure_is_listed_with_phone_and_reason(app):
    with app.app_context():
        order = _order("실패고객", phone="010-1111-2222")
        _event(order.id, "ALIMTALK_FAILED",
               {"error": "invalid_phone", "dedupe_key": "k1", "manual": True})
        body = _render(app, "adm_fail")
        assert "실패고객" in body
        assert "010-1111-2222" in body, "받는 번호는 가리지 않는다(사용자 지시)"
        assert "수신 번호가 올바르지 않습니다" in body, "사유는 한글 문구로"


def test_share_alimtalk_and_sms_failures_are_listed(app):
    with app.app_context():
        share_order = _order("공유실패고객")
        sms_order = _order("문자실패고객")
        _event(share_order.id, "SHARE_ALIMTALK",
               {"status": "failed", "error": "balance", "kind": "drawing"})
        _event(sms_order.id, "SHARE_SMS",
               {"status": "failed", "error": "network", "kind": "estimate"})
        body = _render(app, "adm_share")
        assert "공유실패고객" in body and "문자실패고객" in body


def test_share_in_flight_is_not_listed(app):
    with app.app_context():
        order = _order("공유진행중")
        _event(order.id, "SHARE_ALIMTALK", {"status": "in_flight", "kind": "drawing"})
        body = _render(app, "adm_share_inflight")
        assert "공유진행중" not in body


def test_retrying_is_distinguished_from_final_failure(app):
    """워커가 아직 재시도 중인 건을 '최종 실패'로 보여주면 직원이 중복 발송한다."""
    with app.app_context():
        retrying = _order("재시도중고객")
        final = _order("최종실패고객")
        retry_event = _event(retrying.id, "ALIMTALK_FAILED",
                             {"error": "network", "dedupe_key": "retry-key"})
        final_event = _event(final.id, "ALIMTALK_FAILED",
                             {"error": "network", "dedupe_key": "dead-key"})
        for event, key, status in ((retry_event, "retry-key", "PENDING"),
                                   (final_event, "dead-key", "DEAD")):
            db_session.add(DomainSideEffectOutbox(
                source_domain="ORDER_EVENT", order_event_id=event.id,
                effect_type="ALIMTALK_SEND", payload={"order_id": event.order_id},
                dedupe_key=key, provider_idempotency_key=key, status=status,
            ))
        db_session.commit()
        body = _render(app, "adm_retry")
        assert "재시도중고객" in body and "최종실패고객" in body
        retry_pos = body.index("재시도중고객")
        final_pos = body.index("최종실패고객")
        assert "다시 시도 중" in body[retry_pos:retry_pos + 900]
        assert "최종 실패" in body[final_pos:final_pos + 900]


def test_non_admin_is_rejected(app):
    with app.app_context():
        staff_id = _user("adm_staff", role="STAFF")
        client = app.test_client()
        _login(client, staff_id)
        resp = client.get(_PATH)
        assert resp.status_code in (302, 403), resp.status_code
