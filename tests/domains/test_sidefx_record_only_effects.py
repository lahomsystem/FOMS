"""기록 전용 outbox effect 계약 (SIDEFX-RECORDONLY-01).

운영 실측(2026-09-02): `CHANNEL_PUSH_RECORDED` 행이 **1,188행 DEAD**로 쌓여 있었다.
같은 기간 `CHANNELTALK_PUSH` OrderEvent 는 1,190건 — 즉 **모든 푸시 행이 죽었다**.

기능 손실은 없다(전송은 이 행이 만들어지기 전에 끝나고, 이력·이벤트는 같은 tx 에 쓰인다).
문제는 그 1,188행이 worker 로그와 DEAD 목록을 채워 **진짜 배달 실패를 덮는다**는 것이다.

이 스위트는 두 가지를 잠근다.

1. 러너가 `CHANNEL_PUSH_RECORDED` 를 등록한다(빠지면 다시 NoHandler → DEAD).
2. handler 는 **아무것도 하지 않는다** — 부수효과가 생기면 "기록 전용"이라는 규정이 깨진다.

음성 대조군: 등록되지 않은 effect_type 은 종전대로 :class:`NoHandlerError` 로 남아야 한다
(모든 미등록 타입을 조용히 통과시키는 구현으로 퇴화하면 배포 누락이 안 보인다).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from foms.services.record_only_effects import (
    CHANNEL_PUSH_RECORDED_EFFECT_TYPE,
    handle_record_only,
)
from foms.services.sidefx_worker import NoHandlerError, dispatch, register_handler

_RUNNER_PATH = (
    Path(__file__).resolve().parents[2] / "tools" / "ops" / "run_domain_side_effect_outbox.py"
)


def _row(effect_type: str) -> Any:
    """claim 된 outbox 행 스텁(핸들러가 읽는 필드만)."""
    return SimpleNamespace(
        id=1, effect_type=effect_type, source_domain="ORDER_EVENT",
        payload={"order_id": 7, "push_kind": "measurement", "message_id": "m-1"},
    )


def test_record_only_handler_does_nothing_and_returns() -> None:
    """정상 반환 = worker 가 DONE 으로 끝낸다. 예외도, 부수효과도 없다."""
    row = _row(CHANNEL_PUSH_RECORDED_EFFECT_TYPE)
    before = dict(row.__dict__)

    assert handle_record_only(row) is None
    assert row.__dict__ == before, "기록 전용 handler 가 행을 건드렸다"


def test_runner_registers_channel_push_recorded() -> None:
    """러너 main() 이 이 effect_type 을 등록한다(배선이 빠지면 red).

    소스에 문자열이 있는지가 아니라 **등록 결과**를 본다 — 주석만 남기고 호출을 지우는
    회귀를 잡기 위해서다.
    """
    spec = importlib.util.spec_from_file_location("sidefx_runner_ut", _RUNNER_PATH)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    registered: dict[str, Any] = {}

    def _fake_register(effect_type: str, fn: Any, replace: bool = False) -> None:
        registered[effect_type] = fn

    original_register = runner.register_handler
    original_engine = runner.make_engine_from_env
    runner.register_handler = _fake_register
    runner.make_engine_from_env = lambda: (_ for _ in ()).throw(RuntimeError("stop here"))
    try:
        runner.main(["--once"])  # engine 생성에서 멈춘다 — 등록은 그 앞에서 끝난다
    finally:
        runner.register_handler = original_register
        runner.make_engine_from_env = original_engine

    assert CHANNEL_PUSH_RECORDED_EFFECT_TYPE in registered
    assert registered[CHANNEL_PUSH_RECORDED_EFFECT_TYPE] is runner.handle_record_only
    # 기존 배선도 함께 살아 있어야 한다(등록부를 갈아엎는 회귀 방지).
    for effect_type in ("STORAGE_DELETE", "GEOCODE", "ALIMTALK_SEND"):
        assert effect_type in registered


def test_unregistered_effect_type_still_fails_closed() -> None:
    """음성 대조군: 등록 안 된 타입은 종전대로 NoHandlerError.

    "모르는 타입은 그냥 통과"로 퇴화하면 배포 누락(handler 미등록)이 조용해진다.
    """
    register_handler(CHANNEL_PUSH_RECORDED_EFFECT_TYPE, handle_record_only, replace=True)
    with pytest.raises(NoHandlerError):
        dispatch(_row("EFFECT_THAT_NOBODY_REGISTERED"))
