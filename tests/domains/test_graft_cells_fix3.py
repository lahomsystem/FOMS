"""접목판 남은 화면 흠 고침(점검 3차, 11-15) — 태블릿 작업 표 옆 밀기 · 폰 카드 칩 묶음 · PC 칩 큰 글자 · 레일 강조 칸 · 옛 브라우저.

원장 docs/plans/2026-11-14-foms-graft-plan.md '점검 2차 고치기 기록' 아래 '남은 것 · 알려 둘 것'. 화면 잰 값(고치기 전 · 뒤)은
스크래치패드 audit2/fix3-cells 에 있고, 여기서는 그 고침이 되돌아가지 않게 꾸밈 · 템플릿 · 스크립트 동작을 지킨다.
지어낸 자료만 · 바깥으로 보내지 않는다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from tests.domains.test_graft_cells import ROOT, _pages, _switch, world  # noqa: F401 — world 는 pytest 고정물

NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
CELLS_CSS = ROOT / "static/css/components/foms-graft-cells.css"
LANDSCAPE_CSS = ROOT / "static/css/foundation/foms-tablet-landscape.css"
RAIL_NAV_JS = ROOT / "static/js/foms/tablet-rail-nav.js"


def _rule(css: str, selector: str) -> str:
    return re.search(r"(?:^|\n)" + re.escape(selector) + r" \{(.*?)\}", css, re.S).group(1)


# --- C1 태블릿 작업 표: 넘친 칸은 표 상자 안에서 옆으로 민다 --------------------------------------------------


def test_tablet_workqueue_box_scrolls_sideways_instead_of_cutting_columns():
    """화면 크기 110 ~ 130% · 글자 130 · 150% 에서 표(가장 좁은 폭 663px)가 상자보다 넓어 오른쪽 칸(실측일 ~ 첨부)이 잘린 채 볼 길이
    없었다(overflow: hidden — 스위치를 끈 화면도). 상자만 가로로 굴리고(위아래는 지금처럼 자름 · 뒤로 가기 몸짓으로 안 번짐) 쪽 번호
    줄은 제자리. 칸을 감추거나 글자를 줄이지 않는다 — 날짜 · 담당 칸은 꺾지 않는 그대로."""
    css = LANDSCAPE_CSS.read_text(encoding="utf-8")
    wrap = _rule(css, ".foms-tablet-workqueue-wrap")
    assert "overflow-x: auto;" in wrap and "overflow-y: hidden;" in wrap and "overflow: hidden;" not in wrap
    assert "overscroll-behavior-x: contain;" in wrap and "border-radius: var(--foms-radius-lg, 12px);" in wrap
    pager = _rule(css, ".foms-tablet-workqueue-wrap > .foms-tqgrid-pager")
    assert "position: sticky;" in pager and "left: 0;" in pager
    grid = (ROOT / "templates/orders/partials/tablet_workqueue_grid.html").read_text(encoding="utf-8")
    assert 'class="mt-4 mb-2 d-flex flex-column align-items-center foms-tqgrid-pager"' in grid
    ship = (ROOT / "static/css/contexts/shipment/tablet-day-sheet.css").read_text(encoding="utf-8")
    ship_wrap = ship[ship.index("body.erp-mobile-v2-layout .foms-tablet-shipgrid-wrap {"):]
    assert "overflow: visible;" in ship_wrap[:ship_wrap.index("}")]  # 같은 상자 꼬리표를 쓰는 출고 표는 그대로 펼침
    nowrap = _rule(css, ".foms-tqcell-date,\n.foms-tqcell-manager")
    assert "white-space: nowrap;" in nowrap
    assert "display: none" not in css[css.index(".foms-tqcell-date,"):css.index("/* 첨부 — 우측 정렬")]
    bundle = (ROOT / "static/css/foundation/foms-tablet-bundle.css").read_text(encoding="utf-8")
    assert "foms-tablet-landscape.css?v=20261122w" in bundle  # 기기에 닿게 — 부모 핀은 layout_head 를 시험 다섯이 본다


# --- C2 폰 목록 카드: 칩 설 자리가 없으면 배지 밑으로(머리는 한 줄 높이) ------------------------------------------


def test_phone_card_head_wraps_badges_and_chip_in_one_box_with_the_chip_last(world, monkeypatch):
    """칩 자리와 함께만 묶음 상자 — 단계 배지는 머리 줄의 자식 그대로(실측 압축 시트가 '머리 > 단계 배지'로 고른다), 그 뒤 배지들과
    맨 끝 칩이 묶음 안. 칩이 숨으면 상자가 없고(display: contents), 보이면 남는 폭을 다 맡는 줄바꿈 상자(줄 사이 0 — 배지 줄 둘이
    이력 단추 44px 안)."""
    _switch(monkeypatch, "999999", "brain_ui", "actions", "cell_mobile")
    queue = _pages(world, monkeypatch)["queue"]
    for oid in world["orders"]:
        card = queue[queue.index(f'<article class="queue-card foms-queue-card-v2" data-order-id="{oid}"'):]
        head = card[card.index("<header"):card.index("</header>")]
        assert re.search(r'<span class="foms-stage-badge [^"]*">[^<]*</span>\s*<span class="foms-graft-chip-row">', head), oid
        box = head[head.index('<span class="foms-graft-chip-row">'):]
        assert box.index(f'data-graft-slot="{oid}" data-graft-cell="mobile" hidden></a></span>') < box.index("queue-card__time")
        assert head.count("foms-graft-chip-row") == 1 and head.count("data-graft-slot=") == 1
    sheet_js = (ROOT / "static/js/measurement/mobile-glance-sheet-parts.js").read_text(encoding="utf-8")
    assert "'.foms-queue-card-v2__head > .foms-stage-badge'" in sheet_js  # 단계 배지를 묶음 밖에 두는 까닭
    css = CELLS_CSS.read_text(encoding="utf-8")
    assert "display: contents;" in _rule(css, ".foms-graft-chip-row")
    box_on = _rule(css, ".foms-graft-chip-row:has(> .foms-graft-chip:not([hidden]))")
    for piece in ("display: flex;", "flex: 1 1 0;", "flex-wrap: wrap;", "gap: 0 var(--foms-space-2, 8px);", "min-width: 0;"):
        assert piece in box_on, piece


def test_phone_card_template_cut_still_gives_today():
    """묶음 상자의 여닫는 두 덩이도 '오늘 판' 떼기 무늬로 떼어진다 — 끈 화면은 한 글자도 안 바뀐다(test_graft_cells 의 견주기가
    실제 그림으로 지킨다). 묶음 꼬리표는 칩 덩이에만."""
    from tests.domains.test_graft_cells import BLOCK

    source = (ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(encoding="utf-8")
    assert len(BLOCK.findall(source)) == 2
    cut = BLOCK.sub("", source)
    assert "graft" not in cut and "foms-graft-chip-row" not in cut


# --- C3 PC 칩: 글자 배율이 커 칸이 좁으면 테두리 안 여백 · 아이콘만 제 크기로 -----------------------------------------


def test_pc_chip_tightens_only_when_the_column_is_narrow_for_its_font():
    """1440 · 글자 130 · 150% 에서 칩 7개 모두 말줄임 — 대시보드 아이콘 규칙(.erp-dashboard .fas 0.95rem)이 로봇 아이콘을 칩 글보다
    키워 이름 자리를 먹었다. 칸이 칩 글자 11자 폭보다 좁을 때만(자리 상자 글자 = 칩 글자라 em 이 배율을 따른다) 여백 4px · 사이
    2px · 아이콘 0.85em. 글자 크기 · 칸 폭(자리 상자 폭 0) · 100% 모습은 그대로."""
    css = CELLS_CSS.read_text(encoding="utf-8")
    slot = _rule(css, ".foms-graft-chip-slot")
    assert "width: 0; min-width: 100%;" in slot and "font-size: calc(14px * var(--foms-fs, 1));" in slot
    block = css[css.index("@container (max-width: 11em) {"):]
    block = block[:block.index("\n}")]
    assert '.foms-graft-chip-slot > .foms-graft-chip[data-graft-cell="pc"] { gap: 2px; padding-right: 4px; padding-left: 4px; }' in block
    assert '.foms-graft-chip-slot > .foms-graft-chip[data-graft-cell="pc"] > .foms-graft-chip__icon { font-size: 0.85em; }' in block
    assert "font-size: calc(14px * var(--foms-fs, 1));" in _rule(css, ".foms-graft-chip")  # 칩 글은 줄이지 않는다
    grid = (ROOT / "static/css/contexts/orders/dashboard-grid.css").read_text(encoding="utf-8")
    assert re.search(r"\.erp-dashboard \.fas,\s*\.erp-dashboard \.far \{\s*font-size: 0\.95rem;", grid)  # 이긴 까닭(특이도 0,2,0)


# --- C5 옛 브라우저: 컨테이너 기준 배치를 모르면 좁은 칸 모습 ------------------------------------------------------


def test_old_browsers_without_container_queries_hide_the_head_word():
    css = CELLS_CSS.read_text(encoding="utf-8")
    assert re.search(r"@supports not \(container-type: inline-size\) \{\s*\.foms-graft-chip__head \{ display: none; \}\s*\}", css)
    assert re.search(r"@container \(max-width: 199\.98px\) \{\s*\.foms-graft-chip__head \{ display: none; \}", css)  # 새 브라우저 갈림 그대로


# --- C4 태블릿 레일: 강조 칸이 굴림 영역 밖이면 그 칸이 보이게 묶음만 굴린다 ---------------------------------------------

RAIL_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const L = input.layout;  // 보이는 px: 묶음 위 끝 · 높이, 배율(rect = 배율 전 px × zoom)
let observer = null;
const listeners = {};
function classes(node) {
  return { contains: c => node.cls.has(c), add: c => node.cls.add(c), remove: c => node.cls.delete(c) };
}
const menu = { scrollTop: 0, top: L.menuTop, h: L.menuH, zoom: L.zoom, kids: [], assigns: [] };
let st = 0;
Object.defineProperty(menu, 'scrollTop', {
  get: () => st,
  set: v => { menu.assigns.push(v); const max = Math.max(0, menu.scrollHeight - menu.clientHeight); st = Math.min(max, Math.max(0, Math.round(v))); },
});
Object.defineProperty(menu, 'clientHeight', { get: () => Math.round(menu.h / menu.zoom) });
Object.defineProperty(menu, 'offsetHeight', { get: () => Math.round(menu.h / menu.zoom) });
let reads = 0;  // 굴림 판정이 배치를 읽은 횟수(scrollHeight) — 안 보이는 레일은 화면 바꿀 때 늘지 않아야
Object.defineProperty(menu, 'scrollHeight', { get: () => { reads += 1; return menu.kids.reduce((a, k) => Math.max(a, k.y + k.ch), 0); } });
menu.getBoundingClientRect = () => ({ top: menu.top, bottom: menu.top + menu.h, height: menu.h });
menu.querySelector = sel => menu.kids.find(k => k.cls.has('is-active')) || null;
let y = 0;
input.items.forEach(([title, href, active]) => {
  const k = { title, href, y, ch: L.itemH, cls: new Set(['foms-tablet-rail__item']), attrs: {} };
  if (active) { k.cls.add('is-active'); k.attrs['aria-current'] = 'page'; }
  k.classList = classes(k);
  k.pathname = href;
  k.getAttribute = n => (n in k.attrs ? k.attrs[n] : null);
  k.setAttribute = (n, v) => { k.attrs[n] = String(v); };
  k.removeAttribute = n => { delete k.attrs[n]; };
  k.getBoundingClientRect = () => { const top = menu.top + (k.y - st) * menu.zoom; return { top, bottom: top + k.ch * menu.zoom }; };
  menu.kids.push(k);
  y += L.itemH + 4;
});
const rail = { querySelector: s => (s === '.foms-tablet-rail__menu' ? menu : null), querySelectorAll: () => menu.kids };
const win = {
  location: { pathname: input.path },
  addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
  ResizeObserver: class { constructor(fn) { this.fn = fn; observer = this; } observe() {} },
};
win.window = win;
win.document = {
  querySelector: s => (s === '.foms-tablet-rail' ? rail : null),
  addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
};
const ctx = vm.createContext(win);
vm.runInContext(fs.readFileSync(input.script, 'utf8'), ctx);
const seen = k => { const r = k.getBoundingClientRect(); const b = menu.getBoundingClientRect(); return r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5; };
const snap = tag => { const a = menu.kids.find(k => k.cls.has('is-active')); return [tag, a ? a.title : null, st, a ? seen(a) : null]; };
const out = [snap('load')];
for (const step of input.steps) {
  if (step[0] === 'path') { win.location.pathname = step[1]; (listeners['foms:erp-shell-fragment-swapped'] || []).forEach(fn => fn()); }
  if (step[0] === 'scroll') { st = step[1]; }
  if (step[0] === 'resize') { menu.h = step[1]; if (observer) observer.fn([]); }
  out.push(snap(step.join(':')).concat([reads]));
}
out.push(['assigns', menu.assigns.length]);
out.push(['reads', reads]);
process.stdout.write(JSON.stringify(out));
"""

RAIL_ITEMS = [("대시보드", "/erp/dashboard"), ("실측", "/erp/measurement"), ("도면", "/erp/drawing-workbench"),
              ("생산", "/erp/production/home"), ("출고", "/erp/shipment"), ("AS", "/erp/as"),
              ("시공", "/erp/construction/dashboard"), ("완료", "/erp/completion"), ("이력", "/erp/history"),
              ("계산기", "/wdcalculator")]


def _rail(path: str, active: str, steps: list, *, menu_h: float = 226.0, zoom: float = 1.3) -> list:
    """1176×626 · 130% 의 위 메뉴 묶음 꼴(잰 값: 묶음 176 ~ 402px, 칸 46px · 사이 4px — 10칸 중 3칸 남짓 보임)."""
    payload = {"script": str(RAIL_NAV_JS), "path": path, "layout": {"menuTop": 176.0, "menuH": menu_h, "zoom": zoom, "itemH": 46},
               "items": [[t, h, t == active] for t, h in RAIL_ITEMS], "steps": steps}
    out = subprocess.run(["node", "-e", RAIL_HARNESS], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


@NODE
def test_rail_reveals_the_server_highlighted_item_on_first_paint():
    """1176×626 · 130% 에서 시공 · 완료 · 이력 화면을 열면 강조 칸이 묶음 아래에 숨어 있었다(굴림 0) — 처음 그릴 때 그 칸 아래 끝이
    묶음 아래 끝에 닿게 굴린다."""
    got = _rail("/erp/history", "이력", [])
    assert got[0][0:2] == ["load", "이력"] and got[0][3] is True and got[0][2] > 0
    # 이미 보이는 칸(실측)이면 건드리지 않는다 — 굴림 값을 넣지도 않는다
    still = _rail("/erp/measurement", "실측", [])
    assert still[0] == ["load", "실측", 0, True] and still[-2] == ["assigns", 0]


@NODE
def test_rail_reveals_the_item_when_the_highlight_moves_and_when_the_menu_shrinks():
    got = _rail("/erp/measurement", "실측", [["path", "/erp/construction/dashboard"], ["scroll", 300], ["path", "/erp/dashboard"],
                                             ["path", "/erp/completion"], ["resize", 120]])
    by = {row[0]: row for row in got}
    assert by["path:/erp/construction/dashboard"][1] == "시공" and by["path:/erp/construction/dashboard"][3] is True
    assert by["path:/erp/dashboard"][1] == "대시보드" and by["path:/erp/dashboard"][2] == 0 and by["path:/erp/dashboard"][3] is True
    assert by["path:/erp/completion"][3] is True
    assert by["resize:120"][1] == "완료" and by["resize:120"][3] is True  # 회사 지식 칸이 나타나 묶음이 줄어도


@NODE
def test_rail_without_overflow_never_scrolls():
    """넘치지 않는 화면(1180×820 · 100% — 묶음 537px 이 칸 높이 합과 같다)은 한 번도 굴림 값을 넣지 않는다."""
    got = _rail("/erp/history", "이력", [["path", "/erp/completion"]], menu_h=600.0, zoom=1.0)
    assert got[0] == ["load", "이력", 0, True] and got[-2] == ["assigns", 0]


def test_rail_reveal_is_instant_and_menu_only():
    js = RAIL_NAV_JS.read_text(encoding="utf-8")
    body = js[js.index("function revealActive()"):js.index("function normalizePath")]
    assert "smooth" not in js and "scrollIntoView" not in js  # 부드러운 굴림 · 문서 굴림 없음
    assert "menu.scrollTop = " in body and "menu.scrollHeight <= menu.clientHeight" in body
    assert js.rstrip().endswith("})();") and "if (menuShown) {\n      revealActive();\n    }\n  }" in js  # syncActive 끝에서도 본다(레일이 보일 때만)
    assert "var menuShown = !!menu && menu.clientHeight > 0;" in js
    assert "new window.ResizeObserver(onMenuResize).observe(menu);" in js


@NODE
def test_hidden_rail_skips_the_reveal_on_swap_until_it_is_shown():
    """폰 · PC 는 레일이 display:none(묶음 높이 0) — 화면 바꿀 때마다 굴림 판정을 돌리면 막 들어온 새 화면을 통째로 다시
    배치시켰다(AS · CPU 4배 0.19초, 11-16). 안 보이면 바꿀 때 배치를 읽지 않고, 보이게 되면(ResizeObserver) 다시 본다."""
    got = _rail("/erp/measurement", "실측", [["path", "/erp/history"], ["path", "/erp/as"], ["resize", 226.0],
                                             ["path", "/erp/history"]], menu_h=0.0)
    swap1, swap2, shown, swap3 = got[1], got[2], got[3], got[4]
    assert swap1[1] == "이력" and swap2[1] == "AS"  # 강조는 그대로 옮긴다
    assert swap1[4] == swap2[4] and swap2[2] == 0  # 숨은 채 두 번 바꿔도 배치 읽기가 늘지 않는다
    assert shown[4] > swap2[4]  # 보이게 되면 다시 잰다
    assert swap3[1] == "이력" and swap3[3] is True and swap3[4] > shown[4]  # 이제는 바꿀 때마다 본다
    # 태블릿(보이는 레일)은 그대로 — 바꿀 때마다 판정한다
    tablet = _rail("/erp/measurement", "실측", [["path", "/erp/history"], ["path", "/erp/as"]])
    assert tablet[2][4] > tablet[1][4] > 0 and tablet[2][3] is True
