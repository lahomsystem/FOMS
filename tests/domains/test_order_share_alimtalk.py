"""공유 링크 알림톡 발송 — 변수 폴백·멱등·발신 우선순위·감사 테스트 (Phase A 후속).

Solapi 는 ``kakao_alimtalk._solapi_send`` 를 monkeypatch 해 스텁한다(네트워크 0).
멱등은 send-sms 와 동일 계약 — ``(effect_type, dedupe_key)`` UNIQUE 가 같은 5초
버킷의 2번째 요청을 IntegrityError→409 로 차단한다.
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.api.share as share_routes
from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from models import DomainSideEffectOutbox, Order, OrderEvent, SecurityLog, User

_SD = {
    'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
    'items': [{'product_name': '무몰딩 여닫이', 'quantity': 1, 'price': 100000}],
}

_ENV_KEYS = ('SOLAPI_PF_ID_LAHOM', 'SOLAPI_PF_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_ID_HAUD',
             'SOLAPI_SENDER_PHONE_LAHOM', 'SOLAPI_SENDER_PHONE_HAUD',
             'SOLAPI_SENDER_FALLBACK_LAHOM', 'SOLAPI_SENDER_FALLBACK_HAUD',
             'SOLAPI_SENDER_PHONE')


def _mk_order(**kwargs) -> Order:
    fields = dict(
        received_date=datetime.date(2026, 8, 18),
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
def ata_stub(monkeypatch):
    """알림톡 성공 스텁 — 호출 인자 수집. 기본 HAUD env 구성."""
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return 'ATA-1'

    monkeypatch.setattr(ka, '_solapi_send', _fake)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_PF_ID_HAUD', 'PF-HAUD')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_ID_HAUD', 'TPL-HAUD')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    return calls


@pytest.fixture
def clock(monkeypatch):
    state = {'now': 2_000_000.0}
    monkeypatch.setattr(share_routes.time, 'time', lambda: state['now'])
    return state


def _send(client, share_id, token):
    return client.post(f'/api/share/send-alimtalk/{share_id}', json={'token': token})


# --- 발송·변수 -------------------------------------------------------------------


def test_send_alimtalk_success_with_variables(client, db, ata_stub, clock):
    order_id = _mk_order().id
    _login(client, 'ata1')
    share_id, token = _mk_share(order_id)
    resp = _send(client, share_id, token)
    assert resp.status_code == 200 and resp.get_json()['data']['sent'] is True
    call = ata_stub[0]
    assert call['to'] == '01024736730'
    assert call['from_'] == '15660703'   # 담당자 없음 — 브랜드 대표 발신
    assert call['pf_id'] == 'PF-HAUD' and call['template_id'] == 'TPL-HAUD'
    v = call['variables']
    assert v['#{고객명}'] == '임다슬'
    assert v['#{문서종류}'] == '도면'
    assert v['#{토큰}'] == token
    assert v['#{담당자}'] == '고객센터'          # manager_name 없음 폴백
    assert v['#{담당자연락처}'] == '15660703'    # 브랜드 대표번호 폴백


def test_send_alimtalk_manager_variables_and_sender(client, db, ata_stub, clock):
    manager = User(username='atamgr', password=generate_password_hash('pw'),
                   role='STAFF', team='CS', name='김알림', is_active=True,
                   sender_phone='01055556666')
    db_session.add(manager)
    db_session.commit()
    order_id = _mk_order(manager_name='김알림').id
    _login(client, 'ata2')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    call = ata_stub[0]
    assert call['from_'] == '01055556666'                 # ① 담당자 발신(failover 대비)
    assert call['variables']['#{담당자}'] == '김알림'
    assert call['variables']['#{담당자연락처}'] == '01055556666'


def test_send_alimtalk_regional_shows_head_office_contact(client, db, ata_stub, clock):
    """지방 주문은 도면 컨펌을 본사 CS 가 받는다 — 안내 연락처가 본사 대표번호다."""
    manager = User(username='atargn', password=generate_password_hash('pw'),
                   role='STAFF', team='CS', name='박협력', is_active=True,
                   sender_phone='01055557777')
    db_session.add(manager)
    db_session.commit()
    order_id = _mk_order(manager_name='박협력', is_regional=True).id
    _login(client, 'ata-regional')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)

    call = ata_stub[0]
    assert call['variables']['#{담당자연락처}'] == '1566-0792'
    # 이름도 맞춘다 — 번호는 본사인데 이름만 현장 담당자면 고객이 헷갈린다.
    assert call['variables']['#{담당자}'] == '고객센터'
    # 문자 대체발송 발신번호도 같은 번호(벤더에는 숫자만).
    assert call['from_'] == '15660792'


def test_send_alimtalk_regional_contact_env_override(client, db, ata_stub, monkeypatch,
                                                     clock):
    """본사 대표번호가 바뀌면 env 로 갈아끼운다(코드 재배포 없이)."""
    monkeypatch.setenv('FOMS_REGIONAL_CONTACT_PHONE', '1588-0000')
    order_id = _mk_order(is_regional=True).id
    _login(client, 'ata-regional-env')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)

    assert ata_stub[0]['variables']['#{담당자연락처}'] == '1588-0000'


def test_send_alimtalk_lahom_brand_branch(client, db, ata_stub, monkeypatch, clock):
    monkeypatch.setenv('SOLAPI_PF_ID_LAHOM', 'PF-LAHOM')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_ID_LAHOM', 'TPL-LAHOM')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_LAHOM', '15660792')
    sd = {**_SD, 'parties': {**_SD['parties'], 'orderer': {'name': '라홈'}}}
    order_id = _mk_order(structured_data=sd).id
    _login(client, 'ata3')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    call = ata_stub[0]
    assert call['pf_id'] == 'PF-LAHOM' and call['template_id'] == 'TPL-LAHOM'
    assert call['from_'] == '15660792'


def test_send_alimtalk_not_configured_503(client, db, ata_stub, monkeypatch, clock):
    monkeypatch.delenv('SOLAPI_TEMPLATE_SHARE_ID_HAUD', raising=False)
    order_id = _mk_order().id
    _login(client, 'ata4')
    share_id, token = _mk_share(order_id)
    assert _send(client, share_id, token).status_code == 503
    assert ata_stub == []


# --- 토큰·죽은 링크 ---------------------------------------------------------------


def test_send_alimtalk_wrong_token_400(client, db, ata_stub, clock):
    order_id = _mk_order().id
    _login(client, 'ata5')
    share_id, _ = _mk_share(order_id)
    resp = _send(client, share_id, 'wrong-token')
    assert resp.status_code == 400 and resp.get_json()['error'] == 'token_mismatch'
    assert ata_stub == []


def test_send_alimtalk_revoked_410(client, db, ata_stub, clock):
    order_id = _mk_order().id
    _login(client, 'ata6')
    share_id, token = _mk_share(order_id)
    from models import OrderShareToken
    osvc.revoke_token(db_session.get(OrderShareToken, share_id))
    db_session.commit()
    assert _send(client, share_id, token).status_code == 410
    assert ata_stub == []


# --- 멱등·앵커 --------------------------------------------------------------------


def test_send_alimtalk_duplicate_in_bucket_409(client, db, ata_stub, clock):
    order_id = _mk_order().id
    _login(client, 'ata7')
    share_id, token = _mk_share(order_id)
    assert _send(client, share_id, token).status_code == 200
    assert _send(client, share_id, token).status_code == 409
    assert len(ata_stub) == 1


def test_send_alimtalk_anchor_done_and_no_token_in_payload(client, db, ata_stub, clock):
    order_id = _mk_order().id
    _login(client, 'ata8')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    db_session.expire_all()
    rows = db_session.query(DomainSideEffectOutbox).filter_by(effect_type='SHARE_ALIMTALK').all()
    assert len(rows) == 1 and rows[0].status == 'DONE'
    assert token not in str(rows[0].payload)
    events = db_session.query(OrderEvent).filter_by(event_type='SHARE_ALIMTALK').all()
    assert len(events) == 1 and events[0].payload['status'] == 'sent'


# --- 벤더 실패·감사 ---------------------------------------------------------------


def test_send_alimtalk_vendor_error_surfaced(client, db, ata_stub, monkeypatch, clock):
    def _boom(**kwargs):
        raise TimeoutError('vendor down')

    monkeypatch.setattr(ka, '_solapi_send', _boom)
    order_id = _mk_order().id
    _login(client, 'ata9')
    share_id, token = _mk_share(order_id)
    body = _send(client, share_id, token).get_json()
    assert body['data']['sent'] is False and body['data']['error'] == 'network'
    db_session.expire_all()
    events = db_session.query(OrderEvent).filter_by(event_type='SHARE_ALIMTALK').all()
    assert events[0].payload['status'] == 'failed'


def test_send_alimtalk_audit_masked_no_token(client, db, ata_stub, clock):
    order_id = _mk_order().id
    _login(client, 'ata10')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)
    db_session.expire_all()
    logs = db_session.query(SecurityLog).filter(
        SecurityLog.action == 'SHARE_ALIMTALK_SENT').all()
    assert len(logs) == 1
    detail = str(logs[0].detail or {})
    assert token not in detail
    assert '01024736730' not in detail
    assert logs[0].detail['sent'] is True
    assert logs[0].detail['sender_source'] == 'brand'
