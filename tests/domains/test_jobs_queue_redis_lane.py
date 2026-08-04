"""실제 Redis 가 필요한 RQ positive-path lane (opt-in: ``FOMS_TEST_REDIS_URL``).

``test_jobs_queue_failopen.py`` 는 Redis **장애** 계약을 stub 으로 전부 덮는다. 반면
아래 세 가지는 stub 으로 덮을 수 없다 — stub 은 "우리가 rq 를 이렇게 호출했다"를
확인할 뿐, "rq 가 그 호출을 받아준다"를 확인하지 못하기 때문이다:

* ``q.enqueue("<문자열 함수경로>", args, job_timeout=...)`` 가 실제로 job 을 적재하는가
* ``Worker.count(connection=, queue=)`` 시그니처가 살아 있는가 — 깨지면
  ``get_rq_worker_count`` 가 **조용히 0** 을 반환해(로그만 남기고 fallback) 운영에서
  "워커 0" 오진을 만든다
* ``get_rq_runtime_status`` 가 살아있는 Redis 를 'reachable' 로 판정하는가

``requirements.txt`` 가 ``rq>=1.15.0`` / ``redis>=5.0.0`` 처럼 **상한 없는 floating**
이라 CI 는 매번 최신(현재 rq 2.5.x)을 당겨온다. rq 2.0 은 breaking 릴리스였고 다음
메이저도 같은 위험이 있다 — 이 lane 이 그 드리프트를 잡는 그물이다.

``FOMS_TEST_REDIS_URL`` 미설정이면 전부 skip 되므로 로컬/기본 CI 는 영향이 없다.
``REDIS_URL`` 을 전역으로 켜지 않는 이유: 그 변수는 Socket.IO·dashboard micro-cache·
rate limiter 까지 동시에 켜서 전체 스위트 거동을 바꾼다(PG lane 의
``FOMS_TEST_DATABASE_URL`` 분리와 같은 이유).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Iterator
from urllib.parse import urlparse

import pytest

import foms.services.jobs.queue as queue_mod

_ENV = "FOMS_TEST_REDIS_URL"
_LOGGER_NAME = "foms.services.jobs.queue"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class RedisLaneSafetyError(RuntimeError):
    """Redis lane 이 비로컬 호스트를 가리킬 때 발생한다."""


def assert_local_redis_url(raw_url: str) -> str:
    """로컬 Redis 를 가리키지 않으면 거부한다(운영·스테이징 Redis 접속 차단).

    Args:
        raw_url: 환경변수에서 읽은 Redis URL.

    Returns:
        검증을 통과한 원본 URL.

    Raises:
        RedisLaneSafetyError: host 가 없거나 로컬 호스트가 아닐 때.
    """
    host = (urlparse(raw_url).hostname or "").strip().strip("[]").lower()
    if host not in LOCAL_HOSTS:
        raise RedisLaneSafetyError(
            f"Redis test lane refuses non-local host {host!r}. "
            f"{_ENV} host must be one of {sorted(LOCAL_HOSTS)} "
            "(guards against staging/production Redis)."
        )
    return raw_url


pytestmark = pytest.mark.skipif(
    not (os.environ.get(_ENV) or "").strip(),
    reason=f"{_ENV} 미설정 — 실제 Redis 가 있는 CI lane 에서만 실행",
)


@pytest.fixture
def real_queue(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """실제 Redis 에 연결된 RQ 큐를 주고, 사용한 큐를 비운 뒤 캐시를 되돌린다."""
    url = assert_local_redis_url((os.environ.get(_ENV) or "").strip())
    monkeypatch.setenv("REDIS_URL", url)
    monkeypatch.setattr(queue_mod, "_rq_queue", None)

    q = queue_mod.get_rq_queue()
    assert q is not None, "실제 Redis 가 떠 있는데 get_rq_queue 가 None 을 반환했다"
    q.empty()
    try:
        yield q
    finally:
        q.empty()
        queue_mod._rq_queue = None


def test_enqueue_geocode_lands_real_job(real_queue: Any) -> None:
    """enqueue 가 실제로 job 을 적재하고 함수경로·타임아웃이 보존된다."""
    assert queue_mod.enqueue_geocode_order_address(4242) is True

    jobs = real_queue.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].func_name == "foms.services.jobs.tasks.geocode_order_address"
    assert jobs[0].args == (4242,)
    assert jobs[0].timeout == 120  # job_timeout="2m"


def test_enqueue_thumbnail_lands_real_job(real_queue: Any) -> None:
    """썸네일 enqueue 도 동일하게 실제 적재된다(job_timeout='5m')."""
    assert queue_mod.enqueue_thumbnail_generation(77, "attachments/77/a.jpg") is True

    jobs = real_queue.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].func_name == "foms.services.jobs.tasks.create_thumbnail_for_attachment"
    assert jobs[0].args == (77, "attachments/77/a.jpg")
    assert jobs[0].timeout == 300


def test_enqueue_channeltalk_lands_real_job(real_queue: Any) -> None:
    """채널톡 인바운드 enqueue 도 실제 적재된다."""
    assert queue_mod.enqueue_channeltalk_inbound(9001) is True

    jobs = real_queue.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].func_name == "foms.services.jobs.tasks.process_channeltalk_inbound"
    assert jobs[0].args == (9001,)


def test_worker_count_uses_primary_path_without_fallback(
    real_queue: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """``Worker.count`` 기본 경로가 살아 있어야 한다(조용한 0 fallback 금지).

    워커를 띄우지 않으므로 값 자체는 0 이지만, 그 0 이 **정상 조회 결과**여야지
    ``Worker.count`` 시그니처가 깨져 warning 을 남기고 fallback 으로 떨어진 0 이면
    안 된다. rq 메이저 업그레이드가 이 시그니처를 바꾸면 여기서 빨강이 된다.
    """
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)

    count = queue_mod.get_rq_worker_count(real_queue)

    assert count == 0
    assert not [r for r in caplog.records if r.name == _LOGGER_NAME], (
        "Worker.count 기본 경로가 실패해 fallback 으로 떨어졌다(rq API 드리프트 의심)"
    )


def test_runtime_status_reachable_against_live_redis(real_queue: Any) -> None:
    """살아 있는 Redis 는 'reachable' 로 보고된다(readiness 프로브 positive path)."""
    status = queue_mod.get_rq_runtime_status()

    assert status["state"] == "reachable"
    assert status["worker_count"] == 0
