"""공유 링크 문자 발송 — 폴백·멱등(DB 차단)·토큰 검증·감사 테스트 (Phase A T8).

Solapi 는 ``kakao_alimtalk._solapi_send_text`` 를 monkeypatch 해 스텁한다(네트워크 0).
멱등은 §1 선점 insert — ``(effect_type, dedupe_key)`` UNIQUE 가 같은 5초 버킷의
2번째 요청을 IntegrityError→409 로 차단한다(감사 조회식 check-then-act 아님).
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.api.share as share_routes
from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from foms.services.datetime_kst import now_utc_naive
from models import DomainSideEffectOutbox, Order, OrderEvent, SecurityLog, User

_SD = {
    'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
    'items': [{'product_name': '무몰딩 여닫이', 'quantity': 1, 'price': 100000}],
}


def _mk_order(**kwargs) -> Order:
    fields = dict(
        received_date=datetime.date(2026, 8, 12),
        customer_name='임다슬',
        phone='010-2473-6730',
        address='Seoul',
        product='가구',
        status='ERPORDER',
        is_erp_order=True,
        structured_data=dict(_SD),
    )
    fields.update(kwargs)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, username, role='STAFF', sender_phone=None) -> int:
    user = User(username=username, password=generate_password_hash('pw'),
                role=role, team='CS', name=username, is_active=True,
                sender_phone=sender_phone)
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = username
        sess['role'] = role
    return uid


def _mk_share(order_id, kind='drawing'):
    row, token = osvc.create_share_token(db_session, order_id, kind)
    db_session.commit()
    return row.id, token


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def sms_stub(monkeypatch):
    """성공 스텁 — 호출 인자 수집."""
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return 'SMS-1'

    monkeypatch.setattr(ka, '_solapi_send_text', _fake)
    monkeypatch.setenv('SOLAPI_SENDER_PHONE', '0212345678')
    return calls


@pytest.fixture
def clock(monkeypatch):
    """time.time 고정 — 멱등 버킷 결정적 제어."""
    state = {'now': 1_000_000.0}
    monkeypatch.setattr(share_routes.time, 'time', lambda: state['now'])
    return state


def _send(client, share_id, token):
    return client.post(f'/api/share/send-sms/{share_id}', json={'token': token})


# --- 발신 폴백 (D2) --------------------------------------------------------------


def test_send_uses_company_number_when_no_personal(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms1')
    share_id, token = _mk_share(order_id)
    resp = _send(client, share_id, token)
    assert resp.status_code == 200 and resp.get_json()['data']['sent'] is True
    assert sms_stub[0]['from_'] == '0212345678'
    assert sms_stub[0]['to'] == '01024736730'
    assert '/s/' in sms_stub[0]['text']
    assert '도면' in sms_stub[0]['text']


def test_send_prefers_personal_sender_phone(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms2', sender_phone='01099998888')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    assert sms_stub[0]['from_'] == '01099998888'


def test_send_not_configured_503(client, db, monkeypatch, clock):
    monkeypatch.delenv('SOLAPI_SENDER_PHONE', raising=False)
    order_id = _mk_order().id
    _login(client, 'sms3')
    share_id, token = _mk_share(order_id)
    assert _send(client, share_id, token).status_code == 503


# --- 토큰 원문 재해시 검증 (§1) ----------------------------------------------------


def test_send_rejects_wrong_token_400(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms4')
    share_id, _ = _mk_share(order_id)
    resp = _send(client, share_id, 'wrong-token')
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'token_mismatch'
    assert sms_stub == []


def test_send_rejects_revoked_410(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms5')
    share_id, token = _mk_share(order_id)
    from models import OrderShareToken
    osvc.revoke_token(db_session.get(OrderShareToken, share_id))
    db_session.commit()
    assert _send(client, share_id, token).status_code == 410
    assert sms_stub == []


# --- 멱등: 선점 insert + 시간버킷 UNIQUE (§1) --------------------------------------


def test_send_duplicate_in_bucket_409_single_vendor_call(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms6')
    share_id, token = _mk_share(order_id)
    first = _send(client, share_id, token)
    second = _send(client, share_id, token)  # 같은 5초 버킷
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.get_json()['error'] == 'duplicate_send'
    assert len(sms_stub) == 1  # 벤더 호출 1회뿐


def test_send_next_bucket_allows_resend(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms7')
    share_id, token = _mk_share(order_id)
    assert _send(client, share_id, token).status_code == 200
    clock['now'] += 6  # 다음 버킷 — 의도적 재발송 허용
    assert _send(client, share_id, token).status_code == 200
    assert len(sms_stub) == 2


def test_send_outbox_anchor_done_and_event_recorded(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms8')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    db_session.expire_all()
    rows = db_session.query(DomainSideEffectOutbox).filter_by(effect_type='SHARE_SMS').all()
    assert len(rows) == 1
    assert rows[0].status == 'DONE'  # 동기 전용 — 워커 재소비 방지
    assert rows[0].payload.get('sync_only') is True
    assert token not in str(rows[0].payload)  # bearer 미격납
    events = db_session.query(OrderEvent).filter_by(event_type='SHARE_SMS').all()
    assert len(events) == 1 and events[0].payload['status'] == 'sent'


# --- 벤더 오류 표면화 --------------------------------------------------------------


def test_send_vendor_error_surfaced_not_silent(client, db, monkeypatch, clock):
    monkeypatch.setenv('SOLAPI_SENDER_PHONE', '0212345678')

    def _boom(**kwargs):
        raise TimeoutError('vendor down')

    monkeypatch.setattr(ka, '_solapi_send_text', _boom)
    order_id = _mk_order().id
    _login(client, 'sms9')
    share_id, token = _mk_share(order_id)
    resp = _send(client, share_id, token)
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['data']['sent'] is False
    assert body['data']['error'] == 'network'
    db_session.expire_all()
    events = db_session.query(OrderEvent).filter_by(event_type='SHARE_SMS').all()
    assert events[0].payload['status'] == 'failed'


# --- 감사 -------------------------------------------------------------------------


def test_send_audit_masked_phone_no_token(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms10')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    db_session.expire_all()
    logs = db_session.query(SecurityLog).filter(SecurityLog.action == 'SHARE_SMS_SENT').all()
    assert len(logs) == 1
    detail = str(logs[0].detail or {})
    assert token not in detail
    assert '01024736730' not in detail  # 원문 수신번호 미격납(마스킹)
    assert logs[0].detail['sent'] is True
