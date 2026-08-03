"""``tools/ops/rq_failed_jobs.py`` 단위 테스트 (Redis 없이 동작).

fakeredis 가 requirements 에 없으므로 실제 Redis/RQ 대신 최소 stub job 과
``monkeypatch`` 로 검증한다. 확인 대상:

* 함수 이름별 집계·정렬·대표 에러(가장 최근 실패 건) 추출
* ``REDIS_URL`` 미설정 → 트레이스백 없이 exit 3
* Redis 도달 실패 → 트레이스백 없이 exit 2
* ``--requeue`` 기본 dry-run(실제 ``registry.requeue`` 미호출), ``--apply`` 시에만 호출
"""
import json
from datetime import datetime

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from tools.ops import rq_failed_jobs as cli

_PREFIX = "foms.services.jobs.tasks."


class _StubJob:
    """RQ Job 중 CLI 가 읽는 속성만 가진 최소 stub."""

    def __init__(self, job_id: str, func: str, ended_at, exc_info=None) -> None:
        self.id = job_id
        self.func_name = _PREFIX + func
        self.ended_at = ended_at
        self.exc_info = exc_info


class _StubRegistry:
    """``requeue`` 호출만 기록하는 registry stub."""

    def __init__(self) -> None:
        self.requeued: list[str] = []

    def requeue(self, job_id: str) -> None:
        self.requeued.append(job_id)


def _jobs() -> list:
    return [
        _StubJob("j1", "geocode_order_address", datetime(2026, 7, 30, 1, 0),
                 "Traceback...\nValueError: bad address"),
        _StubJob("j2", "geocode_order_address", datetime(2026, 7, 30, 5, 0),
                 "Traceback...\nTimeoutError: kakao timeout"),
        _StubJob("j3", "create_thumbnail_for_attachment", datetime(2026, 7, 29, 9, 0),
                 "Traceback...\nOSError: r2 down"),
    ]


def test_summarize_groups_and_picks_latest_error():
    """이름별 집계 + 최근 실패 시각/대표 에러, 실패 수 내림차순 정렬."""
    summary = cli.summarize_failed_jobs(_jobs() + [None])

    assert [row["job_name"] for row in summary] == [
        _PREFIX + "geocode_order_address",
        _PREFIX + "create_thumbnail_for_attachment",
    ]
    geo = summary[0]
    assert geo["count"] == 2
    assert geo["last_failed_at"] == "2026-07-30T05:00:00"
    assert geo["sample_job_id"] == "j2"
    assert geo["sample_error"] == "TimeoutError: kakao timeout"


def test_summarize_handles_missing_metadata():
    """``ended_at``/``exc_info`` 가 없어도 집계는 성공한다."""
    summary = cli.summarize_failed_jobs([_StubJob("j9", "send_push_for_notification_task", None)])

    assert summary[0]["count"] == 1
    assert summary[0]["last_failed_at"] is None
    assert summary[0]["sample_job_id"] == "j9"
    assert summary[0]["sample_error"] is None


def test_select_requeue_targets_by_short_name_and_all():
    """짧은 함수명 필터와 ``all`` 이 모두 동작한다."""
    jobs = _jobs()

    assert [j.id for j in cli.select_requeue_targets(jobs, "geocode_order_address")] == ["j1", "j2"]
    assert [j.id for j in cli.select_requeue_targets(jobs, "all")] == ["j1", "j2", "j3"]
    assert cli.select_requeue_targets(jobs, "no_such_job") == []


def test_main_without_redis_url_exits_disabled(monkeypatch, capsys):
    """``REDIS_URL`` 미설정 → exit 3 + 깨끗한 한 줄 메시지(트레이스백 없음)."""
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert cli.main([]) == cli.EXIT_DISABLED
    out = capsys.readouterr().out
    assert "REDIS_URL 미설정" in out
    assert "Traceback" not in out


def test_main_with_unreachable_redis_exits_unreachable(monkeypatch, capsys):
    """Redis 도달 실패 → exit 2 + 한 줄 요약(예외 전파 없음)."""
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    monkeypatch.setattr(cli, "open_failed_registry", lambda url: (_ for _ in ()).throw(
        RedisConnectionError("Connection refused")))

    assert cli.main([]) == cli.EXIT_UNREACHABLE
    out = capsys.readouterr().out
    assert "Redis 도달 실패" in out
    assert "ConnectionError" in out


def test_main_reports_summary_and_flags_failures(monkeypatch, capsys):
    """실패 잡이 있으면 요약을 찍고 exit 1, JSON 모드는 집계 payload 를 낸다."""
    jobs = _jobs()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(cli, "open_failed_registry", lambda url: _StubRegistry())
    monkeypatch.setattr(cli, "fetch_failed_jobs", lambda reg, limit: (jobs, len(jobs)))

    assert cli.main(["--json"]) == cli.EXIT_FAILURES
    payload = json.loads(capsys.readouterr().out)
    assert payload["failed_count"] == 3 and payload["sampled"] == 3
    assert payload["jobs"][0]["job_name"] == _PREFIX + "geocode_order_address"

    assert cli.main([]) == cli.EXIT_FAILURES
    assert "실패 잡 3건" in capsys.readouterr().out


def test_main_clean_when_registry_empty(monkeypatch, capsys):
    """실패 잡 0건 → exit 0."""
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(cli, "open_failed_registry", lambda url: _StubRegistry())
    monkeypatch.setattr(cli, "fetch_failed_jobs", lambda reg, limit: ([], 0))

    assert cli.main([]) == cli.EXIT_CLEAN
    assert "실패 잡 0건" in capsys.readouterr().out


def test_failed_registry_attribute_contract():
    """``fetch_failed_jobs`` 가 의존하는 RQ registry API 를 고정한다(연결 없음).

    ``FailedJobRegistry`` 생성과 ``Redis.from_url`` 은 lazy 라 Redis 가 없어도 통과한다.
    RQ 업그레이드로 속성이 바뀌면 운영이 아니라 여기서 빨강이 나야 한다.
    """
    from redis import Redis
    from rq import Queue
    from rq.registry import FailedJobRegistry

    registry = FailedJobRegistry(
        queue=Queue("default", connection=Redis.from_url("redis://127.0.0.1:6399/0")))

    assert {"connection", "job_class", "serializer"} <= set(registry.__dict__)
    assert isinstance(type(registry).count, property)
    assert callable(registry.get_job_ids) and callable(registry.requeue)
    assert callable(registry.job_class.fetch_many)


@pytest.mark.parametrize("apply_flag, expected", [(False, []), (True, ["j1", "j2"])])
def test_requeue_dry_run_by_default(monkeypatch, capsys, apply_flag, expected):
    """``--requeue`` 는 기본 dry-run, ``--apply`` 가 있을 때만 실제 재큐잉한다."""
    registry = _StubRegistry()
    jobs = _jobs()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(cli, "open_failed_registry", lambda url: registry)
    monkeypatch.setattr(cli, "fetch_failed_jobs", lambda reg, limit: (jobs, len(jobs)))

    argv = ["--requeue", "geocode_order_address"] + (["--apply"] if apply_flag else [])
    exit_code = cli.main(argv)

    assert registry.requeued == expected
    assert exit_code == cli.EXIT_FAILURES  # dry-run 3건 / apply 후 잔여 1건
    assert ("dry-run" in capsys.readouterr().out) is not apply_flag
