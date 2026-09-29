"""WORKER 컨테이너 감독 구조 계약 (2026-09-08 · 2026-09-10 운영 사고 근본 수정).

2026-09-08: 큐 소비 러너(``tools/ops/run_rq_worker.py``)가 ``exec`` 로 PID 1 을 잡고 있어, 운행 중
Redis 재시작에 rq 가 스스로 끝나자 컨테이너째 멈췄다(Railway ON_FAILURE 는 정상 종료를 실패로
안 본다). 발주확인 6건이 큐에 11분 넘게 갇혔다. → 셸 감시 루프.

2026-09-10: 그 감시 루프는 rq **하나만** 지켰다. ``&`` 로 한 번 띄운 네이버 정산 루프가 매일
05:31 에 죽고 다음 배포까지 멈춰 있었다. → 모든 배경 작업을 파이썬 감독자
(``tools/ops/worker_supervisor.py``)가 PID 1 로 지킨다(설계서
``docs/specs/2026-09-29-worker-loop-supervisor-spec.md``).

이 계약은 그 구조가 조용히 원복되지 않게 못 박는다. 감독자의 실제 동작(재시작·대기·신호)은
``test_worker_supervisor_process.py`` 가 실행으로 확인한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.support.worker_jobs import jobs, load_supervisor, worker_branch_of_start_sh

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKER_TOML = _REPO_ROOT / "railway-worker.toml"
_PROCFILE = _REPO_ROOT / "Procfile"


def _code_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def test_worker_branch_waits_for_redis_then_hands_pid_one_to_the_supervisor() -> None:
    lines = _code_lines(worker_branch_of_start_sh())
    assert lines[0].startswith("python tools/ops/wait_for_redis.py"), lines
    assert lines[-1] == "exec python tools/ops/worker_supervisor.py", (
        "PID 1 은 감독자가 잡아야 한다 — 큐 소비자나 루프를 exec 하면 그 종료 = 컨테이너 종료다"
    )


def test_nothing_in_the_worker_branch_is_started_unsupervised() -> None:
    """``&`` 로 띄운 프로세스는 감독자 밖이다 — 2026-09-10 사고의 모양."""
    for line in _code_lines(worker_branch_of_start_sh()):
        assert not re.search(r"&\s*$", line), f"감독자 밖에서 뜬다: {line}"
        assert not (line.startswith("exec ") and "worker_supervisor.py" not in line), line
    assert re.search(r"&\s*$", "python scripts/maintenance/run_x.py --loop &")  # negative control


def test_queue_consumer_is_supervised_with_a_redis_wait_before_every_start() -> None:
    rq = [job for job in jobs() if job.name == "rq_worker"]
    assert len(rq) == 1, "큐 소비자는 켜짐 조건 없이 항상 감독 대상이다"
    job = rq[0]
    assert job.argv[1:] == ("tools/ops/run_rq_worker.py", "--url", "", "--queues", "default"), (
        "rq CLI 를 직접 부르면 RQ_WORKER 하트비트가 사라져 감시 표가 다시 눈을 잃는다"
    )
    assert job.pre_argv is not None and "tools/ops/wait_for_redis.py" in job.pre_argv, (
        "재기동 전에 Redis PING 을 다시 기다려야 한다 — 안 그러면 즉사 루프가 된다"
    )


def test_backoff_doubles_to_sixty_and_resets_after_a_healthy_run() -> None:
    mod = load_supervisor()
    assert mod.next_backoff(5, 1) == 10
    assert mod.next_backoff(40, 1) == 60, "상한이 없으면 무한히 늘어난다"
    assert mod.next_backoff(60, 1) == 60
    assert mod.next_backoff(60, 61) == 5, "오래 살다 죽었으면 일시 장애 — 되돌린다"


def test_supervisor_installs_term_and_int_handlers(monkeypatch) -> None:
    """Railway 정지·재배포(SIGTERM)는 자식에 넘겨 진행 중 잡을 정상 종료시켜야 한다."""
    mod = load_supervisor()
    installed = {}
    monkeypatch.setattr(mod.signal, "signal", lambda sig, handler: installed.setdefault(sig, handler))
    monkeypatch.setattr(mod.Supervisor, "run", lambda self: 0)
    monkeypatch.setattr(mod.sys, "argv", ["worker_supervisor.py"])
    assert mod.main([]) == 0
    assert mod.signal.SIGTERM in installed and mod.signal.SIGINT in installed


def test_no_deploy_entrypoint_bypasses_start_sh() -> None:
    """rq 를 직접 부르는 시작 명령이 남아 있으면 그 경로만 감독 없이 뜬다."""
    for path in (_WORKER_TOML, _PROCFILE):
        for line in _code_lines(path.read_text(encoding="utf-8")):
            assert "rq worker" not in line, (
                f"{path.name} 이 rq 를 직접 띄운다 — start.sh 를 거쳐야 감독자가 붙는다"
            )
