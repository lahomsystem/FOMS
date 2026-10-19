"""마법사 4단계 '… 발송됨' 시각은 한국 시각이어야 한다(9시간 이른 표시 회귀 방지)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SEND_JS = ROOT / "static/js/foms/wizard-send.js"

_needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _extract_format_stamp() -> str:
    js = SEND_JS.read_text(encoding="utf-8")
    match = re.search(r"  function formatStamp\(value\) \{.*?\n  \}\n", js, re.S)
    assert match, "formatStamp 를 찾지 못했다"
    return match.group(0)


@_needs_node
def test_format_stamp_shows_kst() -> None:
    cases = {
        "2026-09-02T05:30:00": "2026-09-02 14:30",          # 시간대 없는 UTC(서버 저장값)
        "2026-09-02T05:30:00.123456": "2026-09-02 14:30",
        "2026-09-02 20:10:00": "2026-09-03 05:10",          # 날짜 넘김
        "2026-09-02T05:30:00.000Z": "2026-09-02 14:30",     # toISOString()
        "2026-09-02T14:30:00+09:00": "2026-09-02 14:30",    # 오프셋 있으면 그대로
        "": "",
    }
    script = (
        _extract_format_stamp()
        + f"var cases = {json.dumps(cases)}; var out = {{}};"
        + "Object.keys(cases).forEach(function (k) { out[k] = formatStamp(k); });"
        + "process.stdout.write(JSON.stringify(out));"
    )
    proc = subprocess.run([shutil.which("node"), "-e", script], capture_output=True, text=True,
                          encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == cases
