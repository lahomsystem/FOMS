"""Measurement-dashboard-only branches for shared ERP map routes (`foms.api.measurement.map`)."""

from __future__ import annotations

from flask import jsonify

from db import get_db
from foms.services.common.map_generator import FOMSMapGenerator
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.map_snapshot import build_measurement_map_query, build_measurement_snapshot
from foms.services.geocode_helpers import extract_address_from_order
from foms.services.erp_display import self_measurement_four_checks_done
from foms.services.erp_permissions import is_order_related_to_user


def _apply_mine_filter(orders, *, mine, current_user):
    """`mine`이 True이고 로그인 유저가 있으면 내 담당 주문만 남긴다.

    Args:
        orders: Order 리스트
        mine: 내 주문 필터 활성 여부
        current_user: 현재 로그인 유저(없으면 필터 미적용)
    Returns:
        필터링된 Order 리스트
    """
    if not (mine and current_user):
        return orders
    return [o for o in orders if is_order_related_to_user(o, current_user)]


def measurement_map_data_response(
    *,
    date_filter: str,
    search_query: str,
    manager_filter: str,
    dashboard: str | None,
    limit: int,
    mine: bool = False,
    current_user=None,
):
    """JSON response for `/api/map_data` when `dashboard=measurement` and date is set."""
    db = get_db()
    query = build_measurement_map_query(
        db, date_filter, search_query, manager_filter, dashboard, limit
    )
    orders = query.all()
    orders = [o for o in orders if not self_measurement_four_checks_done(o)]
    orders = _apply_mine_filter(orders, mine=mine, current_user=current_user)
    snapshot = build_measurement_snapshot(orders, manager_filter)
    return jsonify({
        'success': True,
        'orders': snapshot['orders'],
        'markers': snapshot['markers'],
        'summary': snapshot['summary'],
        'data': snapshot['markers'],
    })


def measurement_generate_map_response(
    *,
    date_filter: str,
    search_query: str,
    manager_filter: str,
    dashboard: str | None,
    limit: int,
    title: str,
    route_mode: bool = False,
    mine: bool = False,
    current_user=None,
):
    """JSON response for `/api/generate_map` when `dashboard=measurement` and date is set.

    ``route_mode``면 오늘(조회일) 실측 주문을 방문 시간순으로 잇는 동선 오버레이
    (순번 배지 + 폴리라인)를 지도에 그린다. ``mine``이면 내 담당 주문만 표시한다.
    """
    db = get_db()
    query = build_measurement_map_query(
        db, date_filter, search_query, manager_filter, dashboard, limit
    )
    orders = query.all()
    orders = [o for o in orders if not self_measurement_four_checks_done(o)]
    orders = _apply_mine_filter(orders, mine=mine, current_user=current_user)

    to_geocode = []
    for order in orders:
        lat = getattr(order, 'lat', None)
        lng = getattr(order, 'lng', None)
        if lat is None or lng is None:
            addr = extract_address_from_order(order)
            if addr and addr.strip() and addr.strip() != '-':
                if getattr(order, 'geocode_status', None) != 'pending':
                    order.geocode_status = 'pending'
                    to_geocode.append((order, addr.strip()))
    for order, _ in to_geocode:
        enqueue_geocode_order_address(order.id)
    if to_geocode:
        db.commit()

    snapshot = build_measurement_snapshot(orders, manager_filter)
    map_generator = FOMSMapGenerator()
    map_data = snapshot['markers']
    orders_list = snapshot['orders']
    # 좌표 없어 동선에서 빠지는 주문 수(범례에 표기 — 조용한 누락 금지)
    route_skipped_count = len(orders_list) - len(map_data)

    if map_data:
        folium_map = map_generator.create_map(
            map_data, title,
            route_mode=route_mode,
            route_skipped_count=route_skipped_count,
        )
        map_html = folium_map._repr_html_() if folium_map else '<div class="error-message">지도를 생성할 수 없습니다.</div>'
        return jsonify({
            'success': True,
            'map_html': map_html,
            'total_orders': len(orders_list),
            'orders': orders_list,
            'snapshot': snapshot,
        })
    empty_map = map_generator.create_empty_map(title)
    map_html = empty_map._repr_html_() if empty_map else ''
    return jsonify({
        'success': True,
        'map_html': map_html,
        'total_orders': len(orders_list),
        'orders': orders_list,
        'snapshot': snapshot,
        'message': (
            f'{title} 지도에 표시할 마커가 없습니다. 우측 목록에서 주소 오류를 확인하세요.'
            if orders_list
            else f'{title}에 해당하는 주문이 없습니다.'
        )
    })
