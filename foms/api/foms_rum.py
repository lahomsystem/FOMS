"""Structured RUM baseline ingest for Railway log aggregation (P0-01 KPI)."""

from __future__ import annotations

import json
import logging
from typing import Any

from flask import Blueprint, jsonify, request

from foms.services.rum_aggregate import record_metric as record_rum_metric

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

    # 부가: 일별 히스토그램 집계(추세 감시). Redis 부재/오류/비화이트리스트 metric 은
    # 조용히 skip 하며 응답·기존 동작에 영향을 주지 않는다(fail-open).
    try:
        record_rum_metric(payload.get("metric"), payload.get("value"))
    except Exception:  # pragma: no cover - 집계 실패가 수신 응답을 막지 않도록.
        pass

    return jsonify({"success": True}), 200
