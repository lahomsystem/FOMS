"""Smoke tests for Cursor hooks and verify-result baseline contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = REPO_ROOT / ".cursor" / "hooks.json"


def _load_hooks_payload() -> dict[str, object]:
    """Return the parsed hooks.json document."""
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def _load_hook_commands() -> list[tuple[str, list[str]]]:
    """Return hook script paths plus argv tail from hooks.json."""
    payload = _load_hooks_payload()
    commands: list[tuple[str, list[str]]] = []
    for entries in payload["hooks"].values():
        for entry in entries:
            parts = entry["command"].split()
            assert parts[0] == "python"
            commands.append((parts[1], parts[2:]))
    return commands


def _hook_env(
    tmp_path: Path,
    *,
    conversation_id: str = "smokehook",
    prompt: str | None = None,
    attachments: list[dict[str, str]] | None = None,
) -> dict[str, str]:
    """Provide a minimal Cursor hook payload rooted in a temp workspace."""
    workspace_root = tmp_path.resolve()
    sample_file = workspace_root / "sample.txt"
    sample_file.write_text("hello", encoding="utf-8")

    payload = {
        "workspace_roots": [str(workspace_root)],
        "conversation_id": conversation_id,
        "status": "completed",
        "command": "git status",
        "file_path": str(sample_file),
        "edits": [{"new_string": "updated"}],
        "prompt": prompt or "status 알려줘",
        "attachments": attachments or [],
    }
    env = os.environ.copy()
    env["CURSOR_PAYLOAD"] = json.dumps(payload)
    return env


def _load_module(module_name: str, relative_path: str):
    """Load a Python module directly from a repo-relative path."""
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hooks_json_commands_reference_existing_scripts() -> None:
    """All registered hook commands should point to repo-local Python entrypoints."""
    commands = _load_hook_commands()
    assert commands

    for script_rel, _ in commands:
        script_path = REPO_ROOT / script_rel
        assert script_path.is_file(), f"Missing hook script: {script_rel}"


def test_hook_entrypoints_smoke_run_with_minimal_payload(tmp_path: Path) -> None:
    """Each hook entrypoint should execute without crashing on minimal payload."""
    for script_rel, extra_args in _load_hook_commands():
        completed = subprocess.run(
            [sys.executable, script_rel, *extra_args],
            cwd=REPO_ROOT,
            env=_hook_env(tmp_path, conversation_id=f"smoke-{Path(script_rel).stem}"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, (
            f"{script_rel} failed with code {completed.returncode}\n"
            f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def test_verify_result_app_ok_contract() -> None:
    """The verify-result baseline command should still emit APP_OK."""
    completed = subprocess.run(
        [sys.executable, "-c", 'import app; print("APP_OK")'],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "APP_OK" in completed.stdout


def test_post_task_quality_check_finds_nested_latest_spec(tmp_path: Path) -> None:
    """The hook should resolve the latest spec recursively, not only at the top level."""
    module = _load_module("post_task_quality_check", ".cursor/hooks/post_task_quality_check.py")

    nested_dir = tmp_path / "docs" / "specs" / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)
    root_dir = tmp_path / "docs" / "specs"
    root_dir.mkdir(parents=True, exist_ok=True)

    older_spec = root_dir / "2026-04-01_ROOT_SPEC.md"
    older_spec.write_text("# Root spec\n", encoding="utf-8")
    newer_spec = nested_dir / "2026-04-02_NESTED_SPEC.md"
    newer_spec.write_text("# Nested spec\n", encoding="utf-8")

    same_time = 1_700_000_000
    os.utime(older_spec, (same_time, same_time))
    os.utime(newer_spec, (same_time, same_time))

    assert module._latest_spec_name(str(tmp_path)) == "nested/2026-04-02_NESTED_SPEC.md"


def test_post_task_quality_check_message_uses_nested_spec_path(tmp_path: Path) -> None:
    """The reminder should show the correct docs/specs relative path for nested specs."""
    nested_dir = tmp_path / "docs" / "specs" / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "2026-04-02_NESTED_SPEC.md").write_text("# Nested spec\n", encoding="utf-8")

    runtime_dir = tmp_path / "docs" / "harness" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "EDIT_LOG.md").write_text(
        "- `tools/harness/run_codex.ps1` <- updated\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/post_task_quality_check.py"],
        cwd=REPO_ROOT,
        env=_hook_env(tmp_path, conversation_id="post-task-nested-spec"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "docs/specs/nested/2026-04-02_NESTED_SPEC.md" in payload["agentMessage"]


def test_session_start_message_mentions_harness_core_changes(tmp_path: Path) -> None:
    """The first-session RPI reminder should explicitly mention harness core changes."""
    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/session_start.py"],
        cwd=REPO_ROOT,
        env=_hook_env(tmp_path, conversation_id="sessionstart"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert "Hooks/Rules/Agents/Verification" in payload["agentMessage"]


def test_before_submit_prompt_hook_is_registered() -> None:
    """The repo should register a beforeSubmitPrompt hook for auto-entry routing."""
    hooks = _load_hooks_payload()["hooks"]
    assert "beforeSubmitPrompt" in hooks
    commands = hooks["beforeSubmitPrompt"]
    assert commands
    assert commands[0]["command"] == "python .cursor/hooks/before_submit_prompt.py"


def test_before_submit_prompt_routes_harness_implement_request(tmp_path: Path) -> None:
    """Harness/core implement prompts should receive wrapper-first routing guidance."""
    target_file = tmp_path / "tools" / "harness" / "run_codex.ps1"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# placeholder\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/before_submit_prompt.py"],
        cwd=REPO_ROOT,
        env=_hook_env(
            tmp_path,
            conversation_id="before-submit-implement",
            prompt="tools/harness/run_codex.ps1 자동 라우팅 구현해",
            attachments=[{"path": str(target_file)}],
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["continue"] is True
    assert "run_codex.ps1" in payload["agentMessage"]
    assert "-Profile implement" in payload["agentMessage"]
    assert "-Plan" in payload["agentMessage"]
    assert "RPI" in payload["agentMessage"]
    assert "Shared classification: route=implement, level=high" in payload["agentMessage"]
    assert "Ask the user for direction before coding" in payload["agentMessage"]


def test_before_submit_prompt_prefers_implement_over_url_hint(tmp_path: Path) -> None:
    """A URL should not override an explicit implementation request."""
    target_file = tmp_path / "tools" / "harness" / "run_codex.ps1"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# placeholder\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/before_submit_prompt.py"],
        cwd=REPO_ROOT,
        env=_hook_env(
            tmp_path,
            conversation_id="before-submit-implement-url",
            prompt="https://example.com 참고해서 tools/harness/run_codex.ps1 자동 라우팅 구현해",
            attachments=[{"path": str(target_file)}],
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["continue"] is True
    assert "run_codex.ps1" in payload["agentMessage"]
    assert "-Profile implement" in payload["agentMessage"]
    assert "run_gstack_qa.ps1" not in payload["agentMessage"]
    assert "Shared classification: route=implement" in payload["agentMessage"]


def test_before_submit_prompt_review_of_test_file_stays_review(tmp_path: Path) -> None:
    """Reviewing a test file should not be reclassified as QA."""
    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/before_submit_prompt.py"],
        cwd=REPO_ROOT,
        env=_hook_env(
            tmp_path,
            conversation_id="before-submit-review-test-file",
            prompt="tests/harness/test_hooks_smoke.py 리뷰해",
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["continue"] is True
    assert "-Profile review" in payload["agentMessage"]
    assert "run_gstack_qa.ps1" not in payload["agentMessage"]
    assert "Shared classification: route=review" in payload["agentMessage"]


def test_before_submit_prompt_test_file_path_without_qa_words_stays_generic(tmp_path: Path) -> None:
    """Mentioning a test file path alone should not trigger QA routing."""
    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/before_submit_prompt.py"],
        cwd=REPO_ROOT,
        env=_hook_env(
            tmp_path,
            conversation_id="before-submit-test-file-generic",
            prompt="tests/harness/test_hooks_smoke.py 열어줘",
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["continue"] is True
    assert "agentMessage" not in payload


def test_before_submit_prompt_skips_generic_prompt(tmp_path: Path) -> None:
    """General prompts should pass through without noisy auto-entry instructions."""
    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/before_submit_prompt.py"],
        cwd=REPO_ROOT,
        env=_hook_env(
            tmp_path,
            conversation_id="before-submit-generic",
            prompt="현재 상태 요약해줘",
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["continue"] is True
    assert "agentMessage" not in payload


def test_before_submit_prompt_routes_qa_request(tmp_path: Path) -> None:
    """QA prompts with a URL should receive the gstack QA wrapper route."""
    completed = subprocess.run(
        [sys.executable, ".cursor/hooks/before_submit_prompt.py"],
        cwd=REPO_ROOT,
        env=_hook_env(
            tmp_path,
            conversation_id="before-submit-qa",
            prompt="https://example.com 에서 erp smoke qa 돌려줘",
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["continue"] is True
    assert "run_gstack_qa.ps1" in payload["agentMessage"]
    assert "https://example.com" in payload["agentMessage"]
    assert "erp-smoke" in payload["agentMessage"]
    assert "Shared classification: route=qa, level=medium" in payload["agentMessage"]
