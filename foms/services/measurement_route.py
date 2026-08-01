"""실측 '오늘 동선' 페이로드 빌더 (SSOT).

`/api/erp/measurement/route` API와 실측 대시보드 뷰의 서버 인라인
(`data-route-inline`)이 동일 계보의 주문/정렬을 쓰도록 빌더를 한곳에 모은다.
대시보드 서버 인라인은 HTML 렌더 hot path 이므로 저장 좌표만 사용하고,
주소 변환/외부 지오코딩은 API·백그라운드 계보에만 둔다.

쿼리·points 구성·최근접 이웃 순서 결정은 기존 API 구현을 동작 보존으로
추출한 것이다(중복 구현 금지).

ROUTE-01: `route`(양쪽 빌더 공통 키)는 항상 예약 순서(측정 시각 오름차순)다.
'다음 방문'/히어로(대표 다음 목적지) 판정은 반드시 이 배열 기준이어야 다른
화면의 히어로 위젯과 일치한다. 최근접 이웃(NN) 재배열은
`build_measurement_route_payload`의 `optimized_route`/`optimized_total_distance_km`로만
별도 제공한다(데스크톱 "경로 계획" 근사 직선거리 참고용 — hero/next 판정 금지).
"""
from __future__ import annotations

import datetime
import logging
import math
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from models import Order, OrderScheduleDate
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.erp_permissions import build_mine_sql_filter
from foms.services.measurement_dates import extract_all_measurement_dates

logger = logging.getLogger(__name__)

# 인라인 페이로드 최소 필드(전송 절제): 스트립 렌더(헤드/풋 캡션·순번·현재 판정)와
# route-eta 요청(id)에 필요한 것만 남긴다. phone/manager_name/status/geo_status 제외.
INLINE_POINT_FIELDS = (
    "id",
    "customer_name",
    "address",
    "measurement_time",
    "measurement_completed",
    "lat",
    "lng",
)


def _query_route_orders(
    db,
    date_filter: str,
    manager_filter: str,
    limit: int,
    current_user,
    mine_active: bool,
) -> list[Order]:
    """동선 대상 주문 조회 (API `/route`와 동일 predicate·정렬·limit).

    Args:
        db: SQLAlchemy 세션.
        date_filter: 실측일(YYYY-MM-DD). 빈 값이면 날짜 필터 없이 limit 만 적용.
        manager_filter: 담당자 부분일치 필터(trigram 인덱스 사용).
        limit: 최대 지점 수(호출부에서 1~30으로 클램프).
        current_user: '내 주문' 필터 대상 사용자.
        mine_active: '내 주문' 필터 활성 여부.

    Returns:
        측정 시각 오름차순 주문 리스트.
    """
    query = db.query(Order).filter(Order.active_filter())

    if date_filter:
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(
            OrderScheduleDate.kind == 'measurement',
            OrderScheduleDate.date == date_filter
        ).distinct()

    if manager_filter:
        query = query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))  # perf-ok: ix_orders_manager_name_trgm

    if mine_active and current_user:
        mine_conds = build_mine_sql_filter(current_user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))

    ordered_query = query.order_by(
        Order.measurement_time.asc().nullslast(),
        Order.id.asc(),
    )
    if date_filter:
        candidate_orders = ordered_query.all()
        return [
            order
            for order in candidate_orders
            if date_filter in extract_all_measurement_dates(order)
        ][:limit]
    return ordered_query.limit(limit).all()


def _route_order_display_fields(o: Order) -> dict[str, Any]:
    """동선 point 표시 필드 추출(ERP structured_data 우선)."""
    address_to_use = o.address
    customer_name = o.customer_name
    phone = o.phone
    manager_name = o.manager_name

    if o.is_erp_order and o.structured_data:
        sd = o.structured_data
        erp_address_full = (sd.get('site') or {}).get('address_full')
        erp_address_main = (sd.get('site') or {}).get('address_main')
        erp_address_detail = (sd.get('site') or {}).get('address_detail')

        if erp_address_full and erp_address_full.strip() and erp_address_full != '-':
            address_to_use = erp_address_full.strip()
        elif erp_address_main and erp_address_main.strip():
            if erp_address_detail and erp_address_detail.strip() and erp_address_detail != '-':
                address_to_use = f"{erp_address_main.strip()} {erp_address_detail.strip()}"
            else:
                address_to_use = erp_address_main.strip()

        erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
        if erp_customer_name:
            customer_name = erp_customer_name

        erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
        if erp_phone:
            phone = erp_phone

        erp_manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
        if erp_manager_name:
            manager_name = erp_manager_name

    return {
        "address": address_to_use,
        "customer_name": customer_name,
        "phone": phone,
        "manager_name": manager_name,
    }


def _point_from_order(
    o: Order,
    *,
    lat: float,
    lng: float,
    geo_status: str,
) -> dict[str, Any]:
    fields = _route_order_display_fields(o)
    return {
        "id": o.id,
        "customer_name": fields["customer_name"],
        "phone": fields["phone"],
        "address": fields["address"],
        "measurement_time": o.measurement_time,
        "manager_name": fields["manager_name"],
        "status": o.status,
        "measurement_completed": bool(o.measurement_completed),
        "lat": float(lat),
        "lng": float(lng),
        "geo_status": geo_status,
    }


def _store_geocode_coords(o: Order, lat: float, lng: float) -> bool:
    """지오코딩 성공 좌표를 주문에 1회 기록. 이미 좌표가 있으면 건드리지 않는다.

    Args:
        o: 대상 주문.
        lat: 지오코딩 성공 위도.
        lng: 지오코딩 성공 경도.

    Returns:
        실제로 기록했으면 True.
    """
    if o.lat is not None and o.lng is not None:
        return False
    o.lat = float(lat)
    o.lng = float(lng)
    o.geocode_status = "success"
    o.geocoded_at = datetime.datetime.now()
    return True


def _build_route_points(orders: list[Order], db=None) -> list[dict[str, Any]]:
    """주문 → 좌표 points 변환 (API용: 좌표 없으면 즉시 지오코딩 시도).

    지오코딩에 성공한 좌표는 `db`가 주어졌을 때 주문에 1회 저장한다. 다음 방문부터는
    저장 좌표 fast path(`build_inline_route_strip_payload`)가 바로 렌더한다.
    실패 상태(`geocode_status='failed'`)는 기록하지 않는다 — 실패 판정은 RQ 태스크
    `geocode_order_address` 소관이며, 일시 네트워크 오류로 정상 주소를 오염시킬 수 있다.

    Args:
        orders: `_query_route_orders` 결과.
        db: SQLAlchemy 세션. None 이면 좌표를 저장하지 않는다.

    Returns:
        {id, customer_name, phone, address, measurement_time, manager_name,
         status, measurement_completed, lat, lng, geo_status} 리스트.
    """
    converter = FOMSAddressConverter()
    points: list[dict[str, Any]] = []
    stored = 0
    for o in orders:
        address_to_use = _route_order_display_fields(o)["address"]
        lat, lng, status = converter.convert_address(address_to_use)
        if lat is None or lng is None:
            continue
        points.append(_point_from_order(o, lat=lat, lng=lng, geo_status=status))
        if db is not None and _store_geocode_coords(o, lat, lng):
            stored += 1

    if db is not None and stored:
        try:
            db.commit()
        except SQLAlchemyError:
            logger.exception("route 지오코딩 좌표 저장 실패 (응답은 계속 진행)")
            db.rollback()
    return points


def _build_route_points_from_stored_coords(orders: list[Order]) -> list[dict[str, Any]]:
    """대시보드 렌더용 fast path: 저장 좌표만 사용하고 외부 지오코딩은 호출하지 않는다."""
    points: list[dict[str, Any]] = []
    for o in orders:
        lat = getattr(o, "lat", None)
        lng = getattr(o, "lng", None)
        if lat is None or lng is None:
            continue
        status = getattr(o, "geocode_status", None) or "success"
        points.append(_point_from_order(o, lat=lat, lng=lng, geo_status=status))
    return points


def _haversine_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    """두 points 간 haversine 거리(km)."""
    R = 6371.0
    lat1 = math.radians(a["lat"])
    lon1 = math.radians(a["lng"])
    lat2 = math.radians(b["lat"])
    lon2 = math.radians(b["lng"])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _order_nearest_neighbor(points: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    """최근접 이웃 휴리스틱 방문 순서 + 총거리(km, 소수 2자리)."""
    remaining = points[:]
    route = [remaining.pop(0)]

    while remaining:
        last = route[-1]
        best_i = 0
        best_d = float("inf")
        for i, cand in enumerate(remaining):
            d = _haversine_km(last, cand)
            if d < best_d:
                best_d = d
                best_i = i
        route.append(remaining.pop(best_i))

    km_h = 0.0
    for i in range(len(route) - 1):
        km_h += _haversine_km(route[i], route[i + 1])
    return route, round(km_h, 2)


def build_measurement_route_payload(
    db,
    *,
    date_filter: str,
    manager_filter: str = "",
    limit: int = 20,
    current_user=None,
    mine_active: bool = False,
) -> dict[str, Any]:
    """실측 동선 페이로드(dict) — API 응답 본문(`success` 제외)과 동일 형태.

    `route`는 예약 순서(측정 시각 오름차순 — `_query_route_orders` SSOT)를 그대로
    반환한다. 히어로/'다음 방문' 판정(첫 미완료 지점)은 반드시 이 순서를 기준으로
    해야 한다 — 스케줄 히어로와 실제 다음 방문지가 어긋나던 버그(ROUTE-01)의 원인이
    바로 이 배열을 최근접 이웃으로 재배열해 반환하던 것이었다.
    `optimized_route`/`optimized_total_distance_km`는 최근접 이웃 휴리스틱으로
    재배열한 별도 동선(데스크톱 "경로 계획" 모달의 근사 직선거리 참고용)이다 —
    예약 순서와 다른 label·sequence로 분리해 제공하며, hero/next 판정에는 쓰지 않는다.

    Args:
        db: SQLAlchemy 세션.
        date_filter: 실측일(YYYY-MM-DD).
        manager_filter: 담당자 부분일치 필터.
        limit: 최대 지점 수(1~30 클램프).
        current_user / mine_active: '내 주문' 필터 계보.

    Returns:
        {date, manager, total_points, route, optimized_route, optimized_total_distance_km}
    """
    limit = max(1, min(int(limit), 30))
    orders = _query_route_orders(db, date_filter, manager_filter, limit, current_user, mine_active)
    points = _build_route_points(orders, db)
    if len(points) <= 1:
        return {
            "date": date_filter,
            "manager": manager_filter,
            "total_points": len(points),
            "route": points,
            "optimized_route": points,
            "optimized_total_distance_km": 0,
        }
    optimized_route, optimized_total_km = _order_nearest_neighbor(points)
    return {
        "date": date_filter,
        "manager": manager_filter,
        "total_points": len(points),
        "route": points,
        "optimized_route": optimized_route,
        "optimized_total_distance_km": optimized_total_km,
    }


def build_inline_route_strip_payload(
    db,
    *,
    date_filter: str,
    current_user=None,
    mine_active: bool = False,
) -> dict[str, Any]:
    """대시보드 서버 인라인용 최소 페이로드.

    HTML 렌더 중에는 `FOMSAddressConverter.convert_address()`를 호출하지 않는다.
    좌표가 없는 주문은 백그라운드 지오코딩 대상이며, 여기서는 제외한다.
    2지점 미만이어도 빈/단일 route 를 내려 JS fetch 폴백의 동기 지오코딩 재진입을 막는다.

    `route`는 예약 순서(측정 시각 오름차순) 그대로다 — 최근접 이웃 재배열을 하지
    않는다(ROUTE-01). 스트립의 히어로/'다음 방문' 캡션이 이 배열의 첫 미완료
    지점에서 파생되므로, 재배열하면 다른 히어로 위젯이 말하는 '다음 방문'과
    어긋난다. 최적 동선(최근접 이웃)이 필요하면 `build_measurement_route_payload`의
    `optimized_route`를 쓴다.

    Args:
        db: SQLAlchemy 세션.
        date_filter: 실측일(YYYY-MM-DD).
        current_user / mine_active: '내 주문' 필터 계보(대시보드 뷰와 동일).

    Returns:
        {"route": [{INLINE_POINT_FIELDS...}]}. 2지점 미만이면 JS가 스트립을 숨긴다.
    """
    orders = _query_route_orders(
        db, date_filter, "", 20, current_user, mine_active,
    )
    pts = _build_route_points_from_stored_coords(orders)
    return {"route": [{k: p.get(k) for k in INLINE_POINT_FIELDS} for p in pts]}
