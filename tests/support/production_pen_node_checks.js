// 생산 도면 펜 기록 쓰는 상태(설계서 2026-11-28-production-pen-record §6-3) — 서버가 그린 진짜 판(argv[2], 스위치 켬 · 카드 note 흉내) 위에서
// 보기 JS 둘(viewer → zoom)을 돌리고, [기록 쓰기]가 script 태그로 받는 쓰기 JS 둘(pen-ink → pen)을 그 자리에서 돌린다.
// tests/domains/test_production_pen_record_screen.py 가 부른다. want = argv[3] {steps, get_note, writes:[result…], natural:{w,h}}.
// step: {do:'open', no} 카드 그림 누름 · {do:'write'} [기록 쓰기] · {do:'pointer', type:'pen'|'touch'|'mouse', path:[[x,y]…]} 쓰는 층 위 한 획
// (쓰는 층 rect = 좌표 기준 크기라 x · y 가 곧 기록 좌표) · {do:'tool'|'color'|'width', v} · {do:'btn', v} 쓰는 줄 단추(undo · redo · save · cancel ·
// keep · drop · fit) · {do:'text', x, y, value} 글 놓기 · {do:'synced'} 30초 받아 오기 뒤 카드 고침 사건 · {do:'escape'} · {do:'show', v} ·
// {do:'sheet', i} · {do:'release'} 붙잡아 둔 저장 응답 풀기. 쓰기 응답은 writes 를 차례로(hold:true 면 release 까지 붙잡음).
// 결과는 stdout JSON {out: [step 마다 모습]}.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]);
const D = fakeDom();
function parts(sel) { return sel.trim().match(/(?:[^\s"'[\]]+|\[[^\]]*\])+/g) || []; }
function under(n, scope) { for (let p = n.parentNode; p; p = p.parentNode) { if (p === scope) { return true; } } return false; }
function matchDesc(n, list) {
  if (!n.matches(list[list.length - 1])) { return false; }
  let i = list.length - 2;
  for (let p = n.parentNode; p && p.tag && i >= 0; p = p.parentNode) { if (p.matches(list[i])) { i -= 1; } }
  return i < 0;
}
function all(scope, sel) {
  const out = [];
  (function walk(node) { node.children.forEach((c) => { if (c.tag) { out.push(c); walk(c); } }); })(scope);
  const groups = sel.split(',').map(parts);
  return out.filter((n) => under(n, scope) && groups.some((g) => matchDesc(n, g)));
}
function cloneText() { return { tag: null, children: [], parentNode: null, textContent: this.textContent, cloneNode: cloneText }; }
const loaded = [];
function deep(n) {
  if (n && !n.tag && !n.cloneNode) { n.cloneNode = cloneText; }
  if (!n || !n.tag || n.__deep) { return n; }
  n.__deep = true;
  if (!n.style) { n.style = {}; }
  n.querySelectorAll = (sel) => all(n, sel);
  n.querySelector = (sel) => all(n, sel)[0] || null;
  const add = n.appendChild.bind(n);
  n.appendChild = (c) => {
    if (n.text !== null && n.text !== '') { // 브라우저처럼 textContent 글도 마디로 남긴다(글 뒤에 점을 붙이는 장 묶음 단추)
      const t = n.text;
      n.text = null;
      n.children.push({ tag: null, children: [], parentNode: n, textContent: t, cloneNode: cloneText });
    }
    add(c); deep(c); (c.children || []).forEach(deep);
    if (c.tag === 'script' && n === head) { runScript(c); }
    return c;
  };
  n.children.forEach(deep);
  return n;
}
const body = deep(D.parse(html));
const head = deep(D.makeEl('head'));
const natural = Object.assign({ w: 1400, h: 1000 }, want.natural || {});
const calls = { gets: [], writes: [], timers: 0 };
let held = null;
const queue = (want.writes || []).slice();
const winListeners = {};

function svgRect(n) { // 쓰는 층 rect = viewBox 크기(보이는 px = 기록 좌표)
  const vb = String(n.getAttribute('viewBox') || '0 0 10 10').split(/\s+/).map(Number);
  return { left: 0, top: 0, width: vb[2], height: vb[3], right: vb[2], bottom: vb[3] };
}
function hitTest(x, y) { // 지우개 — 댄 자리에서 가장 가까운 기록 한 개(굵은 투명 선 폭 30)
  let best = null;
  let bestD = 22;
  body.querySelectorAll('[data-pp-o]').forEach((g) => {
    g.children.filter((c) => c.tag).forEach((c) => {
      const pts = c.tag === 'text' ? [Number(c.getAttribute('x')), Number(c.getAttribute('y'))]
        : String(c.getAttribute('points') || '').split(/[\s,]+/).filter(Boolean).map(Number);
      for (let i = 0; i + 1 < pts.length; i += 2) {
        const d = Math.hypot(pts[i] - x, pts[i + 1] - y);
        if (d < bestD) { bestD = d; best = c; }
      }
    });
  });
  return best;
}
function canvas() {
  const c = D.makeEl('canvas');
  const ops = [];
  const g = new Proxy({}, { get: (t, k) => (k in t ? t[k] : (...a) => ops.push([k].concat(a))), set: (t, k, v) => { t[k] = v; ops.push(['=' + String(k), v]); return true; } });
  c.getContext = () => g;
  c.toBlob = (cb, type) => cb({ fake: 'png', type, width: c.width, height: c.height, ops: ops.length });
  return c;
}
const document = {
  body, head,
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => (t.toLowerCase() === 'canvas' ? canvas() : deep(D.makeEl(t.toLowerCase()))),
  createElementNS: (ns, t) => {
    const n = deep(D.makeEl(t));
    if (t === 'svg') { n.getBoundingClientRect = () => svgRect(n); }
    return n;
  },
  elementFromPoint: (x, y) => hitTest(x, y),
  addEventListener(t, f) { (D.docListeners[t] = D.docListeners[t] || []).push(f); }, dispatchEvent() { return true; },
};
class FormData {
  constructor() { this.entries = []; }
  append(k, v, name) { this.entries.push([k, v, name || null]); }
}
function resolveWrite() {
  const r = queue.shift();
  return r || { ok: true, kind: 'ok', status: 200, data: { success: true, data: { note: { version: 1, view_url: '/api/files/view/orders/1/production/n1.png', by: '김재단', at: '11/28 10:00' } }, error: null }, message: '' };
}
const ctx = {
  console, JSON, Math, Object, Array, String, Number, Boolean, Error, Proxy, Promise, isNaN, isFinite, encodeURIComponent, document, FormData,
  Date: { now: () => 1000000 },
  setTimeout: () => { calls.timers += 1; return calls.timers; }, clearTimeout: () => {},
  fomsUiZoom: () => want.ui_zoom || 1,
  fomsCsrfToken: () => 'tok-1',
  open: () => null,
  addEventListener(t, f) { (winListeners[t] = winListeners[t] || []).push(f); },
  fetch: (url, opts) => {
    calls.gets.push({ url, method: (opts && opts.method) || 'GET' });
    const note = want.get_note === undefined ? null : want.get_note;
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { note }, error: null }) });
  },
  fomsMutationFetch: (url, opts) => {
    const b = opts.body;
    const form = b && b.entries ? b.entries.map((e) => ({ k: e[0], v: typeof e[1] === 'string' ? e[1] : e[1], name: e[2] })) : null;
    calls.writes.push({ url, method: opts.method, json: typeof b === 'string' ? JSON.parse(b) : null, form, headers: opts.headers || null, timeoutMs: opts.timeoutMs || null });
    const r = queue.length && queue[0].hold ? (queue.shift(), null) : resolveWrite();
    if (r) { return Promise.resolve(r); }
    return new Promise((ok) => { held = ok; });
  },
};
ctx.window = ctx;
vm.createContext(ctx);
function runFile(rel) {
  const f = path.join(root, rel);
  vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
}
function runScript(tag) { // [기록 쓰기]가 단 script 태그 — 핀을 떼고 그 파일을 돌린 뒤 load
  const src = tag.getAttribute('src') || '';
  loaded.push(src);
  runFile(src.replace(/^\/static\//, 'static/').replace(/\?.*$/, ''));
  (tag.listeners.load || []).forEach((f) => f({ type: 'load' }));
}

const viewer = body.querySelector('[data-pp-viewer]');
const stage = viewer.querySelector('[data-pp-v-zoom]');
const img = viewer.querySelector('[data-pp-v-img]');
Object.defineProperty(img, 'src', { get() { return this.getAttribute('src') || ''; }, set(v) { this.setAttribute('src', v); } });
Object.assign(img, { style: { transform: '' }, complete: true, naturalWidth: natural.w, naturalHeight: natural.h, offsetLeft: 20, offsetTop: 10, offsetWidth: 700, offsetHeight: 500 });
stage.style = {};
stage.setPointerCapture = () => {};
stage.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 });
img.getBoundingClientRect = () => ({ left: 50, top: 50, width: 700, height: 500, right: 750, bottom: 550 });
const textBox = viewer.querySelector('[data-pp-ptext]');
if (textBox) { textBox.value = ''; textBox.style = {}; }

['viewer', 'zoom'].forEach((n) => runFile('static/js/production/foms-production-parts-' + n + '.js'));

const q = (sel) => viewer.querySelector(sel);
const txt = (n) => (n ? String(n.textContent || '').replace(/\s+/g, ' ').trim() : '');
function pressed(sel) { const n = viewer.querySelectorAll(sel).find((b) => b.getAttribute('aria-pressed') === 'true'); return n || null; }
function snap(extra) {
  const pen = ctx.FomsPen;
  const save = q('[data-pp-pen="save"]');
  const toast = q('[data-pp-ptoast]');
  const ink = stage.querySelector('[data-pp-ink]');
  const card = want.card_no ? body.querySelectorAll('[data-pp-card]').find((c) => c.getAttribute('data-no') === String(want.card_no)) : null;
  const objs = stage.querySelectorAll('[data-pp-o]').map((g) => {
    const vis = g.children.filter((c) => c.tag);
    const line = vis.find((c) => c.tag === 'polyline' && c.getAttribute('stroke') !== 'transparent') || vis[0];
    return { tag: line.tag, stroke: line.getAttribute('stroke') || line.getAttribute('fill'), points: line.getAttribute('points') || '', text: txt(line) };
  });
  const bar = (sel) => { const n = q(sel); return n ? n.hidden : null; };
  return Object.assign({
    editing: !!(pen && pen.editing()), edit_cls: (viewer.getAttribute('class') || '').split(/\s+/).includes('is-pen-edit'),
    view_hidden: bar('[data-pp-pview]'), edit_hidden: bar('[data-pp-pedit]'), ask_hidden: bar('[data-pp-pask]'), vbot_hidden: bar('.pp-vbot'),
    ink: !!ink, objs, src: img.getAttribute('src'), hidden: viewer.hidden,
    save: save ? { disabled: !!save.disabled, text: txt(save) } : null,
    undo: q('[data-pp-pen="undo"]') ? q('[data-pp-pen="undo"]').disabled : null,
    redo: q('[data-pp-pen="redo"]') ? q('[data-pp-pen="redo"]').disabled : null,
    tool: pressed('[data-pp-tool]') ? pressed('[data-pp-tool]').getAttribute('data-pp-tool') : null,
    colors_off: q('[data-pp-colors]') ? q('[data-pp-colors]').classList.contains('is-off') : null,
    widths_off: q('[data-pp-widths]') ? q('[data-pp-widths]').classList.contains('is-off') : null,
    toast: toast && !toast.hidden ? txt(toast) : '', title: txt(q('[data-pp-pen-title]')),
    sheets: viewer.querySelectorAll('[data-pp-sheet]').map((b) => ({ text: txt(b), pressed: b.getAttribute('aria-pressed'), label: b.getAttribute('aria-label'), dot: !!b.querySelector('.pp-pdot') })),
    meta: q('[data-pp-pmeta]') && !q('[data-pp-pmeta]').hidden ? txt(q('[data-pp-pmeta]')) : null,
    show: q('[data-pp-pshow]') && !q('[data-pp-pshow]').hidden ? (pressed('[data-pp-show]') || { getAttribute: () => '' }).getAttribute('data-pp-show') : null,
    write: q('[data-pp-pen-open]') ? { hidden: q('[data-pp-pen-open]').hidden, text: txt(q('[data-pp-pen-open]')) } : null,
    loaded: loaded.slice(), gets: calls.gets.slice(), writes: calls.writes.slice(), has_pen: !!ctx.FomsPen,
    card: card ? { v: card.getAttribute('data-note-v'), by: card.getAttribute('data-note-by'), at: card.getAttribute('data-note-at'),
      url: card.getAttribute('data-note-url'), tag: !!card.querySelector('[data-pp-ptag]'), aria: card.querySelector('[data-pp-open]').getAttribute('aria-label') } : null,
  }, extra || {});
}
function pointer(type, pts) {
  const id = 7;
  const ev = (t, xy) => D.dispatch(stage, t, { pointerId: id, pointerType: type, button: 0, clientX: xy[0], clientY: xy[1], cancelable: true });
  const first = ev('pointerdown', pts[0]);
  pts.slice(1).forEach((xy) => ev('pointermove', xy));
  ev('pointerup', pts[pts.length - 1]);
  return first.defaultPrevented;
}
const flush = () => new Promise((ok) => setImmediate(ok));

(async () => {
  const out = [];
  for (const s of want.steps) {
    let extra = { do: s.do };
    if (s.do === 'open') {
      const card = body.querySelectorAll('[data-pp-card]').find((c) => c.getAttribute('data-no') === String(s.no));
      want.card_no = s.no;
      D.dispatch(card.querySelector('[data-pp-open]'), 'click');
      extra.view_url = card.getAttribute('data-view-url');
      extra.note_url = card.getAttribute('data-note-url');
    } else if (s.do === 'write') {
      D.dispatch(q('[data-pp-pen-open]'), 'click');
    } else if (s.do === 'pointer') {
      extra.prevented = pointer(s.type || 'pen', s.path);
    } else if (s.do === 'tool' || s.do === 'color' || s.do === 'width') {
      D.dispatch(q('[data-pp-' + s.do + '="' + s.v + '"]'), 'click');
    } else if (s.do === 'btn') {
      D.dispatch(q('[data-pp-pen="' + s.v + '"]'), 'click');
    } else if (s.do === 'text') {
      pointer('pen', [[s.x, s.y]]);
      extra.box_open = !textBox.hidden;
      textBox.value = s.value;
      D.dispatch(textBox, 'keydown', { key: 'Enter' });
    } else if (s.do === 'synced') {
      (D.docListeners['foms:part-card-updated'] || []).forEach((f) => f({ type: 'foms:part-card-updated' }));
    } else if (s.do === 'escape') {
      (D.docListeners.keydown || []).forEach((f) => f({ type: 'keydown', key: 'Escape' }));
    } else if (s.do === 'show') {
      D.dispatch(q('[data-pp-show="' + s.v + '"]'), 'click');
    } else if (s.do === 'sheet') {
      D.dispatch(q('[data-pp-sheet="' + s.i + '"]'), 'click');
    } else if (s.do === 'release') {
      const ok = held;
      held = null;
      if (ok) { ok(resolveWrite()); }
    }
    for (let i = 0; i < 6; i += 1) { await flush(); }
    out.push(snap(extra));
  }
  process.stdout.write(JSON.stringify({ out }));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
