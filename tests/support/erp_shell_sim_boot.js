'use strict';
/*
 * erp-shell.js 시뮬레이션 바탕 — 가짜 문서 · 가짜 시계 · 가짜 fetch 로 셸 스크립트를 vm 에서 돌린다.
 * 시나리오는 erp_shell_nav_cache_node_checks.js 가 든다(파일 크기 래칫 때문에 바탕만 갈랐다).
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
  const aborted = [];
  let mainQuery = null;
  const main = {
    _html: '',
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; swaps.push(v); },
    getAttribute: (n) => (n === 'data-foms-erp-shell-wrapped' ? '1' : null),
    setAttribute() {},
    removeAttribute() {},
    querySelectorAll: (sel) => (mainQuery ? mainQuery(sel) : []),
  };
  const navLinks = (o.navLinks || []).map((href) => ({ href: ORIGIN + href, hasAttribute: () => false }));
  const nav = { getClientRects: () => (navLinks.length ? [1] : []), querySelectorAll: () => navLinks };
  const drawerLinks = (o.drawerLinks || []).map((href) => ({ href: ORIGIN + href, hasAttribute: () => false }));
  const drawer = { querySelectorAll: () => drawerLinks };
  const document = {
    visibilityState: 'visible',
    readyState: o.readyState,
    head: { querySelectorAll: () => [], appendChild() {} },
    body: { classList: { remove() {} }, style: { removeProperty() {} } },
    addEventListener: (t, fn) => (listeners.document[t] = listeners.document[t] || []).push(fn),
    dispatchEvent() {},
    getElementById(id) {
      if (id === 'main-content') return main;
      if (id === 'erp-mobile-menu-drawer') return o.drawerLinks ? drawer : null;
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
    const call = { url: u.pathname + u.search, inm: h['If-None-Match'] || null, at: clock };
    calls.push(call);
    const signal = init && init.signal;
    const reply = () => {
      if (call.inm && (o.unchanged === undefined || o.unchanged)) {
        return { status: 304, ok: false, headers: { get: () => null }, url: String(url) };
      }
      const hdr = { 'x-foms-erp-fragment': '1', etag: '"e:' + u.pathname + '"' };
      return { status: 200, ok: true, url: String(url), headers: { get: (n) => hdr[String(n).toLowerCase()] || null },
        text: () => Promise.resolve('<div>' + u.pathname + u.search + '</div>') };
    };
    if (manual) {
      return new Promise((resolve, reject) => {
        let settled = false;
        if (signal) {
          signal.addEventListener('abort', () => {
            if (settled) return;
            settled = true;
            aborted.push(call.url);
            const err = new Error('aborted');
            err.name = 'AbortError';
            reject(err);
          });
        }
        manual.push(() => { if (!settled) { settled = true; resolve(reply()); } });
      });
    }
    return Promise.resolve(reply());
  }
  class FakeDate extends Date { static now() { return clock; } }
  const sandbox = {
    document, console, URL, URLSearchParams, Promise, Date: FakeDate, fetch: fakeFetch, AbortController,
    navigator: { connection: o.saveData ? { saveData: true } : undefined },
    CustomEvent: function () {},
    performance: { now: () => clock - 1700000000000 },
    sessionStorage: o.storage || makeStorage(),
    location: { href: ORIGIN + (o.path || '/erp/dashboard'), origin: ORIGIN },
    history: { state: null, pushState: (s, t, u) => { pushes.push(u); sandbox.location.href = ORIGIN + u; }, replaceState() {} },
    scrollY: 0, scrollTo() {},
    addEventListener: (t, fn) => (listeners.window[t] = listeners.window[t] || []).push(fn),
    setTimeout: addTimer, clearTimeout() {}, setInterval() { return 0; }, clearInterval() {},
  };
  if (o.raf) sandbox.requestAnimationFrame = (fn) => addTimer(fn, 16); // 다음 프레임 = 16ms 뒤(없으면 셸은 setTimeout 0 으로 간다)
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SHELL_JS, sandbox, { filename: 'erp-shell.js' });
  async function drain() {
    for (let i = 0; i < 8; i += 1) await new Promise((r) => setImmediate(r));
  }
  return {
    sandbox, calls, pushes, swaps, listeners, aborted,
    now: () => clock - 1700000000000,
    setMainQuery: (fn) => { mainQuery = fn; },
    fireLoad: async () => { (listeners.window.load || []).forEach((fn) => fn({})); await drain(); },
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

module.exports = { boot, makeStorage, ORIGIN };
