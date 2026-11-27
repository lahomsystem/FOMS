// 작업 시트 · 생산 첫 화면 생산 단추의 앱 확인 창(사장님 2026-11-27 "앱 창으로 바꾸기") — 서버가 그린 진짜 화면(argv[2]) 위에서 Node 로.
// tests/domains/test_production_sheet_app_confirm_1127.py 가 부른다. want = argv[3] {scripts, cohort, app: [...], plain: [...]}.
// · app(앱 창 길 — 단추 하나마다): 누르면 기본 창 0 · 앱 창(제목 · 본문 · [닫기] · [한 일 이름]) → 연 바로 뒤 창 단추 · 같은 단추 다시 = 버림 →
//   [닫기] · Esc · 바깥 = POST 0 → [한 일 이름] = 같은 주소 · 같은 몸통 POST 한 번(두 번 눌러도 · 저장 중 단추를 또 눌러도 한 번) → 다시 읽기.
//   hold 가 있으면 첫 응답이 409 HOLD_ACTIVE — 같은 창에 "보류를 해제하고 진행할까요?" → [보류 해제하고 진행] = 같은 몸통 + release_hold.
// · plain(기본 창 길): 누르면 window.confirm 한 번(지금 글 그대로) · 앱 창은 그대로 숨김 · POST 한 번.
// 가짜 DOM = production_fake_dom.js.
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const want = JSON.parse(process.argv[3]);
const D = fakeDom();
const body = D.parse(fs.readFileSync(process.argv[2], 'utf8'));
const calls = { fetch: [], confirm: [], alert: [], reload: 0 };
let reply = null; // 다음 fetch 응답을 손으로 푼다(저장 중 누름 시험)
const ctx = {
  console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout,
  location: { href: 'http://127.0.0.1/erp/production', origin: 'http://127.0.0.1', pathname: '/erp/production', search: '', replace() {}, assign() {},
    reload() { calls.reload += 1; } },
  navigator: { onLine: true },
  document: {
    body, readyState: 'complete', referrer: '',
    querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
    getElementById: (id) => body.querySelector('#' + id), createElement: (t) => D.makeEl(t.toLowerCase()),
    addEventListener(t, f) { (D.docListeners[t] = D.docListeners[t] || []).push(f); },
    removeEventListener() {}, contains: (n) => body.contains(n), dispatchEvent() { return true; },
  },
  history: { state: null, replaceState() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: !!want.cohort, addEventListener() {}, addListener() {} }),
  getComputedStyle: () => ({ getPropertyValue: () => (want.cohort ? 'ready' : '') }),
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  confirm: (msg) => { calls.confirm.push(msg); return true; },
  alert: (msg) => { calls.alert.push(msg); },
  fetch: (url, opts) => {
    calls.fetch.push({ url, method: opts && opts.method, body: opts && opts.body ? JSON.parse(opts.body) : null });
    return new Promise((resolve) => { reply = resolve; });
  },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const rel of want.scripts) { vm.runInContext(fs.readFileSync(path.join(root, rel), 'utf8'), ctx, { filename: rel }); }

const flush = () => new Promise((r) => setImmediate(r));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => body.querySelector(s);
const box = $('[data-foms-sheet-confirm]');
const posts = () => calls.fetch.filter((c) => c.method === 'POST');
const answer = async (status, data) => {
  const r = reply; reply = null;
  r({ ok: status === 200, status, json: () => Promise.resolve(data) });
  for (let i = 0; i < 6; i += 1) { await flush(); }
};
const click = (el) => D.dispatch(el, 'click');
function shows(title, text, yes) {
  assert.ok(box && !box.hidden, '앱 창이 뜬다: ' + title);
  assert.strictEqual(box.getAttribute('aria-hidden'), 'false');
  assert.strictEqual(box.querySelector('[data-foms-sheet-confirm-title]').textContent, title);
  const p = box.querySelector('[data-foms-sheet-confirm-body]');
  assert.strictEqual(p.textContent, text || '');
  assert.strictEqual(p.hidden, !text, '본문이 없으면 숨김');
  assert.strictEqual(box.querySelector('[data-foms-sheet-confirm-no].foms-btn').textContent, '닫기');
  assert.strictEqual(box.querySelector('[data-foms-sheet-confirm-yes]').textContent, yes);
}

async function appFlow(f) {
  const btn = $(f.sel);
  assert.ok(btn, f.sel);
  const yes = box.querySelector('[data-foms-sheet-confirm-yes]');
  const no = box.querySelector('[data-foms-sheet-confirm-no].foms-btn');
  const dim = box.querySelector('.foms-reason-sheet__backdrop');
  const before = posts().length;
  const reload = calls.reload;
  // ① 누르면 앱 창 · 기본 창 0 — 두 번 누름의 둘째(창 단추 · 같은 단추)는 버린다
  click(btn);
  shows(f.title, f.body, f.yes);
  click(yes); click(btn); click(dim);
  assert.ok(!box.hidden, '연 바로 뒤 누름은 버린다');
  assert.strictEqual(posts().length, before);
  await sleep(450);
  // ② [닫기] · Esc · 바깥 = 아무 것도 안 함
  click(no);
  assert.ok(box.hidden && box.getAttribute('aria-hidden') === 'true');
  click(btn); await sleep(450);
  D.dispatch(body, 'keydown', { key: 'Escape' });
  assert.ok(box.hidden, 'Esc 로 닫힌다');
  click(btn); await sleep(450);
  click(dim);
  assert.ok(box.hidden, '바깥으로 닫힌다');
  assert.strictEqual(posts().length, before, '[닫기] · Esc · 바깥 = POST 0');
  // ③ [한 일 이름] = POST 한 번 — 창 단추 두 번 · 저장 중 같은 단추 = 한 번
  click(btn); shows(f.title, f.body, f.yes); await sleep(450);
  click(yes); click(yes);
  await flush();
  click(btn);
  assert.ok(box.hidden, '저장 중 누름은 창을 다시 열지 않는다');
  assert.deepStrictEqual(posts().slice(before), [{ url: f.url, method: 'POST', body: f.post }]);
  if (f.hold) {
    await answer(409, { success: false, code: 'HOLD_ACTIVE', message: '보류 중', hold: { reason: f.hold } });
    shows('보류를 해제하고 진행할까요?', '보류 중인 주문이에요 (사유: ' + f.hold + ')', '보류 해제하고 진행');
    click(yes); assert.ok(!box.hidden); await sleep(450);
    click(yes); click(yes); await flush();
    assert.deepStrictEqual(posts().slice(before + 1), [{ url: f.url, method: 'POST', body: Object.assign({}, f.post, { release_hold: true }) }]);
  }
  await answer(200, { success: true, data: {} });
  assert.strictEqual(calls.reload, reload + 1, '저장되면 다시 읽는다');
  if (!f.keeps_lock) { assert.strictEqual(btn.disabled, false, '응답 뒤 잠금을 푼다'); } // 공장 단추는 성공하면 잠근 채 다시 읽는다(지금 그대로)
  assert.deepStrictEqual([calls.confirm.length, calls.alert.length], [0, 0], '기본 창 0');
}

async function plainFlow(f) {
  const btn = $(f.sel);
  assert.ok(btn, f.sel);
  const before = posts().length;
  const asked = calls.confirm.length;
  click(btn);
  assert.deepStrictEqual(calls.confirm.slice(asked), [f.plain], '지금 기본 창 글 그대로');
  assert.ok(!box || box.hidden, '앱 창은 안 뜬다');
  assert.deepStrictEqual(posts().slice(before), [{ url: f.url, method: 'POST', body: f.post }]);
  await answer(200, { success: true, data: {} });
}

(async () => {
  for (const f of want.app || []) { await appFlow(f); }
  for (const f of want.plain || []) { await plainFlow(f); }
  console.log('OK');
  process.exit(0);
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
