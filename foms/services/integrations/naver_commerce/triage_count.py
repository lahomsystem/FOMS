"""수집 확인 대기 건수 — nav 뱃지용 (NAVER-INGEST-01 잔여).

nav 는 **모든 페이지**에서 렌더되므로 요청마다 COUNT 를 새로 내면 안 된다. 30초 TTL
인메모리 캐시를 둔다(``dashboard_counts`` 의 nav 뱃지와 같은 규약). 캐시가 비어도
쿼리는 부분 인덱스 ``(channel, created_at) WHERE reviewed_at IS NULL`` 로 풀린다.

**모집단이 두 벌인 이유**: 워크벤치 v3 게이트가 켜진 사용자는 링크를 누르면 처리 탭
목록(``_work_groups``)을 본다 — 확인 큐 ∪ 발주확인 전 집. 게이트가 꺼진 사용자는 옛
트리아지 화면(확인 큐만)을 본다. 뱃지는 **그 사람이 실제로 볼 목록**과 같은 수여야
한다. 한 벌로 통일하면 한쪽이 반드시 어긋난다(2026-08-23 nav 67 · 탭 45 결함).

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

#: 캐시 dict 보호용. **짧게만** 잡는다 — 여기서 계산까지 하면 캐시 히트 요청까지 줄을 선다.
_lock = Lock()
_cache: dict[str, tuple[float, int]] = {}

#: 모집단별 **계산** 잠금(단일 비행). 캐시가 만료되는 순간 동시 요청이 몰리면 그 수만큼
#: `_work_groups` 가 동시에 돈다 — 게이트 ON 경로는 콜드 1회가 113ms(스테이징 73집 실측,
#: 2026-08-24)라 동시 5명이면 조회가 5벌 나간다. 전 직원 개방 = 동시 사용자 증가라 정확히
#: 이 자리가 위험하다. 한 명만 계산하고 나머지는 그 결과를 기다린다.
#: gevent monkey-patch 하에서 `Lock` 대기는 그린렛 양보라 워커를 막지 않는다.
_compute_locks: dict[str, Lock] = {}


def _cache_key(workbench: bool) -> str:
    """모집단별 캐시 키 — 게이트 on/off 가 같은 칸을 쓰면 서로의 값을 읽는다.

    Args:
        workbench: 워크벤치 v3 게이트가 켜진 사용자인가.

    Returns:
        str: 캐시 키.
    """
    return f"{CHANNEL}:{'work' if workbench else 'queue'}"


def _queue_group_count(db: Any) -> int:
    """옛 트리아지 화면 모집단 — 확인 대기 집 수(게이트 off 경로).

    큐(``naver_ingest_triage``)에는 두 종류가 온다: 아직 주문이 없는 수집분
    (``COLLECTED`` — "주문 만들기" 대기)과 주문은 생겼지만 사람이 안 본 건
    (``LINKED``). 뱃지가 ``LINKED`` 만 세면 주문 만들기 대기가 0 으로 보인다
    (T14-A 에서 실제로 났던 불일치).

    **단위가 집인 이유**: 네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 준다.
    링크 행을 세면 한 집이 6건으로 잡혀 nav 는 140, 화면 필터는 43 을 보여줬다 —
    같은 화면에서 업무량이 3배로 읽힌다(2026-08-20 감사 결함 #2).
    묶음 식은 이력 표와 공유한다(``grouping.group_key_expression``).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        int: 확인 대기 집 수.
    """
    from sqlalchemy import distinct, func

    from foms.services.integrations.naver_commerce.grouping import group_key_expression
    from models import ExternalOrderLink

    return int(
        db.query(func.count(distinct(group_key_expression())))
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.sync_status.in_(("COLLECTED", "LINKED")),
            ExternalOrderLink.reviewed_at.is_(None),
        )
        .scalar()
        or 0
    )


def _workbench_group_count(db: Any) -> int:
    """워크벤치 v3 처리 탭 모집단 — 목록 길이와 **같은 함수**로 센다.

    SQL 로 따로 세면 안 된다. 처리 탭 목록은 취소 표식(``triage_state`` JSONB)과
    원본 스냅샷을 읽어 거르고(취소·반품 집), 발주확인 전 집을 더한다 — SQL 술어로는
    같은 수가 나오지 않는다. 실제로 nav 67 · 탭 45 로 어긋났다(v3 계약 §6).

    ``display=False`` 로 부른다 — **모집단이 아니라 문서의 두께만** 바뀐다. 술어·병합·캡
    코드는 그대로고 ``raw_snapshot`` 자리에 판정 경로만 담은 축소 문서가 실린다
    (``naver_ingest._snapshot_projection``). 뱃지는 모든 페이지 렌더에 실리는데 3.3KB
    스냅샷 본문이 행 조회 비용의 약 80% 였다(2026-08-24 실측: 게이트 ON 콜드 113ms).
    두 모드의 집 키 목록이 같다는 것은 회귀 테스트가 직접 비교해 못박는다(계약 §2.4).

    화면 코드(``foms.web.admin.naver_ingest``)를 서비스가 부르므로 **함수 안에서**
    import 한다. 모듈 최상단에서 부르면 web → services → web 순환이 된다.

    뱃지는 **손댈 수 있는 집**만 센다(``_actionable_count``). 취소·반품 집은 목록에
    남지만 어떤 액션도 되지 않는데, 예전에는 그 집까지 세어 담당자가 매일 아침 보는
    업무량이 실제 처리 대상보다 컸다(2026-08-24 실측: 확인 큐 72집 중 13집이 그런 집).
    화면 스트립이 "처리 가능 N집 · 손대지 않음 M집"으로 같은 분해를 보여 준다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        int: 처리 탭 스트립·탭 배지와 같은 수(손댈 수 있는 집).
    """
    from foms.web.admin.naver_ingest import _actionable_count, _work_groups

    groups, _truncated = _work_groups(db, display=False)
    return _actionable_count(groups)


def compute_triage_pending_count(db: Any, *, workbench: bool = False) -> int:
    """뱃지 숫자를 계산한다 — 사용자가 볼 목록과 **같은 정의**로.

    Args:
        db: 요청 스코프 DB 세션.
        workbench: 워크벤치 v3 게이트가 켜진 사용자면 True(처리 탭 목록 길이),
            아니면 False(옛 트리아지 확인 대기 집 수).

    Returns:
        int: 대기 집 수. 조회 실패 시 0(뱃지는 부가 정보라 페이지를 죽이지 않는다).
    """
    try:
        return _workbench_group_count(db) if workbench else _queue_group_count(db)
    except SQLAlchemyError as exc:
        logger.warning("[NAVER] 트리아지 대기 집 수 조회 실패: %s", exc)
        return 0
    except Exception as exc:  # noqa: BLE001 - 뱃지가 전 페이지를 죽이게 두지 않는다
        # 워크벤치 경로는 순수 COUNT 가 아니라 화면 목록 로직 전부(스냅샷 JSONB 파싱 포함)를
        # 돈다. 원본 하나가 예상 밖 모양이면 TypeError/AttributeError 가 SQL 예외 그물 밖으로
        # 새고, 이 함수는 nav 컨텍스트라 **모든 페이지가 500** 이 된다(2026-08-23 리뷰 M1).
        # 위 docstring 의 "뱃지는 부가 정보라 페이지를 죽이지 않는다"를 실제로 지키는 자리다.
        logger.warning("[NAVER] 트리아지 대기 집 수 계산 실패(뱃지 0 으로 진행): %s", exc)
        return 0


def get_triage_pending_count(db: Any, *, workbench: bool = False) -> int:
    """30초 TTL 캐시로 확인 대기 건수를 반환한다(nav 렌더 경로 전용).

    Args:
        db: 요청 스코프 DB 세션.
        workbench: 워크벤치 v3 게이트가 켜진 사용자인가. 모집단이 다르므로 캐시 칸도
            나눈다 — 같은 칸을 쓰면 게이트 on 사용자가 off 사용자의 숫자를 읽는다.

    Returns:
        int: 대기 건수.
    """
    key = _cache_key(workbench)
    cached = _read_cache(key)
    if cached is not None:
        return cached

    # 여기부터가 단일 비행이다. 잠금을 기다린 쪽은 **다시 캐시를 본다** — 앞선 요청이
    # 방금 채워 놨으면 계산하지 않는다. 이 재확인이 없으면 잠금은 계산을 직렬화만 하고
    # 횟수는 그대로다(줄만 서고 일은 N번).
    with _compute_lock(key):
        cached = _read_cache(key)
        if cached is not None:
            return cached
        value = compute_triage_pending_count(db, workbench=workbench)
        with _lock:
            _cache[key] = (time.monotonic() + TRIAGE_COUNT_CACHE_TTL_SEC, value)
        return value


def _read_cache(key: str) -> int | None:
    """살아 있는 캐시 값(없거나 만료면 None)."""
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        return entry[1] if entry and entry[0] > now else None


def _compute_lock(key: str) -> Lock:
    """모집단별 계산 잠금을 준다(없으면 만든다).

    잠금 순서는 **항상** 계산 잠금 → `_lock` 이다. 여기서는 `_lock` 만 짧게 잡고 곧바로
    놓으므로 역순 보유가 생기지 않는다(교착 없음).
    """
    with _lock:
        lock = _compute_locks.get(key)
        if lock is None:
            lock = Lock()
            _compute_locks[key] = lock
        return lock


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
