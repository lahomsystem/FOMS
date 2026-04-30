"""Prompt-side harness auto-entry routing for Cursor hooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from task_classifier import TaskClassification, classify_payload


def route_prompt(payload: dict[str, Any], repo_root: Path) -> TaskClassification:
    """Classify a Cursor hook payload with the shared harness classifier."""
    return classify_payload(payload, repo_root)


def _implementation_command(classification: TaskClassification) -> str:
    plan_hint = classification.plan_hint or "<approved-plan-or-spec-path>"
    return (
        '`powershell -NoProfile -File "tools/harness/run_codex.ps1" '
        f'-Profile implement -Plan "{plan_hint}"`'
    )


def _review_command(classification: TaskClassification) -> str:
    target = classification.primary_path or "<target-file>"
    return (
        '`powershell -NoProfile -File "tools/harness/run_codex.ps1" '
        f'-Profile review -Target "{target}"`'
    )


def _qa_command(classification: TaskClassification) -> str:
    url = classification.url or "<http-url>"
    scenario = classification.scenario or "qa"
    return (
        '`powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" '
        f'-Url "{url}" -Scenario "{scenario}"`'
    )


def build_agent_message(classification: TaskClassification) -> str | None:
    """Return a short Cursor hook system message from the shared classification."""
    if classification.route_kind == "generic":
        return None

    lines = [
        "[SYSTEM] Harness auto-entry router",
        (
            "Shared classification: "
            f"route={classification.route_kind}, "
            f"level={classification.level}, "
            f"context={classification.context_mode}, "
            f"reason={classification.reason}."
        ),
        f"Codex bundle: `{classification.codex_bundle_path}`.",
        f"Cursor bundle: `{classification.cursor_bundle_path}`.",
        f"Claude bundle: `{classification.claude_bundle_path}`.",
    ]

    if classification.route_kind == "review":
        lines.extend(
            [
                "This prompt looks like a review request. Prefer the wrapper-first review path.",
                _review_command(classification),
            ]
        )
    elif classification.route_kind == "implement":
        lines.extend(
            [
                "This prompt looks like an implementation request. Prefer the wrapper-first implementation path.",
                "Because `run_codex.ps1 -Profile implement` requires an approved plan/spec, confirm or create that plan before coding.",
                _implementation_command(classification),
            ]
        )
        if classification.primary_path:
            lines.append(f"Scope hint: `{classification.primary_path}`.")
    elif classification.route_kind == "qa":
        lines.extend(
            [
                "This prompt looks like a QA request. Prefer the QA wrapper path.",
                _qa_command(classification),
            ]
        )

    if classification.needs_rpi:
        lines.append("RPI applies here: Research -> Plan -> Implement.")
    if classification.needs_user_direction and classification.user_direction_reason:
        lines.append(
            "Ask the user for direction before coding: "
            f"{classification.user_direction_reason}."
        )
    if classification.resource_hints:
        lines.append("Resource hints: " + ", ".join(classification.resource_hints) + ".")

    return "\n".join(lines)


def build_hook_output(payload: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Return the JSON-serializable hook output for Cursor."""
    classification = route_prompt(payload, repo_root)
    agent_message = build_agent_message(classification)
    output: dict[str, Any] = {"continue": True}
    if agent_message:
        output["agentMessage"] = agent_message
    return output
