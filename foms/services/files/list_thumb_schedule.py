"""목록 작은 그림 만들기 예약 — web · 도면 전달이 부른다(SPEC 2026-11-19-list-drawing-small-image §3-1 ③ · §3-2).

:mod:`foms.services.files.list_thumb` 와 나눈 까닭: 워커 작업 모듈(``foms.services.jobs.tasks``)이 그쪽을 import 하는데,
큐 모듈을 열면 ``foms.services.jobs`` 패키지가 tasks 를 다시 열어 순환이 된다. 예약은 큐 쪽, 만들기는 그쪽.
"""

from __future__ import annotations

import time

from foms.services.files.list_thumb import is_list_thumb_source, list_thumb_job_id
from foms.services.jobs.queue import (
    LIST_THUMB_ENQUEUE_QUEUED,
    LIST_THUMB_ENQUEUE_UNAVAILABLE,
    enqueue_list_thumb_generation,
)

#: 같은 key 예약을 한 번만 — Redis ``SET NX`` 자물쇠의 유효 시간(초). 그 안에 다시 와도 넣지 않는다.
#: 워커가 건너뛴 key(16MP 초과 · 깨진 그림)는 이 시간이 지나야 다시 시도한다.
LIST_THUMB_ENQUEUE_LOCK_SECONDS = 6 * 3600
#: 예약 실패(큐 없음 · Redis 장애) 뒤 이 프로세스가 다시 시도하지 않는 시간(초) — 목록 한 화면이 그림 수백 장을
#: 부르므로, 막힌 Redis 에 장마다 2초씩 기다리지 않게 한다.
_ENQUEUE_BACKOFF_SECONDS = 60.0
_enqueue_backoff_until = 0.0


def schedule_list_thumb(storage_key: str) -> bool:
    """작은 그림 만들기를 워커 큐에 한 번만 넣는다. 큐가 없거나 막히면 조용히 건너뛴다(False).

    web 안에서 대신 만들지 않는다(ThreadPool 폴백 없음) — 원본이 계속 나갈 뿐이다.

    Args:
        storage_key: 원본 key.

    Returns:
        이번 호출이 큐에 새로 넣었으면 True. 그림 아님 · 이미 넣음 · 큐 없음 · 실패면 False.
    """
    global _enqueue_backoff_until
    key = (storage_key or "").strip()
    if not is_list_thumb_source(key):
        return False
    if time.monotonic() < _enqueue_backoff_until:
        return False
    # 큐 함수는 예외를 올리지 않는다(로그 후 unavailable) — 예약 실패가 그림 응답 · 도면 전달을 깨지 않는다.
    result = enqueue_list_thumb_generation(key, job_id=list_thumb_job_id(key),
                                           lock_seconds=LIST_THUMB_ENQUEUE_LOCK_SECONDS)
    if result == LIST_THUMB_ENQUEUE_UNAVAILABLE:
        _enqueue_backoff_until = time.monotonic() + _ENQUEUE_BACKOFF_SECONDS
    return result == LIST_THUMB_ENQUEUE_QUEUED


def schedule_list_thumbs(storage_keys) -> int:
    """여러 key 를 예약한다(그림 아닌 key 는 건너뜀). 새로 넣은 수를 돌려준다."""
    count = 0
    for key in storage_keys or ():
        if schedule_list_thumb(key):
            count += 1
    return count
