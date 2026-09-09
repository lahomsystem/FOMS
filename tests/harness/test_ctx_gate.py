"""`.claude/hooks/ctx_gate.py` 컨텍스트 임계 게이트 계약 테스트.

커버:
  - 임계 미만 → 무주입 / 임계 초과 → "[CTX-GATE]" 주입
  - 쿨다운 30분 내 재호출 무출력(스팸 방지)
  - 판정 축 = 마지막 assistant `message.usage`의 창 점유(파일 크기 아님).
    도구 결과로 transcript가 아무리 커져도 점유가 낮으면 안 뜬다(헛알림 회귀 방지)
  - compact로 점유가 내려가면 baseline 보정 없이 저절로 미발동
  - usage 없는 transcript / 부재·손상 payload → fail-open(exit 0, 무출력, 사유 기록)
  - 타 세션 상태 파일의 쿨다운 무시
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

# 테스트 창 크기: 1,000 토큰. 임계 55% → 점유 550 토큰 초과 시 발동.
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


def _transcript(tmp_path: Path, *used_tokens: int, pad_bytes: int = 0) -> str:
    """assistant usage 줄을 순서대로 담은 가짜 transcript를 만들어 경로를 반환한다.

    파라미터:
        used_tokens: 각 assistant 턴의 창 점유(마지막 값이 최신).
        pad_bytes: 뒤에 붙일 무의미 바이트(파일 크기와 점유가 무관함을 증명).
    """
    path = tmp_path / "transcript.jsonl"
    lines = []
    for used in used_tokens:
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-opus-5",
                        "usage": {
                            "input_tokens": 2,
                            "cache_read_input_tokens": max(0, used - 2),
                            "cache_creation_input_tokens": 0,
                            "output_tokens": 100,
                        },
                    },
                }
            )
        )
    blob = ("\n".join(lines) + "\n").encode("utf-8")
    if pad_bytes:
        blob += json.dumps({"type": "user", "filler": "x" * pad_bytes}).encode("utf-8") + b"\n"
    path.write_bytes(blob)
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

    code = _run(module, {"session_id": "s1", "transcript_path": _transcript(tmp_path, 200)})

    assert code == 0
    assert emitted == [], "임계 미만인데 리마인더가 주입됐다"


def test_above_threshold_injects_reminder(tmp_path: Path, monkeypatch) -> None:
    """임계 초과 시 additionalContext에 [CTX-GATE] 지시가 실린다."""
    module = _load_ctx_gate("ctx_gate_above")
    runtime, emitted, _ = _prepare(module, tmp_path, monkeypatch)

    code = _run(module, {"session_id": "s1", "transcript_path": _transcript(tmp_path, 800)})

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
    payload = {"session_id": "s1", "transcript_path": _transcript(tmp_path, 800)}

    assert _run(module, payload) == 0
    assert len(emitted) == 1

    assert _run(module, payload) == 0
    assert len(emitted) == 1, "쿨다운 내 재발동은 스팸이다"


def test_file_size_does_not_drive_the_gate(tmp_path: Path, monkeypatch) -> None:
    """도구 결과로 transcript가 아무리 커져도 창 점유가 낮으면 발동하지 않는다.

    옛 구현은 파일 크기/5B로 추정해 점유 11%인 세션에 131%를 보고했다.
    """
    module = _load_ctx_gate("ctx_gate_filesize")
    _, emitted, _ = _prepare(module, tmp_path, monkeypatch)

    transcript = _transcript(tmp_path, 200, pad_bytes=5_000_000)

    assert _run(module, {"session_id": "s1", "transcript_path": transcript}) == 0
    assert emitted == [], "파일 크기가 판정 축으로 되살아났다"


def test_compact_drop_needs_no_baseline(tmp_path: Path, monkeypatch) -> None:
    """compact로 점유가 내려가면 baseline 보정 없이 곧바로 미발동이다."""
    module = _load_ctx_gate("ctx_gate_after_compact")
    _, emitted, _ = _prepare(module, tmp_path, monkeypatch)

    # 800(발동 수준) 뒤에 compact 후 120(점유 급감)이 최신 턴으로 온다.
    transcript = _transcript(tmp_path, 800, 120)

    assert _run(module, {"session_id": "s1", "transcript_path": transcript}) == 0
    assert emitted == [], "옛 턴의 높은 점유를 최신으로 읽었다"


def test_transcript_without_usage_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    """assistant usage가 없는 transcript는 무출력 + 사유 기록이다."""
    module = _load_ctx_gate("ctx_gate_no_usage")
    _, emitted, logged = _prepare(module, tmp_path, monkeypatch)
    path = tmp_path / "no_usage.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}), encoding="utf-8")

    assert _run(module, {"session_id": "s1", "transcript_path": str(path)}) == 0

    assert emitted == []
    assert any("usage" in msg for msg in logged), "fail-open 사유가 묵시적으로 삼켜졌다"


def test_missing_transcript_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    """transcript_path 부재/손상 payload는 exit 0 + 무출력 + 사유 기록."""
    module = _load_ctx_gate("ctx_gate_missing")
    _, emitted, logged = _prepare(module, tmp_path, monkeypatch)

    assert _run(module, {"session_id": "s1"}) == 0
    assert _run(module, {"session_id": "s1", "transcript_path": str(tmp_path / "nope.jsonl")}) == 0
    assert _run(module, {}) == 0

    assert emitted == []
    assert len(logged) == 3, "fail-open 사유가 묵시적으로 삼켜졌다"


def test_other_session_state_is_ignored(tmp_path: Path, monkeypatch) -> None:
    """상태 파일의 session_id가 다르면 쿨다운을 무시한다."""
    module = _load_ctx_gate("ctx_gate_other_session")
    runtime, emitted, _ = _prepare(module, tmp_path, monkeypatch)
    (runtime / module.STATE_FILE).write_text(
        json.dumps({"session_id": "other", "last_fire_ts": time.time()}),
        encoding="utf-8",
    )

    assert _run(module, {"session_id": "s1", "transcript_path": _transcript(tmp_path, 800)}) == 0

    assert "[CTX-GATE]" in _injected(emitted), "타 세션 쿨다운이 내 발동을 막았다"
