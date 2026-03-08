"""Claude Code PreToolUse hook: Bash 명령 실행 전 위험 명령 차단.

stdin으로 {"tool_name": "Bash", "tool_input": {"command": "..."}} 형태를 받음.
위험 명령이면 {"decision": "block", "reason": "..."} 출력.
"""
import json
import os
import re
import sys
from datetime import datetime

# 프로젝트 루트
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import read_stdin_json, get_project_root, write_stdout_json  # type: ignore[import-not-found]

DANGEROUS_PATTERNS = [
    (r"rm\s+(-rf|-fr)\s+[/\\]", "rm -rf /"),
    (r"rm\s+(-rf|-fr)\s+\.\.", "rm -rf .."),
    (r"drop\s+database", "drop database"),
    (r"drop\s+table", "drop table"),
    (r"truncate\s+table", "truncate table"),
    (r"delete\s+from\s+\w+\s*;?\s*$", "unqualified DELETE"),
    (r"format\s+[a-z]:", "format drive"),
    (r"del\s+/s\s+/q\s+[a-z]:\\", "del /s /q"),
    (r"git\s+push\s+.*--force\s+.*(main|master|deploy|production)", "force push to protected branch"),
    (r"git\s+reset\s+--hard\s+origin", "reset --hard origin"),
    (r"git\s+clean\s+-fdx?", "git clean -fd"),
]

WARN_PATTERNS = [
    (r"git\s+push\s+--force", "git push --force"),
    (r"git\s+reset\s+--hard", "git reset --hard"),
    (r"git\s+checkout\s+--\s+\.", "git checkout -- ."),
    (r"pip\s+install\s+(?!-r)", "pip install (not from requirements)"),
    (r"npm\s+install\s+-g", "npm install -g"),
    (r"remove-item\s+.+-recurse.+-force", "Remove-Item -Recurse -Force"),
]

# 일반적인 git 명령은 로그 제외
GIT_NORMAL_SUBCOMMANDS = {
    "push", "merge", "checkout", "add", "commit", "status", "fetch", "pull",
    "stash", "restore", "branch", "log", "diff", "show", "rebase", "revert",
    "clone", "init", "remote", "config", "tag", "switch", "reset",
}


def _classify(command: str):
    lowered = command.lower().strip()
    for pattern, label in DANGEROUS_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "block", label
    for pattern, label in WARN_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "warn", label
    return "allow", ""


def _is_normal_git(cmd: str, decision: str) -> bool:
    if decision != "allow" or not cmd:
        return False
    parts = cmd.strip().split()
    if not parts or parts[0].lower() != "git":
        return False
    if len(parts) >= 2 and parts[1].lower() in GIT_NORMAL_SUBCOMMANDS:
        return True
    return False


def _log_command(project_root: str, decision: str, pattern: str, command: str):
    log_path = os.path.join(project_root, "docs", "context", "SHELL_GUARD_LOG.md")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = f"| {timestamp} | {decision} | `{pattern or '-'}` | `{command[:160]}` |"

    header_lines = [
        "# Shell Guard Log",
        "",
        "> Claude Code Hook(`PreToolUse:Bash`)가 자동 기록합니다.",
        "",
        "| Time | Decision | Pattern | Command |",
        "|------|----------|---------|---------|",
    ]

    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header_lines) + "\n")

    with open(log_path, "r", encoding="utf-8") as f:
        existing = f.readlines()

    data_rows = [l for l in existing if l.startswith("| 20")]
    data_rows.append(row + "\n")
    if len(data_rows) > 300:
        data_rows = data_rows[-300:]

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header_lines) + "\n")
        f.writelines(data_rows)


def main():
    payload = read_stdin_json()
    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        return

    command_clean = re.sub(r"\s+", " ", command.replace("\r", " ").replace("\n", " ").strip())
    decision, pattern = _classify(command_clean)
    project_root = get_project_root()

    # 일반 git 명령이 아니면 로그 기록
    if not _is_normal_git(command_clean, decision):
        try:
            _log_command(project_root, decision, pattern, command_clean)
        except Exception:
            pass

    if decision == "block":
        write_stdout_json({
            "decision": "block",
            "reason": f"[BLOCKED] 위험 명령 차단 ({pattern}): {command_clean[:100]}"
        })
    elif decision == "warn":
        # 경고만 표시, 차단하지 않음 (Claude Code가 사용자에게 확인)
        write_stdout_json({
            "decision": "approve",
            "reason": f"[WARNING] 주의 필요 명령 ({pattern}): {command_clean[:100]}"
        })
    # allow인 경우 아무 출력 없음 = 통과


if __name__ == "__main__":
    main()
