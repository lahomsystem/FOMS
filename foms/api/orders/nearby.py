"""Nearby-order response builder for the legacy orders blueprint."""

from __future__ import annotations

import datetime

from flask import current_app, jsonify, request

from db import get_db
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.schedule_recommendations import (
    compute_construction_nearby_fallback_payload,
    compute_construction_nearby_success_payload,
    load_construction_nearby_valid_items,
    resolve_nearby_start_coordinates,
)


def nearby_orders_response():
    """Build the `/api/orders/nearby` response."""
    target_address = request.args.get("address", "").strip()
    if not target_address:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "주소가 필요합니다.",
                    "error": "주소가 필요합니다.",
                }
            ),
            400,
        )

    exclude_id = request.args.get("exclude_id", type=int)
    try:
        from zoneinfo import ZoneInfo

        kst_tomorrow = (
            datetime.datetime.now(ZoneInfo("Asia/Seoul")) + datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
    except Exception:
        kst_tomorrow = (
            datetime.datetime.utcnow() + datetime.timedelta(hours=9, days=1)
        ).strftime("%Y-%m-%d")
    ref_date = request.args.get("date", kst_tomorrow)

    db = get_db()
    valid_items = load_construction_nearby_valid_items(db, ref_date, exclude_id)

    request_lat = request.args.get("lat", type=float)
    request_lng = request.args.get("lng", type=float)

    try:
        converter = FOMSAddressConverter()
        start_lat, start_lng = resolve_nearby_start_coordinates(
            db, converter, target_address, request_lat, request_lng, exclude_id
        )
        payload = compute_construction_nearby_success_payload(
            valid_items=valid_items,
            converter=converter,
            start_lat=start_lat,
            start_lng=start_lng,
            ref_date=ref_date,
            log_warning=current_app.logger.warning,
            route_timeout_sec=None,
        )
        return jsonify(payload)
    except Exception as error:
        current_app.logger.warning(
            "[NEARBY] 카카오 API 오류, fallback 사용: %s", error, exc_info=True
        )

    fallback = compute_construction_nearby_fallback_payload(valid_items, target_address)
    return jsonify(fallback)
