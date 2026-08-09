"""Claude Code SessionStart hook: SESSION_LOG 기록 + 상황 파악/RPI 안내 주입.

stdin으로 {"session_id": ..., "source": "startup"|"resume"|"clear"|"compact"|"fork", ...}
형태의 페이로드를 받아 SESSION_LOG.md에 세션 시작을 기록하고,
additionalContext로 AI_STATUS/RPI 안내를 주입한다. 실패해도 fail-open(exit 0).
"""
import os
import re
import sys
from datetime import datetime, timedelta

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


# EDIT_LOG 행: `| 2026-07-29 08:37:15 | `상대/경로.py` | Edit |`
_EDIT_ROW_RE = re.compile(
    r"^\|\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*`?([^`|]+?)`?\s*\|"
)
CONCURRENT_EDIT_WINDOW_MIN = 30
_NON_CODE_SUFFIXES = (".md", ".txt")


def _is_code_edit(rel_path: str) -> bool:
    """EDIT_LOG의 편집 경로가 코드 파일인지 판정한다.

    파라미터:
        rel_path: 저장소 상대 경로(`docs/...`, `app.py` 등).
    반환: 문서(.md/.txt, docs/ 하위)가 아니면 True.
    """
    normalized = rel_path.replace("\\", "/")
    if normalized.startswith("docs/"):
        return False
    return not normalized.lower().endswith(_NON_CODE_SUFFIXES)


def _concurrent_edit_window_min() -> int:
    """동시 편집 감지 윈도우(분)를 반환한다.

    env `FOMS_CONCURRENT_EDIT_WINDOW_MIN`이 있으면 그 값, 없거나 정수가 아니면
    기본값(30분) + hook_log.

    반환: 윈도우 분 단위 정수.
    """
    raw = os.environ.get("FOMS_CONCURRENT_EDIT_WINDOW_MIN")
    if raw is None:
        return CONCURRENT_EDIT_WINDOW_MIN
    try:
        return int(raw)
    except ValueError:
        hook_log(f"concurrent edit 윈도우 값 무시({raw!r})", tag="session_start")
        return CONCURRENT_EDIT_WINDOW_MIN


def _concurrent_edit_note(
    source: str,
    *,
    edit_log_path: str | None = None,
    now: datetime | None = None,
) -> str:
    """최근 윈도우 내 타 창 코드 편집이 있으면 격리 worktree 권고를 반환한다.

    새 세션(startup/clear) 기준 EDIT_LOG의 최근 편집은 전부 타 창의 것이다.
    compact/resume은 자기 세션 편집이 남아 있어 오탐이므로 건너뛴다.

    파라미터:
        source: SessionStart source 값.
        edit_log_path: EDIT_LOG 경로(None이면 하네스 runtime 경로). 테스트 주입용.
        now: 기준 시각(None이면 `datetime.now()`). 테스트 주입용.
    반환: 권고 문자열(앞에 개행 포함) 또는 빈 문자열.
    """
    if source not in ("startup", "clear"):
        return ""
    window_min = _concurrent_edit_window_min()
    path = edit_log_path or harness_runtime_path("EDIT_LOG.md")
    try:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            rows = handle.readlines()
    except OSError as exc:
        hook_log(f"concurrent edit 감지 실패(무시): {exc}", tag="session_start")
        return ""
    cutoff = (now or datetime.now()) - timedelta(minutes=window_min)
    recent = [rel for stamp, rel in _parse_edit_rows(rows) if stamp >= cutoff and _is_code_edit(rel)]
    if not recent:
        return ""
    names = list(dict.fromkeys(os.path.basename(rel) for rel in reversed(recent)))[:3]
    return (
        f"\n[CONCURRENT-EDIT] 최근 {window_min}분 내 타 창 코드 편집 "
        f"감지({len(recent)}건, 최근: {', '.join(names)}).\n"
        "이 세션에서 코드 편집이 겹칠 것 같으면 격리 worktree 사용 권장: "
        "`python tools/harness/session_worktree.py create`\n"
        "실행 후 안내된 c:/tmp/foms-s-* 폴더에서 에이전트를 새로 기동하라"
        "(재기동해야 push own 판정 적용).\n"
        "핫파일(tablet 계약테스트 2종·layout_head.html·foms-tablet-bundle.css) 작업은 "
        "공유 트리 유지."
    )


def _parse_edit_rows(rows: list[str]) -> list[tuple[datetime, str]]:
    """EDIT_LOG 행들에서 (시각, 상대경로) 쌍을 뽑는다. 깨진 행은 조용히 skip.

    파라미터:
        rows: EDIT_LOG 원본 행 리스트.
    반환: 파싱 성공한 (naive datetime, 경로) 목록(파일 순서 유지).
    """
    parsed: list[tuple[datetime, str]] = []
    for row in rows:
        match = _EDIT_ROW_RE.match(row.strip())
        if not match:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        parsed.append((stamp, match.group(2).strip()))
    return parsed


def _build_context(source: str) -> str:
    """SessionStart additionalContext 텍스트를 조립한다.

    정적 RPI/AI_STATUS 안내는 CLAUDE.md와 중복이라 제거했다(2026-08-03 하네스
    ablation). compact 재개 시점의 체크포인트 포인터만 조건부로 주입한다.

    파라미터:
        source: "startup"|"resume"|"clear"|"compact" 중 하나.
    반환: 주입할 안내 문자열(없으면 빈 문자열).
    """
    if source == "compact":
        return (
            "[SYSTEM] 컨텍스트 압축 후 재개입니다 — 먼저 "
            "docs/harness/runtime/COMPACT_CHECKPOINT.md를 읽어 직전 작업을 복원하세요."
        )
    return ""


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
                    "additionalContext": (
                        _build_context(source)
                        + _memory_gate_note()
                        + _concurrent_edit_note(source)
                    ),
                }
            }
        )
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"session_start fail-open: {type(exc).__name__}: {exc}", tag="session_start")
    sys.exit(0)


if __name__ == "__main__":
    main()
