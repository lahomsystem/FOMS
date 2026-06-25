"""ChannelTalk routing and manual ERP push message policy."""

from __future__ import annotations

import html
import os
from typing import Any, Dict, List

__all__ = [
    "DEDUPE_WINDOWS",
    "build_message_blocks",
    "get_routing_group_id",
    "build_message_template",
    "apply_attachment_policy",
    "get_policy_version",
    "resolve_push_policy",
    "resolve_resend_policy",
    "resolve_inbound_policy",
]

DEDUPE_WINDOWS = {
    "manual": 0,
}


def _build_order_detail_link(order_id: Any) -> str:
    erp_url = os.environ.get("FOMS_BASE_URL", "https://lahom-dev.up.railway.app").rstrip("/")
    fallback = f"{erp_url}/edit/{order_id}?open=erp-order"
    try:
        from foms.services.channel_security import generate_wam_short_link_token

        token = generate_wam_short_link_token(int(order_id))
        return f"{erp_url}/w/{token}"
    except Exception:
        return fallback


def _text_block(value: str) -> dict[str, str]:
    """ChannelTalk text blocks are plain text; do not HTML-escape body content."""
    return {"type": "text", "value": value}


def _paragraph_blocks(lines: List[str]) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    paragraph: list[str] = []
    for line in lines:
        if line.strip():
            paragraph.append(line)
            continue
        if paragraph:
            blocks.append(_text_block("\n".join(paragraph)))
            paragraph = []
    if paragraph:
        blocks.append(_text_block("\n".join(paragraph)))
    return blocks


def build_message_blocks(event_type: str, data: Dict[str, Any]) -> list[dict[str, str]]:
    """Render ChannelTalk rich blocks for manual ERP push."""
    if event_type != "manual":
        raise ValueError(f"Unsupported ChannelTalk event_type for blocks: {event_type}")

    order_id = data.get("order_id", "?")
    detail_url = data.get("detail_url") or _build_order_detail_link(order_id)
    user_message = str(data.get("text", "")).strip()
    is_retry = data.get("is_retry", False)
    lines: list[str] = []
    if is_retry:
        lines.append("[수정]")
    if user_message:
        if lines:
            lines.extend(["", user_message])
        else:
            lines.append(user_message)
    blocks = _paragraph_blocks(lines)
    blocks.append(
        {
            "type": "text",
            "value": f"🔗 <link type=\"url\" value=\"{html.escape(detail_url, quote=True)}\">주문 보기</link>",
        }
    )
    return blocks


def get_routing_group_id(event_type: str, order_info: Dict[str, Any] = None) -> str:
    """Return the ChannelTalk group id for a manual ERP push.

    Routing branches on ``push_kind``:
        - ``drawing`` (발주 PUSH): 도면 그룹(``CHANNEL_GROUP_DRAWING``,
          미설정 시 운영 그룹 229625로 폴백).
        - 그 외(영발 PUSH, 기본): 실측 그룹(``CHANNEL_GROUP_MEASUREMENT``,
          미설정 시 운영 그룹 209990으로 폴백).

    Args:
        event_type: 항상 ``manual``.
        order_info: ``push_kind`` 키를 포함할 수 있는 dispatch payload.

    Returns:
        ChannelTalk 그룹 id 문자열.
    """
    _ = event_type
    push_kind = (order_info or {}).get("push_kind", "measurement")
    if push_kind == "drawing":
        return os.environ.get("CHANNEL_GROUP_DRAWING", "229625")
    return os.environ.get("CHANNEL_GROUP_MEASUREMENT", "209990")


def build_message_template(event_type: str, data: Dict[str, Any]) -> str:
    """Render plain-text body for manual ERP push."""
    if event_type != "manual":
        raise ValueError(f"Unsupported ChannelTalk event_type for template: {event_type}")

    order_id = data.get("order_id", "?")
    detail_url = data.get("detail_url") or _build_order_detail_link(order_id)
    link_str = f"🔗 주문 상세 보기: {detail_url}"
    user_message = str(data.get("text", "")).strip()
    is_retry = data.get("is_retry", False)
    body_parts: list[str] = []
    if is_retry:
        body_parts.append("[수정]")
    if user_message:
        body_parts.append(user_message)
    body = "\n\n".join(body_parts)
    return f"{body}\n\n{link_str}" if body else link_str


def apply_attachment_policy(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply a simple attachment cap for manual push."""
    return files[:10]


def get_policy_version() -> str:
    """Return the ChannelTalk push policy version."""
    return "2.0.0-manual-only"


def resolve_push_policy(event_type: str, order_snapshot: Dict[str, Any], wave: str = None) -> Dict[str, Any]:
    """Return routing policy for manual push (legacy policy API compatibility)."""
    _ = (order_snapshot, wave)
    group_id = get_routing_group_id(event_type, {})
    return {
        "group_id": group_id,
        "dedupe_window": DEDUPE_WINDOWS.get("manual", 0),
        "template_key": "manual",
        "max_attachments": 10,
    }


def resolve_resend_policy(event_type: str, actor_role: str) -> Dict[str, Any]:
    """Return resend policy for manual push."""
    allowed = actor_role in ["ADMIN", "MANAGER"]
    return {
        "allowed": allowed,
        "default_mode": "latest",
    }


def resolve_inbound_policy(group_id: str, template_key: str, create_enabled: bool) -> Dict[str, Any]:
    """Return inbound webhook policy."""
    allowed_groups_str = os.environ.get("CHANNEL_ALLOWED_GROUP_IDS", "")
    allowed_groups = [g.strip() for g in allowed_groups_str.split(",")] if allowed_groups_str else []

    return {
        "is_allowed_group": not allowed_groups or group_id in allowed_groups,
        "can_create": create_enabled,
    }
