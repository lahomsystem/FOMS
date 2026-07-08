"""Subprocess tests for `.claude/hooks/post_push_watch.py` (push → CI-GATE 주입).

훅을 실제 프로세스로 실행하고 stdin JSON → stdout JSON(additionalContext) 계약을
검증한다. push 아닌 명령은 무출력, 깨진 stdin 은 fail-open(exit 0).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = ".claude/hooks/post_push_watch.py"


def _run(payload_text: str) -> subprocess.CompletedProcess:
    """훅을 subprocess 로 실행하고 CompletedProcess 를 반환한다."""
    return subprocess.run(
        [sys.executable, HOOK],
        input=payload_text,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _run_payload(payload: dict) -> subprocess.CompletedProcess:
    return _run(json.dumps(payload))


def test_git_push_deploy_injects_ci_gate() -> None:
    proc = _run_payload(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin deploy"},
            "tool_response": {"stdout": "", "stderr": "To github.com\n   abc..def  deploy -> deploy"},
        }
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip())
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert data["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "[CI-GATE]" in ctx
    assert "deploy" in ctx
    assert "tools/harness/ci_watch.py" in ctx


def test_gh_pr_merge_targets_production() -> None:
    proc = _run_payload(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr merge 42 --merge"},
            "tool_response": {"stdout": "Merged pull request #42"},
        }
    )
    assert proc.returncode == 0, proc.stderr
    ctx = json.loads(proc.stdout.strip())["hookSpecificOutput"]["additionalContext"]
    assert "production" in ctx
    assert "HEAD production" in ctx  # production 은 명시 인자 안내


def test_non_push_command_emits_nothing() -> None:
    proc = _run_payload(
        {"tool_name": "Bash", "tool_input": {"command": "git status"}, "tool_response": {"stdout": ""}}
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


def test_failed_push_is_not_gated() -> None:
    proc = _run_payload(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git push origin deploy"},
            "tool_response": {
                "stderr": "! [rejected]        deploy -> deploy (fetch first)\nfailed to push some refs"
            },
        }
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ""


def test_broken_stdin_is_fail_open() -> None:
    proc = _run("{ this is not valid json ")
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_push_with_string_response_is_gated() -> None:
    """tool_response 가 문자열(성공 출력)이어도 push 를 감지한다."""
    proc = _run_payload(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git push"},
            "tool_response": "Everything up-to-date",
        }
    )
    assert proc.returncode == 0, proc.stderr
    ctx = json.loads(proc.stdout.strip())["hookSpecificOutput"]["additionalContext"]
    assert "[CI-GATE]" in ctx
