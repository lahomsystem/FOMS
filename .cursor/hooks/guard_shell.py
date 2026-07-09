"""Cursor beforeShellExecution 훅: 위험 명령 차단 (공유 정책 소비).

Claude 훅과 동일한 tools/harness/guard_policy.classify_command 로 판정하되,
Cursor 고유 출력 계약({continue, permission, userMessage, agentMessage})을 보존한다.
  - deny  → continue=False, permission="deny"
  - ask   → continue=True,  permission="ask"
  - allow → continue=True,  permission="allow"

ask/deny 판정만 docs/harness/logs/SHELL_GUARD_LOG.md 에 기록하며,
로그 실패는 shared_utils.hook_runtime_log 로 남긴다(묵시적 삼킴 금지).
"""
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
from shared_utils import (  # noqa: E402
    extract_project_root,
    find_key_recursive,
    harness_log_path,
    hook_runtime_log,
)

_LOG_HEADER = [
    "# Shell Guard Log",
    "",
    "> Cursor Hook(`beforeShellExecution`)가 자동 기록합니다. (ask/deny 판정만)",
    "",
    "| Time | Decision | Label | Command |",
    "|------|----------|-------|---------|",
]
_LOG_CAP = 300


def _sanitize_command(command: str) -> str:
    """개행/중복 공백을 단일 공백으로 정규화한다."""
    command = str(command).replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", command)


def _load_classifier(project_root: str):
    """tools/harness 의 guard_policy.classify_command 를 로드한다."""
    harness_dir = os.path.join(project_root, "tools", "harness")
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)
    from guard_policy import classify_command  # type: ignore[import-not-found]

    return classify_command


def _extract_command(payload: dict) -> str:
    """Cursor payload 에서 실행 명령 문자열을 추출한다."""
    raw_cmd = find_key_recursive(
        payload,
        [
            "command", "commandText", "cmd", "shell_command", "shellCommand",
            "run_command", "runCommand", "input", "text", "execute",
            "commandLine", "script", "code", "executable", "run",
        ],
        default="",
    )
    if isinstance(raw_cmd, list):
        raw_cmd = raw_cmd[0] if raw_cmd else ""
    if isinstance(raw_cmd, dict) and "command" in raw_cmd:
        raw_cmd = raw_cmd.get("command", "")
    if not raw_cmd and isinstance(payload.get("arguments"), list) and payload["arguments"]:
        raw_cmd = " ".join(str(a) for a in payload["arguments"])
    return _sanitize_command(str(raw_cmd))


def _log_command(project_root: str, decision: str, label: str, command: str) -> None:
    """ask/deny 판정을 SHELL_GUARD_LOG.md 에 1행 기록(300행 캡)."""
    try:
        log_path = harness_log_path(project_root, "SHELL_GUARD_LOG.md")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = f"| {timestamp} | {decision} | `{label or '-'}` | `{command[:160]}` |\n"

        data_rows: list[str] = []
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as stream:
                data_rows = [ln for ln in stream.readlines() if ln.startswith("| 20")]
        data_rows.append(row)
        if len(data_rows) > _LOG_CAP:
            data_rows = data_rows[-_LOG_CAP:]

        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write("\n".join(_LOG_HEADER) + "\n")
            stream.writelines(data_rows)
    except Exception as exc:  # noqa: BLE001 - fail-open, 단 반드시 기록
        hook_runtime_log(
            f"SHELL_GUARD_LOG 기록 실패: {exc}", project_root=project_root, tag="guard_shell"
        )


def main() -> None:
    """beforeShellExecution 훅 진입점. 실패는 fail-open(allow)하되 로그 기록."""
    payload = get_payload()
    if not isinstance(payload, dict):
        payload = {}

    project_root = extract_project_root(payload)
    maybe_log_payload("beforeShellExecution", payload, project_root)

    raw_cmd = _extract_command(payload)

    try:
        classify_command = _load_classifier(project_root)
        decision, label = classify_command(raw_cmd) if raw_cmd else ("allow", "")
    except Exception as exc:  # noqa: BLE001 - 정책 로드/판정 실패 시 fail-open
        hook_runtime_log(
            f"guard_policy 판정 실패 fail-open: {exc}", project_root=project_root, tag="guard_shell"
        )
        decision, label = "allow", ""

    if decision != "allow":
        _log_command(project_root, decision, label, raw_cmd)

    log_cmd = raw_cmd if raw_cmd else "(payload에 command 없음)"

    if decision == "deny":
        sys.stdout.write(
            json.dumps(
                {
                    "continue": False,
                    "permission": "deny",
                    "userMessage": f"[BLOCKED] {label}: {log_cmd[:100]}",
                    "agentMessage": "보안 정책상 차단된 명령입니다. 필요 시 사용자 승인 기반 대체 절차로 진행하세요.",
                }
            )
        )
        return

    if decision == "ask":
        sys.stdout.write(
            json.dumps(
                {
                    "continue": True,
                    "permission": "ask",
                    "userMessage": f"[WARNING] {label}: {log_cmd[:100]}",
                    "agentMessage": "주의가 필요한 명령입니다. 실행 의도를 재확인하세요.",
                }
            )
        )
        return

    sys.stdout.write(json.dumps({"continue": True, "permission": "allow"}))


if __name__ == "__main__":
    main()
