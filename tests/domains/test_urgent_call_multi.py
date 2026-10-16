"""복수 긴급 호출: 입력 검증·전체 롤백·수신자별 receipt 회귀."""
import pytest

from models import PartnerOrg
from tests.domains.test_urgent_call_global import (
    DomainSideEffectOutbox, Notification, NotificationEvent, NotificationUserState,
    Order, SecurityLog, User, WRITE_HEADERS, _call, _login, _mk_order, _mk_user, db,
)


def _multi(client, ids, **extra):
    return client.post('/erp/api/urgent-call', json={
        'target_user_ids': ids, 'message': '확인 부탁', **extra,
    }, headers=WRITE_HEADERS)


def test_system_accounts_group_as_other_without_changing_teams(client, db):
    caller = _mk_user('multi_sender', '보낸이')
    bot = _mk_user('naver_ingest_bot', '네이버 수집봇', team='CS')
    owner = _mk_user('naver_unassigned', '미배정 (네이버 수집)', team='SALES')
    staff = _mk_user('multi_staff', '실제 직원', team='SALES')
    _login(client, caller)
    rows = {u['id']: u for u in client.get('/erp/api/urgent-targets').get_json()['targets']}
    for u in (bot, owner):
        assert rows[u.id]['team_label'] == '기타'
        assert rows[u.id]['selection_team'] == '_ETC'
    assert rows[staff.id]['selection_team'] == 'SALES'
    assert db.get(User, bot.id).team == 'CS'
    assert db.get(User, owner.id).team == 'SALES'


def test_multi_dedupes_commits_once_and_each_user_acks_own_receipt(client, db, monkeypatch):
    sender = _mk_user('multi_sender', '보낸이')
    a = _mk_user('multi_a', '첫째')
    b = _mk_user('multi_b', '둘째')
    aid, bid = a.id, b.id
    _login(client, sender)
    commits, emits = [], []
    original = db.commit
    monkeypatch.setattr(db, 'commit', lambda: (commits.append(True), original())[-1])
    monkeypatch.setattr('foms.services.notifications.realtime_notifications.emit_erp_notification_to_users',
                        lambda ids, payload: emits.append((list(ids), payload)))
    response = _multi(client, [aid, bid, aid])
    assert response.status_code == 200, response.get_json()
    assert len(commits) == 1
    notifs = db.query(Notification).order_by(Notification.id).all()
    assert [n.target_user_id for n in notifs] == [aid, bid]
    assert db.query(NotificationUserState).count() == 2
    assert db.query(NotificationEvent).count() == 2
    assert db.query(DomainSideEffectOutbox).count() == 2
    assert db.query(SecurityLog).filter_by(action='URGENT_MENTION_SENT').count() == 2
    assert [(ids, p['notification_id']) for ids, p in emits] == [
        ([aid], notifs[0].id), ([bid], notifs[1].id)]
    _login(client, db.get(User, aid))
    assert client.post(f'/erp/api/notifications/{notifs[0].id}/ack', headers=WRITE_HEADERS).status_code == 200
    assert db.query(NotificationUserState).filter_by(user_id=bid).one().ack_at is None


@pytest.mark.parametrize('ids', [[], None, '1,2', [True], [1.5], ['1.0'], [0], [-1], [{}], [1] * 501])
def test_invalid_arrays_are_400_without_writes(client, db, ids):
    sender = _mk_user('multi_sender', '보낸이')
    _login(client, sender)
    assert _multi(client, ids).status_code == 400
    assert db.query(Notification).count() == 0


@pytest.mark.parametrize('extra', [{'target_user_id': 123}, {'message': {}}, {'message': ['x']}, {'message': ' '}])
def test_ambiguous_or_invalid_body_is_400(client, db, extra):
    sender = _mk_user('multi_sender', '보낸이')
    target = _mk_user('multi_a', '첫째')
    _login(client, sender)
    assert _multi(client, [target.id], **extra).status_code == 400
    assert db.query(Notification).count() == 0


@pytest.mark.parametrize('case,status', [('self', 400), ('unknown', 404), ('inactive', 422), ('partner', 422)])
def test_one_invalid_target_prevents_all_delivery(client, db, monkeypatch, case, status):
    sender = _mk_user('multi_sender', '보낸이')
    good = _mk_user('multi_a', '첫째')
    bad = _mk_user('multi_b', '둘째', is_active=case != 'inactive')
    if case == 'partner':
        org = PartnerOrg(name='외부')
        db.add(org)
        db.flush()
        bad.partner_org_id = org.id
    bad_id = {'self': sender.id, 'unknown': 999999}.get(case, bad.id)
    _login(client, sender)
    emits = []
    monkeypatch.setattr('foms.services.notifications.realtime_notifications.emit_erp_notification_to_users',
                        lambda *args: emits.append(args))
    assert _multi(client, [good.id, bad_id]).status_code == status
    assert db.query(Notification).count() == 0
    assert db.query(DomainSideEffectOutbox).count() == 0
    assert emits == []


def test_second_outbox_failure_rolls_back_first_recipient_too(client, db, monkeypatch):
    from foms.api import notifications

    sender = _mk_user('multi_sender', '보낸이')
    targets = [_mk_user(f'multi_{i}', f'받는이{i}').id for i in range(2)]
    db.commit()
    _login(client, sender)
    original = notifications.enqueue_side_effect
    count, emits = [], []

    def fail_second(*args, **kwargs):
        count.append(True)
        if len(count) == 2:
            raise RuntimeError('second outbox failure')
        return original(*args, **kwargs)

    monkeypatch.setattr(notifications, 'enqueue_side_effect', fail_second)
    monkeypatch.setattr('foms.services.notifications.realtime_notifications.emit_erp_notification_to_users',
                        lambda *args: emits.append(args))
    assert _multi(client, targets).status_code == 500
    assert len(count) == 2
    for model in (Notification, NotificationUserState, NotificationEvent, DomainSideEffectOutbox):
        assert db.query(model).count() == 0
    assert db.query(SecurityLog).filter_by(action='URGENT_MENTION_SENT').count() == 0
    assert emits == []


def test_order_rate_budget_counts_recipients_and_never_partially_sends(client, db):
    sender = _mk_user('multi_sender', '보낸이')
    ids = [_mk_user(f'multi_{i}', f'받는이{i}').id for i in range(3)]
    order = _mk_order()
    oid, version, sd = order.id, order.mutation_version, dict(order.structured_data)
    _login(client, sender)
    assert _multi(client, ids, order_id=oid).status_code == 200
    assert _multi(client, ids, order_id=oid).status_code == 429
    assert db.query(Notification).count() == 3
    assert _multi(client, ids[:2], order_id=oid).status_code == 200
    assert db.query(Notification).count() == 5
    assert db.get(Order, oid).mutation_version == version
    assert db.get(Order, oid).structured_data == sd


@pytest.mark.parametrize('body', [[1, 2], 'invalid', True])
def test_non_object_json_is_400(client, db, body):
    sender = _mk_user('multi_sender', '보낸이')
    _login(client, sender)
    assert client.post('/erp/api/urgent-call', json=body, headers=WRITE_HEADERS).status_code == 400
