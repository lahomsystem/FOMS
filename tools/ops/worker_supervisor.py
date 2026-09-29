"""WORKER 컨테이너의 배경 작업 감독자 — ``start.sh`` WORKER 가지가 ``exec`` 로 넘겨 PID 1 이 된다.

설계서: ``docs/specs/2026-09-29-worker-loop-supervisor-spec.md``.

왜 필요한가
-----------
- 2026-09-08: 큐 소비자(rq)를 ``exec`` 로 띄워 PID 1 이었는데, 운행 중 Redis 재시작에 rq 가
  스스로 끝나자 컨테이너째 멈췄다(Railway ON_FAILURE 는 정상 종료를 실패로 안 본다).
  → ``start.sh`` 에 셸 감시 루프를 붙였지만 **rq 하나만** 지켰다.
- 2026-09-10: ``&`` 로 한 번 띄운 네이버 정산 루프가 매일 05:31 성공 직후 죽었고, 감독자가
  없어 다음 배포까지 조용히 멈췄다. 나머지 루프 4개도 같은 처지였다.

이 모듈이 지키는 것
-------------------
- 작업 목록의 **정본**: :func:`worker_jobs`. 켜짐 조건 env·기본값은 예전 ``start.sh`` 의 ``&``
  줄들과 같다(``${VAR:-기본}`` = 비었거나 없으면 기본).
- 어떤 이유로 끝나든 다시 켠다. 대기는 작업마다 5초에서 두 배씩 최대 60초, 60초 이상 살았으면
  5초로 되돌린다(예전 셸 rq 감시 루프와 같은 규칙).
- 큐 소비자는 켜기 전마다 Redis PING 을 기다린다(실패해도 켠다 — 다음 바퀴에서 다시 기다림).
- TERM/INT: 모든 자식에 TERM → 최대 ``FOMS_SUPERVISOR_STOP_GRACE_SECONDS``(기본 25)초 기다림 →
  남은 자식 KILL → exit 0. rq 는 TERM 에 진행 중 잡을 마치고 끝난다.
- PID 1 이면 떠돌이 손자 프로세스(rq 작업 자식 등)도 거둬 좀비가 쌓이지 않게 한다.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

BACKOFF_START_SECONDS = 5
BACKOFF_MAX_SECONDS = 60
HEALTHY_RUN_SECONDS = 60
STOP_GRACE_ENV = "FOMS_SUPERVISOR_STOP_GRACE_SECONDS"
DEFAULT_STOP_GRACE_SECONDS = 25
TICK_SECONDS = 0.5


@dataclass(frozen=True)
class Job:
    """감독할 작업 하나.

    Attributes:
        name: 로그에 쓰는 이름.
        argv: 실행 명령(저장소 루트 기준 상대 경로).
        pre_argv: 켜기 **전마다** 먼저 돌릴 명령(끝날 때까지 기다리고, 실패해도 본 명령을 켠다).
    """

    name: str
    argv: tuple[str, ...]
    pre_argv: Optional[tuple[str, ...]] = None


def _env(env: Mapping[str, str], key: str, default: str) -> str:
    """셸 ``${KEY:-default}`` 와 같다 — 없거나 빈 값이면 기본값."""
    return env.get(key) or default


def worker_jobs(env: Mapping[str, str], python: str = sys.executable) -> list[Job]:
    """WORKER 컨테이너가 돌리는 작업 목록(배선의 정본).

    Args:
        env: 환경 변수(켜짐 조건·간격).
        python: 자식 프로세스에 쓸 파이썬.

    Returns:
        켤 작업 목록. 큐 소비자(``rq_worker``)는 항상 마지막에 있다.
    """
    jobs: list[Job] = []

    # P0 긴급 알림 escalation 스윕 (알림 Phase 3C): FOMS 에 in-process 스케줄러가 없어 WORKER 에서
    # long-running 루프로 돈다(--loop = 앱 1회 부팅 후 주기 스윕). 다중 replica 여도 멱등.
    if env.get("FOMS_ESCALATION_LOOP_ENABLED") == "1":
        jobs.append(Job("notification_escalation", (
            python, "scripts/maintenance/run_notification_escalation.py", "--loop",
            "--interval", _env(env, "FOMS_ESCALATION_INTERVAL_SECONDS", "60"), "--json")))

    # 네이버 스마트스토어 주문 수집 (NAVER-INGEST-01). **WORKER 에서만** 돈다 — 커머스API센터 호출 IP
    # 한도 3 = Railway static IP 3 이라 네이버로 나가는 HTTP 는 이 서비스 한 곳으로 모은다. 기본 off.
    if env.get("FOMS_NAVER_SYNC_ENABLED") == "1":
        jobs.append(Job("naver_order_sync", (
            python, "scripts/maintenance/run_naver_order_sync.py", "--loop",
            "--interval", _env(env, "FOMS_NAVER_SYNC_INTERVAL_SECONDS", "300"), "--json")))

    # 네이버 발송처리 자동 실행 (NAVER-AUTODISPATCH-01). 평일 정해진 시각(기본 16:50 KST)에 일괄
    # 발송처리를 대신한다. 되돌릴 수 없는 조작이라 기본 off, 하루 1회 계약은 서비스가 DB 로 지킨다.
    if env.get("FOMS_NAVER_AUTO_DISPATCH_ENABLED") == "1":
        jobs.append(Job("naver_auto_dispatch", (
            python, "scripts/maintenance/run_naver_auto_dispatch.py", "--loop",
            "--at", _env(env, "FOMS_NAVER_AUTO_DISPATCH_AT", "16:50"),
            "--window", _env(env, "FOMS_NAVER_AUTO_DISPATCH_WINDOW_MINUTES", "10"), "--json")))

    # 네이버 정산 동기화 (SETTLE-CHANNEL-01 §4). 새벽(기본 05:30 KST)에 돈다. 파티션 통째 교체라
    # 창 안에서 여러 번 깨어나도 결과가 같다(멱등). 기본 off.
    if env.get("FOMS_NAVER_SETTLE_SYNC_ENABLED") == "1":
        jobs.append(Job("naver_settle_sync", (
            python, "scripts/maintenance/run_naver_settle_sync.py", "--loop",
            "--at", _env(env, "FOMS_NAVER_SETTLE_SYNC_AT", "05:30"),
            "--window", _env(env, "FOMS_NAVER_SETTLE_SYNC_WINDOW_MINUTES", "10"), "--json")))

    # 좌표 스윕 (GEO-SWEEP-01): 좌표 없는 주문을 미리 지오코딩 큐에 넣는다. 스윕은 멱등(enqueue 전에
    # pending + 시도 표식을 커밋)이라 replica 가 여럿이어도 큐가 부풀지 않는다.
    if env.get("FOMS_GEOCODE_SWEEP_ENABLED") == "1":
        jobs.append(Job("geocode_sweep", (
            python, "scripts/maintenance/run_geocode_sweep.py", "--loop",
            "--interval", _env(env, "FOMS_GEOCODE_SWEEP_INTERVAL_SECONDS", "60"), "--json")))

    # 큐 소비 본체. `rq worker` CLI 대신 러너를 쓰는 이유: rq 하트비트 자리에서 RQ_WORKER 행을
    # side_effect_worker_heartbeats 에 함께 남긴다(2026-02 워커 offline 을 표만 봐서 몰랐다).
    redis_url = env.get("REDIS_URL", "")
    jobs.append(Job(
        "rq_worker",
        (python, "tools/ops/run_rq_worker.py", "--url", redis_url, "--queues", "default"),
        pre_argv=(python, "tools/ops/wait_for_redis.py", "--url", redis_url,
                  "--timeout", _env(env, "FOMS_REDIS_WAIT_SECONDS", "300")),
    ))
    return jobs


@dataclass
class _Slot:
    job: Job
    proc: Any = None
    phase: str = "idle"  # idle | pre | main
    started_at: float = 0.0
    next_start: float = 0.0
    backoff: int = BACKOFF_START_SECONDS


def next_backoff(previous: int, ran_seconds: float) -> int:
    """다음 재시작까지 기다릴 초. 오래 살았으면 되돌리고, 즉사가 반복되면 두 배씩(상한 60)."""
    if ran_seconds >= HEALTHY_RUN_SECONDS:
        return BACKOFF_START_SECONDS
    return min(previous * 2, BACKOFF_MAX_SECONDS)


class Supervisor:
    """작업들을 켜고, 끝나면 대기 뒤 다시 켜고, 정지 신호에 모두 정리한다."""

    def __init__(
        self,
        jobs: Sequence[Job],
        *,
        spawn: Optional[Callable[[Sequence[str]], Any]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = lambda line: print(line, flush=True),
        stop_grace: float = DEFAULT_STOP_GRACE_SECONDS,
        reap_orphans: Optional[bool] = None,
    ) -> None:
        self.slots = [_Slot(job) for job in jobs]
        self._spawn = spawn or self._default_spawn
        self._clock = clock
        self._sleep = sleep
        self._log = log
        self._stop_grace = stop_grace
        self._reap = (os.name == "posix" and os.getpid() == 1) if reap_orphans is None else reap_orphans
        self.stopping = False

    @staticmethod
    def _default_spawn(argv: Sequence[str]) -> subprocess.Popen:
        # 자식은 표준 출력·오류를 그대로 물려받는다 — 로그가 지금처럼 Railway 로 바로 간다.
        return subprocess.Popen(list(argv), cwd=str(REPO_ROOT))

    def request_stop(self, *_args: Any) -> None:
        """신호 처리기. 다음 tick 에 정리를 시작한다."""
        self.stopping = True

    # --- 한 tick ---------------------------------------------------------------------------
    def step(self) -> None:
        """끝난 자식을 거두고, 때가 된 작업을 켠다."""
        now = self._clock()
        self._reap_orphans()
        for slot in self.slots:
            if slot.proc is None:
                if now >= slot.next_start:
                    self._start(slot, now)
                continue
            rc = slot.proc.poll()
            if rc is None:
                continue
            if slot.phase == "pre":
                self._launch_main(slot, now)
                continue
            ran = now - slot.started_at
            slot.backoff = next_backoff(slot.backoff, ran)
            self._log(f"[supervisor] {slot.job.name} exited rc={rc} after {int(ran)}s "
                      f"- restarting in {slot.backoff}s")
            slot.proc, slot.phase, slot.next_start = None, "idle", now + slot.backoff

    def _start(self, slot: _Slot, now: float) -> None:
        if slot.job.pre_argv:
            slot.proc, slot.phase = self._spawn(slot.job.pre_argv), "pre"
        else:
            self._launch_main(slot, now)

    def _launch_main(self, slot: _Slot, now: float) -> None:
        slot.proc, slot.phase, slot.started_at = self._spawn(slot.job.argv), "main", now
        self._log(f"[supervisor] start {slot.job.name} pid={getattr(slot.proc, 'pid', '?')}")

    def _reap_orphans(self) -> None:
        """PID 1 일 때 떠돌이 자식을 거둔다. 우리 자식이면 종료 코드를 Popen 에 넘겨준다."""
        if not self._reap:
            return
        mine = {getattr(s.proc, "pid", None): s.proc for s in self.slots if s.proc is not None}
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            proc = mine.get(pid)
            if proc is not None and getattr(proc, "returncode", None) is None:
                proc.returncode = os.waitstatus_to_exitcode(status)

    # --- 수명 ------------------------------------------------------------------------------
    def run(self) -> int:
        """정지 신호까지 돌고, 정리한 뒤 0 을 돌려준다."""
        names = ", ".join(slot.job.name for slot in self.slots)
        self._log(f"[supervisor] managing {len(self.slots)} job(s): {names}")
        while not self.stopping:
            self.step()
            self._sleep(TICK_SECONDS)
        return self.shutdown()

    def shutdown(self) -> int:
        """모든 자식에 TERM → 기한까지 기다림 → 남은 자식 KILL."""
        live = [s for s in self.slots if s.proc is not None and s.proc.poll() is None]
        self._log(f"[supervisor] stopping: TERM -> {', '.join(s.job.name for s in live) or '(none)'}")
        for slot in live:
            try:
                slot.proc.terminate()
            except OSError:
                pass
        deadline = self._clock() + self._stop_grace
        while self._clock() < deadline and any(s.proc.poll() is None for s in live):
            self._reap_orphans()
            self._sleep(0.2)
        for slot in live:
            if slot.proc.poll() is None:
                self._log(f"[supervisor] {slot.job.name} did not stop in {self._stop_grace}s - KILL")
                try:
                    slot.proc.kill()
                except OSError:
                    pass
        self._log("[supervisor] stopped")
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 진입점. ``--print-jobs`` 는 켤 작업 목록만 출력한다(확인용)."""
    parser = argparse.ArgumentParser(description="WORKER background job supervisor")
    parser.add_argument("--print-jobs", action="store_true", help="켤 작업 목록만 출력하고 끝낸다")
    args = parser.parse_args(argv)
    jobs = worker_jobs(os.environ)
    if args.print_jobs:
        for job in jobs:
            shown = list(job.argv[1:])
            for i, part in enumerate(shown[:-1]):
                if part == "--url":
                    shown[i + 1] = "<redacted>"  # REDIS_URL 에 비밀번호가 들어 있다
            print(f"{job.name}: {' '.join(shown)}")
        return 0
    try:
        grace = float(os.environ.get(STOP_GRACE_ENV) or DEFAULT_STOP_GRACE_SECONDS)
    except ValueError:
        grace = DEFAULT_STOP_GRACE_SECONDS
    supervisor = Supervisor(jobs, stop_grace=grace)
    signal.signal(signal.SIGTERM, supervisor.request_stop)
    signal.signal(signal.SIGINT, supervisor.request_stop)
    return supervisor.run()


if __name__ == "__main__":
    sys.exit(main())
