"""Web Push payload 계약(PUSH-01) — sender ↔ Service Worker 정합.

근본 결함(P1-5): ``push_sender._build_payload`` 는 ``notification_id``/``deep_link`` 를
``payload["data"]`` 에 **nested** 로 싣는데, ``static/sw.js`` 의 push 핸들러가 이를
top-level(``payload.notification_id``)로 읽어 항상 ``null`` 이 돼 클릭 라우팅/알림 식별이
깨졌다. 이 테스트는 계약을 nested 정본으로 고정한다:

- SW push 핸들러: nested ``payload.data.*`` 우선, 없으면 top-level(legacy) fallback.
- SW deep_link sanitize: same-origin ``/erp/`` 경로만 허용, 외부 origin·``//evil``·
  ``javascript:``·비-/erp 경로는 폴백(오픈 리다이렉트 차단).
- sender: nested ``data.{notification_id,deep_link}`` 계약 유지(top-level 로 새지 않음).
- ``node --check static/sw.js`` 파싱 OK.

정적 regex 로도 nested-read/fallback/sanitize 존재를 확인하되(노드 미설치 환경 대비),
핵심 파싱 동작은 node VM 으로 sw.js 를 실제 로드해 push 핸들러/sanitize 를 실행 검증한다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SW = ROOT / "static/sw.js"

_NODE = shutil.which("node")
_needs_node = pytest.mark.skipif(_NODE is None, reason="node 미설치 — 정적 assertion 만 수행")


# --- sender 계약: nested data.{notification_id, deep_link} --------------------


def test_push_sender_payload_nests_id_and_deep_link() -> None:
    """_build_payload 는 notification_id/deep_link 를 payload['data'] 에 nested 로 싣는다."""
    from foms.services.notifications.push_sender import _build_payload

    notif = SimpleNamespace(
        id=321, is_urgent=False, notification_type="ERP_ORDER_CHANGED", order_id=99
    )
    payload = _build_payload(notif)

    assert isinstance(payload.get("data"), dict)
    assert payload["data"]["notification_id"] == 321
    assert payload["data"]["deep_link"] == "/erp/drawing-workbench/99?tab=timeline"
    # 계약 정본은 nested — top-level 로 새면 안 된다(SW 파싱 계약과 정합).
    assert "notification_id" not in payload
    assert "deep_link" not in payload
    # deep_link 는 same-origin /erp 경로만.
    assert payload["data"]["deep_link"].startswith("/erp/")


# --- SW 정적 계약: nested-read + fallback + sanitize 존재 ----------------------


def test_sw_push_handler_reads_nested_data_with_toplevel_fallback() -> None:
    """sw.js push 핸들러가 payload.data.* 를 읽고 top-level fallback 을 갖는다(정적)."""
    sw = SW.read_text(encoding="utf-8")
    # nested 소스(payload.data) 를 참조한다.
    assert "payload.data" in sw
    # top-level fallback(구 발신본 호환) 도 존재한다.
    assert "payload.notification_id" in sw
    assert "payload.deep_link" in sw


def test_sw_deeplink_sanitize_same_origin_allowlist_present() -> None:
    """deep_link sanitize: same-origin + '/erp/' 허용, 외부/비-erp 폴백(정적)."""
    sw = SW.read_text(encoding="utf-8")
    assert "sanitizePushDeepLink" in sw
    assert 'indexOf("/erp/")' in sw
    assert "target.origin !== self.location.origin" in sw
    assert "/erp/dashboard" in sw  # 폴백 경로


# --- node --check: sw.js 파싱 OK ---------------------------------------------


@_needs_node
def test_sw_js_parses_with_node_check() -> None:
    """node --check static/sw.js 가 파싱 오류 없이 통과한다."""
    proc = subprocess.run(
        [_NODE, "--check", str(SW)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr


# --- node 동작 검증: sw.js 를 VM 로드 후 push 핸들러/sanitize 실행 --------------

# sw.js 를 격리 sandbox 에서 로드(top-level 은 var 선언 + addEventListener 등록뿐).
# push 핸들러를 다양한 payload 로 실행해 nested 우선/ fallback / precedence 를,
# sanitizePushDeepLink 를 직접 호출해 same-origin allowlist 를 검증한다.
_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const src = fs.readFileSync(process.env.FOMS_SW_PATH, 'utf8');

const handlers = {};
const shown = [];

const ctx = {
  self: {
    addEventListener: function (type, fn) { handlers[type] = fn; },
    location: { origin: 'https://foms.example.com' },
    registration: {
      showNotification: function (title, options) { shown.push(options); return Promise.resolve(); }
    },
    skipWaiting: function () {},
    clients: { claim: function () {} }
  },
  caches: { open: function(){return Promise.resolve({addAll:function(){return Promise.resolve();}});},
            keys: function(){return Promise.resolve([]);}, delete: function(){return Promise.resolve();},
            match: function(){return Promise.resolve();} },
  clients: { matchAll: function () { return Promise.resolve([]); },
             openWindow: function () { return Promise.resolve({}); } },
  fetch: function () { return Promise.resolve(); },
  URL: URL,
  Promise: Promise,
  setTimeout: setTimeout,
  console: { debug: function(){}, log: function(){}, error: function(){}, warn: function(){} }
};
vm.createContext(ctx);
vm.runInContext(src, ctx);

function firePush(payloadObj) {
  const before = shown.length;
  handlers.push({
    data: { json: function () { return payloadObj; }, text: function () { return ''; } },
    waitUntil: function () {}
  });
  return shown[shown.length - 1].data;
}

const nested = firePush({ title: 't', body: 'b', data: { notification_id: 42, deep_link: '/erp/orders/9' } });
const toplevel = firePush({ title: 't', body: 'b', notification_id: 7, deep_link: '/erp/x' });
const precedence = firePush({ notification_id: 1, deep_link: '/erp/top', data: { notification_id: 2, deep_link: '/erp/nested' } });

const san = ctx.sanitizePushDeepLink;
const result = {
  push_nested_id: nested.notification_id,
  push_nested_link: nested.deep_link,
  push_toplevel_id: toplevel.notification_id,
  push_toplevel_link: toplevel.deep_link,
  push_precedence_id: precedence.notification_id,
  push_precedence_link: precedence.deep_link,
  san_allow: san('/erp/orders/5'),
  san_external: san('https://evil.com/erp/x'),
  san_protorel: san('//evil.com/erp/x'),
  san_js: san('javascript:alert(1)'),
  san_nonerp: san('/admin/secret')
};
process.stdout.write(JSON.stringify(result));
"""


@_needs_node
def test_sw_push_parsing_behavior_via_node() -> None:
    """sw.js 를 실제 실행: push nested 우선 + top-level fallback + sanitize allowlist."""
    proc = subprocess.run(
        [_NODE, "-e", _HARNESS],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**_env(), "FOMS_SW_PATH": str(SW)},
    )
    assert proc.returncode == 0, proc.stderr
    r = json.loads(proc.stdout)

    # nested payload.data.* 를 읽는다.
    assert r["push_nested_id"] == 42
    assert r["push_nested_link"] == "/erp/orders/9"
    # nested 부재 시 top-level(legacy) fallback.
    assert r["push_toplevel_id"] == 7
    assert r["push_toplevel_link"] == "/erp/x"
    # nested 가 top-level 을 이긴다(정본 우선).
    assert r["push_precedence_id"] == 2
    assert r["push_precedence_link"] == "/erp/nested"

    # sanitize: same-origin /erp 허용, 그 외 폴백.
    assert r["san_allow"] == "/erp/orders/5"
    assert r["san_external"] == "/erp/dashboard"
    assert r["san_protorel"] == "/erp/dashboard"
    assert r["san_js"] == "/erp/dashboard"
    assert r["san_nonerp"] == "/erp/dashboard"


def _env() -> dict:
    import os

    return dict(os.environ)
