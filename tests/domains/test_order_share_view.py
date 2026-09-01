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


def test_view_estimate_reflects_live_order_changes(client, db, r2):
    """발급 후 금액을 고치면 **같은 링크가 최신 계약 내용을 보여준다**(2026-09-01).

    2026-09-01 이전에는 발급 시점 스냅샷을 얼려 두어(D6) 금액을 고쳐도 최초 계약서가
    그대로 떴다. 사용자 결정으로 라이브 반영으로 뒤집혔다 — 유출 차단은 스냅샷
    화이트리스트를 **열람할 때마다 다시 태우는** 방식으로 유지한다.
    """
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
    # 수량 2 × 9,999,999 = 19,999,998 — 고친 값이 그대로 계산돼 나온다.
    assert '19,999,998' in body
    assert '1,000,000' not in body  # 옛 동결값은 더 이상 나오지 않는다
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
    assert 'css/orders/foms-share-contract.css?v=20260901a' in body
    assert 'js/orders/share-contract.js?v=20260831c' in body


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
    # 라이브 렌더라 판정 SSOT 는 저장 스냅샷이 아니라 **주문 structured_data** 다.
    from sqlalchemy.orm.attributes import flag_modified
    sd = _copy.deepcopy(order.structured_data)
    sd.setdefault('flags', {})['factory2'] = True
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db.commit()
    row, token = _mk_estimate_share(order)

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


def test_view_bundle_estimate_side_is_live(client, db, r2):
    """계약서 쪽 규칙은 단독 링크와 같다 — 발급 후 수정이 반영된다(2026-09-01)."""
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
    assert '19,999,998' in body and '1,000,000' not in body


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
    assert 'css/orders/foms-share-contract.css?v=20260901a' in body
    assert 'js/orders/share-contract.js?v=20260831c' in body
    assert 'window.print()' not in body


def test_view_bundle_without_stored_snapshot_still_renders_live(client, db, r2):
    """저장 스냅샷이 없어도 계약서를 라이브로 만들어 붙인다(2026-09-01 이전엔 503)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'plan-nosnap.png')
    row, token = osvc.create_share_token(db_session, order.id, 'bundle')
    db_session.commit()

    resp = client.get(f'/s/{token}')
    assert resp.status_code == 200
    assert '계약 내용' in resp.get_data(as_text=True)


def test_view_bundle_503_when_contract_data_unavailable(client, db, r2, monkeypatch):
    """계약서 데이터를 못 만들면 조용히 도면만 보여주지 않는다 — 503."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-nosnap.png')
    row, token = osvc.create_share_token(db_session, order.id, 'bundle')
    db_session.commit()
    monkeypatch.setattr(share_routes.share_service, 'build_estimate_snapshot',
                        lambda _order: {})

    assert client.get(f'/s/{token}').status_code == 503


def test_view_estimate_without_stored_snapshot_still_renders_live(client, db, r2):
    """저장 스냅샷이 없어도 라이브 재구성으로 뜬다(2026-09-01 이전엔 503 이었다)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    row, token = osvc.create_share_token(db_session, order.id, 'estimate')
    db_session.commit()
    resp = client.get(f'/s/{token}')
    assert resp.status_code == 200
    assert '계약 내용' in resp.get_data(as_text=True)


def test_view_estimate_503_when_live_and_stored_both_unavailable(client, db, r2, monkeypatch):
    """라이브도 저장본도 없으면 빈 계약서 대신 503 — 조용한 실패 금지."""
    order = _mk_order()
    row, token = osvc.create_share_token(db_session, order.id, 'estimate')
    db_session.commit()
    monkeypatch.setattr(share_routes.share_service, 'build_estimate_snapshot',
                        lambda _order: {})
    assert client.get(f'/s/{token}').status_code == 503


def test_view_estimate_falls_back_to_stored_when_live_too_large(client, db, r2, monkeypatch):
    """라이브 재구성이 항목 과다로 실패하면 발급본을 보여준다 — 빈 화면보다 낫다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    row, token = _mk_estimate_share(order)

    def _boom(_order):
        raise osvc.SnapshotTooLargeError(osvc.SNAPSHOT_TOO_LARGE_MSG)

    monkeypatch.setattr(share_routes.share_service, 'build_estimate_snapshot', _boom)
    resp = client.get(f'/s/{token}')
    assert resp.status_code == 200
    assert '1,000,000' in resp.get_data(as_text=True)  # 발급 시점 값


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


def test_contract_print_button_is_desktop_only():
    """인쇄 버튼은 좁은 화면에서 감춘다 — 폰에서는 '이미지로 저장'이 유일한 길이다."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    css = (root / 'static/css/orders/foms-share-contract.css').read_text(encoding='utf-8')
    block = css[css.index('인쇄 버튼은 PC 에서만'):]
    assert '@media (max-width: 599.98px)' in block
    assert '[data-share-print]' in block
    assert 'display: none' in block


# ---------------------------------------------------------------------------
# 합본 사진 GET /s/<token>/drawings-sheet.png (2026-08-31)
#
# 카톡 인앱 웹뷰는 <a download> 를 무시하고 window.print() 도 없다 — 폰에서 도면을
# 가져가는 유일하게 확실한 길이 "이미지를 길게 눌러 사진첩 저장"이라 여러 장을 한 장
# PNG 로 합친다. ZIP 라우트와 **같은 검증 체인·주문 격리·fail-closed** 규약이다.
# ---------------------------------------------------------------------------


def _png_bytes(width: int, height: int, color=(200, 30, 30)) -> bytes:
    """지정 크기의 진짜 PNG 바이트(합본 높이 계산을 결정적으로 만들기 위해)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (width, height), color).save(buf, format='PNG')
    return buf.getvalue()


class SheetR2Storage(FakeR2Storage):
    """합본 사진용 storage stub — key 마다 크기가 다른 **진짜 PNG** 를 돌려준다.

    ``FakeR2Storage`` 는 ``b'BYTES:<key>'`` 를 주므로 Pillow 가 열지 못한다.
    읽은 key 를 기록해 두면 주문 격리를 바이트가 아니라 **호출 자체로** 판정할 수 있다.
    """

    #: 파일명 꼬리 → (폭, 높이). 폭을 같게 두면 합본 높이 = 원본 높이합 + 여백이라
    #: "정말 이어붙였는가"를 축소 효과와 섞이지 않게 볼 수 있다.
    SIZES = {'sheet-a.png': (300, 200), 'sheet-b.png': (300, 150)}

    def __init__(self):
        self.read_keys = []

    def read_file_bytes(self, key: str) -> bytes:
        self.read_keys.append(key)
        width, height = self.SIZES.get(key.rsplit('/', 1)[-1], (120, 90))
        return _png_bytes(width, height)


@pytest.fixture
def sheet_r2(monkeypatch):
    stub = SheetR2Storage()
    monkeypatch.setattr(share_routes, 'get_storage', lambda: stub)
    return stub


def _sheet_image(resp):
    """응답 바이트를 PIL 로 연다 — Content-Type 헤더만 믿지 않는다."""
    from PIL import Image
    return Image.open(io.BytesIO(resp.data))


def test_sheet_is_png_taller_than_sum_of_pages(client, db, sheet_r2):
    """200 + image/png + 높이가 개별 장 높이 합보다 크다(정말 이어붙였는지)."""
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _add_drawing_attachment(order, 'sheet-b.png')
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings-sheet.png')

    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'image/png'
    assert resp.headers['Cache-Control'] == 'no-store'
    with _sheet_image(resp) as sheet:
        assert sheet.format == 'PNG'
        assert sheet.width == 300           # 가장 넓은 장 기준 통일(상한 미만)
        assert sheet.height > 200 + 150     # 개별 장 높이 합보다 크다
        assert sheet.height == 200 + 150 + share_routes._SHEET_GAP


def test_sheet_default_is_inline_not_attachment(client, db, sheet_r2):
    """기본은 inline — 길게 눌러 저장하려면 화면에 떠 있어야 한다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _add_drawing_attachment(order, 'sheet-b.png')
    _, token = _mk_share(order)

    disposition = client.get(f'/s/{token}/drawings-sheet.png').headers['Content-Disposition']
    assert disposition.startswith('inline;')
    assert 'attachment' not in disposition


def test_sheet_download_param_forces_attachment(client, db, sheet_r2):
    """``?download=1`` 이면 attachment — 되는 브라우저에서는 바로 파일로 저장된다."""
    order = _mk_order(customer_name='임/다:슬')
    _add_drawing_attachment(order, 'sheet-a.png')
    _add_drawing_attachment(order, 'sheet-b.png')
    _, token = _mk_share(order)

    disposition = client.get(
        f'/s/{token}/drawings-sheet.png?download=1').headers['Content-Disposition']
    assert disposition.startswith("attachment; filename*=UTF-8''")
    decoded = urllib.parse.unquote(disposition.split("UTF-8''", 1)[1])
    assert decoded == f'도면_임다슬_{order.id}.png'


def test_sheet_bundle_kind_allowed(client, db, sheet_r2):
    """bundle 링크도 도면을 들고 있으므로 합본이 된다."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'sheet-a.png')
    _, token = _mk_bundle_share(order)
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 200


def test_sheet_estimate_kind_404(client, db, sheet_r2):
    """계약서 링크에는 도면이 없다 — 존재 자체를 숨긴다(404)."""
    import copy as _copy
    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    _add_drawing_attachment(order, 'sheet-a.png')
    _, token = _mk_estimate_share(order)
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 404


def test_sheet_unknown_token_404(client, db, sheet_r2):
    resp = client.get('/s/definitely-not-a-token/drawings-sheet.png')
    assert resp.status_code == 404
    assert resp.headers['X-Robots-Tag'] == 'noindex, nofollow'


def test_sheet_revoked_410(client, db, sheet_r2):
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    row, token = _mk_share(order)
    osvc.revoke_token(row)
    db.commit()
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 410


def test_sheet_expired_410(client, db, sheet_r2):
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    row, token = _mk_share(order)
    row.expires_at = now_utc_naive() - datetime.timedelta(seconds=1)
    db.commit()
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 410


def test_sheet_deleted_order_404(client, db, sheet_r2):
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _, token = _mk_share(order)
    order.deleted_at = now_utc_naive()
    db.commit()
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 404


def test_sheet_no_images_404(client, db, sheet_r2):
    """PDF 만 있으면 합칠 게 없다 — 404(PDF→이미지 변환은 이번 범위 밖)."""
    order = _mk_order()
    _add_drawing_attachment(order, 'spec.pdf')
    _, token = _mk_share(order)

    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 404
    # 대조군: 같은 주문에 이미지가 하나라도 있으면 200 이다(404 가 다른 이유로 난 게 아님).
    _add_drawing_attachment(order, 'sheet-a.png')
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 200


def test_sheet_no_drawings_at_all_404(client, db, sheet_r2):
    order = _mk_order()
    _, token = _mk_share(order)
    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 404


def test_sheet_local_storage_fail_closed_503(client, db, monkeypatch):
    """로컬 스토리지면 fail-closed — 열람·ZIP 과 같은 규약."""
    monkeypatch.setattr(share_routes, 'get_storage', lambda: LocalStorage())
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _, token = _mk_share(order)
    resp = client.get(f'/s/{token}/drawings-sheet.png')
    assert resp.status_code == 503
    assert '일시적으로 열람할 수 없습니다' in resp.get_data(as_text=True)


def test_sheet_partial_read_failure_503(client, db, sheet_r2, monkeypatch):
    """한 장이라도 못 읽으면 503 — 일부만 담긴 사진을 내보내지 않는다(ZIP 과 같은 규칙)."""
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _add_drawing_attachment(order, 'sheet-b.png')
    _, token = _mk_share(order)

    original = sheet_r2.read_file_bytes

    def _one_fails(key):
        return None if key.endswith('sheet-b.png') else original(key)

    monkeypatch.setattr(sheet_r2, 'read_file_bytes', _one_fails)
    resp = client.get(f'/s/{token}/drawings-sheet.png')
    assert resp.status_code == 503
    assert '하나씩 저장' in resp.get_data(as_text=True)


def test_sheet_undecodable_bytes_503(client, db, sheet_r2, monkeypatch):
    """PNG 가 아닌 바이트가 오면 좁은 예외로 잡아 503 — 500 스택트레이스 금지."""
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _, token = _mk_share(order)

    monkeypatch.setattr(sheet_r2, 'read_file_bytes', lambda key: b'NOT-AN-IMAGE')
    resp = client.get(f'/s/{token}/drawings-sheet.png')
    assert resp.status_code == 503
    assert '하나씩 저장' in resp.get_data(as_text=True)


def test_sheet_isolates_other_order_keys(client, db, sheet_r2):
    """타 주문·비도면·traversal key 는 합본에 섞이지 않는다(allow-list 승계)."""
    order = _mk_order()
    other = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _add_drawing_attachment(other, 'sheet-b.png')
    order.structured_data = {
        'drawing_current_files': [
            {'key': f'orders/{other.id}/drawing/sheet-b.png', 'filename': 'sheet-b.png'},
            {'key': f'orders/{order.id}/attachments/measure.png', 'filename': 'measure.png'},
            {'key': f'orders/{order.id}/drawing/../../etc/passwd.png', 'filename': 'evil.png'},
        ],
    }
    db.commit()
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings-sheet.png')
    assert resp.status_code == 200
    # 내 도면 한 장만 읽었다 — 남의 key 는 storage 호출조차 없어야 한다.
    assert sheet_r2.read_keys == [f'orders/{order.id}/drawing/sheet-a.png']
    with _sheet_image(resp) as sheet:
        assert (sheet.width, sheet.height) == (300, 200)   # 여백 없음 = 한 장


def test_sheet_over_pixel_budget_shrinks_instead_of_refusing(client, db, sheet_r2,
                                                             monkeypatch):
    """총 픽셀 상한을 넘으면 거절하지 않고 줄여서 맞춘다 — 거절하면 받을 길이 없다."""
    monkeypatch.setattr(share_routes, '_SHEET_MAX_PIXELS', 20_000)
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _add_drawing_attachment(order, 'sheet-b.png')
    _, token = _mk_share(order)

    resp = client.get(f'/s/{token}/drawings-sheet.png')
    assert resp.status_code == 200
    with _sheet_image(resp) as sheet:
        assert sheet.width * sheet.height <= 20_000
        assert sheet.width < 300     # 정말 줄었다


def test_sheet_width_capped_at_max_width(client, db, sheet_r2, monkeypatch):
    """가장 넓은 장이 상한보다 넓으면 비율 유지로 줄인다."""
    monkeypatch.setattr(share_routes, '_SHEET_MAX_WIDTH', 150)
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    _, token = _mk_share(order)

    with _sheet_image(client.get(f'/s/{token}/drawings-sheet.png')) as sheet:
        assert sheet.width == 150
        assert sheet.height == 100   # 300x200 → 비율 유지


def test_sheet_records_file_download_audit_without_view_bump(client, db, sheet_r2):
    """감사 1건(FILE_DOWNLOAD 재사용) + 저장은 열람이 아니다(view_count 그대로)."""
    order = _mk_order()
    _add_drawing_attachment(order, 'sheet-a.png')
    row, token = _mk_share(order)

    assert client.get(f'/s/{token}/drawings-sheet.png').status_code == 200

    logs = db.query(AccessLog).filter(AccessLog.action == 'FILE_DOWNLOAD').all()
    assert len(logs) == 1
    assert f'share/{row.id}' in (logs[0].additional_data or '')
    assert token not in (logs[0].additional_data or '')

    db.expire_all()
    assert (db.get(OrderShareToken, row.id).view_count or 0) == 0


# --- 열람 페이지의 합본 버튼 · 카드 저장 아이콘 --------------------------------------


def test_view_has_sheet_button_and_card_save_icons(client, db, r2):
    """열람 페이지에 합본 버튼 마커·장수 라벨·카드 저장 아이콘 마커가 있다."""
    order = _mk_order()
    _add_drawing_attachment(order, 'plan-a.png')
    _add_drawing_attachment(order, 'plan-b.png')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-sheet' in body
    assert f'/s/{token}/drawings-sheet.png' in body
    assert '도면 전체 저장 (2장 · 사진 1장)' in body
    assert '이미지를 길게 눌러 사진첩에 저장하세요' in body
    # 카드 저장 아이콘 — 카드마다 하나, 카드 <button> 바깥 형제다(중첩 인터랙티브 금지).
    assert body.count('data-share-card-save') == 2
    assert body.count('foms-share-card-wrap') == 2
    # 중첩 인터랙티브 금지: 아이콘 <a> 앞의 마지막 button 태그는 **닫는** 쪽이어야 한다
    # (열린 <button> 안이면 </button> 보다 <button 이 뒤에 온다).
    for icon_at in [i for i in range(len(body))
                    if body.startswith('data-share-card-save', i)]:
        prefix = body[:icon_at]
        assert prefix.rindex('</button>') > prefix.rindex('<button'), (
            '카드 저장 아이콘이 <button> 안에 들어갔다 — HTML 이 깨진다')
    # ZIP 버튼은 마크업에 남아 있고(PC 용) 폰에서는 CSS 로만 감춘다
    assert 'foms-share-dl__primary--zip' in body


def test_view_pdf_only_keeps_zip_button_unhidden(client, db, r2):
    """이미지가 없으면 합본 버튼도 없고, ZIP 을 감추는 수식어도 붙지 않는다.

    폰에서 일괄 저장 수단이 통째로 사라지는 것을 막는 음성 대조군이다.
    """
    order = _mk_order()
    _add_drawing_attachment(order, 'spec-a.pdf')
    _add_drawing_attachment(order, 'spec-b.pdf')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-sheet' not in body
    assert 'data-share-zip' in body
    assert 'foms-share-dl__primary--zip' not in body


def test_view_single_image_shows_no_sheet_button(client, db, r2):
    """이미지가 1장이면 합칠 이유가 없다 — 단건 저장 버튼 그대로."""
    order = _mk_order()
    _add_drawing_attachment(order, 'only.png')
    _, token = _mk_share(order)

    body = client.get(f'/s/{token}').get_data(as_text=True)
    assert 'data-share-sheet' not in body
    assert 'data-share-download-single' in body


def test_erp_gallery_has_no_card_save_icon():
    """ERP 렌더(share_mode 아님)에는 카드 저장 아이콘이 없다 — 카드 마크업은 공용이다."""
    from flask import render_template_string
    import app as app_module

    tpl = "{% include 'drawing/partials/drawing_mobile_v2_gallery.html' %}"
    cards = [{'url': 'http://x/a.png', 'label': 'a.png',
              'download_url': 'http://x/a.png?dl=1'}]
    with app_module.app.test_request_context():
        erp = render_template_string(tpl, drawing_preview_cards=cards)
        shared = render_template_string(tpl, drawing_preview_cards=cards, share_mode=True)

    assert 'data-share-card-save' not in erp
    assert 'foms-share-card-wrap' not in erp
    # 음성 대조군: 같은 카드가 share_mode 에서는 아이콘을 낸다(선택자 오타로 통과 금지)
    assert 'data-share-card-save' in shared


def test_share_view_css_splits_sheet_and_zip_by_breakpoint():
    """모바일=합본 사진 / PC=ZIP 분기는 CSS breakpoint 로만 한다(UA 스니핑 금지)."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    css = (root / 'static/css/orders/foms-share-view.css').read_text(encoding='utf-8')
    common = (root / 'static/css/components/foms-drawing-mobile.css').read_text(encoding='utf-8')

    block = css[css.index('모바일 = 합본 사진'):]
    assert '@media (max-width: 599.98px)' in block
    assert '.foms-share-view .foms-share-dl__primary--zip' in block
    assert '@media (min-width: 600px)' in block
    assert '.foms-share-view .foms-share-dl__primary--sheet' in block
    # 카드 저장 아이콘은 공유 스코프에만 — 공용 갤러리 CSS 는 무변경이어야 한다
    assert '.foms-share-view .foms-share-card-save' in css
    assert 'foms-share-card-save' not in common
    assert 'foms-share-card-wrap' not in common


def test_sheet_pixel_budget_matches_ios_ceiling():
    """합본 픽셀 예산은 아이폰이 디코딩할 수 있는 크기여야 한다.

    이 사진은 폰에서 화면에 띄워 길게 눌러 저장하는 것이 본 경로다. 아이폰이 못 여는
    크기를 만들면 기능 자체가 무의미해진다 — 계약서 캡처가 쓰는 iOS 상한과 같은 값.
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    js = (root / 'static/js/orders/share-contract.js').read_text(encoding='utf-8')
    canvas_ceiling = int(re.search(r'MAX_CANVAS_PIXELS = (\d+)', js).group(1))
    assert share_routes._SHEET_MAX_PIXELS <= canvas_ceiling


def test_contract_number_stays_fixed_while_content_goes_live(client, db, r2):
    """내용은 최신으로 바뀌어도 **계약번호는 발급 시점에 고정**된다.

    번호가 날마다 달라지면 고객이 들고 있는 계약번호와 우리 화면이 어긋난다.
    """
    import copy as _copy
    import re
    from sqlalchemy.orm.attributes import flag_modified

    order = _mk_order(structured_data=_copy.deepcopy(_EST_SD))
    row, token = _mk_estimate_share(order)
    issued = (row.snapshot or {}).get('issued_date') or ''
    assert issued, '발급 시점 스냅샷에 발행일이 있어야 이 계약이 성립한다'

    before = client.get(f'/s/{token}').get_data(as_text=True)
    nums = re.findall(r'erp-est-num-value">([^<]+)<', before)
    assert nums, '계약번호 자리를 못 찾았다'
    fixed = nums[0].strip()
    assert fixed.startswith(issued.replace('-', ''))

    # 주문을 고쳐도(= 내용은 라이브로 바뀐다) 번호는 그대로여야 한다.
    sd = _copy.deepcopy(order.structured_data)
    sd['items'][0]['price'] = 7_777_777
    order.structured_data = sd
    flag_modified(order, 'structured_data')
    db.commit()

    after = client.get(f'/s/{token}').get_data(as_text=True)
    assert '15,555,554' in after, '내용은 최신이어야 한다(수량 2)'
    assert re.findall(r'erp-est-num-value">([^<]+)<', after)[0].strip() == fixed
