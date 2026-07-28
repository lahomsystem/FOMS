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
SCRIPT_CACHEBUSTER = "?v=20260728a"


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
    assert "제작을 시작하시겠습니까" in js  # 시작 confirm
    assert "제작을 완료하시겠습니까" in js  # 완료 confirm


def test_domain_sheets_js_wires_production_cancel_and_uncomplete() -> None:
    """되돌리기 2종(시트 전용): 제작 취소 = /production/cancel + confirm,
    완료 취소 = /production/uncomplete + confirm. 위임 액션명·엔드포인트·문구 고정."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "production-cancel" in js  # 시트 액션 위임 분기
    assert "/production/cancel" in js  # 신규 되돌리기 엔드포인트
    assert "제작을 취소하고 제작대기로 되돌릴까요" in js  # 취소 confirm
    assert "production-uncomplete" in js
    assert "/production/uncomplete" in js
    assert "완료를 취소하고 제작중으로 되돌릴까요" in js  # 완료 취소 confirm


def test_domain_sheets_js_wires_hold_release_confirm() -> None:
    """보류 해제 경로 = confirm 게이트(오조작 방지) + 서버 렌더 사유(data-hold-reason) 병기.
    설정(prompt) 경로는 현행 유지."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "보류를 해제할까요" in js  # 해제 confirm 문구
    assert "data-hold-reason" in js  # 사유는 버튼 인접 DOM 아닌 서버 렌더 데이터에서 읽음


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


# --- (5) 변경 브리핑 모달 (R4: 건별 확인·영구 억제 제거) ----------------------


def test_kanban_body_change_modal_markup_gated_and_a11y() -> None:
    """변경 브리핑 모달은 changed_count>0 일 때만 렌더 + dialog a11y + 행별 [확인]/닫기/딤 data
    속성. R4: [전체 확인]·fingerprint 제거(영구 억제 없음)."""
    body = _read(KANBAN_BODY)
    assert "{% if (changed_count | default(0, true)) > 0 %}" in body
    assert 'id="foms-prod-change-modal"' in body
    assert 'role="dialog"' in body
    assert 'aria-modal="true"' in body
    for attr in (
        "data-prod-change-row-ack",  # 행별 [확인]
        "data-prod-change-close",
        "data-prod-change-dim",
    ):
        assert attr in body, f"모달 버튼/딤 attr 부재: {attr}"
    # R4 제거 계약: 전체확인 버튼·fingerprint 억제 없음.
    assert "data-prod-change-ackall" not in body
    assert "data-fingerprint" not in body


def test_domain_sheets_js_wires_change_modal_per_row() -> None:
    """모달 열기/닫기/행별 ack(리로드 없이 DOM 정리) + fragment 스왑 재도착 배선 + 기존
    change-ack endpoint 재사용. R4: fingerprint(sessionStorage)·전체확인(Promise.all) 제거."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "foms-prod-change-modal" in js
    assert "foms:erp-shell-fragment-swapped" in js  # 스왑 도착 시 재표시(once-only)
    assert "data-prod-change-row-ack" in js  # 행별 [확인] 위임
    assert "/production/change-ack" in js  # 백엔드 무변경 — 기존 endpoint 재사용
    # R4 제거 계약: 영구 억제(sessionStorage)·배치(Promise.all) 없음.
    assert "sessionStorage" not in js
    assert "Promise.all" not in js


# --- (6) 확인 후 상설 "변경됨" 조용한 배지 (R5) ------------------------------

PROD_SHEET = "templates/production/partials/tablet_sheet.html"


def test_kanban_body_quiet_changed_badge_and_history_attr() -> None:
    """확인 후 상설 조용한 칩 + data-change-history 속성 (미확인 아님 + 이력일 때)."""
    body = _read(KANBAN_BODY)
    assert "foms-kanban-card__changed-quiet" in body
    assert "data-change-history=" in body
    assert "not _has_changes and _has_change_history" in body


def test_prod_sheet_confirmed_history_section() -> None:
    """시트: 확인됨(이력만) 시 변경 이력 섹션(확인 버튼 없음, 차분한 변형) — order.change_history 소비."""
    sheet = _read(PROD_SHEET)
    assert "foms-prod-sheet__changes--history" in sheet
    assert "change_history" in sheet


def test_domain_sheets_js_quiet_transition_and_filter_or() -> None:
    """ack 후 조용한 상태 전환(펄스 제거 + data-change-history=1 + 조용한 칩 주입) +
    변경 필터 OR(미확인 data-changed 또는 확인된 이력 data-change-history)."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "injectQuietBadge" in js
    assert 'setAttribute("data-change-history", "1")' in js  # 조용한 상태 전환
    assert 'getAttribute("data-change-history") === "1"' in js  # 필터 OR 조건


# --- (7) 칸반 전량 셋 소비 + 표시 상한 공지 (회귀 수정) ------------------------


def test_kanban_body_consumes_full_set_not_page_rows() -> None:
    """칸반 열 그룹핑은 페이지 행(orders)이 아니라 전량 셋(kanban_orders)을 소비한다 —
    미도착 시 orders 로 폴백(|default). selectattr 버킷 그룹핑은 그 데이터원을 따른다."""
    body = _read(KANBAN_BODY)
    assert "kanban_orders | default(orders, true)" in body
    assert "_korders | selectattr('stage', 'equalto', '제작대기')" in body


def test_kanban_body_cap_notice_gated() -> None:
    """전량 셋이 표시 상한 초과(kanban_capped) 시 무채 1줄 공지(검색 유도)."""
    body = _read(KANBAN_BODY)
    assert "kanban_capped | default(false)" in body
    assert "tablet-prod-cap-note" in body
    assert "표시 상한" in body


# --- (8) 보류 운영 가시성 KPI 타일 + 필터 분기 (P7 C-3) ------------------------


def test_kanban_body_has_hold_kpi_tile() -> None:
    """KPI 행에 보류 타일(data-tablet-prod-kpi='hold') — 기존 상호배타 토글 문법 복제."""
    body = _read(KANBAN_BODY)
    assert 'data-tablet-prod-kpi="hold"' in body
    assert "_kpi.get('hold'" in body  # 서버 KPI 카운트 소비


def test_domain_sheets_js_has_hold_kpi_filter_branch() -> None:
    """applyProdFilter kpiOK 에 hold 분기(.is-held 카드만 표시)."""
    js = _read(DOMAIN_SHEETS_JS)
    assert 'kpi === "hold"' in js
    assert 'classList.contains("is-held")' in js


# --- (9) Phase G: 필터 바 재구성(접기·상태 select 제거, 공장 앞·변경 상시) -----


def test_kanban_body_filter_bar_simplified() -> None:
    """Phase G: [필터] 토글·__more 접이·상태 select 제거 → 전 항목 상시 노출.
    공장 select 가 검색 앞(좌측), 변경·초기화 상시. 전체화면 토글은 유지."""
    body = _read(KANBAN_BODY)
    # 제거된 것: 필터 토글 버튼·접이 컨테이너·개수 배지·상태 select.
    assert "data-tablet-prod-filter-toggle" not in body
    assert "tablet-prod-filter__more" not in body
    assert "data-tablet-prod-filter-count" not in body
    assert "data-tablet-prod-status" not in body
    # 공장 select 가 검색 input 앞(좌측) — 둘 다 상시 노출.
    assert "data-tablet-prod-factory" in body
    assert "data-tablet-prod-search" in body
    assert body.index("data-tablet-prod-factory") < body.index(
        "data-tablet-prod-search"
    ), "공장 select 가 검색 input 앞에 있어야 함(Phase G 순서)"
    # 변경 토글·초기화 상시 노출.
    assert "data-tablet-prod-changed" in body
    assert "data-tablet-prod-reset" in body


def test_domain_sheets_js_filter_collapse_removed() -> None:
    """Phase G: 필터 접기 배선 전부 제거 — localStorage 키·토글 셀렉터·복원·상태 필터 부재.
    검색은 무조건 전 열(status 분기 없음). 전체화면 복원은 유지."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "foms_tablet_prod_filters_open" not in js
    assert "data-tablet-prod-filter-toggle" not in js
    assert "restoreFilterCollapse" not in js
    assert "data-tablet-prod-status" not in js
    assert "restoreFullscreen" in js  # 전체화면 복원은 유지(별도 리스너)


# --- (10) F-2 라벨 인쇄 제거 + F-3 전체화면 토글 -------------------------------


def test_kanban_body_has_fullscreen_toggle_and_exit_markup() -> None:
    """F-3: 필터 바 전체화면 진입 버튼 + board 우상단 플로팅 복원 버튼(기본 hidden).
    진입=fa-expand, 복원=fa-compress. 고유 클래스/data 속성으로 잠근다."""
    body = _read(KANBAN_BODY)
    assert "data-tablet-prod-fullscreen" in body  # 진입 토글 위임 속성
    assert "data-tablet-prod-fullscreen-exit" in body  # 플로팅 복원 버튼(고유)
    assert "tablet-prod-fullscreen-btn" in body  # 필터 바 진입 버튼 클래스(고유)
    assert "fa-expand" in body
    assert "fa-compress" in body


def test_domain_sheets_js_wires_fullscreen_toggle() -> None:
    """F-3: 전체화면 토글 배선 — localStorage 키 + 진입/복원 위임 셀렉터 + is-fullscreen 클래스
    토글(board DOM 상태로 플립) + fragment 스왑 복원."""
    js = _read(DOMAIN_SHEETS_JS)
    assert "foms_tablet_prod_fullscreen" in js  # 상태 기억 키
    assert "data-tablet-prod-fullscreen" in js  # 진입 위임 셀렉터
    assert "data-tablet-prod-fullscreen-exit" in js  # 복원 위임 셀렉터
    assert "is-fullscreen" in js  # board 클래스 토글
    assert "restoreFullscreen" in js  # 부트/스왑 복원
