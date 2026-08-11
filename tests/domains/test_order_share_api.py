"""고객 공유 직원 API — create/revoke 계약 테스트 (Phase A T3).

권한 실패는 ``role_required`` 규약대로 302 redirect 다(JSON 403 아님 — 데코레이터
선례, test_kakao_alimtalk_api.py). 감사는 ``log_access``(SecurityLog) 구조화 컬럼을
직접 assert 한다.
"""
import datetime

import pytest
from werkzeug.security import generate_password_hash

import foms.api.share as share_routes
from db import db_session
from foms.services import order_share as osvc
from foms.services.datetime_kst import now_utc_naive
from models import Order, OrderShareToken, SecurityLog, User

_CREATE = '/api/share/create'
_REVOKE = '/api/share/revoke'


def _mk_order(**kwargs) -> Order:
    fields = dict(
        received_date=datetime.date(2026, 8, 11),
        customer_name='임다슬',
        phone='010-2473-6730',
        address='Seoul',
        product='가구',
        status='ERPORDER',
        is_erp_order=True,
        structured_data={},
    )
    fields.update(kwargs)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, username: str, role: str = 'STAFF') -> int:
    user = User(
        username=username,
        password=generate_password_hash('pw'),
        role=role,
        team='CS',
        name=f'{username}-name',
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = username
        sess['role'] = role
    return uid


def _security_logs(action: str) -> list[SecurityLog]:
    db_session.expire_all()
    return db_session.query(SecurityLog).filter(SecurityLog.action == action).all()


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# --- create ---------------------------------------------------------------------


def test_create_returns_token_url_once_and_audits(client, db):
    order_id = _mk_order().id
    uid = _login(client, 'staff1')

    resp = client.post(f'{_CREATE}/{order_id}', json={'kind': 'drawing'})
    body = resp.get_json()

    assert resp.status_code == 200
    assert body['success'] is True
    data = body['data']
    assert data['kind'] == 'drawing'
    assert len(data['token']) >= 43
    assert f"/s/{data['token']}" in data['url']
    # 저장은 해시만 — 원문은 응답 밖 어디에도 없다.
    row = db_session.get(OrderShareToken, data['share_id'])
    assert row.token_hash == osvc.hash_token(data['token'])
    assert row.created_by_user_id == uid

    logs = _security_logs('SHARE_LINK_CREATED')
    assert len(logs) == 1
    assert logs[0].target_id == order_id
    # 감사 원장에 bearer 자격(토큰 원문·URL) 축적 금지.
    assert data['token'] not in (logs[0].message or '')
    assert data['token'] not in str(logs[0].detail or '')


def test_create_default_kind_is_drawing(client, db):
    order = _mk_order()
    _login(client, 'staff2')
    resp = client.post(f'{_CREATE}/{order.id}', json={})
    assert resp.get_json()['data']['kind'] == 'drawing'


def test_create_estimate_blocked_until_t6(client, db):
    order = _mk_order()
    _login(client, 'staff3')
    resp = client.post(f'{_CREATE}/{order.id}', json={'kind': 'estimate'})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'estimate_not_available'


def test_create_unknown_kind_400(client, db):
    order = _mk_order()
    _login(client, 'staff4')
    resp = client.post(f'{_CREATE}/{order.id}', json={'kind': 'contract'})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'unknown_kind'


def test_create_missing_order_404(client, db):
    _login(client, 'staff5')
    resp = client.post(f'{_CREATE}/999999', json={'kind': 'drawing'})
    assert resp.status_code == 404


def test_create_draft_order_404(client, db):
    order = _mk_order(structured_data={'meta': {'draft': True}})
    _login(client, 'staff6')
    resp = client.post(f'{_CREATE}/{order.id}', json={'kind': 'drawing'})
    assert resp.status_code == 404


def test_create_requires_login_redirects(client, db):
    order = _mk_order()
    resp = client.post(f'{_CREATE}/{order.id}', json={'kind': 'drawing'})
    assert resp.status_code == 302


def test_create_viewer_role_redirects(client, db):
    order = _mk_order()
    _login(client, 'viewer1', role='VIEWER')
    resp = client.post(f'{_CREATE}/{order.id}', json={'kind': 'drawing'})
    assert resp.status_code == 302


# --- revoke ---------------------------------------------------------------------


def test_revoke_marks_row_and_audits(client, db):
    order_id = _mk_order().id
    _login(client, 'staff7')
    row, _ = osvc.create_share_token(db_session, order_id, 'drawing')
    db_session.commit()
    share_id = row.id

    resp = client.post(f'{_REVOKE}/{share_id}')
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(OrderShareToken, share_id).revoked_at is not None

    logs = _security_logs('SHARE_LINK_REVOKED')
    assert len(logs) == 1
    assert logs[0].target_id == order_id


def test_revoke_is_idempotent_200(client, db):
    order = _mk_order()
    _login(client, 'staff8')
    row, _ = osvc.create_share_token(db_session, order.id, 'drawing')
    db_session.commit()
    first = client.post(f'{_REVOKE}/{row.id}').get_json()['data']['revoked_at']
    second = client.post(f'{_REVOKE}/{row.id}')
    assert second.status_code == 200
    assert second.get_json()['data']['revoked_at'] == first


def test_revoke_missing_404(client, db):
    _login(client, 'staff9')
    assert client.post(f'{_REVOKE}/999999').status_code == 404


def test_revoke_works_for_deleted_order(client, db):
    """주문이 삭제돼도 잔존 링크 회수는 허용(안전 방향 조작)."""
    order = _mk_order()
    _login(client, 'staff10')
    row, _ = osvc.create_share_token(db_session, order.id, 'drawing')
    order.deleted_at = now_utc_naive()
    db_session.commit()
    assert client.post(f'{_REVOKE}/{row.id}').status_code == 200
