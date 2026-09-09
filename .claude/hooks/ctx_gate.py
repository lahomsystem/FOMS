"""Claude Code UserPromptSubmit hook: 컨텍스트 임계 초과 시 원장 정리 리마인더 주입.

stdin으로 {"session_id": ..., "transcript_path": ...} 페이로드를 받아 transcript
JSONL 끝에서 가장 최근 assistant 항목의 `message.usage`를 읽어 **현재 창 점유**를
구하고, 임계(기본 55%)를 넘으면 additionalContext로 "progress ledger·AI_STATUS를
굳혀라" 지시를 주입한다.

점유 = input_tokens + cache_read_input_tokens + cache_creation_input_tokens.
이 값은 모델이 실제로 받은 창이라, compaction이 창을 비우면 다음 응답에서 저절로
내려간다 — baseline 보정이 필요 없다.

핵심 함정(옛 구현이 밟은 것): transcript 파일 크기는 append-only 누적 I/O라
컨텍스트 점유가 아니다. 도구 결과 원문·훅 출력처럼 창에 남지 않는 바이트까지
세므로 도구를 많이 쓴 세션은 실제의 몇 배로 뜬다. 실측 사례 = 점유 11%인 세션에
131%를 보고.

창 크기는 transcript에 없다(`message.model`은 `claude-opus-5`처럼 1M 여부를 안
알려준다). `FOMS_CTX_WINDOW_TOKENS`로 덮어쓴다.

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

# 상태 파일: {"session_id": str, "last_fire_ts": float} — 쿨다운 전용.
# 단일 파일이라 동시 세션이 서로의 쿨다운을 덮는다(리마인더가 조금 일찍 뜨는
# 손해뿐). 세션별 파일 분리는 오탐이 실제로 성가실 때.
STATE_FILE = ".ctx_gate_state.json"

# transcript 끝에서 이만큼만 되읽어 최신 usage를 찾는다(전체 파싱 금지 — 수 MB).
TAIL_SCAN_BYTES = 512 * 1024
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
        state: {"session_id", "last_fire_ts"} 상태 dict.
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


def _latest_context_tokens(transcript_path: str) -> int | None:
    """transcript 끝에서 가장 최근 assistant 항목의 창 점유 토큰수를 읽는다.

    파라미터:
        transcript_path: transcript JSONL 절대 경로.
    반환: 점유 토큰수(input + cache_read + cache_creation). 못 찾으면 None.
    """
    size = os.path.getsize(transcript_path)
    with open(transcript_path, "rb") as handle:
        handle.seek(max(0, size - TAIL_SCAN_BYTES))
        chunk = handle.read()
    for line in reversed(chunk.decode("utf-8", "ignore").splitlines()):
        line = line.strip()
        if not line.startswith("{") or '"usage"' not in line:
            continue
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue  # tail 첫 줄은 잘려 있을 수 있다 — 다음 줄로
        if entry.get("type") != "assistant":
            continue
        usage = (entry.get("message") or {}).get("usage") or {}
        total = 0
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            try:
                total += int(usage.get(key) or 0)
            except (ValueError, TypeError):
                continue
        if total > 0:
            return total
    return None


def _process(payload: dict) -> None:
    """페이로드를 평가해 임계 초과 시에만 additionalContext를 주입한다."""
    transcript_path = str(payload.get("transcript_path") or "")
    if not transcript_path or not os.path.exists(transcript_path):
        hook_log(f"transcript 부재 — 게이트 스킵: {transcript_path!r}", tag="ctx_gate")
        return

    session_id = str(payload.get("session_id") or "unknown")
    state = _read_state()
    same_session = state.get("session_id") == session_id
    last_fire = float(state.get("last_fire_ts") or 0.0) if same_session else 0.0

    now = time.time()
    if now - last_fire < COOLDOWN_SEC:
        return

    used = _latest_context_tokens(transcript_path)
    if used is None:
        hook_log("transcript에 assistant usage 없음 — 게이트 스킵", tag="ctx_gate")
        return

    threshold = _env_int("FOMS_CTX_GATE_PCT", DEFAULT_PCT)
    window = _env_int("FOMS_CTX_WINDOW_TOKENS", DEFAULT_WINDOW_TOKENS)
    if window <= 0:
        hook_log(f"창 크기가 비정상 — 게이트 스킵: {window}", tag="ctx_gate")
        return
    pct = used / window * 100.0
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
    _write_state({"session_id": session_id, "last_fire_ts": now})


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
