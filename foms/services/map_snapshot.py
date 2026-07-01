"""
실측 지도 공통 Snapshot 및 Query Builder (2026-03-15).
지도/대시보드 검색 규칙 통일, canonical DTO 조립.
"""
from sqlalchemy import or_, and_, cast, String, func

from foms.persistence.main.models import Order
from foms.services.erp_display import normalize_manager_name
from foms.services.geocode_helpers import extract_address_from_order
from foms.services.erp_shipment_settings import load_erp_shipment_settings
from foms.services.measurement_manager_colors import (
    build_measurement_manager_color_map,
    resolve_measurement_manager_color,
)

__all__ = ["build_measurement_map_query", "build_measurement_snapshot"]


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
            cast(Order.id, String).ilike(term),  # perf-ok: bounded id search admin/cold path
            Order.customer_name.ilike(term),  # perf-ok: ix_orders_customer_name_trgm
            Order.manager_name.ilike(term),  # perf-ok: ix_orders_manager_name_trgm
            Order.address.ilike(term),  # perf-ok: ix_orders_address_trgm
            and_(
                Order.is_erp_order == True,
                cast(Order.structured_data, String).ilike(term)  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )
    )


def _measurement_date_prefix_expr(db, date_column):
    """Return the first 8 normalized digits from a schedule-date column.

    PostgreSQL keeps the legacy `regexp_replace` path. SQLite falls back to nested
    `replace()` calls so local dev/test QA can execute the same query family.
    """
    trimmed = func.trim(date_column)
    dialect_name = ""
    try:
        bind = db.get_bind()
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "") or ""
    except Exception:
        dialect_name = ""

    if dialect_name == "postgresql":
        normalized = func.regexp_replace(trimmed, r"[^0-9]", "", "g")
        return func.substring(normalized, 1, 8)

    normalized = trimmed
    for token in ("-", ".", "/", " "):
        normalized = func.replace(normalized, token, "")
    return func.substr(normalized, 1, 8)


def build_measurement_map_query(db, date, q, manager, dashboard, limit=500):
    """
    실측 지도/대시보드 공통 주문 검색 쿼리.
    measurement 지도/동선이 사용하던 legacy query 규칙을 유지한다.
    화면 본문의 recent-only `dashboard_active_filter(days=60)`는 여기 적용하지 않는다.

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
    from foms.persistence.main.models import OrderScheduleDate

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
                Order.manager_name.ilike(manager_term),  # perf-ok: ix_orders_manager_name_trgm
                and_(
                    Order.is_erp_order == True,
                    cast(Order.structured_data, String).ilike(manager_term)  # perf-ok: ix_orders_structured_data_text_trgm
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
        normalized_date_prefix = _measurement_date_prefix_expr(db, OrderScheduleDate.date)
        # 형식 유연: IN (하이픈/점/슬래시) OR 숫자만 추출 비교 (공백 포함 common separator 대응)
        query = query.filter(
            OrderScheduleDate.kind == 'measurement',
            or_(
                OrderScheduleDate.date.in_(date_variants),
                normalized_date_prefix == date_digits
            )
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
    measurement_time = order.measurement_time
    scheduled_date = order.scheduled_date
    manager_name = order.manager_name or '-'

    if order.is_erp_order and order.structured_data:
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
        erp_meas_time = (((sd.get('schedule') or {}).get('measurement') or {}).get('time'))
        if erp_meas_time:
            measurement_time = erp_meas_time
        erp_sched = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
        if erp_sched:
            scheduled_date = erp_sched
        erp_manager = normalize_manager_name(
            (sd.get('parties') or {}).get('manager'),
            manager_name,
        )
        if erp_manager:
            manager_name = erp_manager

    return {
        'customer_name': customer_name,
        'phone': phone,
        'address_to_use': address_to_use,
        'product': product,
        'measurement_date': measurement_date,
        'measurement_time': measurement_time,
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


def _normalize_location_key(value):
    """Normalize grouping keys for duplicate metadata."""
    if value is None:
        return ''
    text = str(value).strip()
    if not text:
        return ''
    return ' '.join(text.split())


def _duplicate_location_key(lat, lng):
    if lat is None or lng is None:
        return ''
    try:
        return f"{round(float(lat), 8):.8f},{round(float(lng), 8):.8f}"
    except (TypeError, ValueError):
        return ''


def _annotate_duplicate_groups(items, *, key_fn, group_prefix, hint_field='marker_render_hint'):
    """Attach duplicate-group metadata to snapshot rows."""
    groups = {}
    for index, item in enumerate(items):
        group_key = _normalize_location_key(key_fn(item))
        if not group_key:
            continue
        groups.setdefault(group_key, []).append(index)

    for group_key, indices in groups.items():
        group_size = len(indices)
        for position, item_index in enumerate(indices, start=1):
            item = items[item_index]
            item[f'{group_prefix}_group_key'] = group_key
            item[f'{group_prefix}_group_size'] = group_size
            item[f'{group_prefix}_group_index'] = position
            item[f'is_{group_prefix}'] = group_size > 1
            if group_size > 1:
                item[hint_field] = 'pastel_pink'
            elif hint_field not in item:
                item[hint_field] = 'status'


def _annotate_marker_metadata(orders_list, markers):
    """Attach duplicate location and duplicate address metadata."""
    _annotate_duplicate_groups(
        orders_list,
        key_fn=lambda item: _duplicate_location_key(item.get('latitude'), item.get('longitude')),
        group_prefix='duplicate_location',
    )
    _annotate_duplicate_groups(
        markers,
        key_fn=lambda item: _duplicate_location_key(item.get('latitude'), item.get('longitude')),
        group_prefix='duplicate_location',
    )

    _annotate_duplicate_groups(
        orders_list,
        key_fn=lambda item: item.get('address'),
        group_prefix='duplicate_address',
    )
    _annotate_duplicate_groups(
        markers,
        key_fn=lambda item: item.get('address'),
        group_prefix='duplicate_address',
    )

    for item in list(orders_list) + list(markers):
        if item.get('is_duplicate_location') or item.get('is_duplicate_address'):
            item['marker_render_hint'] = 'pastel_pink'
        else:
            item.setdefault('marker_render_hint', 'status')


def build_measurement_snapshot(orders, manager_filter=None, measurement_manager_options=None):
    """
    주문 리스트에서 canonical DTO 조립 (목록 + 마커 + 요약).

    Args:
        orders: Order 객체 리스트 (self_measurement_four_checks_done 제외된 상태)
        manager_filter: 담당자 필터 (부분 일치, None이면 미적용)
        measurement_manager_options: 실측 담당자 설정 목록 (테스트/호출자 주입용)

    Returns:
        {
            'orders': [...],
            'markers': [...],
            'summary': { total_orders, marker_count, pending_count, failed_count, success_count }
        }
    """
    prepared_orders = []
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

        prepared_orders.append({
            'order': order,
            'ctx': ctx,
            'lat': lat,
            'lng': lng,
            'conversion_status': status,
        })

    measurement_manager_options = (
        measurement_manager_options
        if measurement_manager_options is not None
        else (load_erp_shipment_settings().get('measurement_manager') or [])
    )
    manager_color_map = build_measurement_manager_color_map(
        [
            {
                'manager_name': item['ctx']['manager_name'],
                'order_id': item['order'].id,
            }
            for item in prepared_orders
        ],
        measurement_manager_options,
    )

    for item in prepared_orders:
        order = item['order']
        ctx = item['ctx']
        lat = item['lat']
        lng = item['lng']
        status = item['conversion_status']
        manager_color = resolve_measurement_manager_color(
            ctx['manager_name'],
            manager_color_map,
        )

        orders_list.append({
            'id': order.id,
            'customer_name': ctx['customer_name'],
            'phone': ctx['phone'],
            'address': ctx['address_to_use'],
            'product': ctx['product'],
            'status': order.status,
            'received_date': _format_date(order.received_date),
            'measurement_date': _format_date(ctx['measurement_date']),
            'measurement_time': ctx.get('measurement_time'),
            'scheduled_date': _format_date(ctx['scheduled_date']),
            'completion_date': _format_date(order.completion_date),
            'manager_name': ctx['manager_name'],
            'notes': order.notes or '-',
            'conversion_status': status,
            'latitude': float(lat) if lat is not None else None,
            'longitude': float(lng) if lng is not None else None,
            'manager_bg_color': manager_color['background'],
            'manager_bg_source': manager_color['source'],
            'manager_text_color': manager_color['text'],
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
                'measurement_time': ctx.get('measurement_time'),
                'phone': ctx['phone'],
                'manager_name': ctx['manager_name'],
                'manager_bg_color': manager_color['background'],
                'manager_bg_source': manager_color['source'],
                'manager_text_color': manager_color['text'],
            })

    # 동일 주소/좌표 메타데이터만 부여하고, 실제 집계/분리 UX는 클라이언트 줌 상태에서 제어한다.
    _annotate_marker_metadata(orders_list, markers)

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
