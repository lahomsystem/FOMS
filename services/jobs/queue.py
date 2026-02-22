"""
Redis Queue (RQ) 연결 및 enqueue 헬퍼.
REDIS_URL 있으면 enqueue 가능. (USE_RQ_WORKER는 start.sh 전용, enqueue와 분리)
"""
import os

_rq_queue = None


def get_rq_queue():
    """RQ default 큐 반환. REDIS_URL 있으면 enqueue 가능 (FOMS 웹)."""
    global _rq_queue
    if _rq_queue is not None:
        return _rq_queue
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        return None
    try:
        from redis import Redis
        from rq import Queue
        conn = Redis.from_url(redis_url)
        _rq_queue = Queue('default', connection=conn)
        return _rq_queue
    except Exception as e:
        print(f"[RQ] get_queue failed: {e}")
        return None


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
            'services.jobs.tasks.create_thumbnail_for_attachment',
            int(attachment_id),
            storage_key,
            job_timeout='5m',
        )
        return True
    except Exception as e:
        print(f"[RQ] enqueue_thumbnail error: {e}")
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
            'services.jobs.tasks.geocode_order_address',
            int(order_id),
            job_timeout='2m',
        )
        return True
    except Exception as e:
        print(f"[RQ] enqueue_geocode_order_address error: {e}")
        return False
