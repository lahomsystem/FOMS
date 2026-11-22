// 작업 시트 '눌러도 까닭을 알린다'(2026-11-22 터치 점검 P2) — 서버가 그린 진짜 시트(argv[2]) 위에서 Node 로.
// tests/domains/test_production_sheet_tap_explains.py 가 부른다. 시트 JS + 도메인 시트 JS(제작 완료 POST 길)를 같이 돌린다.
// mode=complete: 회색 [제작 완료] 누름 = 상태 줄에 남은 공정 · 요청 0 · 확인 창 0 → 칸을 켜 4칸이 되면 파랑 → 누르면 확인 창 + 완료 POST.
// mode=locked: 잠긴 공정 칸(파트 계정) 누름 = 상태 줄에 잠금 글 · 요청 0.
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { fakeDom } = require('./production_fake_dom.js');

const root = path.resolve(__dirname, '..', '..');
const want = JSON.parse(process.argv[3]); // {mode, order, labels: [4], done: [켜진 칸 열쇠]}
const D = fakeDom();
const body = D.parse(fs.readFileSync(process.argv[2], 'utf8'));
const calls = { fetch: [], confirm: [], alert: [] };
const done = new Set(want.done);
const location = { href: 'http://127.0.0.1/erp/production/sheet/' + want.order, origin: 'http://127.0.0.1', pathname: '/erp/production/sheet/' + want.order,
  search: '', protocol: 'http:', replace() {}, assign() {}, reload() {} };
const ctx = {
  console, URL, JSON, Promise, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Set, Map, setTimeout, clearTimeout,
  location, navigator: { onLine: true },
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
  alert: (msg) => { calls.alert.push(msg); },
  fetch: (url, opts) => {
    const b = opts && opts.body ? JSON.parse(opts.body) : null;
    calls.fetch.push({ url, method: opts && opts.method, body: b });
    let data = { success: true, data: {} };
    if (/\/production\/steps$/.test(url)) {
      if (b.done) { done.add(b.key); } else { done.delete(b.key); }
      const steps = ['cut', 'edge', 'assemble', 'inspect'].map((k) => ({ key: k, done: done.has(k), by_name: done.has(k) ? '이철호' : null }));
      data = { success: true, data: { steps, complete_ready: done.size === 4 || done.size === 0 } };
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
  },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
for (const rel of ['static/js/production/foms-production-sheet-page.js', 'static/js/foms/tablet-domain-sheets.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, rel), 'utf8'), ctx, { filename: rel });
}
const flush = async () => { for (let i = 0; i < 4; i += 1) { await new Promise((r) => setImmediate(r)); } };
const $ = (s) => body.querySelector(s);
const status = () => $('[data-foms-sheet-status]');
const step = (k) => $(`[data-foms-sheet-step="${k}"]`);
const all = (want.labels || []).join(' · ');

(async () => {
  if (want.mode === 'locked') {
    const cell = step('cut');
    assert.strictEqual(cell.getAttribute('aria-disabled'), 'true');
    assert.strictEqual(cell.hasAttribute('disabled'), false, '진짜 disabled 는 없다(누름이 JS 에 닿는다)');
    D.dispatch(cell.querySelector('span'), 'click');
    await flush();
    assert.strictEqual(calls.fetch.length, 0, '잠긴 칸 누름 = 요청 0');
    assert.strictEqual(status().textContent, want.note);
    assert.ok(status().classList.contains('is-bad'));
    console.log('OK');
    return;
  }
  const btn = $('[data-foms-sheet-complete]');
  assert.strictEqual(btn.getAttribute('aria-disabled'), 'true');
  assert.ok(!btn.hasAttribute('disabled') && !btn.disabled, '진짜 disabled 는 없다');
  // 1) 회색 누름(안쪽 글 조각) = 상태 줄 글 · 요청 0 · 확인 창 0
  D.dispatch(btn.querySelector('b'), 'click');
  await flush();
  assert.deepStrictEqual([calls.fetch.length, calls.confirm.length], [0, 0], '회색 [제작 완료] = 요청 0');
  const left = want.labels.filter((l, i) => !want.done.includes(['cut', 'edge', 'assemble', 'inspect'][i])).join(' · ');
  assert.strictEqual(status().textContent, `공정 4칸(${all})을 모두 끝내야 제작 완료를 누를 수 있어요. 남은 공정: ${left}`);
  assert.ok(status().classList.contains('is-bad'));
  // 2) 칸을 하나씩 켠다 — 4칸이 되기 전까지는 회색 · 남은 공정이 줄어든다
  const off = ['cut', 'edge', 'assemble', 'inspect'].filter((k) => !done.has(k));
  for (const k of off.slice(0, -1)) { D.dispatch(step(k), 'click'); await flush(); }
  assert.strictEqual(btn.getAttribute('aria-disabled'), 'true');
  D.dispatch(btn, 'click');
  assert.strictEqual(status().textContent, `공정 4칸(${all})을 모두 끝내야 제작 완료를 누를 수 있어요. 남은 공정: ${want.labels[3]}`);
  assert.strictEqual(calls.fetch.filter((c) => /complete$/.test(c.url)).length, 0);
  // 3) 4번째 칸 → 파랑(aria-disabled 없음 · 안내 글 숨김) → 누르면 확인 창 + 완료 POST 한 번
  D.dispatch(step(off[off.length - 1]), 'click');
  await flush();
  assert.strictEqual(btn.hasAttribute('aria-disabled'), false, '화면 읽기도 켜짐');
  assert.ok(btn.classList.contains('foms-prod-page__btn--pri') && !btn.classList.contains('foms-prod-page__btn--off'));
  assert.ok($('[data-foms-sheet-complete-hint]').hidden);
  D.dispatch(btn, 'click');
  await flush();
  assert.strictEqual(calls.confirm.length, 1);
  assert.deepStrictEqual(calls.fetch.filter((c) => /complete$/.test(c.url)).map((c) => c.url), [`/api/orders/${want.order}/production/complete`]);
  // 4) 한 칸을 다시 끄면 회색으로 돌아가고 다시 까닭을 알린다
  D.dispatch(step('inspect'), 'click');
  await flush();
  assert.strictEqual(btn.getAttribute('aria-disabled'), 'true');
  const before = calls.fetch.length;
  D.dispatch(btn, 'click');
  assert.strictEqual(calls.fetch.length, before);
  console.log('OK');
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
