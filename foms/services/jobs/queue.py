"""
Redis Queue (RQ) 연결 및 enqueue 헬퍼.
REDIS_URL 있으면 enqueue 가능. (USE_RQ_WORKER는 start.sh 전용, enqueue와 분리)
"""

from __future__ import annotations

import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)

_rq_queue = None

# NOTE:
# Enqueued RQ job function paths use this canonical prefix (strict track WR-J1).
# Root ``services/jobs/tasks.py`` remains a thin re-export of
# ``foms.services.jobs.tasks`` so workers resolving *legacy* payload strings that
# still reference ``services.jobs.tasks.*`` import the same callables during drain.
_TASK_PATH_PREFIX = "foms.services.jobs.tasks"

__all__ = [
    "get_rq_queue",
    "get_rq_worker_count",
    "get_rq_runtime_status",
    "enqueue_thumbnail_generation",
    "enqueue_geocode_order_address",
    "enqueue_channeltalk_inbound",
    "enqueue_naver_order_sync",
    "enqueue_naver_backfill",
]


def get_rq_queue():
    """RQ default 큐 반환. REDIS_URL 있으면 enqueue 가능 (FOMS 웹)."""
    global _rq_queue
    if _rq_queue is not None:
        return _rq_queue
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return None
    try:
        from redis import Redis
        from rq import Queue

        # socket_*timeout: Redis 가 blackhole 상태(하드웨어 장애 등)면 from_url 기본값
        # (None = OS TCP 타임아웃, 수십~130초)로는 enqueue 가 웹 워커를 통째로 붙잡는다.
        # 2026-07-21 Redis 장애 때 rate_limit / dashboard_cache 에만 상한을 넣고 이
        # 경로는 빠졌다. 초과 시 예외 → 아래 호출부의 기존 fail-open(False 반환 +
        # 동기 fallback)이 흡수한다.
        conn = Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        _rq_queue = Queue("default", connection=conn)
        return _rq_queue
    except Exception as e:
        logger.warning(f"[RQ] get_queue failed: {e}", exc_info=True)
        return None


def _probe_rq_workers(q=None) -> tuple[int, bool]:
    """워커 수를 재고, **잰 것인지 못 잰 것인지**까지 함께 돌려준다.

    ``get_rq_worker_count`` 는 실패했을 때도 0 을 준다. 그러면 "워커가 정말 0대"와
    "Redis 가 일시적으로 대답을 못 해 셀 수 없었다"가 같은 값이 되어, 호출부가 멀쩡한
    시스템을 두고 "워커가 한 대도 없습니다. WORKER 서비스를 확인하세요"라고 말한다
    (2026-08-26 CEO 지적). 판정이 필요한 호출부는 이 함수를 쓴다.

    Args:
        q: RQ 큐. 없으면 기본 큐를 잡는다.

    Returns:
        ``(worker_count, known)``. ``known`` 이 False 면 ``worker_count`` 는 **모른다는
        뜻의 0** 이지 "0대"가 아니다.
    """
    q = q or get_rq_queue()
    if not q:
        # 큐 자체가 없으면 워커도 없다 — 이건 못 잰 것이 아니라 확실히 아는 사실이다.
        return 0, True

    try:
        from rq import Worker

        return int(Worker.count(connection=q.connection, queue=q)), True
    except Exception as e:
        logger.warning(f"[RQ] Worker.count failed: {e}", exc_info=True)

    try:
        from rq import Worker

        workers = Worker.all(connection=q.connection, queue=q)
        return len(workers), True
    except Exception as e:
        logger.warning(f"[RQ] Worker.all fallback failed: {e}", exc_info=True)
        return 0, False


def get_rq_worker_count(q=None):
    """Return the live worker count for the default queue.

    세지 못한 경우에도 0 을 준다 — "0대"와 "못 셌다"를 갈라야 하는 호출부는
    :func:`_probe_rq_workers` 또는 :func:`get_rq_runtime_status` 의
    ``worker_count_known`` 을 본다.
    """
    count, _known = _probe_rq_workers(q)
    return count


def get_rq_runtime_status():
    """Inspect Redis reachability and live worker count for readiness checks.

    ``worker_count_known`` 이 False 면 ``worker_count`` 의 0 은 **"모른다"**는 뜻이다.
    ping 은 통했는데 그 직후 ``Worker.count`` 가 실패하는 짧은 창이 실제로 있고, 그때
    0 을 "워커 0대"로 읽으면 화면이 멀쩡한 WORKER 서비스를 의심하라고 말한다.
    """
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return {
            "state": "disabled",
            "worker_count": 0,
            "worker_count_known": True,
        }

    q = get_rq_queue()
    if not q:
        return {
            "state": "unreachable",
            "worker_count": 0,
            "worker_count_known": True,
        }

    try:
        q.connection.ping()
    except Exception as e:
        logger.warning(f"[RQ] ping failed: {e}", exc_info=True)
        return {
            "state": "unreachable",
            "worker_count": 0,
            "worker_count_known": True,
        }

    worker_count, known = _probe_rq_workers(q)
    return {
        "state": "reachable",
        "worker_count": worker_count,
        "worker_count_known": known,
    }


def enqueue_thumbnail_generation(attachment_id, storage_key):
    """
    썸네일 생성 job enqueue.
    RQ 활성화 시 큐에 넣고, 아니면 None 반환 (호출측에서 ThreadPool fallback).
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.create_thumbnail_for_attachment",
            int(attachment_id),
            storage_key,
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_thumbnail error: {e}", exc_info=True)
        return False


def enqueue_geocode_order_address(order_id):
    """
    주문 주소 지오코딩 job enqueue (Phase C).
    RQ 활성화 시 큐에 넣고, 아니면 False 반환.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.geocode_order_address",
            int(order_id),
            job_timeout="2m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_geocode_order_address error: {e}", exc_info=True)
        return False


def enqueue_channeltalk_inbound(event_log_id: int):
    """
    채널톡 인바운드 웹훅 파싱 및 처리 job enqueue (CT-E-05).
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.process_channeltalk_inbound",
            event_log_id,
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_channeltalk_inbound error: {e}", exc_info=True)
        return False


def enqueue_naver_fulfillment(link_id: int, action: str, actor_user_id=None):
    """발주확인·발송처리 job enqueue (NAVER-INGEST-02 T16-G).

    web 은 네이버를 직접 부르지 않는다(호출 IP 계약). 큐가 없으면 False 를 돌려주고
    화면이 "지금은 처리할 수 없다"를 그대로 보여준다 — 조용히 성공한 척하지 않는다.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_fulfillment_task",
            int(link_id), str(action), actor_user_id,
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_fulfillment error: {e}", exc_info=True)
        return False


def enqueue_naver_refresh(link_id: int, actor_user_id: Optional[int] = None) -> bool:
    """집 1건 **다시 읽기** job enqueue (T4).

    읽기 전용이지만 큐를 거치는 이유는 같다 — 커머스API 에 등록된 호출 IP 가 WORKER
    것뿐이라 web 에서 상세 조회를 내면 차단된다. 되돌릴 수 없는 호출은 **하나도 없다**.

    Args:
        link_id: 기준 수집 링크 id(그 링크가 속한 집 전체를 다시 읽는다).
        actor_user_id: 화면에서 누른 사람(기록용).

    Returns:
        큐에 넣었으면 True. 큐가 없거나 실패하면 False — 화면이 "지금은 다시 읽을 수
        없다"를 그대로 보여준다(조용히 성공한 척하지 않는다).
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_refresh_task",
            int(link_id), actor_user_id,
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_refresh error: {e}", exc_info=True)
        return False


def enqueue_naver_cancel(link_id: int, reason: str, detail: Optional[str] = None,
                         actor_user_id: Optional[int] = None) -> bool:
    """판매자 직접취소 job enqueue (스펙 §3.4).

    발주확인·발송처리와 같은 출구(WORKER)를 쓴다 — 커머스API 호출 IP 가 WORKER 것뿐이다.
    큐가 없으면 False 를 돌려주고 화면이 "판매자센터에서 처리하세요"를 그대로 보여준다.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_fulfillment_task",
            int(link_id), "cancel", actor_user_id,
            reason=str(reason), detail=detail,
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_cancel error: {e}", exc_info=True)
        return False



def enqueue_naver_return(link_id: int, reason: str, detail: Optional[str] = None,
                         actor_user_id: Optional[int] = None,
                         approve: bool = False) -> bool:
    """판매자 반품 접수 job enqueue (T8-S1). ``approve`` 면 승인까지 (T8-S2).

    취소와 **같은 출구**(WORKER)를 쓴다 — 커머스API 에 등록된 호출 IP 가 WORKER 것뿐이다.
    같은 태스크(``run_naver_fulfillment_task``)에 ``action="return"`` 으로 태운다:
    실패 사유를 DB 에 남기고 커밋하는 규율이 그 자리에 이미 있고, 갈래를 새로 파면
    그 규율이 두 벌이 된다(한쪽만 고쳐지는 자리가 된다).

    큐가 없으면 False 를 돌려주고 화면이 "지금은 접수할 수 없다"를 그대로 보여준다 —
    **불가역 경로라 조용히 성공한 척하는 것이 제일 나쁘다**.

    Args:
        link_id: 기준 수집 링크 id(그 링크가 속한 집 전체가 함께 처리된다).
        reason: 반품 사유 코드(``fulfillment.RETURN_REASONS`` 안의 값 — 라우트가 이미 검사했고
            서비스가 호출 직전에 한 번 더 본다).
        detail: 반품 상세 사유(선택, 500자).
        actor_user_id: 화면에서 누른 사람(기록용).

    Returns:
        큐에 넣었으면 True.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_fulfillment_task",
            int(link_id), "return", actor_user_id,
            reason=str(reason), detail=detail, approve=bool(approve),
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_return error: {e}", exc_info=True)
        return False

def enqueue_naver_return_reject(link_id: int, reason: str,
                                actor_user_id: Optional[int] = None) -> bool:
    """판매자 반품 **거부** job enqueue (T8-S3).

    접수·승인과 **같은 출구**(WORKER)·같은 태스크(``run_naver_fulfillment_task``,
    ``action="return-reject"``)를 쓴다 — 실패 사유를 DB 에 남기고 커밋하는 규율이 그 자리에
    이미 있고, 갈래를 새로 파면 그 규율이 두 벌이 된다.

    ``reason`` 은 사유 **코드가 아니라 문장**이다. 구매자에게 그대로 전달되므로 화이트리스트로
    거를 수 없다 — 대신 라우트가 빈 문장을 막고 서비스가 호출 직전에 한 번 더 본다.

    큐가 없으면 False 를 돌려주고 화면이 "지금은 거부할 수 없다"를 그대로 보여준다 —
    **불가역 경로라 조용히 성공한 척하는 것이 제일 나쁘다**.

    Args:
        link_id: 기준 수집 링크 id(그 링크가 속한 집 전체가 함께 처리된다).
        reason: 거부 사유 문장.
        actor_user_id: 화면에서 누른 사람(기록용).

    Returns:
        큐에 넣었으면 True.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_fulfillment_task",
            int(link_id), "return-reject", actor_user_id,
            reason=str(reason),
            job_timeout="5m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_return_reject error: {e}", exc_info=True)
        return False


def enqueue_naver_backfill(start_iso: str, end_iso: str, dry_run: bool = False):
    """네이버 과거 주문 소급 수집(백필) job enqueue (NAVER-INGEST-BACKFILL).

    "지금 수집" 과 같은 이유로 web 은 **enqueue 만** 한다 — 네이버 HTTP 는 등록된 IP 가
    WORKER 것뿐이다. 백필은 창 수만큼 호출이 이어지므로 job timeout 을 넉넉히 잡는다
    (90일 = 창 90개 + 창마다 0.5초 간격 + 상세 조회).

    Args:
        start_iso: 구간 시작(ISO-8601, KST).
        end_iso: 구간 끝(ISO-8601, KST).
        dry_run: True 면 조회까지만.

    Returns:
        enqueue 성공 여부.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_backfill_task",
            str(start_iso), str(end_iso), bool(dry_run),
            job_timeout="2h",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_backfill error: {e}", exc_info=True)
        return False


def enqueue_naver_order_sync(dry_run: bool = False):
    """네이버 주문 수집 job enqueue (NAVER-INGEST-01 "지금 수집").

    web 은 **enqueue 만** 한다. 실제 네이버 HTTP 는 WORKER 가 낸다 — 커머스API센터에
    등록된 호출 IP 가 WORKER 것뿐이라 web 에서 직접 부르면 차단된다. 취향이 아니라 제약이다.
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            f"{_TASK_PATH_PREFIX}.run_naver_order_sync_task",
            bool(dry_run),
            job_timeout="10m",
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_naver_order_sync error: {e}", exc_info=True)
        return False
