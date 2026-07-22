"""Claude PostToolUse(Bash): 성공한 git commit 을 세션 레저에 기록."""
from __future__ import annotations

import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    find_key_recursive,
    get_project_root,
    hook_log,
    read_stdin_json,
)


def _response_text(tool_response) -> str:
    """tool_response 에서 텍스트 추출."""
    if isinstance(tool_response, str):
        return tool_response
    if isinstance(tool_response, dict):
        parts: list[str] = []
        for key in ("stdout", "stderr", "output", "content", "result"):
            value = tool_response.get(key)
            if isinstance(value, str):
                parts.append(value)
        return "\n".join(parts)
    return ""


def main() -> None:
    """커밋 성공 시 ledger append. 무출력이 정상."""
    try:
        payload = read_stdin_json()
        command = (payload.get("tool_input") or {}).get("command", "") or ""
        if "git commit" not in command.lower():
            return
        project_root = get_project_root()
        session_id = find_key_recursive(
            payload,
            ["session_id", "sessionId", "conversation_id", "conversationId", "id"],
            default="unknown",
        )
        harness = os.path.join(project_root, "tools", "harness")
        if harness not in sys.path:
            sys.path.insert(0, harness)
        from record_git_commit_ledger import record_head_commit  # type: ignore[import-not-found]

        record_head_commit(
            project_root,
            session_id,
            command,
            _response_text(payload.get("tool_response")),
        )
    except Exception as exc:  # noqa: BLE001
        hook_log(
            f"record_commit_ledger fail-open: {type(exc).__name__}: {exc}",
            tag="commit_ledger",
        )


if __name__ == "__main__":
    main()
