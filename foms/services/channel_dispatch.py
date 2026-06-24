"""ChannelTalk dispatch service (manual ERP push only)."""

from __future__ import annotations

import logging
from typing import Any, Dict

from foms.services.channel_client import build_channel_bot_name, send_group_message
from foms.services.channel_policy import (
    apply_attachment_policy,
    build_message_blocks,
    build_message_template,
    get_routing_group_id,
)

__all__ = ["dispatch_order_event"]

logger = logging.getLogger(__name__)


def dispatch_order_event(event_type: str, data: Dict[str, Any], raise_on_error: bool = False) -> dict:
    """
    Send a manual ChannelTalk message without the retired auto-push outbox worker.

    Args:
        event_type: Must be ``manual`` (ERP 푸쉬 버튼).
        data: Order id, customer name, conversion text, optional attachment files,
            optional ``pushed_by_name`` (FOMS login display name for botName).
        raise_on_error: Propagate ChannelTalk API failures when True.

    Returns:
        ChannelTalk send result dict with ``success`` and ``message_id``.
    """
    if event_type != "manual":
        logger.warning("[ChannelDispatch] unsupported event_type=%s (manual only)", event_type)
        return {"success": False, "message_id": None}

    try:
        group_id = get_routing_group_id(event_type, data)
        if not group_id:
            logger.warning("[ChannelDispatch] No routing group for manual push")
            return {"success": False, "message_id": None}

        plain_text = build_message_template(event_type, data)
        blocks = build_message_blocks(event_type, data)
        files = apply_attachment_policy(data.get("files", []))

        return send_group_message(
            group_id=group_id,
            plain_text=plain_text,
            blocks=blocks,
            files=files,
            bot_name=build_channel_bot_name(data.get("pushed_by_name")),
            raise_on_error=raise_on_error,
        )
    except Exception as exc:
        logger.error("[ChannelDispatch] Manual dispatch failed: %s", exc, exc_info=True)
        if raise_on_error:
            raise
        return {"success": False, "message_id": None}
