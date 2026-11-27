// 생산 도면 판 — 여러 명이 같이 작업(M2) JS 를 서버가 그린 진짜 판(argv[2]) 위에서 Node 로 돌린다(설계서 2026-11-25 multi-holder §11 M2).
// tests/domains/test_production_multi_holder_board.py 가 부른다. want = argv[3] {steps: [...], posts: [서버 답…], gets: [서버 답…]}.
// 판 JS 다섯(viewer → claim → modal → crew → parts, 받아 오기 sync 는 want.sync 일 때)을 차례로 싣고 steps 를 차례로 한다:
//   {do:'parity'} 모든 카드의 서버 단추 칸 ↔ JS 가 다시 그린 단추 칸 · {do:'click', key, act} 카드 단추 · {do:'modal'} 창 모습 ·
//   {do:'notice', key} 넘김 말풍선 누름 ·
//   {do:'run'} 실행 단추 · {do:'choice', text} 관리자 고르기 · {do:'who', index} 사람 고르기 · {do:'card', key} 카드 모습 · {do:'sync'} 받아 오기 한 번 ·
//   {do:'timers'} 미뤄 둔 일(창 잠금 풀기 등)을 지금 돌림.
// 서버 답(posts · gets)은 파이썬이 진짜 API 로 받은 JSON 이다(가짜 글 없음). 결과는 stdout JSON {out: [...], calls: [...]}.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]);
const D = fakeDom();
// 가짜 DOM 은 조합자가 없다 — 판 JS 가 쓰는 자손 고르기("[data-pp-other=\"cut\"] i" · "[data-pp-actbox] [data-pp-act]")만 더한다
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
  n.appendChild = (c) => { // 브라우저처럼 textContent 로 넣은 글은 글 마디로 남기고 그 뒤에 붙인다
    if (n.text) { n.children.unshift({ tag: null, children: [], parentNode: n, textContent: n.text }); n.text = null; }
    add(c); deep(c); (c.children || []).forEach(deep); return c;
  };
  const ins = n.insertBefore.bind(n);
  n.insertBefore = (c, ref) => { ins(c, ref); deep(c); return c; };
  n.children.forEach(deep);
  return n;
}
const body = deep(D.parse(html));
const calls = [];
const posts = (want.posts || []).slice();
const gets = (want.gets || []).slice();
const docListeners = {};
const document = {
  body, visibilityState: 'visible',
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  createElement: (t) => deep(D.makeEl(t.toLowerCase())), createTextNode: (t) => ({ tag: null, children: [], parentNode: null, textContent: String(t) }),
  addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); }, dispatchEvent() { return true; },
  contains: (n) => body.contains(n),
};
const timers = [];
const ctx = {
  console, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, Error, isNaN, document,
  navigator: { onLine: true },
  CustomEvent: function CustomEvent(type, init) { this.type = type; this.detail = (init || {}).detail; },
  setTimeout: (f, ms) => { timers.push({ f, ms }); return timers.length; }, clearTimeout: () => {},
  setInterval: () => 0,
  fetch: (url, opts) => {
    const isGet = !opts || !opts.method || opts.method === 'GET';
    calls.push({ url, method: isGet ? 'GET' : opts.method, body: isGet ? null : JSON.parse(opts.body) });
    const next = isGet ? gets.shift() : posts.shift();
    const status = next && next.__status ? next.__status : 200;
    const data = next && next.__status ? next.body : next;
    return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data || { success: true, data: {} }) });
  },
};
ctx.window = ctx;
// 텍스트 노드 — appendChild 가 받는 꼴(fake DOM 의 textNode 와 같은 모양)
vm.createContext(ctx);
const files = ['viewer', 'claim', 'modal', 'crew', ''].concat(want.sync ? ['sync'] : []);
files.forEach((n) => {
  const f = path.join(root, 'static/js/production/foms-production-parts' + (n ? '-' + n : '') + '.js');
  vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
});

const modal = body.querySelector('[data-pp-modal]');
const click = (el) => D.dispatch(el, 'click');
const tick = () => new Promise((r) => setTimeout(r, 0));
const text = (n) => (n ? n.textContent.replace(/\s+/g, ' ').trim() : '');
const cardOf = (key) => body.querySelectorAll('[data-pp-card]').find((c) => c.getAttribute('data-key') === key);
function shape(n) {
  return { tag: n.tag, cls: n.getAttribute('class') || '', act: n.getAttribute('data-pp-act'), text: text(n),
    kids: n.children.filter((k) => k.tag).map(shape) };
}
function actbox(card) {
  return card.querySelector('[data-pp-actbox]').children.filter((k) => k.tag && !(k.getAttribute('class') || '').includes('pp-why')).map(shape);
}
function cardState(card) {
  const tag = card.querySelector('[data-pp-tag]');
  const why = card.querySelector('[data-pp-actbox] .pp-why');
  const note = card.querySelector('[data-pp-notice]');
  return { key: card.getAttribute('data-key'), state: card.getAttribute('data-state'), cls: card.getAttribute('class'),
    in_need: card.getAttribute('data-in-need'), in_done: card.getAttribute('data-in-done'),
    picked_me: card.getAttribute('data-picked-me'), done_me: card.getAttribute('data-done-me'),
    crew: JSON.parse(card.getAttribute('data-pp-crew') || '{}'), act: actbox(card),
    tag: tag ? text(tag) : null, tag_aria: tag ? tag.getAttribute('aria-label') : null,
    why: why && !why.hidden ? text(why) : null, notice: note && !note.hidden ? text(note) : null,
    notice_in_img: !!(note && note.parentNode && (note.parentNode.getAttribute('class') || '').split(' ').includes('pp-img')) };
}
function modalState() {
  const q = (s) => modal.querySelector(s);
  const run = q('[data-pp-modal-run]');
  const choices = q('[data-pp-modal-choices]');
  const label = modal.querySelector('.foms-prod-change-modal__alert-label');
  return { hidden: modal.hidden, title: text(q('[data-pp-modal-title]')), note: q('[data-pp-modal-note]').hidden ? '' : text(q('[data-pp-modal-note]')),
    line: label ? text(label) : '', body: q('[data-pp-modal-body]').hidden ? '' : text(q('[data-pp-modal-body]')), err: q('[data-pp-modal-err]').hidden ? '' : text(q('[data-pp-modal-err]')),
    run: { text: text(run), hidden: run.hidden, locked: run.getAttribute('aria-disabled') === 'true' },
    close: text(q('[data-pp-modal-close]')), choices_cls: choices.getAttribute('class'), choices_hidden: choices.hidden,
    choices: choices.children.filter((b) => b.tag).map((b) => ({ text: text(b), choice: b.getAttribute('data-pp-choice'),
      target: b.getAttribute('data-pp-target'), next: b.hasAttribute('data-pp-next'), who: b.getAttribute('data-pp-who'),
      pressed: b.getAttribute('aria-pressed'), cls: b.getAttribute('class') })),
    lost: (modal.getAttribute('class') || '').includes('is-lost') };
}
function counts() {
  const out = {};
  body.querySelectorAll('[data-pp-count]').forEach((n) => { out[n.getAttribute('data-pp-count')] = (out[n.getAttribute('data-pp-count')] || []).concat(text(n)); });
  return out;
}

(async () => {
  const out = [];
  for (const s of want.steps) {
    if (s.do === 'parity') { // 서버가 그린 단추 칸 ↔ 같은 카드를 JS 가 다시 그린 단추 칸
      const diffs = [];
      body.querySelectorAll('[data-pp-card]').forEach((card) => {
        const before = JSON.stringify(actbox(card));
        const tagBefore = card.querySelector('[data-pp-tag]') ? text(card.querySelector('[data-pp-tag]')) : null;
        ctx.FomsPartsCards.render(card);
        const after = JSON.stringify(actbox(card));
        const tagAfter = card.querySelector('[data-pp-tag]') ? text(card.querySelector('[data-pp-tag]')) : null;
        if (before !== after || tagBefore !== tagAfter) { diffs.push({ key: card.getAttribute('data-key'), before, after, tagBefore, tagAfter }); }
      });
      out.push({ do: 'parity', cards: body.querySelectorAll('[data-pp-card]').length, diffs });
    } else if (s.do === 'click') {
      const btn = cardOf(s.key).querySelector('[data-pp-actbox] [data-pp-act="' + s.act + '"]');
      if (!btn) { throw new Error('no button ' + s.act + ' on ' + s.key); }
      click(btn);
      out.push({ do: 'click', modal: modalState() });
    } else if (s.do === 'modal') {
      out.push({ do: 'modal', modal: modalState() });
    } else if (s.do === 'run') {
      const before = calls.length;
      click(modal.querySelector('[data-pp-modal-run]'));
      await tick(); await tick(); await tick();
      out.push({ do: 'run', sent: calls.length - before, modal: modalState(), status: text(body.querySelector('[data-foms-home-status]')) });
    } else if (s.do === 'choice') {
      const btn = modal.querySelector('[data-pp-modal-choices]').children.find((b) => text(b) === s.text);
      if (!btn) { throw new Error('no choice ' + s.text); }
      const before = calls.length;
      click(btn);
      await tick(); await tick(); await tick();
      out.push({ do: 'choice', sent: calls.length - before, modal: modalState(), status: text(body.querySelector('[data-foms-home-status]')) });
    } else if (s.do === 'who') {
      click(modal.querySelectorAll('[data-pp-who]')[s.index]);
      out.push({ do: 'who', modal: modalState() });
    } else if (s.do === 'card') {
      out.push({ do: 'card', card: cardState(cardOf(s.key)), counts: counts() });
    } else if (s.do === 'apply') { // 받아 오기와 같은 고치기(FomsPartsCards.apply)에 서버 표시 한 장
      ctx.FomsPartsCards.apply(cardOf(s.key), s.mark);
      out.push({ do: 'apply', card: cardState(cardOf(s.key)) });
    } else if (s.do === 'sync') {
      ctx.__FOMS_PROD_PARTS_BOUND.syncTick();
      await tick(); await tick(); await tick(); await tick();
      out.push({ do: 'sync' });
    } else if (s.do === 'notice') { // 넘김 말풍선을 누름 — 바로 닫히고 그림 열기(크게 보기)로 안 넘어간다
      const note = cardOf(s.key).querySelector('[data-pp-notice]');
      const ev = D.dispatch(note, 'click');
      const viewer = body.querySelector('[data-pp-viewer]');
      out.push({ do: 'notice', hidden: note.hidden, stopped: ev.stopped, viewer_open: viewer ? !viewer.hidden : null });
    } else if (s.do === 'timers') {
      timers.splice(0).forEach((t) => t.f());
      out.push({ do: 'timers' });
    } else if (s.do === 'close') {
      click(modal.querySelector('[data-pp-modal-close]'));
      out.push({ do: 'close', hidden: modal.hidden });
    }
  }
  process.stdout.write(JSON.stringify({ out, calls }));
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
