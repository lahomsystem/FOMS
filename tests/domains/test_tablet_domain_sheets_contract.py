"""T2 태블릿 도메인 시트 액션 + 생산 칸반 필터 계약 (목업 v8 마감).

정적 파일/라우트 계약 (병렬 워커 3인 공유 인터페이스):
  - static/js/foms/tablet-domain-sheets.js : 시트 도메인 액션(생산 완료/출고 배정/취소) +
    생산 칸반 클라이언트 필터. 코호트 게이트·싱글턴·엔드포인트·필터 attr 고정.
  - templates/production/partials/tablet_kanban_body.html : 시트 URL soruce + 도메인 시트 JS
    include(defer/?v=) + 필터 바 attr + KPI 타일 클래스.
  - templates/shipment/partials/dashboard_main.html : 시트 URL source + 출고 KPI 스트립.
  - templates/shipment/partials/dashboard_scripts.html : 도메인 시트 JS include(defer/?v=).
  - 라우트: erp_production_page.erp_production_tablet_sheet /
            erp_shipment_page.erp_shipment_tablet_sheet 등록.

주의(병렬 작업): 템플릿/라우트 계약은 형제 워커(생산 칸반 · 출고 대시보드)가 랜딩해야
green 이 된다. 본 JS 계약(첫 테스트)은 이 워커 단독으로 통과해야 한다.
문자열 부분일치로 잠그되 whitespace-exact 블록은 잠그지 않는다(resilient).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOMAIN_SHEETS_JS = "static/js/foms/tablet-domain-sheets.js"
KANBAN_BODY = "templates/production/partials/tablet_kanban_body.html"
SHIPMENT_DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
SHIPMENT_DASHBOARD_SCRIPTS = "templates/shipment/partials/dashboard_scripts.html"

CORE_MEDIA_QUERY = (
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)
SCRIPT_CACHEBUSTER = "?v=20260713a"


def _read(rel: str) -> str:
    """Return the UTF-8 text of a repo-relative file."""
    return (ROOT / rel).read_text(encoding="utf-8")


def _script_tag(html: str, filename: str) -> str:
    """Return the <script ...> open tag that references *filename*."""
    m = re.search(r"<script[^>]*" + re.escape(filename) + r"[^>]*>", html)
    assert m is not None, f"{filename} not wired via <script> tag (searched: {html[:120]!r})"
    return m.group(0)


# --- (1) JS: 코호트 게이트 · 싱글턴 · 엔드포인트 · 필터 attr · no-jQuery --------


def test_domain_sheets_js_exists_with_singleton_and_cohort_gate() -> None:
    """싱글턴 가드(perf G4) + 코어 코호트 MQ + CSS 마커 소비(--foms-tablet-ui)."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "__FOMS_DOMAIN_SHEETS_BOUND" in js
    assert CORE_MEDIA_QUERY in js
    assert "--foms-tablet-ui" in js


def test_domain_sheets_js_reuses_existing_domain_endpoints() -> None:
    """신규 API 없이 기존 생산 완료 / 출고 update 엔드포인트 재사용."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "data-tablet-sheet-action" in js
    assert "/production/complete" in js
    assert "/api/erp/shipment/update/" in js
    assert "credentials" in js  # same-origin 자격증명 전송
    assert ".foms-tablet-sheet__close" in js  # 표준 닫기 경로 재사용


def test_domain_sheets_js_has_production_kanban_filter() -> None:
    """생산 칸반 클라이언트 필터 컨트롤 attr 계약."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "data-tablet-prod-search" in js


def test_domain_sheets_js_is_vanilla_no_jquery() -> None:
    """jQuery 금지(vanilla querySelector/fetch만) — '$(' 부재."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "$(" not in js


# --- (2) 생산 칸반 body: 시트 URL + JS include + 필터 attr + KPI (형제 대기) ----


def test_kanban_body_wires_domain_sheets_and_filter() -> None:
    """생산 칸반 body 가 시트 URL source + 도메인 시트 JS(defer/?v=) + 필터 바 attr +
    KPI 타일 클래스를 배선한다. (형제 워커: 생산 칸반 — 랜딩 전까지 pending.)"""
    body = _read(KANBAN_BODY)
    assert "data-foms-sheet-url" in body
    tag = _script_tag(body, "js/foms/tablet-domain-sheets.js")
    assert SCRIPT_CACHEBUSTER in tag, "도메인 시트 스크립트 ?v 캐시버스터 부재"
    assert "defer" in tag, "도메인 시트 스크립트 defer 부재(perf G1)"
    for attr in (
        "data-tablet-prod-search",
        "data-tablet-prod-status",
        "data-tablet-prod-factory",
        "data-tablet-prod-reset",
    ):
        assert attr in body, f"필터 바 attr 부재: {attr}"
    assert "erp-pro-alert" in body, "KPI 경보 타일 클래스 부재"


# --- (3) 출고 대시보드: 시트 URL + KPI 스트립 + JS include (형제 대기) ----------


def test_shipment_dashboard_main_has_sheet_source_and_kpis() -> None:
    """출고 대시보드 main 이 시트 URL source + 출고 KPI 스트립을 노출한다.
    (형제 워커: 출고 대시보드 — 랜딩 전까지 pending.)"""
    body = _read(SHIPMENT_DASHBOARD_MAIN)
    assert "data-foms-sheet-url" in body
    assert "tablet-ship-kpis" in body


def test_shipment_dashboard_scripts_wires_domain_sheets_deferred() -> None:
    """출고 대시보드 scripts 가 도메인 시트 JS 를 defer + ?v 로 로드한다.
    (형제 워커: 출고 대시보드 — 랜딩 전까지 pending.)"""
    html = _read(SHIPMENT_DASHBOARD_SCRIPTS)
    tag = _script_tag(html, "js/foms/tablet-domain-sheets.js")
    assert SCRIPT_CACHEBUSTER in tag, "도메인 시트 스크립트 ?v 캐시버스터 부재"
    assert "defer" in tag, "도메인 시트 스크립트 defer 부재(perf G1)"


# --- (4) 라우트 등록 (형제 대기) ----------------------------------------------


def test_domain_sheet_routes_registered(app) -> None:
    """생산/출고 태블릿 시트 라우트가 app.url_map 에 등록된다.
    (형제 워커: 생산 칸반 + 출고 대시보드 — 랜딩 전까지 pending.)"""
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "erp_production_page.erp_production_tablet_sheet" in endpoints, (
        "생산 태블릿 시트 라우트 미등록"
    )
    assert "erp_shipment_page.erp_shipment_tablet_sheet" in endpoints, (
        "출고 태블릿 시트 라우트 미등록"
    )
