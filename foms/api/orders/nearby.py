"""Nearby-order response builder for the legacy orders blueprint."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import math

from flask import current_app, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import load_only, selectinload

from db import get_db
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.erp_order_flags import is_erp_order_record
from models import Order, OrderScheduleDate

_SEARCH_RADII_KM = [1.0, 3.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
_MAX_RESULTS = 5
_GEOCODE_WORKERS = 10


def _get_order_schedule_date(order, ref_date: str | None = None):
    """Return the earliest valid construction date for nearby-order ranking."""
    if not order:
        return None

    def _valid(date_value):
        value = str(date_value).strip() if date_value else ""
        return value if value and (not ref_date or value >= ref_date) else None

    structured_data = getattr(order, "structured_data", None)
    if is_erp_order_record(order) and isinstance(structured_data, dict):
        construction_date = (
            ((structured_data.get("schedule") or {}).get("construction") or {}).get("date")
        )
        if valid_date := _valid(construction_date):
            return valid_date

    if valid_date := _valid(getattr(order, "scheduled_date", None)):
        return valid_date

    schedule_dates = getattr(order, "schedule_dates", None)
    if schedule_dates:
        dates = sorted(
            row.date
            for row in schedule_dates
            if row.kind == "construction" and _valid(row.date)
        )
        if dates:
            return dates[0]
    return None


def _get_order_display_address(order):
    """Return the canonical nearby-order address for display and geocoding."""
    if not order:
        return ""
    structured_data = getattr(order, "structured_data", None)
    if isinstance(structured_data, dict):
        site = structured_data.get("site") or {}
        address_full = site.get("address_full")
        address_main = site.get("address_main")
        address_detail = site.get("address_detail")
        if address_full:
            return str(address_full).strip()
        if address_main:
            detail = (address_detail or "").strip()
            return f"{address_main.strip()} {detail}".strip() if detail else address_main.strip()
    return (getattr(order, "address", None) or "").strip()


def _get_order_display_customer_name(order):
    """Return the canonical nearby-order customer name."""
    if not order:
        return ""
    structured_data = getattr(order, "structured_data", None)
    if isinstance(structured_data, dict):
        name = ((structured_data.get("parties") or {}).get("customer") or {}).get("name")
        if name and str(name).strip():
            return str(name).strip()
    return (getattr(order, "customer_name", None) or "").strip()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the straight-line distance between two coordinates in kilometers."""
    radius_km = 6371.0
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a_term = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(delta_lng / 2) ** 2
    )
    return radius_km * 2 * math.asin(math.sqrt(a_term))


def _build_candidate_item(order, ref_date: str | None = None) -> dict:
    """Convert an order ORM object into the nearby-order payload candidate."""
    item = {
        "id": order.id,
        "customer_name": _get_order_display_customer_name(order),
        "address": _get_order_display_address(order),
        "date": _get_order_schedule_date(order, ref_date),
        "type": "시공",
    }

    db_lat = getattr(order, "lat", None)
    db_lng = getattr(order, "lng", None)
    db_geocode_status = getattr(order, "geocode_status", None)
    if db_lat and db_lng and db_geocode_status == "success":
        item["_db_lat"] = float(db_lat)
        item["_db_lng"] = float(db_lng)
    return item


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
    as_statuses = ("AS_RECEIVED", "AS_COMPLETED", "DELETED")

    query = (
        db.query(Order)
        .options(
            load_only(
                Order.id,
                Order.address,
                Order.status,
                Order.shipping_scheduled_date,
                Order.scheduled_date,
                Order.is_erp_order,
                Order.structured_data,
                Order.customer_name,
                Order.lat,
                Order.lng,
                Order.geocode_status,
            ),
            selectinload(Order.schedule_dates),
        )
        .outerjoin(
            OrderScheduleDate,
            and_(
                Order.id == OrderScheduleDate.order_id,
                OrderScheduleDate.kind == "construction",
            ),
        )
        .filter(
            ~Order.status.in_(as_statuses),
            or_(
                Order.scheduled_date >= ref_date,
                and_(
                    OrderScheduleDate.id.isnot(None),
                    OrderScheduleDate.date >= ref_date,
                ),
                and_(
                    Order.is_erp_order.is_(True),
                    func.jsonb_extract_path_text(
                        Order.structured_data, "schedule", "construction", "date"
                    )
                    >= ref_date,
                ),
            ),
        )
        .distinct()
    )

    if exclude_id:
        query = query.filter(Order.id != exclude_id)

    candidates = query.order_by(Order.id.desc()).limit(2500).all()

    valid_items = []
    for order in candidates:
        order_address = _get_order_display_address(order)
        if not order_address:
            continue
        if not _get_order_schedule_date(order, ref_date):
            continue
        valid_items.append(_build_candidate_item(order, ref_date))

    request_lat = request.args.get("lat", type=float)
    request_lng = request.args.get("lng", type=float)
    if not (request_lat and request_lng) and exclude_id:
        source_order = (
            db.query(Order)
            .options(load_only(Order.id, Order.lat, Order.lng, Order.geocode_status))
            .filter(Order.id == exclude_id)
            .first()
        )
        if source_order and source_order.lat and source_order.lng:
            request_lat = float(source_order.lat)
            request_lng = float(source_order.lng)

    try:
        converter = FOMSAddressConverter()

        if request_lat and request_lng:
            start_lat, start_lng = request_lat, request_lng
        else:
            start_lat, start_lng, _, _ = converter.analyze_address(target_address)

        if not start_lat or not start_lng:
            raise ValueError("기준 주소 좌표 변환 실패")

        def geocode_item(item: dict):
            if item.get("_db_lat") and item.get("_db_lng"):
                return item, item["_db_lat"], item["_db_lng"]

            address = item["address"]
            lat, lng, _, _ = converter.analyze_address(address)
            has_region_prefix = address.startswith(
                (
                    "서울",
                    "경기",
                    "인천",
                    "부산",
                    "대구",
                    "광주",
                    "대전",
                    "울산",
                    "세종",
                    "강원",
                    "충북",
                    "충남",
                    "전북",
                    "전남",
                    "경북",
                    "경남",
                    "제주",
                )
            )
            if not lat and not has_region_prefix:
                lat, lng, _, _ = converter.analyze_address(f"경기 {address}")
            return item, lat, lng

        geo_results: list[tuple[dict, float | None, float | None]] = []
        with ThreadPoolExecutor(
            max_workers=min(_GEOCODE_WORKERS, len(valid_items) or 1)
        ) as executor:
            futures = {executor.submit(geocode_item, item): item for item in valid_items}
            for future in as_completed(futures):
                try:
                    geo_results.append(future.result())
                except Exception as geo_error:
                    current_app.logger.warning("[NEARBY] 좌표 변환 실패: %s", geo_error)
                    geo_results.append((futures[future], None, None))

        with_distance = []
        for item, lat, lng in geo_results:
            if lat and lng:
                item["_dist_km"] = _haversine_km(start_lat, start_lng, lat, lng)
                item["_lat"] = lat
                item["_lng"] = lng
                with_distance.append(item)

        max_radius = _SEARCH_RADII_KM[-1]
        within_max = [item for item in with_distance if item["_dist_km"] <= max_radius]
        pool = within_max if within_max else with_distance
        used_radius = max_radius

        by_distance = sorted(
            pool, key=lambda item: (item["_dist_km"], item.get("date") or "9999-99-99")
        )[:_MAX_RESULTS]

        def _dedup_by_date(items: list[dict]) -> list[dict]:
            by_date_dist = sorted(
                items,
                key=lambda item: (item.get("date") or "9999-99-99", item["_dist_km"]),
            )
            seen_dates: set[str] = set()
            result = []
            for item in by_date_dist:
                date_key = item.get("date") or ""
                if date_key and date_key not in seen_dates:
                    seen_dates.add(date_key)
                    result.append(item)
            return result

        by_date = _dedup_by_date(pool)[:_MAX_RESULTS]

        try:
            ref_obj = datetime.date.fromisoformat(ref_date)
        except Exception:
            ref_obj = datetime.date.today()

        if pool:
            max_dist = max(item["_dist_km"] for item in pool) or 1.0

            def _safe_days(item: dict) -> float | None:
                try:
                    return max(
                        0,
                        (datetime.date.fromisoformat(item["date"]) - ref_obj).days,
                    )
                except (ValueError, TypeError, KeyError):
                    return None

            day_values_raw = [_safe_days(item) for item in pool]
            valid_days = [value for value in day_values_raw if value is not None]
            max_days = max(valid_days) if valid_days else 1.0

            def _norm_days(value) -> float:
                return (value / max_days) if (value is not None and max_days > 0) else 1.0

            scored = sorted(
                zip(pool, day_values_raw),
                key=lambda row: 0.5 * (row[0]["_dist_km"] / max_dist)
                + 0.5 * _norm_days(row[1]),
            )
            by_combined = [item for item, _ in scored[:_MAX_RESULTS]]
        else:
            by_distance = []
            by_date = []
            by_combined = []

        def route_item(item: dict):
            route_info = converter.calculate_route(
                start_lat, start_lng, item["_lat"], item["_lng"]
            )
            if route_info.get("status") == "success":
                item["distance_km"] = route_info["distance_km"]
                item["duration_min"] = route_info["duration_min"]
                item["score_text"] = (
                    f"{route_info['distance_km']}km ({route_info['duration_min']}분)"
                )
            else:
                item["score_text"] = f"약 {item['_dist_km']:.1f}km"
            item["dist_km"] = round(item["_dist_km"], 2)
            item.pop("_dist_km", None)
            item["lat"] = item.pop("_lat", None)
            item["lng"] = item.pop("_lng", None)
            return item

        seen_route_ids: set[int] = set()
        route_targets: list[dict] = []
        for item in by_distance + by_date + by_combined:
            if item["id"] not in seen_route_ids:
                seen_route_ids.add(item["id"])
                route_targets.append(item)

        with ThreadPoolExecutor(max_workers=min(len(route_targets) or 1, 15)) as executor:
            futures = [executor.submit(route_item, item) for item in route_targets]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as route_error:
                    current_app.logger.warning("[NEARBY] 경로 계산 실패: %s", route_error)

        def _routed(items: list[dict]) -> list[dict]:
            return [item for item in items if "dist_km" in item]

        return jsonify(
            {
                "success": True,
                "by_distance": _routed(by_distance),
                "by_date": _routed(by_date),
                "by_combined": _routed(by_combined),
                "search_radius_km": used_radius,
                "ref_lat": start_lat,
                "ref_lng": start_lng,
            }
        )
    except Exception as error:
        current_app.logger.warning(
            "[NEARBY] 카카오 API 오류, fallback 사용: %s", error, exc_info=True
        )

    target_tokens = set(target_address.split())
    for item in valid_items:
        order_tokens = set(item["address"].split())
        item["_score"] = len(target_tokens & order_tokens)
        item["score_text"] = ""

    valid_items.sort(key=lambda item: (-item.get("_score", 0), item.get("date") or "9999-99-99"))
    fallback_results = valid_items[:_MAX_RESULTS]
    for item in fallback_results:
        item.pop("_score", None)

    return jsonify(
        {
            "success": True,
            "by_distance": fallback_results,
            "by_date": sorted(
                fallback_results, key=lambda item: item.get("date") or "9999-99-99"
            ),
            "by_combined": fallback_results,
            "search_radius_km": None,
        }
    )
