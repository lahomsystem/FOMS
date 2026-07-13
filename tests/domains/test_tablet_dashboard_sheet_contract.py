"""태블릿 T2 목업 마감 계약 (2026-07-13) — 3건:

  A. 시트 URL 계약: tablet-side-sheet.js 가 행/카드의 data-foms-sheet-url 을 우선 로드하고
     없으면 기존 edit fragment URL 로 폴백(다른 워커 4기가 이 계약에 의존).
  B. 공용 밀도 토글: 컴포넌트(partial) + CSS(40/48/56 행높이, coarse landscape 게이트) +
     JS(defer·singleton·document 위임·localStorage) + 로드 배선 + 배치.
  C. 대시보드(01) 시트 목업화: fragment 라우트 + 목업 템플릿 + 그리드 행 URL 부여.

이 스위트는 기존 test_tablet_t2_contract.py 가 고정하지 않는 마감 문자열을 별도 파일로 잠근다
(동시 워커 병합 충돌 회피)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SIDE_SHEET_JS = "static/js/foms/tablet-side-sheet.js"
DENSITY_JS = "static/js/foms/tablet-density-toggle.js"
DENSITY_PARTIAL = "templates/partials/shared/foms_density_toggle.html"
LANDSCAPE_CSS = "static/css/foundation/foms-tablet-landscape.css"
LAYOUT_SCRIPTS = "templates/partials/shared/layout_scripts.html"
DASHBOARD_GRID = "templates/orders/partials/dashboard_grid.html"
HISTORY_BODY = "templates/orders/partials/history_dashboard_body.html"
DASHBOARD_ROUTE = "foms/web/orders/dashboard.py"
SHEET_TEMPLATE = "templates/orders/partials/tablet_dashboard_sheet.html"

CORE_MEDIA_QUERY = (
    "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# =====================================================================
# A. 시트 URL 계약 (최우선 — 다른 워커 의존)
# =====================================================================


def test_side_sheet_resolves_explicit_sheet_url_first() -> None:
    """행/카드에 data-foms-sheet-url 이 있으면 그 URL을, 없으면 edit fragment 로 폴백."""
    js = _read(SIDE_SHEET_JS)
    assert "resolveSheetUrl" in js, "resolveSheetUrl 헬퍼 부재"
    assert 'getAttribute("data-foms-sheet-url")' in js, "data-foms-sheet-url 미조회"
    # 폴백 = 기존 edit fragment URL (회귀 금지 — 다른 표면은 여전히 edit 로드).
    assert "/api/foms/fragment/order/" in js
    assert "/edit?open=erp-order" in js


def test_side_sheet_open_uses_resolved_url() -> None:
    """open() 이 resolveSheetUrl 결과를 load 에 넘긴다(URL 분기가 실제 로드에 반영)."""
    js = _read(SIDE_SHEET_JS)
    assert "resolveSheetUrl(orderId, row)" in js
    assert "function load(orderId, url)" in js
    assert "load(orderId, sheetUrl)" in js


def test_side_sheet_cachebuster_bumped_to_20260713a() -> None:
    """side-sheet.js ?v 가 20260713a 로 범프(본 워커 수행 1건)."""
    html = _read(LAYOUT_SCRIPTS)
    assert "tablet-side-sheet.js') }}?v=20260713c" in html
    assert "tablet-side-sheet.js') }}?v=20260712b" not in html


# =====================================================================
# B. 공용 밀도 토글
# =====================================================================


def test_density_toggle_js_exists_singleton_delegated_localstorage() -> None:
    js = _read(DENSITY_JS)
    assert "window.__FOMS_DENSITY_TOGGLE_BOUND" in js, "싱글턴 가드 부재(perf G4)"
    assert 'document.addEventListener("click"' in js, "document 위임 부재"
    assert "foms_tablet_density" in js, "localStorage 키 부재"
    assert 'setAttribute("data-foms-density"' in js, "대상에 밀도 속성 미부착"
    assert "foms:erp-shell-fragment-swapped" in js, "스왑 후 재적용 리스너 부재"


def test_density_toggle_wired_in_layout_scripts_deferred() -> None:
    html = _read(LAYOUT_SCRIPTS)
    m = re.search(r"<script[^>]*tablet-density-toggle\.js[^>]*>", html)
    assert m is not None, "tablet-density-toggle.js not wired in layout_scripts.html"
    tag = m.group(0)
    assert "defer" in tag, "density-toggle script must be defer (perf G1)"
    assert "?v=20260713a" in tag, "density-toggle script must carry ?v=20260713a"


def test_density_toggle_partial_exists_with_three_buttons() -> None:
    body = _read(DENSITY_PARTIAL)
    assert 'class="foms-density-toggle"' in body
    assert "data-density-target=" in body
    for level in ("40", "48", "56"):
        assert 'data-density="%s"' % level in body, f"missing density button: {level}"


def test_density_css_base_hide_before_optin_and_token_driven() -> None:
    """base-hide(.foms-density-toggle{display:none})가 opt-in(display:inline-flex) 앞(순서 계약).
    토글 표시는 coarse landscape 코호트 게이트, 터치 타깃은 comfortable(44px) 토큰 구동."""
    css = _norm(_read(LANDSCAPE_CSS))
    base_idx = css.index(".foms-density-toggle { display: none")
    optin_idx = css.index(
        "body.erp-mobile-v2-layout .foms-density-toggle { display: inline-flex"
    )
    assert base_idx < optin_idx, "base-hide 규칙이 opt-in 뒤(순서 계약 위반)"
    assert CORE_MEDIA_QUERY in css
    assert "body.erp-mobile-v2-layout .foms-density-toggle { display: inline-flex" in css
    assert "var(--foms-touch-target-comfortable)" in css


def test_density_css_row_height_overrides_dashboard_and_history() -> None:
    """40/56 만 baseline 을 이기는 특이도로 재정의(48=baseline 유지). 대시보드 그리드 +
    이력 테이블 두 표면 커버."""
    css = _norm(_read(LANDSCAPE_CSS))
    assert (
        '#erp-grid[data-foms-density="40"] tbody tr.erp-main-row { height: 40px' in css
    )
    assert (
        '#erp-grid[data-foms-density="56"] tbody tr.erp-main-row { height: 56px' in css
    )
    assert (
        '.erp-history-mobile-shell[data-foms-density="40"] '
        "tr.history-main-row[data-order-id] { height: 40px" in css
    )


def test_density_toggle_placed_in_dashboard_pcbar() -> None:
    body = _read(DASHBOARD_GRID)
    assert "partials/shared/foms_density_toggle.html" in body
    assert "set foms_density_target = '#erp-grid'" in body
    # 기존 "폭 초기화" 버튼과 같은 pcbar.
    assert "erp-grid-reset-column-widths" in body


def test_density_toggle_placed_in_history_table_top() -> None:
    body = _read(HISTORY_BODY)
    assert "partials/shared/foms_density_toggle.html" in body
    assert "set foms_density_target = '.erp-history-mobile-shell'" in body


# =====================================================================
# C. 대시보드(01) 시트 목업화
# =====================================================================


def test_dashboard_sheet_route_exists_reuses_display_dto() -> None:
    """fragment 라우트 존재 + 대시보드 표시 DTO/첨부 리졸버 재사용 + no-store fragment 헤더."""
    route = _read(DASHBOARD_ROUTE)
    assert "def erp_dashboard_tablet_sheet" in route
    assert "/dashboard/tablet-sheet/<int:order_id>" in route
    assert "build_orders_row_dtos" in route, "표시 DTO 재사용 아님"
    assert "batch_resolve_queue_attachment_preview_items" in route, "첨부 리졸버 재사용 아님"
    assert "tablet_dashboard_sheet.html" in route
    assert 'X-FOMS-Fragment' in route


def test_grid_row_carries_sheet_url_to_dashboard_sheet_route() -> None:
    """그리드 행이 data-foms-sheet-url 로 목업 라우트를 가리킨다(A 계약의 대시보드 소비처).
    파이프라인 소스(data-stage) 및 order-id 소스는 보존(회귀 금지)."""
    body = _read(DASHBOARD_GRID)
    assert (
        'data-foms-sheet-url="{{ url_for(\'erp_dashboard.erp_dashboard_tablet_sheet\''
        in body
    )
    # 파이프라인/시트 트리거 소스 보존.
    assert (
        'class="erp-main-row" data-order-id="{{ o.id }}" data-stage="{{ o.stage_code }}"'
        in body
    )


def test_dashboard_sheet_template_has_mockup_composition() -> None:
    """목업 구성: m-head(고객+단계배지+#id)·mini-quest·요약카드·첨부 스트립·m-foot."""
    body = _read(SHEET_TEMPLATE)
    # m-head + m-count.
    assert "foms-tsheet-head" in body
    assert "foms-tsheet-head__count" in body
    assert "#{{ o.id }}" in body
    assert "o.stage_badge_label" in body
    # mini-quest.
    assert "foms-tsheet-quest" in body
    assert "다음 할 일" in body
    # 요약 카드 필드.
    for label in ("연락처", "현장 주소", "제품", "실측 일정", "시공 일정"):
        assert label in body, f"missing summary field: {label}"
    # 첨부 스트립(60×46) + 기존 프리뷰 리졸버/모달 재사용.
    assert "foms-tsheet-attach-thumb" in body
    assert "erp-btn-attachments-preview" in body


def test_dashboard_sheet_footer_actions_wired() -> None:
    """m-foot: 전화(tel:) · ERP 편집(edit 이동) · 퀘스트 승인(기존 승인 API 위임 클래스)."""
    body = _read(SHEET_TEMPLATE)
    assert "tel:" in body, "전화 tel: 링크 부재"
    assert "order_edit.edit_order" in body, "ERP 편집 이동 부재"
    # 퀘스트 승인 = 기존 document.body 위임 클래스 재사용(신규 API 없음).
    assert "erp-btn-approve-team" in body
    assert "erp-btn-approve-assignee" in body


def test_dashboard_sheet_thumb_is_60x46() -> None:
    """썸네일 스트립 카드는 60×46(목업 스펙)."""
    css = _norm(_read(LANDSCAPE_CSS))
    m = re.search(r"\.foms-tsheet-attach-thumb \{[^}]*\}", css)
    assert m is not None, "foms-tsheet-attach-thumb 규칙 부재"
    assert "width: 60px" in m.group(0)
    assert "height: 46px" in m.group(0)
