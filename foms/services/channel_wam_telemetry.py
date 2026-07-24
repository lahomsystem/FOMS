"""WAM telemetry event validation and logging helpers.

WAM-TELEMETRY-01: this ingest surface is validated strictly — exact canonical
keys, the existing 7-event enum, and per-field bounds — *before* anything is
logged. Only the validated, bounded projection is ever logged; the raw request
body, unknown keys, and nested values never reach the log, so a hostile client
cannot poison logs or drive log/memory DoS. No key aliases are accepted (the
client emits exactly the canonical schema). Recording is fail-open: a telemetry
failure must never surface as a page/endpoint failure.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from foms.services.channel_wam_view_models import WamRequestContext

# ``validate_wam_telemetry`` is a module-internal helper imported explicitly by
# the route; the public ``__all__`` surface (namespace-shim contract) is
# unchanged.
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

# Exact canonical wire schema (client telemetry.js ``send()`` emits exactly
# these keys). Aliases such as eventName / pageState / viewKey / section_key are
# deliberately NOT accepted.
_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "event_name",
        "view_key",
        "page_state",
        "section_count",
        "attachment_count",
        "latency_ms",
        "key",
    }
)
_STRING_KEYS: tuple[str, ...] = ("view_key", "page_state", "key")
_COUNT_KEYS: tuple[str, ...] = ("section_count", "attachment_count")
_MAX_STRING_LEN = 64
_MAX_COUNT = 1000
_MAX_LATENCY_MS = 120000


def _bounded_int(value: Any, upper: int) -> bool:
    """Return True when ``value`` is a non-bool int within ``0..upper`` inclusive.

    Args:
        value: Candidate value from the payload.
        upper: Inclusive upper bound.

    Returns:
        True when the value is an in-range integer (``bool`` is rejected because
        it is an ``int`` subclass), False otherwise.
    """
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper


def validate_wam_telemetry(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Strict-validate a WAM telemetry payload against the canonical schema.

    Args:
        payload: The parsed JSON body (any type; only a ``dict`` is valid).

    Returns:
        ``(record, None)`` where ``record`` is the normalized, bounded projection
        safe to log; or ``(None, error)`` with a short reason string when the
        payload is rejected (caller returns 422).
    """
    if not isinstance(payload, dict):
        return None, "payload must be a JSON object"
    if set(payload) - _ALLOWED_KEYS:
        return None, "unexpected keys"

    event_name = payload.get("event_name")
    if not isinstance(event_name, str) or event_name not in ALLOWED_EVENTS:
        return None, "invalid event_name"

    record: dict[str, Any] = {"event_name": event_name}

    for key in _STRING_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > _MAX_STRING_LEN:
            return None, f"invalid {key}"
        record[key] = value

    for key in _COUNT_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if not _bounded_int(value, _MAX_COUNT):
            return None, f"invalid {key}"
        record[key] = value

    latency_ms = payload.get("latency_ms")
    if latency_ms is not None:
        if not _bounded_int(latency_ms, _MAX_LATENCY_MS):
            return None, "invalid latency_ms"
        record["latency_ms"] = latency_ms

    return record, None


def record_wam_telemetry(context: WamRequestContext, record: dict[str, Any]) -> None:
    """Log the validated, bounded telemetry projection.

    Only the pre-validated ``record`` (canonical keys + bounded values) plus the
    scoped context identifiers are logged — never the raw request body, unknown
    keys, or nested values.

    Args:
        context: The verified WAM request scope (order / manager identifiers).
        record: The bounded projection returned by :func:`validate_wam_telemetry`.
    """
    event_payload = {
        **record,
        "order_id": context.order_id,
        "manager_id": context.manager_id,
        "mapped_foms_user_id": context.mapped_foms_user_id,
        "token_type": context.token_type,
        "source": context.source,
    }
    logger.info("wam_telemetry %s", json.dumps(event_payload, ensure_ascii=False, sort_keys=True))
