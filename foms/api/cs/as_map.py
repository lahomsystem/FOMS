"""AS-dashboard-only branches for shared ERP map routes (`foms.api.cs.as_map`).

`/erp/as?tab=incomplete` 미완료 전체를 지도에 띄운다 — measurement 분기
(`foms.api.measurement.map`)와 동형 구조. 날짜 무관, 지방 포함, 버킷 필터 지원.
"""

from __future__ import annotations

from flask import jsonify

from db import get_db
from foms.services.common.map_generator import FOMSMapGenerator
# 지오코딩 트리거 계보 공유(measurement와 동일 헬퍼 — 좌표 소스는 orders.lat/lng 단일)
from foms.api.measurement.map import _enqueue_missing_measurement_geocodes
from foms.services.map_snapshot import build_as_incomplete_map_query, build_measurement_snapshot

AS_MAP_DEFAULT_TITLE = 'AS 미완료 지도'


def _build_as_map_snapshot(db, *, search_query: str, manager_filter: str,
                           bucket: str, limit: int, enqueue: bool):
    """AS 미완료 주문 조회 + 지오코딩 트리거 + snapshot 조립 (공용 내부 헬퍼).

    Returns:
        (snapshot, truncated): canonical DTO와 limit 잘림 여부.
    """
    query = build_as_incomplete_map_query(
        db, search_query, manager_filter, bucket=bucket, limit=limit
    )
    orders = query.all()
    if enqueue:
        _enqueue_missing_measurement_geocodes(db, orders)
    # AS 모집단은 실측 담당자 설정과 무관 — 마커는 상태색(use_manager_colors=False)
    snapshot = build_measurement_snapshot(
        orders, manager_filter, use_manager_colors=False
    )
    truncated = len(orders) >= limit
    return snapshot, truncated


def as_map_data_response(*, search_query: str, manager_filter: str,
                         bucket: str, limit: int, enqueue: bool = False):
    """JSON response for `/api/map_data` when `dashboard=as`.

    ``enqueue``면 좌표 없는 주문의 지오코딩을 트리거한다(카카오 클라 렌더 최초 로드용).
    """
    db = get_db()
    snapshot, truncated = _build_as_map_snapshot(
        db, search_query=search_query, manager_filter=manager_filter,
        bucket=bucket, limit=limit, enqueue=enqueue,
    )
    summary = dict(snapshot['summary'])
    summary['limit_truncated'] = truncated  # 묵시 잘림 금지 — 클라 배너 노출용
    return jsonify({
        'success': True,
        'orders': snapshot['orders'],
        'markers': snapshot['markers'],
        'summary': summary,
        'data': snapshot['markers'],
    })


def as_generate_map_response(*, search_query: str, manager_filter: str,
                             bucket: str, limit: int, title: str):
    """JSON response for `/api/generate_map` when `dashboard=as` (folium 폴백)."""
    db = get_db()
    snapshot, truncated = _build_as_map_snapshot(
        db, search_query=search_query, manager_filter=manager_filter,
        bucket=bucket, limit=limit, enqueue=True,
    )
    map_generator = FOMSMapGenerator()
    map_data = snapshot['markers']
    orders_list = snapshot['orders']

    if map_data:
        folium_map = map_generator.create_map(map_data, title)
        map_html = folium_map._repr_html_() if folium_map else '<div class="error-message">지도를 생성할 수 없습니다.</div>'
        return jsonify({
            'success': True,
            'map_html': map_html,
            'total_orders': len(orders_list),
            'orders': orders_list,
            'snapshot': snapshot,
            'limit_truncated': truncated,
        })
    empty_map = map_generator.create_empty_map(title)
    map_html = empty_map._repr_html_() if empty_map else ''
    return jsonify({
        'success': True,
        'map_html': map_html,
        'total_orders': len(orders_list),
        'orders': orders_list,
        'snapshot': snapshot,
        'limit_truncated': truncated,
        'message': (
            f'{title} 지도에 표시할 마커가 없습니다. 우측 목록에서 주소 오류를 확인하세요.'
            if orders_list
            else 'AS 미완료 주문이 없습니다.'
        )
    })
