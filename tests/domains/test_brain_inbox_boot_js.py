"""'확인할 것' 화면 스크립트가 켜질 때 멈추지 않는다(node — 가짜 창 · 가짜 DOM).

2단계 배포에서 brain-inbox.js 가 ``root`` 를 정하기 전에 읽어(``root.getAttribute``) 스테이징 화면이 통째로 멈췄다 — node 구문
검사(``--check``)는 이것을 못 잡는다. 여기서는 실제로 한 번 돌려 본다: 읽는 차례 그대로 묶음 · 표 · 제안함 스크립트를 싣고,
켜짐 표시가 서는지 본다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [ROOT / f"static/js/brain/{name}"
           for name in ("brain-inbox-card.js", "brain-inbox-bins.js", "brain-inbox-table.js", "brain-inbox-question.js",
                        "brain-inbox.js")]
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")

BOOT = r"""
const vm = require('vm');
const fs = require('fs');
function stub() {
  return new Proxy(function () {}, {
    get(target, key) {
      if (key === 'hidden' || key === 'checked' || key === 'disabled') return false;
      if (key === 'getAttribute') return () => '1';
      if (key === Symbol.toPrimitive) return () => '';
      return stub();
    },
    set() { return true; },
    apply() { return stub(); },
  });
}
const root = stub();
const window = {
  FOMS_BRAIN_CTX: { root: root, display: {}, actions: [] },
  FOMS_BRAIN_DOM: stub(), FOMS_BRAIN_REVIEW: stub(), FOMS_BRAIN_VIEW: stub(),
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  performance: { now: () => 0 },
};
const context = vm.createContext({ window: window, console: console });
for (const file of JSON.parse(process.argv[1])) vm.runInContext(fs.readFileSync(file, 'utf8'), context, { filename: file });
process.stdout.write(JSON.stringify({ bound: !!window.__FOMS_BRAIN_INBOX_BOUND, bins: !!window.FOMS_BRAIN_INBOX_BINS,
                                      table: !!window.FOMS_BRAIN_INBOX_TABLE, card: !!window.FOMS_BRAIN_INBOX_CARD }));
"""


@NODE
def test_inbox_scripts_boot_without_errors_in_load_order():
    out = subprocess.run(["node", "-e", BOOT, json.dumps([str(p) for p in SCRIPTS])], capture_output=True, text=True,
                         encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    assert json.loads(out.stdout) == {"bound": True, "bins": True, "table": True, "card": True}
