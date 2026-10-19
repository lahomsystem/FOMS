"""긴급 호출 알림은 도면 수신자의 주문 작업실로 연결한다. 권한은 넓히지 않는다."""
import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from db import db_session, engine
from foms.api.notifications import _resolve_notification_deep_link
from models import Notification, NotificationRecipientSource, NotificationUserState
from tests.domains.test_urgent_call_global import _call, _login, _mk_order, _mk_user


def _existing_notification(user_id: int, order_id: int | None, **kwargs) -> Notification:
    """과거 알림과 본인 수신 상태를 저장해 목록 소급 적용을 검증한다."""
    notification = Notification(notification_type=kwargs.pop('notification_type', 'URGENT_MENTION'),
                                order_id=order_id, target_type='USER', target_user_id=user_id,
                                title='기존 알림', message='확인 요청', is_urgent=True, **kwargs)
    db_session.add(notification)
    db_session.flush()
    db_session.add(NotificationUserState(notification_id=notification.id, user_id=user_id,
                                        recipient_source=NotificationRecipientSource.TARGET_USER))
    db_session.flush()
    return notification


def test_sales_call_opens_exact_drawing_workbench_without_edit_permission(client, app):
    order, other = _mk_order(), _mk_order()
    sender = _mk_user('route_sales_sender', '영업 발신자', team='SALES')
    drawing = _mk_user('route_drawing_target', '도면 수신자', team='DRAWING')
    oid, other_id, tid = order.id, other.id, drawing.id
    db_session.commit()
    _login(client, sender)
    assert _call(client, tid, order_id=oid).status_code == 200
    assert _call(client, tid, order_id=other_id).status_code == 200
    _login(client, db_session.get(type(drawing), tid))
    response = client.get('/erp/api/notifications').get_json()
    assert response['success'] is True
    assert {row['order_id']: row['deep_link_url'] for row in response['notifications']} == {
        oid: f'/erp/drawing-workbench/{oid}', other_id: f'/erp/drawing-workbench/{other_id}',
    }
    for row in response['notifications']:
        page = client.get(row['deep_link_url'])
        assert page.status_code == 200
    edit = client.get(f'/edit/{oid}?open=erp-order')
    assert edit.status_code == 302
    with client.session_transaction() as session:
        assert any('ERP Order 주문 수정 권한이 없습니다' in message for _, message in session['_flashes'])


@pytest.mark.parametrize('team,expected_workbench', [('DRAWING', True), (' drawing ', True),
                                                    ('CS', False), ('SALES', False), (None, False)])
def test_existing_notifications_use_current_recipient_team(client, app, team, expected_workbench):
    user = _mk_user('route_existing', '기존 알림 수신자', team=team)
    outsider = _mk_user('route_outsider', '다른 수신자', team='DRAWING')
    order = _mk_order()
    uid, oid = user.id, order.id
    mine = _existing_notification(uid, oid)
    hidden = _existing_notification(outsider.id, oid)
    mine_id, hidden_id = mine.id, hidden.id
    db_session.commit()
    _login(client, user)
    rows = client.get('/erp/api/notifications').get_json()['notifications']
    assert [row['id'] for row in rows] == [mine_id]
    assert hidden_id not in {row['id'] for row in rows}
    expected = f'/erp/drawing-workbench/{oid}' if expected_workbench else None
    assert rows[0]['deep_link_url'] == expected


def test_no_order_and_other_notification_types_keep_existing_links(client, app):
    user = _mk_user('route_no_order', '도면 직원', team='DRAWING')
    order = _mk_order()
    no_order = _existing_notification(user.id, None)
    transferred = _existing_notification(user.id, order.id, notification_type='DRAWING_TRANSFERRED')
    ordinary = _existing_notification(user.id, order.id, notification_type='ANNOUNCEMENT')
    ids, oid = (no_order.id, transferred.id, ordinary.id), order.id
    db_session.commit()
    _login(client, user)
    links = {row['id']: row['deep_link_url'] for row in client.get('/erp/api/notifications').get_json()['notifications']}
    assert links == {ids[0]: None, ids[1]: f'/erp/drawing-workbench/{oid}?tab=timeline', ids[2]: None}
    assert _resolve_notification_deep_link(SimpleNamespace(notification_type='URGENT_MENTION', order_id=oid), {})['deep_link_url'] is None


def test_already_read_and_acknowledged_call_gets_workbench_link(client, app):
    """확인까지 끝난 옛 호출도 데이터 수정/재발송 없이 링크가 계산된다."""
    user = _mk_user('route_old_ack', '도면 직원', team='DRAWING')
    oid = _mk_order().id
    notification = _existing_notification(user.id, oid)
    state = db_session.query(NotificationUserState).filter_by(notification_id=notification.id).one()
    state.read_at = state.ack_at = datetime.datetime(2026, 10, 16, 1, 0, 0)
    db_session.commit()
    _login(client, user)
    row = client.get('/erp/api/notifications').get_json()['notifications'][0]
    assert row['deep_link_url'] == f'/erp/drawing-workbench/{oid}'
    assert row['is_read'] is True and row['ack_at']


def test_many_existing_alerts_add_no_user_queries(client, app):
    user = _mk_user('route_many', '도면 직원', team='DRAWING')
    oid = _mk_order().id
    for _ in range(20):
        _existing_notification(user.id, oid)
    db_session.commit()
    _login(client, user)
    selects = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'FROM users' in statement:
            selects.append(statement)

    event.listen(engine, 'before_cursor_execute', capture)
    try:
        rows = client.get('/erp/api/notifications?limit=30').get_json()['notifications']
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert len(rows) == 20
    assert all(row['deep_link_url'] == f'/erp/drawing-workbench/{oid}' for row in rows)
    assert len(selects) <= 1  # 요청 인증 사용자만 조회, 알림마다 수신자를 조회하지 않는다.
