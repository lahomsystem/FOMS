"""여러 날짜 달력(주 실측일 · 시공일 · 항목 실측일 · 시공일) 폰 계약 — 2026-11-25 사장님 "모바일에서도 가능하게 > UI 최적화 해".

실화면(로컬 준비물 서버 · Playwright 폰 390)에서 찾은 문제가 다시 생기지 않게 묶는다.
- (칸 보이기 · 여러 날짜면 두 칸 위아래로 쌓기는 다른 창 352d158c2 · 1762177f8 것을 쓴다 — 여기서는 그 칸에 달력이 붙는지만 본다.)
- 폰에서 칸을 누르면 손 입력 칸(allowInput)이 잡혀 자판이 올라왔다 · 반폭 시공일 칸에서 두 날 글이 잘렸다.
- 날짜 칸 39px · 앞뒤 달 34px · [확인] 40px — 손가락 크기(44px)보다 작았다.
PC(옛 폼)는 전과 같아야 한다 — 손 입력 · 칸 옆 달력 · [확인] 모양 값.

움직임은 node 로 static/js/orders/erp-date-multi.js 를 실제로 돌려 본다(tests/domains/erp_date_multi_runner.js —
가짜 화면 · 가짜 flatpickr). 진짜 flatpickr 와 맞물리는 것은 실화면으로 확인했다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHARED_JS = ROOT / "static/js/orders/erp-order-shared.js"
DATE_JS = ROOT / "static/js/orders/erp-date-multi.js"
DATE_CSS = ROOT / "static/css/orders/erp-date-multi.css"
ORDER_JS_PARTIAL = ROOT / "templates/orders/partials/erp_order_js.html"
RUNNER = ROOT / "tests/domains/erp_date_multi_runner.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _css_block(css: str, selector: str) -> str:
    """선택자 목록 전체가 `selector` 인 규칙의 몸(다른 목록의 꼬리로 들어 있는 것은 건너뛴다)."""
    for found in re.finditer(re.escape(selector + " {"), css):
        before = css[:found.start()].rstrip()
        if not before or before.endswith(("}", "*/")):
            return css[found.start():css.index("}", found.start())]
    raise AssertionError(f"규칙 없음: {selector}")


@lru_cache(maxsize=1)
def _run() -> dict:
    out = subprocess.run(["node", str(RUNNER), str(DATE_JS)], capture_output=True, text=True, encoding="utf-8",
                         timeout=60, check=True).stdout
    return json.loads(out)


def test_item_date_inputs_keep_the_class_the_helper_attaches_to() -> None:
    js = _read(SHARED_JS)
    start = js.index("function erpNewItemRow(")
    row_fn = js[start:js.index("\nfunction ", start + 1)]
    # 항목 칸 마크업은 다른 창 것(itemDateInput) — 달력은 이 클래스로 붙는다(erpInitFlatpickrForItemRow).
    helper = row_fn[row_fn.index("const itemDateInput = "):]
    helper = helper[:helper.index("\n")]
    assert 'erp-item-date-multiple" data-erp="${key}" placeholder="여러 날짜 가능"' in helper
    assert "row.querySelectorAll('.erp-item-date-multiple')" in js


def test_all_multi_date_pickers_go_through_one_helper_loaded_first() -> None:
    js = _read(SHARED_JS)
    start = js.index("    function initErpMainDatePickers()")
    end = js.index("window.erpInitFlatpickrForItemRow = function", start)
    init_fns = js[start:js.index("    };", end)]
    assert "window.ErpDateMulti.attach(mEl," in init_fns
    assert "window.ErpDateMulti.attach(cEl, erpConstructionCountOptions('days'))" in init_fns
    assert "window.ErpDateMulti.attach(el);" in init_fns
    assert "flatpickr(" not in init_fns.replace("typeof flatpickr", "")
    partial = _read(ORDER_JS_PARTIAL)
    css_at = partial.index("asset_url('css/orders/erp-date-multi.css')")
    helper_at = partial.index("asset_url('js/orders/erp-date-multi.js') }}\" defer")
    assert css_at < helper_at < partial.index("asset_url('js/orders/erp-order-shared.js')")


@NODE
def test_phone_view_follows_value_without_keyboard_path() -> None:
    got = _run()["phone"]
    init = got["init"]
    assert init["allowInput"] is False and init["readonly"] is True and init["src"] is True  # 자판 길 없음
    assert init["viewNext"] and init["view"] == "2026-12-03, 2026-12-04"
    assert init["dataErp"] == []  # 보기 칸은 저장 칸이 아니다
    assert init["positionFn"] and init["ignored"] and init["sharedIgnoredEmpty"]
    assert init["sheet"] and init["yearReadonly"] and init["clearBtn"] and init["done"] == "확인"
    assert init["extraReady"] == 1  # 부르는 쪽 훅(날마다 건수)도 같이 돈다
    assert got["externalView"] == "2026-12-07"  # 서버 값 채우기 · 작성 중 복원도 보기 칸에 바로
    pick = got["pick"]
    assert pick["view"] == pick["value"] == "2026-12-03, 2026-12-04, 2026-12-15"
    assert pick["log"] == ["hook:" + pick["value"], "change:" + pick["value"], "input:" + pick["value"]]
    clear = got["clear"]
    assert clear["value"] == "" and clear["empty"] and clear["open"] and clear["args"] == [True, False]
    assert clear["log"] == ["hook:", "change:", "input:"]
    assert got["disabledOpens"] is False and got["labelOpens"] is True


@NODE
def test_phone_names_focus_and_inline_prev_value() -> None:
    got = _run()["phone"]
    init, item = got["init"], got["item"]
    assert init["role"] == "button" and init["tabIndex"] == 0 and init["expanded"] == "false"
    assert init["name"] == "시공일 | 2026-12-03, 2026-12-04"
    # 문서에 붙기 전 항목 칸: 빈 칸 자리 글은 보이기만(화면 읽기 이름에는 칸 이름만)
    assert item["phone"] and item["allowInput"] is False and item["empty"]
    assert item["view"] == "여러 날짜 가능" and item["placeholderHidden"] == "true" and item["name"] == "항목 실측일 | "
    # 다른 창의 두 칸 쌓기는 change 때 칸 value 를 읽는다 — 날 하나 · 둘 · 지우기에서 나란히 · 쌓기 · 나란히
    assert item["stack"] == [False, True, False] and item["viewTwo"] == "2026-12-01, 2026-12-02"
    opened = got["open"]
    assert opened["isOpen"] and opened["expanded"] == "true" and opened["positioned"] == 0
    assert opened["inlinePrev"] == "2026-12-07" and opened["focusin"]  # 인라인 저장의 '바꾸기 전 값'
    assert opened["active"] != "INPUT"
    assert opened["scrolled"] == [{"block": "nearest"}] and opened["sheetVar"] == "437px"
    assert got["landscapeScrolled"] == 0 and got["visibleScrolled"] == 0
    assert got["done"] == {"open": False, "expanded": "false", "focusView": True}
    kbd = got["kbd"]
    assert kbd["open"] and kbd["focusDay"] == "2026-12-12"
    assert kbd["afterPick"] == {"value": "2026-12-12, 2026-12-13", "focusDay": "2026-12-13", "connected": True}
    assert kbd["closedFocusView"] and kbd["spaceOpenEscapeClose"]
    assert got["touchPickActive"] == "BODY"  # 손가락으로 고를 때는 포커스를 만들지 않는다


@NODE
def test_pc_keeps_typing_and_popup() -> None:
    got = _run()["pc"]
    assert got["allowInput"] is True and got["readonly"] is False
    assert got["view"] is False and got["src"] is False and got["positionFn"] is False
    assert got["sheet"] is False and got["clearBtn"] is False and got["done"] is True and got["yearReadonly"] is False
    assert got["ignoredShared"] is True and got["typed"] == "2026-12-20, 2026-12-21" and got["again"] is True


def test_phone_sheet_fits_screen_with_44px_targets_and_pc_bar_unchanged() -> None:
    css = _read(DATE_CSS)
    sheet = ".flatpickr-calendar.erp-fp-sheet"
    box = _css_block(css, sheet)
    assert "position: fixed;" in box and "max-height: 100%;" in box
    inner = _css_block(css, f"{sheet} .flatpickr-innerContainer")
    assert "overflow-y: auto;" in inner and "min-height: 0;" in inner
    assert "flex: 0 0 auto;" in _css_block(css, f"{sheet} .flatpickr-months,\n{sheet} .erp-fp-done-bar")
    day = _css_block(css, f"{sheet} .flatpickr-day")
    assert "height: 48px;" in day and "max-width: none;" in day  # 칸 폭 = 줄 폭 ÷ 7(늘 한 줄 7칸)
    row = _css_block(css, f"{sheet} .flatpickr-weekdays .flatpickr-weekdaycontainer,\n{sheet} .flatpickr-days")
    assert "max-width: calc(7 * 48px + 8px);" in row
    nav = _css_block(css, f"{sheet} .flatpickr-months .flatpickr-prev-month,\n{sheet} .flatpickr-months .flatpickr-next-month")
    assert "width: 48px;" in nav and "height: 48px;" in nav
    buttons = _css_block(css, f"{sheet} .erp-fp-done-btn,\n{sheet} .erp-fp-clear-btn")
    assert "min-height: 48px;" in buttons
    low = css[css.index("@media (max-height: 480px)"):]
    assert re.findall(r"(?:min-)?height: (\d+)px;", low) and min(
        int(v) for v in re.findall(r"(?:min-)?height: (\d+)px;", low) if int(v) > 30) >= 44
    bar = _css_block(css, f"{sheet} .erp-fp-done-bar")
    assert "background: var(--foms-surface-base" in bar  # 다크 모드에서 흰 줄이 아니게
    # PC [확인] 줄은 전에 JS 가 넣던 값 그대로(글자만 탭별 글자 크기를 따른다).
    pc_btn = _css_block(css, ".flatpickr-calendar .erp-fp-done-btn")
    for decl in ("min-height: 40px;", "padding: 6px 18px;", "border-radius: 8px;", "background: #2563eb;",
                 "font-weight: 600;", "font-size: calc(14px * var(--foms-fs, 1));"):
        assert decl in pc_btn
    pc_bar = _css_block(css, ".flatpickr-calendar .erp-fp-done-bar")
    for decl in ("justify-content: flex-end;", "padding: 6px;", "border-top: 1px solid #e5e7eb;", "background: #fff;"):
        assert decl in pc_bar
    for size in re.findall(r"font-size:\s*([^;]+);", css):
        assert "px" not in size or "var(--foms-fs, 1)" in size, size
