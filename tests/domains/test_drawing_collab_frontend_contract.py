"""도면 협업 수정 — 프론트(F절) 계약 테스트 (2026-07-22).

정적 파일/템플릿 계약 (문자열 부분일치, whitespace-exact 블록 미잠금):
  - erp-dashboard-detail-dom.js : ERP 도면탭 CONFIRMED 축약 분기(수정 요청 진입로).
  - erp-dashboard-entry.js / layout_scripts.html : 내용 변경 캐스케이드 ?v 범프(SW 스테일 봉합).
  - workbench_dashboard_body.html : "컨펌 포함" 토글 + "담당 미지정" 배지.
  - workbench_dashboard_styles.html : 담당 미지정 배지 스타일(인라인 스타일 금지 — partial 블록).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DETAIL_DOM = "static/js/orders/dashboard/erp-dashboard-detail-dom.js"
ENTRY_JS = "static/js/orders/erp-dashboard-entry.js"
LAYOUT_SCRIPTS = "templates/partials/shared/layout_scripts.html"
WB_BODY = "templates/drawing/partials/workbench_dashboard_body.html"
WB_STYLES = "templates/drawing/partials/workbench_dashboard_styles.html"


def _read(rel: str) -> str:
    """Return the UTF-8 text of a repo-relative file."""
    return (ROOT / rel).read_text(encoding="utf-8")


def test_detail_dom_confirmed_revision_entrypoint() -> None:
    """ERP 도면탭: CONFIRM 단계 + drawing_status CONFIRMED 축약 분기 — "도면 완료" 라벨 +
    기존 openRevisionRequestModal 재사용(영업측 노출 조건)."""
    js = _read(DETAIL_DOM)
    assert "stage === 'CONFIRM'" in js
    assert "(sd.drawing_status || '') === 'CONFIRMED'" in js
    assert "도면 완료" in js
    # 수정 요청 버튼 = 기존 모달 재사용(신규 API 없음).
    assert "openRevisionRequestModal(' + orderId + ')" in js


def test_detail_dom_cachebuster_cascade_bumped() -> None:
    """내용 변경 시 로드 전수 ?v 범프(SW staticCacheFirst 스테일 봉합): detail-dom 자식 +
    entry 부모 둘 다 20260722a."""
    entry = _read(ENTRY_JS)
    layout = _read(LAYOUT_SCRIPTS)
    assert "erp-dashboard-detail-dom.js?v=20260722a" in entry
    assert "erp-dashboard-entry.js') }}?v=20260722a" in layout


def test_workbench_include_confirmed_toggle() -> None:
    """워크벤치 필터: "컨펌 포함" 토글 — include_confirmed=1 쿼리 왕복(기존 auto-submit 문법)."""
    body = _read(WB_BODY)
    assert 'name="include_confirmed"' in body
    assert "컨펌 포함" in body
    assert "auto-submit-checkbox" in body  # 기존 토글 문법 재사용


def test_workbench_unassigned_badge() -> None:
    """워크벤치 목록: r.no_assignee → "담당 미지정" 배지(danger 톤, partial 스타일 블록)."""
    body = _read(WB_BODY)
    styles = _read(WB_STYLES)
    assert "r.no_assignee" in body
    assert "dw-order-unassigned-badge" in body
    assert "담당 미지정" in body
    # 인라인 스타일 금지 — 스타일은 partial 블록에 정의.
    assert ".dw-order-unassigned-badge" in styles
