"""Unit tests for the shared harness task classifier."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_TOOLS = REPO_ROOT / "tools" / "harness"
if str(HARNESS_TOOLS) not in sys.path:
    sys.path.insert(0, str(HARNESS_TOOLS))

from task_classifier import LEVEL_RANKS, classify_payload, classify_task  # noqa: E402


def test_daily_review_stays_low_and_daily() -> None:
    result = classify_task(
        repo_root=REPO_ROOT,
        profile="review",
        paths=["docs/AI_STATUS.md"],
        context_signal_path="docs/AI_STATUS.md",
    )

    assert result.route_kind == "review"
    assert result.level == "low"
    assert result.context_mode == "daily"
    assert result.codex_bundle_path == "docs/harness/bundles/HARNESS_BUNDLE_CODEX.md"


def test_harness_file_promotes_to_high_and_harness() -> None:
    result = classify_task(
        repo_root=REPO_ROOT,
        profile="review",
        paths=["tools/harness/build_context_bundle.py"],
        context_signal_path="tools/harness/build_context_bundle.py",
    )

    assert result.level == "high"
    assert result.context_mode == "harness"
    assert "harness core path" in result.auto_reason


def test_level_override_promotes_to_top() -> None:
    result = classify_task(
        repo_root=REPO_ROOT,
        profile="review",
        paths=["docs/AI_STATUS.md"],
        context_signal_path="docs/AI_STATUS.md",
        additional_prompt="[\ub808\ubca8=\ucd5c\uc0c1]",
    )

    assert result.level == "top"
    assert result.auto_level == "low"
    assert result.override_level == "top"
    assert result.override_source == "fixed tag"
    assert result.context_mode == "harness"


def test_harness_plan_implement_promotes_to_top() -> None:
    plan_path = "docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md"
    result = classify_task(
        repo_root=REPO_ROOT,
        profile="implement",
        paths=[plan_path],
        context_signal_path=plan_path,
        plan_path=plan_path,
    )

    assert result.level == "top"
    assert result.context_mode == "harness"
    assert result.plan_metadata.modified_file_count >= 4
    assert result.plan_metadata.step_count >= 4


def test_payload_classification_marks_harness_implementation_needing_direction() -> None:
    result = classify_payload(
        {
            "prompt": "tools/harness/run_codex.ps1 \uc790\ub3d9 \ub77c\uc6b0\ud305 \uad6c\ud604\ud574",
            "attachments": [{"path": str(REPO_ROOT / "tools" / "harness" / "run_codex.ps1")}],
        },
        REPO_ROOT,
    )

    assert result.route_kind == "implement"
    assert result.level == "high"
    assert result.needs_rpi is True
    assert result.needs_user_direction is True
    assert result.user_direction_reason == "harness/core implementation requires an approved plan/spec"


def test_korean_migration_prompt_promotes_to_high_or_top() -> None:
    """한글 마이그레이션/스키마/하네스 프롬프트는 low로 오분류되면 안 된다."""
    result = classify_payload(
        {"prompt": "alembic 마이그레이션으로 notification_events 스키마 변경하고 하네스 훅도 수정"},
        REPO_ROOT,
    )

    assert result.route_kind == "implement"
    assert LEVEL_RANKS[result.level] >= LEVEL_RANKS["high"]
    assert "wide structural scope" in result.reasons
    assert "harness keyword" in result.reasons


def test_korean_auth_prompt_promotes_to_high() -> None:
    """한글 인증/로그인/세션 프롬프트는 auth 신호로 상향돼야 한다."""
    result = classify_payload({"prompt": "로그인 세션 만료 버그 고쳐줘"}, REPO_ROOT)

    assert LEVEL_RANKS[result.level] >= LEVEL_RANKS["high"]
    assert "auth keywords" in result.reasons


def test_korean_typo_prompt_stays_low() -> None:
    """단순 오타 수정 한글 프롬프트는 계속 low여야 한다."""
    result = classify_payload({"prompt": "오타 수정"}, REPO_ROOT)

    assert result.level == "low"
    assert result.reason == "narrow non-core scope"


def test_cli_prompt_only_feeds_level_signals() -> None:
    """--prompt만 준 CLI 경로에서도 프롬프트 텍스트가 레벨 신호로 쓰여야 한다."""
    result = classify_task(
        repo_root=REPO_ROOT,
        profile="auto",
        prompt_text="alembic 마이그레이션으로 notification_events 스키마 변경",
    )

    assert LEVEL_RANKS[result.level] >= LEVEL_RANKS["high"]
    assert "wide structural scope" in result.reasons


def test_english_generic_prompt_stays_low() -> None:
    """키워드 없는 영어 프롬프트 분류는 기존과 동일하게 low."""
    result = classify_payload({"prompt": "current status summary please"}, REPO_ROOT)

    assert result.level == "low"
    assert result.reason == "narrow non-core scope"
