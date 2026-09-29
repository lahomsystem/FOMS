"""도면 탭 고객 보내기 JS(S2)를 Node 로 **실제 실행**하는 작은 틀.

문자열 존재 단언 대신, 파일 전체를 가짜 DOM·가짜 fetch 위에서 돌리고 "어떤 요청을 어떤 순서로
보냈나 · 버튼이 잠겼나 · 어디로 이동했나"를 본다(tests/services/integrations/test_naver_workbench_row_sync_js.py
와 같은 방식). 브라우저 없이 돈다 — 가짜 DOM 은 각 테스트가 쓰는 선택자만 등록한다.

쓰는 법: ``run_js(["static/js/foms/drawing-customer-send.js"], driver)`` — driver 는 async 함수 본문(JS)이고
마지막에 ``out({...})`` 로 결과를 돌려준다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

HARNESS = r"""
'use strict';
const calls = [];
const routes = [];
const alerts = [];
const toasts = [];
const modalOps = [];
const storageWrites = [];
function Resp(status, body) {
  return { ok: status >= 200 && status < 300, status: status, json: async function () { return body; } };
}
function route(match, fn) { routes.push({ match: match, fn: fn }); }
function record(url, opts) {
  opts = opts || {};
  let body = null;
  if (opts.body) { try { body = JSON.parse(opts.body); } catch (_) { body = opts.body; } }
  calls.push({ url: String(url), method: opts.method || 'GET', body: body, headers: opts.headers || {} });
}
async function fakeFetch(url, opts) {
  record(url, opts);
  for (const r of routes) {
    if (String(url).indexOf(r.match) !== -1) return r.fn(url, opts);
  }
  throw new Error('no route ' + url);
}
const docListeners = {};
const byId = {};
const globalSel = {};
function makeEl(opts) {
  opts = opts || {};
  const attrs = Object.assign({}, opts.attrs || {});
  const cls = new Set(opts.cls || []);
  const el = {
    id: opts.id || '', value: opts.value || '', checked: !!opts.checked, disabled: !!opts.disabled,
    textContent: opts.text || '', files: opts.files || [], type: '', className: '', htmlFor: '',
    children: [], _sel: {}, _all: {}, _closest: {}, _inside: [], _listeners: {},
    classList: {
      add: function (c) { cls.add(c); }, remove: function (c) { cls.delete(c); },
      contains: function (c) { return cls.has(c); },
      toggle: function (c, f) { const on = f === undefined ? !cls.has(c) : !!f; if (on) cls.add(c); else cls.delete(c); return on; },
    },
    getAttribute: function (n) { return Object.prototype.hasOwnProperty.call(attrs, n) ? attrs[n] : null; },
    setAttribute: function (n, v) { attrs[n] = String(v); },
    hasAttribute: function (n) { return Object.prototype.hasOwnProperty.call(attrs, n); },
    querySelector: function (s) { return el._sel[s] || null; },
    querySelectorAll: function (s) { return el._all[s] || []; },
    closest: function (s) { return el._closest[s] || null; },
    contains: function (o) { return o === el || el._inside.indexOf(o) !== -1; },
    addEventListener: function (t, fn) { (el._listeners[t] = el._listeners[t] || []).push(fn); },
    appendChild: function (c) { el.children.push(c); return c; },
    click: function () { fire('click', el); },
    getClientRects: function () { return opts.visible ? [1] : []; },
  };
  if (opts.id) byId[opts.id] = el;
  return el;
}
function fire(type, target, extra) {
  const ev = Object.assign({ type: type, target: target, defaultPrevented: false,
    preventDefault: function () { this.defaultPrevented = true; } }, extra || {});
  (docListeners[type] || []).slice().forEach(function (fn) { fn(ev); });
  (target && target._listeners && target._listeners[type] || []).slice().forEach(function (fn) { fn(ev); });
  return ev;
}
function hidden(el) { return el.classList.contains('d-none'); }
globalThis.window = globalThis;
globalThis.document = {
  readyState: 'complete',
  getElementById: function (id) { return byId[id] || null; },
  querySelector: function (s) { return globalSel[s] || null; },
  querySelectorAll: function () { return []; },
  addEventListener: function (t, fn) { (docListeners[t] = docListeners[t] || []).push(fn); },
  createElement: function () { return makeEl({}); },
};
Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'node-harness' }, configurable: true });
globalThis.fetch = fakeFetch;
window.location = { href: '', reloaded: 0, reload: function () { this.reloaded += 1; } };
window.alert = function (m) { alerts.push(String(m)); };
window.__confirmAnswer = true;
window.confirm = function (m) { alerts.push('CONFIRM:' + m); return window.__confirmAnswer; };
window.fomsShowToast = function (m) { toasts.push(String(m)); };
const store = { setItem: function (k, v) { storageWrites.push([k, v]); }, getItem: function () { return null; } };
Object.defineProperty(globalThis, 'localStorage', { value: store, configurable: true });
Object.defineProperty(globalThis, 'sessionStorage', { value: store, configurable: true });
window.bootstrap = { Modal: { getOrCreateInstance: function (el) {
  return {
    show: function () { modalOps.push(['show', el.id]); el.classList.add('show'); },
    hide: function () { modalOps.push(['hide', el.id]); el.classList.remove('show'); fire('hidden.bs.modal', el); },
  };
} } };
async function flush() { for (let i = 0; i < 40; i += 1) { await new Promise(function (r) { setImmediate(r); }); } }
function out(obj) {
  process.stdout.write(JSON.stringify(Object.assign({ calls: calls, alerts: alerts, toasts: toasts,
    modalOps: modalOps, storageWrites: storageWrites, href: window.location.href,
    reloaded: window.location.reloaded }, obj || {})));
}
"""


def node_or_skip() -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 가 PATH 에 없다 — JS 동작 테스트는 CI(node 있음)에서 돈다")
    return node


def run_js(sources: list[str], driver: str) -> dict:
    """HARNESS + 소스 파일들 + driver(async 본문)를 Node 로 돌려 ``out()`` 결과를 돌려준다.

    driver 안에서 ``loadSources()`` 를 불러 소스 파일(IIFE)을 싣는다.
    """
    node = node_or_skip()
    loader = "\n".join(
        "(0, eval)(" + json.dumps((ROOT / src).read_text(encoding="utf-8")) + ");" for src in sources
    )
    script = (
        HARNESS
        + "\nfunction loadSources() {\n" + loader + "\n}\n"
        + "(async function () {\n" + driver + "\n})().catch(function (e) { "
        + "process.stdout.write(JSON.stringify({__error: String(e && e.stack || e)})); });"
    )
    proc = subprocess.run(
        [node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    result = json.loads(proc.stdout or "{}")
    assert "__error" not in result, result.get("__error")
    return result

