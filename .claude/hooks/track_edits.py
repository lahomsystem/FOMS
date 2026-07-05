"""Claude Code PostToolUse hook: Edit/Write 후 변경 파일 추적.

stdin으로 {"tool_name": "Edit", "tool_input": {"file_path": "..."}, ...} 형태를 받음.
docs/harness/runtime/EDIT_LOG.md에 변경 파일 기록.
추가로 `.py` 편집은 Stop 게이트용 pending 상태 파일에 기록한다.
"""
import json
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import get_project_root, harness_runtime_path, read_stdin_json  # type: ignore[import-not-found]


# 메타 파일은 추적 제외
EXCLUDE_PREFIXES = ("docs/", ".claude/", ".cursor/", ".git/")

# Stop 게이트가 소비하는 pending 상태 파일명
PENDING_VERIFY_FILE = ".claude_pending_verify.json"


def _to_relative(file_path: str, project_root: str) -> str:
    """절대 경로를 프로젝트 상대 경로로 변환."""
    try:
        rel = os.path.relpath(file_path, project_root)
        return rel.replace("\\", "/")
    except ValueError:
        return file_path.replace("\\", "/")


def _update_pending_verify(session_id: str, rel_path: str) -> None:
    """`.py` 편집을 Stop 게이트용 pending 상태 파일에 merge-append 한다.

    같은 session_id면 files 목록에 추가(중복 제거), 다른 session_id면 교체.

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


def main():
    payload = read_stdin_json()
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        return

    project_root = get_project_root()
    rel_path = _to_relative(file_path, project_root)

    # 메타 파일 제외
    for prefix in EXCLUDE_PREFIXES:
        if rel_path.startswith(prefix):
            return

    # .py 편집은 Stop 게이트용 pending 상태에 기록
    if rel_path.endswith(".py"):
        session_id = payload.get("session_id") or "unknown"
        _update_pending_verify(session_id, rel_path)

    log_path = harness_runtime_path("EDIT_LOG.md")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tool_name = payload.get("tool_name", "unknown")
    row = f"| {timestamp} | `{rel_path}` | {tool_name} |"

    header_lines = [
        "# Edit Log",
        "",
        "> Claude Code Hook(`PostToolUse:Edit|Write`)가 자동 기록합니다.",
        "",
        "| Time | File | Tool |",
        "|------|------|------|",
    ]

    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header_lines) + "\n")

    with open(log_path, "r", encoding="utf-8") as f:
        existing = f.readlines()

    data_rows = [l for l in existing if l.startswith("| 20")]

    # 중복 제거: 최근 5분 이내 동일 파일은 건너뜀
    last_entries = [r for r in data_rows[-10:] if rel_path in r]
    if last_entries:
        last_time_str = last_entries[-1].split("|")[1].strip()
        try:
            last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_time).total_seconds() < 300:
                return
        except Exception:
            pass

    data_rows.append(row + "\n")
    if len(data_rows) > 50:
        data_rows = data_rows[-50:]

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines) + "\n")
        f.writelines(data_rows)


if __name__ == "__main__":
    main()
