"""W-DRAWING 프레임 03 태블릿 도면 작업실 계약 (2026-07-13).

목업 v8 프레임 03 인벤토리를 잠근다: 상단 바(제목·N건·크기 토글·일괄 배정·마법사) +
필터 바(정렬·D-3·전달 대기·검색·초기화) + KPI 타일 4 + 시트 썸네일 카드 갤러리 +
관리 시트 fragment(썸네일 스트립·자동 채움·버전 이력·시트 전달/마법사 열기).

정적 파일 계약(파일 읽기)만으로 앱 부팅 없이 회귀를 잡는다. 기존 W-DRAWING 계약
(test_tablet_t2_contract.py)이 갤러리 기본형을 잠그고, 이 파일이 프레임 03 확장을 잠근다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GALLERY_PARTIAL = "templates/drawing/partials/tablet_gallery_body.html"
SHEET_PARTIAL = "templates/drawing/partials/tablet_sheet_body.html"
GALLERY_CSS = "static/css/foundation/foms-tablet-drawing-gallery.css"
GALLERY_JS = "static/js/foms/tablet-drawing-gallery.js"
SHEET_ROUTE = "foms/web/drawing/tablet_sheet.py"
DRAWING_INIT = "foms/web/drawing/__init__.py"
WORKBENCH = "foms/web/drawing/workbench.py"

CORE_MEDIA_QUERY = (
    "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- 상단 바 -----------------------------------------------------------------


def test_workshop_top_bar_has_title_count_sizes_bulk_wizard() -> None:
    body = _read(GALLERY_PARTIAL)
    assert "foms-drawing-workshop" in body
    assert "도면 작업실" in body
    assert "total_count" in body or "rows|length" in body  # sub "N건"
    assert "건</span>" in body
    # 크기 토글 3단.
    for size in ("sm", "md", "lg"):
        assert f'data-foms-gallery-size="{size}"' in body, f"missing size toggle: {size}"
    for label in ("작게", "보통", "크게"):
        assert label in body, f"missing size label: {label}"
    # 일괄 배정(ghost) + 마법사(pri).
    assert "data-foms-drawing-bulk-assign" in body
    assert "도면공 일괄 배정" in body
    assert "erp_drawing_workbench.erp_drawing_workbench_wizard" in body
    assert "도면 마법사" in body


# --- 필터 바 -----------------------------------------------------------------


def test_workshop_filter_bar_sort_dday3_pending_search_reset() -> None:
    body = _read(GALLERY_PARTIAL)
    assert 'name="sort"' in body
    assert "시공일 임박순" in body
    assert 'value="schedule"' in body
    assert 'name="dday3"' in body
    assert "D-3 이내만" in body
    assert 'name="pending"' in body
    assert "전달 대기만" in body
    assert 'name="q"' in body
    assert "초기화" in body


# --- KPI 타일 4 --------------------------------------------------------------


def test_workshop_kpi_tiles_four_with_stats_fields() -> None:
    body = _read(GALLERY_PARTIAL)
    assert "foms-drawing-workshop__kpis" in body
    assert body.count("foms-drawing-kpi__value") == 4, "KPI 타일은 정확히 4개여야 함"
    for token in ("stats.total", "stats.d3", "stats.pending_transfer", "stats.RETURNED"):
        assert token in body, f"missing KPI stat: {token}"
    for label in ("전체", "D-3 이내", "전달 대기", "수정 요청"):
        assert label in body, f"missing KPI label: {label}"


# --- 갤러리 카드 확장 --------------------------------------------------------


def test_gallery_card_carries_sheet_url_and_order_id() -> None:
    body = _read(GALLERY_PARTIAL)
    # 시트 인터페이스 계약: data-foms-sheet-url + data-order-id (side-sheet 로 로드).
    assert 'data-foms-sheet-url="{{ url_for(' in body
    assert "erp_drawing_workbench.erp_drawing_workbench_tablet_sheet" in body
    assert 'data-order-id="{{ r.id }}"' in body
    # 상세 앵커(비-코호트/무 JS fallback) 보존.
    assert "erp_drawing_workbench.erp_drawing_workbench_detail" in body
    assert "tab=timeline" in body
    # tlabel "시트N·상태".
    assert "시트 {{ r.file_count }} · {{ r.drawing_status_label }}" in body
    # 전달완료 dim.
    assert "is-dim" in body
    assert "'TRANSFERRED', 'CONFIRMED'" in body
    # 다음 페이지 카드.
    assert "foms-drawing-gallery-card--more" in body
    assert "다음 페이지" in body
    assert "pagination.total_count" in body


def test_gallery_wires_workshop_js_deferred_with_cachebuster() -> None:
    body = _read(GALLERY_PARTIAL)
    m = re.search(r"<script[^>]*tablet-drawing-gallery\.js[^>]*>", body)
    assert m is not None, "tablet-drawing-gallery.js not wired in gallery partial"
    tag = m.group(0)
    assert "defer" in tag, "gallery script must be defer (perf G1)"
    assert "?v=20260713a" in tag, "new file must carry ?v=20260713a"


# --- 관리 시트 fragment ------------------------------------------------------


def test_sheet_fragment_has_head_three_cards_and_foot() -> None:
    body = _read(SHEET_PARTIAL)
    assert "foms-drawing-sheet" in body
    # m-head 고객명 + m-count(#id · 시공) + 원 주문 링크.
    assert "customer_name" in body
    assert "#{{ order_id }}" in body
    assert "construction_md" in body
    assert "원 주문 열기" in body
    # 카드 3: 시트 N·PNG 자동 저장 / 자동 채움(시공일·자수·로고) / 버전 이력.
    assert "PNG 자동 저장" in body
    assert "sheet_count" in body and "sheet_strip" in body
    assert "자동 채움" in body
    for fill in ("시공일", "자수", "로고"):
        assert fill in body, f"missing autofill field: {fill}"
    assert "버전 이력" in body
    assert "timeline" in body
    # m-foot: 시트 전달 + 마법사 열기 ↗.
    assert "data-foms-drawing-transfer" in body
    assert "시트 전달" in body
    assert "마법사 열기" in body
    assert "wizard_url" in body


# --- 관리 시트 라우트 --------------------------------------------------------


def test_sheet_route_registered_and_reuses_wizard_state() -> None:
    route = _read(SHEET_ROUTE)
    assert "@erp_drawing_workbench_bp.route('/drawing-workbench/tablet-sheet/<int:order_id>')" in route
    assert "def erp_drawing_workbench_tablet_sheet" in route
    # 신규 스키마 금지 — 마법사 상태·자동채움 SSOT 재사용.
    assert "_pending_list" in route
    assert "build_wizard_defaults" in route
    assert "drawing/partials/tablet_sheet_body.html" in route
    # 모듈이 __init__ 에서 import 되어 라우트가 등록된다.
    init = _read(DRAWING_INIT)
    assert "from foms.web.drawing import tablet_sheet" in init


# --- 워크벤치 라우트 집계/필터/정렬 확장 (서버 무신규 스키마) ----------------


def test_workbench_route_adds_dday_aggregation_filters_and_sort() -> None:
    route = _read(WORKBENCH)
    # 행 파생 필드.
    assert "'construction_days': alerts.get('construction_days')" in route
    assert "'construction_d3': bool(alerts.get('construction_d3'))" in route
    assert "'product_summary': product_summary" in route
    # KPI 집계.
    assert "stats['d3']" in route
    assert "stats['pending_transfer']" in route
    # 쿼리스트링 필터.
    assert "dday3_only" in route
    assert "pending_only" in route
    # 시공일 임박순 정렬.
    assert "sort_by == 'schedule'" in route


# --- JS 계약 ----------------------------------------------------------------


def test_gallery_js_singleton_size_toggle_bulk_and_transfer() -> None:
    js = _read(GALLERY_JS)
    assert "window.__FOMS_DRAWING_GALLERY_BOUND" in js  # 싱글턴 가드(perf G4)
    # 크기 토글 + 지속.
    assert "data-foms-gallery-size" in js
    assert "localStorage" in js
    assert "is-size-" in js
    # 일괄 배정 = 기존 벌크 UI 재사용.
    assert "openBatchAssignModal" in js
    assert "data-foms-drawing-bulk-assign" in js
    # 시트 전달 = 기존 transfer-pending API.
    assert "data-foms-drawing-transfer" in js
    assert "/drawing-wizard/transfer-pending" in js
    # fragment swap 재적용.
    assert "foms:erp-shell-fragment-swapped" in js


# --- CSS 계약 (배타·크기 3단·landscape 전용) --------------------------------


def test_gallery_css_workshop_shell_size_variants_and_landscape_only() -> None:
    css = _norm(_read(GALLERY_CSS))
    # 셸 기본 은닉(코호트 opt-in 앞) — blank 금지 순서 계약.
    base_idx = css.index(".foms-drawing-workshop { display: none")
    show_idx = css.index("body.erp-mobile-v2-layout .foms-drawing-workshop { display: flex")
    assert base_idx < show_idx, "작업실 셸 base-hide 가 opt-in 뒤에 있음(순서 계약 위반)"
    assert CORE_MEDIA_QUERY in css
    # 크기 3단 (220/260/320).
    assert ".foms-drawing-gallery.is-size-sm { grid-template-columns: repeat(auto-fill, minmax(220px" in css
    assert ".foms-drawing-gallery.is-size-md { grid-template-columns: repeat(auto-fill, minmax(260px" in css
    assert ".foms-drawing-gallery.is-size-lg { grid-template-columns: repeat(auto-fill, minmax(320px" in css
    # KPI + 시트 썸네일 120×84.
    assert "grid-template-columns: repeat(4, 1fr)" in css
    assert "width: 120px" in css
    assert "height: 84px" in css
    # landscape 전용(portrait 토큰 금지, split-view 가드 정합).
    assert "orientation: portrait" not in css
