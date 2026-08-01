"""Claude Code PostToolUse hook: Edit/Write 후 변경 파일 추적 + 동시 세션 경고.

stdin으로 {"tool_name": "Edit", "tool_input": {"file_path": "..."}, ...} 형태를 받음.
docs/harness/runtime/EDIT_LOG.md(테이블 포맷)에 변경 파일 + 세션 태그를 기록.
추가로 `.py` 편집은 Stop 게이트용 pending 상태 파일에 기록한다.

기록 후 EDIT_LOG를 되읽어 **최근 윈도우 내 타 세션 코드 편집**이 있으면
additionalContext로 경고를 주입한다(디바운스: 새 상대 세션 등장 시 1회, 동일 파일
직접 충돌 시 파일당 1회). 반복 주입은 토큰 낭비라 상태 파일로 억제한다.

트리밖 편집(전역 메모리·스크래치패드 등 `../../..` 경로)은 EDIT_LOG·pending
모두 스킵한다 — commonpath 기반 판정으로 startswith prefix 누수를 차단한다.
실패해도 fail-open 하되 사유를 CLAUDE_HOOK_LOG에 남긴다.
"""
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    append_edit_row,
    get_project_root,
    harness_runtime_path,
    hook_log,
    is_within_tree,
    read_stdin_json,
    write_stdout_json,
)

_TOOLS_HARNESS = os.path.join(os.path.dirname(os.path.dirname(_dir)), "tools", "harness")
if _TOOLS_HARNESS not in sys.path:
    sys.path.append(_TOOLS_HARNESS)
from hook_log_utils import (  # type: ignore[import-not-found]  # noqa: E402
    CONCURRENT_EDIT_WINDOW_MIN,
    find_other_session_edits,
)


# 트리 안 메타 파일은 추적 제외
EXCLUDE_PREFIXES = ("docs/", ".claude/", ".cursor/", ".git/")

# Stop 게이트가 소비하는 pending 상태 파일명
PENDING_VERIFY_FILE = ".claude_pending_verify.json"

# 동시 편집 경고 디바운스 상태 파일 + 보관 세션 수 상한
CONCURRENT_STATE_FILE = "concurrent_notice_state.json"
CONCURRENT_STATE_MAX_SESSIONS = 20


def _to_relative(abs_path: str, project_root: str) -> str:
    """트리 안 절대 경로를 프로젝트 상대 경로(POSIX)로 변환."""
    try:
        rel = os.path.relpath(abs_path, project_root)
        return rel.replace("\\", "/")
    except ValueError:
        return abs_path.replace("\\", "/")


def _update_pending_verify(session_id: str, rel_path: str) -> None:
    """`.py` 편집을 Stop 게이트용 pending 상태 파일에 merge-append 한다.

    같은 session_id면 files 목록에 추가(중복 제거), 다른 session_id면 교체.
    스키마({session_id, files, updated})는 quality_check가 소비하므로 불변.

    Args:
        session_id: Stop 훅 payload의 session_id (없으면 "unknown").
        rel_path: 프로젝트 상대 경로 형태의 편집된 .py 파일.
    """
    pending_path = harness_runtime_path(PENDING_VERIFY_FILE)
    os.makedirs(os.path.dirname(pending_path), exist_ok=True)

    state = {"session_id": session_id, "files": []}
    if os.path.exists(pending_path):
        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and loaded.get("session_id") == session_id:
                state = loaded
                state.setdefault("files", [])
        except (OSError, ValueError):
            state = {"session_id": session_id, "files": []}

    if rel_path not in state["files"]:
        state["files"].append(rel_path)
    state["session_id"] = session_id
    state["updated"] = datetime.now().isoformat(timespec="seconds")

    with open(pending_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _session_tag(payload: dict) -> str:
    """payload 세션 식별자를 EDIT_LOG Session 컬럼 값(앞 8자)으로 만든다.

    Args:
        payload: PostToolUse 페이로드.
    Returns:
        세션 앞 8자, 미상이면 "-"(미상은 타 세션으로 세지 않는다).
    """
    sid = str(payload.get("session_id") or "").strip()
    return sid[:8] if sid and sid != "unknown" else "-"


def _window_min() -> int:
    """동시 편집 감지 윈도우(분). env `FOMS_CONCURRENT_EDIT_WINDOW_MIN` 우선."""
    raw = os.environ.get("FOMS_CONCURRENT_EDIT_WINDOW_MIN")
    if raw is None:
        return CONCURRENT_EDIT_WINDOW_MIN
    try:
        return int(raw)
    except ValueError:
        hook_log(f"concurrent edit 윈도우 값 무시({raw!r})", tag="track_edits")
        return CONCURRENT_EDIT_WINDOW_MIN


def _load_notice_state(path: str) -> Dict[str, dict]:
    """디바운스 상태를 읽는다(없거나 깨졌으면 빈 dict — fail-open)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError) as exc:
        hook_log(f"동시편집 상태 읽기 실패(초기화): {exc}", tag="track_edits")
        return {}


def _save_notice_state(path: str, state: Dict[str, dict], own_session: str) -> None:
    """디바운스 상태를 저장한다(자기 세션을 맨 뒤로 + 세션 키 20개 캡).

    여러 세션이 동시에 쓰면 last-write-wins다. 최악의 결과는 경고 1회 중복 주입이며
    이 경고는 advisory이므로 락 없이 단순 쓰기로 수용한다(파일 잠금 = 훅 지연).

    Args:
        path: 상태 파일 경로.
        state: {세션8자: {"warned_sessions": [...], "warned_files": [...]}}.
        own_session: 이번에 갱신한 세션 태그(insertion order 상 최신으로 이동).
    """
    entry = state.pop(own_session, {})
    state[own_session] = entry
    while len(state) > CONCURRENT_STATE_MAX_SESSIONS:
        state.pop(next(iter(state)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def _live_message(others: List[Tuple[str, str]], new_sessions: set, window_min: int) -> str:
    """새 타 세션 등장 경고 문구를 만든다(파일 예시 최대 3개)."""
    names = list(dict.fromkeys(os.path.basename(rel) for _, rel in reversed(others)))[:3]
    return (
        f"[CONCURRENT-EDIT-LIVE] 타 세션 {', '.join(sorted(new_sessions))}이(가) 최근 "
        f"{window_min}분 내 코드 편집 중(예: {', '.join(names)}). "
        "편집 영역이 겹칠 것 같으면 격리 worktree 권장: "
        "python tools/harness/session_worktree.py create "
        "(이 안내는 세션당 새 상대 등장 시 1회만 표시된다)"
    )


def _collision_message(rel_path: str, other_session: str, window_min: int) -> str:
    """동일 파일 직접 충돌 경고 문구를 만든다."""
    return (
        f"[CONCURRENT-EDIT-COLLISION] '{rel_path}'를 타 세션 {other_session}도 최근 "
        f"{window_min}분 내 편집함 — 덮어쓰기 위험. git diff로 상대 변경 확인 후 진행하라."
    )


def concurrent_edit_notice(
    rel_path: str,
    own_session: str,
    *,
    edit_log_path: str,
    state_path: str,
    window_min: int,
    now: Optional[datetime] = None,
) -> str:
    """타 세션 동시 편집 경고 문구를 만들고 디바운스 상태를 갱신한다.

    Args:
        rel_path: 방금 이 세션이 편집한 상대 경로(충돌 판정 대상).
        own_session: 자기 세션 태그(앞 8자, "-"면 감지 생략).
        edit_log_path: EDIT_LOG 경로. 테스트 주입용.
        state_path: 디바운스 상태 파일 경로. 테스트 주입용.
        window_min: 감지 윈도우(분).
        now: 기준 시각(None이면 현재 시각). 테스트 주입용.
    Returns:
        주입할 경고 문구(경고 없거나 이미 안내했으면 빈 문자열).
    """
    if own_session in ("", "-", "unknown") or not os.path.exists(edit_log_path):
        return ""
    with open(edit_log_path, "r", encoding="utf-8") as handle:
        rows = handle.readlines()
    others = find_other_session_edits(rows, own_session, window_min, now or datetime.now())
    if not others:
        return ""

    state = _load_notice_state(state_path)
    mine = state.get(own_session) or {}
    warned_sessions = set(mine.get("warned_sessions") or [])
    warned_files = set(mine.get("warned_files") or [])

    parts: List[str] = []
    new_sessions = {sid for sid, _ in others} - warned_sessions
    if new_sessions:
        parts.append(_live_message(others, new_sessions, window_min))
    collide = next((sid for sid, rel in others if rel == rel_path), None)
    if collide and rel_path not in warned_files:
        parts.append(_collision_message(rel_path, collide, window_min))
        warned_files.add(rel_path)
    if not parts:
        return ""

    mine["warned_sessions"] = sorted(warned_sessions | new_sessions)
    mine["warned_files"] = sorted(warned_files)
    state[own_session] = mine
    _save_notice_state(state_path, state, own_session)
    return "\n".join(parts)


def _emit_concurrent_notice(rel_path: str, own_session: str) -> None:
    """동시 편집 경고를 감지해 additionalContext로 주입한다(전 과정 fail-open).

    편집 기록이라는 본연 기능을 절대 막지 않는다 — 감지·주입 실패는 사유만 남기고
    조용히 통과시킨다.

    Args:
        rel_path: 방금 편집한 상대 경로.
        own_session: 자기 세션 태그.
    """
    try:
        notice = concurrent_edit_notice(
            rel_path,
            own_session,
            edit_log_path=harness_runtime_path("EDIT_LOG.md"),
            state_path=harness_runtime_path(CONCURRENT_STATE_FILE),
            window_min=_window_min(),
        )
    except (OSError, ValueError, TypeError) as exc:
        hook_log(f"동시편집 감지 실패(무시): {type(exc).__name__}: {exc}", tag="track_edits")
        return
    if notice:
        write_stdout_json(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": notice,
                }
            }
        )


def _process(payload: dict) -> None:
    """편집 페이로드를 처리해 EDIT_LOG·pending을 갱신한다(트리밖은 스킵)."""
    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return

    project_root = get_project_root()
    abs_path = file_path if os.path.isabs(file_path) else os.path.join(project_root, file_path)
    abs_path = os.path.abspath(abs_path)

    # 트리밖 편집(전역 메모리·스크래치패드 등)은 EDIT_LOG·pending 모두 스킵.
    if not is_within_tree(project_root, abs_path):
        hook_log(f"트리밖 편집 스킵: {file_path}", tag="track_edits")
        return

    rel_path = _to_relative(abs_path, project_root)

    # 트리 안 메타 파일 제외
    for prefix in EXCLUDE_PREFIXES:
        if rel_path.startswith(prefix):
            return

    # .py 편집은 Stop 게이트용 pending 상태에 기록
    if rel_path.endswith(".py"):
        session_id = payload.get("session_id") or "unknown"
        _update_pending_verify(session_id, rel_path)

    tool_name = payload.get("tool_name", "unknown")
    session = _session_tag(payload)
    append_edit_row(harness_runtime_path("EDIT_LOG.md"), rel_path, tool_name, session=session)
    _emit_concurrent_notice(rel_path, session)


def main() -> None:
    """PostToolUse 페이로드를 처리한다. 실패해도 fail-open."""
    payload = read_stdin_json()
    try:
        _process(payload)
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"track_edits fail-open: {type(exc).__name__}: {exc}", tag="track_edits")


if __name__ == "__main__":
    main()
