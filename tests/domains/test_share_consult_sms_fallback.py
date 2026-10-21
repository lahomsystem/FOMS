"""'상담 먼저' 알림톡 — 카톡 실패 고객에게 링크 문자 자동 발송(워커 스윕).

솔라피 결과 조회는 ``lookup`` 주입으로, 문자 발송은 ``ka._solapi_send_text`` 스텁으로 바꿔
네트워크 없이 돈다. 설계서 ``docs/specs/2026-10-21-consult-sms-fallback-design.md``.
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.api import share_sms_fallback as fb
from foms.services import kakao_alimtalk as ka
from foms.services import share_consult as sc
from foms.services.orders import drawing_customer_send_view as view_mod
from models import OrderEvent, OrderShareToken
from tests.domains.test_share_consult_first import (  # noqa: F401 — ata_stub·db 는 fixture
    _login,
    _mk_order,
    _mk_share,
    ata_stub,
    db,
)

NOW = datetime.datetime(2026, 10, 21, 7, 0, 0)


@pytest.fixture
def sms_stub(app, monkeypatch):
    """문자 발송 스텁 — 보낸 문자를 모은다. ``fail`` 을 켜면 벤더 오류를 낸다."""
    state = {'sent': [], 'fail': False}

    def _fake(*, to, from_, text):
        if state['fail']:
            raise RuntimeError('vendor down')
        state['sent'].append({'to': to, 'from': from_, 'text': text})
        return 'M-SMS'

    monkeypatch.setattr(ka, '_solapi_send_text', _fake)
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_HAUD', '15660703')
    monkeypatch.setenv('SOLAPI_SENDER_PHONE_LAHOM', '15660792')
    yield state
    db_session.rollback()


def _sent_event(order_id, *, kind='drawing', minutes_ago=3, message_id='M-1', **extra) -> OrderEvent:
    consult = sc.build_consult_record(order_id=order_id, code='ABC234', kind=kind, split=False, now=NOW)
    if message_id:
        consult['message_id'] = message_id
    event = OrderEvent(order_id=order_id, event_type='SHARE_ALIMTALK',
                       created_at=NOW - datetime.timedelta(minutes=minutes_ago),
                       payload={'status': 'sent', 'kind': kind, 'consult': consult,
                                'round_at': 'R1', 'round': 1, **extra})
    db_session.add(event)
    db_session.commit()
    return event


def _consult(event_id):
    db_session.expire_all()
    return db_session.get(OrderEvent, event_id).payload['consult']


def test_kakao_failure_sends_link_sms_once(sms_stub):
    order = _mk_order()
    event = _sent_event(order.id)

    counts = fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda _mid: '3104')

    assert counts == {'sms_sent': 1}
    (sms,) = sms_stub['sent']
    assert sms['to'] == '01024736730' and sms['from'] == '15660703'
    assert '/s/' in sms['text']
    consult = _consult(event.id)
    assert consult['kakao_result'] == 'failed' and consult['kakao_status'] == '3104'
    assert consult['sms_fallback']['status'] == 'sent'
    sms_event = (db_session.query(OrderEvent)
                 .filter_by(order_id=order.id, event_type='SHARE_SMS').one())
    assert sms_event.payload['source'] == 'consult_fallback'
    assert sms_event.payload['status'] == 'sent' and sms_event.payload['round_at'] == 'R1'
    # 두 번째 바퀴에는 다시 보내지 않는다.
    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda _mid: '3104') == {}
    assert len(sms_stub['sent']) == 1


def test_delivered_sends_nothing(sms_stub):
    order = _mk_order()
    event = _sent_event(order.id)

    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda _mid: '4000') == {'delivered': 1}
    assert sms_stub['sent'] == []
    assert _consult(event.id)['kakao_result'] == 'delivered'


def test_pending_waits_then_gives_up_without_sms(sms_stub):
    order = _mk_order()
    event = _sent_event(order.id, minutes_ago=5)

    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda _mid: '3000') == {'pending': 1}
    assert 'kakao_result' not in _consult(event.id)

    later = NOW + fb.GIVE_UP_AFTER
    assert fb.run_consult_sms_sweep(db_session, now=later, lookup=lambda _mid: '3000') == {'unknown': 1}
    assert _consult(event.id)['kakao_result'] == 'unknown'
    assert sms_stub['sent'] == []


def test_too_fresh_and_non_consult_are_skipped(sms_stub):
    order = _mk_order()
    _sent_event(order.id, minutes_ago=0)              # 90초 전 — 아직 묻지 않는다
    _sent_event(order.id, message_id=None)            # 벤더 id 없음
    old_path = OrderEvent(order_id=order.id, event_type='SHARE_ALIMTALK',
                          created_at=NOW - datetime.timedelta(minutes=3),
                          payload={'status': 'sent', 'kind': 'drawing'})  # 옛 경로(링크 알림톡)
    db_session.add(old_path)
    db_session.commit()
    calls = []

    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda mid: calls.append(mid) or '3104') == {}
    assert calls == [] and sms_stub['sent'] == []


def test_sms_failure_is_recorded_and_link_revoked(sms_stub):
    sms_stub['fail'] = True
    order = _mk_order()
    event = _sent_event(order.id)

    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda _mid: '3104') == {'sms_failed': 1}
    consult = _consult(event.id)
    assert consult['kakao_result'] == 'failed' and consult['sms_fallback']['status'] == 'failed'
    row = db_session.get(OrderShareToken, consult['sms_fallback']['share_id'])
    assert row.revoked_at is not None


def test_phone_override_is_not_texted(sms_stub):
    """보내기 창에서 번호를 바꿔 보낸 건은 바꾼 번호를 저장하지 않으므로 문자를 보내지 않는다."""
    order = _mk_order()
    event = _sent_event(order.id, to_phone_override=True)

    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=lambda _mid: '3104') == {'sms_skipped': 1}
    assert _consult(event.id)['sms_fallback'] == {'status': 'skipped', 'reason': 'phone_override'}
    assert sms_stub['sent'] == []


def test_lookup_error_retries_next_tick(sms_stub):
    order = _mk_order()
    event = _sent_event(order.id)

    def _boom(_mid):
        raise RuntimeError('timeout')

    assert fb.run_consult_sms_sweep(db_session, now=NOW, lookup=_boom) == {'lookup_failed': 1}
    assert 'kakao_result' not in _consult(event.id)


def test_status_line_names_fallback_sms():
    assert view_mod._FALLBACK_SMS_LABEL == '카톡 실패 → 문자'
    assert view_mod._CHANNEL_WITH[view_mod._FALLBACK_SMS_LABEL] == '카톡이 안 돼 문자로'


def test_send_alimtalk_keeps_vendor_message_id(client, db, ata_stub):
    """'상담 먼저' 발송은 벤더 message id 를 consult 에 남긴다(워커가 결과를 묻는 열쇠)."""
    order_id = _mk_order().id
    _login(client, 'fb1')
    share_id, token = _mk_share(order_id, 'drawing')

    assert client.post(f'/api/share/send-alimtalk/{share_id}', json={'token': token}).status_code == 200
    event = (db_session.query(OrderEvent)
             .filter_by(order_id=order_id, event_type='SHARE_ALIMTALK').one())
    assert event.payload['consult']['message_id'] == 'ATA-1'
