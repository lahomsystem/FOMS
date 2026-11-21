// '내 공정' 탭 오른쪽 판 — 서버가 그린 진짜 조각(HTML 파일 경로 = argv[2]) 위에서 세 JS 를 Node 로 돌린다.
// tests/domains/test_production_home_step_panel.py 가 부른다(설계서 2026-11-21-production-my-steps-panel §3-5 · §6).
// 1) foms-production-home-steps.js: 줄 누름 = 판만 바뀜(요청 0 · 주소 replaceState order=) · 공정 탭 = 그 탭 고른 줄 주소 ·
//    [<공정> 끝] = 확인 창 → [취소] POST 0 → [<공정> 끝] = POST /api/orders/<id>/production/steps {key, done:true} 한 번 → 다음 손님 주소 ·
//    그림 = 전역 원본 뷰어(그림 원본 전부).
// 2) foms-production-sheet-page.js: 판 [불량] → 칩 → POST …/production/defect {reason}.
// 3) tablet-domain-sheets.js: 판 [보류] → 사유 창 → POST …/production/hold {active:true, reason}, [보류 해제] → 확인 → {active:false}.
// 작은 가짜 DOM: 태그 · .class · #id · [attr] · [attr="v"] 묶음 + 쉼표 목록만(조합자 없음 — 세 파일이 그것만 쓴다).
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const html = fs.readFileSync(process.argv[2], 'utf8');

// ── 아주 작은 HTML 읽기(서버 조각 전용: 따옴표 속성 · 빈 요소 · 주석 · script 본문 건너뜀) ──
const VOID = new Set(['img', 'br', 'input', 'meta', 'link', 'hr', 'source', 'path', 'circle', 'rect', 'line', 'use', 'polyline', 'col', 'wbr']);
function decode(s) {
  return s.replace(/&(#\d+|#x[0-9a-f]+|amp|lt|gt|quot|apos|nbsp);/gi, (m, e) => {
    if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }[e.toLowerCase()];
  });
}
function parseSel(sel) {
  const m = { tag: null, id: null, classes: [], attrs: [] };
  const re = /^([a-z][a-z0-9]*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'))?\]/gi;
  let x;
  while ((x = re.exec(sel))) {
    if (x[1]) m.tag = x[1].toLowerCase();
    else if (x[2]) m.id = x[2];
    else if (x[3]) m.classes.push(x[3]);
    else m.attrs.push([x[4], x[5] !== undefined ? x[5] : x[6]]);
  }
  return m;
}
function matchOne(node, sel) {
  if (!node.tag) return false;
  const m = parseSel(sel.trim());
  if (m.tag && node.tag !== m.tag) return false;
  if (m.id && node.attrs.id !== m.id) return false;
  const cls = (node.attrs.class || '').split(/\s+/);
  if (m.classes.some((c) => !cls.includes(c))) return false;
  return m.attrs.every(([k, v]) => k in node.attrs && (v === undefined || node.attrs[k] === v));
}
function matches(node, sel) { return sel.split(',').some((s) => matchOne(node, s)); }
function walk(node, out) { node.children.forEach((c) => { out.push(c); walk(c, out); }); return out; }

function makeEl(tag) {
  const node = {
    tag, attrs: {}, children: [], parentNode: null, listeners: {}, text: null, disabled: false,
    get nodeType() { return 1; },
    get tagName() { return tag.toUpperCase(); },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'disabled') this.disabled = true; },
    hasAttribute(k) { return k in this.attrs; },
    removeAttribute(k) { delete this.attrs[k]; },
    get className() { return this.attrs.class || ''; },
    set className(v) { this.attrs.class = String(v); },
    get id() { return this.attrs.id || ''; },
    get hidden() { return 'hidden' in this.attrs; },
    set hidden(v) { if (v) this.attrs.hidden = ''; else delete this.attrs.hidden; },
    get classList() {
      const self = this;
      const list = () => (self.attrs.class || '').split(/\s+/).filter(Boolean);
      const set = (arr) => { self.attrs.class = arr.join(' '); };
      return {
        contains: (c) => list().includes(c),
        add: (...cs) => set([...new Set(list().concat(cs))]),
        remove: (...cs) => set(list().filter((x) => !cs.includes(x))),
        toggle: (c, on) => { const has = list().includes(c); const want = on === undefined ? !has : !!on; if (want && !has) set(list().concat(c)); if (!want && has) set(list().filter((x) => x !== c)); return want; },
      };
    },
    get textContent() { return this.text !== null ? this.text : this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this.children = []; this.text = String(v); },
    get innerText() { return this.textContent; },
    get firstElementChild() { return this.children[0] || null; },
    appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.text = null; this.children.push(c); return c; },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; },
    replaceChild(n, o) { const i = this.children.indexOf(o); this.children[i] = n; n.parentNode = this; o.parentNode = null; return o; },
    cloneNode(deep) { const c = makeEl(tag); c.attrs = Object.assign({}, this.attrs); if (deep) this.children.forEach((k) => c.appendChild(k.cloneNode(true))); return c; },
    contains(n) { while (n) { if (n === this) return true; n = n.parentNode; } return false; },
    matches(sel) { return matches(this, sel); },
    closest(sel) { let n = this; while (n && n.tag) { if (matches(n, sel)) return n; n = n.parentNode; } return null; },
    querySelector(sel) { return walk(this, []).find((n) => matches(n, sel)) || null; },
    querySelectorAll(sel) { return walk(this, []).filter((n) => matches(n, sel)); },
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
    removeEventListener() {},
    getClientRects() { let n = this; while (n && n.tag) { if (n.hidden) return []; n = n.parentNode; } return [{}]; },
    getBoundingClientRect() { return { top: 0, left: 0, width: 10, height: 10, bottom: 10, right: 10 }; },
    focus() { focused.push(this); },
    click() { dispatch(this, 'click'); },
  };
  return node;
}
function textNode(t) { return { tag: null, children: [], parentNode: null, get textContent() { return t; } }; }

function parse(src) {
  const top = makeEl('body');
  const stack = [top];
  const re = /<!--[\s\S]*?-->|<script\b[^>]*>[\s\S]*?<\/script>|<\/([a-zA-Z][\w-]*)\s*>|<([a-zA-Z][\w-]*)((?:\s+[^\s"'>\/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>|([^<]+)/g;
  let m;
  while ((m = re.exec(src))) {
    const cur = stack[stack.length - 1];
    if (m[1]) {
      const t = m[1].toLowerCase();
      for (let i = stack.length - 1; i > 0; i--) { if (stack[i].tag === t) { stack.length = i; break; } }
    } else if (m[2]) {
      const t = m[2].toLowerCase();
      const n = makeEl(t);
      const are = /([^\s"'>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
      let a;
      while ((a = are.exec(m[3] || ''))) n.attrs[a[1]] = decode(a[2] !== undefined ? a[2] : a[3] !== undefined ? a[3] : a[4] !== undefined ? a[4] : '');
      if ('disabled' in n.attrs) n.disabled = true;
      cur.appendChild(n);
      if (!m[4] && !VOID.has(t)) stack.push(n);
    } else if (m[5] && m[0][0] !== '<') {
      cur.children.push(Object.assign(textNode(decode(m[5])), { parentNode: cur }));
    }
  }
  return top;
}

// ── 문서 · 창 ──
const body = parse(html);
const focused = [];
const docListeners = {};
const calls = { fetch: [], replaceState: [], replace: [], assign: [], viewer: [], reason: [], confirm: [] };
let fetchReply = () => ({ success: true, data: {} });
function dispatch(target, type, extra) {
  const ev = Object.assign({ type, target, defaultPrevented: false, button: 0, metaKey: false, ctrlKey: false, shiftKey: false,
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() {} }, extra || {});
  let n = target;
  while (n && n.tag) { (n.listeners[type] || []).forEach((f) => f.call(n, ev)); n = n.parentNode; }
  (docListeners[type] || []).forEach((f) => f(ev));
  return ev;
}
const store = {};
const location = {
  href: 'http://127.0.0.1/erp/production/home?tab=steps', origin: 'http://127.0.0.1', pathname: '/erp/production/home', search: '?tab=steps',
  replace(u) { calls.replace.push(u); }, assign(u) { calls.assign.push(u); }, reload() { calls.replace.push('reload'); },
};
const document = {
  body, readyState: 'complete', referrer: '',
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  getElementById: (id) => body.querySelector('#' + id),
  createElement: (t) => makeEl(t.toLowerCase()),
  addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
  removeEventListener() {},
  contains: (n) => body.contains(n),
  dispatchEvent() { return true; },
};
const ctx = {
  console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout,
  document, location,
  history: { state: null, replaceState(s, t, u) { calls.replaceState.push(u); } },
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
  navigator: { onLine: true },
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  fetch: (url, opts) => {
    calls.fetch.push({ url, method: (opts || {}).method, body: (opts || {}).body ? JSON.parse(opts.body) : null });
    const data = fetchReply(url);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
  },
  confirm: (msg) => { calls.confirm.push(msg); return true; },
  alert: (msg) => { throw new Error('alert: ' + msg); },
  GlobalImageViewer: { open: (files, i) => calls.viewer.push({ files, i }) },
  FomsReasonSheet: { open: (opts) => calls.reason.push(opts), close() {} },
  ERPUtils: { safeJsonParse: (v, fb) => { try { return JSON.parse(v); } catch (e) { return fb; } } },
};
ctx.window = ctx;
ctx.addEventListener = (t, f) => { (docListeners['win:' + t] = docListeners['win:' + t] || []).push(f); };
vm.createContext(ctx);
for (const rel of ['static/js/production/foms-production-home-steps.js', 'static/js/production/foms-production-sheet-page.js',
  'static/js/foms/tablet-domain-sheets.js']) {
  vm.runInContext(read(rel), ctx, { filename: rel });
}
const flush = () => new Promise((r) => setImmediate(r));
const $ = (s) => body.querySelector(s);
const pane = (id) => $(`[data-foms-step-pane="${id}"]`);
const modal = $('[data-foms-step-modal]');

(async () => {
  const want = JSON.parse(process.argv[3]); // {first, hold, next, key, label, me, other_tab}
  // 0) order= 로 고른 탭은 마지막 탭 기억보다 앞(home.js 가 읽기 전에 기억을 맞춘다)
  if (want.pin) assert.strictEqual(store['foms-prod-step-tab'], want.pin, 'pin → 기억');
  // 1) 줄 누름 = 판만 바뀐다(요청 0) · 주소 · [다시 받기]
  assert.ok(!pane(want.first).hidden && pane(want.hold).hidden, '처음 고른 줄 판만 보임');
  const link = $(`[data-foms-home-qrow="${want.hold}"]`).querySelector('[data-foms-step-sheet]');
  const ev = dispatch(link, 'click');
  assert.ok(ev.defaultPrevented, '줄 링크 누름은 이동하지 않는다');
  assert.ok(pane(want.first).hidden && !pane(want.hold).hidden, '판이 바뀐다');
  assert.ok($(`[data-foms-home-qrow="${want.hold}"]`).classList.contains('is-on') && !$(`[data-foms-home-qrow="${want.first}"]`).classList.contains('is-on'));
  assert.strictEqual(calls.fetch.length, 0, '줄 누름 요청 0');
  assert.strictEqual(calls.replaceState.pop(), `/erp/production/home?tab=steps&order=${want.hold}`);
  assert.strictEqual($('[data-foms-home-reload]').getAttribute('href'), `/erp/production/home?tab=steps&order=${want.hold}`);
  // 보류 줄 판엔 [끝] 이 없다
  assert.strictEqual(pane(want.hold).querySelector('[data-foms-step-finish]'), null);
  // 2) 공정 탭 = 그 탭의 고른 줄 주소
  dispatch($(`[data-foms-home-steptab="${want.other_tab}"]`), 'click');
  assert.strictEqual(calls.replaceState.pop(), want.other_url, '공정 탭 주소');
  dispatch($(`[data-foms-home-qrow="${want.first}"]`).querySelector('.fph-qr__n'), 'click');
  assert.ok(!pane(want.first).hidden);
  // 3) [끝] → 확인 창 → [취소] = POST 0
  dispatch(pane(want.first).querySelector('[data-foms-step-finish]'), 'click');
  assert.ok(!modal.hidden && modal.classList.contains('is-open'), '창이 열린다');
  assert.strictEqual(modal.querySelector('[data-foms-step-modal-title]').textContent, `${want.label} 끝으로 바꿀까요?`);
  assert.strictEqual(modal.querySelector('[data-foms-step-modal-run]').textContent, `${want.label} 끝`);
  const item = modal.querySelector('[data-foms-step-modal-list]').textContent;
  assert.ok(item.includes(`${want.label} 중 → ${want.label} 끝 · ${want.me}`) && item.includes(`#${want.first}`), item);
  assert.ok(modal.querySelector('.pp-mimg img'), '판 그림을 창 줄에 옮겨 담는다');
  dispatch(modal.querySelector('[data-foms-step-modal-close]'), 'click');
  assert.ok(modal.hidden && !modal.classList.contains('is-open'));
  dispatch(pane(want.first).querySelector('[data-foms-step-finish]'), 'click');
  dispatch(modal, 'click'); // 바깥(딤) 누름
  assert.ok(modal.hidden);
  dispatch(pane(want.first).querySelector('[data-foms-step-finish]'), 'click');
  (docListeners.keydown || []).forEach((f) => f({ key: 'Escape' }));
  assert.ok(modal.hidden, 'Esc 로 닫힌다');
  assert.strictEqual(calls.fetch.length, 0, '[취소] · 바깥 · Esc = POST 0');
  // 4) [끝] → 창 [끝] = 공정 API 한 번 → 다음 손님 주소
  fetchReply = () => ({ success: true, data: { steps: [], complete_ready: false } });
  dispatch(pane(want.first).querySelector('[data-foms-step-finish]'), 'click');
  dispatch(modal.querySelector('[data-foms-step-modal-run]'), 'click');
  dispatch(modal.querySelector('[data-foms-step-modal-run]'), 'click'); // 두 번 눌러도 한 번
  await flush(); await flush();
  assert.deepStrictEqual(calls.fetch, [{ url: `/api/orders/${want.first}/production/steps`, method: 'POST', body: { key: want.key, done: true } }]);
  assert.deepStrictEqual(calls.replace, [`http://127.0.0.1/erp/production/home?tab=steps&order=${want.next}`]);
  // 실패면 창에 글 · 단추가 풀린다
  calls.fetch.length = 0;
  ctx.fetch = () => Promise.reject(new Error('offline'));
  // 새 판(다음 줄)으로 다시: 창 상태를 비운다
  modal.hidden = true; modal.classList.remove('is-open');
  // 5) 그림 = 원본 뷰어(그림 원본 전부)
  dispatch(pane(want.first).querySelector('[data-foms-step-view]'), 'click');
  assert.strictEqual(calls.viewer.length, 1);
  assert.ok(calls.viewer[0].files.length >= 1 && calls.viewer[0].files.every((f) => f.view_url.startsWith('/api/files/view/')), JSON.stringify(calls.viewer));
  // 6) [불량] → 칩 → 불량 API
  ctx.fetch = (url, opts) => { calls.fetch.push({ url, method: opts.method, body: JSON.parse(opts.body) }); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { latest: { reason: '파손' } } }) }); };
  const bot = pane(want.first).querySelector('[data-foms-prod-sheet-page]');
  dispatch(bot.querySelector('[data-foms-sheet-defect-toggle]'), 'click');
  assert.ok(!bot.querySelector('[data-foms-sheet-defect-reasons]').hidden, '칩이 열린다');
  dispatch(bot.querySelector('[data-foms-sheet-defect-reason="파손"]'), 'click');
  await flush(); await flush();
  assert.deepStrictEqual(calls.fetch.pop(), { url: `/api/orders/${want.first}/production/defect`, method: 'POST', body: { reason: '파손' } });
  assert.ok(bot.querySelector('[data-foms-sheet-defect-recent]').textContent.includes('최근 불량 · 파손'));
  // 7) [보류] → 사유 창 → 보류 API(주소는 그 줄로 먼저 맞춘다 — 새로고침 뒤 같은 줄)
  dispatch(bot.querySelector('[data-tablet-sheet-action="production-hold"]'), 'click');
  assert.strictEqual(calls.replaceState.pop(), `/erp/production/home?tab=steps&order=${want.first}`);
  assert.strictEqual(calls.reason.length, 1);
  calls.reason[0].onSubmit('', '자재 기다림');
  await flush(); await flush();
  assert.deepStrictEqual(calls.fetch.pop(), { url: `/api/orders/${want.first}/production/hold`, method: 'POST', body: { active: true, reason: '자재 기다림' } });
  // [보류 해제] → 확인 → 보류 API {active:false}
  dispatch(pane(want.hold).querySelector('[data-tablet-sheet-action="production-hold"]'), 'click');
  assert.strictEqual(calls.confirm.length, 1);
  await flush(); await flush();
  assert.deepStrictEqual(calls.fetch.pop(), { url: `/api/orders/${want.hold}/production/hold`, method: 'POST', body: { active: false, reason: '' } });
  // 8) 쓰기 길은 셋뿐(공정 · 불량 · 보류)
  console.log('OK');
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
