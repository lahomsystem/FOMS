"""출고 대시보드 태블릿 가로(목업 06) 클린 그리드 계약.

[지상 재구축 2026-07-14] 기존 "PC 테이블(#shipment-dashboard-table)을 CSS 로 6열만 접기"
방식은 실기기(iPad)에서 컬럼 순서·라벨 정합에 실패했다(CSS 로는 열 재정렬·input→plain 변환
불가). 이제 코호트 태블릿 가로(body.erp-mobile-v2-layout + coarse landscape ≥992)에서:
  - PC 테이블은 래퍼(.shipment-table-wrapper)째 은닉된다.
  - 목업 06 정합 클린 그리드(tablet_ship_grid.html · #foms-tablet-ship-grid)가 대체한다:
      컬럼(좌→우) = 시간 · 고객 · 발주사 · 제품 · 자수(우측정렬·tabular) · 도면담당.
  - 시공팀별 그룹 헤더(tr.foms-tablet-shipgrid__grp) = 좌 "시공 N팀 · 합계자수" / 우 잔여
    (미배정 = "배정 필요"). 팀 파스텔 틴트는 data-team-color-index SSOT 팔레트로 착색.
  - 행 탭 → 배정 시트: 신규 그리드는 id 가 달라 기존 tablet-side-sheet.js 의
    "#shipment-dashboard-table tbody tr" 셀렉터에 안 걸리므로, wrap 에 공용 클린-그리드 훅
    클래스 .foms-tablet-workqueue-wrap 를 병기해 ".foms-tablet-workqueue-wrap tr.erp-main-row
    [data-order-id]" 셀렉터를 만족시킨다(JS 무수정). 각 행 data-foms-sheet-url = 배정 fragment.
  - 숨긴 상세·현장주소·시공자는 배정 시트에서 접근 가능.
PC(fine)·폰·세로 무회귀 = 전 코호트 규칙이 body 클래스 + 코어 MQ 게이트 안.

[은퇴한 계약(과거 column-fold 방식 — 근거와 함께 이관)]
  - test_low_priority_columns_hidden_by_data_col_key → PC 테이블 래퍼 은닉으로 대체.
  - test_hidden_columns_reclaim_col_width → col 폭 회수 불필요(PC 테이블 자체 은닉).
  - test_spec_column_right_aligned_tabular_nums(data-col-key) → 클린 그리드 __num 으로 이관.
  - test_pastel_team_group_promoted_to_row(데이터 행 배경) → 그룹 헤더 틴트로 이관.
  - test_touch_row_height_present(tr.shipment-row) → 클린 그리드 __row 로 이관.
문자열 부분일치로 잠그되 whitespace-exact 블록은 잠그지 않는다(resilient).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

COLUMNS_CSS = "static/css/contexts/shipment/shipment-dashboard-columns.css"
DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
TABLET_GRID = "templates/shipment/partials/tablet_ship_grid.html"
TABLET_SHEET = "templates/shipment/partials/tablet_sheet.html"

CORE_MEDIA_QUERY = (
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- (1) CSS 게이트 + PC 테이블 은닉 / 클린 그리드 표시 -----------------------


def test_tablet_gate_uses_core_cohort_media_query() -> None:
    """코어 코호트 MQ(coarse landscape ≥992)로 게이트한다."""
    css = _read(COLUMNS_CSS)
    assert CORE_MEDIA_QUERY in css


def test_pc_table_wrapper_hidden_in_cohort() -> None:
    """[은퇴 대체] 저우선 열 개별 은닉 대신, 코호트에서 PC 테이블 래퍼째 은닉한다.
    body 클래스 스코프 + !important(Bootstrap .table-responsive 특이도 대비)."""
    css = _norm(_read(COLUMNS_CSS))
    assert "body.erp-mobile-v2-layout .erp-dashboard-shipment .shipment-table-wrapper" in css
    assert "display: none !important;" in css


def test_clean_grid_shown_in_cohort() -> None:
    """클린 그리드 wrap 은 base-hide → 코호트에서만 display:block(순서 계약 = base-hide 선행)."""
    css = _norm(_read(COLUMNS_CSS))
    assert ".foms-tablet-shipgrid-wrap { display: none; }" in css
    assert "body.erp-mobile-v2-layout .foms-tablet-shipgrid-wrap" in css
    assert "display: block;" in css


def test_no_data_col_key_gating_remains() -> None:
    """[은퇴] data-col-key 기반 열 은닉/폭 회수 규칙은 전부 제거되어야 한다
    (PC 테이블은 래퍼째 은닉 — 개별 열 CSS 게이트 불필요). 단 PC 리사이즈용 data-col-key
    마크업(dashboard_main.html)은 유지된다(별도 테스트)."""
    css = _read(COLUMNS_CSS)
    assert 'data-col-key="detail"' not in css
    assert 'data-col-key="address"' not in css
    assert 'data-col-key="spec"' not in css
    assert "width: 0 !important;" not in css


def test_num_column_right_aligned_tabular_nums() -> None:
    """[은퇴 이관] 자수 열 우측 정렬 + tabular-nums 를 클린 그리드 __num 으로 잠근다."""
    css = _norm(_read(COLUMNS_CSS))
    assert "#foms-tablet-ship-grid td.foms-tablet-shipgrid__num" in css
    assert "text-align: right;" in css
    assert "font-variant-numeric: tabular-nums;" in css


def test_group_header_team_pastel_tint() -> None:
    """[은퇴 이관] 팀 파스텔을 데이터 행이 아니라 그룹 헤더 틴트로 착색한다
    (data-team-color-index + SSOT 팔레트 첫·끝 값)."""
    css = _norm(_read(COLUMNS_CSS))
    assert '#foms-tablet-ship-grid tr[data-team-color-index="0"].foms-tablet-shipgrid__grp' in css
    assert '#foms-tablet-ship-grid tr[data-team-color-index="9"].foms-tablet-shipgrid__grp' in css
    # 미배정(-1) danger 틴트.
    assert 'tr[data-team-color-index="-1"].foms-tablet-shipgrid__grp' in css
    # 팔레트 SSOT 정합(템플릿/JS pastel_colors 첫·끝 값).
    assert "#B8D4E3" in css
    assert "#E9E5D5" in css


def test_clean_grid_row_touch_height() -> None:
    """[은퇴 이관] 데이터 행 ≥48px 터치 타깃을 클린 그리드 __row 로 잠근다."""
    css = _norm(_read(COLUMNS_CSS))
    assert "#foms-tablet-ship-grid tbody tr.foms-tablet-shipgrid__row" in css
    assert "--foms-touch-target-min" in css


def test_clean_grid_density_targets_40_and_56() -> None:
    """밀도 토글 40/56 이 클린 그리드 id 를 대상으로 재정의한다(48=baseline)."""
    css = _norm(_read(COLUMNS_CSS))
    assert '#foms-tablet-ship-grid[data-foms-density="40"] tbody tr.foms-tablet-shipgrid__row' in css
    assert '#foms-tablet-ship-grid[data-foms-density="56"] tbody tr.foms-tablet-shipgrid__row' in css


# --- (2) 클린 그리드 템플릿 마크업 계약 ---------------------------------------


def test_clean_grid_columns_order() -> None:
    """클린 그리드 헤더 = 목업 06 컬럼셋(시간·고객·발주사·제품·자수·도면담당)."""
    html = _read(TABLET_GRID)
    for label in ("시간", "고객", "발주사", "제품", "자수", "도면담당"):
        assert f">{label}<" in html, f"헤더 라벨 누락: {label}"


def test_clean_grid_row_sheet_tap_wiring() -> None:
    """행 탭 → 배정 시트: wrap 에 공용 훅 클래스 병기 + 행에 erp-main-row + data-foms-sheet-url
    (기존 tablet-side-sheet.js ROW_SELECTOR 재사용, JS 무수정)."""
    html = _read(TABLET_GRID)
    assert "foms-tablet-workqueue-wrap" in html
    assert "erp-main-row" in html
    assert "data-foms-sheet-url=" in html
    assert "erp_shipment_page.erp_shipment_tablet_sheet" in html


def test_clean_grid_num_and_customer_cells() -> None:
    """자수 셀 = __num(우측정렬 대상), 고객 셀 = __customer(굵게 대상)."""
    html = _read(TABLET_GRID)
    assert "foms-tablet-shipgrid__num" in html
    assert "foms-tablet-shipgrid__customer" in html


def test_clean_grid_group_header_carries_team_color_index() -> None:
    """그룹 헤더 tr 이 파스텔 인덱스(_wi.idx)를 data 속성으로 노출(CSS 틴트 지목)."""
    html = _read(TABLET_GRID)
    assert 'data-team-color-index="{{ _wi.idx }}"' in html
    # 미배정 그룹 우측 = "배정 필요".
    assert "배정 필요" in html


def test_clean_grid_group_sum_source_is_server_meta() -> None:
    """그룹 합계·잔여는 서버 준비 shipment_team_group_meta 를 재소비한다(신규 쿼리 0)."""
    html = _read(TABLET_GRID)
    assert "shipment_team_group_meta" in html


def test_density_toggle_targets_clean_grid() -> None:
    """밀도 토글 대상에 클린 그리드 id 가 포함(결합 셀렉터)."""
    html = _read(DASHBOARD_MAIN)
    assert "#foms-tablet-ship-grid" in html
    assert "foms_density_target" in html
    assert "tablet_ship_grid.html" in html  # 신규 partial include


# --- (3) PC 테이블 마크업은 PC(fine) 리사이즈용으로 유지 ----------------------


def test_dashboard_main_pc_table_keeps_data_col_key() -> None:
    """PC 테이블은 코호트에서 은닉되나 마크업은 유지 — PC(fine) 컬럼 리사이즈용 data-col-key
    (dashboard-columns.js SSOT)는 그대로 있어야 한다."""
    html = _read(DASHBOARD_MAIN)
    for key in ("detail", "spec", "address", "construction_workers", "manager"):
        assert f'data-col-key="{key}"' in html, f"PC 테이블 data-col-key 누락: {key}"
    assert 'data-col-key="construction_time"' in html
    assert 'data-col-key="drawing_managers"' in html


# --- (4) 숨긴 주소는 배정 시트에서 접근 가능 ----------------------------------


def test_tablet_sheet_exposes_site_address() -> None:
    """그리드에서 숨긴 현장주소를 배정 시트에서 노출(order.address)."""
    html = _read(TABLET_SHEET)
    assert "현장주소" in html
    assert "order.address" in html
