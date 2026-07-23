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
    assert "foms-mobile-surfaces.css') }}?v=20260722c" in layout_head
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


def test_kanban_css_confirmed_change_has_persistent_border() -> None:
    """R6/R8: 확인됨 변경 카드(data-change-history=1, is-changed 아님)에 상설 정적 테두리 —
    원거리 식별용. 미확인(.is-changed danger 빨강 펄스)과 파스텔 라벤더로 위계 구분."""
    css = _norm(_read(KANBAN_CSS))
    assert '.foms-kanban-card[data-change-history="1"]:not(.is-changed)' in css


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
MEASURE_FORM_JS = "static/js/foms/tablet-measure-form.js"
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


def test_tablet_measurement_js_exists_cohort_and_delegates_to_form() -> None:
    """실측 split JS(좌측 큐): idempotent 가드 + 코호트 MQ + 카드 셀렉터 + 전용 폼 모듈 위임.

    W-MEASURE-FORM 변경: 우측 패널의 PC ERP Order fragment 주입을 폐기하고 전용 실측 폼 모듈
    (tablet-measure-form.js, window.FomsTabletMeasureForm)에 위임한다. 따라서 이전에 이 파일에서
    핀하던 OLD fragment-injection 계약(window.FomsFragmentLoader / '/edit?open=erp-order')은
    더 이상 실측 split 계약이 아니며, 폼 모듈 위임 계약으로 대체한다."""
    js = _read(MEASURE_JS)
    assert "window.__FOMS_TABLET_MEASURE_BOUND" in js
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in js
    assert ".foms-tablet-measure-card" in js
    # 우측 패널 = 전용 실측 폼 모듈 위임(더 이상 ERP fragment 주입이 아님).
    assert "FomsTabletMeasureForm" in js
    assert "window.FomsFragmentLoader" not in js, "실측 split 은 더 이상 fragment 로더 미사용(폼 위임)"
    assert "/edit?open=erp-order" not in js, "실측 split 은 더 이상 fragment edit URL 미사용(구조화 API)"


def test_tablet_measurement_form_module_exists_uses_structured_api() -> None:
    """전용 실측 폼 모듈(tablet-measure-form.js): 싱글턴 가드 + window.FomsTabletMeasureForm API +
    기존 구조화 API(GET/PUT /api/orders/<id>/structured) read-merge-write + 규격 spec_rows 기록 +
    사진 읽기전용(attachments GET). 신규 백엔드 없음(목업 frame02 전용 폼)."""
    js = _read(MEASURE_FORM_JS)
    assert "window.__FOMS_TABLET_MEASURE_FORM_BOUND" in js
    assert "window.FomsTabletMeasureForm" in js
    assert "/api/orders/" in js
    assert "/structured" in js
    assert "structured_data" in js
    assert "structured_schema_version" in js
    assert "spec_rows" in js
    assert "/attachments?category=measurement" in js
    # 실측 완료 = workflow.stage 변경(서버 _handle_stage_transition 이 단계 전환 처리).
    assert "workflow" in js and "DRAWING" in js


def test_tablet_measurement_form_wired_in_layout_scripts_deferred() -> None:
    """폼 모듈은 layout_scripts.html 에서 defer + ?v 로 로드되고, tablet-measurement.js 보다 먼저
    로드된다(window.FomsTabletMeasureForm 선정의 보장 — defer 순서=정의 순서)."""
    html = _read(LAYOUT_SCRIPTS)
    m = re.search(r"<script[^>]*tablet-measure-form\.js[^>]*>", html)
    assert m is not None, "tablet-measure-form.js not wired in layout_scripts.html"
    tag = m.group(0)
    assert "defer" in tag, "form module script must be defer (perf G1)"
    assert "?v=" in tag, "form module script must carry a ?v cachebuster"
    assert html.index("tablet-measure-form.js") < html.index("tablet-measurement.js"), (
        "form module must load before tablet-measurement.js (FomsTabletMeasureForm defined first)"
    )


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
    로드하고 ?v=20260713h 를 가진다. v2 전용(shell_variant=='v2') 게이트가 아님을 검증.
    (?v 는 2026-07-13 태블릿 클린 작업 큐 그리드 신설로 landscape.css 내용 변경 → 캐시 체인 규칙에 따라 g→h 범프.)"""
    layout_head = _read("templates/partials/shared/layout_head.html")
    idx = layout_head.find("foms-tablet-bundle.css")
    assert idx != -1, "layout_head 에 태블릿 번들 <link> 부재"
    assert "foms-tablet-bundle.css') }}?v=20260723a" in layout_head
    # Anchor on the nearest preceding `{% if %}` (the bundle gate) rather than a fixed
    # char window — the gate string grows over time (2026-07-12: +/wdcalculator arm).
    gate_start = layout_head.rfind("{% if", 0, idx)
    assert gate_start != -1, "번들 <link> 앞에 게이트 {% if %} 부재"
    window = layout_head[gate_start:idx]
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


# =====================================================================
# B1/B2 — AS · 이력 대시보드 융합 레이어 확장 계약 (2026-07-12, T2 확장)
# 목업 v8: 태블릿 가로 전 탭에서 "행 탭 → 우측 사이드 시트 + 터치 보정 그리드".
# #erp-grid(시공/생산/주문)·칸반만 배선돼 있던 것을 AS(.erp-as-dashboard) + 이력
# (.erp-history-mobile-shell) legacy 테이블 표면으로 확장. 서버 무변경(이력 본행 <tr> 에
# data-order-id + history-main-row 클래스만 추가), CSS/JS 확장만.
# =====================================================================

AS_DASHBOARD_BODY = "templates/cs/partials/as_dashboard_body.html"
HISTORY_DASHBOARD_BODY = "templates/orders/partials/history_dashboard_body.html"


def test_side_sheet_delegation_extended_to_as_and_history_rows() -> None:
    """행 탭 → 상세 시트: side-sheet 위임 셀렉터에 AS PC 테이블 본행과 이력 본행을 확장.
    기존 그리드/칸반 소스도 보존(회귀 금지)."""
    js = _read(SIDE_SHEET_JS)
    assert ".erp-as-dashboard .erp-pro-table-wrapper tbody tr[data-order-id]" in js
    assert ".erp-history-mobile-shell tr.history-main-row[data-order-id]" in js
    # 회귀 금지: 기존 그리드/칸반 소스 보존.
    assert "#erp-grid tr.erp-main-row[data-order-id]" in js
    assert ".foms-kanban-card[data-order-id]" in js


def test_side_sheet_interactive_guard_covers_role_button_and_form_check() -> None:
    """인터랙티브 가드 확장: AS 인라인 날짜/체크박스·상세 링크 + 이력 chevron([role=button])
    클릭이 시트를 열지 않도록 가드에 [role="button"], .form-check 포함(기존 6종도 보존)."""
    js = _read(SIDE_SHEET_JS)
    assert 'a, button, input, select, label, textarea, [role="button"], .form-check' in js


def test_side_sheet_active_row_cleanup_is_row_type_agnostic() -> None:
    """B1/B2: 하이라이트 정리 쿼리가 .erp-main-row 한정이면 AS/이력 본행 stale 하이라이트가
    남는다 → 클래스만으로(.foms-tablet-sheet-active) 매치해 행 타입 무관하게 제거."""
    js = _read(SIDE_SHEET_JS)
    assert 'querySelectorAll(".foms-tablet-sheet-active")' in js


def test_as_pc_table_main_row_exposes_side_sheet_source() -> None:
    """AS PC 테이블 본행이 data-order-id 를 노출(side-sheet 행 탭 소스). 마크업은 이미 존재 —
    이 소스가 사라지면 AS 시트가 무동작하므로 잠근다(템플릿 변경 없음)."""
    body = _norm(_read(AS_DASHBOARD_BODY))
    assert 'class="erp-pro-table-wrapper d-none d-md-block"' in body
    assert '<tr data-order-id="{{ r.id }}">' in body


def test_history_main_row_has_side_sheet_source_class_and_order_id() -> None:
    """이력 본행 <tr> 이 history-main-row + data-order-id 를 가져 side-sheet 위임 대상이 된다.
    이력은 읽기전용(감사) 화면이므로 편집 fragment 폴백 대신 읽기전용 스냅샷 시트를 명시 지정한다
    (data-foms-sheet-url → erp_history.history_tablet_sheet). 확장행(history-detail-row)과
    chevron([role=button]) 확장 UX 는 무변경(회귀 금지 동반 확인)."""
    body = _norm(_read(HISTORY_DASHBOARD_BODY))
    assert '<tr class="history-main-row" data-order-id="{{ o.id }}"' in body
    # 읽기전용 스냅샷 시트 명시 지정(편집 fragment 폴백 차단 — gap1).
    assert "data-foms-sheet-url=" in body
    assert "erp_history.history_tablet_sheet" in body
    # 확장행/chevron 계약 보존.
    assert 'class="history-detail-row"' in body
    assert "history-chevron" in body
    assert 'role="button"' in body


def test_as_history_touch_correction_rules_token_driven() -> None:
    """AS/이력 테이블 터치 보정: 본행 ≥48px(--foms-touch-target-min), 버튼 ≥44px
    (--foms-touch-target-comfortable), AS 인라인 입력 16px(--foms-font-size-base).
    코호트 게이트(body.erp-mobile-v2-layout) 하위 + foms 토큰 구동(하드코딩 회귀 차단)."""
    css = _norm(_read(LANDSCAPE_CSS))
    # 48px 본행 (AS + 이력 동일 규칙).
    assert (
        "body.erp-mobile-v2-layout .erp-as-dashboard .erp-pro-table-wrapper tbody "
        "tr[data-order-id], body.erp-mobile-v2-layout .erp-history-mobile-shell "
        "tr.history-main-row[data-order-id] { height: var(--foms-touch-target-min)" in css
    )
    # 44px 버튼 타깃.
    assert "min-height: var(--foms-touch-target-comfortable)" in css
    # 16px AS 인라인 입력(iOS 줌 방지).
    assert (
        ".erp-as-dashboard .erp-pro-table-wrapper .erp-pro-input { "
        "min-height: var(--foms-touch-target-comfortable); "
        "font-size: var(--foms-font-size-base)" in css
    )
    # 코호트 스코프.
    assert "body.erp-mobile-v2-layout .erp-as-dashboard" in css
    assert "body.erp-mobile-v2-layout .erp-history-mobile-shell" in css


# =====================================================================
# W-DRAWING — 도면 시트 썸네일 갤러리 (태블릿 가로)
# 태블릿 가로 코호트에서 도면 데스크톱 테이블을 카드 갤러리로 대체. 서버 무변경
# (rows 재소비, r.thumbnail_url 등). 카드 = 워크벤치 상세로 이동하는 앵커(신규 JS 없음).
# =====================================================================

DRAWING_GALLERY_PARTIAL = "templates/drawing/partials/tablet_gallery_body.html"
DRAWING_GALLERY_CSS = "static/css/foundation/foms-tablet-drawing-gallery.css"
DRAWING_DASHBOARD_BODY = "templates/drawing/partials/workbench_dashboard_body.html"


def test_drawing_gallery_partial_exists_reuses_rows_and_fields() -> None:
    body = _read(DRAWING_GALLERY_PARTIAL)
    assert "foms-drawing-gallery" in body
    assert "foms-drawing-gallery-card" in body
    assert "for r in rows" in body
    assert 'data-order-id="{{ r.id }}"' in body
    for field in ("customer_name", "construction_date", "drawing_status_label",
                  "thumbnail_url", "assignee_text", "sla_level"):
        assert field in body, f"missing card field reference: {field}"


def test_drawing_gallery_card_links_to_workbench_detail() -> None:
    body = _read(DRAWING_GALLERY_PARTIAL)
    assert "erp_drawing_workbench.erp_drawing_workbench_detail" in body
    assert "tab=timeline" in body


def test_dashboard_body_includes_gallery_cohort_gated_with_legacy_wrapper() -> None:
    body = _read(DRAWING_DASHBOARD_BODY)
    assert "foms-drawing-legacy-table" in body
    norm = _norm(body)
    assert (
        "{% if erp_mobile_v2_enabled %} "
        "{% include 'drawing/partials/tablet_gallery_body.html' %}"
    ) in norm


def test_drawing_gallery_css_exists_exclusive_and_landscape_only() -> None:
    css = _norm(_read(DRAWING_GALLERY_CSS))
    assert CORE_MEDIA_QUERY in css
    base_idx = css.index(".foms-drawing-gallery { display: none")
    grid_idx = css.index("display: grid")
    assert base_idx < grid_idx, "base-hide 규칙이 opt-in(display:grid) 뒤에 있음(순서 계약 위반)"
    assert "body.erp-mobile-v2-layout .foms-drawing-legacy-table { display: none" in css
    assert "body.erp-mobile-v2-layout .foms-drawing-gallery { display: grid" in css
    assert "orientation: portrait" not in css


def test_drawing_gallery_bundle_import() -> None:
    bundle = _read(TABLET_BUNDLE_CSS)
    assert '@import url("foms-tablet-drawing-gallery.css?v=' in bundle


# =====================================================================
# W17 — 시공 완료 금액 그리드 (태블릿 가로)
# 태블릿 가로 코호트에서 완료 대시보드의 사진 리뷰 리스트를 금액 그리드로 대체
# (목업 v8 P9). 데이터 = 라우트 서버 렌더(tablet_completion_rows) — 완료 API
# (foms/api/cs) 는 금액 미반환 + 수정 불가라, 라우트가 erp_display SSOT 헬퍼로 파생.
# 잔금 = 출고가 − 예약금 불변식. 행 탭 = tablet-side-sheet 위임 확장(신규 API 없음).
# =====================================================================

COMPLETION_GRID_PARTIAL = "templates/cs/partials/tablet_completion_grid_body.html"
COMPLETION_GRID_CSS = "static/css/foundation/foms-tablet-completion-grid.css"
COMPLETION_DASHBOARD_BODY = "templates/cs/partials/completion_dashboard_body.html"
COMPLETION_ROUTE = "foms/web/cs/completion_dashboard.py"


def test_completion_grid_partial_exists_with_mockup_columns() -> None:
    """파샬 존재 + 목업 P9 8컬럼 헤더(완료일/고객/제품/출고가/예약금/잔금/현금영수증/정산)
    + 카드 order-id 소스(사이드 시트 행 탭)."""
    body = _read(COMPLETION_GRID_PARTIAL)
    for header in ("완료일", "고객", "제품", "출고가", "예약금", "잔금", "현금영수증", "정산"):
        assert header in body, f"missing grid column header: {header}"
    assert "foms-completion-grid" in body
    assert 'data-order-id="{{ row.id }}"' in body


def test_completion_grid_uses_derived_amount_fields_not_reparse() -> None:
    """금액 셀은 라우트에서 1회 파생된 콤마 포맷 문자열을 그대로 출력(문자열 재파싱 금지).
    잔금 = 출고가 − 예약금 불변식은 라우트에서 계산."""
    body = _read(COMPLETION_GRID_PARTIAL)
    for field in ("shipping_price_display", "deposit_display", "balance_display"):
        assert field in body, f"missing derived amount field: {field}"


def test_completion_grid_route_derives_amounts_from_ssot_helpers() -> None:
    """라우트가 금액 SSOT 헬퍼(erp_shipping_price_from_structured /
    erp_deposit_amount_from_structured)로 파생하고, 잔금=출고가−예약금 불변식을 계산.
    코호트(v2∪v3)에서만 서버 적재(PC 서버 쿼리 무추가)."""
    route = _read(COMPLETION_ROUTE)
    assert "erp_shipping_price_from_structured" in route
    assert "erp_deposit_amount_from_structured" in route
    assert "shipping_price - (deposit or 0)" in route  # 잔금 불변식
    assert "is_mobile_v2_shell" in route  # 코호트 게이트(서버 적재)
    assert "tablet_completion_rows" in route


def test_completion_grid_css_exclusivity_couples_hide_and_show_no_blank() -> None:
    """배타(blank 금지): 기본은 그리드 은닉. 태블릿 가로 코호트에서 사진 리뷰 은닉과
    그리드 표시가 **동일 게이트**(코호트 body class + 코어 MQ) 아래 결합."""
    css = _norm(_read(COMPLETION_GRID_CSS))
    base_idx = css.index(".foms-completion-grid { display: none")
    show_idx = css.index("display: flex")
    assert base_idx < show_idx, "base-hide 규칙이 opt-in(display:flex) 뒤에 있음(순서 계약 위반)"
    assert CORE_MEDIA_QUERY in css
    assert "body.erp-mobile-v2-layout .foms-completion-grid { display: flex" in css
    assert "body.erp-mobile-v2-layout .foms-completion-photo-review { display: none" in css


def test_completion_grid_css_landscape_only_and_touch_token_driven() -> None:
    """landscape 전용(portrait 토큰 금지) + 터치 보정 토큰 구동: 데이터 행 ≥48px
    (--foms-touch-target-min), 정산 배지 ≥44px(--foms-touch-target-comfortable).
    하드코딩 회귀 차단."""
    css = _norm(_read(COMPLETION_GRID_CSS))
    assert "orientation: portrait" not in css
    assert (
        ".foms-completion-grid__table tbody tr { height: var(--foms-touch-target-min)"
        in css
    )
    assert "var(--foms-touch-target-comfortable)" in css


def test_completion_grid_wired_into_body_cohort_gated_with_wrapper() -> None:
    """body include 배선(erp_mobile_v2_enabled 게이트) + 사진 리뷰 카드 배타 래퍼 클래스
    (.foms-completion-photo-review)."""
    body = _norm(_read(COMPLETION_DASHBOARD_BODY))
    assert "cs/partials/tablet_completion_grid_body.html" in body
    assert (
        "{% if erp_mobile_v2_enabled %} "
        "{% include 'cs/partials/tablet_completion_grid_body.html' %}"
    ) in body
    assert "foms-completion-photo-review" in body


def test_completion_grid_bundle_import() -> None:
    """번들이 완료 그리드 CSS 를 @import(신규 @import 만 ?v 부여)."""
    bundle = _read(TABLET_BUNDLE_CSS)
    assert '@import url("foms-tablet-completion-grid.css?v=' in bundle


def test_side_sheet_delegation_extended_to_completion_grid_rows() -> None:
    """행 탭 → 상세 시트: side-sheet 위임 셀렉터에 완료 그리드 본행 확장(최소 1줄).
    기존 그리드/칸반/AS/이력 소스 보존(회귀 금지)."""
    js = _read(SIDE_SHEET_JS)
    assert ".foms-completion-grid tbody tr[data-order-id]" in js
    assert "#erp-grid tr.erp-main-row[data-order-id]" in js
    assert ".foms-kanban-card[data-order-id]" in js


# =====================================================================
# PIPE — 사이드 시트 상단 진행 단계 파이프라인 (2026-07-12, 태블릿 가로 마감 ①)
# 컨트롤타워 사이드 시트에 8단계 파이프 복원. 단계 카탈로그(순서·표시명)는 서버가
# STAGE_SEQUENCE(order_timeline_v3 SSOT)를 그리드 컨테이너의 data-foms-stage-catalog(JSON)로
# 내려보내고, 현재 단계는 행의 data-stage(=erp_stage_code)에서 읽는다. JS 단계 하드코딩 금지.
# =====================================================================

CONTROL_TOWER_GRID = "templates/orders/partials/dashboard_grid.html"


def test_pipe_catalog_delivered_via_grid_container_data_attr() -> None:
    """단계 카탈로그는 서버가 그리드 컨테이너의 data-foms-stage-catalog(|tojson)로 내려보낸다
    (JS 하드코딩 금지). 현재 단계는 행 <tr> 의 data-stage(=o.stage_code)에서 읽는다."""
    body = _norm(_read(CONTROL_TOWER_GRID))
    assert "data-foms-stage-catalog='{{ foms_stage_catalog|tojson }}'" in body, (
        "그리드 컨테이너에 stage 카탈로그 data 속성 부재"
    )
    assert 'class="erp-main-row" data-order-id="{{ o.id }}" data-stage="{{ o.stage_code }}"' in body, (
        "행에 data-stage(현재 단계 소스) 부재"
    )


def test_pipe_catalog_order_matches_stage_sequence_ssot() -> None:
    """카탈로그 순서·표시명이 STAGE_SEQUENCE(SSOT)와 정확히 정합(8단계, code+label)."""
    from foms.services.context_processors import _foms_stage_catalog
    from foms.services.order_timeline_v3 import STAGE_SEQUENCE

    catalog = _foms_stage_catalog()
    assert len(catalog) == 8, "8단계 워크플로 카탈로그가 아님"
    assert [code for code, _label, _slug in STAGE_SEQUENCE] == [d["code"] for d in catalog], (
        "카탈로그 코드 순서가 STAGE_SEQUENCE 와 불일치"
    )
    assert [label for _code, label, _slug in STAGE_SEQUENCE] == [d["label"] for d in catalog], (
        "카탈로그 표시명이 STAGE_SEQUENCE 와 불일치"
    )


def test_pipe_js_renders_from_server_catalog_no_hardcoded_stage_list() -> None:
    """JS 는 서버 카탈로그(data-foms-stage-catalog)에서 렌더하고 현재 단계를 data-stage 에서
    읽는다. 단계 코드 목록을 JS 에 하드코딩하지 않는다(RECEIVED/MEASURE 등 부재)."""
    js = _read(SIDE_SHEET_JS)
    assert "renderPipe" in js
    assert '"[data-foms-stage-catalog]"' in js
    assert 'getAttribute("data-stage")' in js
    # 단계 목록 하드코딩 금지(카탈로그는 서버 SSOT).
    for code in ("RECEIVED", "MEASURE", "DRAWING", "CONFIRM", "PRODUCTION", "CONSTRUCTION"):
        assert code not in js, f"JS 에 단계 코드 하드코딩됨: {code}"


def test_pipe_js_graceful_absence_when_stage_not_derivable() -> None:
    """단계 파생 불가 행(카탈로그 미매치=AS/이력/칸반 등)이면 파이프를 hidden 처리(우아한 부재)."""
    js = _read(SIDE_SHEET_JS)
    assert "curIdx < 0" in js
    assert "pipeEl.hidden = true" in js
    # 파이프는 idempotent — 열림마다 innerHTML 재구성.
    assert "pipeEl.innerHTML" in js


def test_pipe_css_exists_token_driven_done_and_now_states() -> None:
    """시트 CSS 에 파이프 스타일: 완료(성공 토큰)·현재(브랜드 토큰) 상태 + 토큰 구동."""
    css = _read(SIDE_SHEET_CSS)
    assert ".foms-tablet-sheet__pipe" in css
    assert ".foms-tablet-pipe__step.is-done" in css
    assert ".foms-tablet-pipe__step.is-now" in css
    assert "var(--foms-color-success-500" in css
    assert "var(--foms-interactive-primary" in css


# =====================================================================
# CALC-SKIN — 계산기 태블릿 표피 (2026-07-12, 태블릿 가로 마감 ②)
# PC 구조·id·계산엔진 DOM 무변경. 순수 CSS 표피(입력 52px·터치 44px), 코호트 MQ 게이트.
# =====================================================================

CALC_SKIN_CSS = "static/css/wdcalculator/tablet-skin.css"
CALC_TEMPLATE = "templates/wdcalculator/calculator.html"


def test_calc_skin_css_exists_cohort_gated_and_landscape_only() -> None:
    """스킨 파일 존재 + 코어 코호트 MQ(min-width:992 landscape coarse) + 페이지 스코프
    (.wdcalculator-container) + landscape 전용(portrait 토큰 금지)."""
    css = _read(CALC_SKIN_CSS)
    assert CORE_MEDIA_QUERY in css, "계산기 스킨에 코어 태블릿 코호트 MQ 부재"
    assert ".wdcalculator-container" in css, "스킨이 계산기 컨테이너로 스코프되지 않음"
    assert "orientation: portrait" not in css, "landscape 전용인데 portrait 토큰 존재"


def test_calc_skin_css_has_52px_input_and_44px_target() -> None:
    """목업 표피 스펙: 주 입력 52px + 터치 타깃 44px."""
    css = _norm(_read(CALC_SKIN_CSS))
    assert "min-height: 52px" in css, "52px 입력 스펙 부재"
    assert "min-height: 44px" in css, "44px 터치 타깃 스펙 부재"


def test_calc_skin_wired_in_calculator_template_with_cachebuster() -> None:
    """calculator.html 이 기존 <link> 패턴대로 스킨을 로드하고 ?v=20260713f 캐시버스터를 가진다.
    (2026-07-13 접힘 스킨 수리로 a→e, 하단 고정 최종견적 바 추가로 e→f, 하단바 가격 정렬 정합으로 f→o 범프.)"""
    html = _read(CALC_TEMPLATE)
    m = re.search(r"tablet-skin\.css'\s*\)\s*}}\?v=20260716g", html)
    assert m is not None, "calculator.html 에 tablet-skin.css ?v=20260716g <link> 부재"


# =====================================================================
# T-CTOWER — 컨트롤타워 상단 바 교체 (2026-07-13, 목업 프레임 01)
# 태블릿 가로 코호트에서 orders 대시보드의 PC 잔존 크롬(프로세스맵 밴드+파이프라인+작업 큐
# 카드 헤더+"표시:N" 뱃지)을 은닉하고 pcbar+KPI 5타일(tablet_dashboard_topbar.html)로 교체.
# 서버 무변경(기존 total_orders/kpis/today_iso 재소비 — 신규 쿼리 없음).
# =====================================================================

CTOWER_TOPBAR_PARTIAL = "templates/orders/partials/tablet_dashboard_topbar.html"
ORDERS_DASHBOARD_MAIN = "templates/orders/partials/dashboard_main.html"
CONSTRUCTION_CSS = "static/css/foundation/foms-tablet-construction.css"
CONSTRUCTION_DASHBOARD_BODY = "templates/construction/partials/dashboard_body.html"


def test_ctower_topbar_partial_exists_with_pcbar_and_five_tiles() -> None:
    """상단 바 파샬: pcbar(제목/sub/밀도 토글 include/엑셀 임포트/지도 생성/주문 생성) + KPI 5타일
    (전체 + 경보 3 + 도면 지연). 신규 쿼리 없이 기존 컨텍스트(total_orders/kpis/today_iso) 재소비."""
    body = _read(CTOWER_TOPBAR_PARTIAL)
    assert "foms-tdash-top" in body
    assert "foms-tdash-pcbar" in body
    assert "주문 대시보드" in body
    assert "주문 생성" in body
    # 밀도 토글 재배치(작업 큐 헤더 → pcbar).
    assert "partials/shared/foms_density_toggle.html" in body
    assert "order_pages.add_order" in body
    # 목업 01 pcbar = [밀도][엑셀 임포트][지도 생성][주문 생성] — 임포트/지도는 기존 라우트 재사용.
    assert "엑셀 임포트" in body and "excel.upload_excel" in body
    assert "지도 생성" in body and "erp_map.map_view" in body
    # KPI 5타일 = 전체 + 경보(긴급/실측 D-4/시공 D-3) + 도면 지연(drawing_overdue_count).
    # read-model 이 기존 overdue_cnt 집계를 drawing_overdue_count 로 합산(신규 쿼리 0).
    assert "foms-tdash-tiles" in body
    for field in (
        "total_orders",
        "kpis.urgent_count",
        "kpis.measurement_d4_count",
        "kpis.construction_d3_count",
        "kpis.drawing_overdue_count",
        "today_iso",
    ):
        assert field in body, f"topbar 파샬에 컨텍스트 참조 부재: {field}"


def test_ctower_topbar_wired_into_dashboard_main_cohort_gated() -> None:
    """dashboard_main.html 이 상단 바를 erp_mobile_v2_enabled 게이트 안에서 include + orders
    페이지 스코프 클래스(.erp-dashboard-orders)를 컨테이너에 부여."""
    body = _norm(_read(ORDERS_DASHBOARD_MAIN))
    assert "erp-dashboard-orders" in body, "orders 컨테이너 페이지 스코프 클래스 부재"
    assert (
        "{% if erp_mobile_v2_enabled %} "
        "{% include 'orders/partials/tablet_dashboard_topbar.html' %}"
    ) in body


def test_ctower_grid_relocates_density_toggle_and_tags_header() -> None:
    """작업 큐 카드 헤더에 은닉용 클래스(.erp-dashboard-workqueue-head)를 부여하고, 밀도 토글은
    이 헤더에서 제거(상단 pcbar 로 재배치 — 헤더째 은닉되므로 여기 두면 토글도 사라진다)."""
    grid = _read(CONTROL_TOWER_GRID)
    assert "erp-dashboard-workqueue-head" in grid
    assert "foms_density_toggle.html" not in grid, "밀도 토글이 그리드 헤더에서 미제거(재배치 실패)"


def test_ctower_landscape_css_hides_pc_chrome_and_shows_topbar() -> None:
    """landscape CSS: 상단 바 base-hide 가 show 앞(순서 계약) + orders 스코프 PC 프로세스맵
    밴드/파이프라인/작업 큐 헤더 은닉 + pcbar/타일이 코호트 게이트 하위."""
    css = _norm(_read(LANDSCAPE_CSS))
    # base-hide 가 opt-in(show) 앞.
    base_idx = css.index(".foms-tdash-top { display: none")
    show_idx = css.index("body.erp-mobile-v2-layout .foms-tdash-top { display: flex")
    assert base_idx < show_idx, "상단 바 base-hide 가 show 뒤에 있음(순서 계약 위반)"
    # 코어 코호트 MQ 하위.
    assert CORE_MEDIA_QUERY in css
    # orders 페이지 스코프 은닉(프로세스맵 밴드 + 파이프라인 본문).
    assert (
        ".erp-dashboard-orders .erp-pro-card--process-map .erp-pro-card__header--with-alerts"
        in css
    )
    assert ".erp-dashboard-orders .erp-pro-card--process-map .erp-pro-card__body" in css
    # 작업 큐 카드 헤더 은닉.
    assert (
        "body.erp-mobile-v2-layout .erp-dashboard-orders .erp-dashboard-workqueue-head "
        "{ display: none" in css
    )
    # KPI 5타일 그리드 + 큰 숫자(2xl).
    assert "grid-template-columns: repeat(5, 1fr)" in css
    assert ".foms-tdash-tile__value { font-size: var(--foms-font-size-2xl" in css


def test_ctower_construction_css_hides_top_chrome_page_scoped() -> None:
    """construction CSS: 워크모드 위쪽 legacy 상단(.foms-shell-desktop-only)과 프로세스맵
    카드(.erp-pro-card--process-map)를 코호트 + construction 페이지 스코프로 은닉한다
    (목업 07: 상단 없음, 워크모드가 페이지 전체 소유). orders 무영향 위해 페이지 스코프 필수."""
    css = _norm(_read(CONSTRUCTION_CSS))
    assert CORE_MEDIA_QUERY in css
    assert (
        "body.erp-mobile-v2-layout .erp-construction-dashboard .foms-shell-desktop-only, "
        "body.erp-mobile-v2-layout .erp-construction-dashboard .erp-pro-card--process-map "
        "{ display: none" in css
    )
    # construction 페이지 컨테이너에 스코프 클래스 부여.
    body = _read(CONSTRUCTION_DASHBOARD_BODY)
    assert "erp-construction-dashboard" in body


# =====================================================================
# T-TQGRID — 컨트롤타워 클린 작업 큐 그리드 (2026-07-13, 목업 프레임 01)
# T-CTOWER 의 "PC 13열을 CSS 로 4열만 접기"는 목업 정합에 도달하지 못했다(컬럼 순서·경보
# 열·퀘스트 버튼/날짜 input/로고/결제 뱃지 잔존 — CSS 로 열 재정렬·버튼→plain 변환 불가).
# 목업 정합 클린 그리드를 템플릿(tablet_workqueue_grid.html)으로 신설하고, PC 그리드는
# 코호트에서 컨테이너째 은닉한다(셀 내용 무변경 → desktop/fine 보존). 행 탭 = 도크 위임 확장.
# 서버 무변경(기존 orders DTO 재소비 — 신규 쿼리 0).
# =====================================================================

WORKQUEUE_GRID_PARTIAL = "templates/orders/partials/tablet_workqueue_grid.html"


def test_tqgrid_partial_exists_with_mockup_columns_in_order() -> None:
    """클린 그리드 파샬: 목업 8열 헤더가 정확한 순서([체크박스]·단계·고객·다음 할 일·제품·
    실측일·시공일·담당·첨부)로 존재하고, 경보 열/PC data-col-key 는 없다."""
    body = _read(WORKQUEUE_GRID_PARTIAL)
    # 헤더 라벨은 순서대로(>LABEL</th> 는 헤더에만 매치 — 상단 주석/셀 주석 불매치).
    order = ["단계", "고객", "다음 할 일", "제품", "실측일", "시공일", "담당", "첨부"]
    idxs = [body.index(">" + label + "</th>") for label in order]
    assert idxs == sorted(idxs), "목업 컬럼 순서 불일치(단계·고객·다음할일·제품·실측일·시공일·담당·첨부)"
    # 경보 열 없음(PC 그리드 data-col-key/경보 th 부재).
    assert ">경보</th>" not in body
    assert "data-col-key" not in body
    # 벌크 호환 체크박스(첫 열).
    assert 'class="form-check-input erp-grid-order-check"' in body


def test_tqgrid_rows_are_plain_no_inputs_buttons_logos_paybadges() -> None:
    """셀 plain 계약: 날짜 input·퀘스트 collapse 버튼·라홈 로고·결제 코인 뱃지가 없다
    (목업: 모든 셀 plain 텍스트/배지). 다음 할 일은 현재 퀘스트 title 을 쓴다."""
    body = _read(WORKQUEUE_GRID_PARTIAL)
    assert 'type="date"' not in body, "실측/시공일에 날짜 input 잔존(목업: plain 텍스트)"
    assert 'data-bs-toggle="collapse"' not in body, "퀘스트 collapse 버튼 잔존(목업: plain 텍스트)"
    assert "lahom-logo" not in body, "고객 셀에 라홈 로고 잔존(목업: 이름+긴급칩만)"
    assert "pay-coin" not in body, "고객 셀에 결제 코인 뱃지 잔존(목업: 이름+긴급칩만)"
    # 다음 할 일 = 현재 퀘스트 title(허구 텍스트 금지 — 실 DTO 필드).
    assert "o.current_quest.title" in body
    # 긴급 칩은 urgent 알림일 때만.
    assert "foms-tqchip-urgent" in body
    assert "o.alerts.urgent" in body


def test_tqgrid_row_exposes_side_sheet_source_and_stage_badge() -> None:
    """행 계약: PC 그리드와 동일한 erp-main-row + data-order-id/data-stage/data-foms-sheet-url
    (도크 위임 소스) + 단계 SSOT 색 배지 + wrap 의 stage 카탈로그 data 속성(파이프라인 소스)."""
    body = _norm(_read(WORKQUEUE_GRID_PARTIAL))
    assert (
        'class="erp-main-row foms-tqrow" data-order-id="{{ o.id }}" '
        'data-stage="{{ o.stage_code }}"' in body
    ), "행에 도크 위임 소스(erp-main-row + data-order-id/data-stage) 부재"
    assert (
        "data-foms-sheet-url=\"{{ url_for('erp_dashboard.erp_dashboard_tablet_sheet'" in body
    ), "행에 시트 URL(data-foms-sheet-url) 부재"
    assert "foms-stage-badge foms-stage-badge{{ o.stage_badge_modifier" in body
    assert (
        "class=\"foms-tablet-workqueue-wrap\" "
        "data-foms-stage-catalog='{{ foms_stage_catalog|tojson }}'" in body
    ), "wrap 에 stage 카탈로그 data 속성(파이프라인 소스) 부재"


def test_tqgrid_wired_into_dashboard_main_cohort_gated() -> None:
    """dashboard_main.html 이 클린 그리드를 erp_mobile_v2_enabled 게이트 안에서 PC 그리드
    직후에 include(서버 v2∪v3 공통 렌더 — 표시/은닉은 CSS 게이트 소유)."""
    body = _norm(_read(ORDERS_DASHBOARD_MAIN))
    assert (
        "{% if erp_mobile_v2_enabled %} "
        "{% include 'orders/partials/tablet_workqueue_grid.html' %}"
    ) in body


def test_tqgrid_css_exclusivity_couples_show_and_pc_hide_no_blank() -> None:
    """배타(blank 금지): base-hide 가 show 앞(순서 계약) + 태블릿 가로 코호트에서 클린 그리드
    표시와 PC 작업 큐 카드(.erp-dashboard-workqueue) 은닉이 동일 게이트 아래 결합. 행 ≥48px
    터치 토큰 구동."""
    css = _norm(_read(LANDSCAPE_CSS))
    base_idx = css.index(".foms-tablet-workqueue-wrap { display: none")
    show_idx = css.index(
        "body.erp-mobile-v2-layout .foms-tablet-workqueue-wrap { display: block"
    )
    assert base_idx < show_idx, "base-hide 가 show 뒤에 있음(순서 계약 위반)"
    assert CORE_MEDIA_QUERY in css
    assert (
        "body.erp-mobile-v2-layout .erp-dashboard-orders .erp-dashboard-workqueue "
        "{ display: none !important" in css
    ), "PC 작업 큐 카드 코호트 은닉 규칙 부재"
    # 행 터치 지오메트리 = --foms-touch-target-min(하드코딩 회귀 차단).
    assert (
        ".foms-tqgrid tbody tr.foms-tqrow { height: var(--foms-touch-target-min" in css
    )


def test_tqgrid_side_sheet_delegation_and_autoselect_prefers_clean_grid() -> None:
    """도크 위임: side-sheet.js 셀렉터에 클린 그리드 본행 확장 + autoSelectFirstRow 가 표시 중인
    클린 그리드를 먼저 조회하고 PC #erp-grid 로 폴백(기존 소스 보존 — 회귀 금지)."""
    js = _read(SIDE_SHEET_JS)
    assert ".foms-tablet-workqueue-wrap tr.erp-main-row[data-order-id]" in js
    assert (
        'document.querySelector(".foms-tablet-workqueue-wrap '
        'tr.erp-main-row[data-order-id]") ||' in js
    ), "autoSelectFirstRow 가 클린 그리드를 우선 조회하지 않음"
    # 회귀 금지: PC 그리드 소스 보존.
    assert "#erp-grid tr.erp-main-row[data-order-id]" in js


# =====================================================================
# 태블릿 실측 견적서 탭 = PC edit iframe (open=erp-estimate&embedded=1)
# + 실측/시공 landscape 하단 여백 축소(과예약 rem 제거)
# =====================================================================


def test_tablet_measure_form_estimate_tab_embeds_pc_edit_iframe() -> None:
    """견적서 탭은 요약 스텁이 아니라 PC /edit?open=erp-estimate&embedded=1 iframe."""
    js = _read(MEASURE_FORM_JS)
    assert "open=erp-estimate" in js
    assert "embedded=1" in js
    assert "renderEstimateTab" in js
    assert 'title="견적서"' in js or "title='견적서'" in js
    # 스텁 요약 UI 폐기 — PC 문서 프리뷰로 대체.
    assert "PC 견적서(문서·인쇄) 열기" not in js
    assert "foms-tmf__est-hero" not in js


def test_tablet_measure_viewport_offset_is_tight() -> None:
    """실측 split 셸: landscape 크롬 숨김 후 과예약(9rem) 금지 — 최대 4rem 이하."""
    import re

    css = _norm(_read(MEASURE_CSS))
    assert "calc(100dvh - 9rem)" not in css
    m = re.search(
        r"\.foms-tablet-measure-split\s*\{[^}]*min-height:\s*calc\(100dvh - (\d+)rem\)",
        css,
    )
    assert m, "실측 split min-height viewport calc 부재"
    assert int(m.group(1)) <= 4, f"실측 split offset 과다: {m.group(1)}rem"


def test_tablet_construction_viewport_offset_is_tight() -> None:
    """시공 workmode 셸: landscape 크롬 숨김 후 과예약(12rem) 금지 — 최대 4rem 이하."""
    import re

    css = _norm(_read(CONSTRUCTION_CSS))
    assert "calc(100dvh - 12rem)" not in css
    m = re.search(
        r"\.foms-construction-workmode\s*\{[^}]*min-height:\s*calc\(100dvh - (\d+)rem\)",
        css,
    )
    assert m, "시공 workmode min-height viewport calc 부재"
    assert int(m.group(1)) <= 4, f"시공 workmode offset 과다: {m.group(1)}rem"
