// 생산 도면 판 — 쓰기 뒤 위 탭 숫자 · 탭 사본 맞추기(foms-production-parts-fresh.js)를 Node 로 돌린다.
// tests/domains/test_production_part_start_label_1127.py 가 부른다. argv[2] = 파일, argv[3] = want
// {tabs: [{href, small, cls}], here, reply(서버 ?view=counts 답), steps: [{type, detail}]}.
// 셸 문(FOMS_ERP_SHELL.invalidateFragmentCache) · fetch 는 받은 것을 적어 두는 가짜. 결과 stdout JSON [{dropped, calls, listeners, smalls}].
'use strict';
const vm = require('vm');
const fs = require('fs');

const src = fs.readFileSync(process.argv[2], 'utf8');
const want = JSON.parse(process.argv[3]);
const O = 'http://foms.test';
function small(text, cls) {
  const s = new Set((cls || '').split(' ').filter(Boolean));
  return { textContent: text, classList: { toggle(c, on) { if (on) { s.add(c); } else { s.delete(c); } }, contains: (c) => s.has(c) } };
}
const tabs = want.tabs.map((t) => ({ href: O + t.href, _s: t.small == null ? null : small(t.small, t.cls), querySelector() { return this._s; } }));
const root = { querySelectorAll: (sel) => (sel.indexOf('.foms-prod-home__navtab') >= 0 ? tabs : []) };
const listeners = {};
const dropped = [];
const calls = [];
const document = {
  querySelector: (s) => (s === '[data-foms-prod-home]' ? root : null), contains: (n) => n === root,
  addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
};
const ctx = { document, URL, console, Promise, JSON, Array, String, Number, Object };
ctx.window = ctx;
ctx.location = { href: O + want.here, origin: O };
ctx.FOMS_ERP_SHELL = { invalidateFragmentCache(u) { dropped.push(String(u).replace(O, '')); } };
ctx.fetch = (url, opts) => {
  calls.push({ url, method: opts.method, cache: opts.cache });
  return Promise.resolve({ ok: true, json: () => Promise.resolve(want.reply) });
};
vm.createContext(ctx);
vm.runInContext(src, ctx);
vm.runInContext(src, ctx); // 셸 조각 교체로 같은 화면에 다시 돌아도 리스너는 한 번
const tick = () => new Promise((r) => setTimeout(r, 0));
(async () => {
  const out = [];
  for (const s of want.steps) {
    dropped.length = 0;
    calls.length = 0;
    (listeners[s.type] || []).forEach((f) => f({ type: s.type, detail: s.detail }));
    await tick(); await tick(); await tick();
    out.push({ dropped: dropped.slice(), calls: calls.slice(), listeners: (listeners[s.type] || []).length,
      smalls: tabs.map((t) => (t._s ? { text: t._s.textContent, hot: t._s.classList.contains('is-hot') } : null)) });
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error((e && e.stack) || e); process.exit(1); });
