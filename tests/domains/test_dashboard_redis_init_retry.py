"""P3-8: 대시보드 Redis 클라이언트 초기화가 한 번 실패해도 프로세스가 캐시를 영영 버리지 않는다.

예전에는 ``get_dashboard_redis`` 가 실패를 ``False`` 로 굳혀 재시작 전까지 캐시·표 버전
카운터(무효화·304 판정)를 건너뛰었다(2026-09-30 운영 워커 Redis 연결 실패 3.5분 사례).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from foms.services.common import dashboard_cache as dc


@pytest.fixture(autouse=True)
def _reset_runtime():
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


class _FlakyRedisFactory:
    """``Redis.from_url`` 대역. ``fail_pings`` 번까지는 ping 이 실패하고 그 뒤엔 성공한다."""

    def __init__(self, fail_pings: int) -> None:
        self.fail_pings = fail_pings
        self.created = 0

    def from_url(self, _url, **_kwargs):
        self.created += 1
        factory = self

        class _Client:
            def ping(self):
                if factory.created <= factory.fail_pings:
                    raise ConnectionError("redis down")
                return True

        return _Client()


def test_get_dashboard_redis_retries_after_init_failure(caplog):
    """P3-8: 초기화 한 번 실패로 프로세스가 캐시를 영영 버리지 않는다.

    실패 직후 ~ 재시도 대기 동안은 연결 시도 없이 바로 None(로그도 없음), 대기가 지나면
    첫 호출이 다시 시도하고, 성공하면 그 클라이언트를 계속 쓴다.
    """
    import logging
    import time

    import redis

    factory = _FlakyRedisFactory(fail_pings=1)
    caplog.set_level(logging.WARNING, logger="foms.services.common.dashboard_cache")
    with patch.dict(os.environ, {"REDIS_URL": "redis://x"}, clear=False), \
            patch.object(redis.Redis, "from_url", factory.from_url):
        before = time.monotonic()
        assert dc.get_dashboard_redis() is None
        assert factory.created == 1
        assert before + dc.REDIS_INIT_RETRY_SECONDS <= dc._redis_retry_at

        # 대기 중: 연결을 다시 만들지 않고, 경고도 더 쌓지 않는다.
        for _ in range(5):
            assert dc.get_dashboard_redis() is None
        assert factory.created == 1
        warnings = [r for r in caplog.records if "init failed" in r.getMessage()]
        assert len(warnings) == 1

        # 대기 시간이 지났다고 치고(시각을 앞당김) 다시 부르면 재시도해서 붙는다.
        dc._redis_retry_at = time.monotonic() - 1
        client = dc.get_dashboard_redis()
        assert client is not None
        assert factory.created == 2
        assert dc._redis_retry_at == 0.0

        # 붙은 뒤에는 같은 클라이언트를 재사용한다(새 연결 없음).
        assert dc.get_dashboard_redis() is client
        assert factory.created == 2


def test_get_dashboard_redis_retry_does_not_queue_behind_running_attempt():
    """재시도 중 들어온 다른 요청은 자물쇠를 기다리지 않고 바로 None 을 받는다.

    장애 중에 요청들이 연결 상한(2초)을 줄줄이 무는 것을 막는다. 첫 초기화(실패 기록 없음)는
    지금처럼 기다린다 — 대조로, 같은 자물쇠 상태에서 실패 기록이 없으면 None 대신 대기한다.
    """
    import threading
    import time

    import redis

    factory = _FlakyRedisFactory(fail_pings=0)
    with patch.dict(os.environ, {"REDIS_URL": "redis://x"}, clear=False), \
            patch.object(redis.Redis, "from_url", factory.from_url):
        dc._redis_retry_at = time.monotonic() - 1  # 실패 기록 있음 + 대기 끝남 = 재시도 차례
        retry_result: dict[str, object] = {}
        assert dc._redis_lock.acquire(blocking=False)
        try:
            # 별도 스레드로 부른다 — 기다리는 구현이면 여기서 테스트가 멈추는 대신 실패한다.
            caller = threading.Thread(
                target=lambda: retry_result.update(c=dc.get_dashboard_redis())
            )
            caller.start()
            caller.join(0.5)
            assert not caller.is_alive(), "재시도 중인 자물쇠를 기다리면 안 된다"
            assert "c" in retry_result and retry_result["c"] is None
            assert factory.created == 0
        finally:
            dc._redis_lock.release()
            caller.join(2)

        # 대조군: 실패 기록이 없는 첫 초기화는 자물쇠가 풀릴 때까지 기다렸다가 붙는다.
        dc.reset_dashboard_cache_runtime_for_tests()
        result: dict[str, object] = {}
        assert dc._redis_lock.acquire(blocking=False)
        worker = threading.Thread(target=lambda: result.update(c=dc.get_dashboard_redis()))
        worker.start()
        worker.join(0.2)
        assert worker.is_alive(), "첫 초기화는 자물쇠를 기다려야 한다"
        dc._redis_lock.release()
        worker.join(2)
        assert result.get("c") is not None
        assert factory.created == 1
