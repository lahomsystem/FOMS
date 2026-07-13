"""출고 대시보드 태블릿 가로(목업 06) 컬럼 게이트 계약.

코호트 태블릿 가로(body.erp-mobile-v2-layout + coarse landscape ≥992)에서:
  - 저우선 열(상세·현장주소·시공자·담당자)은 col/th/td data-col-key 로 자동 숨김.
  - 자수(규격 W/300)는 우측 정렬 + tabular-nums.
  - 시공팀 파스텔 색은 전체 행 배경으로 승격(시공자 열 숨김 보상).
  - 시간(시공시간)·고객·발주사·제품·자수·도면담당 6열은 유지(목업 06).
  - 숨긴 현장주소는 배정 시트에서 접근 가능.
PC(fine)·폰·세로 무회귀 = 전 규칙이 코호트 body 클래스 + 코어 MQ 게이트 안.
문자열 부분일치로 잠그되 whitespace-exact 블록은 잠그지 않는다(resilient).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

COLUMNS_CSS = "static/css/contexts/shipment/shipment-dashboard-columns.css"
DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
TABLET_SHEET = "templates/shipment/partials/tablet_sheet.html"

CORE_MEDIA_QUERY = (
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)
HIDDEN_KEYS = ("detail", "address", "construction_workers", "manager")


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --- (1) CSS 게이트 + 저우선 열 은닉 -----------------------------------------


def test_tablet_gate_uses_core_cohort_media_query() -> None:
    """코어 코호트 MQ(coarse landscape ≥992)로 게이트한다."""
    css = _read(COLUMNS_CSS)
    assert CORE_MEDIA_QUERY in css


def test_low_priority_columns_hidden_by_data_col_key() -> None:
    """저우선 열(상세·현장주소·시공자·담당자)의 th/td 가 display:none.
    컬럼 인덱스가 아니라 data-col-key(콜그룹 SSOT)로 지목한다."""
    css = _norm(_read(COLUMNS_CSS))
    for key in HIDDEN_KEYS:
        assert f'th[data-col-key="{key}"]' in css, f"th 숨김 미지정: {key}"
        assert f'td[data-col-key="{key}"]' in css, f"td 숨김 미지정: {key}"
    # 게이트 body 클래스 스코프(코호트 한정 → PC/폰 무영향).
    assert "body.erp-mobile-v2-layout #shipment-dashboard-table" in css
    assert "display: none;" in css


def test_hidden_columns_reclaim_col_width() -> None:
    """숨긴 열의 col 인라인 폭(JS SSOT)을 !important 로 0 회수(빈칸 방지)."""
    css = _norm(_read(COLUMNS_CSS))
    for key in HIDDEN_KEYS:
        assert f'colgroup col[data-col-key="{key}"]' in css, f"col 폭 회수 미지정: {key}"
    assert "width: 0 !important;" in css


def test_construction_time_column_is_kept_visible() -> None:
    """시간(시공시간)은 목업 06 가시 6열 → 숨김/회수 규칙 대상이 아니어야 한다."""
    css = _read(COLUMNS_CSS)
    assert 'col[data-col-key="construction_time"]' not in css
    assert 'td[data-col-key="construction_time"]' not in css


def test_spec_column_right_aligned_tabular_nums() -> None:
    """자수(규격 W/300) 우측 정렬 + tabular-nums."""
    css = _norm(_read(COLUMNS_CSS))
    assert 'th[data-col-key="spec"]' in css
    assert 'td[data-col-key="spec"]' in css
    assert "text-align: right;" in css
    assert "font-variant-numeric: tabular-nums;" in css


def test_pastel_team_group_promoted_to_row() -> None:
    """시공자 열 숨김 보상 — 팀 파스텔을 행 배경으로 승격(data-team-color-index)."""
    css = _norm(_read(COLUMNS_CSS))
    assert 'tr[data-team-color-index="0"]' in css
    assert 'tr[data-team-color-index="9"]' in css
    # 팔레트 SSOT 정합(템플릿/JS pastel_colors 첫·끝 값).
    assert "#B8D4E3" in css
    assert "#E9E5D5" in css


def test_touch_row_height_present() -> None:
    """데이터 행 ≥48px 터치 타깃 보정."""
    css = _norm(_read(COLUMNS_CSS))
    assert "tbody tr.shipment-row" in css
    assert "--foms-touch-target-min" in css


# --- (2) 템플릿 마크업 계약 ---------------------------------------------------


def test_dashboard_main_tr_carries_team_color_index() -> None:
    """본행 tr 이 파스텔 인덱스(ns.worker_index)를 data 속성으로 노출."""
    html = _read(DASHBOARD_MAIN)
    assert 'data-team-color-index="{{ ns.worker_index }}"' in html


def test_dashboard_main_cells_carry_data_col_key() -> None:
    """저우선 열 + 자수 td 가 data-col-key 를 달아 CSS 지목을 가능케 한다."""
    html = _read(DASHBOARD_MAIN)
    for key in ("detail", "spec", "address", "construction_workers", "manager"):
        assert f'data-col-key="{key}"' in html, f"td data-col-key 미부착: {key}"


def test_dashboard_main_keeps_time_and_drawing_columns() -> None:
    """목업 06 가시열(시간·도면담당)의 헤더 data-col-key 는 유지된다."""
    html = _read(DASHBOARD_MAIN)
    assert 'data-col-key="construction_time"' in html
    assert 'data-col-key="drawing_managers"' in html


# --- (3) 숨긴 주소는 배정 시트에서 접근 가능 ----------------------------------


def test_tablet_sheet_exposes_site_address() -> None:
    """그리드에서 숨긴 현장주소를 배정 시트에서 노출(order.address)."""
    html = _read(TABLET_SHEET)
    assert "현장주소" in html
    assert "order.address" in html
