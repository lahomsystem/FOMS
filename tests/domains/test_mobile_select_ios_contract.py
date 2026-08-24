"""iOS Safari 이중 피커 회귀 차단 계약 (foms-mobile-select.js).

iOS 의 ``<select>`` 네이티브 피커는 focus 로 열린다. 합성 mousedown 을 취소해도 막히지
않으므로 (1) 터치 경로는 ``touchend`` 를 non-passive 로 취소해 합성 mouse/click/focus 자체를
없애고, (2) 시트를 닫을 때 coarse 포인터에서는 select 포커스를 되돌리지 않는다. 둘 중 하나만
되돌아가도 "고르면 또 고르라고 뜬다" 증상이 재발하므로 소스 계약으로 고정한다.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
MOBILE_SELECT_JS = ROOT / "static/js/components/foms-mobile-select.js"
LAYOUT_SCRIPTS = ROOT / "templates/partials/shared/layout_scripts.html"


def _js() -> str:
    return MOBILE_SELECT_JS.read_text(encoding="utf-8")


def test_touchend_listener_is_non_passive() -> None:
    """passive 리스너는 preventDefault 가 무시된다 → 네이티브 피커가 그대로 뜬다."""
    js = _js()
    assert 'document.addEventListener("touchend", onTouchEnd, { passive: false });' in js
    # touchstart 는 취소하지 않는다(select 위에서 시작한 스크롤 보존).
    assert 'document.addEventListener("touchstart", onTouchStart, { passive: true });' in js


def test_touchend_cancels_default_to_block_native_picker() -> None:
    js = _js()
    body = js.split("function onTouchEnd(", 1)[1].split("function onKey(", 1)[0]
    assert "e.preventDefault();" in body, "onTouchEnd 가 기본동작을 취소하지 않음"
    assert "open(sel);" in body


def test_close_skips_focus_restore_on_coarse_pointer() -> None:
    js = _js()
    assert 'var COARSE = window.matchMedia("(pointer: coarse)");' in js
    assert "if (currentSel && currentSel.focus && !COARSE.matches) {" in js


def test_mousedown_path_guarded_against_touch_double_open() -> None:
    js = _js()
    assert "Date.now() - touchOpenAt < 700" in js


def test_load_pin_bumped_off_pre_fix_version() -> None:
    """SW staticCacheFirst 때문에 ?v 범프 없으면 기존 기기에 옛 파일이 계속 나간다."""
    head = LAYOUT_SCRIPTS.read_text(encoding="utf-8")
    assert "js/components/foms-mobile-select.js" in head
    assert "foms-mobile-select.js') }}?v=20260711a" not in head
