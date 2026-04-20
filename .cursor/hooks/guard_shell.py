import json
import os
import re
import sys
from datetime import datetime

def _load_debug():
    try:
        d = os.path.dirname(os.path.abspath(__file__))
        if d not in sys.path:
            sys.path.insert(0, d)
        from hook_payload_debug import maybe_log_payload, get_payload
        return maybe_log_payload, get_payload
    except Exception:
        return lambda *a, **k: None, lambda: {}
maybe_log_payload, get_payload = _load_debug()
from shared_utils import extract_project_root, find_key_recursive, harness_log_path

DANGEROUS_PATTERNS = [
    r"rm\s+(-rf|-fr)\s+[/\\]",
    r"rm\s+(-rf|-fr)\s+\.\.",
    r"drop\s+database",
    r"drop\s+table",
    r"truncate\s+table",
    r"delete\s+from\s+\w+\s*;?\s*$",
    r"format\s+[a-z]:",
    r"del\s+/s\s+/q\s+[a-z]:\\",
    r"git\s+push\s+.*--force\s+.*(main|master|deploy)",
    r"git\s+reset\s+--hard\s+origin",
    r"git\s+clean\s+-fdx?",
]

WARN_PATTERNS = [
    r"git\s+push\s+--force",
    r"git\s+reset\s+--hard",
    r"git\s+checkout\s+--",
    r"pip\s+install\s+(?!-r)",
    r"npm\s+install\s+-g",
    r"remove-item\s+.+-recurse.+-force",
]

def _sanitize_command(command: str) -> str:
    command = str(command).replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", command)

def _classify(command: str):
    lowered = command.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "deny", pattern
    for pattern in WARN_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            return "ask", pattern
    return "allow", ""


# 정상적인 git 명령: 로그 파일에 기록하지 않음 (git checkout/merge 시 로그 수정으로 인한 충돌 방지)
GIT_SKIP_LOG_SUBCOMMANDS = {
    "push", "merge", "checkout", "add", "commit", "status", "fetch", "pull",
    "stash", "restore", "branch", "log", "diff", "show", "rebase", "revert",
    "clone", "init", "remote", "config", "tag", "switch", "reset",
}


def _is_normal_git_command(raw_cmd: str, decision: str) -> bool:
    """allow 결정인 git 일반 명령이면 True (로그 제외 대상)."""
    if decision != "allow" or not raw_cmd:
        return False
    parts = raw_cmd.strip().split()
    if not parts or parts[0].lower() != "git":
        return False
    if len(parts) >= 2:
        sub = parts[1].lower()
        for skip in GIT_SKIP_LOG_SUBCOMMANDS:
            if sub == skip or skip.startswith(sub) or sub.startswith(skip):
                return True
    return False


def main():
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)

    maybe_log_payload("beforeShellExecution", payload, project_root)

    raw_cmd = find_key_recursive(payload, [
        "command", "commandText", "cmd", "shell_command", "shellCommand", "run_command", "runCommand",
        "input", "text", "execute", "commandLine", "script", "code", "executable", "run"
    ], default="")
    if isinstance(raw_cmd, list): raw_cmd = raw_cmd[0]
    if isinstance(raw_cmd, dict) and "command" in raw_cmd: raw_cmd = raw_cmd.get("command", "")
    if not raw_cmd and isinstance(payload.get("arguments"), list) and payload["arguments"]:
        raw_cmd = " ".join(str(a) for a in payload["arguments"])
    raw_cmd = _sanitize_command(str(raw_cmd))
    log_cmd = raw_cmd if raw_cmd else "(payload에 command 없음)"
    
    decision, pattern = _classify(raw_cmd)
    
    log_path = harness_log_path(project_root, "SHELL_GUARD_LOG.md")
    if not _is_normal_git_command(raw_cmd, decision):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = f"| {timestamp} | {decision} | `{pattern or '-'}` | `{log_cmd[:160]}` |"

        header_lines = [
            "# Shell Guard Log",
            "",
            "> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다.",
            "",
            "| Time | Decision | Pattern | Command |",
            "|------|----------|---------|---------|"
        ]

        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as stream:
                stream.write("\n".join(header_lines) + "\n")

        with open(log_path, "r", encoding="utf-8") as stream:
            existing_lines = stream.readlines()

        data_rows = [l for l in existing_lines if l.startswith("| 20")]
        data_rows.append(row + "\n")
        if len(data_rows) > 300:
            data_rows = data_rows[-300:]

        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write("\n".join(header_lines) + "\n")
            stream.writelines(data_rows)

    if decision == "deny":
        out = {
            "continue": False,
            "permission": "deny",
            "userMessage": f"[BLOCKED] 위험 명령 차단: {log_cmd[:100]}",
            "agentMessage": "보안 정책상 차단된 명령입니다. 필요 시 사용자 승인 기반 대체 절차로 진행하세요.",
        }
        sys.stdout.write(json.dumps(out))
        return

    if decision == "ask":
        out = {
            "continue": True,
            "permission": "ask",
            "userMessage": f"[WARNING] 주의 필요 명령: {log_cmd[:100]}",
            "agentMessage": "주의가 필요한 명령입니다. 실행 의도를 재확인하세요.",
        }
        sys.stdout.write(json.dumps(out))
        return

    sys.stdout.write(json.dumps({"continue": True, "permission": "allow"}))

if __name__ == "__main__":
    main()
