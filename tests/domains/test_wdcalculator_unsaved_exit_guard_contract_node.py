"""Shell out to Node to freeze WDCalculator unsaved-exit-guard contract."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NODE_SCRIPT = (
    REPO_ROOT
    / "tests"
    / "support"
    / "wdcalculator_unsaved_exit_guard_contract_node_checks.js"
)


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_wdcalculator_unsaved_exit_guard_contract_node_checks() -> None:
    """Runs tests/support/wdcalculator_unsaved_exit_guard_contract_node_checks.js under Node."""
    proc = subprocess.run(
        ["node", str(NODE_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode != 0:
        print(out, file=sys.stderr)
    assert proc.returncode == 0, out
