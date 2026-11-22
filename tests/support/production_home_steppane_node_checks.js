// '내 공정' 판 하나 받기(foms-production-home-steppane.js, 2026-11-22) — 서버가 그린 진짜 조각(argv[2]) 위에서 Node 로.
// tests/domains/test_production_home_step_panel_wiring.py 가 부른다. 가짜 fetch 는 요청마다 약속을 쥐고 시험이 순서를 정한다.
// 1) 빠르게 두 줄(B → D): 앞 요청은 끊기고(abort) 늦게 온 B 응답은 버린다 — D 만 보인다(마지막 누름).
// 2) 받는 중 같은 줄을 또 눌러도 요청 하나. 3) 연결 실패 = 판 자리에 글 + [다시 해 보기] → 누르면 다시 받아 보인다.
// 4) 404(그 사이 다른 공정으로 옮겨 감) = 글 + [다시 받기] → 누르면 화면을 다시 받는다. 5) 머리글이 다른 판이면 실패로 본다.
// 6) 끼운 판의 [불량] 칩은 작업 시트 JS 가 묶는다(누르면 열린다).
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const want = JSON.parse(process.argv[3]); // {b, d, key, panels: {id: 조각 파일}}
const D = fakeDom();
const body = D.parse(fs.readFileSync(process.argv[2], 'utf8'));
const pending = [];
const calls = { replace: [] };
const location = {
  href: 'http://127.0.0.1/erp/production/home?tab=steps', origin: 'http://127.0.0.1', pathname: '/erp/production/home', search: '?tab=steps',
  replace(u) { calls.replace.push(u); }, assign() {}, reload() {},
};
const ctx = {
  console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout, AbortController,
  location,
  document: {
    body, readyState: 'complete', referrer: '',
    querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
    createElement: (t) => D.makeEl(t.toLowerCase()),
    addEventListener(t, f) { (D.docListeners[t] = D.docListeners[t] || []).push(f); },
    removeEventListener() {}, contains: (n) => body.contains(n), dispatchEvent() { return true; },
  },
  history: { state: null, replaceState() {} },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: { onLine: true },
  fetch: (url, opts) => new Promise((resolve, reject) => {
    const u = new URL(url, location.href);
    pending.push({ id: u.searchParams.get('order'), step: u.searchParams.get('step'), signal: opts.signal, resolve, reject });
  }),
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const rel of ['static/js/production/foms-production-home-steppane.js', 'static/js/production/foms-production-home-steps.js',
  'static/js/production/foms-production-sheet-page.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, rel), 'utf8'), ctx, { filename: rel });
}
const flush = async () => { for (let i = 0; i < 4; i += 1) { await new Promise((r) => setImmediate(r)); } };
const $ = (s) => body.querySelector(s);
const pane = (id) => $(`[data-foms-step-pane="${id}"]`);
const row = (id) => $(`[data-foms-home-qrow="${id}"]`);
const wait = () => cutQ().querySelector('[data-foms-step-wait]');
const tapRow = (id) => D.dispatch(row(id).querySelector('[data-foms-step-sheet]'), 'click');
const ok = (id, headerId) => ({ ok: true, status: 200, headers: { get: (h) => (h === 'X-FOMS-HOME-PANEL' ? String(headerId || id) : null) },
  text: () => Promise.resolve(fs.readFileSync(want.panels[id], 'utf8')) });
const cutQ = () => $(`[data-foms-home-stepq="${want.key}"]`);
const visible = () => cutQ().querySelectorAll('[data-foms-step-pane]').filter((p) => !p.hidden).map((p) => p.getAttribute('data-foms-step-pane'));

(async () => {
  const first = visible();
  assert.strictEqual(first.length, 1, '처음엔 고른 줄 판 하나만 보인다');
  // 1) B → D 빠르게: B 요청은 끊기고 늦게 온 B 응답은 버린다
  tapRow(want.b);
  tapRow(want.b); // 2) 받는 중 같은 줄 또 누름 = 요청 하나
  assert.strictEqual(pending.length, 1, '같은 줄 두 번 = 요청 하나');
  assert.deepStrictEqual(visible(), [], '받는 동안 옛 판은 숨긴다');
  assert.ok(!wait().hidden && wait().textContent.includes('받는 중'));
  tapRow(want.d);
  assert.strictEqual(pending.length, 2);
  assert.ok(pending[0].signal.aborted, '앞 요청은 끊는다');
  pending[1].resolve(ok(want.d));
  await flush();
  pending[0].resolve(ok(want.b)); // 늦게 온 앞 응답
  await flush();
  assert.deepStrictEqual(visible(), [String(want.d)], '마지막 누름(D)만 보인다');
  assert.strictEqual(pane(want.b), null, '버린 응답은 끼우지 않는다');
  assert.ok(wait().hidden && row(want.d).classList.contains('is-on'));
  // 3) 연결 실패 → 글 + [다시 해 보기] → 다시 받아 보인다
  pending.length = 0;
  tapRow(want.b);
  pending[0].reject(new TypeError('Failed to fetch'));
  await flush();
  assert.deepStrictEqual(visible(), [], '못 받으면 다른 주문 판을 보이지 않는다');
  const retry = wait().querySelector('[data-foms-step-retry]');
  assert.ok(!wait().hidden && wait().classList.contains('is-bad') && !retry.hidden);
  assert.ok(wait().textContent.includes('연결이 끊겼어요') && retry.textContent === '다시 해 보기', wait().textContent);
  D.dispatch(retry, 'click');
  assert.strictEqual(pending.length, 2, '[다시 해 보기] = 다시 받기');
  pending[1].resolve(ok(want.b));
  await flush();
  assert.deepStrictEqual(visible(), [String(want.b)]);
  assert.ok(wait().hidden && !wait().classList.contains('is-bad'));
  // 6) 끼운 판의 [불량] 칩은 작업 시트 JS 가 묶었다
  const bot = pane(want.b).querySelector('[data-foms-prod-sheet-page]');
  assert.strictEqual(bot.getAttribute('data-foms-sheet-init'), '1', '끼운 판 루트를 묶는다');
  D.dispatch(bot.querySelector('[data-foms-sheet-defect-toggle]'), 'click');
  assert.ok(!bot.querySelector('[data-foms-sheet-defect-reasons]').hidden, '[불량] 칩이 열린다');
  // 5) 머리글이 다른 판 = 실패
  const extra = want.extra;
  pending.length = 0;
  tapRow(extra);
  pending[0].resolve(ok(extra, 1));
  await flush();
  assert.ok(!wait().hidden && wait().classList.contains('is-bad') && pane(extra) === null, '다른 판 머리글은 끼우지 않는다');
  // 4) 404 → '다시 받기' → 화면을 다시 받는다(셸 없음 = location.replace)
  pending.length = 0;
  D.dispatch(wait().querySelector('[data-foms-step-retry]'), 'click');
  pending[0].resolve({ ok: false, status: 404, headers: { get: () => null }, text: () => Promise.resolve('') });
  await flush();
  assert.ok(wait().textContent.includes('다른 공정으로 옮겨졌어요') && wait().querySelector('[data-foms-step-retry]').textContent === '다시 받기');
  D.dispatch(wait().querySelector('[data-foms-step-retry]'), 'click');
  assert.strictEqual(calls.replace.length, 1);
  assert.ok(calls.replace[0].endsWith(`?tab=steps&order=${extra}`), calls.replace[0]);
  console.log('OK');
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
