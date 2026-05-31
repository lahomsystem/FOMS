"""Structured RUM baseline ingest for Railway log aggregation (P0-01 KPI)."""

from __future__ import annotations

import json
import logging
from typing import Any

from flask import Blueprint, jsonify, request

foms_rum_bp = Blueprint("foms_rum", __name__)
_logger = logging.getLogger("foms.rum")


@foms_rum_bp.route("/api/foms/rum", methods=["POST"])
def ingest_rum_event() -> tuple[Any, int]:
    """Accept Web Vitals / navigation metrics via sendBeacon or fetch.

    Events are written as single-line JSON to stdout for Railway log parsing.

    Returns:
        JSON success envelope.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}

    record = {
        "event": "foms_rum",
        "metric": payload.get("metric"),
        "value": payload.get("value"),
        "path": payload.get("path") or request.path,
        "viewport": payload.get("viewport"),
        "mobile_v2": payload.get("mobile_v2"),
    }
    _logger.info(json.dumps(record, ensure_ascii=False))
    return jsonify({"success": True}), 200
