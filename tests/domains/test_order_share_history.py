"""고객 열람 계약서 원장 — 적재·중복 판정·조회 계약 (SHARE-HIST-00).

스펙: docs/specs/2026-09-01-share-contract-view-history-design.md

계약서가 라이브 반영으로 바뀐 뒤(2026-09-01) "고객이 어제 본 금액"이 남지 않는다는
공백을 메우는 원장이다. 여기서 고정하는 것:

* 내용이 **바뀐 순간에만** 새 행 (같은 내용 재열람은 ``view_count`` 로 접힌다)
* A→B→A 되돌림은 **3행** — 최신 행과만 비교해야 시간축이 산다
* 원장 쓰기 실패가 고객 화면을 죽이지 않는다
* ``drawing`` 링크는 0행 (음성 대조군 — 계약 내용이 없다)
"""
import copy
import datetime

import pytest
from werkzeug.security import generate_password_hash
from sqlalchemy.orm.attributes import flag_modified

import foms.api.share as share_routes
from db import db_session
from foms.services import order_share as osvc
from foms.services import order_share_history as hist
from models import (Order, OrderAttachment, OrderShareSnapshot, OrderShareToken,
                    SecurityLog, User)


class FakeR2Storage:
    """r2 storage stub — 도면 경로가 fail-closed(503) 로 죽지 않게 한다."""

    storage_type = 'r2'

    def get_download_url(self, key: str, expires_in: int = 3600,
                         response_content_disposition=None) -> str:
        return f'https://r2.example/{key}?sig=1'

    def read_file_bytes(self, key: str) -> bytes:
        return b'BYTES:' + key.encode('utf-8')


_EST_SD = {
    'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'},
                'manager': {'name': '김담당'}},
    'site': {'address_full': '서울시 강남구'},
    'items': [{'product_name': '무몰딩 여닫이', 'quantity': 2, 'price': 500000,
               'color': '화이트'}],
    'payment': {'deposit': 100000},
}


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def r2(monkeypatch):
    stub = FakeR2Storage()
    monkeypatch.setattr(share_routes, 'get_storage', lambda: stub)
    return stub


def _mk_order(structured_data=None, **kwargs) -> Order:
    fields = dict(
        received_date=datetime.date(2026, 9, 1),
        customer_name='임다슬',
        phone='010-2473-6730',
        address='Seoul',
        product='가구',
        status='ERPORDER',
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else {},
    )
    fields.update(kwargs)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order


def _mk_share(order, kind='estimate') -> tuple[OrderShareToken, str]:
    snapshot = (osvc.build_estimate_snapshot(order)
                if kind in osvc.SNAPSHOT_KINDS else None)
    row, token = osvc.create_share_token(db_session, order.id, kind, snapshot=snapshot)
    db_session.commit()
    return row, token


def _add_drawing_attachment(order, key='plan.png') -> OrderAttachment:
    att = OrderAttachment(
        order_id=order.id,
        filename=key,
        file_type='image',
        category='drawing',
        storage_key=f'orders/{order.id}/drawing/{key}',
    )
    db_session.add(att)
    db_session.commit()
    return att


def _set_price(order, price: int) -> None:
    sd = copy.deepcopy(order.structured_data)
    sd['items'][0]['price'] = price
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db_session.commit()


def _rows(share_id: int) -> list[OrderShareSnapshot]:
    db_session.expire_all()
    return (db_session.query(OrderShareSnapshot)
            .filter(OrderShareSnapshot.share_token_id == share_id)
            .order_by(OrderShareSnapshot.id)
            .all())


def _login(client, username: str, role: str = 'STAFF') -> int:
    user = User(username=username, password=generate_password_hash('pw'), role=role,
                team='CS', name=f'{username}-name', is_active=True)
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['username'] = username
        sess['role'] = role
    return uid


# --- 적재 규칙 -------------------------------------------------------------------


def test_same_content_reviewed_does_not_add_row(client, db, r2):
    """같은 내용을 두 번 봐도 행은 1개 — 횟수와 마지막 시각만 는다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)

    assert client.get(f'/s/{token}').status_code == 200
    assert client.get(f'/s/{token}').status_code == 200

    rows = _rows(row.id)
    assert len(rows) == 1
    assert rows[0].view_count == 2
    assert rows[0].last_viewed_at >= rows[0].first_viewed_at
    assert rows[0].source == hist.SOURCE_LIVE
    assert rows[0].kind == 'estimate'
    assert rows[0].order_id == order.id


def test_changed_amount_adds_row_and_each_row_keeps_its_own_money(client, db, r2):
    """금액을 고친 뒤 열면 새 행이 생기고, 각 행은 **그때 금액**을 그대로 들고 있다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)

    client.get(f'/s/{token}')
    _set_price(order, 700000)
    client.get(f'/s/{token}')

    rows = _rows(row.id)
    assert len(rows) == 2
    # 수량 2 — 첫 열람 1,000,000 / 두 번째 1,400,000
    assert rows[0].snapshot['items_subtotal'] == 1_000_000
    assert rows[1].snapshot['items_subtotal'] == 1_400_000
    assert rows[0].content_hash != rows[1].content_hash


def test_revert_to_previous_amount_keeps_three_rows(client, db, r2):
    """A→B→A 되돌림은 3행이어야 한다.

    ``(share_token_id, content_hash)`` 를 UNIQUE 로 묶거나 전체에서 같은 해시를 찾으면
    세 번째 상태가 첫 행에 흡수돼 "언제 무엇을 봤나"의 시간축이 무너진다.
    """
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)

    client.get(f'/s/{token}')          # A
    _set_price(order, 700000)
    client.get(f'/s/{token}')          # B
    _set_price(order, 500000)
    client.get(f'/s/{token}')          # A 로 복귀

    rows = _rows(row.id)
    assert len(rows) == 3
    assert [r.snapshot['items_subtotal'] for r in rows] == [1_000_000, 1_400_000, 1_000_000]
    assert rows[0].content_hash == rows[2].content_hash
    assert all(r.view_count == 1 for r in rows)


def test_drawing_share_records_nothing(client, db, r2):
    """음성 대조군 — 도면 링크에는 계약 내용이 없어 원장에 남지 않는다."""
    order = _mk_order()
    _add_drawing_attachment(order)
    row, token = _mk_share(order, kind='drawing')

    assert client.get(f'/s/{token}').status_code == 200
    assert _rows(row.id) == []


def test_bundle_share_records_history(client, db, r2):
    """bundle(도면+계약서) 링크도 계약서 쪽은 같은 규칙으로 남는다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order)
    row, token = _mk_share(order, kind='bundle')

    assert client.get(f'/s/{token}').status_code == 200
    rows = _rows(row.id)
    assert len(rows) == 1
    assert rows[0].kind == 'bundle'
    assert rows[0].snapshot['items_subtotal'] == 1_000_000


def test_stored_fallback_is_recorded_as_stored_source(client, db, r2, monkeypatch):
    """라이브 재구성이 실패해 발급 저장본이 뜨면 ``source='stored'`` 로 남는다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)

    def _boom(_order):
        raise osvc.SnapshotTooLargeError(osvc.SNAPSHOT_TOO_LARGE_MSG)

    monkeypatch.setattr(share_routes.share_service, 'build_estimate_snapshot', _boom)
    assert client.get(f'/s/{token}').status_code == 200

    rows = _rows(row.id)
    assert len(rows) == 1
    assert rows[0].source == hist.SOURCE_STORED


def test_history_write_failure_does_not_break_customer_page(client, db, r2, monkeypatch):
    """원장 적재가 터져도 고객은 계약서를 본다 — 그리고 열람 횟수는 그대로 는다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)

    def _boom(*args, **kwargs):
        raise RuntimeError('ledger down')

    monkeypatch.setattr(share_routes.share_history, 'record_snapshot_view', _boom)
    resp = client.get(f'/s/{token}')

    assert resp.status_code == 200
    assert '계약 내용' in resp.get_data(as_text=True)
    assert _rows(row.id) == []
    db_session.expire_all()
    assert db_session.get(OrderShareToken, row.id).view_count == 1


# --- 직원 조회 -------------------------------------------------------------------


def test_history_list_returns_summary_without_snapshot_body(client, db, r2):
    """목록은 금액 요약만 — 스냅샷 원문은 싣지 않는다(응답 비대 방지)."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)
    client.get(f'/s/{token}')

    _login(client, 'hist-staff1')
    body = client.get(f'/api/share/history/{row.id}').get_json()

    assert body['success'] is True
    items = body['data']['items']
    assert len(items) == 1
    assert items[0]['summary']['items_subtotal'] == 1_000_000
    assert items[0]['summary']['balance_amount'] == 900_000
    assert items[0]['source'] == 'live'
    assert 'snapshot' not in items[0]


def test_history_list_requires_login(client, db, r2):
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, _ = _mk_share(order)
    resp = client.get(f'/api/share/history/{row.id}')
    assert resp.status_code in (302, 401)


def test_history_list_rejects_viewer_role(client, db, r2):
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, _ = _mk_share(order)
    _login(client, 'hist-viewer', role='VIEWER')
    resp = client.get(f'/api/share/history/{row.id}')
    assert resp.status_code in (302, 403)


def test_history_page_renders_stored_amount_not_current(client, db, r2):
    """기록 화면은 **그때 금액**을 보여준다 — 지금 주문 값이 새어 들어오면 증거가 아니다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    row, token = _mk_share(order)
    client.get(f'/s/{token}')
    _set_price(order, 700000)

    snapshot_id = _rows(row.id)[0].id
    _login(client, 'hist-staff2')
    resp = client.get(f'/api/share/history/{snapshot_id}/page')
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert '1,000,000' in body        # 고객이 본 금액
    assert '1,400,000' not in body    # 현재 주문 금액은 안 샌다
    assert '고객이 본 계약서 기록' in body
    assert 'foms-share-hist' in body


def test_history_page_missing_row_is_404(client, db, r2):
    _login(client, 'hist-staff3')
    assert client.get('/api/share/history/99999999/page').status_code == 404


def test_history_page_writes_audit_row(client, db, r2):
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    order_id = order.id
    row, token = _mk_share(order)
    client.get(f'/s/{token}')
    snapshot_id = _rows(row.id)[0].id

    uid = _login(client, 'hist-staff4')
    client.get(f'/api/share/history/{snapshot_id}/page')

    db_session.expire_all()
    logs = (db_session.query(SecurityLog)
            .filter(SecurityLog.action == 'SHARE_HISTORY_VIEWED').all())
    assert len(logs) == 1
    assert logs[0].user_id == uid
    assert logs[0].target_id == order_id
    assert logs[0].detail['snapshot_id'] == snapshot_id


def test_share_history_action_has_business_label():
    """새 감사 action 은 라벨 등재 필수(미등재 시 감사 화면 가독성 게이트 red)."""
    from foms.services.audit_message_display import ACTION_LABELS
    assert ACTION_LABELS.get('SHARE_HISTORY_VIEWED')


# --- 순수 함수 -------------------------------------------------------------------


def test_content_hash_is_key_order_independent():
    """키 순서가 달라도 내용이 같으면 같은 해시 — 순서 흔들림이 가짜 행을 만들면 안 된다."""
    assert hist.content_hash({'a': 1, 'b': 2}) == hist.content_hash({'b': 2, 'a': 1})
    assert hist.content_hash({'a': 1}) != hist.content_hash({'a': 2})


def test_customer_page_has_no_history_banner(client, db, r2):
    """음성 대조군 — 고객 경로에는 직원용 배너 마크업이 존재하지 않는다."""
    order = _mk_order(structured_data=copy.deepcopy(_EST_SD))
    _, token = _mk_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'foms-share-hist' not in body
    assert '변경되면 이 화면에도 반영됩니다' in body
