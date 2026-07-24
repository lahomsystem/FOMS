"""Structured RUM baseline ingest for Railway log aggregation (P0-01 KPI)."""

from __future__ import annotations

import json
import logging
from typing import Any

from flask import Blueprint, g, jsonify, request

from foms.services.rum_aggregate import build_rum_report
from foms.services.rum_aggregate import record_metric as record_rum_metric
from foms.web.auth import login_required

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
        pass  # failopen: intentional: RUM 집계 fail-open (Redis 부재/오류/비화이트리스트 metric)

    return jsonify({"success": True}), 200


@foms_rum_bp.route("/api/foms/rum/report", methods=["GET"])
@login_required
def rum_report() -> tuple[Any, int]:
    """admin 전용 RUM 추세/회귀 리포트(JSON).

    운영 Redis 는 앱 내부에서만 접근되므로 이 엔드포인트가 rum-daily 워크플로의
    **유일한 외부 조회로**다. ``login_required`` 로 비인증은 로그인 리다이렉트,
    role != ADMIN 은 403. Redis 부재 시 503(집계 조회 불가).

    Query:
        days: 조회 일수(기본 7, 파싱 실패 시 7).

    Returns:
        200 ``{"success": True, "data": {days, metrics[], regressed, warnings}}``.
    """
    user = getattr(g, "current_user", None)
    if user is None or getattr(user, "role", None) != "ADMIN":
        return jsonify({"success": False, "error": "forbidden"}), 403

    try:
        days = int(request.args.get("days", 7))
    except (TypeError, ValueError):
        days = 7

    from foms.services.common.dashboard_cache import get_dashboard_redis

    client = get_dashboard_redis()
    if client is None:
        return jsonify({"success": False, "error": "redis_unavailable"}), 503

    report = build_rum_report(client, days)
    return jsonify({"success": True, "data": report}), 200
