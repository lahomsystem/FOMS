"""Nearby-order response builder for the legacy orders blueprint."""

from __future__ import annotations

import datetime

from flask import current_app, jsonify, request

from db import get_db
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.schedule_recommendations import (
    compute_construction_nearby_fallback_payload,
    compute_construction_nearby_success_payload,
    compute_nearby_success_payload,
    load_construction_nearby_valid_items,
    load_measurement_nearby_valid_items,
    resolve_nearby_start_coordinates,
)

#: 후보 종류. 기본은 시공(기존 계약 불변), 실측은 영업 전달 배정용이다.
NEARBY_KINDS = ("construction", "measurement")

#: 실측 후보는 건수가 많아 경로 계산에 반드시 타임아웃을 건다(설계서 §4.1).
MEASUREMENT_ROUTE_TIMEOUT_SEC = 3.0


def _kind_is_empty(payload: dict) -> bool:
    """Return True when all three nearby result lists are empty."""
    return not (
        payload.get("by_distance")
        or payload.get("by_date")
        or payload.get("by_combined")
    )


def nearby_orders_response():
    """Build the `/api/orders/nearby` response.

    Query params:
        address: 기준 주소(필수).
        kind: ``construction``(기본) | ``measurement``. 그 외 값은 400.
        exclude_id / date / lat / lng: 기존 계약과 동일.

    Returns:
        Flask JSON 응답. 성공 시 기존 키 + ``parcel_suggested``.
    """
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

    kind = (request.args.get("kind") or "construction").strip().lower()
    if kind not in NEARBY_KINDS:
        return (
            jsonify(
                {
                    "success": False,
                    "message": "지원하지 않는 후보 종류입니다.",
                    "error": "지원하지 않는 후보 종류입니다.",
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

    is_measurement = kind == "measurement"

    db = get_db()
    if is_measurement:
        valid_items = load_measurement_nearby_valid_items(db, ref_date, exclude_id)
    else:
        valid_items = load_construction_nearby_valid_items(db, ref_date, exclude_id)

    request_lat = request.args.get("lat", type=float)
    request_lng = request.args.get("lng", type=float)

    try:
        converter = FOMSAddressConverter()
        start_lat, start_lng = resolve_nearby_start_coordinates(
            db, converter, target_address, request_lat, request_lng, exclude_id
        )
        compute = (
            compute_nearby_success_payload
            if is_measurement
            else compute_construction_nearby_success_payload
        )
        payload = compute(
            valid_items=valid_items,
            converter=converter,
            start_lat=start_lat,
            start_lng=start_lng,
            ref_date=ref_date,
            log_warning=current_app.logger.warning,
            route_timeout_sec=(
                MEASUREMENT_ROUTE_TIMEOUT_SEC if is_measurement else None
            ),
        )
        payload["parcel_suggested"] = bool(is_measurement and _kind_is_empty(payload))
        return jsonify(payload)
    except Exception as error:
        current_app.logger.warning(
            "[NEARBY] 카카오 API 오류, fallback 사용: %s", error, exc_info=True
        )

    fallback = compute_construction_nearby_fallback_payload(valid_items, target_address)
    fallback["parcel_suggested"] = bool(is_measurement and _kind_is_empty(fallback))
    return jsonify(fallback)
