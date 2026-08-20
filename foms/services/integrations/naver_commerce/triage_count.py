"""수집 확인 대기 건수 — nav 뱃지용 (NAVER-INGEST-01 잔여).

nav 는 **모든 페이지**에서 렌더되므로 요청마다 COUNT 를 새로 내면 안 된다. 30초 TTL
인메모리 캐시를 둔다(``dashboard_counts`` 의 nav 뱃지와 같은 규약). 캐시가 비어도
쿼리는 부분 인덱스 ``(channel, created_at) WHERE reviewed_at IS NULL`` 로 풀린다.

DB 만 읽는다 — 네이버 HTTP 는 여기서 절대 내지 않는다(WORKER 단일 출구 계약).
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from foms.services.integrations.naver_commerce.constants import CHANNEL

logger = logging.getLogger(__name__)

#: nav 뱃지 캐시 수명(초). dashboard_counts.NAV_BADGE_CACHE_TTL_SEC 와 같은 값.
TRIAGE_COUNT_CACHE_TTL_SEC = 30

_lock = Lock()
_cache: dict[str, tuple[float, int]] = {}


def compute_triage_pending_count(db: Any) -> int:
    """확인 대기 링크 수를 센다 — 트리아지 큐 정의와 같은 술어여야 한다.

    큐(``naver_ingest_triage``)에는 두 종류가 온다: 아직 주문이 없는 수집분
    (``COLLECTED`` — "주문 만들기" 대기)과 주문은 생겼지만 사람이 안 본 건
    (``LINKED``). 뱃지가 ``LINKED`` 만 세면 주문 만들기 대기가 0 으로 보인다
    (T14-A 에서 실제로 났던 불일치).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        int: 대기 건수. 조회 실패 시 0(뱃지는 부가 정보라 페이지를 죽이지 않는다).
    """
    from models import ExternalOrderLink

    try:
        return int(
            db.query(ExternalOrderLink.id)
            .filter(
                ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.sync_status.in_(("COLLECTED", "LINKED")),
                ExternalOrderLink.reviewed_at.is_(None),
            )
            .count()
        )
    except SQLAlchemyError as exc:
        logger.warning("[NAVER] 트리아지 대기 건수 조회 실패: %s", exc)
        return 0


def get_triage_pending_count(db: Any) -> int:
    """30초 TTL 캐시로 확인 대기 건수를 반환한다(nav 렌더 경로 전용).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        int: 대기 건수.
    """
    now = time.monotonic()
    with _lock:
        entry = _cache.get(CHANNEL)
        if entry and entry[0] > now:
            return entry[1]

    value = compute_triage_pending_count(db)
    with _lock:
        _cache[CHANNEL] = (now + TRIAGE_COUNT_CACHE_TTL_SEC, value)
    return value


def reset_triage_count_cache_for_tests() -> None:
    """테스트 격리용 캐시 초기화."""
    with _lock:
        _cache.clear()


__all__ = [
    "TRIAGE_COUNT_CACHE_TTL_SEC",
    "compute_triage_pending_count",
    "get_triage_pending_count",
    "reset_triage_count_cache_for_tests",
]
