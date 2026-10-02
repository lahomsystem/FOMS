"""WORKER 부팅 순서 계약 — 큐 소비자(rq)가 먼저 혼자 뜨고, 루프는 그 뒤에 켠다(성능 원장 P2-6).

운영 실측(2026-10-01, 30일): WORKER 재배포 244회. Railway 는 새 컨테이너 시작 약 7초 뒤 옛
컨테이너를 내리는데(healthcheck 없음), 감독자가 자식 6개를 한꺼번에 켜서 CPU 1개를 나눠 앱을
import 하느라 새 rq 의 ``*** Listening on`` 이 p50 20초 · p90 35초 뒤에야 나왔다. 그 사이 큐를
처리하는 프로세스가 0개인 구간이 157회, 합계 44분이었다(최대 248초는 Redis 장애).

여기서 지키는 것:

* 루프 5종은 ``deferred`` — rq 가 준비 표식 파일을 만들거나 최대 N초가 지나야 켜진다.
* 문은 한 번 열리면 닫히지 않는다(운행 중 rq 재시작이 루프를 붙잡지 않는다).
* N=0 이면 예전처럼 모두 같은 tick 에 켜진다(되돌리기 스위치 — 음성 대조군).
* rq 러너는 ``bootstrap()`` 이 끝난 직후에 표식을 만들고, 듣기 전에 잡 모듈을 미리 연다.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import time
from types import SimpleNamespace

import pytest

from tests.support.worker_jobs import jobs, load_supervisor

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_RQ_RUNNER = _REPO_ROOT / "tools" / "ops" / "run_rq_worker.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_rq_worker_boot_ut", _RQ_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Proc:
    """정해진 초만큼 살아 있는 가짜 자식."""

    def __init__(self, argv, lifetime, clock) -> None:
        self.argv, self.pid, self.returncode = tuple(argv), id(self) % 100000, None
        self._end, self._clock = clock() + lifetime, clock
        self.terminated = False

    def poll(self):
        if self.returncode is None and self._clock() >= self._end:
            self.returncode = 1
        return self.returncode

    def terminate(self):
        self.terminated, self.returncode = True, -15

    def kill(self):
        self.returncode = -9


class _Harness:
    def __init__(self, lifetimes, ready_at=None) -> None:
        self.now, self.lifetimes, self.ready_at = 0.0, lifetimes, ready_at
        self.spawned: list[tuple[float, _Proc]] = []
        self.logs: list[str] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def spawn(self, argv):
        proc = _Proc(argv, self.lifetimes[argv[1]], self.clock)
        self.spawned.append((self.now, proc))
        return proc

    def ready(self) -> bool:
        return self.ready_at is not None and self.now >= self.ready_at

    def first_spawn(self, script: str):
        return next((t for t, p in self.spawned if p.argv[1] == script), None)

    def run(self, sup, seconds: float) -> None:
        end = self.now + seconds
        while self.now < end:
            sup.step()
            self.sleep(0.5)


def _jobs(mod):
    return [mod.Job("loop", ("python", "loop.py"), deferred=True),
            mod.Job("rq_worker", ("python", "rq.py"), pre_argv=("python", "wait.py"))]


def _supervisor(mod, h, defer):
    return mod.Supervisor(_jobs(mod), spawn=h.spawn, clock=h.clock, sleep=h.sleep, log=h.logs.append,
                          reap_orphans=False, defer_seconds=defer, ready_probe=h.ready)


# --- 배선 ---------------------------------------------------------------------------------
def test_every_loop_is_deferred_and_the_queue_consumer_is_not() -> None:
    listed = jobs(all_enabled=True)
    assert len(listed) == 6, [j.name for j in listed]
    assert [j.name for j in listed if not j.deferred] == ["rq_worker"]
    assert load_supervisor().Job("x", ("python", "x.py")).deferred is False  # 음성 대조: 기본은 안 미룸


# --- 감독자 동작 --------------------------------------------------------------------------
def test_queue_consumer_starts_alone_and_loops_follow_its_ready_marker() -> None:
    mod = load_supervisor()
    h = _Harness({"wait.py": 1, "rq.py": 10_000, "loop.py": 10_000}, ready_at=6.0)
    h.run(_supervisor(mod, h, defer=30), 20)
    assert h.first_spawn("wait.py") == 0.0
    assert h.first_spawn("loop.py") == 6.0, h.spawned
    assert any("deferring loop until the queue consumer is ready (max 30s)" in l for l in h.logs)
    assert any("queue consumer ready after 6.0s - starting deferred jobs" in l for l in h.logs), h.logs


def test_loops_start_at_the_deadline_when_the_queue_consumer_never_gets_ready() -> None:
    mod = load_supervisor()
    h = _Harness({"wait.py": 1, "rq.py": 10_000, "loop.py": 10_000}, ready_at=None)
    h.run(_supervisor(mod, h, defer=12), 20)
    assert h.first_spawn("loop.py") == 12.0, h.spawned
    assert any("queue consumer not ready yet after 12.0s" in l for l in h.logs), h.logs


def test_zero_defer_starts_everything_in_the_first_tick() -> None:
    """되돌리기 스위치 — 예전 동작(모두 동시에)과 같아야 한다."""
    mod = load_supervisor()
    h = _Harness({"wait.py": 1, "rq.py": 10_000, "loop.py": 10_000}, ready_at=None)
    h.run(_supervisor(mod, h, defer=0), 2)
    assert h.first_spawn("loop.py") == 0.0 and h.first_spawn("wait.py") == 0.0
    assert not any("deferring" in l for l in h.logs)


def test_the_gate_stays_open_when_the_queue_consumer_restarts_later() -> None:
    mod = load_supervisor()
    h = _Harness({"wait.py": 1, "rq.py": 20, "loop.py": 3}, ready_at=2.0)
    sup = _supervisor(mod, h, defer=30)
    h.run(sup, 2.5)
    h.ready_at = None  # rq 가 죽고 표식이 사라진 상황과 같다 — 루프 재시작은 기다리면 안 된다
    h.run(sup, 40)
    loop_starts = [t for t, p in h.spawned if p.argv[1] == "loop.py"]
    assert len(loop_starts) >= 3, loop_starts  # 3초마다 죽는 루프가 백오프대로 다시 켜진다
    assert len([1 for _, p in h.spawned if p.argv[1] == "rq.py"]) >= 2


def test_stop_while_deferring_terminates_what_started_and_never_starts_the_rest() -> None:
    mod = load_supervisor()
    h = _Harness({"wait.py": 1, "rq.py": 10_000, "loop.py": 10_000}, ready_at=None)
    sup = _supervisor(mod, h, defer=30)
    h.run(sup, 3)
    sup.request_stop()
    assert sup.run() == 0
    assert h.first_spawn("loop.py") is None
    assert all(p.terminated for _, p in h.spawned if p.argv[1] == "rq.py")


def test_probe_errors_count_as_not_ready() -> None:
    mod = load_supervisor()
    h = _Harness({"wait.py": 1, "rq.py": 10_000, "loop.py": 10_000})

    def broken() -> bool:
        raise OSError("disk")

    sup = mod.Supervisor(_jobs(mod), spawn=h.spawn, clock=h.clock, sleep=h.sleep, log=h.logs.append,
                         reap_orphans=False, defer_seconds=5, ready_probe=broken)
    h.run(sup, 8)
    assert h.first_spawn("loop.py") == 5.0


# --- 진입점 배선 --------------------------------------------------------------------------
def test_ready_file_env_name_is_the_same_on_both_sides() -> None:
    assert load_supervisor().RQ_READY_FILE_ENV == _load_runner().READY_FILE_ENV


def test_prepare_ready_file_plants_the_path_and_clears_a_stale_marker(tmp_path) -> None:
    mod = load_supervisor()
    stale = tmp_path / "ready"
    stale.write_text("old", encoding="utf-8")
    env = {mod.RQ_READY_FILE_ENV: str(stale)}
    assert mod.prepare_ready_file(env) == str(stale)
    assert not stale.exists(), "옛 표식이 남으면 rq 가 준비되기 전에 문이 열린다"
    fresh: dict = {}
    path = mod.prepare_ready_file(fresh)
    assert fresh[mod.RQ_READY_FILE_ENV] == path and str(os.getpid()) in path


@pytest.mark.parametrize("raw, expected", [(None, 30.0), ("12", 12.0), ("0", 0.0), ("abc", 30.0)])
def test_main_reads_the_defer_env_and_probes_the_ready_file(monkeypatch, tmp_path, raw, expected) -> None:
    mod = load_supervisor()
    marker = tmp_path / "marker"
    monkeypatch.setenv(mod.RQ_READY_FILE_ENV, str(marker))
    monkeypatch.delenv(mod.TEMPLATE_WARM_SKIP_ENV, raising=False)
    if raw is None:
        monkeypatch.delenv(mod.DEFER_LOOPS_ENV, raising=False)
    else:
        monkeypatch.setenv(mod.DEFER_LOOPS_ENV, raw)
    seen = {}
    monkeypatch.setattr(mod.signal, "signal", lambda *a: None)
    monkeypatch.setattr(mod.Supervisor, "run", lambda self: seen.setdefault("sup", self) and 0)
    assert mod.main([]) == 0
    sup = seen["sup"]
    assert sup._defer_seconds == expected
    assert sup._probe_ready() is False
    marker.write_text("1", encoding="utf-8")
    assert sup._probe_ready() is True


# --- rq 러너 ------------------------------------------------------------------------------
def test_runner_marks_ready_right_after_rq_bootstrap(monkeypatch, tmp_path) -> None:
    runner = _load_runner()
    marker = tmp_path / "ready"
    calls = []
    monkeypatch.setattr(runner.Worker, "bootstrap",
                        lambda self, *a, **k: calls.append(("rq", marker.exists())), raising=False)
    monkeypatch.setenv(runner.READY_FILE_ENV, str(marker))
    worker = runner.HeartbeatWorker.__new__(runner.HeartbeatWorker)
    runner.HeartbeatWorker.bootstrap(worker, "INFO")
    assert calls == [("rq", False)], "rq 가 듣기 시작하기 전에 표식을 만들면 안 된다"
    assert marker.exists()


def test_mark_ready_is_quiet_without_a_path_and_survives_write_errors(tmp_path) -> None:
    runner = _load_runner()
    assert runner.mark_ready({}) is False
    assert runner.mark_ready({runner.READY_FILE_ENV: str(tmp_path / "missing-dir" / "x")}) is False


def test_preload_covers_the_module_every_enqueued_job_lives_in() -> None:
    from foms.services.jobs import queue
    from foms.services.notifications import push_sender

    runner = _load_runner()
    assert queue._TASK_PATH_PREFIX in runner.PRELOAD_MODULES
    assert push_sender._PUSH_TASK.rsplit(".", 1)[0] in runner.PRELOAD_MODULES
    assert "foms.services.storage" in runner.PRELOAD_MODULES  # 썸네일 잡의 R2 초기화


def test_preload_warms_storage_without_keeping_an_adapter(monkeypatch) -> None:
    import foms.services.storage as storage

    runner = _load_runner()
    made = []
    monkeypatch.setattr(storage, "StorageAdapter", lambda: made.append(1))
    monkeypatch.setattr(storage, "_storage_instance", None)
    assert runner.preload_job_modules({}) == list(runner.PRELOAD_MODULES)
    assert made == [1]
    assert storage._storage_instance is None, "부모가 어댑터를 쥐면 모든 잡 자식이 그것을 나눠 쓴다"


def test_preload_can_be_switched_off_and_never_raises(monkeypatch) -> None:
    runner = _load_runner()
    assert runner.preload_job_modules({runner.PRELOAD_ENV: "0"}) == []
    monkeypatch.setattr(runner, "PRELOAD_MODULES", ("foms.no_such_module_for_test", "json"))
    assert runner.preload_job_modules({}) == ["json"], "하나가 실패해도 나머지는 연다"


def test_runner_preloads_before_it_starts_listening(monkeypatch) -> None:
    runner = _load_runner()
    order = []
    monkeypatch.setattr(runner, "init_sentry_once", lambda *a: None)
    monkeypatch.setattr(runner, "Redis", SimpleNamespace(from_url=lambda url: object()))
    monkeypatch.setattr(runner, "Queue", lambda name, connection: name)
    monkeypatch.setattr(runner, "preload_job_modules", lambda env: order.append("preload") or [])

    class _W:
        def __init__(self, queues, connection) -> None:
            pass

        def work(self, **kw):
            order.append("work")

    monkeypatch.setattr(runner, "HeartbeatWorker", _W)
    assert runner.main(["--url", "redis://x"]) == 0
    assert order == ["preload", "work"]


# --- 진짜 프로세스 한 바퀴 ------------------------------------------------------------------
def test_real_processes_loop_waits_for_the_ready_marker(monkeypatch, tmp_path) -> None:
    mod = load_supervisor()
    marker = tmp_path / "ready"
    monkeypatch.setenv(mod.RQ_READY_FILE_ENV, str(marker))
    rq = mod.Job("rq_worker", (sys.executable, "-c",
                               "import os, time; time.sleep(1.0); "
                               f"open(os.environ['{mod.RQ_READY_FILE_ENV}'], 'w').write('1'); time.sleep(60)"))
    loop = mod.Job("loop", (sys.executable, "-c", "import time; time.sleep(60)"), deferred=True)
    logs: list[str] = []
    sup = mod.Supervisor([loop, rq], log=logs.append, stop_grace=10, reap_orphans=False,
                         defer_seconds=30, ready_probe=marker.exists)
    try:
        deadline = time.monotonic() + 30
        while not any("start loop" in line for line in logs):
            sup.step()
            time.sleep(0.1)
            assert time.monotonic() < deadline, logs
    finally:
        sup.request_stop()
        assert sup.shutdown() == 0
    ready_idx = next(i for i, l in enumerate(logs) if "queue consumer ready" in l)
    assert ready_idx < next(i for i, l in enumerate(logs) if "start loop" in l), logs
    assert next(i for i, l in enumerate(logs) if "start rq_worker" in l) < ready_idx
