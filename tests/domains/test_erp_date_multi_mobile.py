"""여러 날짜 달력(주 실측일 · 시공일 · 항목 실측일 · 시공일) 폰 계약 — 2026-11-25 사장님 "모바일에서도 가능하게 > UI 최적화 해".

실화면(로컬 준비물 서버 · Playwright 폰 390)에서 찾은 문제가 다시 생기지 않게 원문 자리를 묶는다.
- 모바일 폼 항목 실측일 · 시공일 칸이 `d-none erp-mobile-rare-field` 로 숨어 폰에서 아예 안 보였다.
- 폰에서 칸을 누르면 손 입력 칸(allowInput)이 잡혀 자판이 올라왔다 · 반폭 시공일 칸에서 두 날 글이 잘렸다.
- 날짜 칸 39px · 앞뒤 달 34px · [확인] 40px — 손가락 크기(44px)보다 작았다.
PC(옛 폼)는 전과 같아야 한다 — 손 입력 · 칸 옆 달력 · [확인] 모양 값.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHARED_JS = ROOT / "static/js/orders/erp-order-shared.js"
DATE_JS = ROOT / "static/js/orders/erp-date-multi.js"
DATE_CSS = ROOT / "static/css/orders/erp-date-multi.css"
ORDER_JS_PARTIAL = ROOT / "templates/orders/partials/erp_order_js.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _css_block(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start:css.index("}", start)]


def test_all_multi_date_pickers_go_through_one_helper_loaded_first() -> None:
    js = _read(SHARED_JS)
    assert "window.ErpDateMulti.attach(mEl," in js
    assert "window.ErpDateMulti.attach(cEl, erpConstructionCountOptions('days'))" in js
    assert "window.ErpDateMulti.attach(el);" in js
    assert "flatpickr(el, {" not in js and "flatpickr(mEl, {" not in js
    # [확인] 줄 모양은 CSS 파일로 — JS 가 <style> 을 넣지 않는다.
    assert "erp-fp-done-style" not in js and "createElement('style')" not in js
    partial = _read(ORDER_JS_PARTIAL)
    css_at = partial.index("asset_url('css/orders/erp-date-multi.css')")
    helper_at = partial.index("asset_url('js/orders/erp-date-multi.js') }}\" defer")
    assert css_at < helper_at < partial.index("asset_url('js/orders/erp-order-shared.js')")


def test_phone_mode_hides_keyboard_path_and_keeps_pc_typing() -> None:
    js = _read(DATE_JS)
    assert "closest('.erp-order-mobile-form')" in js
    assert "allowInput: !phone," in js
    assert "mode: 'multiple'," in js and "dateFormat: 'Y-m-d'," in js and "locale: 'ko'," in js
    # 보기 칸은 저장 칸이 아니다(erpCollectStructured 가 [data-erp] 를 모은다).
    view_fn = js[js.index("function mountView(input)"):js.index("function keepViewAboveSheet")]
    assert "data-erp" not in view_fn and "dataset" not in view_fn
    assert "Object.defineProperty(input, 'value'" in view_fn
    # flatpickr 기본 ignoredFocusElements 배열은 모든 인스턴스가 같이 쓴다 — 인스턴스마다 새 배열.
    assert "opts.ignoredFocusElements = [view];" in js
    assert "opts.position = noPosition;" in js
    assert "fp.clear(true, false)" in js


def test_phone_sheet_touch_targets_are_44px_or_more_and_pc_bar_unchanged() -> None:
    css = _read(DATE_CSS)
    sheet = ".flatpickr-calendar.erp-fp-sheet"
    day = _css_block(css, f"{sheet} .flatpickr-day")
    assert "height: 48px;" in day and "max-width: 48px;" in day
    nav = _css_block(css, f"{sheet} .flatpickr-months .flatpickr-prev-month,\n{sheet} .flatpickr-months .flatpickr-next-month")
    assert "width: 48px;" in nav and "height: 48px;" in nav
    buttons = _css_block(css, f"{sheet} .erp-fp-done-btn,\n{sheet} .erp-fp-clear-btn")
    assert "min-height: 48px;" in buttons
    assert "position: fixed;" in _css_block(css, sheet)
    # PC [확인] 줄은 전에 JS 가 넣던 값 그대로(글자만 탭별 글자 크기를 따른다).
    pc_btn = _css_block(css, ".flatpickr-calendar .erp-fp-done-btn")
    for decl in ("min-height: 40px;", "padding: 6px 18px;", "border-radius: 8px;", "background: #2563eb;",
                 "font-weight: 600;", "font-size: calc(14px * var(--foms-fs, 1));"):
        assert decl in pc_btn
    pc_bar = _css_block(css, ".flatpickr-calendar .erp-fp-done-bar")
    for decl in ("justify-content: flex-end;", "padding: 6px;", "border-top: 1px solid #e5e7eb;"):
        assert decl in pc_bar
    # 새 font-size px 는 탭별 글자 크기를 따른다.
    for size in re.findall(r"font-size:\s*([^;]+);", css):
        assert "px" not in size or "var(--foms-fs, 1)" in size, size
