"""
ChannelTalk 연동 상태 영속화 및 배달(Outbox) 조회 서비스
(CT-00-03 observability & admin query)
"""

from typing import Dict, Any, List
import datetime
from sqlalchemy import func
from db import get_db
from models import ChannelDeliveryLog, Order
import os
import logging

logger = logging.getLogger(__name__)

def get_delivery_metrics(db) -> Dict[str, Any]:
    """
    최근 24시간(또는 N분) 기준 Delivery 실패율, 성공률 등 메트릭 조회
    """
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    
    # 24시간 내 전체 시도
    total_count = db.query(func.count(ChannelDeliveryLog.id))\
        .filter(ChannelDeliveryLog.created_at >= yesterday).scalar() or 0
    
    # 성공
    sent_count = db.query(func.count(ChannelDeliveryLog.id))\
        .filter(ChannelDeliveryLog.created_at >= yesterday,
                ChannelDeliveryLog.status == 'sent').scalar() or 0
        
    # duplicate (ignored)
    duplicate_count = db.query(func.count(ChannelDeliveryLog.id))\
        .filter(ChannelDeliveryLog.created_at >= yesterday,
                ChannelDeliveryLog.status == 'ignored_duplicate').scalar() or 0
        
    # resend 비율 (parent_delivery_id 가 있는 경우)
    resend_count = db.query(func.count(ChannelDeliveryLog.id))\
        .filter(ChannelDeliveryLog.created_at >= yesterday,
                ChannelDeliveryLog.parent_delivery_id.isnot(None)).scalar() or 0
    
    success_rate = (sent_count / total_count * 100) if total_count > 0 else 100.0
    duplicate_rate = (duplicate_count / total_count * 100) if total_count > 0 else 0.0
    resend_rate = (resend_count / total_count * 100) if total_count > 0 else 0.0

    return {
        "total_count_24h": total_count,
        "sent_count_24h": sent_count,
        "delivery_success_rate": round(success_rate, 2),
        "duplicate_rate": round(duplicate_rate, 2),
        "resend_rate": round(resend_rate, 2),
    }

def get_queue_backlog(db) -> int:
    """
    queue에 들어가지 못했거나, 처리되지 않고 pending 인 상태의 backlog 개수
    """
    return db.query(func.count(ChannelDeliveryLog.id))\
        .filter(ChannelDeliveryLog.status.in_(['pending', 'queue_enqueue_failed', 'queue_unavailable'])).scalar() or 0

def check_legacy_only_success_after_cutover(db) -> int:
    """
    CT-A-01 이후 신규 전송 건에 대해 ChannelDeliveryLog 없이 
    Order.structured_data['channeltalk_push'] 에만 기록된 건수 확인.
    (간이 구현: 최근 24시간 기준)
    """
    # 임시: 실제 cutover가 일어나기 전까지는 0 반환 또는 무시
    # 나중에 정확히 구현 예정
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    
    # structured_updated_at 이 24시간 내이며, channeltalk_push.pushed = true 인 주문 중
    # 해당 order_id로 ChannelDeliveryLog 가 0건인 주문
    orders = db.query(Order.id, Order.structured_data)\
        .filter(Order.structured_updated_at >= yesterday)\
        .all()
    
    drift_count = 0
    for o_id, sd in orders:
        if not sd: continue
        push_info = sd.get('channeltalk_push')
        if push_info and push_info.get('pushed'):
            # 로그 검사
            log_count = db.query(func.count(ChannelDeliveryLog.id))\
                .filter(ChannelDeliveryLog.order_id == o_id).scalar()
            if not log_count:
                drift_count += 1
                
    return drift_count

def mark_order_updated_for_channel(order: Order, event_type: str = 'update'):
    """
    주문이 변경되어 ChannelTalk 동기화가 필요함을 마킹합니다.
    CT-00-04: channel_source_seq를 증가시켜 동시성 제어 및 메시지 순서 보장의 기반을 마련합니다.
    """
    if order.channel_source_seq is None:
        order.channel_source_seq = 0
    order.channel_source_seq += 1
    
    # 향후 Phase A(CT-A-02)에서 이 위치에 ChannelDeliveryLog(상태=pending) row INSERT 로직이 추가됩니다.
    # pending 로우를 추가한 뒤, 트랜잭션이 commit 되면 Redis queue에 enqueue 하는 구조입니다.

def mask_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Presigned URL 마스킹
    """
    import copy
    if not payload:
        return payload
    masked = copy.deepcopy(payload)
    files = masked.get('files', [])
    for f in files:
        if 'url' in f:
            f['url'] = '[MASKED]'
    return masked
