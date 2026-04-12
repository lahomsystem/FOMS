"""Shell out to Node to verify static/js/wdcalculator/estimate-totals.js behavior."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_SCRIPT = REPO_ROOT / "tests" / "support" / "wdcalculator_estimate_totals_node_checks.js"


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_wdc_compute_aggregate_totals_node_checks() -> None:
    """Runs tests/support/wdcalculator_estimate_totals_node_checks.js under Node."""
    proc = subprocess.run(
        ["node", str(NODE_SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode != 0:
        print(out, file=sys.stderr)
    assert proc.returncode == 0, out
