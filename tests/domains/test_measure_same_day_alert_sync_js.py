"""당일 실측 확인창 재조회(foms-alert-sync.js) 동작 — node VM 으로 실제 실행해 고정한다.

왜: 소켓이 다시 붙은 순간은 "끊긴 사이 온 알림"을 되찾을 유일한 계기다. 페이지를 막 연
직후(30초 제한 안)에 재연결이 와도 재조회가 빠지면 그 알림은 다시 뜨지 않는다.
  - resync('page-load') 직후 resync('socket-connect') 는 fetch 를 한 번 더 부른다.
  - 그 밖의 계기(visible)는 30초 안에 두 번째 fetch 를 하지 않는다.
  - 서버가 대상 팀이 아니라고 내려주면(data-alert-sync-target="0") fetch 하지 않는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC_JS = ROOT / "static" / "js" / "foms" / "foms-alert-sync.js"
_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(_NODE is None, reason="node 미설치")

_HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const [src, target, reasonsJson] = process.argv.slice(1);
const code = fs.readFileSync(src, 'utf8');
const calls = [];
const listeners = {};
const document = {
  readyState: 'complete',
  visibilityState: 'visible',
  currentScript: { getAttribute: (n) => (n === 'data-alert-sync-target' ? target : null) },
  addEventListener: (n, fn) => { (listeners[n] = listeners[n] || []).push(fn); },
};
const store = {};
const window = {
  FOMSDrawingAlert: { handle: () => true, dismiss: () => true },
  sessionStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } },
};
const fetch = async (url) => { calls.push(url); return { json: async () => ({ success: true, data: { items: [] }, error: null }) }; };
const ctx = { window, document, fetch, console, Date, setTimeout, parseInt, isNaN, Math, String };
vm.createContext(ctx);
vm.runInContext(code, ctx);
(async () => {
  // 모듈 로드 때 page-load 1회가 이미 돌았다(readyState complete).
  await new Promise((r) => setTimeout(r, 0));
  for (const reason of JSON.parse(reasonsJson)) {
    await window.FOMSAlertSync.resync(reason);
  }
  process.stdout.write(JSON.stringify({ calls: calls.length }));
})();
"""


def _run(target: str, reasons: list[str]) -> int:
    proc = subprocess.run(
        [_NODE, "-e", _HARNESS, str(SYNC_JS), target, json.dumps(reasons)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return int(json.loads(proc.stdout)["calls"])


def test_socket_connect_right_after_page_load_still_fetches():
    assert _run("1", ["socket-connect"]) == 2


def test_other_reasons_respect_min_interval():
    assert _run("1", ["visible"]) == 1


def test_non_target_team_never_fetches():
    assert _run("0", ["socket-connect", "visible"]) == 0


def test_layout_scripts_passes_server_target_flag():
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    tag = next(line for line in scripts.splitlines() if "js/foms/foms-alert-sync.js" in line)
    assert "data-alert-sync-target=" in tag
