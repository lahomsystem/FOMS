// '내 공정' [<공정> 끝] — 사장님 2026-11-25 "도면이 있는 주문만 한 번 묻기" → 2026-11-27 "도면이 주, 작업 시트는 보기": 도면 있는 줄은
// [끝] 자리가 막힘 칸 링크("재단 0/1 · 1장 미완료", 누르면 그 주문 도면 판)라 누를 단추도 물을 창도 없다. 도면 없는 줄만 지금처럼 바로 저장.
// 서버가 그린 진짜 조각(argv[2]) 위에서 JS 를 Node 로 돌린다. tests/domains/test_production_my_steps_confirm.py 가 부른다.
// want = argv[3] {mode, first, sheets, key, bare, cards, done_status}. done_status 가 있으면 저장 뒤 상태 줄 글도 그린 값으로 잰다.
// · panel(태블릿 가로 판 — foms-production-home-steps.js): sheets > 0 = 판에 [끝] 없음 · 막힘 칸 링크(cards 글) · 창 숨김 · 요청 0.
//   sheets 0 = 창 없이 바로 POST(지금 그대로) · 받기(GET) 0.
// · row(폰 · 세로 · PC 줄 [끝] — foms-production-home.js): 도면 있는 줄(first) = [끝] 없음 · 막힘 칸 링크, 도면 없는 줄(bare) = 창 없이 바로 POST.
// 가짜 DOM = production_fake_dom.js.
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]);
const D = fakeDom();
const { dispatch, docListeners, focused } = D;
const body = D.parse(html);
const calls = { fetch: [], replace: [], reload: 0 };
const store = {};
const location = {
  href: 'http://127.0.0.1/erp/production/home?tab=steps', origin: 'http://127.0.0.1', pathname: '/erp/production/home', search: '?tab=steps',
  replace(u) { calls.replace.push(u); }, assign(u) { calls.replace.push(u); }, reload() { calls.reload += 1; },
};
const document = {
  body, readyState: 'complete', referrer: '',
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  getElementById: (id) => body.querySelector('#' + id),
  createElement: (t) => D.makeEl(t.toLowerCase()),
  addEventListener(t, f) { (docListeners[t] = docListeners[t] || []).push(f); },
  removeEventListener() {},
  contains: (n) => body.contains(n),
  dispatchEvent() { return true; },
};
const ctx = {
  console, URL, JSON, Promise, AbortController, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout,
  setInterval: () => 0, clearInterval() {}, document, location,
  history: { state: null, replaceState() {} },
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
  navigator: { onLine: true },
  performance: { timeOrigin: Date.now() },
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  fetch: (url, opts) => {
    calls.fetch.push({ url, method: (opts || {}).method || 'GET', body: (opts || {}).body ? JSON.parse(opts.body) : null });
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { steps: [], complete_ready: false } }) });
  },
  ERPUtils: { safeJsonParse: (v, fb) => { try { return JSON.parse(v); } catch (e) { return fb; } } },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
const homeRoot = body.querySelector('[data-foms-prod-home]');
homeRoot.style = { setProperty() {} }; // foms-production-home.js 제목 줄 높이(가짜 DOM 에 style 이 없다)
const HOME_JS = 'static/js/production/foms-production-home.js';
const STEPS_JS = 'static/js/production/foms-production-home-steps.js';
const PARTS_JS = 'static/js/production/foms-production-sheet-parts.js';
const run = (rel) => vm.runInContext(read(rel), ctx, { filename: rel });
const scripts = want.mode === 'panel' ? ['static/js/production/foms-production-home-steppane.js', STEPS_JS, HOME_JS, PARTS_JS] : [HOME_JS, PARTS_JS];
scripts.forEach(run);

const flush = () => new Promise((r) => setImmediate(r));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => body.querySelector(s);
const box = $('[data-foms-sheet-confirm]');
const posts = () => calls.fetch.filter((c) => c.method === 'POST');
const gets = () => calls.fetch.filter((c) => c.method === 'GET');
const stepCall = (id) => ({ url: `/api/orders/${id}/production/steps`, method: 'POST', body: { key: want.key, done: true } });
async function tap(btn) { dispatch(btn, 'click'); await flush(); await flush(); }
(async () => {
  assert.strictEqual(body.querySelectorAll('[data-foms-sheet-confirm]').length <= 1, true, '창은 화면에 하나 이하');
  assert.ok(!box || box.hidden, '처음엔 숨김');
  if (want.mode === 'panel') {
    const pane = $(`[data-foms-step-pane="${want.first}"]`);
    const fin = () => pane.querySelector('[data-foms-step-finish]');
    if (want.sheets) { // 도면 있는 줄 = [끝] 없음 · 막힘 칸 링크
      assert.ok(!fin(), '도면 있는 줄에 [끝] 없음');
      const link = pane.querySelector('[data-foms-step-cards]');
      assert.ok(link && link.querySelector('b').textContent === want.cards, link && link.textContent);
      assert.ok((!box || box.hidden) && calls.fetch.length === 0);
      console.log('OK');
      process.exit(0);
    }
    assert.ok(!fin().hasAttribute('data-foms-sheet-parts'));
    await tap(fin());
    assert.ok(!box || box.hidden, '도면 없는 줄은 묻지 않는다');
    assert.deepStrictEqual(posts(), [stepCall(want.first)]);
    assert.strictEqual(gets().length, 0);
    if (want.done_status) { // 저장 뒤 상태 줄 글(그린 값) — "{고객} 재단 완료"(K4 · 지휘 판결)
      const span = $('[data-foms-home-status]').querySelector('span');
      assert.strictEqual(span && span.textContent, want.done_status, $('[data-foms-home-status]').textContent);
    }
  } else {
    const btnOf = (id) => $(`[data-foms-home-step-done][data-order-id="${id}"]`);
    const row = $(`[data-foms-home-qrow="${want.first}"]`);
    assert.ok(!btnOf(want.first), '도면 있는 줄에 [끝] 없음');
    assert.strictEqual(row.querySelector('[data-foms-step-cards]').textContent, want.cards);
    assert.ok(!btnOf(want.bare).hasAttribute('data-foms-sheet-parts'));
    await tap(btnOf(want.bare));
    assert.ok(!box || box.hidden, '도면 없는 줄은 묻지 않는다');
    assert.deepStrictEqual(posts(), [stepCall(want.bare)]);
    assert.strictEqual(gets().length, 0);
    if (want.done_status) { // 저장 뒤 상태 줄 글(그린 값) — 문장 속 움직임 말 "끝냈어요"는 그대로(§8-3 끝)
      assert.strictEqual($('[data-foms-home-status]').textContent, want.done_status);
    }
  }
  console.log('OK');
  process.exit(0); // 되돌리기 · 잠금 타이머를 기다리지 않는다
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
