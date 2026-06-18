"""
Redis Queue (RQ) 연결 및 enqueue 헬퍼.
REDIS_URL 있으면 enqueue 가능. (USE_RQ_WORKER는 start.sh 전용, enqueue와 분리)
"""

from __future__ import annotations

import logging
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

        conn = Redis.from_url(redis_url)
        _rq_queue = Queue("default", connection=conn)
        return _rq_queue
    except Exception as e:
        logger.warning(f"[RQ] get_queue failed: {e}", exc_info=True)
        return None


def get_rq_worker_count(q=None):
    """Return the live worker count for the default queue."""
    q = q or get_rq_queue()
    if not q:
        return 0

    try:
        from rq import Worker

        return int(Worker.count(connection=q.connection, queue=q))
    except Exception as e:
        logger.warning(f"[RQ] Worker.count failed: {e}", exc_info=True)

    try:
        from rq import Worker

        workers = Worker.all(connection=q.connection, queue=q)
        return len(workers)
    except Exception as e:
        logger.warning(f"[RQ] Worker.all fallback failed: {e}", exc_info=True)
        return 0


def get_rq_runtime_status():
    """Inspect Redis reachability and live worker count for readiness checks."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        return {
            "state": "disabled",
            "worker_count": 0,
        }

    q = get_rq_queue()
    if not q:
        return {
            "state": "unreachable",
            "worker_count": 0,
        }

    try:
        q.connection.ping()
    except Exception as e:
        logger.warning(f"[RQ] ping failed: {e}", exc_info=True)
        return {
            "state": "unreachable",
            "worker_count": 0,
        }

    return {
        "state": "reachable",
        "worker_count": get_rq_worker_count(q),
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
