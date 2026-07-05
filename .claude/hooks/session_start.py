"""Claude Code SessionStart hook: SESSION_LOG 기록 + 상황 파악/RPI 안내 주입.

stdin으로 {"session_id": ..., "source": "startup"|"resume"|"clear"|"compact", ...}
형태의 페이로드를 받아 SESSION_LOG.md에 세션 시작을 기록하고,
additionalContext로 AI_STATUS/RPI 안내를 주입한다. 실패해도 fail-open(exit 0).
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    harness_runtime_path,
    hook_log,
    read_stdin_json,
    write_stdout_json,
)

SESSION_HEADER = (
    "# Session Log\n\n"
    "> 이 파일은 Claude Code Hooks에 의해 자동 관리됩니다.\n\n"
    "## 최근 세션\n\n"
)


def _record_session(session_id: str) -> None:
    """SESSION_LOG.md에 세션 시작 항목을 append하고 20개 초과분은 절단한다.

    파라미터:
        session_id: 세션 식별자 앞 8자.
    반환: 없음.
    """
    log_path = harness_runtime_path("SESSION_LOG.md")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    existing = ""
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as handle:
            existing = handle.read()
    sessions_part = existing.split("## 최근 세션\n\n")[-1] if "## 최근 세션" in existing else ""
    if sessions_part.count("### Session:") > 20:
        chunks = sessions_part.split("\n### Session:")
        sessions_part = "\n### Session:".join(chunks[-20:])
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_entry = (
        f"### Session: {session_id}\n"
        f"- **시작**: {timestamp}\n"
        f"- **상태**: 진행중\n"
        f"- **편집 파일**: (기록 중)\n"
        f"- **종료**: -\n\n"
    )
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(SESSION_HEADER + new_entry + sessions_part)


def _build_context(source: str) -> str:
    """SessionStart additionalContext 텍스트를 조립한다.

    파라미터:
        source: "startup"|"resume"|"clear"|"compact" 중 하나.
    반환: 주입할 안내 문자열.
    """
    lines = [
        "[SYSTEM] 새 Claude Code 세션입니다.",
        "1. docs/AI_STATUS.md를 읽어 현재 상황을 파악하세요.",
        "2. 핵심 코어 변경(DB/Auth/API/배포/하네스)이면 RPI(조사→계획→실행)를 따르세요.",
        "   - 조사: docs/harness/policy/DECISIONS.md, docs/ARCHIVE_INDEX.md에서 관련 기록 검색",
        "   - 계획: docs/guides/SPEC_TEMPLATE.md 기반 Spec 작성 → 사용자 승인 대기",
        "   - 실행: 승인 후 코딩 시작",
    ]
    if source == "compact":
        lines.append(
            "3. 컨텍스트 압축 후 재개입니다 — 먼저 "
            "docs/harness/runtime/COMPACT_CHECKPOINT.md를 읽어 직전 작업을 복원하세요."
        )
    return "\n".join(lines)


def main() -> None:
    """SessionStart 페이로드를 처리하고 additionalContext를 주입한다."""
    payload = read_stdin_json()
    try:
        session_id = str(payload.get("session_id") or "unknown")[:8]
        source = str(payload.get("source") or "startup")
        _record_session(session_id)
        write_stdout_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": _build_context(source),
                }
            }
        )
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"session_start fail-open: {type(exc).__name__}: {exc}", tag="session_start")
    sys.exit(0)


if __name__ == "__main__":
    main()
