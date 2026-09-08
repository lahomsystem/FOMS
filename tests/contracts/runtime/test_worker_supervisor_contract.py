"""WORKER 컨테이너의 rq 감시 루프 계약 (2026-09-08 운영 사고 근본 수정).

사고: 운영 승격 배포로 WORKER 와 Redis 가 함께 재기동하다 Redis 가 뒤늦게 내려갔고,
rq 가 ``Redis connection timeout, quitting...`` 으로 스스로 종료했다. 큐 소비 러너
(``tools/ops/run_rq_worker.py``)가 ``exec`` 로 PID 1 을 잡고 있어 컨테이너째 죽었고,
Railway 재시작 정책(ON_FAILURE)이 그 종료를 실패로 보지 않아 워커가 영구 정지했다.
발주확인 6건이 큐에 11분 넘게 갇혔다.

부팅 레이스는 ``wait_for_redis`` 가 이미 막지만 **운행 중 Redis 재시작은 못 막는다**.
그래서 PID 1 은 감시 루프가 잡고, rq 가 어떤 종료 코드로 죽든 다시 띄운다. 이 계약은
그 구조가 조용히 원복되지 않게 못 박는다 — 되돌아가면 다음 Redis 재시작에 또 멈춘다.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_START_SH = _REPO_ROOT / "start.sh"
_WORKER_TOML = _REPO_ROOT / "railway-worker.toml"
_PROCFILE = _REPO_ROOT / "Procfile"


def _worker_branch() -> str:
    """start.sh 의 ``USE_RQ_WORKER=1`` 분기 본문만 잘라 돌려준다.

    Returns:
        WORKER 분기 안의 셸 스크립트 본문(주석 포함).
    """
    text = _START_SH.read_text(encoding="utf-8")
    return text.split('if [ "$USE_RQ_WORKER" = "1" ]; then', 1)[1].split("\nelse\n", 1)[0]


def test_queue_consumer_is_not_pid_one() -> None:
    """큐 소비자를 ``exec`` 로 띄우면 그 종료 = 컨테이너 종료라 사고가 재현된다."""
    branch = _worker_branch()
    for line in branch.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # 사고 경위를 적은 주석에는 exec 표기가 남아 있다.
        assert not stripped.startswith("exec "), (
            "큐 소비자를 exec 로 띄우면 안 된다 — 감시 루프가 PID 1 을 잡아야 한다"
        )


def test_supervisor_loop_restarts_rq_and_rewaits_redis() -> None:
    """감시 루프가 rq 를 백그라운드로 띄우고, 죽으면 Redis 를 다시 기다렸다 재기동한다."""
    branch = _worker_branch()
    assert "while true; do" in branch, "감시 루프가 없다"
    assert 'python tools/ops/run_rq_worker.py --url "$REDIS_URL" --queues default &' in branch, (
        "러너는 백그라운드로 띄우고 wait 로 지켜봐야 트랩이 걸린다. rq CLI 를 직접 부르면 "
        "RQ_WORKER 하트비트가 사라져 감시 표가 다시 눈을 잃는다"
    )
    assert 'wait "$RQ_PID"' in branch, "러너 종료를 wait 로 감지해야 한다"
    loop = branch.split("while true; do", 1)[1]
    assert "wait_for_redis.py" in loop, (
        "재기동 전에 Redis PING 을 다시 기다려야 한다 — 안 그러면 즉사 루프가 된다"
    )
    assert "[rq-supervisor]" in loop, "재기동 사실이 로그에 남아야 사후 추적이 된다"


def test_supervisor_forwards_sigterm_for_graceful_stop() -> None:
    """Railway 정지·재배포(SIGTERM)를 러너에 넘겨야 진행 중 잡이 정상 종료된다."""
    branch = _worker_branch()
    assert "trap _rq_forward_term TERM INT" in branch, "SIGTERM 트랩이 없다"
    assert 'kill -TERM "$RQ_PID"' in branch, "트랩이 러너에 신호를 넘겨야 한다"


def test_supervisor_backs_off_on_hot_crash_loop() -> None:
    """즉사가 반복되면 재시도 간격을 늘려 로그 폭주를 막는다(상한 60초)."""
    branch = _worker_branch()
    assert "RQ_BACKOFF=$(( RQ_BACKOFF * 2 ))" in branch
    assert "RQ_BACKOFF=60" in branch, "backoff 상한이 없으면 무한히 늘어난다"


def test_no_deploy_entrypoint_bypasses_start_sh() -> None:
    """rq 를 직접 부르는 시작 명령이 남아 있으면 그 경로만 감시 없이 뜬다."""
    for path in (_WORKER_TOML, _PROCFILE):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "rq worker" not in stripped, (
                f"{path.name} 이 rq 를 직접 띄운다 — start.sh 를 거쳐야 감시 루프가 붙는다"
            )
