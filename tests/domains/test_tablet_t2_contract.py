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
TABLET_BUNDLE_CSS = "static/css/foundation/foms-tablet-bundle.css"

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
    # 6) (defect 7) sticky 재선언 규칙은 dead rule 로 제거됨 — sticky top/bg/z-index 및
    #    position:sticky !important 는 dashboard-grid.css '#erp-grid thead th' 가 SSOT 로
    #    소유한다. 여기서 문자열 부재를 잠그지는 않는다(무관 규칙 우발 매치로 인한 false-fail
    #    방지) — 삭제는 diff 로 검증.


# --- (2) @import wiring (W9 landscape + W10 side-sheet) --------------------


def test_mobile_surfaces_imports_landscape_and_side_sheet() -> None:
    """W16: 태블릿 T2 융합 레이어는 셸-독립 번들(foms-tablet-bundle.css)이 소유한다(v3 코호트
    미로드 실사고 봉합). 번들이 W9 landscape + W10 side-sheet 를 번들-상대 경로로 @import 하고,
    surfaces 에는 더 이상 없다(단일 소유=번들)."""
    bundle = _read(TABLET_BUNDLE_CSS)
    surfaces = _read(MOBILE_SURFACES_CSS)
    assert '@import url("foms-tablet-landscape.css?v=' in bundle, (
        "missing W9 landscape @import in bundle"
    )
    assert '@import url("../components/foms-tablet-side-sheet.css?v=' in bundle, (
        "missing W10 side-sheet @import in bundle"
    )
    assert "foms-tablet-landscape" not in surfaces
    assert "foms-tablet-side-sheet" not in surfaces


def test_mobile_surfaces_parent_cachebuster_bumped() -> None:
    """The mobile-surfaces content changed (W12 added the measurement + kanban @imports; W14
    bumped the landscape + side-sheet child @imports) so its layout_head ?v must be bumped past
    the prior baseline (T0 교훈: 자식 범프=부모 내용 변경=부모도 범프).
    W9=ae → W11=af → W12=ag → W14=ah."""
    layout_head = _read("templates/partials/shared/layout_head.html")
    assert "foms-mobile-surfaces.css') }}?v=20260712a" in layout_head
    assert "foms-mobile-surfaces.css') }}?v=20260711ag" not in layout_head


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


# =====================================================================
# W13 — 생산 칸반 보드 (태블릿 가로)
# (docs/plans/2026-07-11-tablet-t2-dashboards-spec.md, 실행 단위 W13)
# read-model 3버킷 칸반이 태블릿 가로에서 legacy 작업 큐 테이블을 대체. 서버 무변경
# (dashboard.py `orders` 재소비, 행 stage 버킷으로 Jinja 그룹핑). 열 이동 = 기존
# production start/complete API. 카드 탭 = tablet-side-sheet 위임 확장.
# =====================================================================

KANBAN_PARTIAL = "templates/production/partials/tablet_kanban_body.html"
KANBAN_CSS = "static/css/foundation/foms-tablet-production-kanban.css"
KANBAN_JS = "static/js/foms/tablet-production-kanban.js"
PRODUCTION_DASHBOARD_BODY = "templates/production/partials/dashboard_body.html"


def test_kanban_partial_exists_with_three_bucket_labels() -> None:
    """파샬 존재 + read-model 3버킷 라벨(제작대기/제작중/제작완료) + 카드 order-id 소스."""
    body = _read(KANBAN_PARTIAL)
    for bucket in ("제작대기", "제작중", "제작완료"):
        assert bucket in body, f"missing kanban bucket label: {bucket}"
    assert "foms-kanban-card" in body
    assert "data-order-id=" in body


def test_kanban_groups_read_model_bucket_via_row_stage() -> None:
    """버킷 접근 방식 판정: 서버 무변경 — 행 dict의 stage(버킷 라벨)로 Jinja selectattr
    그룹핑(신규 컨텍스트/쿼리 없음)."""
    body = _norm(_read(KANBAN_PARTIAL))
    assert "selectattr('stage', 'equalto', '제작대기')" in body
    assert "selectattr('stage', 'equalto', '제작중')" in body
    assert "selectattr('stage', 'equalto', '제작완료')" in body


def test_kanban_move_buttons_reuse_existing_production_api() -> None:
    """열 이동 = 신규 API 없이 기존 생산 워크플로 엔드포인트 재사용(production/orders.py)."""
    js = _read(KANBAN_JS)
    assert "/api/orders/" in js
    assert "/production/start" in js
    assert "/production/complete" in js


def test_kanban_js_has_idempotent_guard() -> None:
    """fragment 재실행/재로드 시 전역 listener 중복 바인딩 방지(perf G4)."""
    js = _read(KANBAN_JS)
    assert "window.__FOMS_KANBAN_BOUND" in js


def test_kanban_js_wired_in_layout_scripts_deferred() -> None:
    """칸반 JS는 layout_scripts.html에서 defer + ?v 캐시버스터로 로드(perf G1, W10 전례)."""
    html = _read(LAYOUT_SCRIPTS)
    m = re.search(r"<script[^>]*tablet-production-kanban\.js[^>]*>", html)
    assert m is not None, "tablet-production-kanban.js not wired in layout_scripts.html"
    tag = m.group(0)
    assert "defer" in tag, "kanban script must be defer (perf G1)"
    assert "?v=" in tag, "kanban script must carry a ?v cachebuster"


def test_side_sheet_delegation_extended_to_kanban_cards() -> None:
    """카드 탭 → 상세 시트: side-sheet 위임 셀렉터에 .foms-kanban-card[data-order-id]
    확장(최소 1줄). 기존 그리드 행 셀렉터도 보존(회귀 금지)."""
    js = _read(SIDE_SHEET_JS)
    assert ".foms-kanban-card[data-order-id]" in js
    assert "#erp-grid tr.erp-main-row[data-order-id]" in js


def test_kanban_wired_into_dashboard_body_with_legacy_wrapper() -> None:
    """dashboard_body.html include 배선 + legacy 큐 배타 래퍼(.foms-production-legacy-queue)."""
    body = _read(PRODUCTION_DASHBOARD_BODY)
    assert "production/partials/tablet_kanban_body.html" in body
    assert "foms-production-legacy-queue" in body


def test_kanban_css_exclusivity_couples_hide_and_show_no_blank() -> None:
    """배타(blank 금지): 기본은 칸반 은닉 / legacy 표시. 태블릿 가로 코호트에서 legacy
    은닉과 칸반 표시가 **동일 게이트**(코호트 body class + 코어 MQ) 아래 결합 → 어떤
    조합도 3영역 전부 은닉되지 않는다."""
    css = _norm(_read(KANBAN_CSS))
    assert ".foms-kanban { display: none" in css  # 기본 은닉(PC/모바일 fallback)
    assert CORE_MEDIA_QUERY in css
    assert "body.erp-mobile-v2-layout .foms-kanban { display: grid" in css
    assert "body.erp-mobile-v2-layout .foms-production-legacy-queue { display: none" in css


def test_kanban_css_hmi_color_only_on_dday_chip() -> None:
    """HMI 색 규율: 카드/열은 무채색, 상차 D-day 칩만 임박/지연 시 유채색."""
    css = _norm(_read(KANBAN_CSS))
    assert ".foms-kanban-chip.is-imminent" in css
    assert ".foms-kanban-chip.is-overdue" in css


def test_kanban_css_is_landscape_only_no_portrait_token() -> None:
    """세로=모바일 셸 — 이 파일은 landscape 전용(portrait 토큰 금지, split-view 가드 정합)."""
    css = _read(KANBAN_CSS)
    assert "orientation: portrait" not in css


# =====================================================================
# W12 — 태블릿 실측 특수형 split view 계약
# (docs/plans/2026-07-11-tablet-t2-dashboards-spec.md, 실행 단위 W12)
# 태블릿 가로 코호트: 좌 고객 리스트(300px, 실측일 순) + 우 기존 ERP Order edit fragment.
# "실측 입력 = 주문 원장 직접 기록". 서버 무변경(dashboard.py `rows` 재소비). fragment 로더는
# 공용 SSOT(fragment-loader.js)로 추출 — 사이드 시트와 단일 구현 공유(중복 구현 금지).
# =====================================================================

MEASURE_PARTIAL = "templates/measurement/partials/tablet_split_body.html"
MEASURE_CSS = "static/css/foundation/foms-tablet-measurement.css"
MEASURE_JS = "static/js/foms/tablet-measurement.js"
FRAGMENT_LOADER_JS = "static/js/foms/fragment-loader.js"
MEASURE_DASHBOARD_MAIN = "templates/measurement/partials/dashboard_main.html"


def test_tablet_measure_partial_exists_and_reuses_rows() -> None:
    """파샬 존재 + split 3영역 클래스 + rows 반복(서버 무변경 재소비) + 카드 order-id 소스 +
    5개 카드 필드(고객/주소/실측시간/제품/상태) 참조."""
    body = _read(MEASURE_PARTIAL)
    assert "foms-tablet-measure-split" in body
    assert "foms-tablet-measure-list" in body
    assert "foms-tablet-measure-detail" in body
    assert "for r in" in body
    assert "rows" in body
    assert 'data-order-id="{{ r.id }}"' in body
    for field in ("customer_name", "address", "measurement_time", "strip_product_w", "ALL_STATUS"):
        assert field in body, f"missing card field reference: {field}"


def test_dashboard_main_includes_tablet_split_cohort_gated() -> None:
    """dashboard_main.html 이 split 파샬을 erp_mobile_v2_enabled 게이트 안에서 include."""
    body = _norm(_read(MEASURE_DASHBOARD_MAIN))
    assert "measurement/partials/tablet_split_body.html" in body
    assert (
        "{% if erp_mobile_v2_enabled %} "
        "{% include 'measurement/partials/tablet_split_body.html' %}"
    ) in body


def test_tablet_measurement_css_exists_exclusive_and_landscape_only() -> None:
    """CSS 존재 + 코호트 MQ + base-hide 가 opt-in(flex) 앞(T0 순서 계약) + desktop-shell
    은닉 + 페이지 스코프 + 좌 리스트 300px + portrait 토큰 금지(landscape 전용)."""
    css = _norm(_read(MEASURE_CSS))
    assert CORE_MEDIA_QUERY in css
    base_idx = css.index(".foms-tablet-measure-split { display: none")
    flex_idx = css.index("display: flex")
    assert base_idx < flex_idx, "base-hide 규칙이 opt-in(display:flex) 뒤에 있음(순서 계약 위반)"
    assert ".erp-measurement-desktop-shell { display: none !important" in css
    assert ".erp-measurement-dashboard" in css
    assert "300px" in css
    assert "orientation: portrait" not in css


def test_mobile_surfaces_imports_measurement_and_kanban_reserved() -> None:
    """W16: 번들(foms-tablet-bundle.css)이 W12 measurement + W13 kanban 을 @import 하고,
    surfaces 에는 없다(단일 소유=번들)."""
    bundle = _read(TABLET_BUNDLE_CSS)
    surfaces = _read(MOBILE_SURFACES_CSS)
    assert '@import url("foms-tablet-measurement.css?v=' in bundle
    assert '@import url("foms-tablet-production-kanban.css?v=' in bundle
    assert "foms-tablet-measurement" not in surfaces
    assert "foms-tablet-production-kanban" not in surfaces


def test_fragment_loader_module_exists() -> None:
    """공용 fragment 로더 SSOT: window.FomsFragmentLoader 정의 + activateScripts 식
    createElement("script") + application/json(type) 보존 + erp-shell 재바인딩 디스패치.
    (defect 5: main-content-swapped 는 fragment 인라인 SSOT 로 이관됨 — 아래 double-dispatch
    계약 참고. 로더는 인라인이 발화하지 않는 erp-shell-fragment-swapped 만 발화.)"""
    js = _read(FRAGMENT_LOADER_JS)
    assert "window.FomsFragmentLoader" in js
    assert 'createElement("script")' in js
    assert "s.type = old.type" in js  # type 보존 → application/json 프리로드 블록 실행 방지
    assert "foms:erp-shell-fragment-swapped" in js


def test_tablet_measurement_js_exists_cohort_and_loader() -> None:
    """실측 split JS: idempotent 가드 + 코호트 MQ + 공용 로더 사용 + 카드 셀렉터 + edit URL."""
    js = _read(MEASURE_JS)
    assert "window.__FOMS_TABLET_MEASURE_BOUND" in js
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in js
    assert "window.FomsFragmentLoader" in js
    assert ".foms-tablet-measure-card" in js
    assert "/edit?open=erp-order" in js


def test_split_and_loader_and_measure_js_wired_deferred() -> None:
    """layout_scripts.html: fragment-loader/side-sheet/measurement 세 스크립트 모두 defer +
    ?v=, 그리고 fragment-loader 가 tablet-side-sheet 보다 먼저(defer 순서=정의 순서)."""
    html = _read(LAYOUT_SCRIPTS)
    for name in ("fragment-loader.js", "tablet-side-sheet.js", "tablet-measurement.js"):
        m = re.search(r"<script[^>]*" + re.escape(name) + r"[^>]*>", html)
        assert m is not None, f"{name} not wired in layout_scripts.html"
        tag = m.group(0)
        assert "defer" in tag, f"{name} must be defer (perf G1)"
        assert "?v=" in tag, f"{name} must carry a ?v cachebuster"
    assert html.index("fragment-loader.js") < html.index("tablet-side-sheet.js"), (
        "fragment-loader must load before tablet-side-sheet (shared loader defined first)"
    )


def test_side_sheet_still_uses_shared_loader() -> None:
    """리팩터 후 사이드 시트는 공용 로더 사용 + 모든 pinned 문자열 보존(회귀 금지)."""
    js = _read(SIDE_SHEET_JS)
    assert "window.FomsFragmentLoader" in js
    assert "window.__FOMS_TABLET_SHEET_BOUND" in js
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in js
    assert "/api/foms/fragment/order/" in js
    assert "/edit?open=erp-order" in js
    assert "#erp-grid tr.erp-main-row[data-order-id]" in js
    assert "a, button, input, select, label, textarea" in js


# =====================================================================
# W14 — 울트라 재검토 결함 7건 봉합 계약
# (docs/plans/2026-07-11-tablet-t2-dashboards-spec.md W14 브리프)
# =====================================================================

MEASURE_JS_W14 = "static/js/foms/tablet-measurement.js"
KANBAN_JS_W14 = "static/js/foms/tablet-production-kanban.js"


def test_w14_tablet_ui_gate_marker_is_css_ssot_consumed_by_all_three_js() -> None:
    """defect 1: JS 활성 게이트를 CSS 로드 여부에서 파생(이중 정의 금지).
    마커 --foms-tablet-ui:ready 는 시트 CSS 가 body.erp-mobile-v2-layout 에 정의(SSOT)하고,
    태블릿 JS 3종(side-sheet·measurement·kanban)이 getComputedStyle 로 이를 소비한다.
    → 비-v2(legacy/v3) coarse 태블릿(CSS 미로드)에서 3종 JS 완전 무동작."""
    css = _norm(_read(SIDE_SHEET_CSS))
    assert "body.erp-mobile-v2-layout { --foms-tablet-ui: ready" in css, (
        "side-sheet CSS 에 게이트 마커(SSOT) 부재"
    )
    for rel in (SIDE_SHEET_JS, MEASURE_JS_W14, KANBAN_JS_W14):
        js = _read(rel)
        assert "--foms-tablet-ui" in js, f"{rel}: 게이트 마커 미소비"
        assert "getComputedStyle" in js, f"{rel}: getComputedStyle 로 마커 미조회"
        assert 'trim() === "ready"' in js, f"{rel}: 마커 값 'ready' 미검사"


def test_w14_filter_16px_specificity_override_beats_grid_css() -> None:
    """defect 2: dashboard-grid.css `#erp-filters-form .form-control{.85rem}`(1,1,0)이
    `.erp-dashboard-filters .form-control`(0,3,1)을 이기므로, 동일 id 스코프로 16px 재선언해
    (1,2,1 > 1,1,0) iOS 줌 방지를 실효화한다."""
    css = _norm(_read(LANDSCAPE_CSS))
    assert (
        "body.erp-mobile-v2-layout #erp-filters-form .form-control, "
        "body.erp-mobile-v2-layout #erp-filters-form .form-select { "
        "font-size: var(--foms-font-size-base)" in css
    ), "id-스코프 16px 특이도 재선언 부재"


def test_w14_fragment_loader_dedupes_src_scripts_once() -> None:
    """defect 4: fragment-loader 가 src 스크립트를 1회만 실행(dedupe). erp-order 모듈(~12 src)은
    singleton + 이벤트 재init 이라 매 로드 재로딩=낭비. 인라인은 매 로드 재실행(데이터 주입)."""
    js = _read(FRAGMENT_LOADER_JS)
    assert "activatedFragmentSrc" in js, "src 1회 실행 레지스트리 부재"
    assert "srcAlreadyLive" in js, "중복 src 판정 헬퍼 부재"
    # inert 노드 제거(재실행 skip 경로).
    assert "removeChild(old)" in js


def test_w14_fragment_loader_no_double_dispatch_of_main_content_swapped() -> None:
    """defect 5: fragment 인라인 <script>가 main-content-swapped SSOT 발화(HTMX split flow에도
    필요, activateScripts 재실행으로 로더 경유 커버). 로더는 이를 중복 발화하지 않는다 —
    erp-shell-fragment-swapped(인라인 미발화)만 발화."""
    js = _read(FRAGMENT_LOADER_JS)
    assert "foms:erp-shell-fragment-swapped" in js
    assert 'new CustomEvent("foms:main-content-swapped"' not in js
    assert "new CustomEvent('foms:main-content-swapped'" not in js
    # fragment 인라인 SSOT 는 여전히 존재(제거 금지 — HTMX split flow 계약).
    for rel in (
        "templates/partials/shared/foms_order_detail_fragment.html",
        "templates/orders/partials/order_detail_split_panel.html",
    ):
        assert "foms:main-content-swapped" in _read(rel), f"{rel}: 인라인 SSOT 발화 소실"


def test_w14_side_sheet_no_outside_click_auto_close() -> None:
    """defect 6: 비차단 non-modal 패널 — 외부 탭 자동 닫기 제거(X·ESC만). 뒤 그리드 조작마다
    시트가 닫히는 모순 제거. Escape 키 닫기와 close 버튼은 보존."""
    js = _read(SIDE_SHEET_JS)
    assert "!sheet.contains(target)" not in js, "외부클릭 자동 닫기 잔존"
    assert 'ev.key === "Escape"' in js, "ESC 닫기 소실"
    assert "close" in js  # X/ESC close 경로 보존


# =====================================================================
# W16 — 태블릿 T2 융합 레이어 셸-독립 번들 이관 계약
# (v3 코호트 미로드 실사고 봉합: 4종 @import 를 surfaces→foms-tablet-bundle.css 이관,
#  bundle 을 erp_mobile_v2_enabled(v2∪v3) 게이트로 layout_head 에서 공통 로드.)
# =====================================================================


def test_w16_tablet_bundle_exists_with_four_imports_shell_independent() -> None:
    """번들 파일 존재 + 4종 @import(번들-상대 경로) + 상단에 셸-독립 사유 주석."""
    bundle = _read(TABLET_BUNDLE_CSS)
    for frag in (
        '@import url("foms-tablet-landscape.css?v=',
        '@import url("../components/foms-tablet-side-sheet.css?v=',
        '@import url("foms-tablet-measurement.css?v=',
        '@import url("foms-tablet-production-kanban.css?v=',
    ):
        assert frag in bundle, f"bundle missing @import: {frag}"
    head = bundle[:600]
    assert ("직교" in head) or ("셸 변형" in head), "번들 상단 셸-독립 사유 주석 부재"


def test_w16_layout_head_loads_bundle_for_v2_and_v3_cohort() -> None:
    """layout_head 가 foms-tablet-bundle.css 를 erp_mobile_v2_enabled(코호트 공통) 게이트로
    로드하고 ?v=20260712a 를 가진다. v2 전용(shell_variant=='v2') 게이트가 아님을 검증."""
    layout_head = _read("templates/partials/shared/layout_head.html")
    idx = layout_head.find("foms-tablet-bundle.css")
    assert idx != -1, "layout_head 에 태블릿 번들 <link> 부재"
    assert "foms-tablet-bundle.css') }}?v=20260712a" in layout_head
    window = layout_head[max(0, idx - 200):idx]
    assert "erp_mobile_v2_enabled" in window, "번들 게이트가 erp_mobile_v2_enabled 아님"
    assert "shell_variant == 'v2'" not in window, "번들이 v2 전용 게이트로 로드됨(코호트 미공통)"


def test_w16_surfaces_no_longer_owns_tablet_files() -> None:
    """surfaces 단일 소유 이관: 4종 태블릿 파일명이 surfaces 에 하나도 없다."""
    surfaces = _read(MOBILE_SURFACES_CSS)
    for name in (
        "foms-tablet-landscape",
        "foms-tablet-side-sheet",
        "foms-tablet-measurement",
        "foms-tablet-production-kanban",
    ):
        assert name not in surfaces, f"surfaces 에 태블릿 파일명 잔존: {name}"
