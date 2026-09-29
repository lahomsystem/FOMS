"""하트비트 metadata 조립 결함이 워커 루프를 죽이지 않는다 (2026-09-10 정산 루프 사고의 나머지 러너).

정산 러너는 사고 뒤 ``_safe_heartbeat_metadata`` 로 막았다. 알림 재촉·주문 수집·좌표 스윕도 같은
모양(조립이 루프 예외 가드 밖)이었다 — ``foms.services.loop_heartbeat.safe_metadata`` 로 막는다.
러너 로드·한 tick 구동 도우미는 ``test_loop_heartbeat_wiring.py`` 의 것을 그대로 쓴다.
"""
from __future__ import annotations

import logging

from foms.services import loop_heartbeat
from tests.domains.test_loop_heartbeat_wiring import (
    _ALLOWED_METADATA_KEYS,
    _REPO_ROOT,
    _drive_one_tick,
    _heartbeat_rows,
    _load,
)


# --------------------------------------------------------------------------- #
# 조립 결함이 루프를 죽이지 않는다 (2026-09-10 정산 루프 사고와 같은 모양, 나머지 러너)
# --------------------------------------------------------------------------- #
def test_safe_metadata_falls_back_to_the_same_keys_and_reports(monkeypatch, caplog):
    reported = []
    monkeypatch.setattr(loop_heartbeat, "capture_exception", lambda *a, **k: reported.append(True))
    fallback = {"interval_seconds": 60, "outcome": "ok", "checked": 0}
    with caplog.at_level(logging.WARNING):
        got = loop_heartbeat.safe_metadata(lambda: {"checked": int({"x": 1})}, fallback, label="t")
    assert got == fallback and got is not fallback
    assert reported == [True]
    assert "heartbeat metadata failed" in caplog.text
    assert loop_heartbeat.safe_metadata(lambda: {"a": 1}, fallback) == {"a": 1}  # negative control


def test_escalation_loop_survives_a_malformed_sweep_result(app, monkeypatch):
    """스윕 결과의 수치 칸이 dict 여도(조립 TypeError) 루프는 살아 있고 하트비트가 남는다."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_notification_escalation.py")
    monkeypatch.setattr(runner, "_sweep_once", lambda _dry: {"checked": {"a": 1}, "escalated": 0,
                                                             "operator_escalated": 0, "dry_run": False})
    monkeypatch.setattr(runner, "_print_result", lambda *a, **k: None)
    _drive_one_tick(runner, monkeypatch, lambda: runner._run_loop(60, False, True))
    rows = _heartbeat_rows(runner.HEARTBEAT_WORKER_KIND)
    assert len(rows) == 1
    assert rows[0].metadata_json["outcome"] == "ok" and rows[0].metadata_json["checked"] == 0
    assert set(rows[0].metadata_json) == _ALLOWED_METADATA_KEYS["run_notification_escalation"]


def test_order_sync_loop_survives_a_malformed_sweep_result(app, monkeypatch):
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_naver_order_sync.py")
    monkeypatch.setattr(runner, "_sweep_once", lambda _dry: {"changed": {"a": 1}})
    monkeypatch.setattr(runner, "_print_result", lambda *a, **k: None)
    _drive_one_tick(runner, monkeypatch, lambda: runner._run_loop(300, False, True))
    rows = _heartbeat_rows(runner.HEARTBEAT_WORKER_KIND)
    assert len(rows) == 1
    assert rows[0].metadata_json["changed"] == 0
    assert set(rows[0].metadata_json) == _ALLOWED_METADATA_KEYS["run_naver_order_sync"]


def test_geocode_heartbeat_survives_a_malformed_round_result(app, monkeypatch):
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_geocode_sweep.py")
    runner._emit_heartbeat({"enqueued": {"a": 1}, "failed": 0, "scanned": 3}, 60)
    rows = _heartbeat_rows(runner.HEARTBEAT_WORKER_KIND)
    assert len(rows) == 1
    assert rows[0].metadata_json == {"interval_seconds": 60, "outcome": "ok",
                                     "enqueued": 0, "failed": 0, "scanned": 0}


def test_geocode_loop_survives_an_unexpected_round_error(app, monkeypatch):
    """라운드의 KeyError·TypeError 같은 뜻밖의 예외도 기록하고 다음 라운드로 간다."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_geocode_sweep.py")

    def _boom(**_k):
        raise KeyError("failed")

    monkeypatch.setattr(runner, "_run_round", _boom)
    waits = []

    def _wait(seconds):
        waits.append(seconds)
        runner._shutdown.set()
        return True

    monkeypatch.setattr(runner._shutdown, "wait", _wait)
    try:
        assert runner._run_loop(interval=60, batch=10, include_failed=False, as_json=True) == 0
    finally:
        runner._shutdown.clear()
    assert waits, "라운드가 터지자 루프가 죽었다"
    rows = _heartbeat_rows(runner.HEARTBEAT_WORKER_KIND)
    assert rows and rows[-1].metadata_json["outcome"] == "round_failed"
