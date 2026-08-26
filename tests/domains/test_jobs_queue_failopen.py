"""``foms/services/jobs/queue.py`` Redis 장애 fail-open 회귀 테스트 (실제 Redis 불필요).

2026-07-21 Railway 하드웨어 장애로 Redis 가 죽자 레이트리미터가 매 요청 500 을 뱉었다.
그 사고의 rate limiter 쪽 회귀는 ``tests/domains/test_rate_limit.py`` 가 잡지만, **같은
Redis 를 쓰는 RQ enqueue 경로는 그때 검증에서 빠졌다** — 이 파일이 그 구멍을 막는다.

핵심 계약(호출부가 동기 fallback 으로 degrade 할 수 있으려면 반드시 성립):

* Redis 부재/장애 시 ``enqueue_*`` 는 예외를 밖으로 던지지 않고 ``False`` 를 반환한다.
* 그 실패는 **조용히 삼켜지지 않는다** — logger 에 남는다(무로그 삼킴 = 회귀).
* Redis 클라이언트에 socket 타임아웃 상한이 있다(없으면 blackhole 된 Redis 에서
  enqueue 가 웹 워커를 OS TCP 타임아웃까지 붙잡는다).

fakeredis 가 requirements 에 없으므로 실제 Redis 대신 stub 큐를 ``_rq_queue`` 모듈
캐시에 주입한다. 네트워크 I/O 가 전혀 없어 결정적이고 빠르다. 실제 Redis 가 필요한
positive-path(=rq API 호환) 검증은 ``test_jobs_queue_redis_lane.py`` 가 담당한다.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

import foms.services.jobs.queue as queue_mod

_LOGGER_NAME = "foms.services.jobs.queue"


@pytest.fixture(autouse=True)
def _reset_queue_cache() -> Any:
    """모듈 전역 ``_rq_queue`` 캐시를 테스트마다 초기화한다(누수 시 서로 오염)."""
    queue_mod._rq_queue = None
    yield
    queue_mod._rq_queue = None


class _DeadQueue:
    """Redis 가 죽었을 때의 RQ Queue stub.

    ``enqueue``/``ping`` 은 실제와 같이 ConnectionError 를 올린다. ``Worker.count``
    처럼 이 stub 이 흉내내지 않는 Redis 명령을 호출하는 경로는 AttributeError 로
    실패하는데, 검증 대상인 fail-open 계약(예외를 밖으로 흘리지 않고 degrade + 로그)
    은 예외 종류와 무관하므로 그대로 유효하다.
    """

    # RQ Queue 로서 조회될 때 읽히는 속성(없으면 Redis 도달 실패가 아니라
    # AttributeError 로 실패해 재현 충실도가 떨어진다).
    name = "default"

    def __init__(self) -> None:
        self.connection = self

    def enqueue(self, *args: Any, **kwargs: Any) -> Any:
        """실제 RQ 처럼 Redis 도달 실패를 예외로 올린다."""
        raise RedisConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    def ping(self) -> Any:
        """readiness 프로브용 ping 도 동일하게 실패한다."""
        raise RedisConnectionError("Error 111 connecting to redis:6379. Connection refused.")


# (헬퍼 이름, 호출 인자) — 세 enqueue 헬퍼 전부 같은 fail-open 계약을 지켜야 한다.
_ENQUEUE_CASES: list[tuple[str, tuple[Any, ...]]] = [
    ("enqueue_thumbnail_generation", (123, "attachments/1/x.jpg")),
    ("enqueue_geocode_order_address", (456,)),
    ("enqueue_channeltalk_inbound", (789,)),
]


def _helper(name: str) -> Callable[..., Any]:
    """이름으로 enqueue 헬퍼를 얻는다."""
    return getattr(queue_mod, name)


def test_get_rq_queue_returns_none_without_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """REDIS_URL 미설정 = RQ 비활성. None 을 반환해 호출부가 동기 경로로 간다."""
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert queue_mod.get_rq_queue() is None


def test_get_rq_queue_sets_socket_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis 클라이언트에 connect/read 타임아웃 상한이 걸려 있어야 한다.

    상한이 없으면(``Redis.from_url`` 기본값 None) blackhole 된 Redis 에서 enqueue 가
    OS TCP 타임아웃(수십~130초)까지 웹 워커를 붙잡는다. ``Redis.from_url`` 은 lazy 라
    이 검증에는 네트워크 I/O 가 발생하지 않는다.
    """
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")

    q = queue_mod.get_rq_queue()

    assert q is not None
    kwargs = q.connection.connection_pool.connection_kwargs
    assert kwargs.get("socket_connect_timeout") == 2
    assert kwargs.get("socket_timeout") == 2


@pytest.mark.parametrize(("name", "args"), _ENQUEUE_CASES)
def test_enqueue_returns_false_without_redis_url(
    monkeypatch: pytest.MonkeyPatch, name: str, args: tuple[Any, ...]
) -> None:
    """REDIS_URL 미설정 시 enqueue 는 예외 없이 False (호출부 동기 fallback 신호)."""
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert _helper(name)(*args) is False


@pytest.mark.parametrize(("name", "args"), _ENQUEUE_CASES)
def test_enqueue_fails_open_and_logs_when_redis_dead(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    name: str,
    args: tuple[Any, ...],
) -> None:
    """Redis 장애 시 enqueue 는 (a) 예외를 던지지 않고 (b) False 이며 (c) 로그를 남긴다.

    (c) 가 핵심이다 — ``except Exception: return False`` 로 조용히 삼키면 운영에서
    큐가 죽은 것을 아무도 모른 채 동기 fallback 만 돌게 된다.
    """
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setattr(queue_mod, "_rq_queue", _DeadQueue())
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)

    assert _helper(name)(*args) is False

    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert records, f"{name}: Redis 장애가 로그 없이 삼켜졌다"
    assert any(r.levelno >= logging.ERROR for r in records), (
        f"{name}: enqueue 실패는 ERROR 로 남아야 한다"
    )


def test_get_rq_runtime_status_disabled_without_redis_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REDIS_URL 미설정은 'unreachable'(장애)이 아니라 'disabled'(의도된 비활성)."""
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert queue_mod.get_rq_runtime_status() == {
        "state": "disabled", "worker_count": 0, "worker_count_known": True}


def test_get_rq_runtime_status_unreachable_when_ping_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ping 실패 시 예외를 올리지 않고 'unreachable' 로 보고한다(readiness fail-open)."""
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setattr(queue_mod, "_rq_queue", _DeadQueue())

    assert queue_mod.get_rq_runtime_status() == {
        "state": "unreachable", "worker_count": 0, "worker_count_known": True}


def test_get_rq_worker_count_returns_zero_and_logs_when_redis_dead(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """워커 수 조회 실패는 0 으로 degrade 하되 **단계마다** 로그를 남긴다.

    ``get_rq_worker_count`` 는 ``Worker.count`` → ``Worker.all`` 2단 fallback 이다.
    두 단계 모두 실패해 0 이 나왔다면 두 실패가 모두 관측 가능해야 한다 — 마지막
    단계가 조용히 0 을 반환하면 운영자는 첫 warning 만 보고 "fallback 은 성공했고
    워커가 진짜 0" 이라고 오진한다. 그래서 개수까지 본다.
    """
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    caplog.set_level(logging.WARNING, logger=_LOGGER_NAME)

    count = queue_mod.get_rq_worker_count(_DeadQueue())

    assert count == 0
    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert len(records) >= 2, (
        f"fallback 단계별 로그가 누락됐다(관측된 로그 {len(records)}건). "
        "조용한 0 은 '워커 없음' 오진을 만든다"
    )


def test_unknown_worker_count_is_marked_unknown_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**못 센 0 과 진짜 0 을 가른다** (2026-08-26 CEO 지적).

    바로 위 테스트가 적어 둔 오진("fallback 은 성공했고 워커가 진짜 0")을 로그가 아니라
    **반환값으로** 막는다. 호출부는 로그를 읽지 않는다 — 값을 읽는다.
    """
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")

    count, known = queue_mod._probe_rq_workers(_DeadQueue())

    assert count == 0
    assert known is False, "못 센 것을 '0대'라고 단정했다"


def test_counted_zero_stays_a_known_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """진짜로 0대를 센 경우는 그대로 '안다'로 남는다 — 좁힌 판정이 못을 빼면 안 된다."""

    class _EmptyQueue:
        name = "default"

        def __init__(self) -> None:
            self.connection = self

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setattr("rq.Worker.count", staticmethod(lambda connection=None, queue=None: 0))

    count, known = queue_mod._probe_rq_workers(_EmptyQueue())

    assert count == 0 and known is True


def test_runtime_status_reports_unknown_worker_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """ping 은 통했는데 워커를 못 센 상태가 상태 dict 에 그대로 실린다."""

    class _PingOkCountDead:
        """ping 은 되는데 Worker 조회만 실패하는 짧은 창의 재현."""

        name = "default"

        def __init__(self) -> None:
            self.connection = self

        def ping(self):
            return True

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6390")
    monkeypatch.setattr(queue_mod, "_rq_queue", _PingOkCountDead())

    status = queue_mod.get_rq_runtime_status()

    assert status["state"] == "reachable", status
    assert status["worker_count"] == 0
    assert status["worker_count_known"] is False
