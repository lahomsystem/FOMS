"""견적 공유 스냅샷 — 화이트리스트·동결·64KB 캡 테스트 (Phase A T6).

D5: 해당 브랜드 계좌만·내부 플래그 차단(키 부재 assert).
D6: 발급 시점 동결 — 주문 수정 후에도 저장 스냅샷 불변.
"""
import datetime
import json

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import order_share as osvc
from models import Order, OrderShareToken, User

# 브랜드별 계좌 리터럴(estimate_defaults SSOT) — 교차 유출 assert 에 쓴다.
_HAUD_ACCOUNTS = ('461-082990-04-011', '818737-00-002568')
_FACTORY2_ACCOUNT = '461-091619-01-010'

_SD = {
    'parties': {
        'customer': {'name': '임다슬', 'phone': '010-2473-6730'},
        'manager': {'name': '김담당', 'phone': '010-1111-2222'},
        'orderer': {'name': '하우드'},
    },
    'site': {'address_full': '서울시 강남구'},
    'schedule': {'construction': {'date': '2026-09-01'}},
    'items': [
        {'product_name': '무몰딩 여닫이', 'quantity': 2, 'price': 500000,
         'color': '화이트', 'internal_route': 'FACTORY-LINE-3'},
    ],
    'payment': {'deposit': 100000, 'discount': 50000},
}


def _mk_order(sd=None, **kwargs) -> Order:
    fields = dict(
        received_date=datetime.date(2026, 8, 12),
        customer_name='임다슬',
        phone='010-2473-6730',
        address='Seoul',
        product='가구',
        status='ERPORDER',
        is_erp_order=True,
        structured_data=sd if sd is not None else json.loads(json.dumps(_SD)),
    )
    fields.update(kwargs)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# --- 화이트리스트 (D5) ------------------------------------------------------------


def test_snapshot_default_brand_has_only_haud_accounts(db):
    order = _mk_order()
    snap = osvc.build_estimate_snapshot(order)
    text = json.dumps(snap, ensure_ascii=False)
    assert _FACTORY2_ACCOUNT not in text, '타 브랜드(라홈) 계좌 유출'
    accounts = [a['account'] for a in snap['payment_info']['accounts']]
    assert list(_HAUD_ACCOUNTS) == accounts


def test_snapshot_factory2_has_only_factory2_account(db):
    sd = json.loads(json.dumps(_SD))
    sd['flags'] = {'factory2': True}
    order = _mk_order(sd=sd)
    snap = osvc.build_estimate_snapshot(order)
    text = json.dumps(snap, ensure_ascii=False)
    for acc in _HAUD_ACCOUNTS:
        assert acc not in text, '타 브랜드(하우드) 계좌 유출'
    assert snap['payment_info']['accounts'][0]['account'] == _FACTORY2_ACCOUNT
    assert snap['company_info']['name'] == '라홈시스템'


def test_snapshot_blocks_internal_keys(db):
    order = _mk_order()
    snap = osvc.build_estimate_snapshot(order)
    text = json.dumps(snap, ensure_ascii=False)
    for banned in ('factory2', 'is_lahom', 'variants', 'internal_route',
                   'estimate_preview', 'manual_rows'):
        assert banned not in text, f'차단 키 유출: {banned}'
    # 품목 행은 화이트리스트 키만 남는다.
    assert set(snap['items'][0].keys()) == set(osvc._SNAPSHOT_ITEM_KEYS)


def test_snapshot_grand_total_formula(db):
    """출고가=품목합+자유입력-할인(예약금 제외), 잔금=출고가-예약금."""
    order = _mk_order()
    snap = osvc.build_estimate_snapshot(order)
    assert snap['items_subtotal'] == 1_000_000
    assert snap['shipping_price'] == 1_000_000 - 50_000
    assert snap['deposit_amount'] == 100_000
    assert snap['balance_amount'] == snap['shipping_price'] - 100_000
    assert snap['manager_name'] == '김담당'
    assert snap['company_info']['customer_center']


# --- 동결 (D6) --------------------------------------------------------------------


def test_snapshot_frozen_after_order_mutation(db):
    order = _mk_order()
    snap = osvc.build_estimate_snapshot(order)
    row, _ = osvc.create_share_token(db, order.id, 'estimate', snapshot=snap)
    db.commit()
    frozen = json.dumps(row.snapshot, sort_keys=True)

    # 주문 가격 변경(deepcopy+flag_modified 패턴)
    import copy
    from sqlalchemy.orm.attributes import flag_modified
    sd = copy.deepcopy(order.structured_data or {})
    sd['items'][0]['price'] = 9_999_999
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db.commit()
    db.expire_all()

    fresh = db.get(OrderShareToken, row.id)
    assert json.dumps(fresh.snapshot, sort_keys=True) == frozen
    assert '9999999' not in json.dumps(fresh.snapshot)


# --- 64KB 캡 ----------------------------------------------------------------------


def test_snapshot_over_64kb_raises(db):
    sd = json.loads(json.dumps(_SD))
    sd['items'] = [
        {'product_name': 'X' * 600, 'quantity': 1, 'price': 1000, 'color': 'Y' * 200}
        for _ in range(200)
    ]
    order = _mk_order(sd=sd)
    with pytest.raises(osvc.SnapshotTooLargeError):
        osvc.build_estimate_snapshot(order)


# --- API 해금 ---------------------------------------------------------------------


def _login(client, username='eststaff', role='STAFF') -> int:
    user = User(username=username, password=generate_password_hash('pw'),
                role=role, team='CS', name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = username
        sess['role'] = role
    return uid


def test_api_create_estimate_stores_snapshot(client, db):
    order_id = _mk_order().id
    _login(client)
    resp = client.post(f'/api/share/create/{order_id}', json={'kind': 'estimate'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    row = db_session.get(OrderShareToken, data['share_id'])
    assert row.kind == 'estimate'
    assert row.snapshot and row.snapshot['snapshot_version'] == 1


def test_api_create_estimate_over_cap_400(client, db):
    sd = json.loads(json.dumps(_SD))
    sd['items'] = [
        {'product_name': 'X' * 600, 'quantity': 1, 'price': 1000, 'color': 'Y' * 200}
        for _ in range(200)
    ]
    order_id = _mk_order(sd=sd).id
    _login(client, 'eststaff2')
    resp = client.post(f'/api/share/create/{order_id}', json={'kind': 'estimate'})
    assert resp.status_code == 400
    assert '스냅샷' in resp.get_json()['error']
    # 실패 시 토큰 행이 남지 않는다.
    assert db_session.query(OrderShareToken).filter_by(order_id=order_id).count() == 0
