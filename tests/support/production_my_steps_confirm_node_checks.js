// '내 공정' [<공정> 끝] 확인 창 — 사장님 2026-11-25 "도면이 있는 주문만 한 번 묻기". 서버가 그린 진짜 조각(argv[2]) 위에서 JS 를 Node 로 돌린다.
// tests/domains/test_production_my_steps_confirm.py 가 부른다. want = argv[3] {mode, first, sheets, key, title, text, next, bare}.
// · panel(태블릿 가로 판 [끝] — foms-production-home-steps.js): 도면 있는 줄 = 작업 시트와 같은 창 · 같은 글(foms-production-sheet-parts.js),
//   누를 때 받기(GET) 0 · 두 번 누름의 둘째(창 단추 · 바깥 · [끝])는 버림 · [취소] · Esc = POST 0 · [작업 완료] = POST 한 번 → 다음 손님 주소.
//   셸 조각 교체(세 파일이 다시 돎) 뒤에도 창 단추가 먹는다. 창이 떠 있는 사이 판이 바뀌면(누른 단추가 화면에서 빠짐) [작업 완료]여도 POST 0.
//   도면 없는 줄(sheets 0) = 창 없이 바로 POST(지금 그대로).
// · row(폰 · 세로 · PC 줄 [끝] — foms-production-home.js): 도면 있는 줄 = 같은 창 → [취소] POST 0 · [작업 완료] POST 한 번 + 다시 받기,
//   도면 없는 줄 = 창 없이 바로 POST.
// want.done_status 가 있으면 [작업 완료] 뒤 상태 줄 글(판 = "{고객} 재단 완료" · 줄 = "끝냈어요. 다음 공정으로 옮겨요")도 그린 값으로 잰다.
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
const yes = box.querySelector('[data-foms-sheet-confirm-yes]');
const no = box.querySelector('[data-foms-sheet-confirm-no].foms-btn');
const backdrop = box.querySelector('.foms-reason-sheet__backdrop');
const posts = () => calls.fetch.filter((c) => c.method === 'POST');
const gets = () => calls.fetch.filter((c) => c.method === 'GET');
const keydown = (key) => (docListeners.keydown || []).forEach((f) => f({ key, shiftKey: false, preventDefault() {} }));
const stepCall = (id) => ({ url: `/api/orders/${id}/production/steps`, method: 'POST', body: { key: want.key, done: true } });
async function tap(btn) { dispatch(btn, 'click'); await flush(); await flush(); }
function shown(why) {
  assert.ok(!box.hidden && box.getAttribute('aria-hidden') === 'false', why);
  assert.strictEqual(box.querySelector('[data-foms-sheet-confirm-title]').textContent, want.title);
  assert.strictEqual(box.querySelector('[data-foms-sheet-confirm-body]').textContent, want.text);
}
async function cancelFlow(btn) {
  await tap(btn);
  shown('도면 있는 줄은 창부터');
  assert.strictEqual(calls.fetch.length, 0, '창을 열 때 받기(GET) · 쓰기 0 — 자료는 서버가 단추에 실었다');
  dispatch(yes, 'click'); // 두 번 누름의 둘째가 [작업 완료] 자리에 떨어짐
  dispatch(backdrop, 'click'); // · 바깥에 떨어짐
  await tap(btn); // · [끝]에 다시 떨어짐
  assert.ok(!box.hidden && posts().length === 0, '연 뒤 바로 온 누름은 버린다(창 그대로 · POST 0)');
  await sleep(450);
  dispatch(no, 'click');
  assert.ok(box.hidden && posts().length === 0, '[취소] = POST 0');
  assert.strictEqual(focused[focused.length - 1], btn, '닫으면 누른 [끝]으로 초점');
  assert.ok(!btn.disabled && !btn.hasAttribute('aria-disabled'), '[취소] 뒤 [끝]은 그대로 누를 수 있다');
  await tap(btn);
  shown('[취소] 뒤 다시 누르면 다시 묻는다');
  await sleep(450);
  keydown('Escape');
  assert.ok(box.hidden && posts().length === 0, 'Esc = POST 0');
}

(async () => {
  assert.strictEqual(body.querySelectorAll('[data-foms-sheet-confirm]').length, 1, '창은 화면에 하나');
  assert.ok(box.hidden, '처음엔 숨김');
  if (want.mode === 'panel') {
    const fin = () => $(`[data-foms-step-pane="${want.first}"]`).querySelector('[data-foms-step-finish]');
    if (!want.sheets) { // 도면 없는 줄 = 지금처럼 바로
      assert.ok(!fin().hasAttribute('data-foms-sheet-parts'));
      await tap(fin());
      assert.ok(box.hidden, '도면 없는 줄은 묻지 않는다');
      assert.deepStrictEqual(posts(), [stepCall(want.first)]);
      assert.strictEqual(gets().length, 0);
      console.log('OK');
      process.exit(0);
    }
    await cancelFlow(fin());
    // [작업 완료] = 공정 API 한 번 → 다음 손님 주소(지금 [끝] 저장 뒤와 같은 길)
    await tap(fin());
    await sleep(450);
    dispatch(yes, 'click');
    dispatch(yes, 'click'); // 닫힌 창 단추 · 저장 중 누름은 버린다
    await flush(); await flush();
    assert.ok(box.hidden);
    assert.deepStrictEqual(posts(), [stepCall(want.first)], '[작업 완료] = POST 한 번');
    if (want.done_status) { // 저장 뒤 상태 줄 글(그린 값) — "{고객} 재단 완료"(K4 · 지휘 판결)
      const span = $('[data-foms-home-status]').querySelector('span');
      assert.strictEqual(span && span.textContent, want.done_status, $('[data-foms-home-status]').textContent);
    }
    assert.deepStrictEqual(calls.replace, [`http://127.0.0.1/erp/production/home?tab=steps&order=${want.next}`]);
    assert.strictEqual(gets().length, 0);
    // 셸 조각 교체 = 세 파일이 같은 문서에서 다시 돈다 — 문서 리스너는 한 번 단 그대로, 그래도 새로 연 창의 단추가 먹는다
    calls.fetch.length = 0;
    calls.replace.length = 0;
    homeRoot.listeners = {}; // 새 화면 = 새 루트(옛 루트 리스너는 화면과 함께 떠난다)
    homeRoot.removeAttribute('data-foms-home-steps-bound');
    homeRoot.removeAttribute('data-foms-home-bound');
    [STEPS_JS, HOME_JS, PARTS_JS].forEach(run);
    assert.strictEqual((docListeners.click || []).length, 1, '창 문서 리스너는 한 번');
    await sleep(700); // 저장 뒤 새 화면 [끝] 잠금(600ms)
    await tap(fin());
    shown('셸 교체 뒤에도 묻는다');
    await sleep(450);
    dispatch(yes, 'click');
    await flush(); await flush();
    assert.deepStrictEqual(posts(), [stepCall(want.first)], '셸 교체 뒤에도 [작업 완료]가 먹는다');
    // 창이 떠 있는 사이 판이 바뀌면(누른 [끝]이 화면에서 빠짐) [작업 완료]여도 엉뚱한 주문에 쓰지 않는다 — POST 0
    calls.fetch.length = 0;
    homeRoot.listeners = {};
    homeRoot.removeAttribute('data-foms-home-steps-bound');
    homeRoot.removeAttribute('data-foms-home-bound');
    [STEPS_JS, HOME_JS].forEach(run);
    await sleep(700);
    const old = fin();
    await tap(old);
    shown('다시 묻는다');
    const pane = old.closest('[data-foms-step-pane]');
    pane.parentNode.removeChild(pane);
    await sleep(450);
    dispatch(yes, 'click');
    await flush(); await flush();
    assert.ok(box.hidden && posts().length === 0, '빠진 단추의 주문은 저장하지 않는다');
  } else {
    const btnOf = (id) => $(`[data-foms-home-step-done][data-order-id="${id}"]`);
    await cancelFlow(btnOf(want.first));
    await tap(btnOf(want.first));
    await sleep(450);
    dispatch(yes, 'click');
    await flush(); await flush();
    assert.deepStrictEqual(posts(), [stepCall(want.first)], '[작업 완료] = POST 한 번');
    assert.strictEqual(calls.reload, 1, '줄 · 숫자는 서버가 다시 그린다(지금 줄 [끝] 저장 뒤와 같은 길)');
    if (want.done_status) { // 저장 뒤 상태 줄 글(그린 값) — 문장 속 움직임 말 "끝냈어요"는 그대로(§8-3 끝)
      assert.strictEqual($('[data-foms-home-status]').textContent, want.done_status);
    }
    // 도면 없는 줄 = 창 없이 바로(지금 그대로)
    calls.fetch.length = 0;
    assert.ok(!btnOf(want.bare).hasAttribute('data-foms-sheet-parts'));
    await tap(btnOf(want.bare));
    assert.ok(box.hidden, '도면 없는 줄은 묻지 않는다');
    assert.deepStrictEqual(posts(), [stepCall(want.bare)]);
    assert.strictEqual(gets().length, 0);
  }
  console.log('OK');
  process.exit(0); // 되돌리기 · 잠금 타이머를 기다리지 않는다
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
