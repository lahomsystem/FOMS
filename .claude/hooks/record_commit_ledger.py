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


def process(payload: dict) -> None:
    """커밋 성공 시 ledger append. 무출력이 정상.

    파라미터:
        payload: PostToolUse(Bash) 훅 페이로드(stdin JSON 파싱 결과).
    반환: 없음. 실패는 fail-open + hook_log.
    """
    try:
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

        # 커밋은 `cd <워크트리> && git commit` 처럼 메인 밖에서 돈다 — 그 저장소의 HEAD 를
        # 적어야 한다(설계서 2026-11-02 push-guard-effective-repo F2). 해석 불가면 기록 안 함.
        repo_root = project_root
        try:
            from effective_repo import resolve_repo_root  # type: ignore[import-not-found]
            from guard_policy import git_command_dir  # type: ignore[import-not-found]
        except ImportError:  # 메인 체크아웃이 뒤처져 도우미가 없으면 예전처럼 메인 기준
            resolve_repo_root = None
        if resolve_repo_root is not None:
            payload_cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
            repo_root = resolve_repo_root(
                git_command_dir(command, "commit"),
                base=payload_cwd or project_root,
                reference_root=project_root,
            )
            if repo_root is None:
                hook_log("record_commit_ledger: 커밋 저장소 판정 불가 — 기록 생략", tag="commit_ledger")
                return
        record_head_commit(
            repo_root,
            session_id,
            command,
            _response_text(payload.get("tool_response")),
            main_root=project_root,
        )
    except Exception as exc:  # noqa: BLE001
        hook_log(
            f"record_commit_ledger fail-open: {type(exc).__name__}: {exc}",
            tag="commit_ledger",
        )


def main() -> None:
    """standalone 실행 진입점(stdin JSON 1회 읽어 process 호출)."""
    process(read_stdin_json())


if __name__ == "__main__":
    main()
