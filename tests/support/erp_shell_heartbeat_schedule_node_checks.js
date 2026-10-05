'use strict';
/*
 * erp-shell.js 하트비트 일정 시뮬레이션 — 경로마다 갱신 일정이 정확히 하나인지 센다.
 *
 * 브라우저 대신 가짜 창·가짜 시계로 erp-shell.js 를 그대로 실행한다. setInterval 콜백이
 * 불릴 때 "어느 일정인가"(240초=primary, 50초=fresh) 표식을 달고, 그 콜백이 건 setTimeout
 * 사슬(스태거)은 표식을 물려받는다. fetch 가 불리면 (경로, 표식)을 적는다.
 *
 * 출력: 화면 경로별 JSON 한 줄 — {current, perPath: {경로: {schedule: 횟수}}}.
 * 판정은 파이썬 테스트(tests/domains/test_erp_shell_heartbeat_schedule.py)가 한다.
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');
const SHELL_JS = fs.readFileSync(path.join(ROOT, 'static/js/runtime/erp-shell.js'), 'utf8');
const ORIGIN = 'https://foms.test';
const SIM_SECONDS = 3600;
const ACTIVITY_EVERY_MS = 30 * 1000;

async function simulate(currentPath) {
  let clock = 1700000000000;
  let seq = 0;
  let currentLabel = 'load';
  const timers = [];
  const calls = [];

  function addTimer(fn, delay, repeat) {
    const t = {
      id: ++seq,
      due: clock + Math.max(0, delay || 0),
      fn,
      repeat: repeat ? Math.max(1, delay || 0) : 0,
      // 반복 타이머는 주기로 일정 이름을 정하고, 1회 타이머는 건 쪽의 이름을 물려받는다.
      label: repeat ? (delay === 240000 ? 'primary' : delay === 50000 ? 'fresh' : 'interval:' + delay) : currentLabel,
      seq,
    };
    timers.push(t);
    return t.id;
  }

  const listeners = { document: {}, window: {} };
  function addListener(bucket) {
    return function (type, fn, opts) {
      (listeners[bucket][type] = listeners[bucket][type] || []).push({ fn, opts });
    };
  }

  class FakeDate extends Date {
    static now() {
      return clock;
    }
  }

  const document = {
    visibilityState: 'visible',
    addEventListener: addListener('document'),
    getElementById: function () {
      return null;
    },
    querySelector: function () {
      return null;
    },
  };

  function fakeFetch(url, init) {
    const u = new URL(url);
    const headers = (init && init.headers) || {};
    calls.push({ path: u.pathname, label: currentLabel, conditional: Boolean(headers['If-None-Match']) });
    const body = '<div>' + u.pathname + '</div>';
    const responseHeaders = {
      'x-foms-erp-fragment': '1',
      etag: '"' + u.pathname + '"',
    };
    if (headers['If-None-Match']) {
      return Promise.resolve({ status: 304, ok: false, headers: { get: () => null }, url: String(url) });
    }
    return Promise.resolve({
      status: 200,
      ok: true,
      url: String(url),
      headers: {
        get: function (name) {
          return responseHeaders[String(name).toLowerCase()] || null;
        },
      },
      text: function () {
        return Promise.resolve(body);
      },
    });
  }

  const sandbox = {
    document,
    console,
    URL,
    URLSearchParams,
    Promise,
    Date: FakeDate,
    fetch: fakeFetch,
    location: { href: ORIGIN + currentPath, origin: ORIGIN },
    history: { state: null, pushState() {}, replaceState() {} },
    addEventListener: addListener('window'),
    setTimeout: function (fn, delay) {
      return addTimer(fn, delay, false);
    },
    clearTimeout: function () {},
    setInterval: function (fn, delay) {
      return addTimer(fn, delay, true);
    },
    clearInterval: function () {},
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SHELL_JS, sandbox, { filename: 'erp-shell.js' });

  const activity = (listeners.document.pointerdown || []).filter(function (l) {
    return l.opts && typeof l.opts === 'object' && l.opts.passive === true;
  });
  if (activity.length !== 1) {
    throw new Error('activity listener not found: ' + activity.length);
  }

  async function drain() {
    for (let i = 0; i < 6; i += 1) {
      await new Promise(function (resolve) {
        setImmediate(resolve);
      });
    }
  }

  const end = clock + SIM_SECONDS * 1000;
  let nextActivity = clock + ACTIVITY_EVERY_MS;
  while (true) {
    timers.sort(function (a, b) {
      return a.due - b.due || a.seq - b.seq;
    });
    const t = timers[0];
    const nextDue = Math.min(t ? t.due : Infinity, nextActivity);
    if (nextDue > end) {
      break;
    }
    clock = nextDue;
    if (!t || nextActivity <= t.due) {
      currentLabel = 'activity';
      activity[0].fn({ type: 'pointerdown' });
      nextActivity += ACTIVITY_EVERY_MS;
      await drain();
      continue;
    }
    timers.shift();
    currentLabel = t.label;
    t.fn();
    if (t.repeat) {
      t.due += t.repeat;
      timers.push(t);
    }
    await drain();
  }

  const perPath = {};
  calls.forEach(function (c) {
    const row = (perPath[c.path] = perPath[c.path] || {});
    row[c.label] = (row[c.label] || 0) + 1;
  });
  return { current: currentPath, simSeconds: SIM_SECONDS, perPath };
}

(async function main() {
  const out = [];
  for (const current of ['/erp/production/dashboard', '/erp/shipment']) {
    out.push(await simulate(current));
  }
  process.stdout.write(JSON.stringify(out) + '\n');
})().catch(function (err) {
  process.stderr.write(String((err && err.stack) || err) + '\n');
  process.exit(1);
});
