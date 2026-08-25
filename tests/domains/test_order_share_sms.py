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


_BRAND_ENVS = ('SOLAPI_SENDER_PHONE_LAHOM', 'SOLAPI_SENDER_PHONE_HAUD',
               'SOLAPI_SENDER_FALLBACK_LAHOM', 'SOLAPI_SENDER_FALLBACK_HAUD')


@pytest.fixture
def sms_stub(monkeypatch):
    """성공 스텁 — 호출 인자 수집. 브랜드 env 는 비워 legacy 폴백 경로를 격리한다."""
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return 'SMS-1'

    monkeypatch.setattr(ka, '_solapi_send_text', _fake)
    for name in _BRAND_ENVS:
        monkeypatch.delenv(name, raising=False)
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


# --- 발신 3단 우선순위 (T8.1 — 담당자 → 브랜드 대표번호 → 구 SOLAPI_SENDER_PHONE) ---


def test_send_legacy_fallback_when_no_manager_no_brand_env(client, db, sms_stub, clock):
    order_id = _mk_order().id
    _login(client, 'sms1')
    share_id, token = _mk_share(order_id)
    resp = _send(client, share_id, token)
    assert resp.status_code == 200 and resp.get_json()['data']['sent'] is True
    assert sms_stub[0]['from_'] == '0212345678'
    assert sms_stub[0]['to'] == '01024736730'
    assert '/s/' in sms_stub[0]['text']
    assert '도면' in sms_stub[0]['text']


def test_send_regional_uses_head_office_sender(client, db, sms_stub, clock):
    """지방 주문 문자는 본사 CS 번호로 나간다 — 안내 번호와 발신 번호가 갈리지 않게."""
    manager = User(username='smsrgnmgr', password=generate_password_hash('pw'),
                   role='STAFF', team='CS', name='박협력', is_active=True,
                   sender_phone='01055557777')
    db_session.add(manager)
    db_session.commit()
    order_id = _mk_order(manager_name='박협력', is_regional=True).id
    _login(client, 'sms-regional-from')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)

    assert sms_stub[0]['from_'] == '15660792'


def test_regional_self_sms_body_shows_head_office_contact(client, db, clock):
    """'내 문자로 보내기' 본문(알림톡 문구 미러)도 지방 주문이면 본사 CS 번호를 안내한다."""
    from foms.api.share import share_link_message

    order = _mk_order(is_regional=True, manager_name='박협력')
    with client.application.test_request_context():
        body = share_link_message(order, kind='drawing',
                                  url='https://example.test/s/tok', brand='HAUD')

    assert '담당자 연락처 : 1566-0792' in body


def test_send_ignores_actor_sender_phone(client, db, sms_stub, clock):
    # 구 규칙 폐기 확인: 발송 버튼 누른 직원의 sender_phone 은 더 이상 안 쓴다.
    order_id = _mk_order().id
    _login(client, 'sms2', sender_phone='01099998888')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    assert sms_stub[0]['from_'] == '0212345678'  # legacy 폴백 (actor 번호 아님)


def test_send_uses_order_manager_sender_phone(client, db, sms_stub, clock):
    # ① 담당자 개인번호 — 버튼 누른 사람(actor)이 아니라 주문 담당자 기준.
    manager = User(username='mgr1', password=generate_password_hash('pw'),
                   role='STAFF', team='CS', name='김담당', is_active=True,
                   sender_phone='01011112222')
    db_session.add(manager)
    db_session.commit()
    order_id = _mk_order(manager_name='김담당').id
    _login(client, 'sms21', sender_phone='01099998888')
    share_id, token = _mk_share(order_id)
    resp = _send(client, share_id, token)
    assert resp.get_json()['data']['sent'] is True
    assert sms_stub[0]['from_'] == '01011112222'


def test_send_manager_without_registration_falls_to_brand(client, db, sms_stub,
                                                          monkeypatch, clock):
    # 담당자는 있으나 sender_phone 미등록 — ② 브랜드 대표번호로 폴백(기본 HAUD).
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    manager = User(username='mgr2', password=generate_password_hash('pw'),
                   role='STAFF', team='CS', name='박미등록', is_active=True)
    db_session.add(manager)
    db_session.commit()
    order_id = _mk_order(manager_name='박미등록').id
    _login(client, 'sms22')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    assert sms_stub[0]['from_'] == '15660703'


def test_send_brand_branch_lahom(client, db, sms_stub, monkeypatch, clock):
    # ② 브랜드 분기 — 발주사명에 '라홈' 포함 시 LAHOM 대표번호(resolve_brand SSOT).
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_LAHOM', '15660792')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    sd = {**_SD, 'parties': {**_SD['parties'], 'orderer': {'name': '라홈퍼니처'}}}
    order_id = _mk_order(structured_data=sd).id
    _login(client, 'sms23')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    assert sms_stub[0]['from_'] == '15660792'


def test_send_brand_branch_haud_default(client, db, sms_stub, monkeypatch, clock):
    # ② 발주사에 '라홈' 없으면 전부 HAUD (알림톡 브랜드 분기와 동일 판정).
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_LAHOM', '15660792')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    sd = {**_SD, 'parties': {**_SD['parties'], 'orderer': {'name': '한샘몰'}}}
    order_id = _mk_order(structured_data=sd).id
    _login(client, 'sms24')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    assert sms_stub[0]['from_'] == '15660703'


def test_send_not_configured_503(client, db, monkeypatch, clock):
    monkeypatch.delenv('SOLAPI_SENDER_PHONE', raising=False)
    for name in _BRAND_ENVS:
        monkeypatch.delenv(name, raising=False)
    order_id = _mk_order().id
    _login(client, 'sms25')
    share_id, token = _mk_share(order_id)
    assert _send(client, share_id, token).status_code == 503


# --- ② 실패 → ③ 브랜드 백업번호 1회 재시도 (T8.1) ----------------------------------


def _flaky_stub(monkeypatch, fail_from: set[str]):
    """지정 발신번호만 실패하는 스텁 — (from_, to) 호출 기록 반환."""
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        if kwargs['from_'] in fail_from:
            raise TimeoutError('vendor down')
        return 'SMS-1'

    monkeypatch.setattr(ka, '_solapi_send_text', _fake)
    return calls


def test_send_brand_failure_retries_backup_once(client, db, monkeypatch, clock):
    # ② 대표번호 벤더 실패 → ③ 백업번호 같은 요청 내 1회 재시도, 앵커 1개 유지.
    for name in _BRAND_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    monkeypatch.setenv('SOLAPI_SENDER_FALLBACK_HAUD', '01044644260')
    calls = _flaky_stub(monkeypatch, fail_from={'15660703'})
    order_id = _mk_order().id
    _login(client, 'sms26')
    share_id, token = _mk_share(order_id)
    resp = _send(client, share_id, token)
    body = resp.get_json()
    assert resp.status_code == 200 and body['data']['sent'] is True
    assert [c['from_'] for c in calls] == ['15660703', '01044644260']
    db_session.expire_all()
    rows = db_session.query(DomainSideEffectOutbox).filter_by(effect_type='SHARE_SMS').all()
    assert len(rows) == 1 and rows[0].status == 'DONE'  # 멱등 앵커 1개 그대로
    events = db_session.query(OrderEvent).filter_by(event_type='SHARE_SMS').all()
    assert len(events) == 1 and events[0].payload['status'] == 'sent'
    attempts = events[0].payload['attempts']  # 시도 2회 payload 기록
    assert [a['source'] for a in attempts] == ['brand', 'brand_fallback']
    assert attempts[0]['error'] == 'network' and attempts[1]['error'] is None
    assert '15660703' not in str(attempts)  # 발신번호 원문 미격납(마스킹)


def test_send_brand_failure_without_backup_surfaces_error(client, db, monkeypatch, clock):
    for name in _BRAND_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    calls = _flaky_stub(monkeypatch, fail_from={'15660703'})
    order_id = _mk_order().id
    _login(client, 'sms27')
    share_id, token = _mk_share(order_id)
    body = _send(client, share_id, token).get_json()
    assert body['data']['sent'] is False and body['data']['error'] == 'network'
    assert len(calls) == 1  # 백업 미설정 — 재시도 없음


def test_send_manager_failure_no_retry(client, db, monkeypatch, clock):
    # ① 담당자 개인번호 실패는 재시도 대상 아님(백업번호는 브랜드 전용).
    for name in _BRAND_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_SENDER_FALLBACK_HAUD', '01044644260')
    calls = _flaky_stub(monkeypatch, fail_from={'01011113333'})
    manager = User(username='mgr3', password=generate_password_hash('pw'),
                   role='STAFF', team='CS', name='이실패', is_active=True,
                   sender_phone='01011113333')
    db_session.add(manager)
    db_session.commit()
    order_id = _mk_order(manager_name='이실패').id
    _login(client, 'sms28')
    share_id, token = _mk_share(order_id)
    body = _send(client, share_id, token).get_json()
    assert body['data']['sent'] is False and body['data']['error'] == 'network'
    assert len(calls) == 1  # manager 출처 — 브랜드 백업 재시도 없음


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
    for name in _BRAND_ENVS:
        monkeypatch.delenv(name, raising=False)

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
    assert logs[0].detail['sender_source'] == 'legacy'  # T8.1 최종 시도 출처 기록
