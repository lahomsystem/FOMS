"""Claude Code PostToolUse(Bash) 훅: push 성공 후 CI 감시 게이트 주입.

stdin 으로 {"tool_name": "Bash", "tool_input": {"command": "..."},
"tool_response": {...}} 를 받는다. `git push`(또는 `gh pr merge`)가 성공했다고
판단되면 hookSpecificOutput.additionalContext 로 "[CI-GATE] ..." 리마인더를
주입해, 에이전트가 tools/harness/ci_watch.py 로 CI green 을 확인하도록 강제한다.

성능: push 아닌 Bash 명령엔 문자열 검사만 하고 무출력한다(파일 I/O 없음).
push 실패(거부/error) 감지 시에도 주입하지 않는다(에이전트가 이미 에러를 본다).
실패는 fail-open + hook_log(묵시적 삼킴 금지).
"""
import os
import re
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    hook_log,
    read_stdin_json,
    write_stdout_json,
)

# push 거부/실패를 나타내는 출력 마커(하나라도 있으면 게이트 미주입)
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
    """명령에 git push 또는 gh pr merge 흔적이 있으면 True(빠른 문자열 검사)."""
    lowered = command.lower()
    return ("git push" in lowered) or ("pr merge" in lowered)


def _detect_branch(command: str) -> str:
    """명령에서 대상 브랜치를 추정한다(production/main/deploy)."""
    lowered = command.lower()
    if "pr merge" in lowered:
        return "production"
    if re.search(r"\bproduction\b", lowered):
        return "production"
    if re.search(r"\bmain\b", lowered):
        return "main"
    return "deploy"


def _response_text(tool_response) -> str:
    """tool_response(문자열/딕셔너리/리스트)에서 텍스트를 최대한 뽑아 합친다."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        parts: list[str] = []
        for key in ("stdout", "stderr", "output", "content", "result"):
            value = tool_response.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif isinstance(item, str):
                        parts.append(item)
        return "\n".join(parts)
    return ""


def _push_failed(tool_response) -> bool:
    """push 가 실패했다고 판단되면 True(에러 플래그 또는 실패 마커)."""
    if isinstance(tool_response, dict):
        if tool_response.get("is_error") or tool_response.get("isError"):
            return True
        if tool_response.get("interrupted"):
            return True
    text = _response_text(tool_response).lower()
    return any(marker in text for marker in _FAIL_MARKERS)


def _ci_gate_message(branch: str) -> str:
    """분기별 ci_watch 실행 안내를 담은 CI-GATE 리마인더 문자열을 만든다(논블로킹)."""
    command = (
        "python tools/harness/ci_watch.py"
        if branch == "deploy"
        else f"python tools/harness/ci_watch.py HEAD {branch}"
    )
    return (
        f"[CI-GATE] push 감지 ({branch}). CI 완료 확인은 블로킹 금지 — "
        f"run_in_background 로 `{command}`를 실행하거나 `{command} --quick`로 즉시 상태만 확인하고 "
        "작업을 계속하라(exit 0=green, 4=진행 중). "
        "exit 1이면 실패 로그를 분석해 근본 수정 후 pre_push_smoke→재푸시까지 완료해야 한다. "
        "이 게이트는 생략 금지."
    )


def main() -> None:
    """PostToolUse(Bash) 진입점. push 성공만 감지해 게이트를 주입한다(그 외 무출력)."""
    try:
        payload = read_stdin_json()
        command = (payload.get("tool_input") or {}).get("command", "") or ""
        if not command or not _is_push_command(command):
            return
        if _push_failed(payload.get("tool_response")):
            return
        branch = _detect_branch(command)
        write_stdout_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": _ci_gate_message(branch),
                }
            }
        )
    except Exception as exc:  # noqa: BLE001 - 훅 크래시가 세션을 막지 않도록 fail-open
        hook_log(f"post_push_watch fail-open: {type(exc).__name__}: {exc}", tag="post_push_watch")


if __name__ == "__main__":
    main()
