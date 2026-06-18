"""ChannelTalk dispatch service."""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict

import requests

from foms.services.channel_client import get_attachment_category_for_status, send_group_message
from foms.services.channel_policy import (
    apply_attachment_policy,
    build_message_blocks,
    build_message_template,
    get_routing_group_id,
)

__all__ = [
    "dispatch_channel_push",
    "dispatch_order_event",
]

logger = logging.getLogger(__name__)


def _extract_event_type(log) -> str:
    if getattr(log, "template_key", None):
        return log.template_key

    payload = getattr(log, "masked_request_payload", None) or {}
    payload_event_type = payload.get("event_type")
    if payload_event_type:
        return payload_event_type

    parts = (log.event_key or "").split("_")
    if len(parts) >= 4:
        return "_".join(parts[2:-1]) or "update"
    if len(parts) >= 3:
        return parts[2]
    return "update"


def _extract_customer_name(order) -> str:
    sd = order.structured_data or {}
    return ((sd.get("parties") or {}).get("customer") or {}).get("name") or order.customer_name


def _extract_address(order) -> str:
    sd = order.structured_data or {}
    site = sd.get("site") or {}
    return site.get("address_full") or site.get("address_main") or order.address


def _build_dispatch_data(order, log_payload: Dict[str, Any]) -> Dict[str, Any]:
    sd = order.structured_data or {}
    data = {
        "order_id": order.id,
        "customer_name": _extract_customer_name(order),
        "address": _extract_address(order),
        "measurement_date": ((sd.get("schedule") or {}).get("measurement") or {}).get("date", "-"),
        "status": order.status,
    }
    if log_payload:
        data.update(copy.deepcopy(log_payload))
    data["order_id"] = order.id
    data.setdefault("customer_name", _extract_customer_name(order))
    data.setdefault("address", _extract_address(order))
    data.setdefault("measurement_date", ((sd.get("schedule") or {}).get("measurement") or {}).get("date", "-"))
    data.setdefault("status", order.status)
    return data


def dispatch_channel_push(delivery_id: int):
    """
    Auto outbox worker entry — retired.

    Pending ChannelDeliveryLog rows are marked ignored so backlog does not send
    `[알림]` messages. Intentional ERP pushes use dispatch_order_event (manual).
    """
    from db import db_session
    from models import ChannelDeliveryLog
    from foms.services.channel_delivery import mark_delivery_status

    session = db_session()
    try:
        log = session.query(ChannelDeliveryLog).filter(ChannelDeliveryLog.id == delivery_id).first()
        if not log:
            logger.warning("[ChannelDispatch] Delivery log %s not found", delivery_id)
            return

        if log.status != "pending":
            logger.info("[ChannelDispatch] Delivery log %s skipped because status=%s", delivery_id, log.status)
            return

        mark_delivery_status(session, log.id, "ignored_stale", "Automatic ChannelTalk push disabled")
        session.commit()
        logger.info("[ChannelDispatch] Delivery log %s ignored (auto push disabled)", delivery_id)
    except Exception as exc:
        logger.error("[ChannelDispatch] Error in dispatch_channel_push for log %s: %s", delivery_id, exc, exc_info=True)
        raise
    finally:
        session.close()


def dispatch_order_event(event_type: str, data: Dict[str, Any], raise_on_error: bool = False) -> dict:
    """
    Send a direct/manual ChannelTalk event without the outbox worker.
    """
    try:
        group_id = get_routing_group_id(event_type, data)
        if not group_id:
            logger.warning("[ChannelDispatch] No routing group for event_type=%s", event_type)
            return {"success": False, "message_id": None}

        plain_text = build_message_template(event_type, data)
        blocks = build_message_blocks(event_type, data)
        files = apply_attachment_policy(data.get("files", []))

        return send_group_message(
            group_id=group_id,
            plain_text=plain_text,
            blocks=blocks,
            files=files,
            bot_name="FOMS",
            raise_on_error=raise_on_error,
        )
    except Exception as exc:
        logger.error("[ChannelDispatch] Dispatch failed: %s", exc, exc_info=True)
        if raise_on_error:
            raise
        return {"success": False, "message_id": None}
