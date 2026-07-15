"""실측 '오늘 동선' 페이로드 빌더 (SSOT).

`/api/erp/measurement/route` API와 실측 대시보드 뷰의 서버 인라인
(`data-route-inline`)이 동일 계보의 points 를 쓰도록 빌더를 한곳에 모은다.
분리 이유: 동선 카드 첫 페인트가 route API 왕복(한국↔싱가포르 tail 2-9s)을
기다리지 않게, 뷰가 렌더 시점에 같은 데이터를 직접 인라인하기 위함.

쿼리·points 구성·최근접 이웃 순서 결정은 기존 API 구현을 동작 보존으로
추출한 것이다(중복 구현 금지).
"""
from __future__ import annotations

import math
from typing import Any, Optional

from sqlalchemy import or_

from models import Order, OrderScheduleDate
from foms.services.common.address_converter import FOMSAddressConverter
from foms.services.erp_permissions import build_mine_sql_filter
from foms.services.measurement_dates import extract_all_measurement_dates

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


def _build_route_points(orders: list[Order]) -> list[dict[str, Any]]:
    """주문 → 좌표 points 변환 (ERP structured_data 주소/이름 우선, 지오코딩 실패 제외).

    Args:
        orders: `_query_route_orders` 결과.

    Returns:
        {id, customer_name, phone, address, measurement_time, manager_name,
         status, measurement_completed, lat, lng, geo_status} 리스트.
    """
    converter = FOMSAddressConverter()
    points: list[dict[str, Any]] = []
    for o in orders:
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

        lat, lng, status = converter.convert_address(address_to_use)
        if lat is None or lng is None:
            continue
        points.append({
            "id": o.id,
            "customer_name": customer_name,
            "phone": phone,
            "address": address_to_use,
            "measurement_time": o.measurement_time,
            "manager_name": manager_name,
            "status": o.status,
            "measurement_completed": bool(o.measurement_completed),
            "lat": float(lat),
            "lng": float(lng),
            "geo_status": status
        })
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

    Args:
        db: SQLAlchemy 세션.
        date_filter: 실측일(YYYY-MM-DD).
        manager_filter: 담당자 부분일치 필터.
        limit: 최대 지점 수(1~30 클램프).
        current_user / mine_active: '내 주문' 필터 계보.

    Returns:
        {date, manager, total_points, route, total_distance_km}
    """
    limit = max(1, min(int(limit), 30))
    orders = _query_route_orders(db, date_filter, manager_filter, limit, current_user, mine_active)
    points = _build_route_points(orders)
    if len(points) <= 1:
        return {
            "date": date_filter,
            "manager": manager_filter,
            "total_points": len(points),
            "route": points,
            "total_distance_km": 0,
        }
    route, total_km = _order_nearest_neighbor(points)
    return {
        "date": date_filter,
        "manager": manager_filter,
        "total_points": len(points),
        "route": route,
        "total_distance_km": total_km,
    }


def build_inline_route_strip_payload(
    db,
    *,
    date_filter: str,
    current_user=None,
    mine_active: bool = False,
) -> Optional[dict[str, Any]]:
    """대시보드 서버 인라인용 최소 페이로드 — 2지점 미만이면 None(스트립 비표시).

    Args:
        db: SQLAlchemy 세션.
        date_filter: 실측일(YYYY-MM-DD).
        current_user / mine_active: '내 주문' 필터 계보(대시보드 뷰와 동일).

    Returns:
        {"route": [{INLINE_POINT_FIELDS...}]} 또는 None.
    """
    payload = build_measurement_route_payload(
        db, date_filter=date_filter, current_user=current_user, mine_active=mine_active,
    )
    pts = payload.get("route") or []
    if len(pts) < 2:
        return None
    return {"route": [{k: p.get(k) for k in INLINE_POINT_FIELDS} for p in pts]}
