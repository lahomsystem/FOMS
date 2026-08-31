"""Measurement-dashboard-only branches for shared ERP map routes (`foms.api.measurement.map`)."""

from __future__ import annotations

import datetime
from typing import Any, Iterable

from flask import jsonify

from db import get_db
from foms.services.common.map_generator import FOMSMapGenerator
from foms.services.jobs.queue import enqueue_geocode_order_address
from foms.services.map_snapshot import build_measurement_map_query, build_measurement_snapshot
from foms.services.datetime_kst import now_utc_naive
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


#: ``geocode_status='failed'`` 주문을 다시 큐에 넣기까지 기다리는 최소 간격.
#: 실패 건 대부분은 주소 자체가 틀린 건이라, 지도를 열 때마다 재큐하면 카카오 쿼터만 태우고
#: 단일 RQ 워커를 점유해 진짜 pending(미시도) 건을 뒤로 민다(운영 실패 37건이 매 조회마다
#: 재큐되던 문제). 주소가 고쳐지면 write 경로가 ``geocode_status='pending'`` 으로 되돌리고
#: GEOCODE outbox 를 예약하므로, 여기 재큐는 **안전망**이다 — 영구 제외가 아니라 백오프다
#: (범용 경로 ``foms/api/erp_map.py`` 는 failed 를 아예 재시도하지 않는다. 실측 지도는
#: 오늘 방문할 주문을 지도에 올리는 게 목적이라 그 영구 제외를 따라가지 않는다).
FAILED_GEOCODE_REQUEUE_INTERVAL = datetime.timedelta(hours=24)


def _should_requeue_geocode(order: Any, *, now: datetime.datetime) -> bool:
    """좌표 없는 주문을 지금 지오코딩 큐에 다시 넣어야 하는지 판정한다.

    Args:
        order: 좌표가 없고 주소는 있는 Order.
        now: 백오프 판정 기준 시각(naive UTC — ``geocoded_at`` 저장 규약과 같은 축).

    Returns:
        ``pending``(이미 큐에 있음)이면 False. ``failed`` 는 마지막 시도
        (:attr:`geocoded_at`)로부터 :data:`FAILED_GEOCODE_REQUEUE_INTERVAL` 이 지났을 때만
        True(시도 기록이 없으면 즉시 True). 그 밖(NULL=미시도 등)은 즉시 True.
    """
    status = getattr(order, 'geocode_status', None)
    if status == 'pending':
        return False  # 이미 큐에 있음 — 중복 enqueue 금지(기존 동작 유지)
    if status == 'failed':
        last_attempt = getattr(order, 'geocoded_at', None)
        if last_attempt is None:
            return True  # 실패 시각 미기록(레거시 행) — 1회 재시도해 시각을 남긴다
        return (now - last_attempt) >= FAILED_GEOCODE_REQUEUE_INTERVAL
    return True  # NULL(미시도) 또는 success-but-no-coords → 즉시 큐


def _enqueue_missing_measurement_geocodes(db, orders: Iterable[Any]) -> None:
    """좌표 없는 주문을 pending 마킹 후 지오코딩 큐에 넣는다(generate_map과 동일 계보).

    ``failed`` 건은 :func:`_should_requeue_geocode` 백오프를 통과할 때만 재큐한다.

    Args:
        db: SQLAlchemy 세션.
        orders: 필터 완료된 Order 리스트.
    """
    now = now_utc_naive()
    to_geocode = []
    for order in orders:
        lat = getattr(order, 'lat', None)
        lng = getattr(order, 'lng', None)
        if lat is None or lng is None:
            addr = extract_address_from_order(order)
            if addr and addr.strip() and addr.strip() != '-':
                if _should_requeue_geocode(order, now=now):
                    order.geocode_status = 'pending'
                    to_geocode.append((order, addr.strip()))
    for order, _ in to_geocode:
        enqueue_geocode_order_address(order.id)
    if to_geocode:
        db.commit()


def measurement_map_data_response(
    *,
    date_filter: str,
    search_query: str,
    manager_filter: str,
    dashboard: str | None,
    limit: int,
    mine: bool = False,
    current_user=None,
    enqueue: bool = False,
):
    """JSON response for `/api/map_data` when `dashboard=measurement` and date is set.

    ``enqueue``면 좌표 없는 주문의 지오코딩을 트리거한다(카카오 클라 렌더 최초 로드용).
    """
    db = get_db()
    query = build_measurement_map_query(
        db, date_filter, search_query, manager_filter, dashboard, limit
    )
    orders = query.all()
    orders = [o for o in orders if not self_measurement_four_checks_done(o)]
    orders = _apply_mine_filter(orders, mine=mine, current_user=current_user)
    if enqueue:
        _enqueue_missing_measurement_geocodes(db, orders)
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
    _enqueue_missing_measurement_geocodes(db, orders)

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
