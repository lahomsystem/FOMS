"""
ChannelTalk 연동 상태 영속화 및 배달(Outbox) 조회 서비스
(CT-00-03 observability & admin query)
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import func

from db import get_db
from models import ChannelDeliveryLog, ChannelInboundEventLog, Order

__all__ = [
    "create_pending_delivery",
    "mark_delivery_status",
    "mark_api_failed",
    "mark_api_rejected",
    "mark_token_rate_limited",
    "get_delivery_metrics",
    "get_queue_backlog",
    "check_legacy_only_success_after_cutover",
    "mark_order_updated_for_channel",
    "mask_payload",
]

logger = logging.getLogger(__name__)


def create_pending_delivery(
    db,
    order_id: int,
    event_type: str,
    source_type: str = "order_event",
    parent_delivery_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
    order: Optional["Order"] = None,
) -> ChannelDeliveryLog:
    """CT-A-02: Pending 상태의 DeliveryLog 생성.

    order 인자가 제공되면 DB 재조회를 생략한다 (이미 세션에 로드된 경우).
    """
    if order is None:
        order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError(f"Order {order_id} not found")

    event_key = f"order_{order_id}_{event_type}_{order.channel_source_seq}"

    # 템플릿과 라우팅 정책 임시 적용
    from foms.services.channel_policy import get_routing_group_id

    target_group_id = get_routing_group_id(event_type, {"order_id": order_id})

    log = ChannelDeliveryLog(
        event_key=event_key,
        source_type=source_type,
        source_id=order_id,
        target_type="group",
        target_id=target_group_id,
        target_group_snapshot=target_group_id,
        status="pending",
        order_id=order_id,
        source_version=order.channel_source_seq,
        parent_delivery_id=parent_delivery_id,
        correlation_id=str(uuid.uuid4()),
        template_key=event_type,
        masked_request_payload=mask_payload(payload),
    )
    db.add(log)
    # Flush so callers can safely enqueue by primary key after their commit.
    db.flush()
    return log


def mark_delivery_status(
    db,
    delivery_id: int,
    status: str,
    error_msg: Optional[str] = None,
    message_id: Optional[str] = None,
):
    """CT-A-02: DeliveryLog 상태 전이"""
    log = db.query(ChannelDeliveryLog).filter(ChannelDeliveryLog.id == delivery_id).first()
    if log:
        log.status = status
        log.updated_at = datetime.datetime.now()
        if error_msg:
            log.last_error = error_msg
        if message_id:
            log.message_id = message_id
            log.sent_at = log.updated_at
        db.add(log)


def mark_api_failed(db, delivery_id: int, error_msg: str):
    mark_delivery_status(db, delivery_id, "api_failed", error_msg)


def mark_api_rejected(db, delivery_id: int, error_msg: str):
    mark_delivery_status(db, delivery_id, "api_rejected", error_msg)


def mark_token_rate_limited(db, delivery_id: int, error_msg: str):
    mark_delivery_status(db, delivery_id, "token_rate_limited", error_msg)


def get_delivery_metrics(db) -> Dict[str, Any]:
    """
    최근 24시간(또는 N분) 기준 Delivery 실패율, 성공률 등 메트릭 조회
    """
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)

    # 24시간 내 전체 시도
    total_count = db.query(func.count(ChannelDeliveryLog.id)).filter(ChannelDeliveryLog.created_at >= yesterday).scalar() or 0

    # 성공
    sent_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.created_at >= yesterday, ChannelDeliveryLog.status == "sent")
        .scalar()
        or 0
    )

    # duplicate (ignored)
    duplicate_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.created_at >= yesterday, ChannelDeliveryLog.status == "ignored_duplicate")
        .scalar()
        or 0
    )

    # resend 비율 (parent_delivery_id 가 있는 경우)
    resend_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.created_at >= yesterday, ChannelDeliveryLog.parent_delivery_id.isnot(None))
        .scalar()
        or 0
    )

    # Inbound metrics
    inbound_total = db.query(func.count(ChannelInboundEventLog.id)).filter(ChannelInboundEventLog.received_at >= yesterday).scalar() or 0

    inbound_parsed = (
        db.query(func.count(ChannelInboundEventLog.id))
        .filter(
            ChannelInboundEventLog.received_at >= yesterday,
            ChannelInboundEventLog.status.in_(["parsed_and_enqueued", "completed"]),
        )
        .scalar()
        or 0
    )

    inbound_failed = (
        db.query(func.count(ChannelInboundEventLog.id))
        .filter(ChannelInboundEventLog.received_at >= yesterday, ChannelInboundEventLog.status == "parse_failed")
        .scalar()
        or 0
    )

    success_rate = (sent_count / total_count * 100) if total_count > 0 else 100.0
    duplicate_rate = (duplicate_count / total_count * 100) if total_count > 0 else 0.0
    resend_rate = (resend_count / total_count * 100) if total_count > 0 else 0.0

    parse_success_rate = (inbound_parsed / inbound_total * 100) if inbound_total > 0 else 100.0

    return {
        "total_count_24h": total_count,
        "sent_count_24h": sent_count,
        "delivery_success_rate": round(success_rate, 2),
        "duplicate_rate": round(duplicate_rate, 2),
        "resend_rate": round(resend_rate, 2),
        "inbound_total_24h": inbound_total,
        "parse_success_rate": round(parse_success_rate, 2),
    }


def get_queue_backlog(db) -> int:
    """
    queue에 들어가지 못했거나, 처리되지 않고 pending 인 상태의 backlog 개수
    """
    return (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.status.in_(["pending", "queue_enqueue_failed", "queue_unavailable"]))
        .scalar()
        or 0
    )


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
    orders = db.query(Order.id, Order.structured_data).filter(Order.structured_updated_at >= yesterday).all()

    drift_count = 0
    for o_id, sd in orders:
        if not sd:
            continue
        push_info = sd.get("channeltalk_push")
        if push_info and push_info.get("pushed"):
            # 로그 검사
            log_count = db.query(func.count(ChannelDeliveryLog.id)).filter(ChannelDeliveryLog.order_id == o_id).scalar()
            if not log_count:
                drift_count += 1

    return drift_count


def mark_order_updated_for_channel(
    order: Order,
    event_type: str = "update",
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    주문이 변경되어 ChannelTalk 동기화가 필요함을 마킹합니다.
    CT-00-04: channel_source_seq를 증가시켜 동시성 제어 및 메시지 순서 보장의 기반을 마련합니다.
    """
    if order.channel_source_seq is None:
        order.channel_source_seq = 0
    order.channel_source_seq += 1

    # CT-A-02: DB 세션(트랜잭션) 획득 및 Outbox (ChannelDeliveryLog) row 추가
    from db import db_session

    try:
        db = db_session.object_session(order)
        if db:
            log = create_pending_delivery(db, order.id, event_type, payload=payload, order=order)
            return log.id
    except Exception as e:
        logger.error("[ChannelDelivery] Failed to create pending delivery: %s", e)
    return None


def mask_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Presigned URL 마스킹
    """
    import copy

    if not payload:
        return payload
    masked = copy.deepcopy(payload)
    files = masked.get("files", [])
    for f in files:
        if "url" in f:
            f["url"] = "[MASKED]"
    return masked
