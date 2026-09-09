"""GEO-SWEEP 하트비트·Sentry 배선 계약.

좌표 스윕 루프는 `start.sh` 가 `&` 로 띄우는 무감독 루프이고, `app.py` 를 거치지 않아
`init_sentry` 호출처가 **하나도 없었다** — 여기서 터진 예외는 아무 데도 가지 않았다.
하트비트도 없어서 루프가 멎어도 표에 안 나타났다. 2026-02 워커 offline 사고를 사용자가
지도에서 발견한 것이 이 축이다(검토 보고서 R3).

이 계약이 그 배선을 잠근다. 특히 **하트비트 실패가 스윕을 멈추면 안 되고, 조용히 넘어가서도
안 된다** 는 두 성질을 각각 확인한다.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "maintenance" / "run_geocode_sweep.py"


@pytest.fixture()
def sweep():
    """스크립트를 모듈로 격리 로드한다(sys.path 오염 없이)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("geocode_sweep_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _one_tick(module, monkeypatch, round_result, calls):
    """루프를 정확히 1회 돌린다(1틱 뒤 종료 플래그를 세운다)."""
    def fake_round(**_kwargs):
        if isinstance(round_result, Exception):
            raise round_result
        return round_result

    monkeypatch.setattr(module, "_run_round", fake_round)
    monkeypatch.setattr(module, "print_result", lambda *a, **k: None)

    def fake_wait(_interval):
        module._shutdown.set()
        return True

    monkeypatch.setattr(module._shutdown, "wait", fake_wait)
    module._shutdown.clear()
    try:
        return module._run_loop(interval=15, batch=1, include_failed=False, as_json=False)
    finally:
        module._shutdown.clear()


def test_tick_writes_a_heartbeat_with_the_fixed_kind(sweep, monkeypatch) -> None:
    """1틱 뒤 GEOCODE_SWEEP 하트비트가 남는다."""
    seen = {}
    monkeypatch.setattr(sweep, "_emit_heartbeat",
                        lambda result, interval=0: seen.update(result=result,
                                                               interval=interval))
    _one_tick(sweep, monkeypatch, {"enqueued": 2, "failed": 0, "scanned": 5}, {})
    assert seen["result"] == {"enqueued": 2, "failed": 0, "scanned": 5}
    assert sweep.HEARTBEAT_WORKER_KIND == "GEOCODE_SWEEP"
    # 판정 예산의 근거라 실제 라운드 간격이 그대로 넘어와야 한다(_one_tick 은 15초로 돈다).
    assert seen["interval"] == 15


def test_heartbeat_is_written_even_when_the_round_blows_up(sweep, monkeypatch) -> None:
    """라운드가 터져도 하트비트는 남는다 — '죽었다' 와 '이번 라운드만 실패' 를 가른다."""
    seen = {}
    monkeypatch.setattr(sweep, "_emit_heartbeat",
                        lambda result, interval=0: seen.update(result=result))
    _one_tick(sweep, monkeypatch, RuntimeError("boom"), {})
    assert "result" in seen and seen["result"] is None


def test_heartbeat_failure_does_not_stop_the_sweep_and_is_logged(
    sweep, monkeypatch, caplog
) -> None:
    """음성 대조군 — 하트비트가 터져도 루프는 끝까지 돌고, 경고가 남는다(삼키지 않는다)."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("heartbeat down")

    monkeypatch.setattr("foms.services.sidefx_worker.upsert_heartbeat", boom)
    logged = []
    monkeypatch.setattr(sweep, "_log_error", lambda msg: logged.append(msg))
    monkeypatch.setattr(sweep, "capture_exception",
                        lambda *a, **k: logged.append("sentry:heartbeat"))

    with caplog.at_level(logging.WARNING):
        rc = _one_tick(sweep, monkeypatch, {"enqueued": 0, "failed": 0, "scanned": 0}, {})

    assert rc == 0, "하트비트 실패가 루프를 죽였다"
    # 두 신호를 **따로** 센다. 한 덩어리로 세면 Sentry 메시지에도 'heartbeat' 가 들어 있어
    # 경고 로그를 지워도 통과한다(2026-09-07 변이 검증에서 실제로 그렇게 새어 나갔다).
    warnings = [m for m in logged if not m.startswith("sentry:")]
    captures = [m for m in logged if m.startswith("sentry:")]
    assert any("heartbeat" in m for m in warnings), f"경고 로그가 안 남았다: {logged}"
    assert captures, "Sentry 로도 안 갔다"


def test_the_sweep_uses_the_shared_sentry_gate_not_its_own_copy(sweep) -> None:
    """Sentry 배선은 공용 함수 한 벌이다 — 이 파일이 자기 복제본을 갖고 있으면 갈라진다.

    실제로 갈라져 있었다: 복제본은 env 이름을 ``"SENTRY_DSN"`` 문자열로 박아, 정본 상수
    ``loop_heartbeat.SENTRY_DSN_ENV`` 와 일치를 지키는 계약
    (``test_loop_heartbeat_wiring.py``) 밖에 있었다. 진입 함수가 게이트를 부르는지는
    그 파일의 러너 전수 계약이 따로 본다 — 여기서는 **같은 함수인지**만 못 박는다.
    """
    from foms.services import loop_heartbeat

    assert sweep.init_sentry_once is loop_heartbeat.init_sentry_once, (
        "사설 Sentry init 복제본이 다시 생겼다")
    assert sweep.capture_exception is loop_heartbeat.capture_exception, (
        "사설 capture 복제본이 다시 생겼다")
    assert not hasattr(sweep, "_init_sentry_once") and not hasattr(sweep, "_capture"), (
        "옛 사설 복제본이 남아 있다")


def test_no_dsn_means_no_sentry_import(sweep, monkeypatch) -> None:
    """DSN 이 없으면 sentry_sdk 도 foms.platform 도 건드리지 않는다(부팅 비용 0).

    ``foms.platform.__init__`` 은 app_factory·blueprints 를 통째로 끌어온다 — DSN 없는
    환경에서 그 비용을 내면 워커 부팅이 Railway heartbeat timeout 에 걸린다.
    """
    import builtins

    monkeypatch.delenv("SENTRY_DSN", raising=False)
    real_import = builtins.__import__
    touched = []

    def _record(name, *args, **kwargs):
        touched.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _record)
    sweep.init_sentry_once()
    monkeypatch.setattr(builtins, "__import__", real_import)
    assert not any(n.startswith("sentry_sdk") or n.startswith("foms.platform") for n in touched), (
        f"DSN 없는데 import 했다: {touched}"
    )
