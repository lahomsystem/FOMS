"""워커 컨테이너의 모든 루프가 생존 신호를 남기는지 못박는다 (OPS-HEARTBEAT-01, F-5·F-6).

``start.sh`` 는 백그라운드 루프 여러 개를 ``&`` 로 띄우고 마지막에 큐 소비 본체로 자기를
대체한다. wait/trap/supervisor 가 0 이라 **아무도 죽음을 알리지 않는다** — 2026-02 워커
offline, 2026-08-31 SIDEFX 미배포를 두 번 다 사용자가 화면에서 먼저 발견했다.

여기서 지키는 계약:

* ``start.sh`` 가 띄우는 모든 ``--loop`` 러너는 등록부 상수로 자기 kind 를 선언한다.
  새 루프를 하트비트 없이 배선하면 이 테스트가 빨강이 된다(F-9 이 정확히 이 드리프트였다).
* 큐 소비 본체는 하트비트를 남기는 러너로 뜬다(맨 rq worker 는 자기 생존을 안 남겼다).
* 스윕이 터진 tick 도 하트비트를 남긴다 — "죽었다" 와 "이번 스윕만 실패" 가 갈려야 한다.
* 하트비트 실패는 본 작업을 막지 않되 조용히 사라지지도 않는다(경고 1건).
* 하트비트 metadata 에 고객 정보를 싣지 않는다.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import logging
import pathlib
import re

import pytest
from sqlalchemy import select
from types import SimpleNamespace

from db import engine
from foms.services import loop_heartbeat
from foms.services import sidefx_worker
from foms.services.sidefx_worker import WORKER_KIND_SPECS
from models import SideEffectWorkerHeartbeat

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_START_SH = _REPO_ROOT / "start.sh"
_RQ_RUNNER = _REPO_ROOT / "tools" / "ops" / "run_rq_worker.py"

#: metadata 에 허용된 키. 이름·전화·주소 같은 고객 축이 새로 들어오면 red.
_ALLOWED_METADATA_KEYS = {
    "run_notification_escalation": {"interval_seconds", "outcome", "checked", "escalated",
                                    "operator_escalated", "pushed"},
    "run_naver_order_sync": {"interval_seconds", "outcome", "changed", "candidates",
                             "created", "pending_review"},
    "run_naver_settle_sync": {"interval_seconds", "ran", "status", "calls", "rows"},
}


class _StopLoop(Exception):
    """테스트가 무한 루프를 끊는 신호(``time.sleep`` 자리에서 던진다)."""


def _load(path: pathlib.Path):
    """스크립트를 파일 경로로 읽어 온다(``scripts/``·``tools/`` 는 패키지가 아니다)."""
    spec = importlib.util.spec_from_file_location(f"{path.stem}_ut", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _loop_runners_in_start_sh() -> list:
    """``start.sh`` 가 ``--loop`` 로 띄우는 러너 파일 이름들(중복 제거·정렬)."""
    text = _START_SH.read_text(encoding="utf-8")
    found = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "--loop" not in stripped:
            continue
        match = re.search(r"scripts/maintenance/([A-Za-z0-9_]+)\.py", stripped)
        if match:
            found.add(match.group(1))
    return sorted(found)


def _heartbeat_rows(kind: str) -> list:
    """해당 kind 의 하트비트 행(러너가 자기 세션으로 커밋하므로 엔진에서 직접 읽는다)."""
    table = SideEffectWorkerHeartbeat.__table__
    with engine.connect() as conn:
        return list(conn.execute(
            select(table.c.last_heartbeat_at, table.c.metadata_json)
            .where(table.c.worker_kind == kind)
        ))


# --------------------------------------------------------------------------- #
# 1. 배선 계약 — start.sh 가 띄우는 것 전부가 감시 대상이다
# --------------------------------------------------------------------------- #
def test_start_sh_actually_launches_loops():
    """이 파일의 다른 계약이 빈 목록 위에서 공회전하지 않는지부터 본다."""
    runners = _loop_runners_in_start_sh()
    assert len(runners) >= 5, runners


@pytest.mark.parametrize("runner_name", _loop_runners_in_start_sh())
def test_every_start_sh_loop_declares_a_registered_kind(runner_name):
    """하트비트를 안 남기는 루프를 배선하면 여기서 걸린다(F-9 의 드리프트 형태)."""
    source = (_REPO_ROOT / "scripts" / "maintenance" / f"{runner_name}.py").read_text(
        encoding="utf-8")
    match = re.search(r"^HEARTBEAT_WORKER_KIND = (WORKER_KIND_[A-Z_]+)$", source, re.M)
    assert match, f"{runner_name} 이 등록부 상수로 kind 를 선언하지 않는다"
    kind = getattr(sidefx_worker, match.group(1))
    assert kind in WORKER_KIND_SPECS, f"{kind} 가 판정 등록부에 없다 — 아무도 안 읽는다"


def test_queue_consumer_runs_through_the_heartbeat_runner():
    """맨 rq worker 는 자기 생존을 FOMS 표에 안 남긴다 — 러너를 거쳐야 한다.

    2026-09-08 이후 러너는 ``exec`` 가 아니라 감시 루프 안에서 백그라운드로 뜬다
    (PID 1 은 루프가 잡는다 — ``test_worker_supervisor_contract.py``). 여기서 지키는 것은
    그대로다: 큐 소비자는 **반드시 러너를 거친다**.
    """
    text = _START_SH.read_text(encoding="utf-8")
    code_lines = [ln.strip() for ln in text.splitlines() if not ln.strip().startswith("#")]
    runner_lines = [ln for ln in code_lines if "run_rq_worker.py" in ln]
    assert len(runner_lines) == 1, runner_lines
    assert runner_lines[0].endswith("&"), "러너는 백그라운드로 띄워야 감시 루프가 wait 로 지킨다"
    assert not any(ln.startswith("exec rq worker") for ln in code_lines),         "맨 rq CLI 로 돌아가면 RQ_WORKER 하트비트가 사라진다"


def test_rq_runner_drops_inherited_db_connections_in_the_child(monkeypatch):
    """fork 자식이 부모의 DB 연결을 물려받아 같이 쓰면 TLS 가 깨진다(2026-09-08 운영 결함).

    부모는 하트비트 때문에 psycopg2 연결을 풀에 살려 두고, rq 는 잡마다 ``fork`` 한다.
    자식이 그 소켓을 그대로 쓰면 60초 뒤 부모의 다음 하트비트와 레코드가 섞여
    ``SSL error: decryption failed or bad record mac`` → 잡이 통째로 실패한다.
    실측: 정산 동기화 run 28·29 가 두 번 다 정확히 60초에 죽었다.

    rq 의 진짜 ``main_work_horse`` 는 잡을 돌리고 ``os._exit`` 한다 — 대역으로 끊는다.
    """
    runner = _load(_RQ_RUNNER)
    calls = []

    class _Engine:
        def dispose(self, close=True):
            calls.append(("dispose", close))

    monkeypatch.setattr(runner, "engine", _Engine())
    monkeypatch.setattr(runner.Worker, "main_work_horse",
                        lambda self, *a, **k: calls.append(("super", a)), raising=False)

    worker = runner.HeartbeatWorker.__new__(runner.HeartbeatWorker)
    worker._last_db_heartbeat_at = "부모에게서 물려받은 표식"
    runner.HeartbeatWorker.main_work_horse(worker, "job", "queue")

    assert calls == [("dispose", False), ("super", ("job", "queue"))], (
        "자식은 super() 로 넘어가기 전에 engine.dispose(close=False) 를 해야 한다 — "
        f"close=True 면 소켓의 진짜 주인인 부모 연결까지 끊는다. 실제 호출: {calls}"
    )
    assert worker._last_db_heartbeat_at is None, "자식이 부모의 하트비트 표식을 물려받았다"


def test_rq_runner_kind_is_registered():
    """큐 소비 본체의 kind 도 등록부에 있어야 판정된다."""
    runner = _load(_RQ_RUNNER)
    assert runner.HEARTBEAT_WORKER_KIND in WORKER_KIND_SPECS


# --------------------------------------------------------------------------- #
# 2. 공통 헬퍼 — 실패해도 본 작업을 막지 않되 삼키지도 않는다
# --------------------------------------------------------------------------- #
def test_helper_reports_success(app):
    """정상 경로: True 를 돌려주고 행이 생긴다."""
    kind = "DELIVERY"
    assert loop_heartbeat.emit_heartbeat(engine, kind, metadata={"n": 1}) is True
    rows = _heartbeat_rows(kind)
    assert len(rows) == 1 and rows[0].metadata_json == {"n": 1}


def test_helper_swallows_failure_but_leaves_a_warning_and_a_sentry_event(monkeypatch, caplog):
    """음성 대조군 — 예외를 올리지 않되 경고 1건 + Sentry 이벤트를 남긴다."""
    def _boom(*args, **kwargs):
        raise RuntimeError("side_effect_worker_heartbeats is unreachable")

    captured = []
    # 모듈 최상단 import 라 loop_heartbeat 쪽 이름을 갈아야 한다(지연 import 는 계층
    # 래칫이 금지한다 — tests/contracts/runtime/test_layer_dependency_ratchet.py).
    monkeypatch.setattr(loop_heartbeat, "upsert_heartbeat", _boom)
    monkeypatch.setattr(loop_heartbeat, "capture_exception",
                        lambda *a, **k: captured.append(True))
    logger = logging.getLogger("loop_heartbeat_ut")

    with caplog.at_level(logging.WARNING, logger="loop_heartbeat_ut"):
        result = loop_heartbeat.emit_heartbeat(engine, "DELIVERY", logger=logger)

    assert result is False
    records = [r for r in caplog.records if r.name == "loop_heartbeat_ut"]
    assert len(records) == 1, "하트비트 실패가 조용히 사라졌다"
    assert "heartbeat" in records[0].getMessage()
    assert captured == [True], "Sentry 로 안 갔다"


# --------------------------------------------------------------------------- #
# 3. 루프 3종 — 스윕이 터진 tick 도 하트비트를 남긴다
# --------------------------------------------------------------------------- #
def _drive_one_tick(runner, monkeypatch, call):
    """러너의 진짜 ``_run_loop`` 를 1 tick 만 돌린다(``time.sleep`` 자리에서 끊는다)."""
    def _sleep(_seconds):
        raise _StopLoop

    monkeypatch.setattr(runner.time, "sleep", _sleep)
    with pytest.raises(_StopLoop):
        call()


def test_escalation_loop_beats_even_when_the_sweep_explodes(app, monkeypatch):
    """스윕이 터져도 루프는 살아 있고, 그 사실이 하트비트에 남는다."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_notification_escalation.py")
    kind = runner.HEARTBEAT_WORKER_KIND
    assert _heartbeat_rows(kind) == []

    def _boom(_dry_run):
        raise RuntimeError("escalation exploded")

    monkeypatch.setattr(runner, "_sweep_once", _boom)
    _drive_one_tick(runner, monkeypatch, lambda: runner._run_loop(60, False, True))

    rows = _heartbeat_rows(kind)
    assert len(rows) == 1
    assert rows[0].metadata_json["outcome"] == "sweep_failed"


def test_order_sync_loop_beats_even_when_the_sweep_explodes(app, monkeypatch):
    """수집이 조용히 멎는 것이 최악이라 실패 tick 도 신호를 남긴다."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_naver_order_sync.py")
    kind = runner.HEARTBEAT_WORKER_KIND
    assert _heartbeat_rows(kind) == []

    def _boom(_dry_run):
        raise RuntimeError("ingest exploded")

    monkeypatch.setattr(runner, "_sweep_once", _boom)
    _drive_one_tick(runner, monkeypatch, lambda: runner._run_loop(300, False, True))

    rows = _heartbeat_rows(kind)
    assert len(rows) == 1
    assert rows[0].metadata_json["outcome"] == "sweep_failed"


def test_settle_sync_loop_beats_outside_its_window(app, monkeypatch):
    """창 밖 tick 도 남긴다 — 안 그러면 하루 대부분이 '죽은 것' 처럼 보인다."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_naver_settle_sync.py")
    kind = runner.HEARTBEAT_WORKER_KIND
    assert _heartbeat_rows(kind) == []

    monkeypatch.setattr(runner, "should_run", lambda *a, **k: False)
    args = argparse.Namespace(at="05:30", window=10, tick=5, dry_run=False, json=True,
                              backfill_from=None, loop=True)
    _drive_one_tick(runner, monkeypatch, lambda: runner._run_loop(args))

    rows = _heartbeat_rows(kind)
    assert len(rows) == 1
    assert rows[0].metadata_json["ran"] is False


def test_loops_declare_their_real_tick_interval(app, monkeypatch):
    """신고 값이 실제 간격과 갈리면 판정 예산이 틀린다 — 루프가 받은 값을 그대로 싣는다."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / "run_naver_order_sync.py")
    kind = runner.HEARTBEAT_WORKER_KIND
    assert _heartbeat_rows(kind) == []

    monkeypatch.setattr(runner, "_sweep_once", lambda _dry: {"changed": 0})
    _drive_one_tick(runner, monkeypatch, lambda: runner._run_loop(1800, False, True))

    rows = _heartbeat_rows(kind)
    assert len(rows) == 1
    assert rows[0].metadata_json["interval_seconds"] == 1800


def test_rq_worker_declares_its_dequeue_cadence():
    """rq 는 놀 때 ``worker_ttl - 15`` 주기로만 heartbeat 를 부른다 — 그 값을 신고한다."""
    runner = _load(_RQ_RUNNER)

    class _Probe(runner.HeartbeatWorkerMixin):
        dequeue_timeout = 405

        def queue_names(self):
            return ["default"]

    assert _Probe().db_heartbeat_metadata()["interval_seconds"] == 405


@pytest.mark.parametrize("runner_name", sorted(_ALLOWED_METADATA_KEYS))
def test_heartbeat_metadata_never_carries_customer_information(runner_name):
    """metadata 는 운영 감시용 집계 수치만 싣는다(이름·전화·주소 금지)."""
    runner = _load(_REPO_ROOT / "scripts" / "maintenance" / f"{runner_name}.py")
    if runner_name == "run_naver_settle_sync":
        payload = runner._heartbeat_metadata(ran_now=True, result={
            "status": "OK", "stats": {"calls": 3, "rows": 9},
            "customer_name": "홍길동", "phone": "010-0000-0000"})
    else:
        payload = runner._heartbeat_metadata({
            "checked": 1, "escalated": 1, "operator_escalated": 0, "delivery": {"pushed": 2},
            "changed": 1, "candidates": 2, "created": 1, "pending_review": 0,
            "customer_name": "홍길동", "phone": "010-0000-0000"})
    assert set(payload) == _ALLOWED_METADATA_KEYS[runner_name]


# --------------------------------------------------------------------------- #
# 4. 큐 소비 본체 — rq 하트비트 자리에서 같이 뛴다
# --------------------------------------------------------------------------- #
def _mixin_probe(runner):
    """Redis 없이 mixin 만 시험하기 위한 최소 객체."""
    calls = []

    class _Probe(runner.HeartbeatWorkerMixin):
        db_heartbeat_interval = 60

        def db_heartbeat_metadata(self):
            return {"queues": "default", "successful": 0, "failed": 0, "state": "idle"}

    return _Probe(), calls


def test_rq_heartbeat_is_throttled_between_ticks(monkeypatch):
    """바쁜 워커는 잡마다 heartbeat 를 부른다 — DB 는 간격을 두고만 때린다."""
    runner = _load(_RQ_RUNNER)
    probe, calls = _mixin_probe(runner)

    def _fake_emit(*args, **kwargs):
        calls.append(kwargs.get("metadata"))
        return True

    monkeypatch.setattr(runner, "emit_heartbeat", _fake_emit)
    t0 = datetime.datetime(2026, 9, 8, 0, 0, 0)

    assert probe.maybe_emit_db_heartbeat(t0) is True
    assert probe.maybe_emit_db_heartbeat(t0 + datetime.timedelta(seconds=59)) is False
    assert probe.maybe_emit_db_heartbeat(t0 + datetime.timedelta(seconds=61)) is True
    assert len(calls) == 2


def test_rq_heartbeat_retries_after_a_failed_write(monkeypatch):
    """기록에 실패한 tick 은 조임 시계를 전진시키지 않는다 — 다음 tick 이 다시 시도한다."""
    runner = _load(_RQ_RUNNER)
    probe, _ = _mixin_probe(runner)
    monkeypatch.setattr(runner, "emit_heartbeat", lambda *a, **k: False)
    t0 = datetime.datetime(2026, 9, 8, 0, 0, 0)

    assert probe.maybe_emit_db_heartbeat(t0) is False
    assert probe._last_db_heartbeat_at is None

    monkeypatch.setattr(runner, "emit_heartbeat", lambda *a, **k: True)
    assert probe.maybe_emit_db_heartbeat(t0 + datetime.timedelta(seconds=1)) is True


def test_rq_worker_class_wraps_rq_heartbeat():
    """mixin 이 rq Worker 앞에 서야 ``heartbeat()`` 가 우리 것을 먼저 탄다."""
    runner = _load(_RQ_RUNNER)
    order = runner.HeartbeatWorker.__mro__
    assert order.index(runner.HeartbeatWorkerMixin) < order.index(runner.Worker)


# --------------------------------------------------------------------------- #
# 5. SIDEFX outbox 워커 — 잡은 예외가 Sentry 로 간다 (F-7)
# --------------------------------------------------------------------------- #
def _init_sentry_with(monkeypatch, *, dsn: str, client_active: bool) -> list:
    """``init_sentry_once`` 를 주어진 상태에서 돌리고 init 호출 횟수를 돌려준다."""
    import sentry_sdk
    from foms.platform import sentry_setup

    calls = []
    if dsn:
        monkeypatch.setenv(loop_heartbeat.SENTRY_DSN_ENV, dsn)
    else:
        monkeypatch.delenv(loop_heartbeat.SENTRY_DSN_ENV, raising=False)
    monkeypatch.setattr(sentry_sdk, "get_client",
                        lambda: SimpleNamespace(is_active=lambda: client_active))
    monkeypatch.setattr(sentry_setup, "init_sentry", lambda: calls.append(True) or True)

    loop_heartbeat.init_sentry_once()
    return calls


def test_worker_sentry_is_attached_when_a_dsn_is_set(monkeypatch):
    """app.py 를 안 거치는 워커도 DSN 이 있으면 Sentry 를 붙인다."""
    assert _init_sentry_with(monkeypatch, dsn="https://public@example.invalid/1",
                             client_active=False) == [True]


def test_worker_sentry_is_not_reinitialized(monkeypatch):
    """음성 대조군 — 이미 붙어 있으면 다시 부르지 않는다(앞 클라이언트가 교체된다)."""
    assert _init_sentry_with(monkeypatch, dsn="https://public@example.invalid/1",
                             client_active=True) == []


def test_worker_sentry_is_skipped_without_a_dsn(monkeypatch):
    """DSN 이 없으면 아무것도 하지 않는다(foms.platform 을 열지 않기 위해서다)."""
    assert _init_sentry_with(monkeypatch, dsn="", client_active=False) == []


def test_sentry_env_name_matches_the_platform_constant():
    """게이트가 보는 env 이름이 정본과 갈리면 워커가 조용히 Sentry 없이 뜬다."""
    from foms.platform.sentry_setup import SENTRY_DSN_ENV

    assert loop_heartbeat.SENTRY_DSN_ENV == SENTRY_DSN_ENV


def test_outbox_worker_initializes_sentry_and_reports_step_failures(monkeypatch):
    """SIDEFX 워커의 잡은 예외가 지금까지 아무 데도 안 갔다 — 이제 Sentry 로 간다."""
    outbox = _load(_REPO_ROOT / "tools" / "ops" / "run_domain_side_effect_outbox.py")
    captured = []
    monkeypatch.setattr(outbox, "capture_exception", lambda *a, **k: captured.append(True))

    def _boom():
        raise RuntimeError("delivery step exploded")

    assert outbox._safe(_boom, "delivery") is False
    assert captured == [True], "잡은 예외가 Sentry 로 안 갔다"
    assert outbox._safe(lambda: None, "delivery") is True
    assert captured == [True], "성공한 step 까지 Sentry 로 보냈다"


def test_outbox_worker_calls_the_sentry_gate_on_startup():
    """호출처가 없으면 배선이 있어도 안 붙는다 — main 이 게이트를 부르는지 본다."""
    source = (_REPO_ROOT / "tools" / "ops" / "run_domain_side_effect_outbox.py").read_text(
        encoding="utf-8")
    assert "init_sentry_once(" in source.split("def main(", 1)[1]
