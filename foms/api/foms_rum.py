"""Structured RUM baseline ingest for Railway log aggregation (P0-01 KPI).

RUM-INGEST-01: this is an **unauthenticated** telemetry surface, so the anonymous
POST is validated strictly (exact keys + per-field bounds) before anything is
logged or aggregated. Only the validated, bounded projection is ever logged —
never the raw request body — and per-client rate limiting is applied via the
canonical ``request.remote_addr`` (PROXY-01), never a raw ``X-Forwarded-For``.
Body size is capped at 2 KiB by REQUEST-LIMIT-01 (telemetry cap) before the
handler runs.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from flask import Blueprint, g, jsonify, request

from foms.services.rum_aggregate import ALLOWED_METRICS, build_rum_report
from foms.services.rum_aggregate import record_metric as record_rum_metric

foms_rum_bp = Blueprint("foms_rum", __name__)
_logger = logging.getLogger("foms.rum")

# Anonymous ingest contract (rum-baseline.js sends exactly these keys).
_ALLOWED_KEYS: frozenset[str] = frozenset({"metric", "value", "path", "viewport", "mobile_v2"})
_MAX_VALUE_MS: float = 120000.0
_MAX_PATH_LEN: int = 500
_MAX_VIEWPORT_DIM: int = 10000
_MAX_VIEWPORT_LEN: int = 32

# Admin report ``days`` bound (aggregation TTL is 35 days).
_DEFAULT_DAYS: int = 7
_MIN_DAYS: int = 1
_MAX_DAYS: int = 35


def _valid_relative_path(path: str) -> bool:
    """Return True if ``path`` is a site-root-relative URL path.

    Rejects absolute/protocol-relative URLs, query strings, fragments, control
    characters (log-injection defense), and anything over ``_MAX_PATH_LEN``.

    Args:
        path: Candidate path from the client payload.

    Returns:
        True when the path is safe to log/store, False otherwise.
    """
    if not isinstance(path, str) or not path or len(path) > _MAX_PATH_LEN:
        return False
    if not path.startswith("/") or path.startswith("//"):
        return False
    if "?" in path or "#" in path:
        return False
    return all(ord(ch) >= 0x20 for ch in path)


def _valid_viewport(viewport: str) -> bool:
    """Return True if ``viewport`` is ``"WxH"`` with each dim an int in 1..10000.

    Args:
        viewport: Candidate viewport string (e.g. ``"1920x1080"``).

    Returns:
        True when both dimensions parse and fall within bounds, False otherwise.
    """
    if not isinstance(viewport, str) or len(viewport) > _MAX_VIEWPORT_LEN:
        return False
    parts = viewport.split("x")
    if len(parts) != 2:
        return False
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return False
    return 1 <= width <= _MAX_VIEWPORT_DIM and 1 <= height <= _MAX_VIEWPORT_DIM


def _validate_rum_payload(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Strict-validate an anonymous RUM payload.

    Args:
        payload: The parsed JSON body (any type; only a ``dict`` is valid).

    Returns:
        ``(record, None)`` where ``record`` is the normalized, bounded projection
        safe to log/aggregate; or ``(None, error)`` with a short reason string
        when the payload is rejected (caller returns 400).
    """
    if not isinstance(payload, dict):
        return None, "payload must be a JSON object"
    if set(payload) - _ALLOWED_KEYS:
        return None, "unexpected keys"

    metric = payload.get("metric")
    if not isinstance(metric, str) or metric not in ALLOWED_METRICS:
        return None, "invalid metric"

    value = payload.get("value")
    # bool is an int subclass but is not a valid metric value.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "value must be a number"
    fvalue = float(value)
    if not math.isfinite(fvalue) or fvalue < 0 or fvalue > _MAX_VALUE_MS:
        return None, "value out of range"

    path = payload.get("path")
    if path is None:
        path = request.path
    elif not _valid_relative_path(path):
        return None, "invalid path"

    viewport = payload.get("viewport")
    if viewport is not None and not _valid_viewport(viewport):
        return None, "invalid viewport"

    mobile_v2 = payload.get("mobile_v2")
    if mobile_v2 is not None and not isinstance(mobile_v2, bool):
        return None, "invalid mobile_v2"

    return {
        "metric": metric,
        "value": fvalue,
        "path": path,
        "viewport": viewport,
        "mobile_v2": mobile_v2,
    }, None


def _parse_report_days(raw: str | None) -> tuple[int, str | None]:
    """Parse and bound the report ``days`` query param to ``_MIN_DAYS.._MAX_DAYS``.

    Args:
        raw: The raw ``days`` query value (or None when absent).

    Returns:
        ``(days, None)`` on success (absent → ``_DEFAULT_DAYS``); ``(0, error)``
        when non-integer or out of the 1..35 bound (caller returns 400).
    """
    if raw is None:
        return _DEFAULT_DAYS, None
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return 0, "days must be an integer"
    if days < _MIN_DAYS or days > _MAX_DAYS:
        return 0, f"days out of range ({_MIN_DAYS}..{_MAX_DAYS})"
    return days, None


@foms_rum_bp.route("/api/foms/rum", methods=["POST"])
def ingest_rum_event() -> tuple[Any, int]:
    """Accept Web Vitals / navigation metrics via sendBeacon or fetch.

    The anonymous payload is strictly validated; only the validated, bounded
    projection is written as single-line JSON to stdout for Railway log parsing
    (never the raw body). Rate limiting is bound to the canonical client IP by
    ``foms.platform.realtime`` (PROXY-01). Body size is capped by REQUEST-LIMIT-01.

    Returns:
        200 JSON success envelope, or 400 when the payload fails validation.
    """
    record, error = _validate_rum_payload(request.get_json(silent=True))
    if error is not None:
        return jsonify({"success": False, "error": error}), 400

    _logger.info(json.dumps({"event": "foms_rum", **record}, ensure_ascii=False))

    # 일별 히스토그램 집계(추세 감시). record_metric 은 Redis 부재/오류를 내부에서
    # warning 로그(raw payload 미포함) + fail-open(집계만 skip)으로 처리하므로,
    # 여기서 예외를 삼키지(silent except) 않는다.
    record_rum_metric(record["metric"], record["value"])

    return jsonify({"success": True}), 200


@foms_rum_bp.route("/api/foms/rum/report", methods=["GET"])
def rum_report() -> tuple[Any, int]:
    """admin 전용 RUM 추세/회귀 리포트(JSON).

    운영 Redis 는 앱 내부에서만 접근되므로 이 엔드포인트가 rum-daily 워크플로의
    **유일한 외부 조회로**다. JSON 엔드포인트이므로 미인증은 **401**, role != ADMIN 은
    **403**(로그인 리다이렉트 대신). Redis 부재 시 503(집계 조회 불가).

    Query:
        days: 조회 일수(기본 7). 정수가 아니거나 1..35 밖이면 400.

    Returns:
        200 ``{"success": True, "data": {days, metrics[], regressed, warnings}}``.
    """
    user = getattr(g, "current_user", None)
    if user is None:
        return jsonify({"success": False, "error": "unauthorized"}), 401
    if getattr(user, "role", None) != "ADMIN":
        return jsonify({"success": False, "error": "forbidden"}), 403

    days, days_error = _parse_report_days(request.args.get("days"))
    if days_error is not None:
        return jsonify({"success": False, "error": days_error}), 400

    from foms.services.common.dashboard_cache import get_dashboard_redis

    client = get_dashboard_redis()
    if client is None:
        return jsonify({"success": False, "error": "redis_unavailable"}), 503

    report = build_rum_report(client, days)
    return jsonify({"success": True, "data": report}), 200
