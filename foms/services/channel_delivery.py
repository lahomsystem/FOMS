"""
ChannelTalk delivery observability (admin health / historical logs).

Automatic order-change push/outbox was removed; ERP 발주방 알림은
/api/channel/push-manual(푸쉬 버튼)만 사용한다.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict

from sqlalchemy import func

from models import ChannelDeliveryLog, ChannelInboundEventLog

__all__ = [
    "mark_delivery_status",
    "get_delivery_metrics",
    "get_queue_backlog",
    "check_legacy_only_success_after_cutover",
]

logger = logging.getLogger(__name__)


def mark_delivery_status(
    db,
    delivery_id: int,
    status: str,
    error_msg: str | None = None,
    message_id: str | None = None,
) -> None:
    """Update a historical ChannelDeliveryLog row (admin/legacy drain only)."""
    log = db.query(ChannelDeliveryLog).filter(ChannelDeliveryLog.id == delivery_id).first()
    if not log:
        return
    log.status = status
    log.updated_at = datetime.datetime.now()
    if error_msg:
        log.last_error = error_msg
    if message_id:
        log.message_id = message_id
        log.sent_at = log.updated_at
    db.add(log)


def get_delivery_metrics(db) -> Dict[str, Any]:
    """Return recent ChannelDeliveryLog and inbound metrics for admin health."""
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)

    total_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.created_at >= yesterday)
        .scalar()
        or 0
    )
    sent_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.created_at >= yesterday, ChannelDeliveryLog.status == "sent")
        .scalar()
        or 0
    )
    duplicate_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(
            ChannelDeliveryLog.created_at >= yesterday,
            ChannelDeliveryLog.status == "ignored_duplicate",
        )
        .scalar()
        or 0
    )
    resend_count = (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(
            ChannelDeliveryLog.created_at >= yesterday,
            ChannelDeliveryLog.parent_delivery_id.isnot(None),
        )
        .scalar()
        or 0
    )

    inbound_total = (
        db.query(func.count(ChannelInboundEventLog.id))
        .filter(ChannelInboundEventLog.received_at >= yesterday)
        .scalar()
        or 0
    )
    inbound_parsed = (
        db.query(func.count(ChannelInboundEventLog.id))
        .filter(
            ChannelInboundEventLog.received_at >= yesterday,
            ChannelInboundEventLog.status.in_(["parsed_and_enqueued", "completed"]),
        )
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
    """Count legacy outbox rows that were never drained (historical observability)."""
    return (
        db.query(func.count(ChannelDeliveryLog.id))
        .filter(ChannelDeliveryLog.status.in_(["pending", "queue_enqueue_failed", "queue_unavailable"]))
        .scalar()
        or 0
    )


def check_legacy_only_success_after_cutover(db) -> int:
    """Manual-only push no longer writes ChannelDeliveryLog; cutover drift metric retired."""
    _ = db
    return 0
