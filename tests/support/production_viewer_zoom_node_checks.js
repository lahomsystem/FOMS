// 생산 도면 '크게 보기' 그 자리 확대(2026-11-27 사장님 "큰 화면에서 바로 확대") — 서버가 그린 진짜 판(argv[2]) 위에서
// 보기 JS 둘(foms-production-parts-viewer.js → foms-production-parts-zoom.js)을 Node 로 돌린다. tests/domains/test_production_viewer_zoom_1127.py 가 부른다.
// want = argv[3] {ui_zoom, stage: {left, top, width, height}, base: {w, h}, steps: [...]}. 손짓 step:
//   {do:'open', no} 카드 그림 누름 · {do:'touch', type, touches:[[x,y]…], changed:[[x,y]…]} · {do:'clock', ms} 시계 앞으로 ·
//   {do:'tap', x, y} 짧게 한 번(touchstart → touchend → click) · {do:'click'} 그림 칸 click · {do:'wheel', dy, x, y} · {do:'step', by} ◀ ▶ ·
//   {do:'close'} [닫기] · {do:'stage', rect} 그림 칸 크기 바꿈 · {do:'resize'} 창 resize · {do:'updated'} 30초 받아 오기 뒤 다시 그림.
// 그림 rect 는 style.transform(translate ÷ 화면 크기 배율 · scale)을 거꾸로 읽어 보이는 px 로 낸다(브라우저와 같은 꼴).
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
// 가짜 DOM 은 조합자가 없다 — 보기 JS 가 쓰는 자손 고르기(".pp-head .fph-pane__h" · "[data-pp-actbox] [data-pp-act]")만 더한다
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
function deep(n) {
  if (n && !n.tag && !n.cloneNode) { n.cloneNode = cloneText; } // 크게 보기가 카드 글 마디를 복사한다(fillActions · 담당 줄)
  if (!n || !n.tag || n.__deep) { return n; }
  n.__deep = true;
  n.querySelectorAll = (sel) => all(n, sel);
  n.querySelector = (sel) => all(n, sel)[0] || null;
  const add = n.appendChild.bind(n);
  n.appendChild = (c) => { add(c); deep(c); (c.children || []).forEach(deep); return c; };
  n.children.forEach(deep);
  return n;
}
const body = deep(D.parse(html));
let clock = 1000000;
let uiZoom = want.ui_zoom || 1;
let stageRect = Object.assign({ left: 0, top: 0, width: 800, height: 600 }, want.stage || {});
const base = Object.assign({ w: 800, h: 400 }, want.base || {});
const calls = { gv: [], open: [] };
const winListeners = {};
const document = {
  body, querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => deep(D.makeEl(t.toLowerCase())),
  addEventListener(t, f) { (D.docListeners[t] = D.docListeners[t] || []).push(f); }, dispatchEvent() { return true; },
};
const ctx = {
  console, JSON, Math, Object, Array, String, Number, Boolean, Error, isNaN, document,
  Date: { now: () => clock },
  setTimeout: () => 0, clearTimeout: () => {},
  fomsUiZoom: () => uiZoom,
  GlobalImageViewer: { open: (files, i) => calls.gv.push({ files, i }) },
  open: (url, target) => { calls.open.push({ url, target }); return null; },
  addEventListener(t, f) { (winListeners[t] = winListeners[t] || []).push(f); },
};
ctx.window = ctx;

const viewer = body.querySelector('[data-pp-viewer]');
const stage = viewer.querySelector('[data-pp-v-zoom]');
const img = viewer.querySelector('[data-pp-v-img]');
// 그림 src 는 속성으로(브라우저처럼 getAttribute 로 보인다) · style 은 transform 만
Object.defineProperty(img, 'src', { get() { return this.getAttribute('src') || ''; }, set(v) { this.setAttribute('src', v); } });
img.style = { transform: '' };
stage.style = {};
function parsed() {
  const t = img.style.transform || '';
  const m = /translate\((-?[\d.e-]+)px, (-?[\d.e-]+)px\) scale\(([\d.e-]+)\)/.exec(t);
  return m ? { tx: Number(m[1]) * uiZoom, ty: Number(m[2]) * uiZoom, k: Number(m[3]) } : { tx: 0, ty: 0, k: 1 };
}
stage.getBoundingClientRect = () => Object.assign({ right: stageRect.left + stageRect.width, bottom: stageRect.top + stageRect.height }, stageRect);
img.getBoundingClientRect = () => {
  const p = parsed();
  const fit = Math.min(1, stageRect.width / base.w, stageRect.height / base.h); // max-width · max-height 100% = 줄여 맞춤(비율 그대로)
  const w = base.w * fit * p.k;
  const h = base.h * fit * p.k;
  const cx = stageRect.left + stageRect.width / 2 + p.tx;
  const cy = stageRect.top + stageRect.height / 2 + p.ty;
  return { left: cx - w / 2, top: cy - h / 2, width: w, height: h, right: cx + w / 2, bottom: cy + h / 2 };
};

vm.createContext(ctx);
['viewer', 'zoom'].forEach((n) => {
  const f = path.join(root, 'static/js/production/foms-production-parts-' + n + '.js');
  vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
});

const pt = (xy) => ({ clientX: xy[0], clientY: xy[1] });
function snap(extra) {
  const z = ctx.FomsPartsZoom.state();
  const cls = (stage.getAttribute('class') || '').split(/\s+/);
  const card = viewer.querySelector('[data-pp-v-page]');
  return Object.assign({ scale: Math.round(z.scale * 1000) / 1000, tx: Math.round(z.tx * 10) / 10, ty: Math.round(z.ty * 10) / 10,
    transform: img.style.transform, zoomed: cls.includes('is-zoomed'), anim: cls.includes('is-anim'), hidden: viewer.hidden,
    src: img.getAttribute('src'), img_hidden: img.hidden, page: card ? card.textContent.trim() : '',
    gv: calls.gv.length, open: calls.open.map((c) => c.url), acts: acts() }, extra || {});
}
// 크게 보기 아래 줄 단추 · 글(카드 단추 칸 복사본 — test_production_start_strong_viewer_1127)
function acts() {
  const box = viewer.querySelector('[data-pp-v-act]');
  return (box ? box.children : []).filter((c) => c.tag).map((c) => ({ tag: c.tag, cls: c.getAttribute('class') || '',
    proxy: c.getAttribute('data-pp-proxy') || '', text: String(c.textContent || '').replace(/\s+/g, ' ').trim() }));
}
function touch(type, touches, changed) {
  return D.dispatch(stage, type, { cancelable: true, touches: (touches || []).map(pt), changedTouches: (changed || []).map(pt) });
}

const out = [];
for (const s of want.steps) {
  if (s.do === 'open') {
    const card = body.querySelectorAll('[data-pp-card]').find((c) => c.getAttribute('data-no') === String(s.no) && c.querySelector('[data-pp-open]'));
    D.dispatch(card.querySelector('[data-pp-open]'), 'click');
    out.push(snap({ do: 'open', view_url: card.getAttribute('data-view-url') }));
  } else if (s.do === 'touch') {
    const ev = touch(s.type, s.touches, s.changed);
    out.push(snap({ do: 'touch', type: s.type, prevented: ev.defaultPrevented }));
  } else if (s.do === 'clock') {
    clock += s.ms;
    out.push(snap({ do: 'clock' }));
  } else if (s.do === 'tap') {
    touch('touchstart', [[s.x, s.y]], [[s.x, s.y]]);
    clock += 60;
    const ev = touch('touchend', [], [[s.x, s.y]]);
    if (!ev.defaultPrevented) { D.dispatch(stage, 'click'); } // 브라우저는 막지 않은 두드림에만 click 을 만든다
    clock += 120;
    out.push(snap({ do: 'tap', prevented: ev.defaultPrevented }));
  } else if (s.do === 'click') {
    D.dispatch(s.on === 'img' ? img : stage, 'click');
    out.push(snap({ do: 'click' }));
  } else if (s.do === 'wheel') {
    const ev = D.dispatch(stage, 'wheel', { deltaY: s.dy, clientX: s.x, clientY: s.y });
    out.push(snap({ do: 'wheel', prevented: ev.defaultPrevented }));
  } else if (s.do === 'mouse') {
    const ev = D.dispatch(s.type === 'mousedown' ? stage : body, s.type, { clientX: s.x, clientY: s.y, button: 0 });
    out.push(snap({ do: 'mouse', prevented: ev.defaultPrevented }));
  } else if (s.do === 'step') {
    D.dispatch(viewer.querySelector('[data-pp-v-step="' + s.by + '"]'), 'click');
    out.push(snap({ do: 'step' }));
  } else if (s.do === 'close') {
    D.dispatch(viewer.querySelector('[data-pp-v-close]'), 'click');
    out.push(snap({ do: 'close' }));
  } else if (s.do === 'stage') {
    stageRect = Object.assign({}, stageRect, s.rect);
    out.push(snap({ do: 'stage' }));
  } else if (s.do === 'resize') {
    (winListeners.resize || []).forEach((f) => f({ type: 'resize' }));
    out.push(snap({ do: 'resize', resize_listeners: (winListeners.resize || []).length }));
  } else if (s.do === 'updated') {
    (D.docListeners['foms:part-card-updated'] || []).forEach((f) => f({ type: 'foms:part-card-updated' }));
    out.push(snap({ do: 'updated' }));
  } else if (s.do === 'view') { // 칸 단추(전체 도면 · 작업 중 · 완료)
    D.dispatch(body.querySelector('[data-pp-view="' + s.v + '"]'), 'click');
    out.push(snap({ do: 'view' }));
  } else if (s.do === 'ui_zoom') {
    uiZoom = s.value;
    out.push(snap({ do: 'ui_zoom' }));
  }
}
process.stdout.write(JSON.stringify({ out }));
