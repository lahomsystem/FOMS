"""도면 마법사 V2 — 다시 배치(지우기 · [다시 자동 배치] · [자동 배치] · 늦은 이름표 · 고정 그림) 배선(node, 가짜 코어).

설계서: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §4
스테이징 주문 4385(2026-10-27) 사용자 보고:
1) 그림 몇 장을 지워도 다시 배치되지 않았다 — 지우기 사건이 없었다(wizard.js deleteSelected 는 render · change 만).
2) [다시 자동 배치]를 눌러도 알림이 없고, 바뀐 것이 없으면 화면도 그대로라 안 되는 것처럼 보였다(헛 되돌리기 한 번도 남았다).
   앱바 [자동 배치]는 이미 정리한 시트에서 아무 일도 하지 않았다.
5) 고정 그림(손으로 옮김 · 잠금 · 돌림) 자리를 비우지 않아 다시 놓은 그림이 그 위에 겹쳤다(장애물 — v2-layout).
실제 v2-*.js 를 싣고 wizard.js 사건 순서를 흉내 낸다. 시계는 가짜(tick)라 0.45초 묶기를 기다리지 않는다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "static/js/drawing"

RUNNER = r"""
const dir = process.argv[1];
// ---- 가짜 시계 · DOM ----
let now = 0, tid = 0, timers = [];
global.window = {
  setTimeout: (fn, ms) => { const id = ++tid; timers.push({ id, fn, at: now + (ms || 0) }); return id; },
  clearTimeout: id => { timers = timers.filter(t => t.id !== id); },
  localStorage: { getItem: () => null, setItem: () => {} }
};
function tick(ms) {
  const end = now + ms;
  for (;;) {
    timers.sort((a, b) => a.at - b.at || a.id - b.id);
    const t = timers[0];
    if (!t || t.at > end) { break; }
    timers.shift(); now = t.at; t.fn();
  }
  now = end;
}
function mkEl(tag) {
  const e = { tagName: String(tag || 'div').toUpperCase(), children: [], style: {}, attrs: {}, handlers: {}, hidden: false, disabled: false,
    className: '', title: '', type: '', _text: '' };
  Object.defineProperty(e, 'textContent', {
    get() { return e._text + e.children.map(c => c.textContent).join(''); },
    set(v) { e._text = String(v == null ? '' : v); e.children = []; } });
  e.appendChild = c => { e.children.push(c); c.parentNode = e; return c; };
  e.removeChild = c => { e.children = e.children.filter(x => x !== c); };
  e.addEventListener = (n, fn) => { (e.handlers[n] = e.handlers[n] || []).push(fn); };
  e.click = () => (e.handlers.click || []).forEach(fn => fn({ stopPropagation() {}, preventDefault() {} }));
  e.setAttribute = (k, v) => { e.attrs[k] = String(v); };
  e.getAttribute = k => (k in e.attrs ? e.attrs[k] : null);
  const cls = new Set();
  e.classList = { add: (...c) => c.forEach(x => cls.add(x)), remove: (...c) => c.forEach(x => cls.delete(x)),
    toggle: (c, on) => { if (on === undefined ? !cls.has(c) : on) { cls.add(c); } else { cls.delete(c); } }, contains: c => cls.has(c) };
  e.querySelector = () => null;
  e.querySelectorAll = () => [];
  return e;
}
const dom = {};
['dws-root', 'dws-v2-slots', 'dws-v2-badges', 'dws-v2-summary', 'dws-v2-templates', 'dws-v2-seen', 'dws-v2-toggles',
 'dws-v2-relayout', 'dws-v2-rearrange', 'dws-v2-unpin'].forEach(id => { dom[id] = mkEl('div'); dom[id].id = id; });
global.document = { readyState: 'complete', getElementById: id => dom[id] || null, querySelectorAll: () => [], querySelector: () => null,
  createElement: mkEl, addEventListener: () => {} };
// ---- 가짜 코어: wizard.js 사건 순서 ----
const handlers = {}, toasts = [], undo = [], state = { sheets: [] };
let cur = 0;
function emit(name, data) { (handlers[name] || []).slice().forEach(fn => fn(data)); }
const core = {
  ui: 'v2', on: (n, fn) => { (handlers[n] = handlers[n] || []).push(fn); },
  state: () => state, sheet: () => state.sheets[cur] || null, canSave: () => true,
  recordUndo: () => { undo.push(JSON.stringify(state.sheets[cur])); },
  undo: () => { const s = undo.pop(); if (s) { state.sheets[cur] = JSON.parse(s); emit('render'); emit('change'); } },
  markDirty: () => emit('change'), redraw: () => emit('render'),
  select: () => {}, toast: m => toasts.push(m), editing: () => false, dragging: () => false,
  items: imgs => imgs.map((o, i) => ({ id: o.id, nw: o.natural_w || o.w, nh: o.natural_h || o.h, order: i, tx: 0,
    label: (o.part && o.part.label) || '미분류' })),
  baseline: () => ({}), productText: () => '몰딩 화장대 여닫이',
  photos: () => [], photoVisible: () => true, importPhoto: () => Promise.resolve(false), threshold: () => 0.5,
  fitCell: () => {}, hatch: () => null, viewUrl: () => '', setTool: () => {},
  setPartLabel: (id, label) => {
    const o = core.sheet().objects.find(x => x.id === id);
    core.recordUndo(); o.part = Object.assign({}, o.part, { label, src: 'user' }); core.markDirty(); emit('labels', { id, by: 'user' });
  }
};
window.FomsWizardCore = core;
for (const f of ['part-pack.js', 'part-layout.js', 'v2-slots.js', 'v2-pack.js', 'v2-hero.js', 'v2-layout.js', 'v2-plan.js', 'v2-paper.js',
  'v2-right.js', 'v2-chrome.js', 'v2-shell.js']) { require(dir + '/' + f); }
const V2 = window.FomsV2, S = window.FomsV2Slots;
// ---- 시트 · 사람 동작 ----
const img = (id, label, w, h, extra) => Object.assign({ id, type: 'image', key: id + '.png', x: 500, y: 300, w: Math.min(900, w),
  h: Math.round(Math.min(900, w) * h / w), natural_w: w, natural_h: h, rotation: 0, part: { label, src: 'ai', conf: 0.8 } }, extra || {});
function sheet4385(id) {   // 주문 4385 꼴: 큰 그림 3(칸 짐작 2) · 상세 3 · 평면 1 · 기타 1
  return { id: id || 's1', name: '몰딩 화장대 여닫이', form: { v2_ai: 'g1=f71 g2=i81' }, objects: [
    img('g1', '미분류', 1600, 1100, { part: { label: '미분류', src: 'ai', ai: '정면·도어', conf: 0.36 } }),
    img('g2', '미분류', 1700, 1150, { part: { label: '미분류', src: 'ai', ai: '입체·내부', conf: 0.36 } }),
    img('i1', '입체·내부', 1700, 1150), img('d1', '부품 상세', 700, 420), img('d2', '서랍 단면', 600, 500), img('d3', '서랍 단면', 650, 480),
    img('p1', '평면·상판', 1500, 700),
    img('u1', '미분류', 500, 900, { part: { label: '미분류', src: 'ai', ai: '부품 상세', conf: 0.49 } })] };
}
function laidSheet() {   // 같이 올린 묶음이 끝남 → 칸 배치
  state.sheets = [sheet4385()]; cur = 0;
  emit('batch', { ids: state.sheets[0].objects.map(o => o.id), sheetId: 's1' });
  tick(100);
  return core.sheet();
}
function deleteSelected(ids) {   // wizard.js deleteSelected: recordUndo → splice → render → markDirty(change) → removed
  const sh = core.sheet(), images = ids.filter(id => (sh.objects.find(o => o.id === id) || {}).type === 'image').length;
  core.recordUndo();
  sh.objects = sh.objects.filter(o => ids.indexOf(o.id) < 0);
  emit('render'); core.markDirty(); emit('removed', { ids, images });
}
const obj = id => core.sheet().objects.find(o => o.id === id);
const rects = () => JSON.stringify(core.sheet().objects.filter(o => o.type === 'image').map(o => [o.id, o.x, o.y, o.w, o.h]));
const over = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
function box(o) {   // 돌린 그림을 감싼 상자 — Konva offset 0 이라 (x, y)가 축
  const r = (o.rotation || 0) * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  const xs = [0, o.w * c, -o.h * s, o.w * c - o.h * s].map(v => o.x + v), ys = [0, o.w * s, o.h * c, o.w * s + o.h * c].map(v => o.y + v);
  const x0 = Math.min(...xs), y0 = Math.min(...ys);
  return { x: x0, y: y0, w: Math.max(...xs) - x0, h: Math.max(...ys) - y0 };
}
function overlaps() {
  const m = core.sheet().objects.filter(o => o.type === 'image').map(box), n = [];
  for (let i = 0; i < m.length; i++) { for (let j = i + 1; j < m.length; j++) { if (over(m[i], m[j])) { n.push(i + '/' + j); } } }
  return n;
}
const out = {};
"""


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def _run(body: str) -> dict:
    script = RUNNER + body + "\nprocess.stdout.write(JSON.stringify(out));"
    proc = subprocess.run([_node(), "-e", script, str(JS_DIR)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_delete_rearranges_remaining_pictures_in_one_undo_step():
    out = _run(r"""
const sh = laidSheet();
const laid = rects(), depth = undo.length;
out.layout0 = sh.form.v2_layout;
deleteSelected(['g1', 'd2', 'p1']);
const justDeleted = rects();
tick(500);   // 0.45초 묶기
out.moved = rects() !== justDeleted;
out.layout = core.sheet().form.v2_layout;
out.undoAdded = undo.length - depth;          // 지우기가 남긴 한 번뿐(배치는 따로 남기지 않는다)
out.toast = toasts.slice(-1)[0] || '';
out.overlaps = overlaps();
core.undo();                                   // Ctrl+Z 한 번 = 지운 그림과 옛 자리
out.undone = rects() === laid;
""")
    assert out["layout0"] in ("band", "column")
    assert out["moved"], "지운 뒤 남은 그림을 다시 놓아야 한다"
    assert out["layout"] in ("band", "column")
    assert out["undoAdded"] == 1
    assert "3장을 빼고" in out["toast"] and "Ctrl+Z" in out["toast"]
    assert out["overlaps"] == []
    assert out["undone"]


def test_delete_does_not_move_in_free_mode_unlaid_sheet_or_after_quick_undo():
    out = _run(r"""
// 자유 배치 모드
laidSheet();
V2.setMode('free', true);
deleteSelected(['g1']);
let before = rects();
tick(500);
out.free = rects() === before;
V2.setMode('free', false);
// 칸으로 정리하기 전 시트(v2_layout 없음) — 자동 배치 모드여도 옮기지 않는다
window.localStorage.getItem = () => null;
V2.setMode('auto');
state.sheets = [sheet4385('s2')]; cur = 0;
deleteSelected(['g1']);
before = rects();
tick(500);
out.unlaid = rects() === before && !core.sheet().form.v2_layout;
// 지운 직후(0.45초 안) 되돌리면 그 사이 돌아온 그림을 다시 놓지 않는다
laidSheet();
core.sheet().objects = core.sheet().objects.filter(o => o.id !== 'd3');   // 낡은 종이(지우기 사건 없이 빠짐)
const stale = rects();
deleteSelected(['g2']);
core.undo();
tick(500);
out.quickUndo = rects() === stale;
""")
    assert out["free"] and out["unlaid"] and out["quickUndo"]


def test_relayout_button_reports_result_and_leaves_no_dead_undo():
    out = _run(r"""
laidSheet();
const depth = undo.length, laid = rects();
toasts.length = 0;
dom['dws-v2-relayout'].click();                // 바뀐 것이 없다
dom['dws-v2-rearrange'].click();               // 앱바 단추도 같은 일
out.same = rects() === laid;
out.undoAdded = undo.length - depth;
out.toasts = toasts.slice();
// 낡은 종이(지우기 사건 없이 3장 빠짐)에서 누르면 다시 놓고 장수를 말한다
core.sheet().objects = core.sheet().objects.filter(o => ['g1', 'd2', 'p1'].indexOf(o.id) < 0);
const stale = rects();
toasts.length = 0;
dom['dws-v2-relayout'].click();
out.changed = rects() !== stale;
out.undoAfter = undo.length - depth;
out.toast2 = toasts.slice(-1)[0] || '';
""")
    assert out["same"] and out["undoAdded"] == 0, "바뀐 것이 없으면 되돌리기 사본을 남기지 않는다"
    assert len(out["toasts"]) == 2 and all("이미 칸에 맞게" in t for t in out["toasts"])
    assert out["changed"] and out["undoAfter"] == 1
    assert "장을 칸에 맞춰 다시 놓았어요" in out["toast2"] and "Ctrl+Z" in out["toast2"]


def test_pinned_picture_is_named_in_toast_unpin_link_shows_and_nothing_overlaps():
    out = _run(r"""
laidSheet();
const i1 = obj('i1');
core.recordUndo(); i1.x += 40; i1.y += 12; core.markDirty();   // 손으로 끌어 옮김 = 고정
const pinned = [i1.x, i1.y, i1.w, i1.h];
deleteSelected(['g1', 'd3']);
tick(500);
toasts.length = 0;
dom['dws-v2-relayout'].click();
tick(100);
out.toast = toasts.slice(-1)[0] || '';
out.pinnedKept = JSON.stringify([obj('i1').x, obj('i1').y, obj('i1').w, obj('i1').h]) === JSON.stringify(pinned);
out.overlaps = overlaps();
out.unpinHidden = dom['dws-v2-unpin'].hidden;
out.unpinText = dom['dws-v2-unpin'].textContent;
dom['dws-v2-unpin'].click();                   // 고정 풀고 모두 다시
tick(100);
out.afterUnpin = Object.keys(V2.plan().g.fixed);
out.unpinHidden2 = dom['dws-v2-unpin'].hidden;
// 고른 틀만 있으면 바닥 링크는 숨고, 고른 틀이 추천과 다르면 틀 고르기에 [추천 틀로 돌아가기](2026-10-27 도면팀 평가)
const rec = V2.plan().out.rec;
core.sheet().form.v2_pick = rec === 'band' ? 'column' : 'band';
V2.refresh(); tick(100);
out.pickHidden = dom['dws-v2-unpin'].hidden;
out.back = dom['dws-v2-templates'].textContent;
""")
    assert "고정된 그림 1장" in out["toast"]
    assert out["pinnedKept"] and out["overlaps"] == []
    assert out["unpinHidden"] is False and "1장" in out["unpinText"]
    assert out["afterUnpin"] == [] and out["unpinHidden2"] is True
    assert out["pickHidden"] is True and "추천 틀로 돌아가기" in out["back"]


def test_auto_mode_button_rearranges_stale_sheet_but_opening_does_not():
    out = _run(r"""
laidSheet();
core.sheet().objects = core.sheet().objects.filter(o => ['g1', 'd2'].indexOf(o.id) < 0);   // 낡은 종이
const stale = rects();
V2.setMode('auto');                            // 화면을 열 때(init)와 같은 부름 — 옮기지 않는다
out.open = rects() === stale;
toasts.length = 0;
V2.setMode('auto', true);                      // 사람이 앱바 [자동 배치]를 누름
out.clicked = rects() !== stale;
out.toast = toasts.slice(-1)[0] || '';
""")
    assert out["open"] and out["clicked"]
    assert "다시 놓았어요" in out["toast"]


def test_late_ai_label_after_batch_rearranges_on_that_sheet():
    out = _run(r"""
laidSheet();
const u1 = obj('u1'), before = [u1.x, u1.y, u1.w, u1.h];
u1.part = Object.assign({}, u1.part, { label: '서랍 단면', conf: 0.7 });   // 30초가 지나 늦게 온 AI 이름표
emit('labels', { id: 'u1', by: 'ai', batch: true, fam: 'detail', famConf: 0.7 });
tick(600);   // 묶기 0.45초 + 화면 다시 그리기 0.06초
const u = obj('u1');
out.moved = JSON.stringify([u.x, u.y, u.w, u.h]) !== JSON.stringify(before);
out.inDetail = V2.plan().g.detail.some(o => o.id === 'u1');
""")
    assert out["moved"] and out["inDetail"]


def test_batch_finishing_on_other_sheet_waits_until_that_sheet_opens():
    out = _run(r"""
const a = sheet4385('A'), b = { id: 'B', name: 'B', form: { v2_layout: 'band' }, objects: [img('z1', '정면·내부', 1200, 800)] };
state.sheets = [a, b]; cur = 1;                // 묶음 그림은 A 에 있는데 사람이 B 를 보고 있다
const bBefore = rects();
emit('batch', { ids: a.objects.map(o => o.id), sheetId: 'A' });
tick(100);
out.bUntouched = rects() === bBefore;
out.aWaiting = !state.sheets[0].form.v2_layout;
cur = 0; emit('sheet');                        // A 를 연다
tick(100);
out.aLaid = !!state.sheets[0].form.v2_layout;
out.overlaps = overlaps();
""")
    assert out["bUntouched"] and out["aWaiting"]
    assert out["aLaid"] and out["overlaps"] == []


def test_paper_head_skips_pinned_member_and_pill_floats_above_head_text():
    out = _run(r"""
laidSheet();
const d1 = obj('d1');
core.recordUndo(); d1.x = 900; d1.y = 560; core.markDirty();   // 상세 한 장을 큰 그림 칸 가운데로 끌어 놓음 = 고정
dom['dws-v2-relayout'].click();
tick(100);
const heads = dom['dws-v2-slots'].children.filter(n => /dws-v2-head(\s|$)/.test(n.className));
const detail = heads.find(n => n.children.some(c => /서랍|부품|상세/.test(c.textContent) && /head-name/.test(c.className)));
const left = parseInt(detail.style.left, 10), width = parseInt(detail.style.width, 10), top = parseInt(detail.style.top, 10);
const g = V2.plan().g, b = window.FomsV2Paper.bbox(g.detail.filter(o => !g.fixed[o.id]));
out.fixed = Object.keys(g.fixed);
out.headOnLoose = left === Math.round(b.x) && width === Math.round(Math.max(b.w, 132));
out.pinnedOutside = obj('d1').x >= left + width || obj('d1').x + obj('d1').w <= left;
const pill = dom['dws-v2-badges'].children.find(n => /dws-v2-pill /.test(n.className) && parseInt(n.style.left, 10) === left + width);
out.pillUp = pill ? top - parseInt(pill.style.top, 10) : null;   // 배율 표시 위끝이 머리 위로 얼마나 — 높이 22 라 머리 글 윗선까지만
out.pins = dom['dws-v2-badges'].children.filter(n => n.className === 'dws-v2-pin').map(n => n.textContent);
out.overlaps = overlaps();
""")
    assert out["fixed"] == ["d1"]
    assert out["headOnLoose"] and out["pinnedOutside"], "고정 그림은 칸 머리 자리에서 빠진다"
    assert out["pillUp"] == 18      # 예전 14 — 머리 가운데에 걸쳐 좁은 칸 글을 가렸다('B 서랍 단면 · 부[32%]세')
    assert out["pins"] == ["고정"]
    assert out["overlaps"] == []


def test_resizing_a_picture_rearranges_the_rest_around_it_in_one_undo_step():
    """사용자 보고(2026-10-28, 스테이징 주문 4385): 메인을 키우면 나머지가 저절로 맞춰져야 하는데 겹친 채 남았다.
    끌기 · 크기 바꾸기를 마치면(코어 moved) 고정이 된 그 그림을 비켜 나머지를 다시 놓는다 — 되돌리기는 끌기 시작이 남긴 한 번,
    손으로 맞추던 그림은 골라진 채 둔다."""
    out = _run(r"""
laidSheet();
const before = rects(), t = obj('g2'), selects = [];        // 큰 그림 칸 가운데 그림을 키운다(4385 의 메인 자리)
core.select = ids => selects.push((ids || []).length);
core.recordUndo();                                           // wizard.js transformstart
t.w = Math.round(t.w * 1.5); t.h = Math.round(t.h * 1.5);
const keep = [t.x, t.y, t.w, t.h].join(',');
core.markDirty(); emit('moved', { ids: ['g2'] });           // wizard.js transformend → commitNode → emitMoved
out.overlapBefore = overlaps().length;
tick(500);
out.kept = [obj('g2').x, obj('g2').y, obj('g2').w, obj('g2').h].join(',') === keep;
out.pinned = Object.keys(V2.plan().g.fixed);
out.overlaps = overlaps();
out.toast = toasts[toasts.length - 1] || '';
out.selects = selects;
core.undo();
out.undone = rects() === before;
""")
    assert out["overlapBefore"] > 0                           # 키운 그림이 옆 그림 위로 올라갔다(고치기 전엔 그대로 남았다)
    assert out["kept"] and out["pinned"] == ["g2"]
    assert out["overlaps"] == [] and "옮긴 그림을 비켜 나머지" in out["toast"], out
    assert out["selects"] == []                               # 골라진 채 둔다(이어서 크기를 맞추게)
    assert out["undone"]                                      # Ctrl+Z 한 번이면 키우기 전 그대로


def test_moved_waits_for_drag_and_skips_jitter_free_mode_and_unpinned_moves():
    out = _run(r"""
laidSheet();
const others = () => JSON.stringify(core.sheet().objects.filter(o => o.type === 'image' && o.id !== 'd1').map(o => [o.id, o.x, o.y, o.w, o.h]));
let base = others();
// 1) 손떨림(6px 안쪽)은 고정이 아니다 — 다시 놓지 않는다
core.recordUndo(); obj('d1').x += 4; core.markDirty(); emit('moved', { ids: ['d1'] }); tick(500);
out.jitter = others() === base;
// 2) 끄는 중에는 기다린다(다시 그리면 끌던 노드가 사라진다) — 끝나면 놓는다
let dragging = true;
core.dragging = () => dragging;
core.recordUndo(); obj('d1').x = 900; obj('d1').y = 560; core.markDirty(); emit('moved', { ids: ['d1'] });
tick(2000);
out.waited = others() === base;
dragging = false; tick(500);
out.after = others() !== base && overlaps().length === 0;
// 3) 자유 배치 모드는 저절로 옮기지 않는다
V2.setMode('free');
base = others();
core.recordUndo(); obj('d1').x += 120; core.markDirty(); emit('moved', { ids: ['d1'] }); tick(500);
out.free = others() === base;
// 4) '손으로 옮긴 그림은 고정'을 끄면 옮긴 그림이 고정이 아니라 다시 놓지 않는다(놓으면 옮긴 그림이 바로 제자리로 간다)
V2.setMode('auto'); tick(500);
V2.setSetting('lockMoved', false); tick(500);
base = others();
core.recordUndo(); obj('d1').x += 120; core.markDirty(); emit('moved', { ids: ['d1'] }); tick(500);
out.unpinned = others() === base;
""")
    assert out["jitter"] and out["waited"] and out["after"], out
    assert out["free"] and out["unpinned"], out

