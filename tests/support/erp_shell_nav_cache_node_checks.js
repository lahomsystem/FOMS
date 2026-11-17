'use strict';
/*
 * erp-shell.js 스왑 · 캐시 동작 시뮬레이션(가짜 문서 · 가짜 시계) — 판정은
 * tests/domains/test_erp_shell_nav_cache.py 가 한다. 시나리오마다 JSON 한 줄을 낸다.
 *
 *   marker   — 링크의 view=queue 가 조각 요청에 남고 표식은 foms_shell 로 간다.
 *   stale    — TTL 이 지난 줄도 ETag 를 남겨 If-None-Match 를 보내고 304 면 그 html 로 스왑한다.
 *   seed     — 받은 뒤 한가한 틈에 적은 씨앗으로 새 문서가 If-None-Match 를 보낸다(다른 사용자면 지운다). pagehide 는 비어 있다.
 *   dedupe   — 같은 곳 스왑이 도는 중 다시 누름 · 스왑 끝 1초 안 다시 누름은 요청 · 스왑을 늘리지 않는다. 1초 뒤 누름은 다시 그린다.
 *   prewarm  — 첫 웜업: 아래 탭 순서 → 예전 PRIMARY 앞 3개. 서랍 몫은 서랍을 열 때(신선한 것 · 데이터 절약 · 아래 탭 없음이면 뺌).
 *              아래 탭이 없으면 예전 PRIMARY 앞 3개.
 *   drawerDefer — 서랍 몫 미리 받기는 서랍 열기 클릭 작업 밖(그린 뒤)에서 쏜다. 그 틈의 누름은 목적지만 바로 받는다.
 *   yield    — 사용자 이동이 미리 받기를 이긴다: load 전엔 웜업 0발, 다른 곳 미리 받기는 끊고 같은 곳은 이어받는다, 스왑 직후엔 쉰다.
 *   overlay  — 전환 중(hiding)인 서랍은 스왑이 바로 dispose 하지 않고 hidden 뒤(또는 1초 대비책)에 정리한다.
 *
 * 환경 변수 FOMS_SIM_SHELL_JS 가 있으면 그 사본을 돌린다(음성 대조군).
 */
const { boot, makeStorage, ORIGIN } = require('./erp_shell_sim_boot.js');

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
  const pagehideListeners = (a.listeners.window.pagehide || []).length;
  const seedKeys = () => Array.from(storage.data.keys()).filter((k) => k.indexOf('foms_shell_seed:') === 0).length;
  const beforeIdle = seedKeys();
  await a.advance(5 * 1000); // 받은 뒤 한가한 틈(스왑 직후 쉼 1.5초 + 1초)에 씨앗을 적는다
  const afterIdle = seedKeys();
  a.pagehide();
  const same = boot({ path: '/erp/dashboard', storage });
  await same.shell.navigateByShell(ORIGIN + '/erp/shipment');
  const other = boot({ path: '/erp/dashboard', storage, subject: '8' });
  await other.advance(60 * 1000); // 첫 웜업 자리에서 남의 씨앗을 지운다
  await other.shell.navigateByShell(ORIGIN + '/erp/shipment');
  return { pagehideListeners, beforeIdle, afterIdle, same: same.calls[0], sameSwap: same.swaps[0], other: other.calls.filter((c) => c.url.indexOf('/erp/shipment') === 0)[0],
    keysAfterOther: Array.from(storage.data.keys()).filter((k) => k.indexOf('foms_shell_seed:') === 0).length,
    subjectAfterOther: (JSON.parse(storage.data.get('foms_shell_seed_index') || 'null') || {}).s || null };
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
  await b.shell.navigateByShell(ORIGIN + '/erp/as', { inputTs: b.now() - 50 });
  await b.drain();
  const afterQueued = { fetches: b.calls.length, swaps: b.swaps.length };
  // 스왑이 끝나고 0.6초 뒤 같은 탭 다시 누름(반응을 기다리다 한 번 더) — 다시 받지 · 그리지 않는다.
  await b.advance(600);
  await b.shell.navigateByShell(ORIGIN + '/erp/as', { inputTs: b.now() });
  await b.drain();
  const afterRepeat = { fetches: b.calls.length, swaps: b.swaps.length };
  // 1초가 지난 뒤 다시 누름은 의도한 새로고침 — 지금처럼 다시 그린다(신선한 캐시면 캐시로).
  await b.advance(1000);
  await b.shell.navigateByShell(ORIGIN + '/erp/as', { inputTs: b.now() });
  await b.drain();
  const afterLater = { fetches: b.calls.length, swaps: b.swaps.length };
  // 다른 화면 스왑이 날고 있는 동안 지금 화면 탭을 누르면 '돌아가기' — 막지 않는다.
  const c = boot({ path: '/erp/dashboard' });
  await c.shell.navigateByShell(ORIGIN + '/erp/as');
  c.holdFetches();
  c.shell.navigateByShell(ORIGIN + '/erp/shipment', { inputTs: c.now() });
  const back = c.shell.navigateByShell(ORIGIN + '/erp/as', { inputTs: c.now() + 100 });
  await c.releaseFetches();
  await back;
  await c.drain();
  return { afterInflight, afterQueued, afterRepeat, afterLater,
    backDuringOther: { path: c.pushes[c.pushes.length - 1], lastSwap: c.swaps[c.swaps.length - 1] } };
}

const PHONE_NAV = ['/erp/construction/dashboard', '/erp/shipment', '/erp/dashboard', '/erp/as', '/wdcalculator'];
const PHONE_DRAWER = ['/erp/drawing-workbench', '/erp/production/dashboard', '/erp/as', '/erp/completion', '/erp/history/',
  '/erp/settlement', '/erp/shipment-settings', '/notices', '/erp/dashboard'];

/* 서랍 열림: Bootstrap 은 서랍 요소에서 show.bs.offcanvas 를 거품으로 올린다. other=true 면 다른 offcanvas 가 열린 것.
 * 그 클릭 작업 안에서(동기) 쏜 요청 수를 돌려주고, 다음 그리기 뒤(rAF 16ms + setTimeout 0)까지 흘린다. */
async function openDrawer(b, other) {
  const target = other ? {} : b.sandbox.document.getElementById('erp-mobile-menu-drawer');
  const before = b.calls.length;
  (b.listeners.document['show.bs.offcanvas'] || []).forEach((fn) => fn({ target }));
  const sync = b.calls.length - before;
  await b.advance(32);
  return sync;
}

/* 서랍 열기 작업에서 요청을 떼어 냈다: 클릭 작업 안 0발 · 다음 프레임 전 0발 · 그린 뒤 서랍 몫. 그 틈에 서랍 링크를 누르면
 * 그 목적지는 바로 받고(1발) 나머지 미리 받기는 쏘지 않는다. */
async function drawerDefer() {
  const b = boot({ path: '/erp/dashboard', navLinks: PHONE_NAV, drawerLinks: PHONE_DRAWER, raf: true });
  await b.advance(60 * 1000);
  const n0 = b.calls.length;
  const drawer = b.sandbox.document.getElementById('erp-mobile-menu-drawer');
  (b.listeners.document['show.bs.offcanvas'] || []).forEach((fn) => fn({ target: drawer }));
  const inClick = b.calls.length - n0;
  await b.advance(8);
  const beforeFrame = b.calls.length - n0;
  await b.advance(24);
  const afterPaint = b.calls.slice(n0).map((c) => c.url);
  const t = boot({ path: '/erp/dashboard', navLinks: PHONE_NAV, drawerLinks: PHONE_DRAWER, raf: true });
  await t.advance(60 * 1000);
  const m0 = t.calls.length;
  (t.listeners.document['show.bs.offcanvas'] || []).forEach((fn) => fn({ target: t.sandbox.document.getElementById('erp-mobile-menu-drawer') }));
  const nav = t.shell.navigateByShell(ORIGIN + '/erp/completion', { inputTs: t.now() });
  const atTap = t.calls.slice(m0).map((c) => c.url);
  await nav;
  await t.advance(2000);
  return { inClick, beforeFrame, afterPaint, atTap, afterTap: t.calls.slice(m0).map((c) => c.url) };
}

async function prewarm() {
  const urls = (b, from) => b.calls.slice(from || 0).map((c) => c.url);
  const phone = boot({ path: '/erp/dashboard', navLinks: PHONE_NAV, drawerLinks: PHONE_DRAWER });
  await phone.advance(60 * 1000);
  const phoneLoad = phone.calls.length;
  await openDrawer(phone, true);
  const otherOffcanvas = urls(phone, phoneLoad);
  await openDrawer(phone);
  const phoneOpen = phone.calls.length;
  await phone.advance(2000);
  await openDrawer(phone); // 다시 열어도 신선한 것은 다시 받지 않는다
  const saver = boot({ path: '/erp/dashboard', navLinks: PHONE_NAV, drawerLinks: PHONE_DRAWER, saveData: true });
  await saver.advance(60 * 1000);
  await openDrawer(saver);
  const pc = boot({ path: '/erp/dashboard', drawerLinks: PHONE_DRAWER });
  await pc.advance(60 * 1000);
  await openDrawer(pc);
  return { phone: urls(phone).slice(0, phoneLoad), otherOffcanvas, drawerOpen: urls(phone, phoneLoad).slice(0, phoneOpen - phoneLoad),
    reopen: urls(phone, phoneOpen), saver: urls(saver), pc: urls(pc) };
}

async function yieldToUser() {
  // load 전에는 웜업 0발, load 뒤 IDLE_DELAY 에 시작한다.
  const w = boot({ path: '/erp/dashboard', navLinks: PHONE_NAV, readyState: 'interactive' });
  await w.advance(9 * 1000);
  const beforeLoad = w.calls.length;
  w.sandbox.document.readyState = 'complete';
  await w.fireLoad();
  await w.advance(1600 + 50);
  const afterLoad = w.calls.map((c) => c.url);

  // 미리 받기(시공)가 날고 있을 때 출고를 누르면 시공 미리 받기는 끊긴다. 스왑 직후 1.5초는 다음 미리 받기를 쉰다.
  const b = boot({ path: '/erp/dashboard', navLinks: PHONE_NAV });
  b.holdFetches();
  await b.advance(1600 + 10);
  const inflight = b.calls.map((c) => c.url);
  const nav = b.shell.navigateByShell(ORIGIN + '/erp/shipment', { inputTs: b.now() });
  await b.drain();
  const abortedOther = b.aborted.slice();
  await b.releaseFetches();
  await nav;
  const swapAt = b.now();
  b.holdFetches();
  const after = (since) => b.calls.filter((c) => c.at - 1700000000000 > since).map((c) => c.url);
  await b.advance(1400);
  const duringQuiet = after(swapAt);
  await b.advance(2000);
  const afterQuiet = after(swapAt);
  // 날고 있는 미리 받기와 같은 곳을 누르면 그 요청을 이어받는다(새 요청 0, 끊김 0).
  const callsBefore = b.calls.length;
  const abortedBefore = b.aborted.length;
  const target = afterQuiet[afterQuiet.length - 1].split('?')[0];
  const nav2 = b.shell.navigateByShell(ORIGIN + target, { inputTs: b.now() });
  await b.drain();
  const adopted = { newCalls: b.calls.length - callsBefore, aborted: b.aborted.length - abortedBefore };
  await b.releaseFetches();
  await nav2;
  adopted.lastSwap = b.swaps[b.swaps.length - 1];
  return { beforeLoad, afterLoad, inflight, abortedOther, duringQuiet, afterQuiet, adopted };
}

/* 전환 중 서랍: 가짜 Bootstrap — hide() 는 .hiding 을 달고 300ms 뒤 완료 콜백이 this._element.classList 를 읽는다(진짜와 같다). */
function fakeBootstrap(b) {
  const errors = [];
  const instances = new Map();
  function makeEl(classes) {
    const set = new Set(classes);
    const ls = {};
    return {
      classList: { contains: (c) => set.has(c), add: (c) => set.add(c), remove: (...cs) => cs.forEach((c) => set.delete(c)) },
      addEventListener: (t, fn) => (ls[t] = ls[t] || []).push(fn),
      removeEventListener: (t, fn) => { ls[t] = (ls[t] || []).filter((f) => f !== fn); },
      fire: (t) => (ls[t] || []).slice().forEach((fn) => fn({ type: t })),
      _set: set,
    };
  }
  class Offcanvas {
    constructor(el) { this._element = el; this._isShown = el._set.has('show'); instances.set(el, this); }
    static getInstance(el) { return instances.get(el) || null; }
    hide() {
      if (!this._isShown) return;
      this._isShown = false;
      this._element.classList.add('hiding');
      b.sandbox.setTimeout(() => {
        try {
          this._element.classList.remove('show', 'hiding');
          this._element.fire('hidden.bs.offcanvas');
        } catch (err) {
          errors.push(String(err.message || err));
        }
      }, 300);
    }
    dispose() { instances.delete(this._element); this._element = null; this._isShown = null; }
  }
  return { Offcanvas, errors, instances, makeEl };
}

async function overlay() {
  const runs = {};
  for (const mode of ['hiding', 'still']) {
    const b = boot({ path: '/erp/dashboard' });
    const bs = fakeBootstrap(b);
    const el = bs.makeEl(['offcanvas', 'show']);
    const inst = new bs.Offcanvas(el);
    b.sandbox.bootstrap = { Offcanvas: bs.Offcanvas };
    b.setMainQuery((sel) => (sel.indexOf('offcanvas') !== -1 ? [el] : []));
    if (mode === 'hiding') inst.hide(); // 서랍 링크 누름 → erp-mobile-shell.js 의 offcanvas.hide()
    await b.shell.navigateByShell(ORIGIN + '/erp/shipment');
    const disposedAtSwap = !bs.instances.has(el);
    await b.advance(2000);
    runs[mode] = { disposedAtSwap, disposedLater: !bs.instances.has(el), errors: bs.errors, classes: Array.from(el._set) };
  }
  return runs;
}

(async function run() {
  const out = { marker: await marker(), stale: await stale(), seed: await seed(), dedupe: await dedupe(), prewarm: await prewarm(), drawerDefer: await drawerDefer(), yield: await yieldToUser(), overlay: await overlay() };
  process.stdout.write(JSON.stringify(out) + '\n');
})().catch((err) => {
  process.stderr.write(String((err && err.stack) || err) + '\n');
  process.exit(1);
});
