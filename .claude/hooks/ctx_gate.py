"""Claude Code UserPromptSubmit hook: 컨텍스트 임계 초과 시 원장 정리 리마인더 주입.

stdin으로 {"session_id": ..., "transcript_path": ...} 페이로드를 받아 transcript
파일 크기로 컨텍스트 사용률을 보수 추정하고, 임계(기본 55%)를 넘으면
additionalContext로 "progress ledger·AI_STATUS를 굳혀라" 지시를 주입한다.
정밀도는 불필요하다 — 리마인더 트리거일 뿐이다.

핵심 함정: compact 후에도 transcript는 append-only로 계속 자란다. baseline을
리셋하지 않으면 압축 뒤에도 영구 과대추정이 된다. `session_start.py`가
source=="compact"일 때 `record_compact_baseline()`으로 현재 크기를 굳힌다.

실패는 전부 fail-open(exit 0) + CLAUDE_HOOK_LOG 기록 — 묵시적 삼킴 금지.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)
from shared_utils import (  # type: ignore[import-not-found]  # noqa: E402
    harness_runtime_path,
    hook_log,
    read_stdin_json,
    write_stdout_json,
)

# 상태 파일: {"session_id": str, "baseline_bytes": int, "last_fire_ts": float}
# ponytail: 단일 파일이라 동시 세션이 서로의 baseline을 덮는다(리마인더가 조금
# 일찍 뜨는 손해뿐). 세션별 파일 분리는 오탐이 실제로 성가실 때.
STATE_FILE = ".ctx_gate_state.json"

BYTES_PER_TOKEN = 5  # 보수 계수 — transcript JSONL은 토큰당 5B보다 크다
COOLDOWN_SEC = 1800  # 발동 후 30분은 무출력(스팸 방지)
DEFAULT_PCT = 55
DEFAULT_WINDOW_TOKENS = 1_000_000

REMINDER = (
    "[CTX-GATE] 컨텍스트 사용 추정 {pct}% (임계 {threshold}%). 지금이 정리 시점이다 — "
    "생략 금지: (1) progress ledger·docs/AI_STATUS.md '진행 중' 섹션을 현재 상태로 "
    "갱신하라(완료 항목 제거·신규 항목 등재). (2) 사용자가 응답 가능한 유인 세션이면 "
    "지시형 /compact(남길 것 명시) 또는 /clear+재개를 한 줄로 권고하라. "
    "(3) 무인/백그라운드/goal 진행 중이면 권고 없이 (1)만 수행하고 작업을 계속하라 — "
    "auto-compact가 나머지를 처리한다."
)


def _state_path() -> str:
    """상태 파일의 절대 경로를 반환한다."""
    return harness_runtime_path(STATE_FILE)


def _read_state() -> dict:
    """상태 파일을 읽어 dict로 반환한다(없거나 손상이면 빈 dict)."""
    path = _state_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    """상태를 tmp+os.replace로 원자 교체 저장한다(부분 기록 노출 차단).

    파라미터:
        state: {"session_id", "baseline_bytes", "last_fire_ts"} 상태 dict.
    반환: 없음.
    """
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False)
    os.replace(tmp, path)


def _env_int(name: str, default: int) -> int:
    """양의 정수 환경변수를 읽는다(미설정·비정수·비양수면 default)."""
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _estimate_pct(transcript_path: str, baseline_bytes: int, window_tokens: int) -> float:
    """transcript 증가분으로 컨텍스트 사용률(%)을 보수 추정한다.

    파라미터:
        transcript_path: transcript JSONL 절대 경로.
        baseline_bytes: 직전 compact 시점 크기(없으면 0).
        window_tokens: 컨텍스트 창 크기(토큰).
    반환: 추정 사용률(0.0 이상). 창 크기가 비정상이면 0.0.
    """
    if window_tokens <= 0:
        return 0.0
    grown = max(0, os.path.getsize(transcript_path) - max(0, baseline_bytes))
    return (grown / BYTES_PER_TOKEN) / window_tokens * 100.0


def record_compact_baseline(session_id: str, transcript_path: str) -> None:
    """compact 직후 transcript 크기를 baseline으로 굳힌다(영구 과대추정 차단).

    `session_start.py`가 source=="compact"일 때 호출한다. 자체 fail-open이므로
    호출측은 예외를 신경 쓰지 않아도 된다.

    파라미터:
        session_id: SessionStart payload의 session_id(전체 문자열 — 절단 금지).
        transcript_path: SessionStart payload의 transcript_path(없으면 스킵).
    반환: 없음.
    """
    try:
        if not transcript_path or not os.path.exists(transcript_path):
            hook_log("compact baseline 스킵: transcript_path 없음/부재", tag="ctx_gate")
            return
        state = _read_state()
        keep_ts = (
            float(state.get("last_fire_ts") or 0.0)
            if state.get("session_id") == session_id
            else 0.0
        )
        _write_state(
            {
                "session_id": session_id,
                "baseline_bytes": os.path.getsize(transcript_path),
                "last_fire_ts": keep_ts,
            }
        )
    except (OSError, ValueError, TypeError) as exc:  # fail-open + 로그
        hook_log(f"compact baseline fail-open: {type(exc).__name__}: {exc}", tag="ctx_gate")


def _process(payload: dict) -> None:
    """페이로드를 평가해 임계 초과 시에만 additionalContext를 주입한다."""
    transcript_path = str(payload.get("transcript_path") or "")
    if not transcript_path or not os.path.exists(transcript_path):
        hook_log(f"transcript 부재 — 게이트 스킵: {transcript_path!r}", tag="ctx_gate")
        return

    session_id = str(payload.get("session_id") or "unknown")
    state = _read_state()
    same_session = state.get("session_id") == session_id
    baseline = int(state.get("baseline_bytes") or 0) if same_session else 0
    last_fire = float(state.get("last_fire_ts") or 0.0) if same_session else 0.0

    now = time.time()
    if now - last_fire < COOLDOWN_SEC:
        return

    threshold = _env_int("FOMS_CTX_GATE_PCT", DEFAULT_PCT)
    window = _env_int("FOMS_CTX_WINDOW_TOKENS", DEFAULT_WINDOW_TOKENS)
    pct = _estimate_pct(transcript_path, baseline, window)
    if pct < threshold:
        return

    write_stdout_json(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": REMINDER.format(pct=int(pct), threshold=threshold),
            }
        }
    )
    _write_state(
        {"session_id": session_id, "baseline_bytes": baseline, "last_fire_ts": now}
    )


def main() -> None:
    """UserPromptSubmit 페이로드를 처리한다. 어떤 실패도 fail-open(exit 0)."""
    payload = read_stdin_json()
    try:
        _process(payload)
    except Exception as exc:  # noqa: BLE001 - fail-open + 로그
        hook_log(f"ctx_gate fail-open: {type(exc).__name__}: {exc}", tag="ctx_gate")
    sys.exit(0)


if __name__ == "__main__":
    main()
