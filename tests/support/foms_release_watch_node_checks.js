'use strict';
/*
 * foms-release-watch.js 시뮬레이션 — 가짜 창 · 가짜 시계 · 가짜 fetch/XHR 로 "언제 새로 읽나"를 시나리오마다 잰다.
 * 결과는 JSON 한 덩어리(시나리오 → 숫자 · 이유)로 찍고 tests/domains/test_foms_release_watch_js.py 가 판정한다.
 * 환경 변수 FOMS_SIM_WATCH_JS 가 있으면 그 사본을 돌린다(음성 대조군).
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');
const SRC = fs.readFileSync(process.env.FOMS_SIM_WATCH_JS || path.join(ROOT, 'static/js/runtime/foms-release-watch.js'), 'utf8');
const SEC = 1000;
const MIN = 60 * SEC;

function makeStorage(broken) {
  const data = new Map();
  const fail = () => { throw new Error('SecurityError'); };
  return broken ? { getItem: fail, setItem: fail, removeItem: fail } : {
    data, getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => data.set(k, String(v)), removeItem: (k) => data.delete(k),
  };
}

function el(props) {
  return Object.assign({
    nodeType: 1, tagName: 'INPUT', type: 'text', value: '', defaultValue: '', isConnected: true, form: null, hiddenUp: false,
    rect: { width: 300, height: 200, left: 10, top: 10, right: 310, bottom: 210 }, style: { display: 'block', visibility: 'visible', opacity: '1' },
    closest() { return this.hiddenUp ? {} : null; }, getBoundingClientRect() { return this.rect; },
    getClientRects() { return this.rendered === false ? [] : [this.rect]; },
  }, props);
}

/* 겹층 셀렉터 판정 — attrs/classes 를 가진 가짜 요소만 실제 셀렉터 글로 견준다(태그 · .class · [attr] · [attr="v"] · :not(…)). */
function matchCompound(e, compound) {
  const nots = [];
  const body = compound.replace(/:not\(([^)]*)\)/g, (_, inner) => { nots.push(inner); return ''; }).trim();
  const tokens = body.match(/^[a-z]+|\.[\w-]+|\[[\w-]+(?:="[^"]*")?\]/g) || [];
  if (tokens.join('') !== body) throw new Error('가짜 셀렉터 판정이 모르는 꼴: ' + compound);
  const one = (t) => {
    if (t[0] === '.') return (e.classes || []).indexOf(t.slice(1)) !== -1;
    if (t[0] === '[') {
      const m = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(t);
      return Object.prototype.hasOwnProperty.call(e.attrs, m[1]) && (m[2] === undefined || e.attrs[m[1]] === m[2]);
    }
    return String(e.tagName).toLowerCase() === t;
  };
  return tokens.every(one) && !nots.some((n) => matchCompound(e, n));
}
const matchesSel = (e, sel) => sel.split(',').some((c) => matchCompound(e, c.trim()));

function FakeXHR() { this.ls = {}; }
FakeXHR.prototype.open = function (m) { this.method = m; };
FakeXHR.prototype.send = function () {};
FakeXHR.prototype.addEventListener = function (t, fn) { (this.ls[t] = this.ls[t] || []).push(fn); };
FakeXHR.prototype.removeEventListener = function (t, fn) { this.ls[t] = (this.ls[t] || []).filter((f) => f !== fn); };
FakeXHR.prototype.finish = function () { (this.ls.loadend || []).slice().forEach((fn) => fn({})); };

function boot(o) {
  const env = { clock: 1700000000000, timers: [], seq: 0, reloads: 0, calls: [], logs: [], held: [], overlays: o.overlays || [],
    busy: false, server: o.server || 'R2', fetchFails: false };
  const ls = { document: {}, window: {} };
  const on = (bag) => (t, fn) => (bag[t] = bag[t] || []).push(fn);
  const tag = { getAttribute: (n) => (n === 'data-foms-release' ? (o.page === undefined ? 'R1' : o.page) : null) };
  const body = { className: o.bodyClass || '', classList: { contains: (c) => (' ' + body.className + ' ').indexOf(' ' + c + ' ') !== -1 } };
  const document = {
    visibilityState: o.hidden ? 'hidden' : 'visible', currentScript: tag, documentElement: { className: '' }, body, activeElement: body,
    addEventListener: on(ls.document),
    querySelector: (s) => (s === 'script[data-foms-release]' ? tag : s === '[aria-busy="true"]' && env.busy ? {} : null),
    querySelectorAll: (s) => (s.indexOf('aria-modal') !== -1 ? env.overlays.filter((e) => !e.attrs || matchesSel(e, s)) : []),
  };
  const addTimer = (fn, ms) => { const id = ++env.seq; env.timers.push({ id, fn, due: env.clock + Math.max(0, ms || 0) }); return id; };
  const every = (fn, ms) => { const tick = () => addTimer(() => { tick(); fn(); }, ms); tick(); return 0; };
  function fakeFetch(url, init) {
    env.calls.push({ url: String(url), method: String((init && init.method) || 'GET').toUpperCase(), at: env.clock });
    if (String(url) !== '/api/foms/release') return new Promise((resolve) => env.held.push(() => resolve({ ok: true, status: 200 })));
    if (env.fetchFails) return Promise.reject(new Error('Failed to fetch'));
    const release = env.server;
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { release }, error: null }) });
  }
  class FakeDate extends Date { static now() { return env.clock; } }
  const log = (kind) => (...a) => env.logs.push(kind + ':' + a.map(String).join(' '));
  const win = {
    document, Date: FakeDate, console: { info: log('info'), warn: log('warn'), log: log('log') }, sessionStorage: o.storage || makeStorage(),
    fetch: fakeFetch, XMLHttpRequest: FakeXHR, navigator: { onLine: !o.offline }, location: { reload: () => { env.reloads += 1; } },
    performance: { getEntriesByType: () => (o.nav ? [o.nav] : []) }, innerWidth: 1176, innerHeight: 626,
    getComputedStyle: (e) => e.style, addEventListener: on(ls.window),
    setTimeout: addTimer, clearTimeout: (id) => { env.timers = env.timers.filter((t) => t.id !== id); }, setInterval: every,
  };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(SRC, win, { filename: 'foms-release-watch.js' });
  const drain = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setImmediate(r)); };
  async function advance(ms) { // 약속(fetch 응답)이 다 풀린 뒤에 다음 타이머 — 응답이 거는 0초 타이머도 같은 구간에서 돈다
    const end = env.clock + ms;
    for (;;) {
      await drain();
      env.timers.sort((a, b) => a.due - b.due || a.id - b.id);
      if (!env.timers.length || env.timers[0].due > end) break;
      const t = env.timers.shift();
      env.clock = Math.max(env.clock, t.due);
      t.fn();
    }
    env.clock = end;
  }
  const fire = async (where, type, ev) => { (ls[where][type] || []).slice().forEach((fn) => fn(ev || {})); await advance(1); };
  return {
    env, win, document, body, advance, fire,
    wake: async () => { document.visibilityState = 'visible'; await fire('document', 'visibilitychange'); },
    why: () => (win.FOMS_RELEASE_WATCH ? win.FOMS_RELEASE_WATCH.why() : 'unbound'),
    asks: () => env.calls.filter((c) => c.url === '/api/foms/release').length,
  };
}

async function run(o, body) {
  const t = boot(o);
  const out = await body(t);
  return Object.assign({ reloads: t.env.reloads, asks: t.asks() }, out || {});
}

const S = {};
S.idle_new_release = () => run({}, async (t) => { await t.wake(); return { guard: t.win.sessionStorage.getItem('foms_release_reload') }; });
S.same_release = () => run({ server: 'R1' }, async (t) => { await t.wake(); await t.advance(10 * MIN); });
S.passive_heartbeat = () => run({}, async (t) => { t.win.FOMS_RELEASE_WATCH.observe('R2'); await t.advance(1); });
S.passive_same_release = () => run({}, async (t) => { t.win.FOMS_RELEASE_WATCH.observe('R1'); await t.advance(1); });
S.no_page_release = () => run({ page: '' }, async (t) => { await t.wake(); return { bound: !!t.win.FOMS_RELEASE_WATCH }; });
S.focused_input = () => run({}, async (t) => {
  t.document.activeElement = el({});
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.document.activeElement = t.body;
  await t.advance(15 * SEC);
  return { before };
});
S.open_modal = () => run({ overlays: [el({ tagName: 'DIV' })] }, async (t) => {
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.env.overlays[0].hiddenUp = true; // 닫힘 = hidden
  await t.advance(15 * SEC);
  return { before };
});
S.offscreen_sheet_is_closed = () => run({ overlays: [el({ tagName: 'DIV', rect: { width: 300, height: 400, left: 0, top: 626, right: 300, bottom: 1026 } })] },
  async (t) => { await t.wake(); });
S.body_open_class = () => run({ bodyClass: 'foms-tower-sheet-open' }, async (t) => {
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.body.className = '';
  await t.advance(15 * SEC);
  return { before };
});
S.dirty_text = () => run({}, async (t) => {
  const field = el({ value: '메모 고침', defaultValue: '' });
  await t.fire('document', 'input', { target: field });
  await t.advance(31 * SEC); // 타자 활동은 따로 세지 않는다 — 고친 칸만으로 막혀야 한다
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  field.value = ''; // 되돌림
  await t.advance(15 * SEC);
  return { before };
});
S.dirty_field_removed = () => run({}, async (t) => {
  const field = el({ tagName: 'TEXTAREA', value: 'x' });
  await t.fire('document', 'input', { target: field });
  await t.wake();
  const before = t.env.reloads;
  field.isConnected = false; // 셸 스왑 · 창 닫힘으로 칸이 사라짐
  await t.advance(15 * SEC);
  return { before };
});
S.search_box_is_unsaved = () => run({}, async (t) => {
  const box = el({ type: 'search', value: '김' });
  await t.fire('document', 'input', { target: box });
  await t.advance(31 * SEC);
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  box.value = ''; // 비우면 막지 않는다
  await t.advance(15 * SEC);
  return { before };
});
S.untouched_search_box_does_not_block = () => run({}, async (t) => {
  t.document.activeElement = t.body; // 서버가 그린 찾을 말(defaultValue)은 그대로 — 고친 것이 아니다
  await t.fire('document', 'change', { target: el({ type: 'search', value: '박', defaultValue: '박' }) });
  await t.wake();
});
S.closed_overlay_search_does_not_block = () => run({}, async (t) => {
  await t.fire('document', 'input', { target: el({ type: 'search', value: '김', rendered: false }) }); // 닫힌 찾기 창 속 칸
  await t.wake();
});
const dialogEl = (attrs, classes) => el({ tagName: 'ASIDE', attrs, classes: classes || [] });
const SHEET = ['foms-tablet-sheet', 'is-open'];
S.docked_side_sheet_is_not_overlay = () => run({ overlays: [dialogEl({ role: 'dialog', 'aria-modal': 'false' }, SHEET.concat('foms-tablet-sheet--docked'))] },
  async (t) => { await t.wake(); return { why: t.why() }; });
S.undocked_open_side_sheet_blocks = () => run({ overlays: [dialogEl({ role: 'dialog', 'aria-modal': 'false' }, SHEET)] }, async (t) => {
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.env.overlays[0].classes = ['foms-tablet-sheet']; // 닫힘
  await t.advance(15 * SEC);
  return { before };
});
S.modal_dialog_role_blocks = () => run({ overlays: [dialogEl({ role: 'dialog', 'aria-modal': 'true' }), dialogEl({ role: 'alertdialog' })] },
  async (t) => {
    await t.wake();
    const before = { n: t.env.reloads, why: t.why() };
    t.env.overlays.forEach((o) => { o.hiddenUp = true; }); // 문서에 남아 있어도 숨으면(hidden) 열린 창이 아니다
    await t.advance(15 * SEC);
    return { before };
  });
S.instant_checkbox_is_not_unsaved = () => run({}, async (t) => {
  await t.fire('document', 'change', { target: el({ type: 'checkbox', checked: true, defaultChecked: false }) });
  await t.wake();
});
S.form_checkbox_is_unsaved = () => run({}, async (t) => {
  await t.fire('document', 'change', { target: el({ type: 'checkbox', checked: true, defaultChecked: false, form: {} }) });
  await t.wake();
  return { why: t.why() };
});
S.fetch_write_in_flight = () => run({}, async (t) => {
  t.win.fetch('/api/orders/1/step', { method: 'POST' });
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.env.held.splice(0).forEach((f) => f());
  await t.advance(15 * SEC);
  return { before };
});
S.xhr_upload_in_flight = () => run({}, async (t) => {
  const xhr = new t.win.XMLHttpRequest();
  xhr.open('PUT', 'https://bucket.r2.cloudflarestorage.com/x');
  xhr.send({});
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  xhr.finish();
  await t.advance(15 * SEC);
  return { before };
});
S.recent_touch = () => run({}, async (t) => {
  await t.fire('document', 'pointerdown');
  await t.wake();
  const at15 = (await t.advance(15 * SEC), t.env.reloads);
  await t.advance(15 * SEC);
  return { at15 };
});
S.busy_shell_nav = () => run({}, async (t) => {
  t.env.busy = true;
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.env.busy = false;
  await t.advance(15 * SEC);
  return { before };
});
S.printing = () => run({}, async (t) => {
  await t.fire('window', 'beforeprint');
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  await t.fire('window', 'afterprint');
  await t.advance(15 * SEC);
  return { before };
});
S.hidden_waits_for_wake = () => run({ hidden: true }, async (t) => {
  t.win.FOMS_RELEASE_WATCH.observe('R2');
  await t.advance(30 * MIN);
  const before = t.env.reloads;
  await t.wake();
  return { before };
});
S.offline_then_online = () => run({ offline: true }, async (t) => {
  await t.wake();
  const before = { n: t.env.reloads, asks: t.asks() };
  t.win.navigator.onLine = true;
  await t.fire('window', 'online');
  return { before };
});
S.check_fails_keeps_page = () => run({}, async (t) => {
  t.env.fetchFails = true;
  await t.wake();
  return { logged: t.env.logs.some((l) => l.indexOf('info:[foms-release-watch] 릴리스 확인 실패') === 0) };
});
S.stale_heard_rechecks = () => run({}, async (t) => {
  await t.fire('document', 'pointerdown');
  t.win.FOMS_RELEASE_WATCH.observe('R2'); // 하트비트로 들음 — 손대는 중이라 기다린다
  for (let i = 0; i < 8; i += 1) { await t.advance(15 * SEC); await t.fire('document', 'pointerdown'); }
  t.env.server = 'R1'; // 배포가 되돌려짐(또는 옛 컨테이너) — 새로 읽기 직전에 다시 물어 본다
  await t.advance(2 * MIN);
});
S.periodic_check_when_idle = () => run({}, async (t) => {
  await t.advance(4 * MIN + 59 * SEC);
  const before = t.asks();
  await t.advance(2 * MIN);
  return { before };
});
S.heartbeat_heard_skips_ask = () => run({ server: 'R1' }, async (t) => {
  await t.advance(4 * MIN);
  t.win.FOMS_RELEASE_WATCH.observe('R1');
  await t.advance(4 * MIN);
  const at8 = t.asks();
  await t.advance(2 * MIN);
  return { at8 };
});
S.served_from_cache = () => run({ nav: { type: 'back_forward', transferSize: 0, decodedBodySize: 900 } }, async (t) => { await t.advance(1); });
S.storage_broken = () => run({ storage: makeStorage(true) }, async (t) => {
  await t.wake();
  await t.advance(10 * MIN);
  return { warns: t.env.logs.filter((l) => l.indexOf('warn:') === 0).length };
});
S.guard_stops_loop = async () => {
  const storage = makeStorage();
  const first = await run({ storage }, async (t) => { await t.wake(); });
  // 새로 읽었는데 옛 컨테이너가 받았다(여전히 R1) — 5분 안에는 다시 읽지 않고, 5분 뒤 한 번 더.
  const second = await run({ storage }, async (t) => {
    await t.wake();
    const at4 = (await t.advance(4 * MIN), t.env.reloads);
    await t.advance(2 * MIN);
    return { at4 };
  });
  const third = await run({ storage }, async (t) => { await t.wake(); await t.advance(60 * MIN); });
  const landed = await run({ storage, page: 'R2', server: 'R3' }, async (t) => { await t.wake(); }); // 다음 배포는 또 받는다
  return { first: first.reloads, second, third: third.reloads, landed };
};
S.no_flapping_back = async () => {
  const storage = makeStorage();
  await run({ storage }, async (t) => { await t.wake(); }); // R1 → R2 로 떠남
  return run({ storage, page: 'R2', server: 'R1' }, async (t) => {
    await t.wake(); // 배포 중 옛 컨테이너가 R1 로 답한다 — 방금 떠난 릴리스라 좇지 않는다
    await t.advance(9 * MIN);
    const at9 = t.env.reloads;
    await t.advance(3 * MIN); // 10분 넘어서도 R1 이면 되돌리기 배포 — 따른다(10분 째 물음)
    return { at9 };
  });
};

(async () => {
  const out = {};
  for (const name of Object.keys(S)) out[name] = await S[name]();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
