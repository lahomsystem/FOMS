"""고객 공유 비로그인 열람 라우트 — 격리·상태·fail-closed·감사 테스트 (Phase A T2).

스펙 §3.2 검증 체인: 해시 → 회수 → 만료 → ``Order.active_filter()``(draft 포함).
storage 는 ``foms.api.share.get_storage`` 를 stub 으로 교체한다
(test_file_access_log.py 선례). SQLite 레인은 audit engine 이 메인 engine 이라
FILE_VIEW 행을 ``db_session`` 으로 바로 검증할 수 있다.

2026-08-31: 도면 일괄 저장 ``GET /s/<token>/drawings.zip`` 계약을 추가했다 —
열람과 **같은 검증 체인**(404/410/503)·주문 격리·용량 가드·감사 1건.
"""
import datetime
import io
import urllib.parse
import zipfile

import pytest

import foms.api.share as share_routes
from db import db_session
from foms.services import audit_writer
from foms.services import order_share as osvc
from foms.services.datetime_kst import now_utc_naive
from models import AccessLog, Order, OrderAttachment, OrderShareToken


class FakeR2Storage:
    """r2 storage stub — presigned URL 과 원본 바이트를 결정적으로 만든다."""

    storage_type = 'r2'

    def get_download_url(self, key: str, expires_in: int = 3600,
                         response_content_disposition=None) -> str:
        # attachment presign 은 &dl=1 마커로 구분 — 다운로드 섹션 어서션용.
        suffix = '&dl=1' if response_content_disposition else ''
        return f'https://r2.example/{key}?sig=1&exp={expires_in}{suffix}'

    def read_file_bytes(self, key: str) -> bytes:
        # 바이트에 key 를 심어 두면 zip 내용만 보고 주문 격리를 판정할 수 있다.
        return b'BYTES:' + key.encode('utf-8')


class LocalStorage(FakeR2Storage):
    storage_type = 'local'


class BrokenPresignStorage(FakeR2Storage):
    def get_download_url(self, key, expires_in=3600, response_content_disposition=None):
        return None


class BrokenReadStorage(FakeR2Storage):
    """presign 은 되는데 원본 바이트를 못 읽는 storage(ZIP 전멸 경로)."""

    def read_file_bytes(self, key):
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
    # 2장 이상이면 주 버튼(ZIP) + 접힌 개별 목록이 함께 나온다.
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    _, token = _mk_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert '도면 저장' in body
    assert '&amp;dl=1' in body or '&dl=1' in body
    assert '하나씩 저장' in body
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
    # 2026-08-31: 고객 화면 문구가 '견적서'→'계약서'로 바뀌었다(ERP 계약서 폼 이식).
    # 페이지 제목보다 문서 본문의 섹션 제목이 더 강한 계약이라 그쪽으로 옮긴다.
    assert '계약 내용' in body
    assert '임다슬' in body
    assert '1,000,000' in body      # 동결 시점 품목합
    assert '9,999,999' not in body  # 수정분 미반영
    assert '461-082990-04-011' in body  # 하우드 기본 계좌
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'


# --- 계약서 폼 계약 (2026-08-31 — ERP 견적서 탭 폼 이식) ---------------------------


def test_view_estimate_renders_erp_contract_form_sections(client, db, r2):
    """계약서가 ERP `erp-est-doc` 과 같은 구성으로 나온다(밋밋한 표 아님)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_estimate_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)

    assert 'data-share-contract-doc' in body      # 문서 루트(=PNG 캡처 대상)
    assert 'erp-est-topbar' in body               # 상단 컬러바
    assert '사업자 정보' in body
    assert '고객 정보' in body
    assert '계약번호' in body
    assert '계약 내용' in body
    assert '결제정보' in body
    assert '작성 일자' in body
    assert '법적 효력' in body
    assert 'company-stamp.png' in body            # 인감(기본 브랜드)


def test_view_estimate_contract_number_reuses_erp_formula(client, db, r2):
    """계약번호는 스냅샷 필드가 아니다 — ERP 와 같은 식(발행일_연락처숫자)으로 재현한다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    row, token = _mk_estimate_share(order)
    expected = row.snapshot['issued_date'].replace('-', '') + '_01024736730'
    assert expected in client.get(f'/s/{token}').get_data(as_text=True)


def test_view_estimate_has_copy_and_png_and_amount_and_asset_pins(client, db, r2):
    """고객 조작 표면 4종 — 계좌 복사·PNG 저장·품목 금액칸·신규 자산 ?v 핀."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_estimate_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)

    # (a) 계좌번호 복사 버튼 — 계좌마다 복사 대상 값이 붙는다.
    assert 'data-share-copy' in body
    assert 'data-share-copy-value="461-082990-04-011"' in body
    # (b) PNG 저장 버튼(window.print() 단독 의존 제거).
    assert 'data-share-contract-save' in body
    assert 'window.print()' not in body
    # (c) 품목표 금액 칸 — 좁은 화면에서 잘리지 않게 폭이 고정된 열.
    assert 'erp-est-col--amount' in body
    assert '금액 <span class="erp-est-th-vat">(VAT 포함)</span>' in body
    # (d) 신규 자산 ?v 핀(캐시 무효화 — 핀 없이 배포하면 옛 스타일이 남는다).
    assert 'css/orders/foms-share-contract.css?v=20260831b' in body
    assert 'js/orders/share-contract.js?v=20260831b' in body


def test_view_estimate_has_no_inline_style_or_script(client, db, r2):
    """인라인 style= / 인라인 script 블록 금지(프로젝트 규칙)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_estimate_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert ' style="' not in body
    assert '<script>' not in body


def test_view_estimate_factory2_uses_lahom_logo_and_stamp(client, db, r2):
    """2공장(라홈시스템) 스냅샷이면 로고·인감이 라홈 자산으로 갈린다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    row, token = _mk_estimate_share(order)
    # 스냅샷 상호를 2공장으로 바꾼다(발주사 판정은 상호 문자열이 SSOT).
    snap = _copy.deepcopy(row.snapshot)
    snap['company_info']['name'] = '라홈시스템'
    row.snapshot = snap
    db.commit()

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'lahom-company-stamp.png' in body
    assert 'lahom-logo-en.png' in body  # ERP 폼의 data-factory2-src 와 같은 파일
    assert 'images/company-stamp.png' not in body   # 기본(하우드) 인감은 안 나온다


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


def test_view_bundle_uses_same_contract_partial(client, db, r2):
    """계약서 본문은 사본이 아니라 같은 파셜 — 조작 표면과 자산 핀이 단독 페이지와 같다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-bundle-form.png')
    _, token = _mk_bundle_share(order)
    body = client.get(f'/s/{token}').get_data(as_text=True)

    assert 'data-share-contract-doc' in body
    assert 'data-share-copy-value="461-082990-04-011"' in body
    assert 'data-share-contract-save' in body
    assert 'erp-est-col--amount' in body
    assert 'css/orders/foms-share-contract.css?v=20260831b' in body
    assert 'js/orders/share-contract.js?v=20260831b' in body
    assert 'window.print()' not in body


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


# --- 도면 일괄 저장 ZIP (/s/<token>/drawings.zip, 2026-08-31) --------------------


def _zip_of(resp) -> zipfile.ZipFile:
    """응답 바이트가 진짜 zip 인지 열어서 확인한다(헤더만 믿지 않는다)."""
    return zipfile.ZipFile(io.BytesIO(resp.data))


def test_zip_returns_application_zip_with_every_drawing(client, db, r2):
    """drawing 토큰 → 200 application/zip, 항목 수가 도면 수와 같다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    order.structured_data = {
        'drawing_current_files': [
            {'key': f'orders/{order.id}/drawing_wizard/w1.png', 'filename': 'w1.png'},
        ],
    }
    db.commit()
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings.zip')

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/zip'
    with _zip_of(resp) as zf:
        assert sorted(zf.namelist()) == ['plan-a.png', 'plan-b.png', 'w1.png']
        assert zf.read('plan-a.png') == (
            b'BYTES:' + f'orders/{order.id}/drawing/plan-a.png'.encode('utf-8'))


def test_zip_bundle_kind_allowed(client, db, r2):
    """bundle 링크도 도면을 들고 있으므로 일괄 저장이 된다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-bundle.png')
    _, token = _mk_bundle_share(order)

    resp = client.get(f'/s/{token}/drawings.zip')
    assert resp.status_code == 200
    with _zip_of(resp) as zf:
        assert zf.namelist() == ['plan-bundle.png']


def test_zip_estimate_kind_404(client, db, r2):
    """계약서 링크에는 도면이 없다 — 존재 자체를 숨긴다(404)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-est.png')
    _, token = _mk_estimate_share(order)
    assert client.get(f'/s/{token}/drawings.zip').status_code == 404


def test_zip_unknown_token_404(client, db, r2):
    resp = client.get('/s/definitely-not-a-token/drawings.zip')
    assert resp.status_code == 404
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'


def test_zip_revoked_410(client, db, r2):
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-revoked.png')
    row, token = _mk_share(order)
    osvc.revoke_token(row)
    db.commit()
    assert client.get(f'/s/{token}/drawings.zip').status_code == 410


def test_zip_expired_410(client, db, r2):
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-expired.png')
    row, token = _mk_share(order)
    row.expires_at = now_utc_naive() - datetime.timedelta(seconds=1)
    db.commit()
    assert client.get(f'/s/{token}/drawings.zip').status_code == 410


def test_zip_deleted_order_404(client, db, r2):
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-deleted.png')
    _, token = _mk_share(order)
    order.deleted_at = now_utc_naive()
    db.commit()
    assert client.get(f'/s/{token}/drawings.zip').status_code == 404


def test_zip_no_drawings_404(client, db, r2):
    order = _mk_order()
    _, token = _mk_share(order)
    assert client.get(f'/s/{token}/drawings.zip').status_code == 404


def test_zip_local_storage_fail_closed_503(client, db, monkeypatch):
    monkeypatch.setattr(share_routes, 'get_storage', lambda: LocalStorage())
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-local.png')
    _, token = _mk_share(order)
    resp = client.get(f'/s/{token}/drawings.zip')
    assert resp.status_code == 503
    assert '일시적으로 열람할 수 없습니다' in resp.get_data(as_text=True)


def test_zip_all_reads_fail_503_not_empty_zip(client, db, monkeypatch):
    """한 장도 못 읽으면 빈 zip 을 내려보내지 않는다(조용한 실패 금지)."""
    monkeypatch.setattr(share_routes, 'get_storage', lambda: BrokenReadStorage())
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-unreadable.png')
    _, token = _mk_share(order)
    assert client.get(f'/s/{token}/drawings.zip').status_code == 503


def test_zip_over_size_limit_503(client, db, r2, monkeypatch):
    """총 바이트 상한을 넘으면 503 — 무한 메모리 적재 금지."""
    monkeypatch.setattr(share_routes, '_ZIP_MAX_TOTAL_BYTES', 4)
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-huge.png')
    _, token = _mk_share(order)
    resp = client.get(f'/s/{token}/drawings.zip')
    assert resp.status_code == 503
    assert '하나씩 저장' in resp.get_data(as_text=True)


def test_zip_isolates_other_order_keys(client, db, r2):
    """타 주문·비도면·traversal key 는 zip 안에 들어가지 않는다(allow-list)."""
    order = _mk_order()
    other = _mk_order()
    _add_drawing_attachment(order, 'mine.png')
    _add_drawing_attachment(other, 'leak.png')
    order.structured_data = {
        'drawing_current_files': [
            {'key': f'orders/{other.id}/drawing/leak.png', 'filename': 'leak.png'},
            {'key': f'orders/{order.id}/attachments/measure.png', 'filename': 'measure.png'},
            {'key': f'orders/{order.id}/drawing/../../etc/passwd', 'filename': 'evil'},
        ],
    }
    db.commit()
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings.zip')
    assert resp.status_code == 200
    with _zip_of(resp) as zf:
        assert zf.namelist() == ['mine.png']
    blob = resp.data
    assert f'orders/{other.id}/'.encode('utf-8') not in blob
    assert b'measure.png' not in blob
    assert b'passwd' not in blob


def test_zip_duplicate_entry_names_get_numbered(client, db, r2):
    """같은 파일명이 두 key 로 오면 두 번째는 '이름 (2).png' 로 담긴다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan.png')
    _add_drawing_attachment(order, 'rev2/plan.png')
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings.zip')
    with _zip_of(resp) as zf:
        assert sorted(zf.namelist()) == ['plan (2).png', 'plan.png']


def test_zip_entry_names_have_no_path_separators(client, db, r2):
    """항목명에 경로가 남으면 압축 해제 시 디렉토리가 생긴다 — basename 만."""
    order = _mk_order()
    att = _add_drawing_attachment(order, 'plan.png')
    att.filename = 'sub/dir/plan.png'
    db.commit()
    _, token = _mk_share(order)

    with _zip_of(client.get(f'/s/{token}/drawings.zip')) as zf:
        assert zf.namelist() == ['plan.png']


def test_zip_content_disposition_is_rfc5987_korean(client, db, r2):
    """한글 파일명은 RFC 5987 로 인코딩되고 고객명은 살균된다."""
    order = _mk_order(customer_name='임/다:슬')
    _add_drawing_attachment(order, 'plan-name.png')
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings.zip')
    disposition = resp.headers['Content-Disposition']
    assert disposition.startswith("attachment; filename*=UTF-8''")
    decoded = urllib.parse.unquote(disposition.split("UTF-8''", 1)[1])
    assert decoded == f'도면_임다슬_{order.id}.zip'


def test_zip_records_file_download_audit(client, db, r2):
    """감사 1건 — 액션은 라벨 맵에 이미 있는 FILE_DOWNLOAD, 토큰 원문은 안 남는다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-audit.png')
    row, token = _mk_share(order)

    assert client.get(f'/s/{token}/drawings.zip').status_code == 200

    logs = db.query(AccessLog).filter(AccessLog.action == 'FILE_DOWNLOAD').all()
    assert len(logs) == 1
    assert f'share/{row.id}' in (logs[0].additional_data or '')
    assert token not in (logs[0].additional_data or '')


def test_zip_does_not_bump_view_count(client, db, r2):
    """저장은 열람이 아니다 — 페이지 1회 방문이 view_count 2 로 부풀지 않게."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-count.png')
    row, token = _mk_share(order)

    assert client.get(f'/s/{token}/drawings.zip').status_code == 200

    db.expire_all()
    assert (db.get(OrderShareToken, row.id).view_count or 0) == 0


# --- 열람 페이지의 저장 섹션 UI (2026-08-31) -------------------------------------


def test_view_has_zip_button_marker(client, db, r2):
    """열람 페이지에 ZIP 주 버튼 마커와 장수 라벨이 있다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-zip' in body
    assert f'/s/{token}/drawings.zip' in body
    assert '도면 전체 저장 (2개 · ZIP)' in body


def test_view_single_drawing_shows_no_zip_button(client, db, r2):
    """1장짜리는 압축할 이유가 없다 — 그 파일 저장 버튼 하나만."""
    order = _mk_order()
    _add_drawing_attachment(order, 'only.png')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-download-single' in body
    assert 'data-share-zip' not in body
    assert '도면 저장 (1개)' in body


def test_view_bundle_has_zip_button(client, db, r2):
    """bundle 페이지에도 같은 저장 섹션이 나온다(사본 금지 — 파셜 공유)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    _, token = _mk_bundle_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-zip' in body
    assert f'/s/{token}/drawings.zip' in body


def test_view_kakao_inapp_note_only_for_kakaotalk_ua(client, db, r2):
    """인앱 안내는 UA 에 KAKAOTALK 이 있을 때만 — 판정은 서버에서 한다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    _, token = _mk_share(order)

    kakao_ua = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                'AppleWebKit/605.1.15 KAKAOTALK 10.4.5')
    with_kakao = client.get(f'/s/{token}', headers={'User-Agent': kakao_ua})
    assert '다른 브라우저로 열어 주세요' in with_kakao.get_data(as_text=True)

    plain = client.get(f'/s/{token}', headers={'User-Agent': 'Mozilla/5.0 (Macintosh)'})
    assert '다른 브라우저로 열어 주세요' not in plain.get_data(as_text=True)


# ---------------------------------------------------------------------------
# 자산 핀 · 인앱 저장 폴백 (2026-08-31)
#
# 공유 페이지 자산의 ``?v=`` 핀을 검사하는 테스트가 저장소에 없어서 핀이 페이지마다
# 갈라져도 CI 가 못 잡았다(실제로 estimate 페이지만 옛 핀으로 남아 있었다). SW
# staticCacheFirst 는 ``?v=`` 포함 URL 전체를 캐시 키로 쓰므로, 핀이 갈리면 그 페이지만
# 옛 CSS 를 계속 서빙한다. 소스 리터럴로 고정한다.
# ---------------------------------------------------------------------------

_SHARE_TEMPLATES = (
    'templates/orders/share_view.html',
    'templates/orders/share_estimate_view.html',
    'templates/orders/share_bundle_view.html',
)

#: 공유 페이지 3종이 공유하는 자산 → 모든 페이지에서 같은 핀이어야 한다.
_SHARED_PINNED_ASSETS = (
    'css/orders/foms-share-view.css',
    'css/orders/foms-share-contract.css',
    'js/orders/share-view.js',
    'js/orders/share-contract.js',
)


def _template_text(rel_path):
    """저장소 루트 기준 템플릿 원문."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    return (root / rel_path).read_text(encoding='utf-8')


def _pins_for(text, asset):
    """템플릿 원문에서 해당 자산 링크의 ``?v=`` 핀 값들."""
    import re
    pattern = re.escape(asset) + r"'\s*\)\s*\}\}\?v=([0-9a-z]+)"
    return re.findall(pattern, text)


def test_share_pages_pin_shared_assets_to_same_version():
    """같은 자산은 공유 페이지 3종에서 같은 ``?v=`` 핀이어야 한다."""
    texts = {path: _template_text(path) for path in _SHARE_TEMPLATES}
    for asset in _SHARED_PINNED_ASSETS:
        found = {}
        for path, text in texts.items():
            pins = _pins_for(text, asset)
            assert len(pins) <= 1, f'{path} 가 {asset} 를 {len(pins)}번 싣는다'
            if pins:
                found[path] = pins[0]
        assert found, f'{asset} 를 싣는 공유 페이지가 하나도 없다'
        assert len(set(found.values())) == 1, (
            f'{asset} 핀 드리프트: {found} — SW 캐시가 페이지별로 갈린다'
        )


def test_contract_save_prefers_dataurl_not_blob_download():
    """WKWebView(iOS·카톡 인앱)는 blob: 을 <a download> href 로 못 쓴다.

    toDataURL 이 1순위여야 원래 신고된 "저장 버튼 무반응"이 재발하지 않는다.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    js = (root / 'static/js/orders/share-contract.js').read_text(encoding='utf-8')
    body = js[js.index('function canvasToUrl'):]
    body = body[:body.index('function isInAppBrowser')]
    assert body.index('toDataURL') < body.index('toBlob'), (
        'canvasToUrl 이 toBlob 을 먼저 시도한다 — iOS 인앱에서 저장이 무반응이 된다'
    )


def test_view_estimate_has_inapp_save_fallback(client, db, r2):
    """다운로드가 막히는 인앱 브라우저용 '길게 눌러 저장' 폴백 자리가 있다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _, token = _mk_estimate_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-contract-fallback' in body
    assert 'data-share-contract-fallback-img' in body
    assert '길게 눌러' in body


def test_view_estimate_hides_discount_line(client, db, r2):
    """할인은 출고가에 이미 흡수돼 있다 — 별도 줄을 두면 두 번 빼는 것으로 읽힌다.

    ERP 읽기전용 요약(estimate-preview.js)과 같은 규칙.
    """
    import copy as _copy
    sd = _copy.deepcopy(_EST_SD)
    sd.setdefault('payment', {})['discount'] = 50000
    order = _mk_order(structured_data=sd)
    row, token = _mk_estimate_share(order)

    # 대조군: 스냅샷에 할인이 실제로 들어 있어야 '숨긴다'는 주장이 의미를 갖는다.
    assert (row.snapshot or {}).get('discount_amount') == 50000

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'erp-est-sum-discount' not in body
    assert '할인' not in body


def test_zip_partial_read_failure_503(client, db, r2, monkeypatch):
    """한 장이라도 못 읽으면 불완전한 zip 대신 503 — 고객이 '전부 받았다'고 믿으면 안 된다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    _, token = _mk_share(order)

    original = r2.read_file_bytes

    def _one_fails(key):
        return None if key.endswith('plan-b.png') else original(key)

    monkeypatch.setattr(r2, 'read_file_bytes', _one_fails)
    resp = client.get(f'/s/{token}/drawings.zip')
    assert resp.status_code == 503
    assert '하나씩 저장' in resp.get_data(as_text=True)


def test_contract_export_uses_desktop_clone_not_screen_node(client, db, r2):
    """저장물은 폰 레이아웃이 아니라 ERP 계약서와 같은 700px 문서여야 한다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    js = (root / 'static/js/orders/share-contract.js').read_text(encoding='utf-8')
    assert 'EXPORT_WIDTH = 700' in js
    assert 'buildExportClone' in js
    # html2canvas 는 별도 iframe 에 렌더하므로 windowWidth 를 줘야 미디어쿼리가 PC 로 평가된다.
    assert 'windowWidth: EXPORT_WIDTH' in js
    body = js[js.index('function savePng'):]
    assert 'html2canvas(clone' in body, 'savePng 이 화면 노드를 그대로 캡처한다'

    css = (root / 'static/css/orders/foms-share-contract.css').read_text(encoding='utf-8')
    assert '.foms-share-contract__export-clone' in css


def test_estimate_factory2_logo_matches_erp_form(client, db, r2):
    """2공장 로고 파일이 ERP 계약서 폼(data-factory2-src)과 같아야 한다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    erp = (root / 'templates/orders/partials/estimate_pane.html').read_text(encoding='utf-8')
    share = (root / 'templates/orders/partials/share_estimate_body.html').read_text(encoding='utf-8')
    assert "data-factory2-src=\"{{ url_for('static', filename='images/lahom-logo-en.png') }}\"" in erp
    assert 'images/lahom-logo-en.png' in share
    assert 'images/lahom-logo.png' not in share


def test_share_drawing_page_uses_customer_wording_not_erp(client, db, r2):
    """고객 화면에 ERP 내부 낱말('승인'·'16:9'·'lightbox')이 새면 안 된다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert '이미지를 누르면 크게 볼 수 있습니다' in body
    assert '좌우 스와이프로 승인' not in body
    assert 'lightbox)' not in body
    assert '>16:9<' not in body


def test_share_drawing_page_has_no_preview_heading(client, db, r2):
    """고객 화면에는 '도면 미리보기' 머리줄을 두지 않는다 — 머리글이 이미 말한다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert '도면 미리보기' not in body
    # 안내는 페이지 머리글 한 곳에서만 (갤러리 파셜이 같은 말을 반복하지 않는다)
    assert body.count('이미지를 누르면 크게 볼 수 있습니다') == 1


def test_share_gallery_sizing_is_scoped_to_share_page():
    """미리보기 크기 재정의는 공유 페이지에만 걸어야 한다 — 공용 CSS 를 고치면 ERP 큐가 같이 커진다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    share = (root / 'static/css/orders/foms-share-view.css').read_text(encoding='utf-8')
    common = (root / 'static/css/components/foms-drawing-mobile.css').read_text(encoding='utf-8')

    assert '.foms-share-view .foms-drawing-card-grid' in share
    assert 'minmax(min(100%, 300px), 1fr)' in share
    # 공용 파일의 ERP 기준 하한은 그대로여야 한다
    assert 'minmax(140px, 1fr)' in common
    # 저장 버튼은 터치 하한을 지키되 화면 폭을 다 먹지 않는다
    assert 'max-width: 340px' in share


def test_erp_gallery_keeps_its_own_wording():
    """ERP 화면(share_mode 아님)은 머리줄·안내 문구를 그대로 유지한다."""
    from flask import render_template_string
    import app as app_module

    tpl = "{% include 'drawing/partials/drawing_mobile_v2_gallery.html' %}"
    with app_module.app.test_request_context():
        html = render_template_string(
            tpl, drawing_preview_cards=[{'url': 'http://x/a.png', 'label': 'a.png'}])
    assert '도면 미리보기' in html
    assert '좌우 스와이프로 승인' in html
    assert '16:9' in html
