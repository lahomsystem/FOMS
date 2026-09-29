"""WORKER 감독자(``tools/ops/worker_supervisor.py``)를 **실행**해서 확인하는 계약.

예전 셸 감시 루프는 dash 문법이라 윈도우에서 실행 시험을 못 했고, 글자만 검사했다. 감독자는
파이썬이라 여기서 실제로 돌린다: 가짜 자식(시계·잠 주입)으로 재시작·대기·전단계를, 진짜 자식
프로세스로 정지 신호 전달·강제 종료를 본다.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.support.worker_jobs import jobs, load_supervisor


class _FakeProc:
    """``poll()`` 결과를 미리 정한 가짜 자식."""

    _next_pid = 100

    def __init__(self, argv, lifetime: float, rc: int, clock) -> None:
        _FakeProc._next_pid += 1
        self.pid = _FakeProc._next_pid
        self.argv = tuple(argv)
        self._end = clock() + lifetime
        self._rc = rc
        self._clock = clock
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        if self.returncode is None and self._clock() >= self._end:
            self.returncode = self._rc
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


class _Harness:
    """가짜 시계·잠·spawn 을 묶는다. ``lifetimes[argv[1]]`` = (살아 있는 초, 종료 코드)."""

    def __init__(self, lifetimes) -> None:
        self.now = 0.0
        self.lifetimes = lifetimes
        self.spawned: list[_FakeProc] = []
        self.logs: list[str] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def spawn(self, argv):
        lifetime, rc = self.lifetimes[argv[1]]
        proc = _FakeProc(argv, lifetime, rc, self.clock)
        self.spawned.append(proc)
        return proc

    def starts_of(self, script: str) -> list[float]:
        return [line for line in self.logs if line.startswith("[supervisor] start") and script in line]


def _supervisor(mod, harness, job_list, **kw):
    return mod.Supervisor(job_list, spawn=harness.spawn, clock=harness.clock, sleep=harness.sleep,
                          log=harness.logs.append, reap_orphans=False, **kw)


def _run_for(sup, harness, seconds: float) -> None:
    end = harness.now + seconds
    while harness.now < end:
        sup.step()
        harness.sleep(0.5)


def test_a_job_that_exits_is_restarted_with_doubling_backoff() -> None:
    mod = load_supervisor()
    h = _Harness({"crash.py": (1, 3)})
    sup = _supervisor(mod, h, [mod.Job("crash", ("python", "crash.py"))])
    _run_for(sup, h, 40)
    exits = [line for line in h.logs if "exited" in line]
    assert "rc=3" in exits[0] and "restarting in 10s" in exits[0]
    assert "restarting in 20s" in exits[1]
    assert len(h.spawned) == 3  # t=0, ~11, ~32


def test_a_long_run_resets_the_backoff() -> None:
    mod = load_supervisor()
    h = _Harness({"long.py": (70, 0)})
    sup = _supervisor(mod, h, [mod.Job("long", ("python", "long.py"))])
    _run_for(sup, h, 80)
    assert any("exited rc=0 after 70s - restarting in 5s" in line for line in h.logs), h.logs


def test_one_crashing_job_does_not_disturb_the_others() -> None:
    mod = load_supervisor()
    h = _Harness({"crash.py": (1, 1), "steady.py": (10_000, 0)})
    sup = _supervisor(mod, h, [mod.Job("crash", ("python", "crash.py")),
                               mod.Job("steady", ("python", "steady.py"))])
    _run_for(sup, h, 60)
    steady = [p for p in h.spawned if p.argv[1] == "steady.py"]
    assert len(steady) == 1 and steady[0].returncode is None


def test_pre_step_runs_before_every_start_and_its_failure_does_not_block() -> None:
    mod = load_supervisor()
    h = _Harness({"wait.py": (2, 1), "rq.py": (1, 0)})
    sup = _supervisor(mod, h, [mod.Job("rq", ("python", "rq.py"), pre_argv=("python", "wait.py"))])
    _run_for(sup, h, 30)
    order = [p.argv[1] for p in h.spawned]
    assert order[:4] == ["wait.py", "rq.py", "wait.py", "rq.py"], order


def test_stop_terminates_every_child_and_returns_zero() -> None:
    mod = load_supervisor()
    h = _Harness({"a.py": (10_000, 0), "b.py": (10_000, 0)})
    sup = _supervisor(mod, h, [mod.Job("a", ("python", "a.py")), mod.Job("b", ("python", "b.py"))])
    _run_for(sup, h, 2)
    sup.request_stop()
    assert sup.run() == 0
    assert all(p.terminated for p in h.spawned) and not any(p.killed for p in h.spawned)


def test_a_child_ignoring_term_is_killed_after_the_grace_period() -> None:
    mod = load_supervisor()
    h = _Harness({"stubborn.py": (10_000, 0)})
    sup = _supervisor(mod, h, [mod.Job("stubborn", ("python", "stubborn.py"))], stop_grace=3)
    _run_for(sup, h, 1)
    proc = h.spawned[0]
    proc.terminate = lambda: setattr(proc, "terminated", True)  # TERM 을 무시한다
    sup.request_stop()
    sup.run()
    assert proc.terminated and proc.killed
    assert any("did not stop in 3s - KILL" in line for line in h.logs)


def test_real_child_process_is_restarted_and_stopped() -> None:
    """진짜 자식 프로세스로 한 바퀴: 즉시 끝나는 자식은 다시 뜨고, 정지는 오래 자는 자식을 끝낸다."""
    mod = load_supervisor()
    quick = mod.Job("quick", (sys.executable, "-c", "import sys; sys.exit(7)"))
    sleeper = mod.Job("sleeper", (sys.executable, "-c", "import time; time.sleep(60)"))
    logs: list[str] = []
    sup = mod.Supervisor([quick, sleeper], log=logs.append, stop_grace=10, reap_orphans=False)
    try:
        deadline = __import__("time").monotonic() + 20
        while not any("quick exited rc=7" in line for line in logs):
            sup.step()
            __import__("time").sleep(0.1)
            assert __import__("time").monotonic() < deadline, logs
    finally:
        sup.request_stop()
        assert sup.shutdown() == 0
    sleeper_proc = [s.proc for s in sup.slots if s.job.name == "sleeper"][0]
    assert sleeper_proc.poll() is not None, "정지 뒤에도 자식이 살아 있다"


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, ["rq_worker"]),
        ({"FOMS_NAVER_SETTLE_SYNC_ENABLED": "1"}, ["naver_settle_sync", "rq_worker"]),
        ({"FOMS_NAVER_SETTLE_SYNC_ENABLED": "0"}, ["rq_worker"]),
    ],
)
def test_enable_flags_select_the_jobs(env, expected) -> None:
    assert [job.name for job in jobs(env)] == expected


def test_all_loops_can_be_enabled_and_queue_consumer_is_last() -> None:
    names = [job.name for job in jobs(all_enabled=True)]
    assert names[-1] == "rq_worker"
    assert len(names) == 6, names


def test_print_jobs_redacts_the_redis_url(capsys, monkeypatch) -> None:
    mod = load_supervisor()
    monkeypatch.setenv("REDIS_URL", "redis://default:s3cret@host:6379")
    assert mod.main(["--print-jobs"]) == 0
    out = capsys.readouterr().out
    assert "s3cret" not in out and "<redacted>" in out


def test_supervisor_module_runs_as_a_script_without_the_app() -> None:
    """``python tools/ops/worker_supervisor.py`` 가 앱을 import 하지 않고 뜬다(콜드스타트·격리)."""
    from tests.support.worker_jobs import SUPERVISOR_PATH

    out = subprocess.run([sys.executable, str(SUPERVISOR_PATH), "--print-jobs"],
                         capture_output=True, text=True, timeout=60, env={"PATH": "", "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert out.returncode == 0, out.stderr
    assert "rq_worker:" in out.stdout
