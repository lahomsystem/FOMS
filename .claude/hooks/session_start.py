"""Claude Code SessionStart hook: SESSION_LOG 기록 + 상황 파악/RPI 안내 주입.

stdin으로 {"session_id": ..., "source": "startup"|"resume"|"clear"|"compact"|"fork", ...}
형태의 페이로드를 받아 SESSION_LOG.md에 세션 시작을 기록하고,
additionalContext로 AI_STATUS/RPI 안내를 주입한다. 실패해도 fail-open(exit 0).
"""
import os
import sys
from datetime import datetime

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from ctx_gate import record_compact_baseline  # type: ignore[import-not-found]  # noqa: E402
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


# MEMORY.md 자동 로드 캡(첫 200줄)의 80% — 초과분은 조용히 잘리므로 선제 권고
MEMORY_GATE_LINES = 160
_MEMORY_INDEX_PATH = os.path.expanduser(
    "~/.claude/projects/C--DEV-FOMS/memory/MEMORY.md"
)


def _memory_gate_note() -> str:
    """MEMORY.md 인덱스가 로드 캡에 근접하면 정리 권고 1줄을 반환한다.

    자동 로드는 첫 200줄/25KB뿐이라 초과분은 에러 없이 잘린다(silent truncation).
    임계(기본 160줄, env FOMS_MEMORY_GATE_LINES) 초과 시 모델에게 가지치기 제안을
    지시한다. 파일 부재는 정상(신규 환경) — 빈 문자열. 그 외 실패는 로그 후 빈 문자열.

    반환: 권고 문자열 또는 빈 문자열.
    """
    try:
        if not os.path.exists(_MEMORY_INDEX_PATH):
            return ""
        limit = int(os.environ.get("FOMS_MEMORY_GATE_LINES", MEMORY_GATE_LINES))
        with open(_MEMORY_INDEX_PATH, "r", encoding="utf-8") as handle:
            count = sum(1 for _ in handle)
        if count > limit:
            return (
                f"\n[MEMORY-GATE] MEMORY.md {count}줄 — 자동 로드 캡(200줄) 근접, "
                "초과분은 조용히 잘린다. 낡은 항목 삭제·중복 통합 가지치기를 "
                "사용자에게 제안하라(지식 자산이므로 무단 삭제 금지)."
            )
    except (OSError, ValueError) as exc:
        hook_log(f"memory gate 실패(무시): {exc}", tag="session_start")
    return ""


def _build_context(source: str) -> str:
    """SessionStart additionalContext 텍스트를 조립한다.

    파라미터:
        source: "startup"|"resume"|"clear"|"compact" 중 하나.
    반환: 주입할 안내 문자열.
    """
    lines = [
        "[SYSTEM] 새 Claude Code 세션입니다.",
        "1. docs/AI_STATUS.md는 상단 40줄만 읽으세요(Read limit=40) — live 상태는 전부 상단에 있고, 아래는 상세 기록입니다(필요 시 grep).",
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
        full_session_id = str(payload.get("session_id") or "unknown")
        session_id = full_session_id[:8]
        source = str(payload.get("source") or "startup")
        _record_session(session_id)
        if source == "compact":
            # compact 후 transcript는 계속 자라므로 baseline을 여기서 굳힌다
            # (안 하면 ctx_gate가 영구 과대추정). id는 절단 없이 전체를 넘긴다.
            record_compact_baseline(full_session_id, str(payload.get("transcript_path") or ""))
        write_stdout_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": _build_context(source) + _memory_gate_note(),
                }
            }
        )
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"session_start fail-open: {type(exc).__name__}: {exc}", tag="session_start")
    sys.exit(0)


if __name__ == "__main__":
    main()
