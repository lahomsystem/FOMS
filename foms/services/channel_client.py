"""ChannelTalk Native Functions API client."""

from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any

import requests

logger = logging.getLogger(__name__)

_NATIVE_FUNCTIONS_URL = "https://app-store-api.channel.io/general/v1/native/functions"
_TOKEN_TTL_SECONDS = 29 * 60  # 29-minute cache (30-minute expiry minus one-minute buffer)

CHANNEL_APP_SECRET = os.environ.get("CHANNEL_APP_SECRET", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")
CHANNEL_GROUP_MEASUREMENT = os.environ.get("CHANNEL_GROUP_MEASUREMENT", "")
CHANNEL_GROUP_CONSTRUCTION = os.environ.get("CHANNEL_GROUP_CONSTRUCTION", "")
CHANNEL_GROUP_GENERAL = os.environ.get("CHANNEL_GROUP_GENERAL", "")
FOMS_BASE_URL = os.environ.get("FOMS_BASE_URL", "https://lahom-production.up.railway.app")

__all__ = [
    "CHANNEL_APP_SECRET",
    "CHANNEL_ID",
    "CHANNEL_GROUP_MEASUREMENT",
    "CHANNEL_GROUP_CONSTRUCTION",
    "CHANNEL_GROUP_GENERAL",
    "FOMS_BASE_URL",
    "is_configured",
    "get_target_group_id",
    "get_attachment_category_for_status",
    "format_order_message",
    "send_group_message",
]

# Token cache: {channel_id: (access_token, expires_at_unix_ts)}
_token_lock = Lock()
_token_cache: dict[str, tuple[str, float]] = {}

_STATUS_KR = {
    "RECEIVED": "접수",
    "MEASURE": "실측",
    "DRAWING": "도면",
    "CONFIRM": "컨펌",
    "PRODUCTION": "생산",
    "CONSTRUCTION": "시공",
    "CS": "CS",
    "COMPLETED": "완료",
    "AS": "AS",
}

_STATUS_TO_ATTACHMENT_CATEGORY = {
    "MEASURE": "measurement",
    "DRAWING": "drawing",
    "CONFIRM": "drawing",
    "CONSTRUCTION": "construction",
}


def is_configured() -> bool:
    """Return whether the required ChannelTalk env vars are configured."""
    return bool(CHANNEL_APP_SECRET and CHANNEL_ID)


def get_target_group_id(status: str) -> str:
    """Return the ChannelTalk group id for an order status."""
    mapping = {
        "RECEIVED": CHANNEL_GROUP_GENERAL,
        "MEASURE": CHANNEL_GROUP_MEASUREMENT,
        "DRAWING": CHANNEL_GROUP_MEASUREMENT,
        "CONFIRM": CHANNEL_GROUP_MEASUREMENT,
        "PRODUCTION": CHANNEL_GROUP_GENERAL,
        "CONSTRUCTION": CHANNEL_GROUP_CONSTRUCTION,
        "CS": CHANNEL_GROUP_GENERAL,
        "COMPLETED": CHANNEL_GROUP_GENERAL,
        "AS": CHANNEL_GROUP_GENERAL,
    }
    return mapping.get(status, CHANNEL_GROUP_GENERAL) or ""


def get_attachment_category_for_status(status: str) -> str:
    """Return the attachment category for an order status."""
    return _STATUS_TO_ATTACHMENT_CATEGORY.get(status, "")


def format_order_message(
    customer_name: str,
    status: str,
    address: str,
    order_id: int,
    schedule: dict[str, Any] | None = None,
    event_type: str = "update",
) -> str:
    """Build the legacy order message text."""
    event_label = {
        "new": "신규 접수",
        "update": "상태 변경",
        "save": "정보 저장",
    }.get(event_type, "업데이트")

    status_kr = _STATUS_KR.get(status, status)
    schedule = schedule or {}

    parts = [
        f"[{event_label}] {customer_name or '고객명 없음'}",
        f"상태: {status_kr}",
    ]

    if address:
        parts.append(f"주소: {address}")

    measure_date = (schedule.get("measurement") or {}).get("date", "")
    if measure_date:
        parts.append(f"실측일: {measure_date}")

    construction_date = (schedule.get("construction") or {}).get("date", "")
    if construction_date:
        parts.append(f"시공일: {construction_date}")

    try:
        from foms.services.channel_security import generate_wam_short_link_token

        parts.append(f"{FOMS_BASE_URL.rstrip('/')}/w/{generate_wam_short_link_token(order_id)}")
    except Exception:
        parts.append(f"{FOMS_BASE_URL}/erp/orders/{order_id}")

    return "\n".join(parts)


def _issue_token() -> tuple[str, float]:
    """Issue a ChannelTalk access token and return it with its local expiry timestamp."""
    payload = {
        "method": "issueToken",
        "params": {
            "secret": CHANNEL_APP_SECRET,
            "channelId": CHANNEL_ID,
        },
    }
    resp = requests.put(
        _NATIVE_FUNCTIONS_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    err = data.get("error") or {}
    if err.get("message"):
        raise RuntimeError(f"채널톡 issueToken 오류: {err['message']}")
    access_token = data["result"]["accessToken"]
    return access_token, time.time() + _TOKEN_TTL_SECONDS


def _get_access_token() -> str:
    """Return a cached valid access token or issue a new one."""
    if not is_configured():
        raise RuntimeError("CHANNEL_APP_SECRET, CHANNEL_ID 환경변수 미설정")

    with _token_lock:
        cached = _token_cache.get(CHANNEL_ID)
        if cached and time.time() < cached[1]:
            return cached[0]

        access_token, expires_at = _issue_token()
        _token_cache[CHANNEL_ID] = (access_token, expires_at)
        return access_token


def send_group_message(
    group_id: str,
    plain_text: str,
    blocks: list[dict[str, Any]] | None = None,
    files: list[dict[str, Any]] | None = None,
    bot_name: str = "FOMS",
    raise_on_error: bool = False,
) -> dict[str, Any]:
    """Send a message to a ChannelTalk group chat."""
    if not group_id:
        logger.warning("[채널톡] group_id 없음 - 전송 건너뜀")
        return {"success": False, "message_id": None}

    try:
        access_token = _get_access_token()
        payload = {
            "method": "writeGroupMessage",
            "params": {
                "channelId": CHANNEL_ID,
                "groupId": group_id,
                "rootMessageId": "",
                "broadcast": False,
                "dto": {
                    "plainText": plain_text,
                    "blocks": blocks or [],
                    "botName": bot_name,
                    "files": files or [],
                },
            },
        }
        resp = requests.put(
            _NATIVE_FUNCTIONS_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-access-token": access_token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        err = data.get("error") or {}
        if err.get("message"):
            logger.error("[채널톡] writeGroupMessage 오류: %s", err["message"])
            if raise_on_error:
                raise RuntimeError(err["message"])
            return {"success": False, "message_id": None}
        message_id = ((data.get("result") or {}).get("message") or {}).get("id")
        logger.info("[채널톡] 메시지 전송 완료 (group=%s, message_id=%s)", group_id, message_id)
        return {"success": True, "message_id": message_id}
    except Exception as exc:
        logger.error("[채널톡] 메시지 전송 실패 (group=%s): %s", group_id, exc)
        if raise_on_error:
            raise
        return {"success": False, "message_id": None}
