"""Cursor afterShellExecution 훅: push 관측 후 CI 게이트 마커 기록.

afterShellExecution 은 Cursor 에서 **관측(observational) 전용** 훅이라 에이전트에
메시지를 주입할 수 없다(agentMessage 등 출력 필드 미지원 — cursor.com/docs 기준).
따라서 여기서는 `git push`/`gh pr merge` 성공을 감지해 마커 파일만 기록하고,
실제 "[CI-GATE]" 리마인더 주입은 afterAgentResponse(post_task_quality_check.py)가
담당한다(주입 가능한 채널로 역할 분리).

payload(afterShellExecution): {"command": "...", "output": "...",
  "duration": <ms>, "sandbox": <bool>} + 공통 필드(workspace_roots 등).
실패는 fail-open + hook_runtime_log(묵시적 삼킴 금지).
"""
import json
import os
import re
import sys
import time


def _load_debug():
    """payload 디버그 헬퍼를 로드한다(실패 시 no-op 폴백)."""
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from hook_payload_debug import get_payload, maybe_log_payload

        return maybe_log_payload, get_payload
    except Exception:  # noqa: BLE001 - 디버그 헬퍼 부재는 치명적이지 않음
        return lambda *a, **k: None, lambda: {}


maybe_log_payload, get_payload = _load_debug()
from shared_utils import (  # noqa: E402
    extract_project_root,
    harness_runtime_path,
    hook_runtime_log,
)

MARKER_FILE = ".cursor_ci_gate_pending.json"

# push 거부/실패를 나타내는 출력 마커(하나라도 있으면 기록 안 함)
_FAIL_MARKERS = (
    "[rejected]",
    "! [remote rejected]",
    "failed to push",
    "fatal:",
    "protected branch",
    "authentication failed",
    "permission denied",
)


def _is_push_command(command: str) -> bool:
    """명령에 git push 또는 gh pr merge 흔적이 있으면 True."""
    lowered = (command or "").lower()
    return ("git push" in lowered) or ("pr merge" in lowered)


def _detect_branch(command: str) -> str:
    """명령에서 대상 브랜치를 추정한다(production/main/deploy)."""
    lowered = (command or "").lower()
    if "pr merge" in lowered:
        return "production"
    if re.search(r"\bproduction\b", lowered):
        return "production"
    if re.search(r"\bmain\b", lowered):
        return "main"
    return "deploy"


def _push_failed(output: str) -> bool:
    """출력에 push 실패 마커가 있으면 True."""
    text = (output or "").lower()
    return any(marker in text for marker in _FAIL_MARKERS)


def _write_marker(project_root: str, branch: str, command: str) -> None:
    """CI 게이트 마커 파일을 기록한다(afterAgentResponse 가 소비·삭제)."""
    path = harness_runtime_path(project_root, MARKER_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {"branch": branch, "ts": time.time(), "command": command[:200]},
            handle,
            ensure_ascii=False,
        )


def main() -> None:
    """afterShellExecution 진입점. push 성공 시 마커만 기록(관측 전용)."""
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}
    project_root = extract_project_root(payload)
    maybe_log_payload("afterShellExecution", payload, project_root)

    try:
        command = payload.get("command") or ""
        if _is_push_command(command) and not _push_failed(payload.get("output")):
            _write_marker(project_root, _detect_branch(command), command)
    except Exception as exc:  # noqa: BLE001 - fail-open + 기록
        hook_runtime_log(
            f"after_shell_execution fail-open: {type(exc).__name__}: {exc}",
            project_root=project_root,
            tag="ci_gate",
        )

    sys.stdout.write(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
