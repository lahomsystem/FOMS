"""Claude Code PreToolUse 훅: Bash 명령 실행 전 위험 명령 차단.

stdin 으로 {"tool_name": "Bash", "tool_input": {"command": "..."}} 페이로드를 받아
공유 정책 모듈(tools/harness/guard_policy.py)의 classify_command 로 판정한다.

출력 스키마 (신 PreToolUse 계약):
  - deny  → hookSpecificOutput.permissionDecision="deny"  (실행 차단)
  - ask   → hookSpecificOutput.permissionDecision="ask"   (사용자 확인)
  - allow → 무출력 (통과)

레거시 top-level `decision` 키는 제거되었다(무확인 자동 승인 결함 제거).
ask/deny 판정은 docs/harness/logs/SHELL_GUARD_LOG.md 에 기록하며(공용 writer tools/harness/guard_log.py),
로그 실패는 shared_utils.hook_log 로 남긴다(묵시적 삼킴 금지).
"""
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
    write_stdout_json,
)

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


def _load_guard_log(project_root: str):
    """tools/harness 의 guard_log 모듈(공용 SHELL_GUARD_LOG writer)을 로드한다.

    파라미터:
        project_root: 저장소 루트 절대 경로.
    반환: guard_log 모듈.
    """
    harness_dir = os.path.join(project_root, "tools", "harness")
    if harness_dir not in sys.path:
        sys.path.insert(0, harness_dir)
    import guard_log  # type: ignore[import-not-found]

    return guard_log


def _log_command(project_root: str, decision: str, label: str, command: str) -> None:
    """ask/deny 판정을 SHELL_GUARD_LOG.md 에 1행 기록(공용 writer, 3,000행 캡 + 월별 보관).

    파라미터:
        project_root: 저장소 루트.
        decision: "ask" 또는 "deny".
        label: 판정 사유 요약.
        command: 정규화된 명령 문자열.
    반환: 없음. 파일 로그 실패 시 hook_log 로 사유를 남긴다.
    """
    try:
        guard_log = _load_guard_log(project_root)
        guard_log.append_guard_row(guard_log.resolve_log_dir(project_root), decision, label, command)
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

        project_root = get_project_root()
        session_id = find_key_recursive(
            payload,
            ["session_id", "sessionId", "conversation_id", "conversationId", "id"],
            default="unknown",
        )
        classify_command = _load_classifier(project_root)
        decision, label = classify_command(
            command, project_root=project_root, session_id=session_id
        )

        if decision == "allow":
            return

        normalized = " ".join(str(command).split())
        _log_command(project_root, decision, label, normalized)
        _emit(decision, label, normalized)
    except Exception as exc:  # noqa: BLE001 - 훅 크래시가 세션을 막지 않도록 fail-open
        hook_log(f"guard_shell 예외 fail-open: {exc}", tag="guard_shell")


if __name__ == "__main__":
    main()
