"""
실측 지도 공통 Snapshot 및 Query Builder (2026-03-15).
지도/대시보드 검색 규칙 통일, canonical DTO 조립.
"""
from sqlalchemy import or_, and_, cast, String

from models import Order
from services.erp_display import self_measurement_four_checks_done
from services.geocode_helpers import extract_address_from_order


def _measurement_search_filter(query, q):
    """고객·담당자·주소 전체 검색 (Order + ERP Beta structured_data)."""
    if not q or not q.strip():
        return query
    term = f'%{q.strip()}%'
    return query.filter(
        or_(
            Order.customer_name.ilike(term),
            Order.manager_name.ilike(term),
            Order.address.ilike(term),
            and_(
                Order.is_erp_beta == True,
                cast(Order.structured_data, String).ilike(term)
            )
        )
    )


def build_measurement_map_query(db, date, q, manager, dashboard, limit=500):
    """
    실측 지도/대시보드 공통 주문 검색 쿼리.
    대시보드와 동일한 주문 집합 규칙 적용.

    Args:
        db: DB 세션
        date: 실측일 (YYYY-MM-DD)
        q: 검색어
        manager: 담당자 필터 (부분 일치)
        dashboard: 'measurement' 등
        limit: 최대 주문 수

    Returns:
        SQLAlchemy query (아직 .all() 호출 전)
    """
    from models import OrderScheduleDate

    query = db.query(Order).filter(Order.active_filter())
    query = _measurement_search_filter(query, q)

    # 자가실측·지방실측 제외(진짜 실측 필요한 것만)
    if dashboard == 'measurement':
        query = query.filter(
            or_(
                and_(
                    Order.is_regional != True,
                    ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
                ),
                Order.is_self_measurement == True
            )
        )
    else:
        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )

    # measurement 모드: status는 ALL 고정
    if dashboard != 'measurement':
        pass  # status 필터는 caller가 적용 (현재 erp_map에서 status_filter 사용)

    if date:
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(
            OrderScheduleDate.kind == 'measurement',
            OrderScheduleDate.date == date
        )
        query = query.distinct()

    query = query.order_by(Order.id.desc()).limit(limit)

    return query


def _extract_order_display_fields(order):
    """Order에서 목록/지도 표시용 필드 추출."""
    customer_name = order.customer_name
    phone = order.phone
    address_to_use = order.address
    product = order.product
    measurement_date = order.measurement_date
    scheduled_date = order.scheduled_date
    manager_name = order.manager_name or '-'

    if order.is_erp_beta and order.structured_data:
        sd = order.structured_data
        erp_customer = ((sd.get('parties') or {}).get('customer') or {}).get('name')
        if erp_customer:
            customer_name = erp_customer
        erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
        if erp_phone:
            phone = erp_phone
        site = sd.get('site') or {}
        erp_full = site.get('address_full')
        if erp_full and str(erp_full).strip() and str(erp_full).strip() != '-':
            address_to_use = str(erp_full).strip()
        elif site.get('address_main'):
            main = str(site['address_main']).strip()
            detail = (site.get('address_detail') or '').strip()
            if detail and detail != '-':
                address_to_use = f"{main} {detail}"
            else:
                address_to_use = main
        items = sd.get('items') or []
        if items:
            first = items[0]
            pn = first.get('product_name') or first.get('name')
            if pn:
                product = f"{pn} 외 {len(items) - 1}개" if len(items) > 1 else pn
        erp_meas = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
        if erp_meas:
            measurement_date = erp_meas
        erp_sched = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
        if erp_sched:
            scheduled_date = erp_sched
        erp_manager = ((sd.get('parties') or {}).get('manager') or {}).get('name')
        if erp_manager:
            manager_name = erp_manager

    return {
        'customer_name': customer_name,
        'phone': phone,
        'address_to_use': address_to_use,
        'product': product,
        'measurement_date': measurement_date,
        'scheduled_date': scheduled_date,
        'manager_name': manager_name,
    }


def _canonicalize_geocode_status(order, lat, lng, has_address):
    """DB geocode_status를 success|pending|failed 3상태로 정규화."""
    raw = getattr(order, 'geocode_status', None)
    if raw in ('success', 'pending', 'failed'):
        return raw
    if lat is not None and lng is not None:
        return 'success'
    if has_address:
        return 'pending'
    return 'failed'


def _format_date(val):
    """날짜를 YYYY-MM-DD 문자열로."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    return str(val)


def build_measurement_snapshot(orders, manager_filter=None):
    """
    주문 리스트에서 canonical DTO 조립 (목록 + 마커 + 요약).

    Args:
        orders: Order 객체 리스트 (self_measurement_four_checks_done 제외된 상태)
        manager_filter: 담당자 필터 (부분 일치, None이면 미적용)

    Returns:
        {
            'orders': [...],
            'markers': [...],
            'summary': { total_orders, marker_count, pending_count, failed_count, success_count }
        }
    """
    orders_list = []
    markers = []
    pending_count = 0
    failed_count = 0
    success_count = 0

    for order in orders:
        ctx = _extract_order_display_fields(order)
        lat = getattr(order, 'lat', None)
        lng = getattr(order, 'lng', None)
        addr = extract_address_from_order(order)
        has_address = bool(addr and addr.strip() and addr.strip() != '-')
        status = _canonicalize_geocode_status(order, lat, lng, has_address)

        if manager_filter:
            mn = str(ctx['manager_name'] or '')
            if manager_filter.lower() not in mn.lower():
                continue

        if self_measurement_four_checks_done(order):
            continue

        if status == 'pending':
            pending_count += 1
        elif status == 'failed':
            failed_count += 1
        else:
            success_count += 1

        orders_list.append({
            'id': order.id,
            'customer_name': ctx['customer_name'],
            'phone': ctx['phone'],
            'address': ctx['address_to_use'],
            'product': ctx['product'],
            'status': order.status,
            'received_date': _format_date(order.received_date),
            'measurement_date': _format_date(ctx['measurement_date']),
            'scheduled_date': _format_date(ctx['scheduled_date']),
            'completion_date': _format_date(order.completion_date),
            'manager_name': ctx['manager_name'],
            'notes': order.notes or '-',
            'conversion_status': status,
            'latitude': float(lat) if lat is not None else None,
            'longitude': float(lng) if lng is not None else None,
        })

        if lat is not None and lng is not None:
            markers.append({
                'id': order.id,
                'customer_name': ctx['customer_name'],
                'latitude': float(lat),
                'longitude': float(lng),
                'address': ctx['address_to_use'],
                'product': ctx['product'],
                'status': order.status,
                'received_date': _format_date(order.received_date),
                'phone': ctx['phone'],
            })

    return {
        'orders': orders_list,
        'markers': markers,
        'summary': {
            'total_orders': len(orders_list),
            'marker_count': len(markers),
            'pending_count': pending_count,
            'failed_count': failed_count,
            'success_count': success_count,
        },
    }
