// 작업 시트 공정 칸 — 도면이 있는 주문은 보기 줄, 도면 0장 주문만 체크 칸(사장님 2026-11-27 "도면 두 장 이상이면 막기" → "도면이 주,
// 작업 시트는 보기"). 서버가 그린 진짜 작업 시트(argv[2]) 위에서 시트 JS(foms-production-sheet-parts.js + foms-production-sheet-page.js)를 Node 로.
// tests/domains/test_production_per_sheet_only_1127.py · test_production_steps_view_only_1127.py 가 부른다. want = argv[3] {key, mode, msg, text, reply}.
// · mode=view: 보기 줄 누름 = POST 0 · 확인 창 0 · 칸 아래 글 0(줄은 링크 · 글뿐 — 시트 JS 가 받지 않는다).
// · mode=stale: 낡은 화면(체크 칸이 남았는데 서버 자료 per_sheet = msg) — 꺼진 칸 누름 = POST 0 · 확인 창 0 · 칸 아래 글 = msg · 칸은 꺼진 채.
// · mode=off: 켜진 칸 누름(끄기) = 확인 창 없이 POST 한 번 {key, done:false}. reply(공정 응답 data)가 있으면 그 응답 뒤 손 체크 칸은 숨고
//   공정 칸 셈에서 빠지며(data-foms-sheet-step 없음) 서버가 그려 둔 줄(data-foms-sheet-hand-after)이 보인다(글 = text).
// · mode=zero: 도면 0장 주문 꺼진 칸 누름 = 확인 창 없이 POST 한 번 {key, done:true}(지금 그대로).
// · mode=why: 회색 [제작 완료] 누름 = POST 0 · 상태 줄 글 = text.
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
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: want.reply || {} }) });
  },
};
ctx.window = ctx;
ctx.addEventListener = () => {};
vm.createContext(ctx);
const $ = (s) => body.querySelector(s);
const page = $('[data-foms-prod-sheet-page]');
page.dispatchEvent = () => true; // 가짜 DOM 에 없는 것 — 공정 응답 뒤 공장 단추 알림(sheet-parts render)
if (want.mode === 'stale') { // 낡은 화면 — 도면 0장 때 그린 체크 칸 그대로인데 그사이 도면이 왔다(서버 자료만 새 것)
  const holder = $('[data-foms-sheet-parts]');
  const info = JSON.parse(holder.getAttribute('data-foms-sheet-parts'));
  holder.setAttribute('data-foms-sheet-parts', JSON.stringify(Object.assign(info, { sheets: 1, per_sheet: want.msg })));
}
for (const rel of ['static/js/production/foms-production-sheet-parts.js', 'static/js/production/foms-production-sheet-page.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, rel), 'utf8'), ctx, { filename: rel });
}
const flush = async () => { for (let i = 0; i < 6; i += 1) { await new Promise((r) => setImmediate(r)); } };
const posts = () => calls.fetch.filter((c) => c.method === 'POST');
const box = $('[data-foms-sheet-confirm]');
const msg = $('[data-foms-sheet-stepmsg]');

(async () => {
  assert.ok(box && msg, '확인 창 · 칸 아래 글 자리');
  if (want.mode === 'view') {
    const line = $(`[data-foms-sheet-line="${want.key}"]`);
    assert.ok(line && !$(`[data-foms-sheet-step="${want.key}"]`), '보기 줄만(체크 칸 없음)');
    D.dispatch(line.querySelector('span'), 'click');
    await flush();
    assert.strictEqual(calls.fetch.length, 0, '요청 0');
    assert.ok(box.hidden && msg.hidden, '확인 창 · 칸 아래 글 없음');
  } else if (want.mode === 'why') {
    const done = $('[data-foms-sheet-complete]');
    assert.strictEqual(done.getAttribute('aria-disabled'), 'true', '회색 [제작 완료]');
    D.dispatch(done, 'click');
    await flush();
    assert.strictEqual(posts().length, 0);
    assert.strictEqual($('[data-foms-sheet-status]').textContent, want.text);
  } else {
    const cell = $(`[data-foms-sheet-step="${want.key}"]`);
    assert.ok(cell, '체크 칸');
    D.dispatch(cell.querySelector('span'), 'click');
    await flush();
    if (want.mode === 'stale') {
      assert.strictEqual(calls.fetch.length, 0, '요청 0(자료는 화면에 실려 있다)');
      assert.ok(box.hidden, '확인 창 없음');
      assert.strictEqual(msg.textContent, want.msg);
      assert.strictEqual(msg.hidden, false);
      assert.strictEqual(cell.getAttribute('aria-pressed'), 'false', '칸은 꺼진 채');
      assert.strictEqual(cell.disabled, false, '다시 누를 수 있다');
    } else if (want.mode === 'off') {
      assert.ok(box.hidden, '끄기는 묻지 않는다');
      assert.deepStrictEqual(posts().map((c) => c.body), [{ key: want.key, done: false }]);
      if (want.reply) {
        const after = $(`[data-foms-sheet-hand-after="${want.key}"]`);
        assert.ok(cell.hidden && !cell.hasAttribute('data-foms-sheet-step'), '끈 칸은 숨고 셈에서 빠진다');
        assert.strictEqual(after.hidden, false);
        assert.strictEqual(after.textContent.replace(/\s+/g, ' ').trim(), want.text);
      }
    } else { // zero
      assert.ok(box.hidden, '도면 0장 = 묻지 않는다');
      assert.ok(msg.hidden, '칸 아래 글 없음');
      assert.deepStrictEqual(posts().map((c) => c.body), [{ key: want.key, done: true }]);
    }
  }
  console.log('OK');
})().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
