"""
Redis Queue (RQ) 연결 및 enqueue 헬퍼.
REDIS_URL 있으면 enqueue 가능. (USE_RQ_WORKER는 start.sh 전용, enqueue와 분리)

[ChannelTalk 연동 - Queue & Session Ownership Contract (CT-00-05)]
1. Transaction Outbox:
   - enqueue_channeltalk_push()는 반드시 db.commit() 직후에 호출해야 합니다.
   - 큐 장애 시 ChannelDeliveryLog의 status('pending')를 기반으로 cron/admin에서 재시도할 수 있어야 합니다 (Outbox Pattern).
   - Redis Queue 자체는 휘발될 수 있음을 가정하며, Source-of-Truth는 DB의 ChannelDeliveryLog 입니다.

2. Session Ownership:
   - Enqueue 하는 웹 프로세스: ChannelDeliveryLog Row를 'pending' 상태로 INSERT/UPDATE 하고 Commit.
   - RQ Worker 프로세스: Enqueue된 job을 받아 ChannelDeliveryLog를 조회하고 채널톡 API 통신 후 결과를 DB에 반영.
   - worker는 자신의 job id와 일치하는 row만 처리해야 하며 (optimistic lock), timeout 시 재시도 로직은 worker가 아닌 스케줄러가 통제합니다.

3. Queue Cutover Rollback:
   - 장애 발생 시 `CHANNEL_PUSH_ENABLED=false` 처리하면 큐는 그대로 통과(drain)하되, API 통신을 생략(ignored)하거나 
     구버전 동기 전송(legacy_only_success_after_cutover) 로 롤백할 수 있도록 worker 코드가 설계되어야 합니다.
"""
import os
import logging

logger = logging.getLogger(__name__)

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
        logger.warning(f"[RQ] get_queue failed: {e}", exc_info=True)
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
            'services.jobs.tasks.geocode_order_address',
            int(order_id),
            job_timeout='2m',
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_geocode_order_address error: {e}", exc_info=True)
        return False


def enqueue_channeltalk_push(order_id, event_type="update"):
    """
    채널톡 그룹 메시지 push job enqueue.

    Args:
        order_id: Order.id
        event_type: "new" / "update" / "save"

    Returns:
        큐 등록 성공 여부 (False이면 RQ 미활성화)
    """
    q = get_rq_queue()
    if not q:
        return False
    try:
        q.enqueue(
            'services.jobs.tasks.push_order_to_channeltalk',
            int(order_id),
            event_type,
            job_timeout='2m',
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_channeltalk_push error: {e}", exc_info=True)
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
            'services.jobs.tasks.process_channeltalk_inbound',
            event_log_id,
            job_timeout='5m',
        )
        return True
    except Exception as e:
        logger.error(f"[RQ] enqueue_channeltalk_inbound error: {e}", exc_info=True)
        return False

