"""T2/W9 tablet-landscape touch-correction layer contracts (2026-07-11).

Static file contracts for the W9 work
(docs/plans/2026-07-11-tablet-t2-dashboards-spec.md):

  - The new ``static/css/foundation/foms-tablet-landscape.css`` exists and carries
    the exact tablet-landscape media query + the touch-correction rules (row ≥48px,
    target ≥44px, filter input 16px, checkbox 24px, pagination 44px, sticky header).
  - ``foms-mobile-surfaces.css`` @imports BOTH the W9 landscape file and the W10
    side-sheet file (import reserved even though W10 may not exist yet — CSS @import
    is fail-soft).
  - The row-48px / target-44px geometry is token-driven (``--foms-touch-target-min``
    for the 48px row, ``--foms-touch-target-comfortable: 44px`` for the target) so a
    future edit that hard-codes or regresses the touch metrics fails fast here.

These lock strings the broader mockup-parity / P2 gate suites do not pin.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LANDSCAPE_CSS = "static/css/foundation/foms-tablet-landscape.css"
MOBILE_SURFACES_CSS = "static/css/foundation/foms-mobile-surfaces.css"

# The single core media condition (Spec W9 적용 조건): true touch tablet landscape.
CORE_MEDIA_QUERY = (
    "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    """Return the UTF-8 text of a repo-relative file."""
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Collapse every whitespace run to a single space so multi-line CSS selector
    chains can be matched as a stable one-line substring."""
    return re.sub(r"\s+", " ", text)


# --- (1) new CSS exists + core query / correction rules --------------------


def test_landscape_css_exists_with_core_media_query() -> None:
    """The W9 file exists and carries the exact tablet-landscape media query."""
    css = _read(LANDSCAPE_CSS)
    assert CORE_MEDIA_QUERY in css, "missing core tablet-landscape @media query"


def test_landscape_css_has_no_portrait_token() -> None:
    """This file is landscape-only; it must never emit a raw portrait token
    (세로=모바일 셸, foms-split-view.css portrait 금지 가드와 정합)."""
    css = _read(LANDSCAPE_CSS)
    assert "orientation: portrait" not in css


def test_landscape_css_is_cohort_scoped() -> None:
    """Every correction rule is scoped under the cohort gate so PC / phone /
    cohort-OFF are unaffected — the file must not select a legacy class at top level."""
    css = _read(LANDSCAPE_CSS)
    # The correction selectors all live under the cohort body class.
    assert "body.erp-mobile-v2-layout" in css


def test_landscape_css_carries_touch_correction_rules() -> None:
    """The six touch corrections from the mockup v8 spec are all present."""
    css = _norm(_read(LANDSCAPE_CSS))
    # 2) button / link / nav / open-icon ≥44px targets.
    for sel in (".erp-pro-btn", ".erp-pro-nav-item", ".erp-open-btn-icon"):
        assert sel in css, f"missing touch-target selector: {sel}"
    # 3) filter inputs: 44px + 16px (iOS zoom guard) via the base font token.
    assert ".erp-dashboard-filters .form-control" in css
    assert ".erp-dashboard-filters .form-select" in css
    assert "font-size: var(--foms-font-size-base)" in css
    # 4) checkbox 24px always (overrides inline 1.1em → !important required).
    assert ".form-check-input" in css
    assert "width: 24px !important" in css
    assert "height: 24px !important" in css
    # 5) pagination 44px.
    assert ".pagination .page-link" in css
    # 6) sticky header preserved.
    assert "#erp-grid thead th" in css
    assert "position: sticky" in css


# --- (2) @import wiring (W9 landscape + W10 side-sheet) --------------------


def test_mobile_surfaces_imports_landscape_and_side_sheet() -> None:
    """foms-mobile-surfaces.css @imports BOTH the W9 landscape file and the W10
    side-sheet file. W10 may not exist yet — the import is reserved (fail-soft)."""
    css = _read(MOBILE_SURFACES_CSS)
    assert '@import url("../foundation/foms-tablet-landscape.css?v=' in css, (
        "missing W9 landscape @import"
    )
    assert '@import url("../components/foms-tablet-side-sheet.css?v=' in css, (
        "missing W10 side-sheet @import (reserved line)"
    )


def test_mobile_surfaces_parent_cachebuster_bumped() -> None:
    """The mobile-surfaces content changed (W11 bumped the landscape @import a→b) so its
    layout_head ?v must be bumped past the prior baseline (T0 교훈: 자식 범프=부모 내용
    변경=부모도 범프). W9=ae → W11=af."""
    layout_head = _read("templates/partials/shared/layout_head.html")
    assert "foms-mobile-surfaces.css') }}?v=20260711af" in layout_head
    assert "foms-mobile-surfaces.css') }}?v=20260711ae" not in layout_head


# --- (3) row 48px / target 44px token locks --------------------------------


def test_row_height_uses_48px_min_touch_token() -> None:
    """The grid data row height is driven by --foms-touch-target-min (48px), applied
    only to the main data row (not the collapse detail row)."""
    css = _norm(_read(LANDSCAPE_CSS))
    assert "tr.erp-main-row { height: var(--foms-touch-target-min)" in css


def test_target_size_uses_44px_comfortable_token() -> None:
    """The ≥44px touch target is a foms-namespaced token defined = 44px and consumed
    via var(), not hard-coded per rule."""
    css = _read(LANDSCAPE_CSS)
    assert "--foms-touch-target-comfortable: 44px" in css
    assert "var(--foms-touch-target-comfortable)" in css


# =====================================================================
# W10 — 태블릿 사이드 시트 컴포넌트 계약
# (docs/plans/2026-07-11-tablet-t2-dashboards-spec.md, 실행 단위 W10)
# 행 탭 → 우측 슬라이드 시트에 기존 fragment 상세/edit 로드. 신규 API 없음.
# W9 섹션과 같은 파일 공존 — 섹션 분리로 병합(spec: 충돌 시 클래스/섹션 분리).
# =====================================================================

SIDE_SHEET_JS = "static/js/foms/tablet-side-sheet.js"
SIDE_SHEET_CSS = "static/css/components/foms-tablet-side-sheet.css"
LAYOUT_SCRIPTS = "templates/partials/shared/layout_scripts.html"

# 3 legacy 그리드 partial — 행 order-id 소스 계약(세 그리드 동일 마크업 공유).
_LEGACY_GRID_PARTIALS = (
    "templates/orders/partials/dashboard_grid.html",
    "templates/construction/partials/filters_grid.html",
    "templates/production/partials/filters_grid.html",
)


# --- (W10-1) JS: 존재 + idempotent 가드 + 코호트 MQ + fragment URL 패턴 -----


def test_side_sheet_js_exists_with_idempotent_guard() -> None:
    """The side-sheet JS carries the window.__FOMS_TABLET_SHEET_BOUND singleton guard
    (perf G4 — no duplicate global listeners on fragment replay / reload)."""
    js = _read(SIDE_SHEET_JS)
    assert "window.__FOMS_TABLET_SHEET_BOUND" in js


def test_side_sheet_js_activates_only_in_tablet_landscape_cohort() -> None:
    """Activation is gated on the exact tablet-landscape cohort MQ; off-cohort (phone /
    portrait / desktop) it is fully inert so legacy row clicks + inline editing are
    preserved."""
    js = _read(SIDE_SHEET_JS)
    assert (
        "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in js
    )


def test_side_sheet_js_uses_shared_fragment_url_and_row_selector() -> None:
    """Content reuses the existing fragment infra (no new API — same URL as
    foms_split_view.build_split_master_cards.detail_href) and targets the shared legacy
    grid row selector; interactive row children are excluded from the tap target."""
    js = _read(SIDE_SHEET_JS)
    assert "/api/foms/fragment/order/" in js
    assert "/edit?open=erp-order" in js
    assert "#erp-grid tr.erp-main-row[data-order-id]" in js
    assert "a, button, input, select, label, textarea" in js


def test_side_sheet_js_is_non_blocking_dialog() -> None:
    """ARIA: role=dialog + aria-modal=false (non-blocking — no scrim, the grid stays
    interactive behind the sheet, per spec)."""
    js = _read(SIDE_SHEET_JS)
    assert '"role", "dialog"' in js
    assert '"aria-modal", "false"' in js


# --- (W10-2) CSS: 존재 + foms 토큰 + 폭/모션 -------------------------------


def test_side_sheet_css_exists_token_driven() -> None:
    """The side-sheet CSS exists, is 400px right-anchored (380px on ≤1200px viewport),
    uses foms tokens only (no hard-coded palette), and respects prefers-reduced-motion."""
    css = _read(SIDE_SHEET_CSS)
    assert ".foms-tablet-sheet" in css
    assert "width: 400px" in css
    assert "width: 380px" in css  # ≤1200px viewport
    assert "var(--foms-surface-base" in css
    assert "var(--foms-z-modal" in css
    assert "prefers-reduced-motion: reduce" in css


def test_side_sheet_css_header_close_is_44px_touch_target() -> None:
    """The header close control is a ≥44px touch target."""
    css = _norm(_read(SIDE_SHEET_CSS))
    m = re.search(r"\.foms-tablet-sheet__close \{[^}]*\}", css)
    assert m is not None, "missing .foms-tablet-sheet__close rule"
    assert "width: 44px" in m.group(0)
    assert "height: 44px" in m.group(0)


# --- (W10-3) layout_scripts defer 로드 + ?v 캐시버스터 (perf G1) -----------


def test_side_sheet_js_wired_in_layout_scripts_deferred() -> None:
    """The JS is loaded via layout_scripts.html with defer (perf G1) + a ?v cachebuster,
    mirroring the foms-mobile-select.js load line."""
    html = _read(LAYOUT_SCRIPTS)
    m = re.search(r"<script[^>]*tablet-side-sheet\.js[^>]*>", html)
    assert m is not None, "tablet-side-sheet.js not wired in layout_scripts.html"
    tag = m.group(0)
    assert "defer" in tag, "side-sheet script must be defer (perf G1)"
    assert "?v=" in tag, "side-sheet script must carry a ?v cachebuster"


# --- (W10-4) 3페이지 legacy 그리드 행 order-id 소스 계약 -------------------


def test_legacy_grids_expose_order_id_on_main_row() -> None:
    """All three legacy grids (control-tower / construction / production) expose the
    order id on tr.erp-main-row via data-order-id — the side-sheet row-tap source.
    Shared markup, so no template change was needed for W10; this locks that source."""
    for rel in _LEGACY_GRID_PARTIALS:
        body = _norm(_read(rel))
        assert 'id="erp-grid"' in body, f"{rel}: missing #erp-grid table"
        assert 'class="erp-main-row" data-order-id=' in body, (
            f"{rel}: main row missing data-order-id source"
        )


# =====================================================================
# W11 — 요약 타일 스트립 (프로세스맵 경보/스텝 태블릿 타일 시각)
# (docs/plans/2026-07-11-tablet-t2-dashboards-spec.md, 실행 단위 W11)
# 마크업 무변경 — 태블릿 가로 코호트에서만 타일 시각 전환(CSS만, --process-map 스코프).
# 큰 숫자 ≥22px(=2xl 24px), 라벨 12px(=xs), 정상 무채색·경보만 유채색(HMI).
# =====================================================================


def test_tile_pipeline_steps_are_touch_tiles_with_big_number() -> None:
    """파이프라인 스텝이 태블릿 코호트에서 터치 타일(≥48px, --process-map 스코프) +
    큰 숫자(2xl ≥22px) + 12px 라벨로 전환된다(마크업 무변경, 수평 strip 유지)."""
    css = _norm(_read(LANDSCAPE_CSS))
    assert (
        ".erp-pro-card--process-map .erp-pro-pipeline__stage "
        "{ min-height: var(--foms-touch-target-min)" in css
    )
    assert ".erp-pro-pipeline__count { font-size: var(--foms-font-size-2xl)" in css
    assert ".erp-pro-pipeline__label { font-size: var(--foms-font-size-xs)" in css


def test_tile_alerts_become_full_width_grid_strip() -> None:
    """경보 KPI가 카드 헤더 세로 스택 → 전폭 4-타일 그리드 스트립으로 재배치되고,
    값은 큰 숫자(2xl), 라벨은 12px. 색(danger/warning/info)은 03-card-pipeline.css
    소유 규칙이 유지(HMI: 정상 무채색·경보만 유채색)."""
    css = _norm(_read(LANDSCAPE_CSS))
    assert "with-alerts .erp-pro-alerts { display: grid" in css
    assert "grid-template-columns: repeat(4, 1fr)" in css
    assert ".erp-pro-alert__value { font-size: var(--foms-font-size-2xl)" in css
    assert ".erp-pro-alert__label { font-size: var(--foms-font-size-xs)" in css


def test_tile_section_is_token_driven_and_cohort_scoped() -> None:
    """타일 터치 지오메트리는 foms 토큰 구동(하드코딩 회귀 차단): 경보 타일 최소 높이 =
    comfortable(44px). W11 규칙도 코호트 게이트(body.erp-mobile-v2-layout) 하위."""
    css = _norm(_read(LANDSCAPE_CSS))
    assert ".erp-pro-alert { min-height: var(--foms-touch-target-comfortable)" in css
    assert "body.erp-mobile-v2-layout .erp-pro-card--process-map" in css
