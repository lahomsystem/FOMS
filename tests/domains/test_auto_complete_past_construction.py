"""매일 자동 완료 밤 단계 — DB 없는 순수 계약 (설계서 docs/specs/2026-11-23-daily-backlog-auto-complete_SPEC.md)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from tools.cron.nightly import NIGHTLY_STEPS

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "auto_complete_past_construction_pure", _ROOT / "tools/cron/auto_complete_past_construction.py")
auto = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(auto)


def test_actor_env_must_be_a_positive_id() -> None:
    assert auto.actor_from_env({}) is None
    assert auto.actor_from_env({auto.ACTOR_ENV: ""}) is None
    assert auto.actor_from_env({auto.ACTOR_ENV: "abc"}) is None
    assert auto.actor_from_env({auto.ACTOR_ENV: "0"}) is None
    assert auto.actor_from_env({auto.ACTOR_ENV: " 57 "}) == 57


def test_batch_name_is_per_day() -> None:
    assert auto.batch_name("2026-11-24") == "auto-2026-11-24"


def test_nightly_runs_auto_complete_last_with_apply() -> None:
    last = NIGHTLY_STEPS[-1]
    assert last.script == "tools/cron/auto_complete_past_construction.py"
    assert last.args == ("--apply",)


def test_core_completed_workflow_carries_batch() -> None:
    from datetime import datetime

    wf = auto.apply_one.__globals__["completed_workflow"]({"stage": "DRAWING"}, now=datetime(2026, 11, 24),
                                                           batch="auto-2026-11-24")
    assert wf["stage"] == "COMPLETED" and wf["stage_override"]["batch"] == "auto-2026-11-24"
