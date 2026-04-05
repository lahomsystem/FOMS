"""Profile-level contracts for harness cost optimization."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _profile(name: str) -> dict:
    module_path = REPO_ROOT / "tools" / "harness" / "build_context_bundle.py"
    spec = importlib.util.spec_from_file_location("build_context_bundle", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_profile(REPO_ROOT / "tools" / "harness" / "profiles" / f"{name}.yaml")


def test_cursor_profile_uses_slim_daily_context() -> None:
    """Cursor daily bundle should not inline Claude-only or plan-heavy sources."""
    profile = _profile("cursor")
    assert profile["source_ids"] == [
        "agents_md",
        "rules_00_project_context",
        "rules_50_win11_shell",
        "workflow_verify_result",
    ]


def test_codex_profile_uses_slim_daily_context() -> None:
    """Codex baseline bundle should stay focused on portable policy plus verification."""
    profile = _profile("codex")
    assert profile["source_ids"] == [
        "agents_md",
        "rules_00_project_context",
        "rules_50_win11_shell",
        "workflow_verify_result",
    ]


def test_claude_profile_keeps_claude_rules_but_not_master_plan() -> None:
    """Claude bundle should keep Claude-specific rules but avoid always-on plan loading."""
    profile = _profile("claude")
    assert profile["source_ids"] == [
        "agents_md",
        "claude_md",
        "rules_00_project_context",
        "rules_50_win11_shell",
        "workflow_verify_result",
    ]


def test_cursor_harness_profile_adds_master_plan_only_when_requested() -> None:
    """Cursor harness bundle should extend daily context with the harness master plan."""
    profile = _profile("cursor-harness")
    assert profile["source_ids"] == [
        "agents_md",
        "rules_00_project_context",
        "rules_50_win11_shell",
        "workflow_verify_result",
        "plan_harness_engineering_master",
    ]


def test_codex_harness_profile_adds_master_plan_only_when_requested() -> None:
    """Codex harness bundle should extend daily context with the harness master plan."""
    profile = _profile("codex-harness")
    assert profile["source_ids"] == [
        "agents_md",
        "rules_00_project_context",
        "rules_50_win11_shell",
        "workflow_verify_result",
        "plan_harness_engineering_master",
    ]


def test_claude_harness_profile_keeps_claude_policy_and_master_plan() -> None:
    """Claude harness bundle should keep Claude policy and add the harness master plan."""
    profile = _profile("claude-harness")
    assert profile["source_ids"] == [
        "agents_md",
        "claude_md",
        "rules_00_project_context",
        "rules_50_win11_shell",
        "workflow_verify_result",
        "plan_harness_engineering_master",
    ]
