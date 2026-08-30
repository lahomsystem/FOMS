"""고객 공유 비로그인 열람 라우트 — 격리·상태·fail-closed·감사 테스트 (Phase A T2).

스펙 §3.2 검증 체인: 해시 → 회수 → 만료 → ``Order.active_filter()``(draft 포함).
storage 는 ``foms.api.share.get_storage`` 를 stub 으로 교체한다
(test_file_access_log.py 선례). SQLite 레인은 audit engine 이 메인 engine 이라
FILE_VIEW 행을 ``db_session`` 으로 바로 검증할 수 있다.
"""
import datetime

import pytest

import foms.api.share as share_routes
from db import db_session
from foms.services import audit_writer
from foms.services import order_share as osvc
from foms.services.datetime_kst import now_utc_naive
from models import AccessLog, Order, OrderAttachment, OrderShareToken


class FakeR2Storage:
    """r2 storage stub — presigned URL 을 결정적으로 만든다."""

    storage_type = 'r2'

    def get_download_url(self, key: str, expires_in: int = 3600,
                         response_content_disposition=None) -> str:
        # attachment presign 은 &dl=1 마커로 구분 — 다운로드 섹션 어서션용.
        suffix = '&dl=1' if response_content_disposition else ''
        return f'https://r2.example/{key}?sig=1&exp={expires_in}{suffix}'


class LocalStorage(FakeR2Storage):
    storage_type = 'local'


class BrokenPresignStorage(FakeR2Storage):
    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return None


@pytest.fixture(autouse=True)
def _audit_isolation():
    audit_writer.reset_dedupe_cache()
    yield
    audit_writer.reset_dedupe_cache()


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
        received_date=datetime.date(2026, 8, 11),
        customer_name='임다슬',
        phone='010-2473-6730',
        address='Seoul',
        product='가구',
        status='ERPORDER',
        is_erp_order=True,
        structured_data=structured_data or {},
    )
    fields.update(kwargs)
    order = Order(**fields)
    db_session.add(order)
    db_session.commit()
    return order


def _mk_share(order, kind='drawing') -> tuple[OrderShareToken, str]:
    row, token = osvc.create_share_token(db_session, order.id, kind)
    db_session.commit()
    return row, token


def _add_drawing_attachment(order, key='x.png') -> OrderAttachment:
    att = OrderAttachment(
        order_id=order.id,
        filename=key.rsplit('/', 1)[-1],
        file_type='image',
        category='drawing',
        storage_key=f'orders/{order.id}/drawing/{key}',
    )
    db_session.add(att)
    db_session.commit()
    return att


# --- 열람 성공 경로 -------------------------------------------------------------


def test_view_renders_attachment_and_sd_keys_with_isolation(client, db, r2):
    order = _mk_order()
    other = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    order.structured_data = {
        'drawing_current_files': [
            {'key': f'orders/{order.id}/drawing_wizard/w1.png', 'filename': 'w1.png'},
            # 타 주문 key·비도면 key·traversal — 전부 차단돼야 한다(allow-list).
            {'key': f'orders/{other.id}/drawing/leak.png', 'filename': 'leak.png'},
            {'key': f'orders/{order.id}/attachments/measure.png', 'filename': 'measure.png'},
            {'key': f'orders/{order.id}/drawing/../../etc/passwd', 'filename': 'evil'},
        ],
    }
    db.commit()
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}')
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert f'orders/{order.id}/drawing/plan-a.png' in body
    assert f'orders/{order.id}/drawing_wizard/w1.png' in body
    assert 'leak.png' not in body
    assert 'measure.png' not in body
    assert 'passwd' not in body


def test_view_renders_download_section_with_attachment_presign(client, db, r2):
    # 고객 다운로드 요구 — 모든 파일에 attachment presign(&dl=1) 링크가 나와야 한다.
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _, token = _mk_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert '파일 다운로드' in body
    assert '&amp;dl=1' in body or '&dl=1' in body
    assert 'plan-a.png 내려받기' in body


def test_view_estimate_has_print_button(client, db, r2):
    # 견적서(계약서) 저장·인쇄 버튼 — 다운로드 요구의 estimate 측 표면.
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_estimate_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-print' in body


def test_view_sets_noindex_and_no_referrer_headers(client, db, r2):
    order = _mk_order()
    _add_drawing_attachment(order)
    _, token = _mk_share(order)
    resp = client.get(f'/s/{token}')
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'
    assert resp.headers['Referrer-Policy'] == 'no-referrer'


def test_view_records_view_count_and_file_view_audit(client, db, r2):
    order = _mk_order()
    _add_drawing_attachment(order)
    row, token = _mk_share(order)

    resp = client.get(f'/s/{token}')
    assert resp.status_code == 200

    db.expire_all()
    fresh = db.get(OrderShareToken, row.id)
    assert fresh.view_count == 1
    assert fresh.last_viewed_at is not None

    logs = db.query(AccessLog).filter(AccessLog.action == 'FILE_VIEW').all()
    assert len(logs) == 1
    assert f'share/{row.id}' in (logs[0].additional_data or '')
    # 토큰 원문은 어떤 감사 컬럼에도 남지 않는다.
    assert token not in (logs[0].additional_data or '')


def test_view_empty_drawing_renders_empty_state(client, db, r2):
    order = _mk_order()
    _, token = _mk_share(order)
    resp = client.get(f'/s/{token}')
    assert resp.status_code == 200
    assert '등록된 도면이 없습니다' in resp.get_data(as_text=True)


# --- 검증 체인 실패 경로 ---------------------------------------------------------


def test_view_unknown_token_404_with_headers(client, db, r2):
    resp = client.get('/s/definitely-not-a-token')
    assert resp.status_code == 404
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'


def test_view_expired_410(client, db, r2):
    order = _mk_order()
    _add_drawing_attachment(order)
    row, token = _mk_share(order)
    row.expires_at = now_utc_naive() - datetime.timedelta(seconds=1)
    db.commit()
    assert client.get(f'/s/{token}').status_code == 410


def test_view_revoked_410(client, db, r2):
    order = _mk_order()
    row, token = _mk_share(order)
    osvc.revoke_token(row)
    db.commit()
    assert client.get(f'/s/{token}').status_code == 410


def test_view_draft_order_404(client, db, r2):
    order = _mk_order(structured_data={'meta': {'draft': True}})
    _, token = _mk_share(order)
    assert client.get(f'/s/{token}').status_code == 404


def test_view_deleted_order_404(client, db, r2):
    order = _mk_order()
    _, token = _mk_share(order)
    order.deleted_at = now_utc_naive()
    db.commit()
    assert client.get(f'/s/{token}').status_code == 404


# --- estimate 열람 (T7) ----------------------------------------------------------


def _mk_estimate_share(order) -> tuple[OrderShareToken, str]:
    from foms.services.order_share import build_estimate_snapshot
    snap = build_estimate_snapshot(order)
    row, token = osvc.create_share_token(db_session, order.id, 'estimate', snapshot=snap)
    db_session.commit()
    return row, token


_EST_SD = {
    'parties': {'customer': {'name': '임다슬', 'phone': '010-2473-6730'},
                'manager': {'name': '김담당'}},
    'site': {'address_full': '서울시 강남구'},
    'items': [{'product_name': '무몰딩 여닫이', 'quantity': 2, 'price': 500000,
               'color': '화이트'}],
    'payment': {'deposit': 100000},
}


def test_view_estimate_renders_snapshot_only(client, db, r2):
    """스냅샷만 렌더 — 발급 후 주문 수정은 열람에 반영되지 않는다(D6)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_estimate_share(order)

    # 발급 후 가격 변경
    from sqlalchemy.orm.attributes import flag_modified
    sd = _copy.deepcopy(order.structured_data)
    sd['items'][0]['price'] = 9_999_999
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db.commit()

    resp = client.get(f'/s/{token}')
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert '견적서' in body
    assert '임다슬' in body
    assert '1,000,000' in body      # 동결 시점 품목합
    assert '9,999,999' not in body  # 수정분 미반영
    assert '461-082990-04-011' in body  # 하우드 기본 계좌
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'


# --- bundle 열람 (도면 + 계약서 한 링크, 2026-08-25) ------------------------------


def _mk_bundle_share(order) -> tuple[OrderShareToken, str]:
    from foms.services.order_share import build_estimate_snapshot
    snap = build_estimate_snapshot(order)
    row, token = osvc.create_share_token(db_session, order.id, 'bundle', snapshot=snap)
    db_session.commit()
    return row, token


def test_view_bundle_renders_drawing_and_estimate_together(client, db, r2):
    """링크 하나에 두 문서 — 도면 파일과 동결 계약서가 같은 페이지에 나온다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-bundle.png')
    _, token = _mk_bundle_share(order)

    resp = client.get(f'/s/{token}')
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert f'orders/{order.id}/drawing/plan-bundle.png' in body   # 도면 섹션
    assert '1,000,000' in body                                    # 계약서 섹션(동결 품목합)
    assert '임다슬' in body
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'


def test_view_bundle_estimate_side_is_frozen(client, db, r2):
    """계약서 쪽 동결 규칙은 단독 링크와 같다 — 발급 후 수정은 반영되지 않는다(D6)."""
    import copy as _copy
    from sqlalchemy.orm.attributes import flag_modified

    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-frozen.png')
    _, token = _mk_bundle_share(order)

    sd = _copy.deepcopy(order.structured_data)
    sd['items'][0]['price'] = 9_999_999
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db.commit()

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert '1,000,000' in body and '9,999,999' not in body


def test_view_bundle_without_drawing_still_shows_estimate(client, db, r2):
    """도면이 아직 없어도 계약서는 보여준다(빈 도면 안내 + 계약서 본문)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_bundle_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert '아직 등록된 도면이 없습니다' in body
    assert '1,000,000' in body


def test_view_bundle_missing_snapshot_503(client, db, r2):
    """스냅샷 없는 bundle 링크는 존재하면 안 되는 상태 — 조용히 도면만 보여주지 않는다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-nosnap.png')
    row, token = osvc.create_share_token(db_session, order.id, 'bundle')
    db_session.commit()

    assert client.get(f'/s/{token}').status_code == 503


def test_view_estimate_missing_snapshot_503(client, db, r2):
    order = _mk_order()
    row, token = osvc.create_share_token(db_session, order.id, 'estimate')
    db_session.commit()
    assert client.get(f'/s/{token}').status_code == 503


def test_view_estimate_revoked_410(client, db, r2):
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    row, token = _mk_estimate_share(order)
    osvc.revoke_token(row)
    db.commit()
    assert client.get(f'/s/{token}').status_code == 410


# --- fail-closed ---------------------------------------------------------------


def test_view_local_storage_fail_closed_503(client, db, monkeypatch):
    monkeypatch.setattr(share_routes, 'get_storage', lambda: LocalStorage())
    order = _mk_order()
    _add_drawing_attachment(order)
    _, token = _mk_share(order)
    resp = client.get(f'/s/{token}')
    assert resp.status_code == 503
    assert '일시적으로 열람할 수 없습니다' in resp.get_data(as_text=True)


def test_view_all_presign_failures_503_not_blank(client, db, monkeypatch):
    monkeypatch.setattr(share_routes, 'get_storage', lambda: BrokenPresignStorage())
    order = _mk_order()
    _add_drawing_attachment(order)
    _, token = _mk_share(order)
    assert client.get(f'/s/{token}').status_code == 503
