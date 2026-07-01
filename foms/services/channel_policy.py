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

# ChannelTalk 1메시지당 최대 첨부 수. 채널톡이 10→20으로 상향(2026-06).
MAX_MANUAL_ATTACHMENTS = 20


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


def _manual_push_body_lines(user_message: str, change_note: str | None = None) -> list[str]:
    """Build the single-line list for a manual push (resend header + conversion body).

    Each element is one visual line. Multi-line inputs (note/body) are pre-split so the
    caller can map one line to one ChannelTalk block.

    Args:
        user_message: ERP conversion text (고객명 ~).
        change_note: Re-push note; when set, prepends ``[수정]`` and the note lines.

    Returns:
        Flat line list consumed by ``_paragraph_blocks``.
    """
    text = str(user_message or "").strip()
    note = str(change_note or "").strip()
    lines: list[str] = []
    if note:
        lines.append("[수정]")
        lines.extend(note.splitlines())
        # Blank line: paragraph break for the plainText fallback; skipped by block builder.
        lines.append("")
    if text:
        lines.extend(text.splitlines())
    return lines


def _paragraph_blocks(lines: List[str]) -> list[dict[str, str]]:
    """Map each non-empty line to its own ChannelTalk text block.

    ChannelTalk renders every block on its own line, but does NOT reliably render a raw
    ``\\n`` inside a single block's ``value`` as a line break. So line breaks must be
    expressed structurally (one block per line) rather than by joining lines with ``\\n``.
    """
    return [_text_block(line) for line in lines if line.strip()]


def build_message_blocks(event_type: str, data: Dict[str, Any]) -> list[dict[str, str]]:
    """Render ChannelTalk rich blocks for manual ERP push."""
    if event_type != "manual":
        raise ValueError(f"Unsupported ChannelTalk event_type for blocks: {event_type}")

    order_id = data.get("order_id", "?")
    detail_url = data.get("detail_url") or _build_order_detail_link(order_id)
    user_message = str(data.get("text", "")).strip()
    change_note = str(data.get("change_note") or "").strip() if data.get("is_retry") else ""
    lines = _manual_push_body_lines(user_message, change_note or None)
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
    change_note = str(data.get("change_note") or "").strip() if data.get("is_retry") else ""
    body_lines = _manual_push_body_lines(user_message, change_note or None)
    paragraphs: list[str] = []
    paragraph: list[str] = []
    for line in body_lines:
        if line.strip():
            paragraph.append(line)
            continue
        if paragraph:
            paragraphs.append("\n".join(paragraph))
            paragraph = []
    if paragraph:
        paragraphs.append("\n".join(paragraph))
    body = "\n\n".join(paragraphs)
    return f"{body}\n\n{link_str}" if body else link_str


def apply_attachment_policy(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply a simple attachment cap for manual push."""
    return files[:MAX_MANUAL_ATTACHMENTS]


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
        "max_attachments": MAX_MANUAL_ATTACHMENTS,
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
