"""Nightly FOMS-cron runner — runs each cleanup step as its own process.

Railway builds the FOMS-cron service from the root ``Dockerfile``, and a Dockerfile
service's start command is exec'd **without a shell**. The old start command
``A && B && C`` therefore only ever ran ``A``: the two retention purges never started
(docs/specs/2026-09-29-nightly-cron-single-runner-spec.md). This runner needs no shell —
the start command is just ``python tools/cron/nightly.py``.

Steps are independent: a failing step does not stop the next one (they clean unrelated
tables, and each is batch-committed and advisory-locked, so the next night resumes).
Each step has a timeout because Railway skips the next scheduled run while a previous
one is still running — one hung step would otherwise stop every later night.

Exit 0 only when every step exited 0.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger("nightly")

REPO_ROOT = Path(__file__).resolve().parents[2]
STEP_TIMEOUT_SECONDS = 20 * 60
TIMEOUT_EXIT_CODE = 124
LAUNCH_ERROR_EXIT_CODE = 127


@dataclass(frozen=True)
class NightlyStep:
    """One nightly cleanup: a repo-relative script and its CLI arguments."""

    name: str
    script: str
    args: tuple[str, ...]


# ``--execute`` / ``--apply`` are part of the contract: without them each tool is a
# dry-run that "succeeds" every night while deleting nothing.
#
# 보류(2026-10-05 사용자 결정): 초안 표식 규칙 감시 ``tools/ops/check_draft_flag_invariant.py``
# (읽기만, 위반 시 exit 3)는 운영 숨은 초안 7건을 정리한 뒤에 ``cleanup_order_drafts`` 바로
# 다음 단계로 넣는다. 지금 넣으면 그 7건 때문에 매일 밤 실패로 울린다.
NIGHTLY_STEPS: tuple[NightlyStep, ...] = (
    NightlyStep("cleanup_order_drafts", "tools/cron/cleanup_order_drafts.py", ("--execute",)),
    NightlyStep(
        "purge_order_mutation_receipts",
        "tools/ops/purge_order_mutation_receipts.py",
        ("--retention-days", "7", "--batch-size", "1000", "--apply"),
    ),
    NightlyStep("purge_audit_logs", "tools/ops/purge_audit_logs.py", ("--apply",)),
)

Runner = Callable[..., subprocess.CompletedProcess]


def run_step(step: NightlyStep, runner: Runner = subprocess.run) -> int:
    """Run one step in a child process (inheriting stdout/stderr) and return its exit code."""
    command = [sys.executable, str(REPO_ROOT / step.script), *step.args]
    try:
        completed = runner(command, cwd=REPO_ROOT, timeout=STEP_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        logger.error("[nightly] step=%s timed out after %ds", step.name, STEP_TIMEOUT_SECONDS)
        return TIMEOUT_EXIT_CODE
    except OSError:
        logger.exception("[nightly] step=%s could not start", step.name)
        return LAUNCH_ERROR_EXIT_CODE
    return completed.returncode


def main(steps: Sequence[NightlyStep] = NIGHTLY_STEPS, runner: Runner = subprocess.run) -> int:
    """Run every step in order; one summary line per step, exit 1 if any step failed."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    failed: list[str] = []
    for step in steps:
        started = time.monotonic()
        code = run_step(step, runner)
        logger.info(
            "[nightly] step=%s rc=%d elapsed=%.1fs", step.name, code, time.monotonic() - started
        )
        if code != 0:
            failed.append(step.name)
    logger.info("[nightly] done steps=%d failed=%s", len(steps), ",".join(failed) or "none")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
