"""야간 러너(``tools/cron/nightly.py``) 동작 계약.

cron startCommand 가 ``A && B && C`` 였을 때는 셸 없이 exec 되어 첫 명령만 돌았다. 러너는
단계를 **각각** 돌리고, 한 단계가 실패하거나 멈춰도 나머지를 돌며, 실패가 하나라도 있으면
exit 1 이다(docs/specs/2026-09-29-nightly-cron-single-runner-spec.md).
"""

from __future__ import annotations

import logging
import subprocess
import sys

from tools.cron import nightly
from tools.cron.nightly import NIGHTLY_STEPS, NightlyStep, main


class _FakeRunner:
    """Records each launched command and returns scripted outcomes per script name."""

    def __init__(self, outcomes: dict[str, object] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        outcome = self.outcomes.get(command[1].replace("\\", "/").split("/")[-1], 0)
        if isinstance(outcome, BaseException):
            raise outcome
        return subprocess.CompletedProcess(command, outcome)


def _scripts(runner: _FakeRunner) -> list[str]:
    return [cmd[1].replace("\\", "/").split("/")[-1] for cmd, _ in runner.calls]


def test_all_steps_run_in_order_with_their_arguments_and_exit_zero() -> None:
    runner = _FakeRunner()
    assert main(runner=runner) == 0
    assert _scripts(runner) == [step.script.split("/")[-1] for step in NIGHTLY_STEPS]
    for (command, kwargs), step in zip(runner.calls, NIGHTLY_STEPS):
        assert command[0] == sys.executable
        assert command[2:] == list(step.args)
        assert kwargs["cwd"] == nightly.REPO_ROOT
        assert kwargs["timeout"] == nightly.STEP_TIMEOUT_SECONDS


def test_failing_first_step_does_not_stop_the_purges(caplog) -> None:
    """The old ``&&`` chain skipped the purges when cleanup failed; the runner must not."""
    runner = _FakeRunner({"cleanup_order_drafts.py": 1})
    with caplog.at_level(logging.INFO, logger="nightly"):
        assert main(runner=runner) == 1
    assert len(runner.calls) == len(NIGHTLY_STEPS)
    assert "failed=cleanup_order_drafts" in caplog.text


def test_timed_out_step_is_reported_and_the_rest_still_run(caplog) -> None:
    timeout = subprocess.TimeoutExpired(cmd="x", timeout=nightly.STEP_TIMEOUT_SECONDS)
    runner = _FakeRunner({"purge_order_mutation_receipts.py": timeout})
    with caplog.at_level(logging.INFO, logger="nightly"):
        assert main(runner=runner) == 1
    assert len(runner.calls) == len(NIGHTLY_STEPS)
    assert f"rc={nightly.TIMEOUT_EXIT_CODE}" in caplog.text
    assert "failed=purge_order_mutation_receipts" in caplog.text


def test_every_step_logs_one_summary_line(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="nightly"):
        main(runner=_FakeRunner())
    summaries = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[nightly] step=")]
    assert len(summaries) == len(NIGHTLY_STEPS)
    assert "[nightly] done steps=3 failed=none" in caplog.text


def test_run_step_launches_a_real_child_and_returns_its_exit_code() -> None:
    """One real subprocess (no fake) so the launch path itself is exercised.

    The probe is the docstring-only package ``__init__`` — never a real cleanup step,
    which would touch whatever DATABASE_URL the test process has.
    """
    assert nightly.run_step(NightlyStep("probe", "tools/cron/__init__.py", ())) == 0
    missing = NightlyStep("missing", "tools/cron/does_not_exist.py", ())
    assert nightly.run_step(missing) != 0
