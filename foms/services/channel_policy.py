"""ChannelTalk unified routing and message template policy."""

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

# Dedupe Windows (seconds)
DEDUPE_WINDOWS = {
    "urgent": 0,
    "manual": 0,
    "normal": 60,
    "info": 300,
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


def _render_change_lines(change_lines: List[str]) -> str:
    lines = [str(line).strip() for line in (change_lines or []) if str(line).strip()]
    if not lines:
        return ""
    return "\n".join(f"- {line}" for line in lines)


def _text_block(value: str) -> dict[str, str]:
    return {"type": "text", "value": html.escape(value, quote=True)}


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
    """Render ChannelTalk rich blocks so links can be shown as a short label."""
    order_id = data.get("order_id", "?")
    customer_name = data.get("customer_name", "고객")
    detail_url = data.get("detail_url") or _build_order_detail_link(order_id)

    if event_type == "manual":
        user_message = str(data.get("text", "")).strip()
        is_retry = data.get("is_retry", False)
        lines = [
            "[수정]" if is_retry else "[ERP 푸시]",
            f"주문 #{order_id} - {customer_name}",
        ]
        if user_message:
            lines.extend(["", user_message])
        blocks = _paragraph_blocks(lines)
        blocks.append(
            {
                "type": "text",
                "value": f"🔗 <link type=\"url\" value=\"{html.escape(detail_url, quote=True)}\">주문 보기</link>",
            }
        )
        return blocks

    if event_type == "measurement_completed":
        address = data.get("address", "-")
        date_str = data.get("measurement_date", "-")
        blocks = _paragraph_blocks(
            [
                f"[실측완료] 주문 #{order_id} - {customer_name} 고객",
                "실측이 완료되어 보고서가 등록되었습니다.",
                "",
                f"📍 주소: {address}",
                f"📅 실측일: {date_str}",
            ]
        )
        blocks.append(
            {
                "type": "text",
                "value": f"🔗 <link type=\"url\" value=\"{html.escape(detail_url, quote=True)}\">주문 보기</link>",
            }
        )
        return blocks

    if event_type == "urgent":
        reason = data.get("reason", "긴급 확인 필요")
        blocks = _paragraph_blocks(
            [
                f"🚨 [긴급] 주문 #{order_id} - {customer_name} 고객",
                str(reason),
                "관련 담당자는 즉시 확인 바랍니다. @all",
            ]
        )
        blocks.append(
            {
                "type": "text",
                "value": f"🔗 <link type=\"url\" value=\"{html.escape(detail_url, quote=True)}\">주문 보기</link>",
            }
        )
        return blocks

    event_title = data.get("event_title") or {
        "stage_changed": "상태 변경",
        "manager_changed": "담당자 변경",
        "owner_team_changed": "담당 팀 변경",
        "schedule_changed": "일정 변경",
        "shipment_updated": "출고/시공 정보 변경",
        "payment_confirmation_changed": "결제 확인 변경",
        "order_updated": "정보 변경",
    }.get(event_type, "상태 변경")
    change_lines = [str(line).strip() for line in (data.get("change_lines") or []) if str(line).strip()]
    changed_by = str(data.get("changed_by") or "").strip()
    reason = str(data.get("reason") or "").strip()

    blocks = _paragraph_blocks([f"[알림] 주문 #{order_id} - {customer_name} {event_title}"])
    if change_lines:
        blocks.append(
            {
                "type": "bullets",
                "blocks": [{"type": "text", "value": html.escape(line, quote=True)} for line in change_lines],
            }
        )
    if reason and event_type != "urgent":
        blocks.extend(_paragraph_blocks([f"사유: {reason}"]))
    if changed_by:
        blocks.extend(_paragraph_blocks([f"변경자: {changed_by}"]))
    blocks.append(
        {
            "type": "text",
            "value": f"🔗 <link type=\"url\" value=\"{html.escape(detail_url, quote=True)}\">주문 보기</link>",
        }
    )
    return blocks


def get_routing_group_id(event_type: str, order_info: Dict[str, Any] = None) -> str:
    """Return the ChannelTalk group id for the event."""
    base_group = os.environ.get("CHANNEL_GROUP_MEASUREMENT", "")
    if event_type == "as_urgent":
        return os.environ.get("CHANNEL_GROUP_AS", base_group)
    return base_group


def build_message_template(event_type: str, data: Dict[str, Any]) -> str:
    """Render a ChannelTalk message body from the event payload."""
    order_id = data.get("order_id", "?")
    customer_name = data.get("customer_name", "고객")
    detail_url = data.get("detail_url") or _build_order_detail_link(order_id)
    link_str = f"🔗 주문 상세 보기: {detail_url}"

    if event_type == "manual":
        user_message = data.get("text", "")
        is_retry = data.get("is_retry", False)
        prefix = "[수정]\n" if is_retry else "[ERP 푸시]\n"
        return f"{prefix}주문 #{order_id} - {customer_name}\n\n{user_message}\n\n{link_str}"

    if event_type == "measurement_completed":
        address = data.get("address", "-")
        date_str = data.get("measurement_date", "-")
        return (
            f"[실측완료] 주문 #{order_id} - {customer_name} 고객\n"
            f"실측이 완료되어 보고서가 등록되었습니다.\n"
            f"📍 주소: {address}\n"
            f"📅 실측일: {date_str}\n\n"
            f"{link_str}"
        )

    if event_type == "urgent":
        reason = data.get("reason", "긴급 확인 필요")
        return (
            f"🚨 [긴급] 주문 #{order_id} - {customer_name} 고객\n"
            f"{reason}\n"
            f"관련 담당자는 즉시 확인 바랍니다. @all\n\n"
            f"{link_str}"
        )

    event_title = data.get("event_title") or {
        "stage_changed": "상태 변경",
        "manager_changed": "담당자 변경",
        "owner_team_changed": "담당 팀 변경",
        "schedule_changed": "일정 변경",
        "shipment_updated": "출고/시공 정보 변경",
        "payment_confirmation_changed": "결제 확인 변경",
        "order_updated": "정보 변경",
    }.get(event_type, "상태 변경")
    change_block = _render_change_lines(data.get("change_lines") or [])
    changed_by = str(data.get("changed_by") or "").strip()
    reason = str(data.get("reason") or "").strip()

    lines = [f"[알림] 주문 #{order_id} - {customer_name} {event_title}"]
    if change_block:
        lines.append("")
        lines.append(change_block)
    if reason and event_type != "urgent":
        lines.append("")
        lines.append(f"사유: {reason}")
    if changed_by:
        lines.append("")
        lines.append(f"변경자: {changed_by}")
    lines.append("")
    lines.append(link_str)
    return "\n".join(lines)


def apply_attachment_policy(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply a simple attachment cap."""
    return files[:10]


def get_policy_version() -> str:
    """Return the ChannelTalk push policy version."""
    return "1.0.0"


def resolve_push_policy(event_type: str, order_snapshot: Dict[str, Any], wave: str = None) -> Dict[str, Any]:
    """Return routing and processing policy for an event."""
    group_id = get_routing_group_id(event_type, order_snapshot)
    dedupe_window = DEDUPE_WINDOWS.get("normal", 60)
    if event_type in ["manual", "urgent", "as_urgent"]:
        dedupe_window = DEDUPE_WINDOWS.get(event_type, 0)

    return {
        "group_id": group_id,
        "dedupe_window": dedupe_window,
        "template_key": event_type,
        "max_attachments": 10,
    }


def resolve_resend_policy(event_type: str, actor_role: str) -> Dict[str, Any]:
    """Return resend policy for an event."""
    allowed = actor_role in ["ADMIN", "MANAGER"]
    return {
        "allowed": allowed,
        "default_mode": "snapshot" if event_type != "manual" else "latest",
    }


def resolve_inbound_policy(group_id: str, template_key: str, create_enabled: bool) -> Dict[str, Any]:
    """Return inbound webhook policy."""
    allowed_groups_str = os.environ.get("CHANNEL_ALLOWED_GROUP_IDS", "")
    allowed_groups = [g.strip() for g in allowed_groups_str.split(",")] if allowed_groups_str else []

    return {
        "is_allowed_group": not allowed_groups or group_id in allowed_groups,
        "can_create": create_enabled,
    }
