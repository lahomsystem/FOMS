"""도면·계약서 '상담 먼저' 알림톡 — 발송·확인코드·채널톡 상담 자동 발송 테스트(설계서 2026-10-20).

벤더는 모두 스텁이다: Solapi 는 ``kakao_alimtalk._solapi_send``, 채널톡은
``channel_client.send_user_chat_message`` 를 바꿔 끼운다(네트워크 0).
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.api.share as share_routes
from db import db_session
from foms.services import channel_client
from foms.services import channel_inbound
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as osvc
from foms.services import share_consult as sc
from models import ChannelInboundEventLog, Order, OrderEvent, OrderShareToken, User

_SD = {
    'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'}},
    'items': [{'product_name': '무몰딩 여닫이', 'quantity': 1, 'price': 100000}],
}

_ENV_KEYS = ('SOLAPI_PF_ID_LAHOM', 'SOLAPI_PF_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_BOTH_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD',
             'SOLAPI_TEMPLATE_SHARE_CONSULT_ID_LAHOM', 'SOLAPI_TEMPLATE_SHARE_CONSULT_ID_HAUD',
             'SOLAPI_SENDER_PHONE_LAHOM', 'SOLAPI_SENDER_PHONE_HAUD', 'SOLAPI_SENDER_PHONE')


def _mk_order(**kwargs) -> Order:
    fields = dict(
        received_date=datetime.date(2026, 10, 20),
        customer_name='임다슬',
        phone='010-2473-6730',
        address='Seoul',
        product='가구',
        status='ERPORDER',
        is_erp_order=True,
        manager_name='박민수',
        structured_data=dict(_SD),
    )
    fields.update(kwargs)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, username) -> int:
    user = User(username=username, password=generate_password_hash('pw'),
                role='STAFF', team='CS', name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess['user_id'] = user.id
        sess['username'] = username
        sess['role'] = 'STAFF'
    return user.id


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
    """알림톡 성공 스텁 — HAUD 브랜드에 상담 먼저 템플릿까지 켠다."""
    calls = []

    def _fake(**kwargs):
        calls.append(kwargs)
        return 'ATA-1'

    monkeypatch.setattr(ka, '_solapi_send', _fake)
    for name in _ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SOLAPI_PF_ID_HAUD', 'PF-HAUD')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_ID_HAUD', 'TPL-HAUD')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_BOTH_ID_HAUD', 'TPL-BOTH')
    monkeypatch.setenv('SOLAPI_TEMPLATE_SHARE_CONSULT_ID_HAUD', 'TPL-CONSULT')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    return calls


@pytest.fixture
def chat_stub(monkeypatch):
    """채널톡 상담 쓰기 스텁 — 보낸 글을 모은다. ``fail`` 을 켜면 공개 메시지가 실패한다."""
    state = {'sent': [], 'fail': False, 'fail_from': None}

    def _fake(user_chat_id, plain_text, *, bot_name='FOMS', private=False):
        state['sent'].append({'chat': user_chat_id, 'text': plain_text, 'private': private})
        public_count = sum(1 for m in state['sent'] if not m['private'])
        failing = state['fail'] or (state['fail_from'] is not None and public_count > state['fail_from'])
        if failing and not private:
            return {'success': False, 'message_id': None, 'error': 'provider_error'}
        return {'success': True, 'message_id': f"m{len(state['sent'])}", 'error': None}

    monkeypatch.setattr(channel_client, 'send_user_chat_message', _fake)
    return state


def _send(client, share_id, token, **extra):
    return client.post(f'/api/share/send-alimtalk/{share_id}', json={'token': token, **extra})


def _request_event(order_id, *, kind='bundle', split=False, code='ABC234',
                   now=None) -> OrderEvent:
    event = OrderEvent(order_id=order_id, event_type='SHARE_ALIMTALK', payload={
        'status': 'sent', 'kind': kind,
        'consult': sc.build_consult_record(order_id=order_id, code=code, kind=kind,
                                           split=split, now=now)})
    db_session.add(event)
    db_session.commit()
    return event


def _message(order_id, code='ABC234', *, person='user', chat_type='userChat'):
    return {'type': 'message', 'entity': {
        'chatType': chat_type, 'chatId': 'uc-1', 'personType': person, 'id': 'msg-1',
        'plainText': f"문서 받기\n[하우드] 도면·계약서 준비 완료\n임다슬 고객님, 안녕하세요.\n"
                     f"■ 주문번호: {order_id}\n■ 확인코드: {code}\n■ 담당: 박민수 010-1234-5678"}}


# --- 발송(알림톡) -------------------------------------------------------------


def test_consult_send_uses_template_without_links(client, db, ata_stub):
    order_id = _mk_order().id
    _login(client, 'cf1')
    share_id, token = _mk_share(order_id, 'bundle')
    before = db_session.query(OrderShareToken).count()

    res = _send(client, share_id, token, split=True)

    assert res.status_code == 200 and res.get_json()['data']['sent'] is True
    call = ata_stub[0]
    assert call['template_id'] == 'TPL-CONSULT'
    assert call['disable_sms'] is True
    variables = call['variables']
    assert set(variables) == {'#{고객명}', '#{문서종류}', '#{주문번호}', '#{확인코드}',
                              '#{담당자}', '#{담당자연락처}'}
    assert variables['#{주문번호}'] == str(order_id)
    assert variables['#{문서종류}'] == '도면·계약서'
    code = variables['#{확인코드}']
    assert len(code) == 6
    # 알림톡에는 링크가 없으니 짝 링크를 새로 발급하지 않는다.
    assert db_session.query(OrderShareToken).count() == before
    event = (db_session.query(OrderEvent)
             .filter_by(order_id=order_id, event_type='SHARE_ALIMTALK').one())
    consult = event.payload['consult']
    assert event.payload['status'] == 'sent'
    assert consult['docs'] == 'both' and consult['split'] is True
    assert consult['code_hash'] == sc.hash_code(order_id, code)
    assert code not in str(event.payload)


def test_consult_estimate_only_label(client, db, ata_stub):
    order_id = _mk_order().id
    _login(client, 'cf2')
    share_id, token = _mk_share(order_id, 'estimate')

    assert _send(client, share_id, token).status_code == 200
    assert ata_stub[0]['variables']['#{문서종류}'] == '계약서'


def test_without_consult_env_old_path_unchanged(client, db, ata_stub, monkeypatch):
    monkeypatch.delenv('SOLAPI_TEMPLATE_SHARE_CONSULT_ID_HAUD')
    order_id = _mk_order().id
    _login(client, 'cf3')
    share_id, token = _mk_share(order_id, 'drawing')

    assert _send(client, share_id, token).status_code == 200
    assert ata_stub[0]['template_id'] == 'TPL-HAUD'
    assert 'disable_sms' not in ata_stub[0]


def test_consult_false_picks_old_path(client, db, ata_stub):
    order_id = _mk_order().id
    _login(client, 'cf4')
    share_id, token = _mk_share(order_id, 'bundle')

    assert _send(client, share_id, token, consult=False).status_code == 200
    assert ata_stub[0]['template_id'] == 'TPL-BOTH'


# --- 고객이 [문서 받기]를 눌렀을 때(채널톡 상담) ---------------------------------


def test_parse_consult_message():
    assert sc.parse_consult_message('■ 주문번호: 5231\n■ 확인코드: ab2c3d') == (5231, 'AB2C3D')
    assert sc.parse_consult_message('주문번호 : 77 확인코드：XYZ234') == (77, 'XYZ234')
    assert sc.parse_consult_message('주문번호: 5231') is None
    assert sc.parse_consult_message('') is None


def test_delivers_links_together(app, chat_stub):
    order = _mk_order()
    request = _request_event(order.id)

    outcome = sc.handle_user_chat_message(db_session, _message(order.id))

    assert outcome == 'delivered'
    public = [m for m in chat_stub['sent'] if not m['private']]
    notes = [m for m in chat_stub['sent'] if m['private']]
    assert len(public) == 1 and public[0]['chat'] == 'uc-1'
    assert '▶ 도면 보기' in public[0]['text'] and '▶ 계약서 보기' in public[0]['text']
    assert public[0]['text'].count('/s/') == 2
    assert len(notes) == 1 and f'주문 {order.id}' in notes[0]['text']
    kinds = sorted(t.kind for t in db_session.query(OrderShareToken).filter_by(order_id=order.id))
    assert kinds == ['drawing', 'estimate']
    db_session.expire_all()
    assert db_session.get(OrderEvent, request.id).payload['consult']['deliveries'] == 1
    delivered = (db_session.query(OrderEvent)
                 .filter_by(order_id=order.id, event_type='SHARE_CONSULT_DELIVERED').one())
    assert delivered.payload['status'] == 'sent'


def test_delivers_links_split(app, chat_stub):
    order = _mk_order()
    _request_event(order.id, split=True)

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'
    public = [m for m in chat_stub['sent'] if not m['private']]
    assert len(public) == 2
    assert '▶ 도면 보기' in public[0]['text'] and '계약서' not in public[0]['text']
    assert '▶ 계약서 보기' in public[1]['text']


def test_drawing_only_sends_one_link(app, chat_stub):
    order = _mk_order()
    _request_event(order.id, kind='drawing')

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'
    public = [m for m in chat_stub['sent'] if not m['private']]
    assert public[0]['text'].count('/s/') == 1 and '도면 보기' in public[0]['text']


def test_wrong_code_sends_nothing_to_customer(app, chat_stub):
    order = _mk_order()
    _request_event(order.id, code='ABC234')

    assert sc.handle_user_chat_message(db_session, _message(order.id, code='ZZZ999')) == 'rejected'
    assert all(m['private'] for m in chat_stub['sent'])
    assert db_session.query(OrderShareToken).filter_by(order_id=order.id).count() == 0
    assert (db_session.query(OrderEvent)
            .filter_by(order_id=order.id, event_type='SHARE_CONSULT_REJECTED').count() == 1)


def test_code_of_other_order_does_not_match(app, chat_stub):
    first, second = _mk_order(), _mk_order()
    _request_event(first.id, code='ABC234')

    assert sc.handle_user_chat_message(db_session, _message(second.id, code='ABC234')) == 'rejected'


def test_expired_code_rejected(app, chat_stub):
    order = _mk_order()
    long_ago = datetime.datetime(2020, 1, 1)
    _request_event(order.id, now=long_ago)

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'rejected'


def test_delivery_limit(app, chat_stub):
    order = _mk_order()
    _request_event(order.id)
    for _ in range(sc.MAX_DELIVERIES):
        assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'limit'


@pytest.mark.parametrize('person,chat_type,expected', [
    ('manager', 'userChat', 'ignored_not_customer'),
    ('bot', 'userChat', 'ignored_not_customer'),
    ('user', 'group', 'ignored_not_user_chat'),
])
def test_ignores_non_customer_messages(app, chat_stub, person, chat_type, expected):
    order = _mk_order()
    _request_event(order.id)

    outcome = sc.handle_user_chat_message(
        db_session, _message(order.id, person=person, chat_type=chat_type))

    assert outcome == expected
    assert chat_stub['sent'] == []


def test_send_failure_revokes_links(app, chat_stub):
    order = _mk_order()
    request = _request_event(order.id)
    chat_stub['fail'] = True

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'send_failed'
    db_session.expire_all()
    rows = db_session.query(OrderShareToken).filter_by(order_id=order.id).all()
    assert rows and all(r.revoked_at is not None for r in rows)
    assert db_session.get(OrderEvent, request.id).payload['consult']['deliveries'] == 0


def test_split_partial_failure_keeps_sent_link(app, chat_stub):
    """따로따로에서 첫 글만 가면 그 링크는 살리고, 못 보낸 링크만 회수한다."""
    order = _mk_order()
    request = _request_event(order.id, split=True)
    chat_stub['fail_from'] = 1  # 두 번째 공개 글부터 실패

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'partial'
    db_session.expire_all()
    rows = {r.kind: r for r in db_session.query(OrderShareToken).filter_by(order_id=order.id)}
    assert rows['drawing'].revoked_at is None
    assert rows['estimate'].revoked_at is not None
    assert db_session.get(OrderEvent, request.id).payload['consult']['deliveries'] == 1
    notes = [m for m in chat_stub['sent'] if m['private']]
    assert notes and '나머지는 쓰지 못했어요' in notes[-1]['text']


def test_staff_revoke_stops_resend(app, chat_stub):
    """직원이 보낸 링크를 회수하면 같은 코드로 다시 눌러도 새 링크가 나가지 않는다."""
    order = _mk_order()
    _request_event(order.id)
    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'delivered'
    for row in db_session.query(OrderShareToken).filter_by(order_id=order.id):
        osvc.revoke_token(row)
    db_session.commit()
    before = db_session.query(OrderShareToken).filter_by(order_id=order.id).count()

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'rejected'
    assert db_session.query(OrderShareToken).filter_by(order_id=order.id).count() == before


def test_rejection_note_does_not_reveal_order(app, chat_stub):
    """없는 주문과 틀린 코드가 같은 메모 — 어느 주문이 있는지 드러내지 않는다."""
    order = _mk_order()
    _request_event(order.id, code='ABC234')
    sc.handle_user_chat_message(db_session, _message(order.id, code='ZZZ999'))
    sc.handle_user_chat_message(db_session, _message(999999, code='ZZZ999'))

    notes = [m['text'] for m in chat_stub['sent'] if m['private']]
    assert len(notes) == 2 and notes[0] == notes[1]
    assert str(order.id) not in notes[0]


def test_partner_order_rejected(app, chat_stub, monkeypatch):
    order = _mk_order()
    _request_event(order.id)
    monkeypatch.setattr(sc, 'is_partner_order', lambda _order: True)

    assert sc.handle_user_chat_message(db_session, _message(order.id)) == 'rejected'
    assert all(m['private'] for m in chat_stub['sent'])


# --- 웹훅 워커 경로 ----------------------------------------------------------------


def test_worker_routes_user_chat_away_from_order_intake(app, chat_stub):
    """고객 상담 글에 주문 접수 항목이 있어도 주문 접수 파싱으로 가지 않는다."""
    order = _mk_order()
    _request_event(order.id)
    payload = _message(order.id)
    payload['entity']['plainText'] += '\n고객명: 홍길동\n연락처: 010-1111-2222\n주소: 서울'
    log = ChannelInboundEventLog(dedupe_key='evt_consult_1', payload_hash='c' * 64,
                                 chat_type='message', source_chat_id='uc-1',
                                 status='received', raw_payload=payload)
    db_session.add(log)
    db_session.commit()
    log_id = log.id

    channel_inbound.process_inbound_job(log_id)

    db_session.expire_all()
    saved = db_session.get(ChannelInboundEventLog, log_id)
    assert saved.status == 'user_chat_handled'
    assert saved.error_reason == 'delivered'
    assert saved.receipt_state != 'ACCEPTED'


def test_send_user_chat_message_payload(monkeypatch):
    seen = {}

    def _fake_call(payload):
        seen.update(payload)
        return {'result': {'message': {'id': 'm-9'}}}

    monkeypatch.setattr(channel_client, '_call_native_function', _fake_call)
    result = channel_client.send_user_chat_message('uc-7', '메모', private=True)

    assert result == {'success': True, 'message_id': 'm-9', 'error': None}
    assert seen['method'] == 'writeUserChatMessage'
    assert seen['params']['userChatId'] == 'uc-7'
    assert seen['params']['dto']['options'] == ['MESSAGE_OPTION_PRIVATE']


def test_send_user_chat_message_provider_error(monkeypatch):
    monkeypatch.setattr(channel_client, '_call_native_function',
                        lambda payload: {'error': {'message': 'forbidden'}})
    result = channel_client.send_user_chat_message('uc-7', '안녕')
    assert result['success'] is False and result['error'] == 'provider_error'
