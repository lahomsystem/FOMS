"""도면 마법사 앱바 '도구 ▾' 묶음 · 떠 있는 막대 자리 · 알림 시간 · 누르는 칸 계약.

2026-10-25 사용성 평가 큼-1(앱바 넘침)·막힘-2(세로 태블릿 [나가기]·[제품 목록] 겹침)·큼-4(미니 막대가
계산 칸을 덮고 글자가 꺾임)·보통-6(알림이 계산 칸 밑에 깔리고 2.6초 만에 사라짐)·글자 대비·'작음'(누르는 칸).

- 문자열 계약: 템플릿·CSS·wizard.js 의 연결 지점.
- 동작 계약: wizard-chrome.js 를 node 로 돌려 알림 시간·보이는 캔버스 계산·막대 자리·메뉴가 원래 단추를 누르는지 본다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TPL = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
JS = (ROOT / "static/js/drawing/wizard.js").read_text(encoding="utf-8")
CHROME = ROOT / "static/js/drawing/wizard-chrome.js"
CSS_CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)   # 주석 뺀 CSS(옛 값을 주석에 적어 둔 것은 세지 않는다)

_FN_DECL = chr(10) + "  function "


def _fn_slice(src: str, decl: str) -> str:
    start = src.index(decl)
    nxt = src.find(_FN_DECL, start + len(decl))
    return src[start:] if nxt < 0 else src[start:nxt]


def _header() -> str:
    return TPL.split('<header class="dws-appbar dws-ui">', 1)[1].split("</header>", 1)[0]


def _media(query: str) -> str:
    """'@media <query> {' 덩어리 본문(첫 덩어리). 중괄호 짝을 세어 자른다."""
    head = "@media " + query + " {"
    start = CSS.index(head) + len(head)
    depth, i = 1, start
    while depth:
        if CSS[i] == "{":
            depth += 1
        elif CSS[i] == "}":
            depth -= 1
        i += 1
    return CSS[start:i - 1]


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, selector
    return m.group(1)


# ---- 템플릿 ----------------------------------------------------------------

def test_tools_dropdown_in_appbar_targets_original_buttons():
    head = _header()
    assert 'id="dws-btn-tools"' in head and 'aria-controls="dws-tools-menu"' in head
    menu = head.split('id="dws-tools-menu"', 1)[1].split("</div>\n        </div>", 1)[0]
    assert head.split('id="dws-tools-menu"', 1)[1].split(">", 1)[0].rstrip().endswith("hidden")
    targets = re.findall(r'data-tools-for="([^"]+)"', menu)
    assert targets[:3] == ["dws-btn-autofill", "dws-btn-arrange", "dws-btn-calc"]
    assert {"dws-btn-font-dec", "dws-btn-font-inc", "dws-btn-table-reset", "dws-btn-zoom-fit"} <= set(targets)
    for t in targets:   # 원래 단추는 그대로 앱바에 있다(넓은 화면에서 보이고, 메뉴는 그것을 눌러 준다)
        assert f'id="{t}"' in head, t
    # 계산 칸 단추의 aria-expanded·aria-controls 는 그대로
    calc = next(ln for ln in head.splitlines() if 'id="dws-btn-calc"' in ln)
    assert 'aria-expanded="false"' in calc and 'aria-controls="dws-calc"' in calc
    # 도구 단추 자체는 잠그지 않는다(열람 전용도 계산 칸은 연다) — 항목이 원래 단추의 잠금을 따른다
    tools = next(ln for ln in head.splitlines() if 'id="dws-btn-tools"' in ln)
    assert "dws-edit-ctl" not in tools


def test_appbar_header_has_no_inline_style():
    assert "style=" not in _header()


def test_chrome_script_loads_deferred_before_wizard():
    tag = re.search(r'<script src="[^"]*wizard-chrome\.js[^"]*"[^>]*>', TPL)
    assert tag and "?v=" in tag.group(0) and " defer" in tag.group(0)
    assert TPL.index("js/drawing/wizard-chrome.js") < TPL.index("js/drawing/wizard.js')")


# ---- CSS: 앱바 ---------------------------------------------------------------

def test_left_track_keeps_exit_and_title_min():
    # 왼쪽 열: 최소는 [나가기] + 제목 76px(contain), 상한은 제목 글 폭(--dws-left-w, wizard-appbar.js fitLeft) —
    # 남는 자리가 제목 칸이 아니라 도구 묶음 뒤에 남아 가운데 도구 묶음이 옆으로 안 움직인다(2026-10-25 실화면 확인 V1)
    assert "grid-template-columns: minmax(min-content, var(--dws-left-w, 1fr)) auto minmax(max-content, 1fr);" in CSS
    wrap = _rule(".dws-appbar-titlewrap")
    assert "min-width: 76px;" in wrap and "contain: inline-size;" in wrap and "flex: 1 1 auto;" in wrap


def test_status_slots_keep_width_so_buttons_do_not_shift():
    """2026-10-25 실화면 확인 V1: 진행 칩·저장 칩 글이 바뀔 때마다 앱바 단추가 옆으로 밀렸다
    (1920 진행 칩 −168px · 새로고침 뒤 첫 편집 −90px · 탭 바꿈 44px). 글이 바뀌어도 자리 폭은 그대로여야 한다."""
    head = _header()
    # 칩 묶음은 처음부터 템플릿에 — 저장 칩 바로 앞(part-status.js 가 이 묶음을 채운다)
    assert head.index('id="dws-part-status"') < head.index('id="dws-save-status"') < head.index('id="dws-btn-save"')
    box = next(ln for ln in head.splitlines() if 'id="dws-part-status"' in ln)
    assert 'class="dws-part-status"' in box and " hidden>" in box
    # '미분류'·딱지 단추 묶음 124px · 저장 칩 118px 고정 — 비었을 때(hidden)도 자리는 남기고 안 보이게만
    assert ".dws-appbar .dws-part-status { min-width: 124px; justify-content: flex-end; }" in CSS_CODE
    assert ".dws-appbar .dws-part-status[hidden] { display: inline-flex; visibility: hidden; }" in CSS_CODE
    assert ".dws-appbar .dws-save-status { flex: 0 0 auto; width: 118px; text-align: center; }" in CSS_CODE
    assert ".dws-appbar .dws-save-status[hidden] { display: inline-block; visibility: hidden; }" in CSS_CODE
    # [저장] '저장'·'저장 *' 같은 폭 — 별표 몫을 안 보이게 붙인다(-5px = .dws-btn 틈)
    assert '#dws-btn-save:not(.dws-dirty)::after { content: " *"; white-space: pre; visibility: hidden; margin-left: -5px; }' in CSS_CODE
    assert "gap: 5px;" in _rule(".dws-btn")
    # '알아보는 중' 칩은 앱바 밖(바로 아래)에 뜬다 — 옆으로 미는 줄에서는 스크롤 칸에 잘리지 않게 화면 기준
    busy = _rule(".dws-appbar-right .dws-part-status-busy")
    for needle in ("position: absolute;", "top: calc(100% + 6px);", "pointer-events: none;", "max-width: var(--dws-busy-max"):
        assert needle in busy, needle
    strip = _media("(max-width: 1179px), (max-width: 1279px) and (pointer: coarse)")
    assert ".dws-appbar-right .dws-part-status-busy { position: fixed; top: 58px; right: 8px; }" in strip
    # 앱바 안에서 칩 폭을 줄이던 단계·알아보는 동안 '미분류'를 숨기던 규칙은 없앴다(칩이 앱바 밖에 뜬다)
    assert "--dws-busy-max: 170px" not in CSS_CODE and "--dws-busy-max: 88px" not in CSS_CODE
    assert ":has(> .dws-part-status-busy" not in CSS_CODE
    # 상태 칩 자리를 늘 잡아 두는 몫 — 1920 이하에서는 줌 막대를 숨겨 '선택'·'텍스트' 이름 자리를 남긴다
    assert "#dws-zoom-range { display: none; }" in _media("(min-width: 901px) and (max-width: 1920px)")


def test_tools_group_breakpoints():
    assert "display: none;" in _rule(".dws-tools-more")
    b1900 = _media("(max-width: 1900px)")
    assert ".dws-tools-more { display: inline-flex; }" in b1900
    for sel in ("#dws-btn-autofill", "#dws-btn-arrange", "#dws-btn-calc"):
        assert sel in b1900
    b1700 = _media("(max-width: 1700px)")
    assert ".dws-appbar-right .dws-fontctl" in b1700 and ".dws-tools-menu .dws-tools-font { display: block; }" in b1700
    b1280 = _media("(min-width: 901px) and (max-width: 1280px)")
    assert "#dws-btn-zoom-fit { display: none; }" in b1280 and ".dws-tools-menu .dws-tools-fit { display: block; }" in b1280
    # 원래 단추가 숨은 항목은 메뉴에서도 숨는다(특이도: [hidden] 규칙이 display:block 보다 세다)
    assert ".dws-tools-menu .dws-menu-item[hidden] { display: none; }" in CSS
    # 저장 상태 칩은 시각까지 보이게 120px — 예전 좁은 폭 상한(96·84px)은 없앴다
    assert ".dws-save-status { max-width: 96px; }" not in CSS and ".dws-save-status { max-width: 84px" not in CSS


def test_portrait_tablet_left_group_never_shrinks():
    b900 = _media("(max-width: 900px)")
    left = b900.split(".dws-appbar-left {", 1)[1].split("}", 1)[0]
    assert "flex: 0 0 auto;" in left and "min-width: max-content;" in left
    assert "#dws-tools-menu {" in b900 or "#dws-tools-menu," in b900   # 스크롤 줄에 잘리지 않는 fixed 메뉴


def test_narrow_desktop_falls_back_to_scroll_strip():
    q = "(min-width: 901px) and (max-width: 1179px), (min-width: 901px) and (max-width: 1279px) and (pointer: coarse)"
    strip = _media(q)
    assert "overflow-x: auto;" in strip and "display: flex;" in strip
    assert "min-width: max-content;" in strip and "#dws-tools-menu" in strip and "position: fixed;" in strip


def test_part_status_chip_keeps_room_not_hidden():
    # 그림 종류 칩(part-badges.js)은 숨기지 않고 '알아보는 중' 칩에 폭 상한만 건다
    assert "max-width: var(--dws-busy-max" in CSS
    assert ".dws-part-status { display: none" not in CSS


# ---- CSS: 막대·알림·글자·누르는 칸 ---------------------------------------------

def test_toast_above_calc_panel():
    host = _rule(".dws-toast-host")
    z = int(re.search(r"z-index:\s*(\d+)", host).group(1))
    calc_z = [int(v) for v in re.findall(r"\.dws-calc \{[^}]*?z-index:\s*(\d+)", CSS)]
    help_z = int(re.search(r"z-index:\s*(\d+)", _rule(".dws-help-overlay")).group(1))
    assert z == 130 and calc_z and all(z > c for c in calc_z) and z > help_z   # 계산 칸(120)·도움말(125) 위


def test_minitoolbar_buttons_do_not_break_and_bar_wraps():
    btn = _rule(".dws-mt-btn")
    assert "white-space: nowrap;" in btn and "flex-shrink: 0;" in btn
    assert "flex-wrap: wrap;" in _rule(".dws-mt-group")
    assert "max-width: calc(100vw - 16px);" in _rule(".dws-minitoolbar")
    # '삭제' 글자 — #ff8a80(3.24) → #ffb8b0(4.49, 아직 모자람) → #ffc9c2(5.1, 2026-10-25 실화면 QA). 대비 계산은 appbar_menus 시험
    assert ".dws-mt-del { color: #ffc9c2; }" in CSS and "#ff8a80" not in CSS_CODE and "#ffb8b0" not in CSS_CODE


def test_text_contrast_and_size_in_appbar_tabs_help():
    zoom_label = re.sub(r"/\*.*?\*/", "", _rule(".dws-zoom-label"), flags=re.S)
    assert "color: #6e6e73;" in zoom_label and "#86868b" not in zoom_label
    assert "color: #6e6e73;" in _rule(".dws-appbar-sub")
    for sel in (".dws-tab-x", ".dws-tab-dup"):
        r = _rule(sel)
        assert "width: 24px;" in r and "height: 24px;" in r and "color: #6e6e73;" in r, sel
    assert "word-break: keep-all;" in _rule(".dws-help-card")
    assert "font-size: 12px;" in _rule(".dws-help-list kbd")
    help_btn = _rule(".dws-appbar-right .dws-zoom .dws-help-btn")
    assert "width: 32px;" in help_btn and "height: 32px;" in help_btn and "border: 1px solid" in help_btn


def test_coarse_pointer_targets_40px():
    block = CSS.split("@media (pointer: coarse) {")[-1].split("\n}\n", 1)[0]
    for needle in (".dws-appbar-right .dws-btn { min-height: 40px; }",
                   ".dws-mt-btn { min-width: 40px; }",
                   ".dws-help-close { width: 40px; height: 40px; }",
                   ".dws-tab { min-height: 40px;"):
        assert needle in block, needle


# ---- wizard.js 연결 ----------------------------------------------------------

def test_wizard_js_hooks():
    mini = _fn_slice(JS, "function positionMiniToolbar() {")
    assert "placeFloatingBar(els.mt," in mini and "window.innerWidth" not in mini
    assert "placeFloatingBar(els.alignToolbar," in _fn_slice(JS, "function positionAlignToolbar() {")
    assert "placeFloatingBar(els.mt," in _fn_slice(JS, "function positionEditToolbar() {")
    place = _fn_slice(JS, "function placeFloatingBar(el, anchor, lift) {")
    assert "C.placeFloating(el, anchor, lift, els.canvas, [document.getElementById('dws-calc'), els.products])" in place
    assert "if (els.toolsMenu) { els.toolsMenu.hidden = true; }" in _fn_slice(JS, "function closeMenus() {")
    assert "initToolsMenu({ toggleMenu: toggleMenu, closeMenus: closeMenus })" in JS
    assert "FomsWizardChrome.toastMs(msg)" in _fn_slice(JS, "function toast(msg, opts) {")
    assert "watchLayout(" in JS


# ---- wizard-chrome.js 동작(node) ----------------------------------------------

def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def test_chrome_js_syntax_and_size():
    proc = subprocess.run([_node(), "--check", str(CHROME)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert len(CHROME.read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


RUNNER = r"""
global.window = { innerWidth: 820, innerHeight: 1180 };
const byId = {};
global.document = { getElementById: (id) => byId[id] || null };
require(process.argv[1]);
const C = window.FomsWizardChrome;

function el(id, props) {
  const on = {};
  const o = Object.assign({
    id, hidden: false, disabled: false, attrs: {}, style: {}, clicks: 0, cls: [],
    classList: { contains: (c) => o.cls.indexOf(c) >= 0 },
    getAttribute: (k) => (k in o.attrs ? o.attrs[k] : null),
    setAttribute: (k, v) => { o.attrs[k] = String(v); },
    addEventListener: (t, fn) => { (on[t] = on[t] || []).push(fn); },
    click: () => { if (o.disabled) { return; } o.clicks += 1; (on.click || []).forEach((fn) => fn({ stopPropagation() {} })); },
  }, props || {});
  if (id) { byId[id] = o; }
  return o;
}

const out = {};
out.toast = ['', 'x'.repeat(25), 'x'.repeat(50), 'x'.repeat(200), null].map(C.toastMs);

const base = { left: 0, top: 100, right: 1000, bottom: 800 };
out.shrinkCalc = C.shrinkBounds(base, [{ left: 660, top: 52, right: 1000, bottom: 800 }]);
out.shrinkDrawerClosed = C.shrinkBounds(base, [{ left: -300, top: 0, right: 0, bottom: 800 }, null]);
out.shrinkDrawerOpen = C.shrinkBounds(base, [{ left: 0, top: 0, right: 300, bottom: 800 }]);
out.shrinkMiddle = C.shrinkBounds(base, [{ left: 400, top: 300, right: 600, bottom: 500 }]);

const vis = { left: 0, top: 100, right: 660, bottom: 800 };
const bar = { w: 400, h: 40 };
out.placeRightEnd = C.placeBar({ left: 600, top: 400, bottom: 500 }, bar, vis, 34);
out.placeBelow = C.placeBar({ left: 100, top: 120, bottom: 300 }, bar, vis, 34);
out.placeHuge = C.placeBar({ left: 100, top: 90, bottom: 790 }, bar, vis, 34);
out.placeOffBelow = C.placeBar({ left: 100, top: 900, bottom: 1000 }, bar, vis, 34);
out.placeWide = C.placeBar({ left: 300, top: 400, bottom: 500 }, { w: 700, h: 40 }, vis, 0);

// 세로 태블릿: 계산 칸이 캔버스 오른쪽을 덮는다(position: fixed) → 막대는 계산 칸 왼쪽 8px 안
const canvas = el('dws-canvas', { clientLeft: 0, clientTop: 0, clientWidth: 805, clientHeight: 1070,
  getBoundingClientRect: () => ({ left: 0, top: 96, right: 820, bottom: 1180 }) });
const calc = el('dws-calc', { getBoundingClientRect: () => ({ left: 460, top: 0, right: 820, bottom: 1180 }) });
const mt = el('dws-minitoolbar', { offsetWidth: 300, offsetHeight: 44 });
C.placeFloating(mt, { left: 700, top: 500, bottom: 600 }, 34, canvas, [calc]);
out.floating = Object.assign({}, mt.style);
calc.hidden = true;   // 닫힌 계산 칸은 빼지 않는다(스크롤 막대 15px 는 뺀다)
C.placeFloating(mt, { left: 700, top: 500, bottom: 600 }, 34, canvas, [calc]);
out.floatingNoCalc = Object.assign({}, mt.style);

// 도구 ▾: 메뉴 항목은 원래 단추를 눌러 준다
const tools = el('dws-btn-tools');
const items = ['dws-btn-autofill', 'dws-btn-arrange', 'dws-btn-calc', 'dws-btn-font-dec'].map((t) => el(null, { attrs: { 'data-tools-for': t } }));
const menu = el('dws-tools-menu', { hidden: true, querySelectorAll: () => items });
const autofill = el('dws-btn-autofill');
const arrange = el('dws-btn-arrange', { disabled: true });           // 열람 전용 — 잠김
const calcBtn = el('dws-btn-calc', { attrs: { 'aria-expanded': 'true' } });
el('dws-btn-font-dec', { hidden: true });                             // 없는(숨은) 단추
let closed = 0;
out.init = C.initToolsMenu({ toggleMenu: (m) => { m.hidden = !m.hidden; }, closeMenus: () => { closed += 1; menu.hidden = true; } });
tools.click();
out.afterOpen = { menuHidden: menu.hidden, expanded: tools.attrs['aria-expanded'],
  arrangeDisabled: items[1].disabled, calcPressed: items[2].attrs['aria-pressed'], fontHidden: items[3].hidden,
  autofillHidden: items[0].hidden };
items[0].click();
items[1].click();
items[2].click();
out.afterItems = { autofill: autofill.clicks, arrange: arrange.clicks, calc: calcBtn.clicks, closed,
  menuHidden: menu.hidden, expanded: tools.attrs['aria-expanded'] };
out.initMissing = (delete byId['dws-tools-menu'], C.initToolsMenu({ toggleMenu: () => {} }));
process.stdout.write(JSON.stringify(out));
"""


def _run():
    proc = subprocess.run([_node(), "-e", RUNNER, str(CHROME)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_toast_duration_min_4s_and_grows_with_length():
    res = _run()
    assert res["toast"] == [4000, 4000, 6000, 12000, 4000]


def test_visible_bounds_subtract_calc_and_open_drawer_only():
    res = _run()
    assert res["shrinkCalc"] == {"left": 0, "top": 100, "right": 660, "bottom": 800}
    assert res["shrinkDrawerClosed"] == {"left": 0, "top": 100, "right": 1000, "bottom": 800}
    assert res["shrinkDrawerOpen"]["left"] == 300
    assert res["shrinkMiddle"] == {"left": 0, "top": 100, "right": 1000, "bottom": 800}


def test_bar_stays_inside_visible_canvas():
    res = _run()
    # 오른쪽 끝 그림: 계산 칸 왼쪽(660) 8px 안 = 660 - 400 - 8, 그림 위(회전 손잡이 34px 더 위)
    assert res["placeRightEnd"] == {"left": 252, "top": 400 - 40 - 8 - 34}
    assert res["placeBelow"] == {"left": 100, "top": 308}        # 위가 모자라면 그림 아래
    assert res["placeHuge"]["top"] == 108                        # 둘 다 모자라면 보이는 칸 맨 위
    assert res["placeOffBelow"]["top"] == 800 - 40 - 8           # 그림이 아래로 벗어나면 보이는 칸 맨 아래
    assert res["placeWide"]["left"] == 8                         # 막대가 더 넓으면 왼쪽 가장자리부터


def test_floating_bar_clamps_left_of_overlay_calc_and_caps_width():
    res = _run()
    f = res["floating"]
    assert f["maxWidth"] == "444px"            # 보이는 폭 460 - 16 → 모자라면 두 줄로 접힌다
    assert f["left"] == "152px"                # 460 - 300 - 8
    assert f["top"] == f"{500 - 44 - 8 - 34}px"
    g = res["floatingNoCalc"]
    assert g["left"] == f"{805 - 300 - 8}px"   # 닫힌 계산 칸은 빼지 않고, 캔버스 스크롤 막대(15px)는 뺀다
    assert g["maxWidth"] == f"{805 - 16}px"


def test_tools_menu_clicks_original_buttons_and_mirrors_state():
    res = _run()
    assert res["init"] is True
    assert res["afterOpen"] == {"menuHidden": False, "expanded": "true", "arrangeDisabled": True,
                                "calcPressed": "true", "fontHidden": True, "autofillHidden": False}
    # 자동 채움·자재표 계산은 원래 단추가 눌리고, 잠긴 자동 배치 항목은 잠겨 눌리지 않는다(메뉴 닫기도 2번뿐).
    assert res["afterItems"] == {"autofill": 1, "arrange": 0, "calc": 1, "closed": 2,
                                 "menuHidden": True, "expanded": "false"}
    assert res["initMissing"] is False


# ---- part-status.js: 템플릿의 칩 묶음을 그대로 쓴다(상태 칩 자리, 2026-10-25 실화면 확인 V1) ----------

STATUS_BOX_RUNNER = r"""
const reg = {};
function el(tag) {
  return { tagName: tag.toUpperCase(), className: '', hidden: false, title: '', children: [], attrs: {}, ls: {}, textContent: '',
    scrollWidth: 0, clientWidth: 0,
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    insertBefore(c, ref) { c.parentNode = this; this.children.splice(this.children.indexOf(ref), 0, c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, addEventListener(t, f) { (this.ls[t] = this.ls[t] || []).push(f); },
    set id(v) { this.attrs.id = v; reg[v] = this; }, get id() { return this.attrs.id; } };
}
global.window = {};
global.document = { createElement: el, createElementNS: (ns, t) => el(t), getElementById: (id) => reg[id] || null };
require(process.argv[1]);
const right = el('div'), box = right.appendChild(el('span')), save = right.appendChild(el('span'));
box.id = 'dws-part-status'; box.className = 'dws-part-status'; save.id = 'dws-save-status';
const St = window.FomsPartStatus;
St.init(save, {});
const snap = () => ({ box: box.hidden, kids: box.children.map((k) => [k.className.split(' ').pop(), k.hidden]) });
const out = { siblings: right.children.length, first: snap() };
St.progress(3, 8, {}); St.paint(0, 0, false); out.busyOnly = snap();      // 알아보는 중만 — 묶음은 보이고(칩이 떠서 보임)
St.progress(0, 0, {}); St.paint(2, 3, false); out.unsure = snap();       // 0.8초 안에 끝나 'N/N' 이 남아 있다
process.stdout.write(JSON.stringify(out));
"""


def test_part_status_reuses_template_box_in_fixed_order():
    proc = subprocess.run([_node(), "-e", STATUS_BOX_RUNNER, str(ROOT / "static/js/drawing/part-status.js")],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    assert res["siblings"] == 2                                   # 새 묶음을 만들지 않고 템플릿 것을 채운다
    order = ["dws-part-status-busy", "dws-part-status-unsure", "dws-part-status-eye"]
    assert res["first"] == {"box": True, "kids": [[k, True] for k in order]}
    # 순서는 [알아보는 중(떠 있음)] [미분류] [딱지 단추] 그대로 — CSS 가 오른쪽(저장 칩 쪽)부터 붙인다
    assert res["busyOnly"] == {"box": False, "kids": [[order[0], False], [order[1], True], [order[2], True]]}
    assert res["unsure"]["kids"][1:] == [[order[1], False], [order[2], False]]
