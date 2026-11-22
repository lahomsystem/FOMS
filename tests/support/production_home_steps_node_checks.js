// '내 공정' 탭 오른쪽 판 — 서버가 그린 진짜 조각(HTML 파일 경로 = argv[2]) 위에서 세 JS 를 Node 로 돌린다.
// tests/domains/test_production_home_step_panel.py 가 부른다(설계서 2026-11-21-production-my-steps-panel §3-5 · §6).
// 1) foms-production-home-steps.js + steppane.js: 줄 누름 = 고른 표시 즉시 · 판 하나 받기(view=panel 한 번, 받은 판은 남김 — 다시 누르면 0)
//    · 주소 replaceState order= · 공정 탭 = 그 탭 고른 줄 주소 ·
//    [<공정> 끝] = 바로 POST /api/orders/<id>/production/steps {key, done:true} 한 번(두 번 눌러도) → 다음 손님 주소 · 새 화면 [끝] 600ms 잠금 ·
//    [되돌리기] = {done:false} 한 번 → 그 주문 주소 · 저장 · 되돌리기 실패 글 ·
//    그림 = 전역 원본 뷰어(그림 원본 전부).
// 2) foms-production-sheet-page.js: 판 [불량] → 칩 → POST …/production/defect {reason}.
// 3) tablet-domain-sheets.js: 판 [보류] → 사유 창 → POST …/production/hold {active:true, reason}, [보류 해제] → 확인 → {active:false}.
// 가짜 DOM = production_fake_dom.js(태그 · .class · #id · [attr] 묶음 + 쉼표 목록만 — 세 파일이 그것만 쓴다).
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8');
const html = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]); // {first, hold, next, key, label, me, pin, other_tab, other_url, panels: {id: 조각 파일}}
const D = fakeDom();
const { dispatch, docListeners, focused } = D;
// ── 문서 · 창 ──
const body = D.parse(html);
const calls = { fetch: [], replaceState: [], replace: [], assign: [], viewer: [], reason: [], confirm: [] };
let fetchReply = () => ({ success: true, data: {} });
const store = {};
const location = {
  href: 'http://127.0.0.1/erp/production/home?tab=steps', origin: 'http://127.0.0.1', pathname: '/erp/production/home', search: '?tab=steps',
  replace(u) { calls.replace.push(u); }, assign(u) { calls.assign.push(u); }, reload() { calls.replace.push('reload'); },
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
  document, location,
  history: { state: null, replaceState(s, t, u) { calls.replaceState.push(u); } },
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } },
  navigator: { onLine: true },
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  CustomEvent: function CustomEvent(t, o) { this.type = t; this.detail = (o || {}).detail; },
  fetch: (url, opts) => {
    calls.fetch.push({ url, method: (opts || {}).method, body: (opts || {}).body ? JSON.parse(opts.body) : null });
    const u = new URL(url, location.href);
    if (u.searchParams.get('view') === 'panel') { // 판 하나 조각 = 서버가 그린 진짜 조각 파일
      const id = u.searchParams.get('order');
      const text = fs.readFileSync(want.panels[id], 'utf8');
      return Promise.resolve({ ok: true, status: 200, headers: { get: (h) => (h === 'X-FOMS-HOME-PANEL' ? id : null) }, text: () => Promise.resolve(text) });
    }
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
for (const rel of ['static/js/production/foms-production-home-steppane.js', 'static/js/production/foms-production-home-steps.js',
  'static/js/production/foms-production-sheet-page.js',
  'static/js/foms/tablet-domain-sheets.js']) {
  vm.runInContext(read(rel), ctx, { filename: rel });
}
const flush = () => new Promise((r) => setImmediate(r));
const $ = (s) => body.querySelector(s);
const pane = (id) => $(`[data-foms-step-pane="${id}"]`);

(async () => {
  // 0) order= 로 고른 탭은 마지막 탭 기억보다 앞(home.js 가 읽기 전에 기억을 맞춘다)
  if (want.pin) assert.strictEqual(store['foms-prod-step-tab'], want.pin, 'pin → 기억');
  // 1) 줄 누름 = 고른 표시 즉시 · 고른 줄 판만 서버가 그렸다 → 판 하나 받아 끼움 · 주소 · [다시 받기]
  assert.ok(!pane(want.first).hidden && pane(want.hold) === null, '처음엔 고른 줄 판만 있다');
  const link = $(`[data-foms-home-qrow="${want.hold}"]`).querySelector('[data-foms-step-sheet]');
  const ev = dispatch(link, 'click');
  assert.ok(ev.defaultPrevented, '줄 링크 누름은 이동하지 않는다');
  assert.ok($(`[data-foms-home-qrow="${want.hold}"]`).classList.contains('is-on') && !$(`[data-foms-home-qrow="${want.first}"]`).classList.contains('is-on'));
  assert.ok(pane(want.first).hidden && !$('[data-foms-step-wait]').hidden, '받는 동안 옛 판은 숨기고 받는 중');
  await flush(); await flush(); await flush();
  assert.ok(pane(want.hold) && !pane(want.hold).hidden && $('[data-foms-step-wait]').hidden, '받은 판이 보인다');
  const got = new URL(calls.fetch.pop().url, location.href);
  assert.deepStrictEqual([got.searchParams.get('view'), got.searchParams.get('step'), got.searchParams.get('order'), got.searchParams.get('tab')],
    ['panel', want.key, String(want.hold), 'steps']);
  dispatch($(`[data-foms-home-qrow="${want.first}"]`).querySelector('.fph-qr__n'), 'click');
  dispatch(link, 'click'); // 받은 판은 남는다 — 다시 누르면 요청 0
  assert.strictEqual(calls.fetch.length, 0, '받은 판 다시 누름 요청 0');
  assert.ok(pane(want.first).hidden && !pane(want.hold).hidden);
  assert.strictEqual(calls.replaceState.pop(), `/erp/production/home?tab=steps&order=${want.hold}`);
  assert.strictEqual($('[data-foms-home-reload]').getAttribute('href'), `/erp/production/home?tab=steps&order=${want.hold}`);
  // 보류 줄 판엔 [끝] 이 없다
  assert.strictEqual(pane(want.hold).querySelector('[data-foms-step-finish]'), null);
  // 2) 공정 탭 = 그 탭의 고른 줄 주소
  dispatch($(`[data-foms-home-steptab="${want.other_tab}"]`), 'click');
  assert.strictEqual(calls.replaceState.pop(), want.other_url, '공정 탭 주소');
  dispatch($(`[data-foms-home-qrow="${want.first}"]`).querySelector('.fph-qr__n'), 'click');
  assert.ok(!pane(want.first).hidden);
  // 3) [끝] = 확인 창 없이 바로 공정 API 한 번(두 번 눌러도 한 번, 2026-11-22 "확인 창 빼기") → 다음 손님 주소 · [되돌리기] 띠
  assert.strictEqual($('[data-foms-step-modal]'), null, '확인 창은 없다');
  fetchReply = () => ({ success: true, data: { steps: [], complete_ready: false } });
  const fin = pane(want.first).querySelector('[data-foms-step-finish]');
  dispatch(fin, 'click');
  assert.ok(fin.getAttribute('aria-disabled') === 'true' && fin.classList.contains('is-wait'), '첫 누름부터 답이 올 때까지 잠근다');
  dispatch(fin, 'click');
  await flush(); await flush();
  const stepCall = (done) => ({ url: `/api/orders/${want.first}/production/steps`, method: 'POST', body: { key: want.key, done } });
  assert.deepStrictEqual(calls.fetch, [stepCall(true)]);
  assert.deepStrictEqual(calls.replace, [`http://127.0.0.1/erp/production/home?tab=steps&order=${want.next}`]);
  const status = $('[data-foms-home-status]');
  assert.ok(status.classList.contains('is-undo') && status.querySelector('span').textContent === `${want.first_name} ${want.label} 끝`, status.textContent);
  assert.strictEqual(status.querySelector('[data-foms-step-undo]').textContent, '되돌리기');
  // 4) 새 화면(셸 교체로 이 JS 가 다시 돈다): 되돌리기 띠를 다시 그리고 [끝]은 잠깐(600ms) 잠근다 — 두 번 누름이 다음 주문에 떨어지지 않게
  calls.fetch.length = 0;
  const homeRoot = $('[data-foms-prod-home]');
  homeRoot.removeAttribute('data-foms-home-steps-bound');
  status.textContent = '';
  status.classList.remove('is-undo');
  vm.runInContext(read('static/js/production/foms-production-home-steps.js'), ctx);
  assert.ok(status.classList.contains('is-undo') && status.querySelector('[data-foms-step-undo]'), '새 화면에도 되돌리기');
  const locked = () => fin.getAttribute('aria-disabled') === 'true' && fin.classList.contains('is-wait');
  assert.ok(locked() && !fin.disabled, '새 화면 [끝] 잠금(진짜 disabled 아님 — 누름을 받아 연장한다)');
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  dispatch(fin, 'click'); // 연타: 잠금 동안 누르면 600ms 를 다시 센다
  await sleep(400);
  dispatch(fin, 'click');
  await sleep(400);
  assert.ok(locked(), '연타하는 동안은 계속 잠금');
  assert.strictEqual(calls.fetch.length, 0, '잠금 동안 [끝] 누름은 버린다');
  await sleep(350);
  assert.ok(!locked(), '손을 떼고 600ms 뒤 풀린다');
  // 5) [되돌리기] = 같은 공정 API {done:false} 한 번(두 번 눌러도) → 그 주문 줄로 다시 받기
  calls.replace.length = 0;
  dispatch(status.querySelector('[data-foms-step-undo]'), 'click');
  dispatch(status.querySelector('[data-foms-step-undo]'), 'click');
  await flush(); await flush();
  assert.deepStrictEqual(calls.fetch, [stepCall(false)]);
  assert.deepStrictEqual(calls.replace, [`http://127.0.0.1/erp/production/home?tab=steps&order=${want.first}`]);
  assert.ok(status.textContent.startsWith('되돌렸어요') && !status.classList.contains('is-undo'), status.textContent);
  // 6) 실패: 저장 실패 = 판 글 · 단추 풀림 · 이동 0. 되돌리기 실패 = 띠가 붉게 + 글, 단추는 남는다
  calls.fetch.length = 0;
  calls.replace.length = 0;
  ctx.fetch = (url, opts) => { calls.fetch.push({ url, method: opts.method, body: JSON.parse(opts.body) }); return Promise.reject(new Error('offline')); };
  dispatch(fin, 'click');
  await flush(); await flush();
  assert.strictEqual(pane(want.first).querySelector('[data-foms-sheet-status]').textContent, '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.');
  assert.ok(!fin.hasAttribute('aria-disabled') && calls.replace.length === 0 && !status.classList.contains('is-undo'));
  const G = ctx.__FOMS_PROD_STEPS_BOUND;
  G.undo = { id: String(want.first), key: want.key, name: want.first_name, label: want.label, until: Date.now() + 8000, busy: false, error: '' };
  G.api.showUndo();
  dispatch(status.querySelector('[data-foms-step-undo]'), 'click');
  await flush(); await flush();
  assert.ok(status.classList.contains('is-err') && status.textContent.includes('되돌리지 못했어요') && status.querySelector('[data-foms-step-undo]'), status.textContent);
  assert.strictEqual(calls.replace.length, 0);
  G.undo = null;
  // 5) 그림 = 원본 뷰어(그림 원본 전부)
  dispatch(pane(want.first).querySelector('[data-foms-step-view]'), 'click');
  assert.ok(calls.viewer.length >= 1); // 4) 에서 셸 교체를 같은 루트로 흉내 내 두 번 묶였다(실제는 새 루트) — 열림만 본다
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
  process.exit(0); // 되돌리기 · 잠금 타이머를 기다리지 않는다
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
