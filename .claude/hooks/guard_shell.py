"""Claude Code PreToolUse 훅: Bash 명령 실행 전 위험 명령 차단.

stdin 으로 {"tool_name": "Bash", "tool_input": {"command": "..."}} 페이로드를 받아
공유 정책 모듈(tools/harness/guard_policy.py)의 classify_command 로 판정한다.

출력 스키마 (신 PreToolUse 계약):
  - deny  → hookSpecificOutput.permissionDecision="deny"  (실행 차단)
  - ask   → hookSpecificOutput.permissionDecision="ask"   (사용자 확인)
  - allow → 무출력 (통과)

레거시 top-level `decision` 키는 제거되었다(무확인 자동 승인 결함 제거).
ask/deny 판정은 docs/harness/logs/SHELL_GUARD_LOG.md 에 기록하며,
로그 실패는 shared_utils.hook_log 로 남긴다(묵시적 삼킴 금지).
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    get_project_root,
    harness_log_path,
    hook_log,
    read_stdin_json,
    write_stdout_json,
)

_LOG_HEADER = [
    "# Shell Guard Log",
    "",
    "> Claude Code Hook(`PreToolUse:Bash`)가 자동 기록합니다. (ask/deny 판정만)",
    "",
    "| Time | Decision | Label | Command |",
    "|------|----------|-------|---------|",
]
_LOG_CAP = 300


def _load_classifier(project_root: str):
    """tools/harness 의 guard_policy.classify_command 를 로드한다.

    파라미터:
        project_root: 저장소 루트 절대 경로.
    반환: classify_command 콜러블.
    """
    harness_dir = os.path.join(project_root, "tools", "harness")
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)
    from guard_policy import classify_command  # type: ignore[import-not-found]

    return classify_command


def _log_command(decision: str, label: str, command: str) -> None:
    """ask/deny 판정을 SHELL_GUARD_LOG.md 에 1행 기록(300행 캡).

    파라미터:
        decision: "ask" 또는 "deny".
        label: 판정 사유 요약.
        command: 정규화된 명령 문자열.
    반환: 없음. 파일 로그 실패 시 hook_log 로 사유를 남긴다.
    """
    try:
        log_path = harness_log_path("SHELL_GUARD_LOG.md")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = f"| {timestamp} | {decision} | `{label or '-'}` | `{command[:160]}` |\n"

        data_rows: list[str] = []
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as handle:
                data_rows = [ln for ln in handle.readlines() if ln.startswith("| 20")]
        data_rows.append(row)
        if len(data_rows) > _LOG_CAP:
            data_rows = data_rows[-_LOG_CAP:]

        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(_LOG_HEADER) + "\n")
            handle.writelines(data_rows)
    except Exception as exc:  # noqa: BLE001 - fail-open, 단 반드시 기록
        hook_log(f"SHELL_GUARD_LOG 기록 실패: {exc}", tag="guard_shell")


def _emit(decision: str, label: str, command: str) -> None:
    """PreToolUse 신스키마로 판정 결과를 출력한다."""
    reason = f"[{'차단' if decision == 'deny' else '확인'}] {label}: {command[:100]}"
    write_stdout_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        }
    )


def main() -> None:
    """PreToolUse 훅 진입점. 실패는 fail-open(allow)하되 hook_log 로 기록."""
    try:
        payload = read_stdin_json()
        command = (payload.get("tool_input") or {}).get("command", "")
        if not command:
            return

        classify_command = _load_classifier(get_project_root())
        decision, label = classify_command(command)

        if decision == "allow":
            return

        normalized = " ".join(str(command).split())
        _log_command(decision, label, normalized)
        _emit(decision, label, normalized)
    except Exception as exc:  # noqa: BLE001 - 훅 크래시가 세션을 막지 않도록 fail-open
        hook_log(f"guard_shell 예외 fail-open: {exc}", tag="guard_shell")


if __name__ == "__main__":
    main()
