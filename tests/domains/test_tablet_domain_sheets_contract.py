"""T2 태블릿 도메인 시트 액션 계약 (목업 v8 마감 · 2026-11-27 옛 생산 칸반 몫 지움).

정적 파일/라우트 계약 (병렬 워커 3인 공유 인터페이스):
  - static/js/foms/tablet-domain-sheets.js : 시트 도메인 액션(생산 완료/출고 배정/취소) +
    생산 칸반 클라이언트 필터. 코호트 게이트·싱글턴·엔드포인트·필터 attr 고정.
  - 옛 생산 칸반 본문 · 옆 시트 · 칸반 필터 · 변경 브리핑 창 계약은 2026-11-27 옛 보드와 함께 지웠다
    (설계서 2026-11-27-production-legacy-board-removal §6-4). 생산 쪽 싣는 곳 = 첫 화면 · 작업 시트.
  - templates/shipment/partials/dashboard_main.html : 시트 URL source + 출고 KPI 스트립.
  - static/js/shipment/shipment-entry.js : 출고 쪽 도메인 시트 JS 를 entry CHAIN 으로 1회 로드(?v=).
    (2026-10-02 전엔 dashboard_scripts.html 의 defer 태그였다 — 파샬은 이제 entry 1개만.)
  - 라우트: erp_shipment_page.erp_shipment_tablet_sheet 등록(생산 옆 시트 라우트는 없다).

주의(병렬 작업): 템플릿/라우트 계약은 형제 워커(생산 칸반 · 출고 대시보드)가 랜딩해야
green 이 된다. 본 JS 계약(첫 테스트)은 이 워커 단독으로 통과해야 한다.
문자열 부분일치로 잠그되 whitespace-exact 블록은 잠그지 않는다(resilient).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DOMAIN_SHEETS_JS = "static/js/foms/tablet-domain-sheets.js"
SHIPMENT_DASHBOARD_MAIN = "templates/shipment/partials/dashboard_main.html"
SHIPMENT_DASHBOARD_SCRIPTS = "templates/shipment/partials/dashboard_scripts.html"
SHIPMENT_ENTRY_JS = "static/js/shipment/shipment-entry.js"

CORE_MEDIA_QUERY = (
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
)
# ADMIN-OVERRIDE-01: tablet-domain-sheets.js 에 관리자 강제 진행 재시도가 들어가
# 자산 핀을 올렸다. 핀 고정 계약은 새 핀을 따라간다(안 바꾼 자산의 핀은 안 올린다).
SCRIPT_CACHEBUSTER = "?v=20261128c"  # 11-28 c: 수정 제작 고르기 창 · 11-28 b: 보류 · 수정 제작 창 글 · 11-28 a: 확인 창 띄어쓰기 · 11-27: 옛 생산 칸반 몫(필터 · 숫자 타일 · 전체 화면 · 변경 브리핑 창)을 지웠다


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


def test_domain_sheets_js_wires_production_start_with_confirm() -> None:
    """제작 시작 액션 = 기존 /production/start 엔드포인트 재사용 + confirm 게이트.
    생산 완료도 confirm 게이트를 가진다(오조작 방지)."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "production-start" in js  # 시트 액션 위임 분기
    assert "/production/start" in js  # 기존 엔드포인트 재사용
    assert "제작을 시작할까요?" in js  # 시작 confirm
    assert "제작을 완료할까요?" in js  # 완료 confirm


def test_domain_sheets_js_wires_production_cancel_and_uncomplete() -> None:
    """되돌리기 2종(시트 전용): 제작 취소 = /production/cancel, 완료 취소 =
    /production/uncomplete. 위임 액션명·엔드포인트·문구 고정.

    묻는 문장은 그대로 두되 창만 바뀌었다 — 제작 취소는 사유를 받아야 해서
    window.confirm 대신 공용 사유 시트의 제목으로 같은 문장을 띄운다(2026-09-20).
    """
    js = _read(DOMAIN_SHEETS_JS)
    assert "production-cancel" in js  # 시트 액션 위임 분기
    assert "/production/cancel" in js  # 신규 되돌리기 엔드포인트
    assert "제작을 취소하고 제작 대기로 되돌릴까요" in js  # 취소 confirm
    assert "production-uncomplete" in js
    assert "/production/uncomplete" in js
    assert "완료를 취소하고 제작 중으로 되돌릴까요" in js  # 완료 취소 confirm


def test_domain_sheets_js_wires_hold_release_confirm() -> None:
    """보류 해제 경로 = confirm 게이트(오조작 방지) + 서버 렌더 사유(data-hold-reason) 병기.
    설정(prompt) 경로는 현행 유지."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "보류를 해제할까요" in js  # 해제 confirm 문구
    assert "data-hold-reason" in js  # 사유는 버튼 인접 DOM 아닌 서버 렌더 데이터에서 읽음


def test_domain_sheets_js_is_vanilla_no_jquery() -> None:
    """jQuery 금지(vanilla querySelector/fetch만) — '$(' 부재."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "$(" not in js


# --- (2) 생산 칸반 body: 시트 URL + JS include + 필터 attr + KPI (형제 대기) ----


# --- (3) 출고 대시보드: 시트 URL + KPI 스트립 + JS include (형제 대기) ----------


def test_shipment_dashboard_main_has_sheet_source_and_kpis() -> None:
    """출고 대시보드 main 이 시트 URL source + 위 줄 요약을 노출한다.
    (2026-11-11 설계서 tablet-production-ui §14.3: KPI 네 칸 → "N건" + "시공자 없음 n" 알약. 시트 URL 은
    하루치 출고표 파샬 tablet_ship_grid.html 의 줄이 싣는다.)"""
    body = _read(SHIPMENT_DASHBOARD_MAIN)
    assert "tablet_ship_grid.html" in body
    assert "data-foms-sheet-url" in _read("templates/shipment/partials/tablet_ship_grid.html")
    assert "foms-ship-pcbar__miss" in body
    assert "tablet-ship-kpis" not in body


def test_shipment_dashboard_scripts_wires_domain_sheets_deferred() -> None:
    """출고 대시보드는 도메인 시트 JS 를 shipment-entry.js CHAIN 으로 ?v 붙여 1회 로드한다.

    파샬(dashboard_scripts.html)에는 entry(defer) 1개만 둔다 — 동적 삽입이라 렌더를 막지 않고(G1),
    셸 스왑마다 다시 실행되지 않는다(fragment-multi-script)."""
    html = _read(SHIPMENT_DASHBOARD_SCRIPTS)
    assert "js/foms/tablet-domain-sheets.js" not in html, "도메인 시트는 entry CHAIN 이 싣는다"
    entry_tag = _script_tag(html, "js/shipment/shipment-entry.js")
    assert "defer" in entry_tag, "출고 entry 스크립트 defer 부재(perf G1)"
    entry = _read(SHIPMENT_ENTRY_JS)
    assert "'/static/js/foms/tablet-domain-sheets.js" + SCRIPT_CACHEBUSTER + "'" in entry, (
        "entry CHAIN 에 도메인 시트(?v 캐시버스터 포함)가 없다"
    )


# --- (4) 라우트 등록 (형제 대기) ----------------------------------------------


def test_domain_sheet_routes_registered(app) -> None:
    """생산/출고 태블릿 시트 라우트가 app.url_map 에 등록된다.
    (형제 워커: 생산 칸반 + 출고 대시보드 — 랜딩 전까지 pending.)"""
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "erp_production_page.erp_production_tablet_sheet" not in endpoints, (
        "생산 옆 시트 라우트는 2026-11-27 옛 보드와 함께 지웠다"
    )
    assert "erp_shipment_page.erp_shipment_tablet_sheet" in endpoints, (
        "출고 태블릿 시트 라우트 미등록"
    )
