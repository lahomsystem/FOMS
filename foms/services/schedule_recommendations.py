"""Shared schedule recommendation helpers (construction nearby + shipment AS batch).

Pure/domain logic for ranking, geocoding pools, and route scoring lives here so
`/api/orders/nearby` and shipment batch endpoints share one implementation.

Display addresses use `foms.services.geocode_helpers.get_order_display_address` (spec §2.7).
"""

from __future__ import annotations

import datetime
import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, load_only, selectinload

from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.geocode_helpers import get_order_display_address
from foms.services.erp_order_flags import is_erp_order_record
from models import Order, OrderScheduleDate

SEARCH_RADII_KM = [1.0, 3.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
NEARBY_MAX_RESULTS = 5
GEOCODE_WORKERS = 10

_AS_NEARBY_EXCLUDED_STATUSES = ("AS_RECEIVED", "AS_COMPLETED", "DELETED")

_LOGGER = logging.getLogger(__name__)


def get_order_schedule_date(order, ref_date: str | None = None):
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


def get_order_display_customer_name(order) -> str:
    """Return the canonical nearby-order customer name."""
    if not order:
        return ""
    structured_data = getattr(order, "structured_data", None)
    if isinstance(structured_data, dict):
        name = ((structured_data.get("parties") or {}).get("customer") or {}).get("name")
        if name and str(name).strip():
            return str(name).strip()
    return (getattr(order, "customer_name", None) or "").strip()


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
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


def build_construction_candidate_item(order, ref_date: str | None = None) -> dict:
    """Convert an order ORM object into the nearby-order payload candidate."""
    item = {
        "id": order.id,
        "customer_name": get_order_display_customer_name(order),
        "address": get_order_display_address(order),
        "date": get_order_schedule_date(order, ref_date),
        "type": "시공",
    }

    db_lat = getattr(order, "lat", None)
    db_lng = getattr(order, "lng", None)
    db_geocode_status = getattr(order, "geocode_status", None)
    if db_lat and db_lng and db_geocode_status == "success":
        item["_db_lat"] = float(db_lat)
        item["_db_lng"] = float(db_lng)
    return item


def load_construction_nearby_valid_items(
    db: Session, ref_date: str, exclude_id: int | None
) -> list[dict]:
    """Load construction-schedule orders and return display items with dates/addresses."""
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
            ~Order.status.in_(_AS_NEARBY_EXCLUDED_STATUSES),
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

    valid_items: list[dict] = []
    for order in candidates:
        order_address = get_order_display_address(order)
        if not order_address:
            continue
        if not get_order_schedule_date(order, ref_date):
            continue
        valid_items.append(build_construction_candidate_item(order, ref_date))
    return valid_items


def resolve_nearby_start_coordinates(
    db: Session,
    converter: FOMSAddressConverter,
    target_address: str,
    request_lat: float | None,
    request_lng: float | None,
    exclude_id: int | None,
) -> tuple[float, float]:
    """Resolve start lat/lng for nearby search; raises ValueError if impossible."""
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

    if request_lat and request_lng:
        return request_lat, request_lng

    start_lat, start_lng, _, _ = converter.analyze_address(target_address)
    if not start_lat or not start_lng:
        raise ValueError("기준 주소 좌표 변환 실패")
    return start_lat, start_lng


def _geocode_region_prefixes() -> tuple[str, ...]:
    return (
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


def compute_construction_nearby_success_payload(
    *,
    valid_items: list[dict],
    converter: FOMSAddressConverter,
    start_lat: float,
    start_lng: float,
    ref_date: str,
    log_warning: Callable[..., None] | None = None,
    route_timeout_sec: float | None = None,
) -> dict[str, Any]:
    """Geocode, rank, and route-score construction candidates (legacy nearby contract)."""
    warn = log_warning or _LOGGER.warning

    def geocode_item(item: dict):
        if item.get("_db_lat") and item.get("_db_lng"):
            return item, item["_db_lat"], item["_db_lng"]

        address = item["address"]
        lat, lng, _, _ = converter.analyze_address(address)
        has_region_prefix = address.startswith(_geocode_region_prefixes())
        if not lat and not has_region_prefix:
            lat, lng, _, _ = converter.analyze_address(f"경기 {address}")
        return item, lat, lng

    geo_results: list[tuple[dict, float | None, float | None]] = []
    with ThreadPoolExecutor(
        max_workers=min(GEOCODE_WORKERS, len(valid_items) or 1)
    ) as executor:
        futures = {executor.submit(geocode_item, item): item for item in valid_items}
        for future in as_completed(futures):
            try:
                geo_results.append(future.result())
            except Exception as geo_error:
                warn("[NEARBY] 좌표 변환 실패: %s", geo_error)
                geo_results.append((futures[future], None, None))

    with_distance = []
    for item, lat, lng in geo_results:
        if lat and lng:
            item["_dist_km"] = haversine_km(start_lat, start_lng, lat, lng)
            item["_lat"] = lat
            item["_lng"] = lng
            with_distance.append(item)

    max_radius = SEARCH_RADII_KM[-1]
    within_max = [item for item in with_distance if item["_dist_km"] <= max_radius]
    pool = within_max if within_max else with_distance
    used_radius = max_radius

    by_distance = sorted(
        pool, key=lambda item: (item["_dist_km"], item.get("date") or "9999-99-99")
    )[:NEARBY_MAX_RESULTS]

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

    by_date = _dedup_by_date(pool)[:NEARBY_MAX_RESULTS]

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
        by_combined = [item for item, _ in scored[:NEARBY_MAX_RESULTS]]
    else:
        by_distance = []
        by_date = []
        by_combined = []

    def route_item(item: dict):
        route_info = converter.calculate_route(
            start_lat, start_lng, item["_lat"], item["_lng"], timeout=route_timeout_sec
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
                warn("[NEARBY] 경로 계산 실패: %s", route_error)

    def _routed(items: list[dict]) -> list[dict]:
        return [item for item in items if "dist_km" in item]

    return {
        "success": True,
        "by_distance": _routed(by_distance),
        "by_date": _routed(by_date),
        "by_combined": _routed(by_combined),
        "search_radius_km": used_radius,
        "ref_lat": start_lat,
        "ref_lng": start_lng,
    }


def compute_construction_nearby_fallback_payload(
    valid_items: list[dict], target_address: str
) -> dict[str, Any]:
    """Token-similarity fallback when Kakao path fails (legacy nearby contract)."""
    target_tokens = set(target_address.split())
    for item in valid_items:
        order_tokens = set(item["address"].split())
        item["_score"] = len(target_tokens & order_tokens)
        item["score_text"] = ""

    valid_items.sort(key=lambda item: (-item.get("_score", 0), item.get("date") or "9999-99-99"))
    fallback_results = valid_items[:NEARBY_MAX_RESULTS]
    for item in fallback_results:
        item.pop("_score", None)

    return {
        "success": True,
        "by_distance": fallback_results,
        "by_date": sorted(
            fallback_results, key=lambda item: item.get("date") or "9999-99-99"
        ),
        "by_combined": fallback_results,
        "search_radius_km": None,
    }


def _geocode_address_for_batch(
    address: str, converter: FOMSAddressConverter
) -> tuple[float | None, float | None]:
    """Resolve lat/lng for one address (경기 prefix retry matches nearby)."""
    if not (address or "").strip():
        return None, None
    lat, lng, _, _ = converter.analyze_address(address)
    if not lat and not address.startswith(_geocode_region_prefixes()):
        lat, lng, _, _ = converter.analyze_address(f"경기 {address}")
    return lat, lng


def _batch_geocode_unique_addresses(
    addresses: set[str],
    converter: FOMSAddressConverter,
    warn: Callable[..., None],
) -> dict[str, tuple[float | None, float | None]]:
    """Parallel geocode for unique non-empty addresses."""
    unique = sorted({a.strip() for a in addresses if (a or "").strip()})
    out: dict[str, tuple[float | None, float | None]] = {}

    def one(addr: str) -> None:
        try:
            out[addr] = _geocode_address_for_batch(addr, converter)
        except Exception as exc:
            warn("[AS-REC] geocode 실패 (%s): %s", addr, exc)
            out[addr] = (None, None)

    with ThreadPoolExecutor(max_workers=min(GEOCODE_WORKERS, len(unique) or 1)) as ex:
        futs = [ex.submit(one, a) for a in unique]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as exc:
                warn("[AS-REC] geocode 작업 오류: %s", exc)
    return out


def _entity_lat_lng(
    entity: dict[str, Any], geo_map: dict[str, tuple[float | None, float | None]]
) -> tuple[float | None, float | None]:
    """Prefer DB cache on entity, else geo_map by address."""
    clat = entity.get("cached_lat")
    clng = entity.get("cached_lng")
    if clat is not None and clng is not None:
        try:
            return float(clat), float(clng)
        except (TypeError, ValueError):
            pass
    addr = (entity.get("address") or "").strip()
    return geo_map.get(addr, (None, None))


def _token_overlap_score(addr_a: str, addr_b: str) -> int:
    tokens_a = set((addr_a or "").split())
    tokens_b = set((addr_b or "").split())
    return len(tokens_a & tokens_b)


def recommend_nearby_schedules_for_targets(
    *,
    converter: FOMSAddressConverter,
    targets: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    per_target_limit: int = 2,
    duration_limit_min: int = 30,
    route_candidates_per_target: int = 10,
    max_targets_per_request: int = 5,
    max_route_calls_per_request: int = 50,
    route_timeout_sec: float = 3.0,
    reference_date: str | None = None,
    include_workers: bool = False,
    route_worker_concurrency: int = 5,
    log_warning: Callable[..., None] | None = None,
    route_provider: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Batch AS recommendations for shipment dashboard targets (spec §2.2–2.4)."""
    warn = log_warning or _LOGGER.warning
    warnings: list[str] = []
    partial = False
    active = targets[:max_targets_per_request]
    if len(targets) > max_targets_per_request:
        warnings.append(
            f"출고 기준 건이 {max_targets_per_request}건을 초과하여 앞선 {max_targets_per_request}건만 처리했습니다."
        )

    addr_set: set[str] = set()
    for row in active:
        if (row.get("address") or "").strip():
            addr_set.add(row["address"].strip())
    for row in candidates:
        if (row.get("address") or "").strip():
            addr_set.add(row["address"].strip())

    geo_map = _batch_geocode_unique_addresses(addr_set, converter, warn)

    jobs: list[tuple[int, dict[str, Any], float, float, float, float, float]] = []
    budget = max_route_calls_per_request
    ranked_by_target: dict[int, list[tuple[float, dict[str, Any], float, float]]] = {}

    for t_idx, tgt in enumerate(active):
        slat, slng = _entity_lat_lng(tgt, geo_map)
        if slat is None or slng is None:
            ranked_by_target[t_idx] = []
            continue
        ranked: list[tuple[float, dict[str, Any], float, float]] = []
        for cand in candidates:
            if (cand.get("current_visit_date") or "").strip():
                continue
            caddr = (cand.get("address") or "").strip()
            if not caddr:
                continue
            elat, elng = _entity_lat_lng(cand, geo_map)
            if elat is None or elng is None:
                continue
            skm = haversine_km(slat, slng, elat, elng)
            ranked.append((skm, cand, elat, elng))
        ranked.sort(key=lambda row: row[0])
        ranked_by_target[t_idx] = ranked
        for skm, cand, elat, elng in ranked[:route_candidates_per_target]:
            if budget <= 0:
                partial = True
                break
            jobs.append((t_idx, cand, slat, slng, elat, elng, skm))
            budget -= 1
        if budget <= 0 and t_idx < len(active) - 1:
            partial = True

    route_by_pair: dict[tuple[int, int], dict[str, Any]] = {}

    provider = route_provider or converter.calculate_route

    def run_route(
        job: tuple[int, dict[str, Any], float, float, float, float, float],
    ) -> None:
        t_idx, cand, slat, slng, elat, elng, skm = job
        oid = int(cand["order_id"])
        try:
            info = provider(
                slat, slng, elat, elng, timeout=route_timeout_sec
            )
        except Exception as exc:
            warn("[AS-REC] 경로 계산 예외: %s", exc)
            info = {"status": "error", "message": str(exc)}
        route_by_pair[(t_idx, oid)] = {"straight_km": skm, "route": info}

    if jobs:
        workers = min(route_worker_concurrency, len(jobs))
        with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
            futs = [executor.submit(run_route, j) for j in jobs]
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception as exc:
                    warn("[AS-REC] 경로 워커 실패: %s", exc)

    out_targets: list[dict[str, Any]] = []

    for t_idx, tgt in enumerate(active):
        tgt_address = (tgt.get("address") or "").strip()
        slat, slng = _entity_lat_lng(tgt, geo_map)
        base = {
            "order_id": int(tgt["order_id"]),
            "customer_name": tgt.get("customer_name") or "",
            "address": tgt_address,
            "target_date": tgt.get("target_date") or "",
            "workers": (list(tgt.get("workers") or []) if include_workers else []),
            "recommendations": [],
            "linked_as_schedules": [],
            "message": "",
        }
        if slat is None or slng is None:
            base["message"] = "출고 주소 좌표를 확인할 수 없어 추천하지 않았습니다."
            out_targets.append(base)
            continue
        base["lat"] = float(slat)
        base["lng"] = float(slng)

        ranked = ranked_by_target.get(t_idx) or []
        raw_recs: list[dict[str, Any]] = []
        for skm, cand, elat, elng in ranked:
            oid = int(cand["order_id"])
            payload = route_by_pair.get((t_idx, oid))
            if not payload:
                continue
            info = payload["route"]
            cur_visit = (cand.get("current_visit_date") or "").strip()
            if info.get("status") == "success":
                dur = int(info.get("duration_min") or 0)
                dist = float(info.get("distance_km") or 0)
                if dur > duration_limit_min:
                    continue
                raw_recs.append(
                    {
                        "as_order_id": oid,
                        "customer_name": cand.get("customer_name") or "",
                        "address": (cand.get("address") or "").strip(),
                        "current_visit_date": cur_visit,
                        "lat": float(elat),
                        "lng": float(elng),
                        "route_distance_km": dist,
                        "route_duration_min": dur,
                        "straight_distance_km": round(payload["straight_km"], 2),
                        "score_text": f"실제 {dist}km / {dur}분, 출고일에 함께 배정 가능",
                        "as_info_id": cand.get("as_info_id"),
                        "will_apply_workers": list(base["workers"]),
                        "will_apply_date": tgt.get("target_date") or "",
                        "already_scheduled": bool(cur_visit),
                        "fallback": False,
                        "sort_date": cand.get("sort_date") or "9999-99-99",
                    }
                )

        def primary_sort_key(rec: dict[str, Any]) -> tuple:
            return (
                rec.get("route_duration_min") or 9999,
                rec.get("route_distance_km") or 9999,
                rec.get("sort_date") or "9999-99-99",
                rec["as_order_id"],
            )

        raw_recs.sort(key=primary_sort_key)
        chosen = raw_recs[:per_target_limit]

        # §2.4.15: token/straight fallback only when no route calculation succeeded
        # for this target. If any Kakao route returned success (even duration > cap),
        # do not show misleading "확인 불가" rows or discard known metrics.
        if not chosen and ranked:
            any_route_success = False
            for skm, cand, _elat, _elng in ranked:
                oid = int(cand["order_id"])
                payload = route_by_pair.get((t_idx, oid))
                if not payload:
                    continue
                if payload["route"].get("status") == "success":
                    any_route_success = True
                    break
            if any_route_success:
                base["message"] = (
                    "실제 이동 시간이 조건(30분 이하)을 만족하는 인근 AS가 없습니다."
                )
            else:
                fb2: list[tuple[int, float, dict[str, Any]]] = []
                for skm, cand, _elat, _elng in ranked:
                    tok = _token_overlap_score(
                        tgt_address, (cand.get("address") or "").strip()
                    )
                    fb2.append((tok, skm, cand))
                fb2.sort(key=lambda row: (-row[0], row[1], row[2]["order_id"]))
                for tok, skm, cand in fb2[:per_target_limit]:
                    if tok <= 0 and skm <= 0:
                        continue
                    elat, elng = _entity_lat_lng(cand, geo_map)
                    if elat is None or elng is None:
                        continue
                    cur_visit = (cand.get("current_visit_date") or "").strip()
                    chosen.append(
                        {
                            "as_order_id": int(cand["order_id"]),
                            "customer_name": cand.get("customer_name") or "",
                            "address": (cand.get("address") or "").strip(),
                            "current_visit_date": cur_visit,
                            "lat": float(elat),
                            "lng": float(elng),
                            "route_distance_km": None,
                            "route_duration_min": None,
                            "straight_distance_km": round(skm, 2),
                            "score_text": "실제거리/소요시간 확인 불가 (직선·주소 유사도 기준)",
                            "as_info_id": cand.get("as_info_id"),
                            "will_apply_workers": list(base["workers"]),
                            "will_apply_date": tgt.get("target_date") or "",
                            "already_scheduled": bool(cur_visit),
                            "fallback": True,
                            "sort_date": cand.get("sort_date") or "9999-99-99",
                        }
                    )

        base["recommendations"] = chosen
        out_targets.append(base)

    ref_norm = str(reference_date or "").strip()
    if ref_norm:
        for tgt_row in out_targets:
            td = str(tgt_row.get("target_date") or "").strip()
            if td and td != ref_norm:
                oid = tgt_row.get("order_id")
                warnings.append(
                    f"출고 #{oid}: 화면 기준일({ref_norm})과 주문 시공일({td})이 다를 수 있습니다."
                )

    return {
        "targets": out_targets,
        "partial": partial,
        "warnings": warnings,
    }
