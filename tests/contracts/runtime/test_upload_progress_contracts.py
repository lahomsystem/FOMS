from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_upload_progress_mobile_safe_compression_contract() -> None:
    """Shared upload runtime keeps mobile compression bounded and fallback-safe."""
    node = shutil.which("node")
    assert node, "node must be on PATH for upload progress contract tests"
    script = ROOT / "tests/support/upload_progress_contract_node_checks.js"
    proc = subprocess.run(
        [node, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = proc.stdout + "\n" + proc.stderr
    if proc.returncode != 0:
        print(output, file=sys.stderr)
    assert proc.returncode == 0, output
