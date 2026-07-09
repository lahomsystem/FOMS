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
    prepend_session_block,
    read_stdin_json,
    write_stdout_json,
)


def _record_session(session_id: str) -> None:
    """SESSION_LOG.md 맨 위에 새 세션 블록을 삽입하고 최신 20블록만 유지한다.

    포맷·로테이션은 공용 유틸(`hook_log_utils.prepend_session_block`)에 위임한다.
    기존 `chunks[-20:]` 로테이션은 newest-first 구조에서 최신 세션을 버리는
    역전 버그가 있어 폐기했다.

    파라미터:
        session_id: 세션 식별자 앞 8자.
    반환: 없음.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prepend_session_block(harness_runtime_path("SESSION_LOG.md"), session_id, timestamp)


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
