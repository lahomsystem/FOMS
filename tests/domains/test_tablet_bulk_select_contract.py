"""태블릿 목업 융합 프레임 12/13 마감 계약 (2026-07-13).

  A. 프레임 12 — long-press 벌크 선택: tablet-bulk-select.js 존재/싱글턴/coarse landscape
     게이트/long-press(스크롤 취소)/시트 억제(capture stopPropagation)/기존 벌크 재사용,
     foms-tablet-landscape.css contextual bar + coarse landscape 게이트,
     erp-dashboard-entry.js CHAIN 논블로킹 배선.
  B. 프레임 13 — erp-wdc-split.css coarse landscape arm(태블릿 가로 "계산기 같이 보기").

별도 파일로 마감 문자열을 잠근다(동시 워커 병합 충돌 회피)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BULK_JS = "static/js/foms/tablet-bulk-select.js"
LANDSCAPE_CSS = "static/css/foundation/foms-tablet-landscape.css"
ENTRY_JS = "static/js/orders/erp-dashboard-entry.js"
WDC_SPLIT_CSS = "static/css/orders/erp-wdc-split.css"

CORE_MQ = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
CORE_MQ_INNER = "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# =====================================================================
# A. 프레임 12 — long-press 벌크 선택
# =====================================================================


def test_bulk_select_js_exists_singleton_gated() -> None:
    """싱글턴 가드(perf G4) + coarse landscape MQ + CSS 마커 게이트."""
    js = _read(BULK_JS)
    assert "window.__FOMS_TABLET_BULK_SELECT_BOUND" in js, "싱글턴 가드 부재(perf G4)"
    assert CORE_MQ_INNER in js, "coarse landscape MQ 게이트 부재"
    assert "--foms-tablet-ui" in js, "CSS 마커(--foms-tablet-ui:ready) 게이트 부재"


def test_bulk_select_longpress_with_scroll_cancel() -> None:
    """pointerdown 타이머 long-press + pointermove 스크롤 취소 + pointerup/cancel 정리."""
    js = _read(BULK_JS)
    assert "pointerdown" in js, "long-press pointerdown 부재"
    assert "setTimeout" in js, "long-press 타이머 부재"
    assert "LONG_PRESS_MS" in js
    assert "pointermove" in js, "스크롤 취소(pointermove) 부재"
    assert "pointerup" in js and "pointercancel" in js, "포인터 종료 정리 부재"


def test_bulk_select_reuses_existing_bulk_mechanism() -> None:
    """기존 PC 벌크 체크박스 + change 이벤트 트리거 + 기존 벌크 바 액션 재사용(중복 구현 금지)."""
    js = _read(BULK_JS)
    assert "erp-grid-order-check" in js, "기존 벌크 체크박스 미재사용"
    assert 'new Event("change"' in js, "기존 change 이벤트 트리거 부재"
    assert "erp-grid-bulk-status" in js, "기존 벌크 바 상태 select 재사용 부재"
    assert "erp-grid-select-all" in js, "전체 선택 경로 동기화 부재"


def test_bulk_select_suppresses_sheet_via_capture_stopprop() -> None:
    """시트 억제 = document click capture 위임 + stopPropagation(버블 시트 리스너 차단)."""
    js = _read(BULK_JS)
    assert "stopPropagation" in js, "시트 억제 stopPropagation 부재"
    # click 리스너가 capture(3번째 인자 true)로 등록되어 버블 시트 리스너보다 우선.
    assert re.search(
        r'addEventListener\(\s*"click".*?\}\s*,\s*true\s*\)', js, re.DOTALL
    ), "click 리스너 capture 등록(} , true) 부재"


def test_bulk_select_wired_nonblocking_in_entry_chain() -> None:
    """erp-dashboard-entry.js CHAIN 동적 주입(async=false) — 렌더 비차단(perf G1)."""
    entry = _read(ENTRY_JS)
    assert "js/foms/tablet-bulk-select.js" in entry, "entry CHAIN 미배선"
    assert "s.async = false" in entry, "CHAIN 동적 로드 async=false(논블로킹) 부재"


def test_bulk_select_css_contextual_bar_and_gate() -> None:
    """base-hide + coarse landscape 게이트 + contextual bar/선택 행 강조 클래스."""
    css = _read(LANDSCAPE_CSS)
    norm = _norm(css)
    assert ".foms-tablet-bulk-bar { display: none; }" in norm, "contextual bar base-hide 부재"
    assert "foms-tablet-bulk-bar__count" in css, "선택 카운트 요소 스타일 부재"
    assert "foms-tablet-bulk-selected" in css, "선택 행 강조 클래스 부재"
    assert "foms-tablet-bulk-mode" in css, "선택 모드 body 클래스 부재"
    assert CORE_MQ in css, "coarse landscape 게이트 부재"


# =====================================================================
# B. 프레임 13 — 계산기 같이 보기 coarse landscape arm
# =====================================================================


def test_wdc_split_coarse_landscape_arm() -> None:
    """태블릿 가로 arm: coarse landscape MQ + 토글 표시 명시 + 44px 터치 타깃."""
    css = _read(WDC_SPLIT_CSS)
    assert CORE_MQ in css, "erp-wdc-split.css coarse landscape arm(MQ) 부재"
    assert ".erp-wdc-split-toggle" in css
    assert "--foms-touch-target-comfortable" in css, "44px 터치 타깃 보정 부재"
    # arm 이 max-width:991.98px 하드 은닉 블록 뒤에 온다(게이트 축소 회귀 방지 의도).
    assert css.index("max-width: 991.98px") < css.index(CORE_MQ)
