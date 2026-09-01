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
from models import (DomainSideEffectOutbox, Order, OrderEvent, OrderShareToken,
                    SecurityLog, User)

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


# --- 통합(버튼 2개) 템플릿 전환 — 심사 승인 대비 배선 -------------------------------


def _mk_bundle_share(order_id):
    """bundle 링크 발급(계약서 동결 스냅샷 동반 — 실제 발급 경로와 같은 모양)."""
    from foms.services.order_share import build_estimate_snapshot
    from models import Order as _Order
    order = db_session.get(_Order, order_id)
    row, token = osvc.create_share_token(db_session, order_id, 'bundle',
                                         snapshot=build_estimate_snapshot(order))
    db_session.commit()
    return row.id, token


def test_bundle_send_uses_single_link_template_until_both_is_registered(
        client, db, ata_stub, clock):
    """통합 템플릿 env 가 없으면 지금처럼 링크 1개(통합 열람 페이지)로 나간다."""
    order_id = _mk_order().id
    _login(client, 'ata-bundle-legacy')
    share_id, token = _mk_bundle_share(order_id)

    _send(client, share_id, token)

    call = ata_stub[0]
    assert call['template_id'] == 'TPL-HAUD'
    assert call['variables']['#{토큰}'] == token
    assert call['variables']['#{문서종류}'] == '도면·계약서'
    assert '#{도면토큰}' not in call['variables']


def test_bundle_send_switches_to_two_button_template_by_env(
        client, db, ata_stub, monkeypatch, clock):
    """통합 템플릿이 등록되면 도면·계약서 링크를 그 자리에서 발급해 버튼 2개로 보낸다."""
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD', 'TPL-HAUD-BOTH')
    order_id = _mk_order().id
    _login(client, 'ata-bundle-both')
    share_id, token = _mk_bundle_share(order_id)

    resp = _send(client, share_id, token)
    assert resp.status_code == 200 and resp.get_json()['data']['sent'] is True

    call = ata_stub[0]
    assert call['template_id'] == 'TPL-HAUD-BOTH'
    variables = call['variables']
    assert variables['#{도면토큰}'] and variables['#{계약서토큰}']
    assert variables['#{도면토큰}'] != variables['#{계약서토큰}']
    assert '#{토큰}' not in variables and '#{문서종류}' not in variables

    # 실제로 링크 2개가 발급됐고, 계약서 쪽은 동결 스냅샷을 들고 있다.
    rows = (db_session.query(OrderShareToken)
            .filter(OrderShareToken.order_id == order_id)
            .order_by(OrderShareToken.id.asc()).all())
    kinds = [r.kind for r in rows]
    assert kinds == ['bundle', 'drawing', 'estimate']
    assert rows[2].snapshot is not None


def test_bundle_send_two_button_records_pair_in_audit(client, db, ata_stub, monkeypatch,
                                                      clock):
    """어느 링크 두 개가 나갔는지 감사에 남는다(회수·문의 추적용)."""
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD', 'TPL-HAUD-BOTH')
    order_id = _mk_order().id
    _login(client, 'ata-bundle-audit')
    share_id, token = _mk_bundle_share(order_id)

    _send(client, share_id, token)

    log = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == 'SHARE_ALIMTALK_SENT')
           .order_by(SecurityLog.id.desc()).first())
    assert log is not None
    assert log.detail['template'] == 'share_both'
    assert log.detail['drawing_share_id'] and log.detail['estimate_share_id']


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
    assert call['variables']['#{담당자연락처}'] == '1566-0703'   # 라홈 외 발주사 = 하우드
    # 이름도 맞춘다 — 번호는 본사인데 이름만 현장 담당자면 고객이 헷갈린다.
    assert call['variables']['#{담당자}'] == '고객센터'
    # 문자 대체발송 발신번호도 같은 번호(벤더에는 숫자만).
    assert call['from_'] == '15660703'


def test_send_alimtalk_regional_lahom_uses_lahom_number(client, db, ata_stub, monkeypatch,
                                                        clock):
    """발주사가 라홈이면 라홈 본사 번호로 안내·발신한다(그 외 발주사는 하우드 번호)."""
    monkeypatch.setenv('SOLAPI_PF_ID_LAHOM', 'PF-LAHOM')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_ID_LAHOM', 'TPL-LAHOM')
    sd = {**_SD, 'parties': {**_SD['parties'], 'orderer': {'name': '라홈'}}}
    order_id = _mk_order(structured_data=sd, is_regional=True).id
    _login(client, 'ata-regional-lahom')
    share_id, token = _mk_share(order_id)
    _send(client, share_id, token)

    call = ata_stub[0]
    assert call['variables']['#{담당자연락처}'] == '1566-0792'
    assert call['from_'] == '15660792'


def test_send_alimtalk_regional_contact_env_override(client, db, ata_stub, monkeypatch,
                                                     clock):
    """본사 대표번호가 바뀌면 env 로 갈아끼운다(코드 재배포 없이)."""
    monkeypatch.setenv('FOMS_REGIONAL_CONTACT_PHONE_HAUD', '1588-0000')
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


# --- 발송 흔적 칩(공유) ----------------------------------------------------------
#
# 사용자 요청 2026-09-01: 도면+계약서 묶음을 보냈으면 주문 화면 칩 자리에 '보냈다'가
# 남아야 한다. 예약 안내 흔적(alimtalk_measurement)과 대칭이되 별개 레코드다.


def test_bundle_send_records_share_trace(client, db, ata_stub, clock):
    """묶음 발송이 sd['alimtalk_share'] 를 남기고 응답에도 실어 준다."""
    order_id = _mk_order().id
    uid = _login(client, 'trace1')
    share_id, token = _mk_share(order_id, kind='bundle')

    resp = _send(client, share_id, token)

    assert resp.status_code == 200
    last = resp.get_json()['data']['last_share']
    assert last['kind'] == 'bundle' and last['channel'] == 'alimtalk'
    assert last['error'] is None and last['sent_at']
    assert last['sent_by'] == uid and last['sent_by_name'] == 'trace1'

    record = (db_session.get(Order, order_id).structured_data or {}).get('alimtalk_share')
    assert record == last


def test_drawing_send_leaves_no_share_trace(client, db, ata_stub, clock):
    """음성 대조군: 추적 대상이 아닌 종류(도면 단독)는 아무것도 안 남긴다."""
    order_id = _mk_order().id
    _login(client, 'trace2')
    share_id, token = _mk_share(order_id, kind='drawing')

    resp = _send(client, share_id, token)

    assert resp.status_code == 200 and resp.get_json()['data']['last_share'] is None
    assert 'alimtalk_share' not in (db_session.get(Order, order_id).structured_data or {})


def test_failed_bundle_send_records_reason(client, db, ata_stub, clock, monkeypatch):
    """벤더 실패도 흔적을 남긴다 — 실패를 숨기면 칩이 '안 보냄'과 구별되지 않는다."""
    def _boom(**kwargs):
        raise RuntimeError('vendor down')

    monkeypatch.setattr(ka, '_solapi_send', _boom)
    order_id = _mk_order().id
    _login(client, 'trace3')
    share_id, token = _mk_share(order_id, kind='bundle')

    resp = _send(client, share_id, token)

    last = resp.get_json()['data']['last_share']
    assert last['sent_at'] is None and last['error']
    record = (db_session.get(Order, order_id).structured_data or {}).get('alimtalk_share')
    assert record['error'] == last['error']


def test_share_trace_does_not_touch_measurement_record(client, db, ata_stub, clock):
    """예약 안내 흔적을 덮지 않는다 — 두 레코드는 독립이다."""
    order = _mk_order()
    sd = dict(order.structured_data or {})
    sd['alimtalk_measurement'] = {'sent_at': '2026-08-01T00:00:00', 'error': None}
    order.structured_data = sd
    from sqlalchemy.orm.attributes import flag_modified as _fm
    _fm(order, 'structured_data')
    db_session.commit()
    order_id = order.id

    _login(client, 'trace4')
    share_id, token = _mk_share(order_id, kind='bundle')
    _send(client, share_id, token)

    fresh = (db_session.get(Order, order_id).structured_data or {})
    assert fresh['alimtalk_measurement']['sent_at'] == '2026-08-01T00:00:00'
    assert fresh['alimtalk_share']['kind'] == 'bundle'
