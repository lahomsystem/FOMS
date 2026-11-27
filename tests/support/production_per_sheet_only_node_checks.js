// 작업 시트 공정 칸 — 도면 여러 장 주문은 통째 켜기 대신 칸 아래 까닭(사장님 2026-11-27 "도면 두 장 이상이면 막기").
// 서버가 그린 진짜 작업 시트(argv[2]) 위에서 시트 JS(foms-production-sheet-parts.js + foms-production-sheet-page.js)를 Node 로.
// tests/domains/test_production_per_sheet_only_1127.py 가 부른다. want = argv[3] {key, mode, msg, text}.
// · mode=many: 꺼진 칸 누름 = POST 0 · 확인 창 0 · 칸 아래 글(.fpp-stepmsg) = 서버 글(msg) 그대로 · 칸은 꺼진 채.
// · mode=off: 켜진 칸 누름(끄기) = 확인 창 없이 POST 한 번 {key, done:false}(지금 그대로).
// · mode=one: 꺼진 칸 누름 = 확인 창(본문 text) · POST 0 → [<공정> 완료] = POST 한 번 {key, done:true}(지금 그대로).
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
const calls = { fetch: [], confirm: [] };
const ctx = {
  console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout,
  location: { href: 'http://127.0.0.1/erp/production/sheet/1', origin: 'http://127.0.0.1', pathname: '/erp/production/sheet/1', search: '',
    replace() {}, assign() {}, reload() {} },
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
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  confirm: (msg) => { calls.confirm.push(msg); return true; },
  alert() {},
  fetch: (url, opts) => {
    calls.fetch.push({ url, method: (opts && opts.method) || 'GET', body: opts && opts.body ? JSON.parse(opts.body) : null });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: {} }) });
  },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const rel of ['static/js/production/foms-production-sheet-parts.js', 'static/js/production/foms-production-sheet-page.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, rel), 'utf8'), ctx, { filename: rel });
}
const flush = async () => { for (let i = 0; i < 6; i += 1) { await new Promise((r) => setImmediate(r)); } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => body.querySelector(s);
const posts = () => calls.fetch.filter((c) => c.method === 'POST');
const cell = $(`[data-foms-sheet-step="${want.key}"]`);
const box = $('[data-foms-sheet-confirm]');
const msg = $('[data-foms-sheet-stepmsg]');
const page = $('[data-foms-prod-sheet-page]');
page.dispatchEvent = () => true; // 가짜 DOM 에 없는 것 — 공정 응답 뒤 공장 단추 알림(sheet-parts render)

(async () => {
  assert.ok(cell && box && msg, '칸 · 확인 창 · 칸 아래 글 자리');
  D.dispatch(cell.querySelector('span'), 'click');
  await flush();
  if (want.mode === 'many') {
    assert.strictEqual(calls.fetch.length, 0, '요청 0(자료는 화면에 실려 있다)');
    assert.ok(box.hidden, '확인 창 없음');
    assert.strictEqual(msg.textContent, want.msg);
    assert.strictEqual(msg.hidden, false);
    assert.strictEqual(cell.getAttribute('aria-pressed'), 'false', '칸은 꺼진 채');
    assert.strictEqual(cell.disabled, false, '다시 누를 수 있다');
    D.dispatch(cell, 'click'); // 다시 눌러도 같다
    await flush();
    assert.strictEqual(calls.fetch.length, 0);
  } else if (want.mode === 'off') {
    assert.ok(box.hidden, '끄기는 묻지 않는다');
    assert.deepStrictEqual(posts().map((c) => c.body), [{ key: want.key, done: false }]);
  } else {
    assert.strictEqual(box.hidden, false, '도면 1장 = 지금 확인 창');
    assert.strictEqual(box.querySelector('[data-foms-sheet-confirm-body]').textContent, want.text);
    assert.strictEqual(posts().length, 0);
    assert.ok(msg.hidden, '칸 아래 글 없음');
    await sleep(450); // 연 뒤 0.4초 안 누름은 버린다(OPEN_GUARD_MS)
    D.dispatch(box.querySelector('[data-foms-sheet-confirm-yes]'), 'click');
    await flush();
    assert.deepStrictEqual(posts().map((c) => c.body), [{ key: want.key, done: true }]);
  }
  console.log('OK');
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
