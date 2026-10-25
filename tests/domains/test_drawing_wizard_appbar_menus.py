"""도면 마법사 앱바 — 메뉴 Esc 닫기 · 옆으로 미는 줄의 메뉴 자리 · 도구 이름 맞춤 · 글자 대비(2026-10-25 실화면 QA).

- '도구 ▾'·프리셋 메뉴가 Esc 로 닫히지 않았다(도움말은 'Esc … 창 닫기') → 닫고 초점을 단추로.
- 901~1179px·≤900px 의 fixed 메뉴가 단추가 아니라 화면 오른쪽 끝에 열렸다(1024: 단추 x373, 메뉴 x864) → 단추 왼쪽에 맞춘다.
- 2399px 이하 도구 이름 숨김 때문에 1920 에서도 이름이 다 사라졌다 → 남는 자리를 재서 다 / '선택'·'텍스트'만 / 그림만.
- 미니 막대 '삭제' 글자 대비 4.49(기준 4.5) · 820 세로에서 제목 앞말이 남아 줄이 길어짐.

동작은 wizard-appbar.js 를 node 로 돌려 본다(가짜 DOM·가짜 배치).
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
APPBAR = ROOT / "static/js/drawing/wizard-appbar.js"
APPBAR_SRC = APPBAR.read_text(encoding="utf-8")


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _luminance(hex6: str) -> float:
    def ch(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(fg: str, bg: str) -> float:
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _over(fg: tuple, alpha: float, bg: tuple) -> tuple:
    return tuple(alpha * f + (1 - alpha) * b for f, b in zip(fg, bg))


# ---- 문자열 계약 ---------------------------------------------------------------

def test_appbar_script_loads_before_wizard_and_is_wired():
    tag = re.search(r'<script src="[^"]*wizard-appbar\.js[^"]*"[^>]*>', TPL)
    assert tag and "?v=" in tag.group(0) and " defer" in tag.group(0)
    assert TPL.index("js/drawing/wizard-appbar.js") < TPL.index("js/drawing/wizard.js')")
    assert "window.FomsWizardAppbar.init({ closeMenus: closeMenus })" in JS
    # Esc 는 잡는 단계(capture)에서 — 마법사 Esc(그림 선택 풀기)보다 먼저 메뉴를 닫는다
    init = APPBAR_SRC.split("function init(opts) {", 1)[1]
    assert "document.addEventListener('keydown'" in init and "}, true);" in init


def test_appbar_js_syntax_and_size():
    proc = subprocess.run([_node(), "--check", str(APPBAR)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert len(APPBAR_SRC.splitlines()) < 300   # 새 JS 300줄 래칫


def test_seg_names_css_states():
    for sel in ('.dws-appbar[data-seg-names="all"] .dws-seg-label',
                '.dws-appbar[data-seg-names="two"] #dws-btn-select .dws-seg-label',
                '.dws-appbar[data-seg-names="two"] #dws-btn-add-text .dws-seg-label'):
        assert sel in CSS, sel
    assert '.dws-appbar[data-seg-names="none"] .dws-seg-label { display: none; }' in CSS


def test_title_prefix_hidden_on_portrait_too():
    # 900px 이하(옆으로 미는 줄)도 '도면 마법사 · ' 를 뺀다 — min-width: 901px 덩어리에만 있으면 820 에서 남는다
    m = re.search(r"@media \(max-width: 2399px\) \{\s*\.dws-appbar-title-prefix \{ display: none; \}", CSS)
    assert m
    assert not re.search(r"@media \(min-width: 901px\) and \(max-width: 2399px\) \{\s*\.dws-appbar-title-prefix", CSS)


def test_minitoolbar_delete_contrast_meets_4_5():
    m = re.search(r"\.dws-mt-del \{ color: #([0-9a-fA-F]{6}); \}", CSS)
    assert m
    fg = m.group(1)
    assert _contrast(fg, "555557") >= 4.5                     # QA 가 잰 단추 바탕
    bar = _over((30, 30, 32), 0.85, (255, 255, 255))            # 흰 도면 위 반투명 막대(rgba(30,30,32,.85))
    btn = _over((255, 255, 255), 0.12, bar)                     # 단추 바탕 rgba(255,255,255,.12)
    btn_hex = "".join(f"{round(v):02x}" for v in btn)
    assert _contrast(fg, btn_hex) >= 4.5


# ---- 동작(node) ----------------------------------------------------------------

RUNNER = r"""
const cs = new Map();
global.window = { innerWidth: 1024, getComputedStyle: (el) => cs.get(el) || {} };
let active = null;
global.document = {
  get activeElement() { return active; },
  createRange: () => ({ el: null, selectNodeContents(e) { this.el = e; }, getBoundingClientRect() { return { width: (this.el && this.el.textW) || 0 }; } }),
};
require(process.argv[1]);
const A = window.FomsWizardAppbar;
const out = {};

// fixed 메뉴 왼쪽 자리
out.left = [A.menuLeft(373, 152, 1024), A.menuLeft(528, 150, 820), A.menuLeft(1284, 152, 820), A.menuLeft(2, 100, 1024)];

function menuWith(btnLeft, pos, w) {
  const btn = { tagName: 'BUTTON', focused: 0, focus() { btn.focused += 1; active = btn; }, getBoundingClientRect: () => ({ left: btnLeft }) };
  const menu = { hidden: false, style: { left: 'x', right: 'y' }, offsetWidth: w || 152, parentNode: { querySelector: (s) => (s === 'button' ? btn : null) } };
  cs.set(menu, { position: pos });
  return { menu, btn };
}
let m = menuWith(373, 'fixed');
A.placeMenu(m.menu);
out.fixed = Object.assign({}, m.menu.style);
window.innerWidth = 820;
m = menuWith(1284, 'fixed');
A.placeMenu(m.menu);
out.offRight = Object.assign({}, m.menu.style);
m = menuWith(373, 'absolute');
A.placeMenu(m.menu);
out.absolute = Object.assign({}, m.menu.style);
m = menuWith(373, 'fixed');
m.menu.hidden = true;
A.placeMenu(m.menu);
out.hidden = Object.assign({}, m.menu.style);

// Esc
function ev(key) { return { key, prevented: 0, stopped: 0, preventDefault() { this.prevented += 1; }, stopPropagation() { this.stopped += 1; } }; }
const tools = menuWith(373, 'fixed'), preset = menuWith(500, 'fixed');
preset.menu.hidden = true;
let closed = 0;
const closeAll = () => { closed += 1; tools.menu.hidden = true; preset.menu.hidden = true; };
active = tools.btn;
let e = ev('Escape');
out.esc = { ret: A.closeMenuByEsc(e, [tools.menu, preset.menu], closeAll), prevented: e.prevented, stopped: e.stopped,
  closed, toolsHidden: tools.menu.hidden, focused: tools.btn.focused };
e = ev('Escape');
out.escNone = { ret: A.closeMenuByEsc(e, [tools.menu, preset.menu], closeAll), prevented: e.prevented, closed };
tools.menu.hidden = false;
e = ev('a');
out.otherKey = { ret: A.closeMenuByEsc(e, [tools.menu], closeAll), hidden: tools.menu.hidden };
active = { isContentEditable: true, tagName: 'DIV' };   // 글 편집 중 편집 막대 프리셋 메뉴
const mt = menuWith(300, 'absolute');
e = ev('Escape');
out.typing = { ret: A.closeMenuByEsc(e, [mt.menu], () => { mt.menu.hidden = true; }), hidden: mt.menu.hidden, focused: mt.btn.focused };

// 도구 이름 맞춤 — 1920 실측(QA2): 왼쪽 칸 378.67(이름 없음·칩 없음), 왼쪽 최소 175(나가기 91 + 틈 8 + 제목 76).
// 새 격자(2026-10-25 실화면 확인 V1): 왼쪽 칸 상한은 제목 글 폭(--dws-left-w = 나가기·틈 99 + 글 폭 + 1)이고
// 남는 자리는 오른쪽 묶음 앞(가운데 도구 묶음 뒤)에 남는다. chip = 오른쪽 묶음이 더 쓰는 폭.
const EXTRA = { all: 242, two: 77, none: 0 };
function bar(vw, chip, subW, display, titleW) {
  const attrs = {}, props = {};
  const b = {
    getAttribute: (k) => (k in attrs ? attrs[k] : null), setAttribute: (k, v) => { attrs[k] = String(v); }, removeAttribute: (k) => { delete attrs[k]; },
    getBoundingClientRect: () => ({ right: vw }),
    style: { setProperty: (k, v) => { props[k] = v; }, removeProperty: (k) => { delete props[k]; } }, props,
  };
  const room = () => 378.67 + (vw - 1920) - (EXTRA[attrs['data-seg-names']] || 0) - chip;   // 왼쪽 칸 + 빈 자리에 줄 수 있는 폭
  const leftMax = () => ('--dws-left-w' in props ? parseFloat(props['--dws-left-w']) : Infinity);
  const leftCol = () => Math.max(175, Math.min(room(), leftMax()));
  const spare = () => Math.max(0, room() - leftCol());
  const left = { getBoundingClientRect: () => ({ left: 12 }) };
  const wrap = { get clientWidth() { return leftCol() - 99; }, getBoundingClientRect: () => ({ left: 12 + 99 }) };
  const rightLeft = () => 12 + leftCol() + 600;   // 오른쪽 묶음 왼쪽 끝(빈 자리만 본다 — 값은 아무것이나)
  const right = {
    children: [{ getBoundingClientRect: () => ({ left: 0, width: 0 }) },   // 숨은 단추(넓은 화면의 '도구 ▾')는 건너뛴다
      { getBoundingClientRect: () => ({ left: rightLeft() + spare(), width: 80 }) }],
    getBoundingClientRect: () => ({ left: rightLeft(), right: vw - 12 + Math.max(0, 175 - room()) }),
  };
  // 제목은 칸(블록) 폭을 다 쓴다 — 말줄임으로 잘리면 글자 범위는 보이는 몫만 잡힐 수 있어 scrollWidth 로 글 전체 폭을 본다
  const tw = titleW || 73;
  const title = { get clientWidth() { return wrap.clientWidth; }, get scrollWidth() { return Math.max(wrap.clientWidth, tw); },
    get textW() { return Math.min(tw, wrap.clientWidth); } };
  const parts = { '.dws-appbar-left': left, '.dws-appbar-titlewrap': wrap, '.dws-appbar-right': right,
    '.dws-appbar-title': title, '.dws-appbar-sub': { textW: subW == null ? 60 : subW } };
  b.querySelector = (s) => parts[s] || null;
  cs.set(b, { display: display || 'grid', paddingRight: '12px' });
  return b;
}
const pick = (b) => [A.fitSegNames(b), b.getAttribute('data-seg-names')];
const from = (b, step) => { b.setAttribute('data-seg-names', step); return pick(b); };
out.fit1920 = pick(bar(1920, 0));
out.fit1920busy = pick(bar(1920, 176));      // 오른쪽이 176px 더 쓰면(예전 '그림 종류 알아보는 중' 칩 170 + 틈 6)
out.fit1920unsure = pick(bar(1920, 106, 150));  // '미분류' 칩 + 긴 고객명(다섯 글자 몫만 남긴다)
out.fit1920tight = pick(bar(1920, 140));
out.fit2560 = pick(bar(2560, 0));
out.fit5digit = pick(bar(1920, 126.67, 60, 'grid', 81));   // '주문 #12345'(81px): 칸이 최소 76px 로 눌려 잘리면 이름을 접는다
const strip = bar(1024, 0, 60, 'flex');
strip.setAttribute('data-seg-names', 'two');
strip.props['--dws-left-w'] = '176px';
out.fitStrip = pick(strip).concat([Object.keys(strip.props)]);
// 되돌림 문턱(HYST 16px): 'two' 로 펴면 빈 자리가 5.67px 만 남는 폭 — 처음 잴 때는 펴고, 접혀 있었으면 그대로 둔다
out.hystFresh = pick(bar(1920, 120));
out.hystHold = from(bar(1920, 120), 'none');
out.hystOpen = from(bar(1920, 100), 'none');     // 빈 자리 25.67px ≥ 16 → 편다
out.hystKeep = from(bar(1920, 120), 'two');      // 지금 단계는 여유 없이도 그대로
out.hystFold = from(bar(1920, 176), 'two');      // 넘치면 바로 접는다
out.hystAll = from(bar(2560, 0), 'two');         // 넉넉하면 다 편다
// 긴 고객명(150px)은 남는 자리를 제목 칸이 먼저 가져간다 — 고객명이 다섯 글자 몫까지 줄 수 있는 폭도 여유로 센다
out.hystLongSub = [from(bar(1920, 100, 150), 'none'), from(bar(1920, 120, 150), 'none')];
// 제목 칸 상한(--dws-left-w): 나가기·틈 99 + 주문 번호·고객명 중 긴 글(최소 76) + 1
const lb = bar(1920, 0, 150);
out.leftCap = [A.fitLeft(lb), lb.props['--dws-left-w'], A.fitLeft(bar(1920, 0)), A.fitLeft({ querySelector: () => null })];
const fb = bar(1920, 0, 150);
A.fitSegNames(fb);
out.leftViaFit = fb.props['--dws-left-w'];

// init 연결: 잡는 단계 keydown 하나 — 메뉴가 열려 있으면 Esc 로 닫고, 대화 상자·도움말이 떠 있으면 그쪽 몫으로 둔다
const reg = [];
let over = null, closedByInit = 0;
const t2 = menuWith(373, 'fixed');
document.getElementById = (id) => (id === 'dws-tools-menu' ? t2.menu : null);
document.querySelector = (s) => (s.indexOf('dialog[open]') >= 0 ? over : null);
document.addEventListener = (type, fn, capture) => { reg.push({ type, fn, capture: capture === true }); };
window.addEventListener = () => {};
out.init = [A.init({ closeMenus: () => { closedByInit += 1; t2.menu.hidden = true; } }), A.init({})];
const kd = reg.filter((r) => r.type === 'keydown');
over = {};
kd[0].fn(ev('Escape'));
out.initOver = { closed: closedByInit, hidden: t2.menu.hidden };
over = null;
kd[0].fn(ev('Escape'));
out.initEsc = { listeners: kd.length, capture: kd[0].capture, closed: closedByInit, hidden: t2.menu.hidden };
process.stdout.write(JSON.stringify(out));
"""


def _run():
    proc = subprocess.run([_node(), "-e", RUNNER, str(APPBAR)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_fixed_menu_opens_under_its_button():
    res = _run()
    assert res["left"] == [373, 528, 660, 8]
    assert res["fixed"] == {"left": "373px", "right": "auto"}       # 1024: 단추 x373 바로 아래
    assert res["offRight"] == {"left": "660px", "right": "auto"}    # 820: 밀려난 단추 → 화면 밖이면 오른쪽 끝 8px 안
    assert res["absolute"] == {"left": "", "right": ""}             # 넓은 화면(absolute) 메뉴는 CSS 그대로
    assert res["hidden"] == {"left": "", "right": ""}               # 닫히면 손댄 자리를 지운다


def test_escape_closes_open_menu_and_returns_focus():
    res = _run()
    assert res["esc"] == {"ret": True, "prevented": 1, "stopped": 1, "closed": 1, "toolsHidden": True, "focused": 1}
    # 열린 메뉴가 없으면 손대지 않는다(마법사 Esc 가 그대로 그림 선택을 푼다)
    assert res["escNone"] == {"ret": False, "prevented": 0, "closed": 1}
    assert res["otherKey"] == {"ret": False, "hidden": False}
    # 글 편집 중이면 메뉴만 닫고 초점은 편집 칸에 둔다
    assert res["typing"] == {"ret": True, "hidden": True, "focused": 0}


def test_init_wires_one_capture_escape_listener():
    res = _run()
    assert res["init"] == [True, False]                                   # 한 번만 건다
    assert res["initOver"] == {"closed": 0, "hidden": False}              # 대화 상자·도움말이 떠 있으면 Esc 는 그쪽 몫
    assert res["initEsc"] == {"listeners": 1, "capture": True, "closed": 1, "hidden": True}


def test_seg_names_fit_the_room_left():
    res = _run()
    assert res["fit1920"] == ["two", "two"]            # 1920: '선택'·'텍스트' 이름은 남는다(다 두면 오른쪽이 밀린다)
    assert res["fit1920busy"] == ["none", "none"]      # 오른쪽이 자리를 먹으면 그림만 — 오른쪽 단추가 화면 밖으로 밀리지 않게
    assert res["fit1920unsure"] == ["two", "two"]
    assert res["fit1920tight"] == ["none", "none"]
    assert res["fit2560"] == ["all", "all"]
    assert res["fit5digit"] == ["none", "none"]        # 앱바는 안 넘쳐도 주문 번호가 잘리면 이름을 접는다
    assert res["fitStrip"] == ["", None, []]           # 옆으로 미는 줄(grid 아님)은 속성·제목 칸 상한을 지워 CSS 폭 단계(그림만)


def test_seg_names_hysteresis_keeps_step_at_the_edge():
    """2026-10-25 실화면 확인 V1: 잠깐 뜨는 칩 때문에 이름 단계가 바뀌어 단추가 밀렸다 → 다시 펴는 쪽은 16px 여유가 있어야."""
    res = _run()
    assert res["hystFresh"] == ["two", "two"]          # 처음 잴 때는 들어가면 편다
    assert res["hystHold"] == ["none", "none"]         # 접혀 있었으면 빈 자리 5.67px(< 16)로는 다시 펴지 않는다
    assert res["hystOpen"] == ["two", "two"]           # 빈 자리 25.67px 면 편다
    assert res["hystKeep"] == ["two", "two"]           # 지금 단계는 여유 없이도 그대로
    assert res["hystFold"] == ["none", "none"]         # 넘치면 바로 접는다(단추가 화면 밖으로 밀리면 안 된다)
    assert res["hystAll"] == ["all", "all"]
    # 긴 고객명: 빈 자리는 0 이어도 제목 칸이 30px 더 줄 수 있으면 편다 · 10px 이면 그대로
    assert res["hystLongSub"] == [["two", "two"], ["none", "none"]]


def test_left_column_cap_is_title_text_width():
    """제목 칸 상한(--dws-left-w) = [나가기]·틈 + 주문 번호·고객명 중 긴 글(최소 76px) + 1 — 남는 자리는 도구 묶음 뒤로."""
    res = _run()
    assert res["leftCap"] == [250, "250px", 176, 0]    # 긴 고객명 150px · 짧은 제목은 최소 76px · 못 재면 0(안 건드림)
    assert res["leftViaFit"] == "250px"                # fitSegNames 가 재기 전에 상한부터 맞춘다
    assert "grid-template-columns: minmax(min-content, var(--dws-left-w, 1fr)) auto minmax(max-content, 1fr);" in CSS
