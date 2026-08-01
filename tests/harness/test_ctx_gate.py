"""`.claude/hooks/ctx_gate.py` 컨텍스트 임계 게이트 계약 테스트.

커버:
  - 임계 미만 → 무주입 / 임계 초과 → "[CTX-GATE]" 주입
  - 쿨다운 30분 내 재호출 무출력(스팸 방지)
  - compact baseline 반영 시 증가분만 계산(영구 과대추정 회귀 방지)
  - transcript_path 부재/손상 payload → fail-open(exit 0, 무출력)
  - 타 세션 상태 파일의 baseline 무시
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_REL = ".claude/hooks/ctx_gate.py"

# 테스트 창 크기: 1,000 토큰(=5,000B). 임계 55% → 2,750B 초과 시 발동.
TEST_WINDOW_TOKENS = "1000"


def _load_ctx_gate(module_name: str):
    """ctx_gate 훅 모듈을 fresh 로드하고 sys.path/shared_utils를 복원한다."""
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / HOOK_REL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    saved_shared = sys.modules.get("shared_utils")
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        if saved_shared is not None:
            sys.modules["shared_utils"] = saved_shared
        else:
            sys.modules.pop("shared_utils", None)
    return module


def _prepare(module, tmp_path: Path, monkeypatch) -> tuple[Path, list[dict], list[str]]:
    """모듈의 상태 경로·출력·로그를 tmp 워크스페이스로 리다이렉트한다.

    반환: (runtime 디렉터리, 주입된 stdout JSON 리스트, hook_log 메시지 리스트).
    """
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    emitted: list[dict] = []
    logged: list[str] = []

    monkeypatch.setattr(module, "harness_runtime_path", lambda *p: str(runtime.joinpath(*p)))
    monkeypatch.setattr(module, "write_stdout_json", emitted.append)
    monkeypatch.setattr(module, "hook_log", lambda msg, tag="hook": logged.append(msg))
    monkeypatch.setenv("FOMS_CTX_WINDOW_TOKENS", TEST_WINDOW_TOKENS)
    monkeypatch.delenv("FOMS_CTX_GATE_PCT", raising=False)
    return runtime, emitted, logged


def _transcript(tmp_path: Path, size_bytes: int) -> str:
    """지정 크기의 가짜 transcript 파일을 만들어 경로를 반환한다."""
    path = tmp_path / "transcript.jsonl"
    path.write_bytes(b"x" * size_bytes)
    return str(path)


def _run(module, payload: dict) -> int:
    """훅 main()을 실행하고 종료 코드를 반환한다."""
    module.read_stdin_json = lambda: payload  # type: ignore[assignment]
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    return int(excinfo.value.code or 0)


def _injected(emitted: list[dict]) -> str:
    """주입된 additionalContext 문자열을 뽑는다(없으면 빈 문자열)."""
    if not emitted:
        return ""
    return emitted[0]["hookSpecificOutput"]["additionalContext"]


def test_below_threshold_injects_nothing(tmp_path: Path, monkeypatch) -> None:
    """추정 사용률이 임계 미만이면 아무것도 주입하지 않는다."""
    module = _load_ctx_gate("ctx_gate_below")
    _, emitted, _ = _prepare(module, tmp_path, monkeypatch)

    code = _run(module, {"session_id": "s1", "transcript_path": _transcript(tmp_path, 1_000)})

    assert code == 0
    assert emitted == [], "임계 미만인데 리마인더가 주입됐다"


def test_above_threshold_injects_reminder(tmp_path: Path, monkeypatch) -> None:
    """임계 초과 시 additionalContext에 [CTX-GATE] 지시가 실린다."""
    module = _load_ctx_gate("ctx_gate_above")
    runtime, emitted, _ = _prepare(module, tmp_path, monkeypatch)

    code = _run(module, {"session_id": "s1", "transcript_path": _transcript(tmp_path, 4_000)})

    assert code == 0
    context = _injected(emitted)
    assert "[CTX-GATE]" in context
    assert "progress ledger" in context
    assert emitted[0]["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    state = json.loads((runtime / module.STATE_FILE).read_text(encoding="utf-8"))
    assert state["session_id"] == "s1"
    assert state["last_fire_ts"] > 0, "발동 시각이 기록돼야 쿨다운이 작동한다"


def test_cooldown_suppresses_second_fire(tmp_path: Path, monkeypatch) -> None:
    """쿨다운(30분) 안의 재호출은 무출력이어야 한다."""
    module = _load_ctx_gate("ctx_gate_cooldown")
    _, emitted, _ = _prepare(module, tmp_path, monkeypatch)
    payload = {"session_id": "s1", "transcript_path": _transcript(tmp_path, 4_000)}

    assert _run(module, payload) == 0
    assert len(emitted) == 1

    assert _run(module, payload) == 0
    assert len(emitted) == 1, "쿨다운 내 재발동은 스팸이다"


def test_compact_baseline_suppresses_stale_growth(tmp_path: Path, monkeypatch) -> None:
    """baseline 기록 후에는 증가분만 계산해 임계 미만이면 무출력이다."""
    module = _load_ctx_gate("ctx_gate_baseline")
    runtime, emitted, _ = _prepare(module, tmp_path, monkeypatch)
    transcript = _transcript(tmp_path, 4_000)  # baseline 없으면 80% → 발동할 크기

    module.record_compact_baseline("s1", transcript)

    state = json.loads((runtime / module.STATE_FILE).read_text(encoding="utf-8"))
    assert state["baseline_bytes"] == 4_000

    Path(transcript).write_bytes(b"x" * 5_000)  # 증가분 1,000B = 20% → 미발동
    assert _run(module, {"session_id": "s1", "transcript_path": transcript}) == 0
    assert emitted == [], "compact baseline이 반영되지 않아 과대추정했다"

    Path(transcript).write_bytes(b"x" * 8_000)  # 증가분 4,000B = 80% → 발동
    assert _run(module, {"session_id": "s1", "transcript_path": transcript}) == 0
    assert "[CTX-GATE]" in _injected(emitted)


def test_missing_transcript_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    """transcript_path 부재/손상 payload는 exit 0 + 무출력 + 사유 기록."""
    module = _load_ctx_gate("ctx_gate_missing")
    _, emitted, logged = _prepare(module, tmp_path, monkeypatch)

    assert _run(module, {"session_id": "s1"}) == 0
    assert _run(module, {"session_id": "s1", "transcript_path": str(tmp_path / "nope.jsonl")}) == 0
    assert _run(module, {}) == 0

    assert emitted == []
    assert len(logged) == 3, "fail-open 사유가 묵시적으로 삼켜졌다"


def test_other_session_baseline_is_ignored(tmp_path: Path, monkeypatch) -> None:
    """상태 파일의 session_id가 다르면 baseline·쿨다운 모두 무시한다."""
    module = _load_ctx_gate("ctx_gate_other_session")
    runtime, emitted, _ = _prepare(module, tmp_path, monkeypatch)
    (runtime / module.STATE_FILE).write_text(
        json.dumps({"session_id": "other", "baseline_bytes": 4_000, "last_fire_ts": time.time()}),
        encoding="utf-8",
    )

    assert _run(module, {"session_id": "s1", "transcript_path": _transcript(tmp_path, 4_000)}) == 0

    assert "[CTX-GATE]" in _injected(emitted), "타 세션 baseline이 내 추정을 가렸다"
