"""Claude Code PostToolUse hook: Edit/Write 후 변경 파일 추적.

stdin으로 {"tool_name": "Edit", "tool_input": {"file_path": "..."}, ...} 형태를 받음.
docs/harness/runtime/EDIT_LOG.md에 변경 파일 기록.
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import get_project_root, harness_runtime_path, read_stdin_json  # type: ignore[import-not-found]


# 메타 파일은 추적 제외
EXCLUDE_PREFIXES = ("docs/", ".claude/", ".cursor/", ".git/")


def _to_relative(file_path: str, project_root: str) -> str:
    """절대 경로를 프로젝트 상대 경로로 변환."""
    try:
        rel = os.path.relpath(file_path, project_root)
        return rel.replace("\\", "/")
    except ValueError:
        return file_path.replace("\\", "/")


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
