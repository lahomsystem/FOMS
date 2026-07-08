"""Claude Code PostToolUse hook: Edit/Write 후 변경 파일 추적.

stdin으로 {"tool_name": "Edit", "tool_input": {"file_path": "..."}, ...} 형태를 받음.
docs/harness/runtime/EDIT_LOG.md(테이블 포맷)에 변경 파일 기록.
추가로 `.py` 편집은 Stop 게이트용 pending 상태 파일에 기록한다.

트리밖 편집(전역 메모리·스크래치패드 등 `../../..` 경로)은 EDIT_LOG·pending
모두 스킵한다 — commonpath 기반 판정으로 startswith prefix 누수를 차단한다.
실패해도 fail-open 하되 사유를 CLAUDE_HOOK_LOG에 남긴다.
"""
import json
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    append_edit_row,
    get_project_root,
    harness_runtime_path,
    hook_log,
    is_within_tree,
    read_stdin_json,
)


# 트리 안 메타 파일은 추적 제외
EXCLUDE_PREFIXES = ("docs/", ".claude/", ".cursor/", ".git/")

# Stop 게이트가 소비하는 pending 상태 파일명
PENDING_VERIFY_FILE = ".claude_pending_verify.json"


def _to_relative(abs_path: str, project_root: str) -> str:
    """트리 안 절대 경로를 프로젝트 상대 경로(POSIX)로 변환."""
    try:
        rel = os.path.relpath(abs_path, project_root)
        return rel.replace("\\", "/")
    except ValueError:
        return abs_path.replace("\\", "/")


def _update_pending_verify(session_id: str, rel_path: str) -> None:
    """`.py` 편집을 Stop 게이트용 pending 상태 파일에 merge-append 한다.

    같은 session_id면 files 목록에 추가(중복 제거), 다른 session_id면 교체.
    스키마({session_id, files, updated})는 quality_check가 소비하므로 불변.

    Args:
        session_id: Stop 훅 payload의 session_id (없으면 "unknown").
        rel_path: 프로젝트 상대 경로 형태의 편집된 .py 파일.
    """
    pending_path = harness_runtime_path(PENDING_VERIFY_FILE)
    os.makedirs(os.path.dirname(pending_path), exist_ok=True)

    state = {"session_id": session_id, "files": []}
    if os.path.exists(pending_path):
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and loaded.get("session_id") == session_id:
                state = loaded
                state.setdefault("files", [])
        except (OSError, ValueError):
            state = {"session_id": session_id, "files": []}

    if rel_path not in state["files"]:
        state["files"].append(rel_path)
    state["session_id"] = session_id
    state["updated"] = datetime.now().isoformat(timespec="seconds")

    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _process(payload: dict) -> None:
    """편집 페이로드를 처리해 EDIT_LOG·pending을 갱신한다(트리밖은 스킵)."""
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    project_root = get_project_root()
    abs_path = file_path if os.path.isabs(file_path) else os.path.join(project_root, file_path)
    abs_path = os.path.abspath(abs_path)

    # 트리밖 편집(전역 메모리·스크래치패드 등)은 EDIT_LOG·pending 모두 스킵.
    if not is_within_tree(project_root, abs_path):
        hook_log(f"트리밖 편집 스킵: {file_path}", tag="track_edits")
        return

    rel_path = _to_relative(abs_path, project_root)

    # 트리 안 메타 파일 제외
    for prefix in EXCLUDE_PREFIXES:
        if rel_path.startswith(prefix):
            return

    # .py 편집은 Stop 게이트용 pending 상태에 기록
    if rel_path.endswith(".py"):
        session_id = payload.get("session_id") or "unknown"
        _update_pending_verify(session_id, rel_path)

    tool_name = payload.get("tool_name", "unknown")
    append_edit_row(harness_runtime_path("EDIT_LOG.md"), rel_path, tool_name)


def main() -> None:
    """PostToolUse 페이로드를 처리한다. 실패해도 fail-open."""
    payload = read_stdin_json()
    try:
        _process(payload)
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"track_edits fail-open: {type(exc).__name__}: {exc}", tag="track_edits")


if __name__ == "__main__":
    main()
