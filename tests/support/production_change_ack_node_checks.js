// [바뀐 것] 탭 [확인했어요] — 성공하면 다시 읽지 않고 그 줄만 지운다(사장님 결정 2026-11-26). 다른 화면 줄은 지금처럼 다시 읽는다.
// tests/domains/test_production_flow_1126_g3.py 가 부른다. 가짜 DOM = production_fake_dom.js.
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const D = fakeDom();
const body = D.parse(`
<div data-foms-prod-home><nav><a class="foms-prod-home__navtab is-on" aria-current="page">바뀐 것 <small class="is-hot">2</small></a></nav>
<div class="fph-inbox fph-inbox--page">
  <h2 class="fph-inbox__h">바뀐 것 <b>2</b></h2>
  <div class="fph-al" data-foms-home-inbox="11"><button data-kanban-action="change-ack" data-order-id="11" id="b11">확인했어요</button></div>
  <div class="fph-al" data-foms-home-inbox="12"><button data-kanban-action="change-ack" data-order-id="12" id="b12">확인했어요</button></div>
  <div class="fph-al is-done" data-foms-home-done="5"></div>
</div></div>
<div data-foms-prod-sheet-page><section class="foms-prod-page__box"><button data-kanban-action="change-ack" data-order-id="99" id="bsheet">확인했어요</button></section></div>
`);
const calls = { fetch: [], reload: 0, alert: [] };
const document = {
  body, readyState: 'complete', referrer: '',
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  getElementById: (id) => body.querySelector('#' + id), createElement: (t) => D.makeEl(t.toLowerCase()),
  addEventListener(t, f) { (D.docListeners[t] = D.docListeners[t] || []).push(f); }, removeEventListener() {}, contains: (n) => body.contains(n),
};
const ctx = {
  console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout,
  document, location: { href: 'http://127.0.0.1/erp/production/home?tab=changes', origin: 'http://127.0.0.1', pathname: '/erp/production/home', search: '?tab=changes', reload() { calls.reload += 1; } },
  history: { state: null, replaceState() {} }, localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, navigator: { onLine: true },
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }), getComputedStyle: () => ({ getPropertyValue: () => '' }),
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  fetch: (url, opts) => { calls.fetch.push({ url, method: opts.method }); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true }) }); },
  confirm: () => true, alert: (m) => { calls.alert.push(m); },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, 'static/js/foms/tablet-domain-sheets.js'), 'utf8'), ctx);
const flush = () => new Promise((r) => setImmediate(r));
const $ = (s) => body.querySelector(s);

(async () => {
  // 1) 첫 줄: 줄만 사라지고 숫자 2 → 1, 다시 읽기 없음
  D.dispatch($('#b11'), 'click'); await flush(); await flush();
  assert.deepStrictEqual(calls.fetch, [{ url: '/api/orders/11/production/change-ack', method: 'POST' }]);
  assert.strictEqual(calls.reload, 0, '다시 읽지 않는다');
  assert.strictEqual($('[data-foms-home-inbox="11"]'), null);
  assert.ok($('[data-foms-home-inbox="12"]'));
  assert.strictEqual($('.fph-inbox__h').querySelector('b').textContent, '1');
  assert.strictEqual($('.foms-prod-home__navtab').querySelector('small').textContent, '1');
  assert.ok($('.foms-prod-home__navtab').querySelector('small').classList.contains('is-hot'));
  assert.strictEqual($('.foms-prod-home__empty'), null);
  // 2) 마지막 줄: 숫자 0 · is-hot 빠짐 · 서버가 그리는 빈 글 · 확인한 것 줄은 남음
  D.dispatch($('#b12'), 'click'); await flush(); await flush();
  assert.strictEqual(calls.reload, 0);
  assert.strictEqual($('.fph-inbox__h').querySelector('b').textContent, '0');
  assert.ok($('.fph-inbox__h').querySelector('b').classList.contains('is-zero'));
  assert.strictEqual($('.foms-prod-home__navtab').querySelector('small').textContent, '0');
  assert.ok(!$('.foms-prod-home__navtab').querySelector('small').classList.contains('is-hot'));
  assert.strictEqual($('.foms-prod-home__empty').textContent, '새로 바뀐 것이 없어요.');
  assert.ok($('[data-foms-home-done="5"]'));
  // 3) 다른 화면(작업 시트 상자)의 같은 단추는 지금처럼 다시 읽는다
  D.dispatch($('#bsheet'), 'click'); await flush(); await flush();
  assert.strictEqual(calls.reload, 1, '다른 화면은 다시 읽는다');
  assert.deepStrictEqual(calls.alert, []);
  console.log('OK');
})().catch((e) => { console.error(e); process.exit(1); });
