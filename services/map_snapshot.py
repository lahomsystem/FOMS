"""
실측 지도 공통 Snapshot 및 Query Builder (2026-03-15).
지도/대시보드 검색 규칙 통일, canonical DTO 조립.
"""
import math
from sqlalchemy import or_, and_, cast, String, func

from models import Order
from services.geocode_helpers import extract_address_from_order


def _measurement_date_variants(yyyy_mm_dd):
    """
    OrderScheduleDate.date가 다양한 형식으로 저장된 경우 모두 매칭.
    - 2026-03-16, 2026-3-16 (하이픈)
    - 2026.03.16, 2026.3.16 (점)
    - 2026/03/16, 2026/3/16 (슬래시)
    """
    if not yyyy_mm_dd or len(yyyy_mm_dd) < 10:
        return [yyyy_mm_dd] if yyyy_mm_dd else []
    parts = yyyy_mm_dd.replace('.', '-').replace('/', '-').split('-')
    if len(parts) != 3:
        return [yyyy_mm_dd]
    y, m, d = parts[0], parts[1].lstrip('0') or '0', parts[2].lstrip('0') or '0'
    m2, d2 = parts[1], parts[2]  # zero-padded
    variants = [
        f"{y}-{m2}-{d2}",   # 2026-03-16
        f"{y}-{m}-{d}",     # 2026-3-16
        f"{y}.{m2}.{d2}",   # 2026.03.16
        f"{y}.{m}.{d}",     # 2026.3.16
        f"{y}/{m2}/{d2}",   # 2026/03/16
        f"{y}/{m}/{d}",     # 2026/3/16
    ]
    return list(dict.fromkeys(variants))


def _measurement_search_filter(query, q):
    """고객·담당자·주소·주문ID 전체 검색 (Order + ERP Beta structured_data)."""
    if not q or not q.strip():
        return query
    term = f'%{q.strip()}%'
    return query.filter(
        or_(
            cast(Order.id, String).ilike(term),  # q=2662 주문 ID 검색
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

    if manager and manager.strip():
        manager_term = f'%{manager.strip()}%'
        query = query.filter(
            or_(
                Order.manager_name.ilike(manager_term),
                and_(
                    Order.is_erp_beta == True,
                    cast(Order.structured_data, String).ilike(manager_term)
                )
            )
        )

    # measurement 모드: status는 ALL 고정
    if dashboard != 'measurement':
        pass  # status 필터는 caller가 적용 (현재 erp_map에서 status_filter 사용)

    if date:
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        date_variants = _measurement_date_variants(date)
        date_digits = date.replace('-', '')[:8] if date else ''  # 20260316
        # 형식 유연: IN (하이픈/점/슬래시) OR 숫자만 추출 비교 (공백·기타 구분자 대응)
        query = query.filter(
            OrderScheduleDate.kind == 'measurement',
            or_(
                OrderScheduleDate.date.in_(date_variants),
                func.substring(
                    func.regexp_replace(func.trim(OrderScheduleDate.date), r'[^0-9]', '', 'g'),
                    1, 8
                ) == date_digits
            )
        )
        query = query.distinct(Order.id)

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
    # 주소 있으나 좌표 없음: pending(변환 중)만 노란색, NULL/기타는 failed(분홍색)
    if has_address and raw == 'pending':
        return 'pending'
    return 'failed'  # geocode_status NULL 등 → 좌표 변환 실패로 간주


def _format_date(val):
    """날짜를 YYYY-MM-DD 문자열로."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, 'strftime'):
        return val.strftime('%Y-%m-%d')
    return str(val)


def _apply_marker_offset_for_duplicates(markers):
    """
    동일 (lat,lng) 마커에 소량 오프셋 적용. 겹쳐서 1개만 보이던 2건 표시.
    ~0.00015도(약 15m)씩 나선형으로 분산.
    """
    if not markers:
        return
    # (lat, lng) → 해당 마커 인덱스 목록
    by_pos = {}
    for i, m in enumerate(markers):
        key = (round(m['latitude'], 8), round(m['longitude'], 8))
        by_pos.setdefault(key, []).append(i)
    offset = 0.00015
    for indices in by_pos.values():
        if len(indices) <= 1:
            continue
        for k, i in enumerate(indices[1:], 1):
            # 나선형: 1→동, 2→남동, 3→남, 4→남서...
            angle = (k - 1) * 60
            rad = math.radians(angle)
            markers[i]['latitude'] = markers[i]['latitude'] + offset * math.cos(rad)
            markers[i]['longitude'] = markers[i]['longitude'] + offset * math.sin(rad)


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

    # 동일 좌표 마커 오프셋: 겹쳐서 1개만 보이던 문제 해결 (2662↔2655, 2670↔2650 등)
    _apply_marker_offset_for_duplicates(markers)

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
