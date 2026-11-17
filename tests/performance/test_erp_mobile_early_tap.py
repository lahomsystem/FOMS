"""셸 첫 누름(11-16) · 아래 탭 높이 ResizeObserver 계약.

배경: 폰에서 화면이 보인 뒤 JS 가 묶이기 전(4배 CPU 0.7~1.4초) 더보기 · 검색 · 뒤로 · 달력 날 누름이 버려져
"두 번 눌러야" 했다(첫 누름 성공 0/5). `partials/shared/erp_mobile_early_tap.html` 인라인 스크립트가 하단 탭 바로 뒤에서
누름을 받아 뒤로 · 검색은 바로 처리하고, 서랍(Bootstrap) · 달력 날 · 상세 ⋯ 는 진짜 처리기가 묶이는 순간 한 번만 다시 누른다.
아래 탭 높이는 조각 교체마다 offsetHeight 를 읽던 것(AS 조각 강제 레이아웃 4배 0.98초)을 ResizeObserver 로 바꿨다.

동작 검사는 node vm 에 가짜 document 를 두고 스크립트를 돌린다(node 없으면 건너뜀). 각 검사에 음성 대조군을 둔다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EARLY = ROOT / "templates/partials/shared/erp_mobile_early_tap.html"
APP_SHELL = ROOT / "templates/partials/shared/foms_app_shell.html"
SHELL_JS = ROOT / "static/js/runtime/erp-mobile-shell.js"
SEARCH_JS = ROOT / "static/js/foms/search.js"
_NODE = shutil.which("node")
_SCRIPT_RE = re.compile(r'<script data-foms-run-once="erp-mobile-early-tap">(.*?)</script>', re.S)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _early_js() -> str:
    found = _SCRIPT_RE.findall(_read(EARLY))
    assert len(found) == 1, "셸 첫 누름 인라인 스크립트는 정확히 하나"
    return found[0]


def test_early_tap_is_inline_right_after_bottom_nav() -> None:
    """하단 탭 바로 뒤에 인라인(외부 src 아님 — 렌더 차단 가드 G1)으로, 문서당 한 번."""
    shell = _read(APP_SHELL)
    nav = shell.index("erp_mobile_bottom_nav.html")
    early = shell.index("erp_mobile_early_tap.html")
    assert nav < early < shell.index("htmx_layout.html") < shell.index("js/foms/search.js")
    html = _read(EARLY)
    assert "<script src" not in html and "src=" not in html.split("<script", 1)[1].split(">", 1)[0]
    js = _early_js()
    assert "window.__FOMS_EARLY_TAP_BOUND" in js
    assert "MAX_WAIT_MS = 4000" in js


def test_back_binding_in_mobile_shell_yields_to_early_tap() -> None:
    """뒤로는 첫 누름 스크립트가 맡는다 — erp-mobile-shell.js 는 그 스크립트가 없을 때만 묶는다(두 번 back 금지)."""
    js = _read(SHELL_JS)
    body = js.split("function initMobileShellBackButtons() {", 1)[1].split("\n  }\n", 1)[0]
    assert body.lstrip().startswith("if (window.__FOMS_EARLY_TAP_BOUND) {")


def test_search_takes_over_early_opened_dialog() -> None:
    js = _read(SEARCH_JS)
    assert "data-foms-early-open" in js and "takeOverEarlyOpen();" in js
    # 묶은 뒤(리스너 다음)에 이어받는다.
    assert js.index("window.__FOMS_SEARCH_OVERLAY_BOUND = true;") < js.index("takeOverEarlyOpen();\n})();")


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_early_tap_script_parses() -> None:
    proc = subprocess.run([_NODE, "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"], input=_early_js(),
                          capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr


_EARLY_HARNESS = r"""
const vm = require('vm');
const src = require('fs').readFileSync(0, 'utf8');
const scenario = process.argv[1];
let clock = 1000;
const docL = {}; const winL = {};
const log = { show: 0, back: 0, clicks: 0, modal: 0, nav: '', focus: 0 };
function el(sels, extra) {
  const e = Object.assign({ sels: new Set(sels), parent: null, isConnected: true, attrs: {} }, extra || {});
  e.closest = (s) => { for (let n = e; n; n = n.parent) { if (n.sels.has(s)) return n; } return null; };
  e.getAttribute = (k) => (k in e.attrs ? e.attrs[k] : null);
  e.setAttribute = (k, v) => { e.attrs[k] = String(v); };
  e.removeAttribute = (k) => { delete e.attrs[k]; };
  e.hasAttribute = (k) => k in e.attrs;
  e.contains = (o) => { for (let n = o; n; n = n.parent) { if (n === e) return true; } return false; };
  e.click = () => { log.clicks += 1; dispatch('click', e); };
  return e;
}
function dispatch(type, target) { (docL[type] || []).slice().forEach((fn) => fn({ target })); }
const drawerBtn = el(['[data-bs-toggle="offcanvas"][data-bs-target="#erp-mobile-menu-drawer"]']);
const drawer = el([]);
const tower = el(['[data-foms-tower]']);
const tile = el(['[data-foms-day-tile]']); tile.parent = tower;
const dots = el(['[data-foms-more-open]']);
const back = el(['[data-foms-shell-back]']);
const other = el([]);
const dialog = el([], { open: false, showModal() { this.open = true; log.modal += 1; }, close() { this.open = false; } });
const searchBtn = el(['[data-foms-search-open]']);
const closeBtn = el(['[data-foms-search-close]']); closeBtn.parent = dialog;
const input = { value: 'x', focus() { log.focus += 1; } };
const ids = { 'erp-mobile-menu-drawer': drawer, 'foms-search-overlay': dialog, 'foms-search-input': input };
const document = {
  addEventListener: (t, fn) => { (docL[t] = docL[t] || []).push(fn); },
  removeEventListener: (t, fn) => { docL[t] = (docL[t] || []).filter((f) => f !== fn); },
  getElementById: (id) => ids[id] || null,
  referrer: '',
};
const window = {
  location: { href: 'https://x/erp/orders/5/mobile' },
  history: { length: 2, back() { log.back += 1; } },
  addEventListener: (t, fn) => { (winL[t] = winL[t] || []).push(fn); },
  setTimeout: (fn) => fn(),
};
function bootstrapUp() {
  window.bootstrap = { Offcanvas: { getOrCreateInstance: (d) => ({ show: () => { if (d === drawer) log.show += 1; } }) } };
}
const ctx = vm.createContext({ window, document, console, Date: { now: () => clock } });
vm.runInContext(src, ctx);
vm.runInContext(src, ctx); // 두 번 실행돼도 리스너는 하나(창 가드)
const load = () => dispatch('load', {});
const dcl = () => dispatch('DOMContentLoaded', {});
const winLoad = () => (winL.load || []).forEach((fn) => fn());
({
  drawer_early() { dispatch('click', drawerBtn); load(); bootstrapUp(); load(); load(); dcl(); winLoad(); },
  drawer_bound() { bootstrapUp(); dispatch('click', drawerBtn); load(); dcl(); winLoad(); },
  drawer_expired() { dispatch('click', drawerBtn); clock += 4001; bootstrapUp(); load(); },
  drawer_navigated() { dispatch('click', drawerBtn); window.location.href = 'https://x/erp/dashboard'; bootstrapUp(); load(); },
  drawer_other_tap() { dispatch('click', drawerBtn); dispatch('click', other); bootstrapUp(); load(); },
  drawer_removed() { dispatch('click', drawerBtn); drawerBtn.isConnected = false; bootstrapUp(); load(); },
  drawer_double_tap() { dispatch('click', drawerBtn); dispatch('click', drawerBtn); bootstrapUp(); load(); load(); },
  tile_early() { dispatch('click', tile); load(); tower.attrs['data-foms-tower-bound'] = '1'; load(); load(); },
  tile_bound() { tower.attrs['data-foms-tower-bound'] = '1'; dispatch('click', tile); load(); },
  dots_early() { dispatch('click', dots); load(); dcl(); winLoad(); },
  back_history() { dispatch('click', back); },
  back_fallback() { window.history.length = 1; back.attrs['data-foms-shell-back-href'] = '/erp/dashboard?x=1'; dispatch('click', back); log.nav = window.location.href; },
  search_early() { dispatch('click', searchBtn); dispatch('click', searchBtn); log.early = dialog.getAttribute('data-foms-early-open'); log.value = input.value; dispatch('click', closeBtn); log.openAfterClose = dialog.open; log.attrAfterClose = dialog.getAttribute('data-foms-early-open'); },
  search_bound() { window.__FOMS_SEARCH_OVERLAY_BOUND = true; dispatch('click', searchBtn); },
})[scenario]();
log.docClick = (docL.click || []).length;
process.stdout.write(JSON.stringify(log));
"""


def _run_early(scenario: str) -> dict:
    proc = subprocess.run([_NODE, "-e", _EARLY_HARNESS, scenario], input=_early_js(), capture_output=True,
                          text=True, encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_drawer_tap_before_bootstrap_opens_exactly_once() -> None:
    got = _run_early("drawer_early")
    assert got["show"] == 1 and got["docClick"] == 1
    assert _run_early("drawer_double_tap")["show"] == 1  # 두 번 눌러도 열기 한 번(토글로 닫히지 않음)


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_drawer_tap_not_replayed_when_bound_stale_navigated_or_cancelled() -> None:
    """음성 대조군: 묶인 뒤 누름 · 4초 넘음 · 주소 바뀜 · 다른 곳 누름 · 단추 빠짐 — 다시 누르지 않는다."""
    for scenario in ("drawer_bound", "drawer_expired", "drawer_navigated", "drawer_other_tap", "drawer_removed"):
        assert _run_early(scenario)["show"] == 0, scenario


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_day_tile_and_detail_more_replay_once_when_ready() -> None:
    assert _run_early("tile_early")["clicks"] == 1
    assert _run_early("tile_bound")["clicks"] == 0
    assert _run_early("dots_early")["clicks"] == 1


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_back_is_handled_directly() -> None:
    assert _run_early("back_history")["back"] == 1
    got = _run_early("back_fallback")
    assert got["back"] == 0 and got["nav"] == "/erp/dashboard?x=1"


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_search_opens_natively_before_search_js_and_not_after() -> None:
    got = _run_early("search_early")
    assert got["modal"] == 1 and got["early"] == "1" and got["value"] == "" and got["focus"] == 1
    assert got["openAfterClose"] is False and got["attrAfterClose"] is None
    assert _run_early("search_bound")["modal"] == 0


_NAV_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const [src, wide] = process.argv.slice(1);
const listeners = {};
let reads = 0;
const writes = [];
const rootProps = {};
const mk = (id) => ({ id, get offsetHeight() { reads += 1; return 64; } });
const nav1 = mk('nav1'); const nav2 = mk('nav2');
let current = nav1;
const observed = []; const unobserved = [];
let ro = null;
class ResizeObserver {
  constructor(cb) { this.cb = cb; ro = this; }
  observe(t) { observed.push(t.id); }
  unobserve(t) { unobserved.push(t.id); }
}
const document = {
  querySelector: (sel) => (sel === '.erp-mobile-bottom-nav' ? current : null),
  querySelectorAll: () => [],
  getElementById: () => null,
  addEventListener: (n, fn) => { (listeners[n] = listeners[n] || []).push(fn); },
  documentElement: { style: {
    getPropertyValue: (k) => rootProps[k] || '',
    setProperty: (k, v) => { writes.push(v); rootProps[k] = v; },
  } },
};
const window = {
  ResizeObserver,
  matchMedia: (q) => ({ matches: q === '(pointer: coarse)' ? wide !== '1' : (q === '(min-width: 992px)' ? wide === '1' : false) }),
  addEventListener: (n, fn) => { (listeners['win:' + n] = listeners['win:' + n] || []).push(fn); },
};
const fire = (n) => (listeners[n] || []).forEach((fn) => fn());
const entry = (t, h) => ({ target: t, borderBoxSize: [{ blockSize: h }] });
vm.runInContext(fs.readFileSync(src, 'utf8'), vm.createContext({ window, document, console }));
fire('DOMContentLoaded');
const beforeFirst = writes.length;
ro.cb([entry(nav1, 64.4)]);
fire('foms:main-content-swapped'); // 같은 아래 탭 — 그대로
current = nav2;
fire('foms:main-content-swapped'); // 새 아래 탭 — 대상만 바꿈
ro.cb([entry(nav1, 80)]); // 옛 대상의 늦은 알림은 무시
ro.cb([entry(nav2, 64)]); // 같은 값 — 다시 쓰지 않음
ro.cb([entry(nav2, 72)]);
process.stdout.write(JSON.stringify({ reads, beforeFirst, writes, observed, unobserved, resize: (listeners['win:resize'] || []).length }));
"""


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_nav_height_follows_resize_observer_without_layout_reads() -> None:
    proc = subprocess.run([_NODE, "-e", _NAV_HARNESS, str(SHELL_JS), "0"], capture_output=True, text=True,
                          encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got == {"reads": 0, "beforeFirst": 0, "writes": ["64px", "72px"], "observed": ["nav1", "nav2"],
                   "unobserved": ["nav1"], "resize": 0}


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_nav_height_wide_mouse_pc_writes_zero() -> None:
    proc = subprocess.run([_NODE, "-e", _NAV_HARNESS, str(SHELL_JS), "1"], capture_output=True, text=True,
                          encoding="utf-8", check=False)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got["reads"] == 0 and got["writes"] == ["0px"]
