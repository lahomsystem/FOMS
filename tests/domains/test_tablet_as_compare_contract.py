"""태블릿 가로 AS 전/후 대조 표면 계약 (2026-07-12, P8 목업 이식).

정적 문자열 잠금 + 사진 전/후 매핑 기능 계약:

  - 신규 파샬 ``templates/cs/partials/tablet_as_compare_body.html`` 존재 + 대조 카드
    그리드 클래스 + rows 재소비 + order-id 소스 + 서비스 보강 필드(as_before/after_photos)
    + 이미지 뷰어 재사용 훅([data-foms-lightbox-gallery]/[data-foms-lightbox-src]) +
    목업 전/후 라벨(접수 시 / 조치 후) + 빈 상태 placeholder(사진 없음).
  - as_dashboard_body 가 erp_mobile_v2_enabled 게이트로 include(전례 패턴). 데스크톱
    테이블 마크업(side-sheet 소스 + T2 lock)은 무변경 보존(회귀 금지).
  - 신규 CSS ``foms-tablet-as-compare.css``: 코어 MQ + base-hide 가 opt-in(grid) 앞
    (순서 계약) + 데스크톱 테이블 은닉(!important) + 코호트/페이지 스코프 + landscape 전용
    (portrait 토큰 금지) + 터치 토큰(48px 행/44px 타깃) 구동.
  - 번들(foms-tablet-bundle.css)이 신규 파일을 @import(신규 ?v).
  - 서비스 ``batch_resolve_as_compare_photos``: created_at vs as_completed_date 로 전/후
    분리, 비이미지 제외, 미완료 건은 전량 before(after 빈 placeholder).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from unittest.mock import patch

from db import db_session
from models import Order, OrderAttachment

ROOT = Path(__file__).resolve().parents[2]

COMPARE_PARTIAL = "templates/cs/partials/tablet_as_compare_body.html"
COMPARE_CSS = "static/css/foundation/foms-tablet-as-compare.css"
AS_DASHBOARD_BODY = "templates/cs/partials/as_dashboard_body.html"
TABLET_BUNDLE_CSS = "static/css/foundation/foms-tablet-bundle.css"

CORE_MEDIA_QUERY = (
    "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- (1) 파샬 존재 + 대조 카드 구조 -----------------------------------------


def test_compare_partial_exists_with_card_grid_and_order_id() -> None:
    """파샬 존재 + 대조 섹션/카드 클래스 + rows 재소비 + 카드 order-id 소스."""
    body = _read(COMPARE_PARTIAL)
    assert "foms-as-compare" in body
    assert "foms-as-compare-card" in body
    assert "for r in rows" in body
    assert 'data-order-id="{{ r.id }}"' in body


def test_compare_partial_reuses_service_before_after_fields() -> None:
    """전/후 사진은 서비스 배치 보강 필드(as_before_photos / as_after_photos)를 소비 —
    템플릿에서 DB/N+1 없음."""
    body = _read(COMPARE_PARTIAL)
    assert "r.as_before_photos" in body
    assert "r.as_after_photos" in body


def test_compare_partial_reuses_global_image_viewer_via_lightbox_hooks() -> None:
    """이미지 탭 → 기존 GlobalImageViewer 재사용: lightbox.js 가 자동 마운트하는
    [data-foms-lightbox-gallery] 컨테이너 + [data-foms-lightbox-src] 이미지 훅(신규 뷰어/JS 없음)."""
    body = _read(COMPARE_PARTIAL)
    assert "data-foms-lightbox-gallery" in body
    assert "data-foms-lightbox-src=" in body


def test_compare_partial_has_before_after_labels_and_empty_placeholder() -> None:
    """목업 '접수 사진 → 조치 후' 대조 라벨 + 부재 시 placeholder(사진 없음)."""
    body = _read(COMPARE_PARTIAL)
    assert "접수 시" in body
    assert "조치 후" in body
    assert "사진 없음" in body


def test_compare_partial_no_inline_style_or_script() -> None:
    """인라인 스타일/스크립트 금지(프로젝트 규칙 + perf 가드)."""
    body = _read(COMPARE_PARTIAL)
    assert "<script" not in body
    assert "style=" not in body


# --- (2) as_dashboard_body 게이트 include + 데스크톱 테이블 보존 ------------


def test_as_dashboard_body_includes_compare_cohort_gated() -> None:
    """as_dashboard_body 가 대조 파샬을 erp_mobile_v2_enabled 게이트 안에서 include(전례)."""
    body = _norm(_read(AS_DASHBOARD_BODY))
    assert (
        "{% if erp_mobile_v2_enabled %}"
        "{% include 'cs/partials/tablet_as_compare_body.html' %}"
        "{% endif %}"
    ) in body


def test_as_dashboard_body_keeps_desktop_table_markup() -> None:
    """데스크톱 테이블 마크업(side-sheet 소스 + T2 lock)은 무변경 보존 — CSS 로만 은닉한다
    (마크업 제거 금지, 회귀 금지)."""
    body = _norm(_read(AS_DASHBOARD_BODY))
    assert 'class="erp-pro-table-wrapper d-none d-md-block"' in body
    assert '<tr data-order-id="{{ r.id }}">' in body


# --- (3) CSS: 코어 MQ + 순서 계약 + 테이블 은닉 + 스코프 + landscape 전용 ---


def test_compare_css_exists_exclusive_and_ordered() -> None:
    """CSS 존재 + 코어 MQ + base-hide(display:none) 가 opt-in(display:grid) 앞(순서 계약)
    + 데스크톱 테이블 은닉(!important) + 대조 표시가 동일 게이트 블록."""
    css = _norm(_read(COMPARE_CSS))
    assert CORE_MEDIA_QUERY in css
    base_idx = css.index(".foms-as-compare { display: none")
    show_idx = css.index(".erp-as-dashboard .foms-as-compare { display: grid")
    assert base_idx < show_idx, "base-hide 규칙이 opt-in(display:grid) 뒤에 있음(순서 계약 위반)"
    assert ".erp-as-dashboard .erp-pro-table-wrapper { display: none !important" in css


def test_compare_css_is_cohort_and_page_scoped() -> None:
    """모든 표시 규칙은 코호트 body class + AS 페이지 스코프 하위 → PC/폰/코호트 OFF 무영향."""
    css = _norm(_read(COMPARE_CSS))
    assert "body.erp-mobile-v2-layout .erp-as-dashboard" in css


def test_compare_css_is_landscape_only_no_portrait_token() -> None:
    """세로=모바일 셸 — 이 파일은 landscape 전용(portrait 토큰 금지, split-view 가드 정합)."""
    css = _read(COMPARE_CSS)
    assert "orientation: portrait" not in css


def test_compare_css_touch_targets_token_driven() -> None:
    """터치 보정: 카드 ≥48px(--foms-touch-target-min), 버튼/썸네일 타깃 44px
    (--foms-touch-target-comfortable) — foms 토큰 구동(하드코딩 회귀 차단)."""
    css = _read(COMPARE_CSS)
    assert "var(--foms-touch-target-min)" in css
    assert "var(--foms-touch-target-comfortable)" in css


def test_compare_css_hmi_color_only_on_dday_chip() -> None:
    """HMI 색 규율: 카드/메타는 무채색, 방문 D-day 칩만 임박/지남 시 유채색."""
    css = _norm(_read(COMPARE_CSS))
    assert ".foms-as-compare-dday.is-imminent" in css
    assert ".foms-as-compare-dday.is-overdue" in css


# --- (4) 번들 @import ------------------------------------------------------


def test_tablet_bundle_imports_compare_css() -> None:
    """번들이 신규 대조 CSS 를 @import(신규 ?v). 기존 @import 는 보존(추가만)."""
    bundle = _read(TABLET_BUNDLE_CSS)
    assert '@import url("foms-tablet-as-compare.css?v=' in bundle
    # 회귀 금지: 기존 융합 레이어 @import 보존.
    assert '@import url("foms-tablet-landscape.css?v=' in bundle
    assert '@import url("../components/foms-tablet-side-sheet.css?v=' in bundle


# --- (5) 서비스: 전/후 사진 매핑 기능 계약 ----------------------------------


def _make_as_order(*, status, completed=None, received=None):
    return Order(
        received_date="2026-01-01",
        customer_name="대조 고객",
        phone="010-0000-0000",
        address="Seoul",
        product="장",
        status=status,
        as_received_date=received,
        as_completed_date=completed,
        is_erp_order=True,
        structured_data={"shipment": {"as_content": "<div>x</div>"}},
    )


def _make_as_image(order_id, name, when, *, file_type="image", key=None):
    return OrderAttachment(
        order_id=order_id,
        filename=name,
        file_type=file_type,
        category="as",
        file_size=1,
        storage_key=key or ("as/" + name),
        created_at=when,
    )


def test_compare_photos_split_by_completion_date(app) -> None:
    """완료일 이전 이미지 = before(접수 시), 완료일 당일/이후 = after(조치 후). 비이미지 제외."""
    from foms.services.as_dashboard_display import batch_resolve_as_compare_photos

    today = datetime.date.today()
    order = _make_as_order(
        status="AS_COMPLETED",
        completed=today.strftime("%Y-%m-%d"),
        received=(today - datetime.timedelta(days=3)).strftime("%Y-%m-%d"),
    )
    db_session.add(order)
    db_session.commit()
    db_session.add_all(
        [
            _make_as_image(
                order.id,
                "before.jpg",
                datetime.datetime.combine(today - datetime.timedelta(days=2), datetime.time(9)),
            ),
            _make_as_image(
                order.id, "after.jpg", datetime.datetime.combine(today, datetime.time(15))
            ),
            _make_as_image(
                order.id,
                "note.pdf",
                datetime.datetime.combine(today, datetime.time(15)),
                file_type="document",
            ),
        ]
    )
    db_session.commit()

    with patch(
        "foms.services.as_dashboard_display.build_file_view_url",
        side_effect=lambda k: "/f/" + k,
    ):
        result = batch_resolve_as_compare_photos([order], db_session)

    bucket = result[order.id]
    assert [p["name"] for p in bucket["before"]] == ["before.jpg"]  # 완료일 이전
    assert [p["name"] for p in bucket["after"]] == ["after.jpg"]  # 완료일 당일 (pdf 제외)
    assert bucket["before"][0]["full"] == "/f/as/before.jpg"


def test_compare_photos_incomplete_all_before(app) -> None:
    """미완료 건(완료일 없음)은 전량 before, after 는 빈 리스트(→ placeholder)."""
    from foms.services.as_dashboard_display import batch_resolve_as_compare_photos

    today = datetime.date.today()
    order = _make_as_order(status="AS_RECEIVED", completed=None, received=today.strftime("%Y-%m-%d"))
    db_session.add(order)
    db_session.commit()
    db_session.add(
        _make_as_image(order.id, "p.jpg", datetime.datetime.combine(today, datetime.time(9)))
    )
    db_session.commit()

    with patch(
        "foms.services.as_dashboard_display.build_file_view_url",
        side_effect=lambda k: "/f/" + k,
    ):
        result = batch_resolve_as_compare_photos([order], db_session)

    bucket = result[order.id]
    assert len(bucket["before"]) == 1
    assert bucket["after"] == []
