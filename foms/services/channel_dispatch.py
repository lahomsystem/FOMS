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
    Build and send a message from ChannelDeliveryLog.
    """
    from db import db_session
    from models import ChannelDeliveryLog, Order, OrderAttachment
    from foms.services.channel_delivery import (
        mark_api_failed,
        mark_api_rejected,
        mark_delivery_status,
        mark_token_rate_limited,
        mask_payload,
    )
    from foms.services.storage import get_storage

    session = db_session()
    try:
        log = session.query(ChannelDeliveryLog).filter(ChannelDeliveryLog.id == delivery_id).first()
        if not log:
            logger.warning("[ChannelDispatch] Delivery log %s not found", delivery_id)
            return

        if log.status != "pending":
            logger.info("[ChannelDispatch] Delivery log %s skipped because status=%s", delivery_id, log.status)
            return

        order = session.query(Order).filter(Order.id == log.order_id).first()
        if not order:
            mark_delivery_status(session, log.id, "ignored_stale", "Order deleted")
            session.commit()
            return

        if log.source_version and order.channel_source_seq and log.source_version < order.channel_source_seq:
            mark_delivery_status(
                session,
                log.id,
                "ignored_stale",
                f"Stale event (log_v={log.source_version} < order_v={order.channel_source_seq})",
            )
            session.commit()
            return

        event_type = _extract_event_type(log)
        log_payload = copy.deepcopy(log.masked_request_payload or {})
        data = _build_dispatch_data(order, log_payload)

        img_category = get_attachment_category_for_status(order.status)
        files = []
        if img_category:
            storage = get_storage()
            attachments = (
                session.query(OrderAttachment)
                .filter(
                    OrderAttachment.order_id == order.id,
                    OrderAttachment.category == img_category,
                    OrderAttachment.file_type == "image",
                )
                .order_by(OrderAttachment.id.desc())
                .limit(5)
                .all()
            )
            for att in attachments:
                if not att.storage_key:
                    continue
                url = storage.get_download_url(att.storage_key, expires_in=3600)
                if url:
                    files.append(
                        {
                            "fileName": att.filename or "image.jpg",
                            "url": url,
                            "mime": "image/jpeg",
                        }
                    )

        data["files"] = files
        group_id = get_routing_group_id(event_type, data)
        if not group_id:
            logger.warning("[ChannelDispatch] No routing group for event_type=%s", event_type)
            log.template_key = event_type
            log.last_error = "No routing group"
            mark_api_failed(session, log.id, "No routing group")
            session.commit()
            return

        plain_text = build_message_template(event_type, data)
        blocks = build_message_blocks(event_type, data)
        files = apply_attachment_policy(files)

        log.template_key = event_type
        log.target_group_snapshot = group_id
        log.rendered_text_snapshot = plain_text
        log.masked_request_payload = mask_payload(data)

        try:
            result = send_group_message(
                group_id=group_id,
                plain_text=plain_text,
                blocks=blocks,
                files=files,
                bot_name="FOMS",
                raise_on_error=True,
            )
            log.masked_response_payload = {"success": True, "message_id": result.get("message_id")}
            mark_delivery_status(session, log.id, "sent", message_id=result.get("message_id"))
            session.commit()
        except requests.exceptions.HTTPError as exc:
            response = exc.response
            if response is not None:
                log.masked_response_payload = {"success": False, "status_code": response.status_code}
                if response.status_code == 429:
                    mark_token_rate_limited(session, log.id, str(exc))
                elif 400 <= response.status_code < 500:
                    mark_api_rejected(session, log.id, str(exc))
                else:
                    mark_api_failed(session, log.id, str(exc))
            else:
                log.masked_response_payload = {"success": False}
                mark_api_failed(session, log.id, str(exc))
            session.commit()
            raise
        except Exception as exc:
            log.masked_response_payload = {"success": False}
            mark_api_failed(session, log.id, str(exc))
            session.commit()
            raise
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
