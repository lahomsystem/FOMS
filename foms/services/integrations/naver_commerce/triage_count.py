"""수집 확인 대기 건수 — nav 뱃지용 (NAVER-INGEST-01 잔여).

nav 는 **모든 페이지**에서 렌더되므로 요청마다 COUNT 를 새로 내면 안 된다. 30초 TTL
캐시를 둔다(``dashboard_counts`` 의 nav 뱃지와 같은 규약). 캐시가 비어도
쿼리는 부분 인덱스 ``(channel, created_at) WHERE reviewed_at IS NULL`` 로 풀린다.

**캐시는 Redis 공유가 기본이다**(2026-10-02, 성능 원장 P2-2). 프로세스 메모리 캐시만 있던
때는 운영 web 4개 프로세스(2 replica × gunicorn 2)가 30초마다 **각자** 콜드 계산을 했다 —
스테이징 콜드 674~757ms. 대시보드 캐시의 Redis 클라이언트(:func:`get_dashboard_redis`)를
그대로 쓰고, Redis 가 없거나 오류면 예전처럼 프로세스 캐시로 돈다(fail-open).
신선도 약속은 그대로 **최대 30초**다 — 무효화 지점은 예전에도 없었고(TTL 만), 지금도 없다.
처리 탭 렌더가 같은 정의로 센 값은 :func:`remember_triage_pending_count` 로 바로 넣는다.

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

from foms.services.common.dashboard_cache import get_dashboard_redis
from foms.services.integrations.naver_commerce.constants import CHANNEL

logger = logging.getLogger(__name__)

#: nav 뱃지 캐시 수명(초). dashboard_counts.NAV_BADGE_CACHE_TTL_SEC 와 같은 값.
TRIAGE_COUNT_CACHE_TTL_SEC = 30

#: 공유 캐시 키 머리. 대시보드 슬라이스 캐시 접두사(``foms:dashcache:v1:``) **밖에** 둔다 —
#: 그 접두사는 주문 저장 경로들이 SCAN 으로 통째 비우는 자리라, 거기 두면 주문 저장마다
#: 배지가 콜드로 돌아간다(이 값은 주문 저장과 무관하다).
SHARED_KEY_PREFIX = "foms:naver-triage-count:v1:"

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
    # 워크벤치 페이지가 이 요청에서 이미 같은 목록을 계산했으면 그 답을 쓴다.
    # 안 그러면 한 요청이 `_work_groups` 를 **두 번** 돈다 — 배지용 1회 + 페이지용 1회
    # (스테이징 실측: 콜드에서 배지 몫만 411~428ms). `display` 는 모집단을 바꾸지 않으므로
    # (:func:`_work_groups` docstring) 두 경로의 집계 값은 같다.
    try:
        from flask import g, has_request_context

        if has_request_context():
            cached = getattr(g, "wb_actionable_count", None)
            if isinstance(cached, int):
                return cached
    except RuntimeError:  # 요청 밖(워커·CLI) — 그냥 계산한다
        pass

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
        _write_cache(key, value)
        return value


def remember_triage_pending_count(value: int, *, workbench: bool) -> None:
    """**같은 정의로 이미 센** 값을 캐시에 넣는다 — 다음 배지 요청이 다시 세지 않게.

    처리 탭 렌더는 :func:`_workbench_group_count` 와 같은 함수(``_work_groups`` →
    ``_actionable_count``)로 같은 수를 이미 셌다. 그 직후 nav 배지 요청
    (``/triage/pending-count``)이 캐시가 비었다는 이유로 같은 계산을 처음부터 다시
    도는 것을 막는다. 부르는 쪽이 정의가 같다는 것을 보장한다(정렬이 캡을 바꾸는 경우 등은
    부르지 않는다).

    Args:
        value: 손댈 수 있는 집 수.
        workbench: 워크벤치 v3 모집단인가(캐시 칸).
    """
    _write_cache(_cache_key(workbench), int(value))


def _shared_redis() -> Any | None:
    """대시보드 캐시와 같은 Redis 클라이언트(없거나 연결 실패면 None)."""
    try:
        return get_dashboard_redis()
    except Exception:  # noqa: BLE001 - 캐시 장애가 배지를 죽이지 않는다
        logger.debug("[NAVER] 배지 공유 캐시 클라이언트 없음", exc_info=True)
        return None


def _read_cache(key: str) -> int | None:
    """살아 있는 캐시 값(없거나 만료면 None).

    Redis 가 있으면 **Redis 만** 본다 — 프로세스 칸까지 보면 다른 프로세스가 갱신한 값보다
    낡은 값을 돌려줄 수 있다. Redis 오류일 때만 프로세스 칸으로 내려간다.
    """
    client = _shared_redis()
    if client is not None:
        try:
            raw = client.get(SHARED_KEY_PREFIX + key)
        except Exception as exc:  # noqa: BLE001 - 공유 캐시 장애는 프로세스 칸으로
            logger.warning("[NAVER] 배지 공유 캐시 읽기 실패(프로세스 캐시로): %s", exc)
        else:
            if raw is None:
                return None
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        return entry[1] if entry and entry[0] > now else None


def _write_cache(key: str, value: int) -> None:
    """값을 공유 캐시와 프로세스 칸 **둘 다**에 넣는다.

    프로세스 칸은 Redis 가 잠깐 오류일 때 내려가는 자리다 — 늘 함께 채워 둬야 그때
    곧바로 콜드 계산으로 떨어지지 않는다.
    """
    with _lock:
        _cache[key] = (time.monotonic() + TRIAGE_COUNT_CACHE_TTL_SEC, value)
    client = _shared_redis()
    if client is None:
        return
    try:
        client.setex(SHARED_KEY_PREFIX + key, max(int(TRIAGE_COUNT_CACHE_TTL_SEC), 1),
                     str(int(value)))
    except Exception as exc:  # noqa: BLE001 - 공유 캐시 장애가 배지를 죽이지 않는다
        logger.warning("[NAVER] 배지 공유 캐시 쓰기 실패(프로세스 캐시만): %s", exc)


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
    """테스트 격리용 캐시 초기화 — **프로세스 칸만** 비운다.

    공유 칸(Redis)은 건드리지 않는다. 테스트가 환경변수의 실제 Redis 에 붙어 키를 지우는
    일이 없게 하기 위해서다 — 공유 칸을 쓰는 테스트는 가짜 클라이언트를 직접 꽂는다.
    """
    with _lock:
        _cache.clear()


__all__ = [
    "SHARED_KEY_PREFIX",
    "TRIAGE_COUNT_CACHE_TTL_SEC",
    "compute_triage_pending_count",
    "get_triage_pending_count",
    "remember_triage_pending_count",
    "reset_triage_count_cache_for_tests",
]
