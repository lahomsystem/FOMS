// 생산 새 흐름(설계서 2026-11-28-production-my-steps-flow §3-2 · §3-4 · §3-6) — 서버가 그린 진짜 화면(argv[2]) 위에서 판 JS 아홉
// (viewer → claim → modal → cancel → crew → give → parts → sync → flow, 페이지와 같은 차례)을 Node 로 돌린다.
// tests/domains/test_production_flow_screen.py 가 부른다. want = argv[3] 파일(JSON) {href, posts: [서버 답…], gets: [{match, json | html, header}…], steps}.
// GET 은 want.gets 에서 주소에 match 글이 든 첫 답을 꺼내 준다(없으면 실패 — 부르지 말아야 할 받기를 잡는다). 서버 답은 파이썬이 진짜로 받은 것.
// steps: {do:'click', key, act, part?} 카드 단추 · {do:'run'} 확인 창 실행 · {do:'modal'} 창 모습 · {do:'close'} · {do:'card', key, part?} 카드 모습 ·
//   {do:'day', key} '내 공정' 띠 줄 누름 · {do:'screen'} 보이는 카드 · 묶음 · 숫자 · {do:'sync'} 30초 받아 오기 한 번 · {do:'settle'} 미뤄 둔 일 · 받기 끝내기.
// 결과는 stdout JSON {out, calls}.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')); // 화면 HTML 이 든 답이 길어 파일로
const D = fakeDom();
// 가짜 DOM 은 조합자가 없다 — 판 JS 가 쓰는 자손 고르기만 더한다(production_multi_holder_node_checks.js 와 같은 꼴)
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
function deep(n) {
  if (!n || !n.tag || n.__deep) { return n; }
  n.__deep = true;
  n.querySelectorAll = (sel) => all(n, sel);
  n.querySelector = (sel) => all(n, sel)[0] || null;
  const add = n.appendChild.bind(n);
  n.appendChild = (c) => {
    if (n.text) { n.children.unshift({ tag: null, children: [], parentNode: n, textContent: n.text }); n.text = null; }
    add(c); deep(c); (c.children || []).forEach(deep); return c;
  };
  const ins = n.insertBefore.bind(n);
  n.insertBefore = (c, ref) => { ins(c, ref); deep(c); return c; };
  const rep = n.replaceChild.bind(n);
  n.replaceChild = (c, old) => { if (c.parentNode) { c.parentNode.removeChild(c); } rep(c, old); deep(c); return old; };
  const setInner = Object.getOwnPropertyDescriptor(n, 'innerHTML');
  Object.defineProperty(n, 'innerHTML', { set(v) { setInner.set.call(n, v); n.children.forEach(deep); }, configurable: true });
  n.children.forEach(deep);
  return n;
}
const body = deep(D.parse(html));
const calls = [];
const posts = (want.posts || []).slice();
const gets = (want.gets || []).slice();
const docListeners = {};
const timers = [];
const document = {
  body, visibilityState: 'visible',
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => deep(D.makeEl(t.toLowerCase())),
  createTextNode: (t) => ({ tag: null, children: [], parentNode: null, textContent: String(t) }),
  addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
  dispatchEvent(ev) { (docListeners[ev.type] || []).forEach((f) => f(ev)); return true; },
  contains: (n) => body.contains(n),
};
const ctx = {
  console, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, Error, RegExp, isNaN, URL, document,
  navigator: { onLine: true },
  location: { href: 'http://localhost' + (want.href || '/erp/production/home'), origin: 'http://localhost' },
  CustomEvent: function CustomEvent(type, init) { this.type = type; this.detail = (init || {}).detail; },
  setTimeout: (f, ms) => { timers.push({ f, ms }); return timers.length; }, clearTimeout: () => {},
  setInterval: () => 0,
  fetch: (url, opts) => {
    const isGet = !opts || !opts.method || opts.method === 'GET';
    calls.push({ url: String(url), method: isGet ? 'GET' : opts.method, body: isGet ? null : JSON.parse(opts.body) });
    if (!isGet) {
      const next = posts.shift();
      const status = next && next.__status ? next.__status : 200;
      const data = next && next.__status ? next.body : next;
      return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data || { success: true, data: {} }) });
    }
    const i = gets.findIndex((g) => String(url).indexOf(g.match) >= 0);
    if (i < 0) { return Promise.reject(new Error('unexpected GET ' + url)); }
    const g = gets.splice(i, 1)[0];
    const head = g.header || {};
    return Promise.resolve({ ok: true, status: 200, headers: { get: (k) => head[k] || null },
      json: () => Promise.resolve(g.json), text: () => Promise.resolve(g.html) });
  },
};
ctx.window = ctx;
vm.createContext(ctx);
['viewer', 'claim', 'modal', 'cancel', 'crew', 'give', '', 'sync'].forEach((n) => {
  const f = path.join(root, 'static/js/production/foms-production-parts' + (n ? '-' + n : '') + '.js');
  vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
});
const flowFile = path.join(root, 'static/js/production/foms-production-flow.js');
vm.runInContext(fs.readFileSync(flowFile, 'utf8'), ctx, { filename: flowFile });

const modal = () => body.querySelector('[data-pp-modal]');
const click = (el) => D.dispatch(el, 'click');
const tick = () => new Promise((r) => setImmediate(r));
async function settle() { for (let i = 0; i < 6; i += 1) { await tick(); timers.splice(0).forEach((t) => t.f()); await tick(); } }
const text = (n) => (n ? n.textContent.replace(/\s+/g, ' ').trim() : '');
function cardOf(key, part) {
  return body.querySelectorAll('[data-pp-card]').find((c) => c.getAttribute('data-key') === key && (!part || c.getAttribute('data-part') === part));
}
function cardState(c) {
  if (!c) { return null; }
  return { key: c.getAttribute('data-key'), part: c.getAttribute('data-part'), state: c.getAttribute('data-state'),
    picked_me: c.getAttribute('data-picked-me'), cls: c.getAttribute('class'),
    others: c.querySelectorAll('[data-pp-other]').map((s) => s.getAttribute('data-pp-other') + ':' + s.getAttribute('class')),
    acts: c.querySelectorAll('[data-pp-actbox] [data-pp-act]').map((b) => [b.getAttribute('data-pp-act'), text(b)]),
    text: text(c.querySelector('[data-pp-actbox]')) };
}
function hiddenUp(n) { for (let p = n; p && p.tag; p = p.parentNode) { if (p.hidden) { return true; } } return false; }
function screen() {
  const visible = body.querySelectorAll('[data-pp-card]').filter((c) => !hiddenUp(c) && !c.classList.contains('fpf-off'));
  const done = body.querySelector('[data-flow-done]');
  const count = (k) => { const s = body.querySelector('[data-flow-count="' + k + '"]'); return s ? { text: text(s), hidden: s.hidden } : null; };
  const empty = body.querySelector('[data-flow-empty]') || body.querySelector('[data-pp-empty]');
  const allChip = body.querySelector('[data-pp-count="all"]');
  return {
    cards: visible.filter((c) => !(done && done.contains(c))).map((c) => c.getAttribute('data-key') + (c.getAttribute('data-part') ? '@' + c.getAttribute('data-part') : '')),
    done: done ? visible.filter((c) => done.contains(c)).map((c) => c.getAttribute('data-key')) : null,
    groups: body.querySelectorAll('[data-flow-group="day"], [data-flow-group="order"]').filter((g) => !g.hidden).map((g) => text(g.querySelector('h3, h4'))),
    done_n: text(body.querySelector('[data-flow-done-n]')),
    pressed: body.querySelectorAll('[data-flow-day]').filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.getAttribute('data-flow-day')),
    mine: count('mine'), crew: count('crew'), all_chip: allChip ? text(allChip) : null,
    empty: empty ? { text: text(empty), hidden: empty.hidden } : null,
    status: text(body.querySelector('[data-foms-home-status]')),
    day_pane: (body.querySelector('[data-foms-home-daypane]') || { getAttribute: () => null }).getAttribute('data-foms-home-daypane'),
  };
}
function modalState() {
  const m = modal();
  const q = (s) => m.querySelector(s);
  const label = m.querySelector('.foms-prod-change-modal__alert-label');
  return { hidden: m.hidden, title: text(q('[data-pp-modal-title]')), line: label ? text(label) : '',
    run: text(q('.foms-prod-change-modal__foot [data-pp-modal-run]')) };
}

(async () => {
  const out = [];
  await settle(); // 처음 숫자 받기(숫자 없이 그린 탭)
  for (const s of want.steps) {
    if (s.do === 'click') {
      const card = cardOf(s.key, s.part);
      const btn = card && card.querySelector('[data-pp-actbox] [data-pp-act="' + s.act + '"]');
      if (!btn) { throw new Error('no button ' + s.act + ' on ' + s.key); }
      click(btn);
      await tick();
      out.push({ do: 'click', modal: modalState() });
    } else if (s.do === 'run') {
      const before = calls.length;
      click(modal().querySelector('.foms-prod-change-modal__foot [data-pp-modal-run]'));
      await settle();
      out.push({ do: 'run', sent: calls.length - before, modal: modalState(), screen: screen() });
    } else if (s.do === 'close') {
      click(modal().querySelector('[data-pp-modal-close]'));
      await settle();
      out.push({ do: 'close', screen: screen() });
    } else if (s.do === 'modal') {
      out.push({ do: 'modal', modal: modalState() });
    } else if (s.do === 'card') {
      out.push({ do: 'card', card: cardState(cardOf(s.key, s.part)) });
    } else if (s.do === 'day') {
      click(body.querySelector('[data-flow-day="' + s.key + '"]'));
      out.push({ do: 'day', screen: screen() });
    } else if (s.do === 'screen') {
      out.push({ do: 'screen', screen: screen() });
    } else if (s.do === 'sync') {
      ctx.__FOMS_PROD_PARTS_BOUND.syncTick();
      await settle();
      out.push({ do: 'sync', screen: screen() });
    } else if (s.do === 'settle') {
      await settle();
      out.push({ do: 'settle', screen: screen() });
    }
  }
  process.stdout.write(JSON.stringify({ out, calls, left: gets.map((g) => g.match) }));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
