"""PWA metadata must not reuse an old theme color from CacheStorage."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")

NODE_CHECK = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const handlers = {};
const oldManifest = JSON.stringify({theme_color:'#0070f2'});
const cache = {
  match: async () => new Response(oldManifest),
  put: async () => {},
};
const sandbox = {
  URL, Response, setTimeout, clearTimeout, AbortController, console,
  self: {
    location: {origin:'https://foms.example'},
    addEventListener: (name, handler) => {handlers[name] = handler;},
  },
  caches: {open: async () => cache},
  fetch: async () => new Response(JSON.stringify({theme_color:'#ffffff'})),
};
vm.runInNewContext(fs.readFileSync('static/sw.js','utf8'), sandbox);
async function dispatch(path) {
  let intercepted = false;
  let response;
  handlers.fetch({
    request: {method:'GET',url:'https://foms.example'+path},
    respondWith: value => {intercepted=true; response=value;},
    waitUntil: () => {},
  });
  return {intercepted, response:response ? await response : null};
}
(async () => {
  const path = process.argv[1];
  const result = await dispatch(path);
  assert.equal(result.intercepted,false,
    'manifest was intercepted by the SW and can return an old cached theme color');
  const asset = await dispatch('/static/js/foms/theme.js?v=1');
  assert.equal(asset.intercepted,true,'ordinary JS must retain its static cache policy');
  assert.equal(await asset.response.text(),oldManifest,'ordinary static cache changed');
  assert.ok(!sandbox.STATIC_URLS.some(url => /manifest.*\.json/.test(url)),
    'install must not precache app manifests');
})().catch(error => {console.error(error); process.exitCode=1;});
"""


@pytest.mark.skipif(NODE is None, reason="Node.js is required for service-worker execution")
@pytest.mark.parametrize("path", [
    "/static/manifest.json",
    "/static/manifest.json?v=20260902h",
    "/static/manifest-partner.json",
    "/static/manifest-partner.json?v=1",
])
def test_manifest_bypasses_stale_sw_cache_but_js_keeps_cache(path: str) -> None:
    """Execute the real SW with old metadata; only manifest requests pass through."""
    result = subprocess.run(
        [NODE, "-e", NODE_CHECK, path], cwd=ROOT, capture_output=True,
        text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
