'use strict';
/*
 * erp-shell.js 스왑 · 캐시 동작 시뮬레이션(가짜 문서 · 가짜 시계) — 판정은
 * tests/domains/test_erp_shell_nav_cache.py 가 한다. 시나리오마다 JSON 한 줄을 낸다.
 *
 *   marker   — 링크의 view=queue 가 조각 요청에 남고 표식은 foms_shell 로 간다.
 *   stale    — TTL 이 지난 줄도 ETag 를 남겨 If-None-Match 를 보내고 304 면 그 html 로 스왑한다.
 *   seed     — pagehide 때 적은 씨앗으로 새 문서가 If-None-Match 를 보낸다(다른 사용자면 지운다).
 *   dedupe   — 같은 곳 스왑이 도는 중 다시 누름은 요청 · 스왑을 늘리지 않는다(줄 선 누름 포함).
 *   prewarm  — 첫 웜업이 보이는 아래 탭을 탭 순서대로 받는다(아래 탭이 없으면 예전 PRIMARY 앞 3개).
 *
 * 환경 변수 FOMS_SIM_SHELL_JS 가 있으면 그 사본을 돌린다(음성 대조군).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');
const SHELL_PATH = process.env.FOMS_SIM_SHELL_JS || path.join(ROOT, 'static/js/runtime/erp-shell.js');
const SHELL_JS = fs.readFileSync(SHELL_PATH, 'utf8');
const ORIGIN = 'https://foms.test';

function makeStorage() {
  const data = new Map();
  return {
    data,
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
  };
}

function boot(opts) {
  const o = opts || {};
  let clock = 1700000000000;
  const timers = [];
  const listeners = { document: {}, window: {} };
  const calls = [];
  const pushes = [];
  const swaps = [];
  let manual = null; // 손으로 답할 fetch 들(null 이면 바로 답한다)
  const main = {
    _html: '',
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; swaps.push(v); },
    getAttribute: (n) => (n === 'data-foms-erp-shell-wrapped' ? '1' : null),
    setAttribute() {},
    removeAttribute() {},
    querySelectorAll: () => [],
  };
  const navLinks = (o.navLinks || []).map((href) => ({ href: ORIGIN + href, hasAttribute: () => false }));
  const nav = { getClientRects: () => (navLinks.length ? [1] : []), querySelectorAll: () => navLinks };
  const document = {
    visibilityState: 'visible',
    head: { querySelectorAll: () => [], appendChild() {} },
    body: { classList: { remove() {} }, style: { removeProperty() {} } },
    addEventListener: (t, fn) => (listeners.document[t] = listeners.document[t] || []).push(fn),
    dispatchEvent() {},
    getElementById(id) {
      if (id === 'main-content') return main;
      if (id === 'foms-sw-config') return { getAttribute: () => (o.subject === undefined ? '7' : o.subject) };
      return null;
    },
    querySelector: (sel) => (sel === '.erp-mobile-bottom-nav' && o.navLinks ? nav : null),
    querySelectorAll: () => [],
  };
  function addTimer(fn, delay) {
    timers.push({ fn, due: clock + Math.max(0, delay || 0) });
    return timers.length;
  }
  function fakeFetch(url, init) {
    const u = new URL(url);
    const h = (init && init.headers) || {};
    const call = { url: u.pathname + u.search, inm: h['If-None-Match'] || null };
    calls.push(call);
    const reply = () => {
      if (call.inm && (o.unchanged === undefined || o.unchanged)) {
        return { status: 304, ok: false, headers: { get: () => null }, url: String(url) };
      }
      const hdr = { 'x-foms-erp-fragment': '1', etag: '"e:' + u.pathname + '"' };
      return { status: 200, ok: true, url: String(url), headers: { get: (n) => hdr[String(n).toLowerCase()] || null },
        text: () => Promise.resolve('<div>' + u.pathname + u.search + '</div>') };
    };
    if (manual) return new Promise((resolve) => manual.push(() => resolve(reply())));
    return Promise.resolve(reply());
  }
  class FakeDate extends Date { static now() { return clock; } }
  const sandbox = {
    document, console, URL, URLSearchParams, Promise, Date: FakeDate, fetch: fakeFetch,
    CustomEvent: function () {},
    performance: { now: () => clock - 1700000000000 },
    sessionStorage: o.storage || makeStorage(),
    location: { href: ORIGIN + (o.path || '/erp/dashboard'), origin: ORIGIN },
    history: { state: null, pushState: (s, t, u) => { pushes.push(u); sandbox.location.href = ORIGIN + u; }, replaceState() {} },
    scrollY: 0, scrollTo() {},
    addEventListener: (t, fn) => (listeners.window[t] = listeners.window[t] || []).push(fn),
    setTimeout: addTimer, clearTimeout() {}, setInterval() { return 0; }, clearInterval() {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SHELL_JS, sandbox, { filename: 'erp-shell.js' });
  async function drain() {
    for (let i = 0; i < 8; i += 1) await new Promise((r) => setImmediate(r));
  }
  return {
    sandbox, calls, pushes, swaps, listeners,
    shell: sandbox.FOMS_ERP_SHELL,
    advance: async (ms) => {
      const end = clock + ms;
      for (;;) {
        timers.sort((a, b) => a.due - b.due);
        if (!timers.length || timers[0].due > end) break;
        const t = timers.shift();
        clock = Math.max(clock, t.due);
        t.fn();
        await drain();
      }
      clock = end;
      await drain();
    },
    holdFetches: () => { manual = []; },
    releaseFetches: async () => { const q = manual || []; manual = null; q.forEach((f) => f()); await drain(); },
    pagehide: () => (listeners.window.pagehide || []).forEach((fn) => fn({})),
    drain,
  };
}

async function marker() {
  const b = boot({ path: '/erp/dashboard' });
  await b.shell.navigateByShell(ORIGIN + '/erp/dashboard?view=queue');
  await b.drain();
  return { fetched: b.calls.map((c) => c.url), pushed: b.pushes };
}

async function stale() {
  const b = boot({ path: '/erp/dashboard' });
  await b.shell.navigateByShell(ORIGIN + '/erp/shipment');
  await b.shell.navigateByShell(ORIGIN + '/erp/dashboard?view=queue');
  await b.advance(11 * 60 * 1000);
  await b.shell.navigateByShell(ORIGIN + '/erp/shipment');
  return { calls: b.calls, lastSwap: b.swaps[b.swaps.length - 1] };
}

async function seed() {
  const storage = makeStorage();
  const a = boot({ path: '/erp/dashboard', storage });
  await a.shell.navigateByShell(ORIGIN + '/erp/shipment');
  a.pagehide();
  const same = boot({ path: '/erp/dashboard', storage });
  await same.shell.navigateByShell(ORIGIN + '/erp/shipment');
  const other = boot({ path: '/erp/dashboard', storage, subject: '8' });
  await other.advance(60 * 1000); // 첫 웜업 자리에서 남의 씨앗을 지운다
  await other.shell.navigateByShell(ORIGIN + '/erp/shipment');
  return { same: same.calls[0], sameSwap: same.swaps[0], other: other.calls.filter((c) => c.url.indexOf('/erp/shipment') === 0)[0],
    keysAfterOther: Array.from(storage.data.keys()).filter((k) => k.indexOf('foms_shell_seed:') === 0).length };
}

async function dedupe() {
  const b = boot({ path: '/erp/dashboard' });
  b.holdFetches();
  const p1 = b.shell.navigateByShell(ORIGIN + '/erp/as');
  const p2 = b.shell.navigateByShell(ORIGIN + '/erp/as');
  await b.releaseFetches();
  await Promise.all([p1, p2]);
  const afterInflight = { fetches: b.calls.length, swaps: b.swaps.length, samePromise: p1 === p2 };
  // 스왑 긴 작업 동안 줄 선 누름: 입력 시각이 스왑 끝보다 앞이다.
  await b.shell.navigateByShell(ORIGIN + '/erp/as', { inputTs: b.sandbox.performance.now() - 50 });
  await b.drain();
  return { afterInflight, afterQueued: { fetches: b.calls.length, swaps: b.swaps.length } };
}

async function prewarm() {
  const phone = boot({ path: '/erp/dashboard', navLinks: ['/erp/construction/dashboard', '/erp/shipment', '/erp/dashboard', '/erp/as', '/wdcalculator'] });
  await phone.advance(30 * 1000);
  const pc = boot({ path: '/erp/dashboard' });
  await pc.advance(30 * 1000);
  return { phone: phone.calls.map((c) => c.url), pc: pc.calls.map((c) => c.url) };
}

(async function run() {
  const out = { marker: await marker(), stale: await stale(), seed: await seed(), dedupe: await dedupe(), prewarm: await prewarm() };
  process.stdout.write(JSON.stringify(out) + '\n');
})().catch((err) => {
  process.stderr.write(String((err && err.stack) || err) + '\n');
  process.exit(1);
});
