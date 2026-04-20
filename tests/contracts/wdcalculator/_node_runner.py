"""Shared Node subprocess runner for WDCalculator contract checks."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def run_wdcalculator_node_check(support_script_relative: str) -> None:
    """Run `node` on a support script under repo root; fail with output on non-zero exit.

    Args:
        support_script_relative: Path relative to repo root, e.g.
            ``tests/support/wdcalculator_early_bootstrap_contract_node_checks.js``.
    """
    script = (_REPO_ROOT / support_script_relative).resolve()
    if not script.is_file():
        raise AssertionError(f"Missing support script: {script}")
    node = shutil.which("node")
    assert node, "node must be on PATH for WDCalculator chunk contract tests"
    proc = subprocess.run(
        [node, str(script)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout + "\n" + proc.stderr
    if proc.returncode != 0:
        print(out, file=sys.stderr)
    assert proc.returncode == 0, out
