// 작업 시트 [수정 제작] 고르기 창(설계서 2026-11-28 흐름 셋 §2-2) — 서버가 그린 진짜 화면(argv[2]) 위에서 Node 로.
// tests/domains/test_production_rework_pick_1128.py 가 부른다. want = argv[3]
//   {scripts, order_id, kind: 'drawings'|'steps', pick: [줄 열쇠…], locked: {key, why}|null, note, post, message}.
// 길: [수정 제작] → 고르기 창(사유 창 · POST 0) → 연 바로 뒤 누름은 버림 → 줄을 누르면 골라지고 다시 누르면 풀림 · 0개면 [다음] 잠김 + 아래 한 줄
//   → 남의 공장 줄은 안 골라지고 글만 → [닫기] · Esc · 바깥 = 아무 것도 안 함 → [다음] = 지금 사유 창(지금 글 + 한 줄) → [수정 제작] = 같은 주소로
//   POST 한 번(사유 + 고른 것) → 다시 읽기 → 다시 받은 화면 상태 줄에 서버 글 한 번.
// 가짜 DOM = production_fake_dom.js(문서 리스너의 잡기 단계 · MutationObserver 는 없다 — 그 둘은 여기서 안 본다).
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
const store = {};
let reply = null;
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
  sessionStorage: { getItem: (k) => (k in store ? store[k] : null), setItem(k, v) { store[k] = String(v); }, removeItem(k) { delete store[k]; } },
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
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
const load = (rel) => vm.runInContext(fs.readFileSync(path.join(root, rel), 'utf8'), ctx, { filename: rel });
want.scripts.forEach(load);

const flush = () => new Promise((r) => setImmediate(r));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (s) => body.querySelector(s);
const click = (el) => D.dispatch(el, 'click');
const posts = () => calls.fetch.filter((c) => c.method === 'POST');

(async () => {
  const btn = $('[data-tablet-sheet-action="production-rework"][data-order-id="' + want.order_id + '"]');
  const box = $('[data-foms-rework-pick]');
  const reason = $('[data-foms-reason-sheet]');
  assert.ok(btn && box && reason, '단추 · 고르기 창 · 사유 창이 한 화면에 있다');
  assert.strictEqual(box.getAttribute('data-foms-rework-pick'), want.kind);
  const next = box.querySelector('[data-foms-rework-next]');
  const hint = box.querySelector('[data-foms-rework-hint]');
  const msg = box.querySelector('[data-foms-rework-msg]');
  const close = box.querySelector('[data-foms-rework-close].foms-btn');
  const dim = box.querySelector('.foms-reason-sheet__backdrop');
  const row = (key) => box.querySelectorAll('[data-foms-rework-item]').find((r) => r.getAttribute('data-foms-rework-item') === key);
  const pressed = () => box.querySelectorAll('[data-foms-rework-item]').filter((r) => r.getAttribute('aria-pressed') === 'true').length;
  const open = async () => { click(btn); assert.ok(!box.hidden && box.getAttribute('aria-hidden') === 'false', '고르기 창이 뜬다'); await sleep(450); };

  // ① 누르면 고르기 창 먼저 — 사유 창 · 요청 없음, 아무것도 안 고른 채 [다음] 잠김 + 아래 한 줄
  click(btn);
  assert.ok(!box.hidden && reason.hidden, '고르기 창이 먼저, 사유 창은 아직');
  assert.strictEqual(next.disabled, true);
  assert.strictEqual(hint.hidden, false);
  const first = row(want.pick[0]);
  click(first); click(next);
  assert.strictEqual(pressed(), 0, '연 바로 뒤 누름은 버린다');
  await sleep(450);
  // ② 누르면 골라지고 다시 누르면 풀린다
  click(first);
  assert.strictEqual(first.getAttribute('aria-pressed'), 'true');
  assert.strictEqual(next.disabled, false);
  assert.strictEqual(hint.hidden, true);
  click(first);
  assert.strictEqual(first.getAttribute('aria-pressed'), 'false');
  assert.strictEqual(next.disabled, true, '0개면 [다음] 잠김');
  assert.strictEqual(hint.hidden, false);
  click(next);
  assert.ok(!box.hidden && reason.hidden, '잠긴 [다음]은 아무 일도 안 한다');
  // ③ 남의 공장 도면 — 안 골라지고 글만
  if (want.locked) {
    const other = row(want.locked.key);
    assert.strictEqual(other.getAttribute('aria-disabled'), 'true');
    click(other);
    assert.strictEqual(other.getAttribute('aria-pressed'), 'false');
    assert.strictEqual(msg.textContent, want.locked.why);
    assert.strictEqual(msg.hidden, false);
    assert.strictEqual(next.disabled, true);
  }
  // ④ [닫기] · Esc · 바깥 = 아무 것도 안 함(다시 열면 고른 것이 비어 있다)
  click(first); click(close);
  assert.ok(box.hidden && box.getAttribute('aria-hidden') === 'true' && reason.hidden);
  await open();
  assert.strictEqual(pressed(), 0, '다시 열면 고른 것이 비어 있다');
  assert.strictEqual(msg.hidden, true);
  D.dispatch(body, 'keydown', { key: 'Escape' });
  assert.ok(box.hidden, 'Esc 로 닫힌다');
  await open();
  click(dim);
  assert.ok(box.hidden, '바깥으로 닫힌다');
  assert.strictEqual(posts().length, 0, '[닫기] · Esc · 바깥 = POST 0');
  assert.ok(reason.hidden);
  // ⑤ 고르고 [다음] → 지금 사유 창 + 한 줄
  await open();
  want.pick.forEach((key) => click(row(key)));
  assert.strictEqual(pressed(), want.pick.length);
  click(next);
  assert.ok(box.hidden && !reason.hidden, '[다음] = 사유 창');
  assert.strictEqual(reason.querySelector('[data-foms-reason-title]').textContent, '수정 제작으로 되돌릴까요?');
  assert.strictEqual(reason.querySelector('[data-foms-reason-detail-label]').textContent, '수정 제작 사유(안 적어도 돼요)');
  assert.strictEqual(reason.querySelector('[data-foms-reason-submit]').textContent, '수정 제작');
  const line = reason.querySelector('[data-foms-rework-note]');
  assert.ok(line, '사유 창에 한 줄');
  assert.strictEqual(line.textContent, want.note);
  assert.strictEqual(reason.querySelectorAll('[data-foms-rework-note]').length, 1);
  assert.strictEqual(posts().length, 0, '사유 창까지 POST 0');
  // ⑥ [수정 제작] = 사유 + 고른 것을 같은 주소로 한 번
  await sleep(450);
  reason.querySelector('[data-foms-reason-detail]').value = '  문짝 치수  ';
  click(reason.querySelector('[data-foms-reason-submit]'));
  await flush();
  assert.deepStrictEqual(posts(), [{ url: '/api/orders/' + want.order_id + '/production/rework', method: 'POST',
    body: Object.assign({ reason: '문짝 치수' }, want.post) }]);
  assert.ok(reason.hidden);
  // ⑦ 성공 → 다시 읽기 · 다시 받은 화면 상태 줄에 서버 글 한 번
  const r = reply; reply = null;
  r({ ok: true, status: 200, json: () => Promise.resolve({ success: true, message: want.message, new_status: 'PRODUCTION' }) });
  for (let i = 0; i < 6; i += 1) { await flush(); }
  assert.strictEqual(calls.reload, 1, '저장되면 다시 읽는다');
  const status = $('[data-foms-sheet-status]');
  assert.ok(status, '상태 줄');
  assert.strictEqual(status.textContent, '', '다시 읽기 전에는 그대로');
  load(want.scripts.filter((s) => /sheet-rework\.js$/.test(s))[0]); // 다시 받은 화면 = 스크립트가 다시 돈다
  assert.strictEqual(status.textContent, want.message);
  assert.ok(status.classList.contains('is-ok') && !status.classList.contains('is-bad'));
  status.textContent = '';
  load(want.scripts.filter((s) => /sheet-rework\.js$/.test(s))[0]);
  assert.strictEqual(status.textContent, '', '알림은 한 번만');
  assert.deepStrictEqual([calls.confirm.length, calls.alert.length], [0, 0], '기본 창 0');
  console.log('OK');
  process.exit(0);
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
