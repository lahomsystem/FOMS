"""WAM telemetry event validation and logging helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from foms.services.channel_wam_view_models import WamRequestContext

__all__ = [
    "ALLOWED_EVENTS",
    "record_wam_telemetry",
]

logger = logging.getLogger(__name__)

ALLOWED_EVENTS = {
    "wam_page_opened",
    "wam_bootstrap_succeeded",
    "wam_bootstrap_failed",
    "wam_section_opened",
    "wam_attachments_opened",
    "wam_attachment_clicked",
    "wam_timeline_opened",
}


def _safe_int(value: Any) -> int | None:
    """Coerce telemetry numeric fields to integers while preserving empty values as None."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def record_wam_telemetry(
    context: WamRequestContext,
    event_name: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Validate and log a WAM telemetry event payload."""
    if event_name not in ALLOWED_EVENTS:
        logger.warning("[WAMTelemetry] Ignored unknown event: %s", event_name)
        return False

    payload = payload or {}
    event_payload = {
        "event_name": event_name,
        "order_id": context.order_id,
        "manager_id": context.manager_id,
        "mapped_foms_user_id": context.mapped_foms_user_id,
        "token_type": context.token_type,
        "source": context.source,
        "section_key": payload.get("key") or payload.get("section_key"),
        "page_state": payload.get("page_state") or payload.get("pageState"),
        "view_key": payload.get("view_key") or payload.get("viewKey") or "order-detail",
        "latency_ms": _safe_int(payload.get("latency_ms")),
        "section_count": _safe_int(payload.get("section_count")),
        "attachment_count": _safe_int(payload.get("attachment_count")),
    }
    logger.info("wam_telemetry %s", json.dumps(event_payload, ensure_ascii=False, sort_keys=True))
    return True
