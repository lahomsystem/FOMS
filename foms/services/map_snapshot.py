"""
실측 지도 공통 Snapshot 및 Query Builder (2026-03-15).
지도/대시보드 검색 규칙 통일, canonical DTO 조립.
"""
from sqlalchemy import or_, and_, cast, String, func

from foms.persistence.main.models import Order
from foms.services.erp_display import normalize_manager_name
from foms.services.geocode_helpers import extract_address_from_order
from foms.services.geocode_retry import canonicalize_status
from foms.services.erp_shipment_settings import load_erp_shipment_settings
from foms.services.measurement_manager_colors import (
    build_measurement_manager_color_map,
    resolve_measurement_manager_color,
)
from foms.services.measurement_read_model import apply_measurement_dashboard_order_scope

__all__ = [
    "build_measurement_map_query",
    "build_measurement_snapshot",
    "build_as_incomplete_map_query",
    "apply_as_map_display_fields",
]

# AS 탭 요약 pill 라벨과 동일(as_dashboard_body.html) — 지도 카드/팝업 배지 표기 SSOT.
AS_MAP_BUCKET_LABELS = {
    'visit_confirmed': '방문 확정',
    'pending': '미결',
    'unassigned': '아직 미정',
    'paid_unconfirmed': '유상 미확정',
}
# 카드 배지는 1개만 표기 — 유상 미확정(방문 협의 전 선결 판정)이 최우선,
# 나머지 3키는 미완료 모집단을 상호배타로 3분할하므로 순서 무관하나 방어적으로 명시.
_AS_MAP_BUCKET_PRECEDENCE = ('paid_unconfirmed', 'pending', 'visit_confirmed', 'unassigned')


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


def _apply_map_manager_filter(query, manager):
    """담당자 부분 일치 필터 (Order.manager_name + ERP structured_data)."""
    if not (manager and manager.strip()):
        return query
    manager_term = f'%{manager.strip()}%'
    return query.filter(
        or_(
            Order.manager_name.ilike(manager_term),  # perf-ok: ix_orders_manager_name_trgm
            and_(
                Order.is_erp_order == True,
                cast(Order.structured_data, String).ilike(manager_term)  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )
    )


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

    # 자가실측 상태는 플래그 있는 주문만 포함. 지방주문(is_regional)도 실측 대시보드에 표시.
    if dashboard == 'measurement':
        query = apply_measurement_dashboard_order_scope(query)
    else:
        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )

    query = _apply_map_manager_filter(query, manager)

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


def build_as_incomplete_map_query(db, q, manager, bucket=None, avail_days=None,
                                  avail_time=None, limit=500):
    """AS 미완료 지도 주문 쿼리 — AS 탭 미완료 판정 SSOT를 그대로 공유한다.

    탭(`/erp/as?tab=incomplete`)과 1:1 일치가 목표: 날짜 필터 없음(미완료 전체),
    지방(is_regional) 주문 포함, `sales_delivery` 행 제외.

    Args:
        db: DB 세션
        q: 검색어
        manager: 담당자 필터 (부분 일치)
        bucket: 미완료 하위 버킷 키 (``AS_INCOMPLETE_BUCKET_KEYS`` 외 값은 무시)
        avail_days: 가능 요일 필터 — 'weekday'/'weekend'(무관 any 포함) 또는
            'unknown'(미기입만). 그 외 값은 무시.
        avail_time: 가능 시간대 필터 — 'am'/'pm'/'evening'(무관 any 포함). 그 외 무시.
        limit: 최대 주문 수

    Returns:
        SQLAlchemy query (아직 .all() 호출 전)
    """
    from foms.services.as_dashboard_helpers import (
        _as_availability_days_expr,
        _as_availability_time_expr,
    )
    from foms.services.as_dashboard_helpers import erp_as_scope_condition
    from foms.services.as_dashboard_read_model import (
        build_as_incomplete_bucket_conditions,
        build_as_tab_query_conditions,
    )

    dialect_name = ''
    try:
        bind = db.get_bind()
        dialect_name = getattr(getattr(bind, 'dialect', None), 'name', '') or ''
    except Exception:
        dialect_name = ''

    conditions = build_as_tab_query_conditions(dialect_name=dialect_name)
    query = db.query(Order).filter(Order.active_filter())
    # AS 탭 모집단과 동일한 선행 축소 (as_dashboard.py 목록 쿼리와 동형).
    # AS-AXIS-01: status 가 아니라 AS 축 투영을 본다 — 탭↔지도 건수 1:1 계약 유지.
    query = query.filter(erp_as_scope_condition())
    query = query.filter(conditions['incomplete_non_sales_condition'])
    query = _measurement_search_filter(query, q)
    query = _apply_map_manager_filter(query, manager)

    bucket_key = (bucket or '').strip()
    buckets = build_as_incomplete_bucket_conditions(
        incomplete_non_sales_condition=conditions['incomplete_non_sales_condition'],
        as_pending_true=conditions['as_pending_true'],
        as_visit_date_present=conditions['as_visit_date_present'],
        paid_unconfirmed_condition=conditions['paid_unconfirmed_condition'],
    )
    if bucket_key in buckets:
        query = query.filter(buckets[bucket_key])

    # 가능시간 필터 — '가능' 필터는 명시적 무관(any)을 포함하되 미기입('')은 제외
    # (미기입 제외 건수 고지는 호출자 몫 — services/orders/as_availability.py 참조)
    days_key = (avail_days or '').strip().lower()
    if days_key in ('weekday', 'weekend'):
        query = query.filter(
            _as_availability_days_expr(dialect_name=dialect_name).in_((days_key, 'any')))
    elif days_key == 'unknown':
        query = query.filter(_as_availability_days_expr(dialect_name=dialect_name) == '')
    time_key = (avail_time or '').strip().lower()
    if time_key in ('am', 'pm', 'evening'):
        query = query.filter(
            _as_availability_time_expr(dialect_name=dialect_name).in_((time_key, 'any')))

    return query.order_by(Order.id.desc()).limit(limit)


def _load_as_bucket_id_sets(db, order_ids):
    """4버킷 조건별 주문 id 집합 배치 조회 (버킷당 1쿼리 = 총 4쿼리, N+1 금지).

    AS 탭 pill과 같은 조건(build_as_incomplete_bucket_conditions SSOT)으로 판정한다.

    Args:
        db: DB 세션.
        order_ids: 판정 대상 주문 id 리스트(스냅샷에 실린 행들).

    Returns:
        {bucket_key: set[int]} — 키는 AS_MAP_BUCKET_LABELS와 동일.
    """
    from foms.services.as_dashboard_read_model import (
        build_as_incomplete_bucket_conditions,
        build_as_tab_query_conditions,
    )

    if not order_ids:
        return {}
    dialect_name = ''
    try:
        bind = db.get_bind()
        dialect_name = getattr(getattr(bind, 'dialect', None), 'name', '') or ''
    except Exception:
        dialect_name = ''
    conditions = build_as_tab_query_conditions(dialect_name=dialect_name)
    buckets = build_as_incomplete_bucket_conditions(
        incomplete_non_sales_condition=conditions['incomplete_non_sales_condition'],
        as_pending_true=conditions['as_pending_true'],
        as_visit_date_present=conditions['as_visit_date_present'],
        paid_unconfirmed_condition=conditions['paid_unconfirmed_condition'],
    )
    return {
        key: {row[0] for row in db.query(Order.id).filter(Order.id.in_(order_ids), cond).all()}
        for key, cond in buckets.items()
    }


def _truncate_preview(text):
    """개행을 공백으로 접고 60자 초과 시 말줄임."""
    text = str(text or '').replace('\n', ' ').strip()
    if len(text) > 60:
        return text[:60].rstrip() + '…'
    return text


def _as_content_preview(shipment):
    """AS 내용 HTML → 60자 plain text 요약.

    Args:
        shipment: structured_data['shipment'] dict(비 dict 허용).

    Returns:
        요약 문자열. 내용 없으면 빈 문자열.
    """
    from foms.services.as_content_safety import as_content_html_to_text

    raw = (shipment or {}).get('as_content') if isinstance(shipment, dict) else None
    return _truncate_preview(as_content_html_to_text(raw))


def _as_recent_log_preview(sd):
    """as_log 최신 기록 1건 → 60자 요약 (AS 대시보드 cell_recent_text와 동일 소스).

    접수 앵커·legacy 항목은 제외(as_content_preview가 담당) — 기록이 없으면 빈 문자열.

    Args:
        sd: 주문 structured_data dict.

    Returns:
        최신 기록 텍스트 요약 또는 ''.
    """
    from foms.services.as_content_safety import as_content_html_to_text
    from foms.services.orders.as_log import build_as_timeline_view

    # system 자동 기록(가능시간·방문일 확정 등)은 제외 — 지도 카드/팝업의 전용 행과
    # 중복되는 노이즈(스테이징 실증: 최근 기록 행 == 가능시간 행). 사람 기록만 추종.
    view = build_as_timeline_view(sd, recent_limit=8)
    recent = next((e for e in view['stream'] if e.get('type') != 'system'), None)
    if not recent:
        return ''
    # as_log 항목 text는 저장 시점에 이미 sanitize 통과(as_dashboard_display._timeline_cell_text 동형)
    return _truncate_preview(as_content_html_to_text(recent.get('text'), already_sanitized=True))


def apply_as_map_display_fields(snapshot, orders, db):
    """AS 지도 스냅샷의 orders/markers에 AS 표시 필드를 in-place 보강한다.

    measurement 지도 페이로드는 이 함수를 타지 않는다(as 모드 전용 — 호출자는
    foms/api/cs/as_map.py 한 곳). 클라이언트 as 분기 판정은 `as_bucket` 존재 여부.

    Args:
        snapshot: build_measurement_snapshot 결과 dict(orders/markers/summary).
        orders: 스냅샷 조립에 쓴 Order 객체 리스트(structured_data 원본 접근용).
        db: DB 세션(버킷 id-set 배치 조회용).

    Returns:
        None (snapshot 행 dict들을 직접 수정).
    """
    from foms.services.as_dashboard_display import (
        _as_visit_dday,
        as_billing_badge_kind,
        as_billing_state_text,
    )
    from foms.services.erp_display import get_today_kst
    from foms.services.orders.as_schedule_link import read_as_visit_date

    order_map = {o.id: o for o in orders}
    bucket_id_sets = _load_as_bucket_id_sets(db, list(order_map.keys()))
    today = get_today_kst()

    # 주문당 1회 계산(orders/markers에 같은 주문이 중복 등장 — 타임라인 파싱 이중 지불 방지)
    per_order = {}
    for oid, order in order_map.items():
        sd = getattr(order, 'structured_data', None)
        sd = sd if isinstance(sd, dict) else {}
        shipment = sd.get('shipment') if isinstance(sd.get('shipment'), dict) else {}
        bucket = next(
            (k for k in _AS_MAP_BUCKET_PRECEDENCE if oid in bucket_id_sets.get(k, ())),
            'unassigned',
        )
        visit_date = read_as_visit_date(sd)
        billing = shipment.get('as_billing')
        per_order[oid] = {
            'as_bucket': bucket,
            'as_bucket_label': AS_MAP_BUCKET_LABELS[bucket],
            'as_visit_date': visit_date,
            'as_visit_dday': _as_visit_dday(visit_date, today),
            'as_content_preview': _as_content_preview(shipment),
            'as_recent_log_preview': _as_recent_log_preview(sd),
            'as_billing_badge': as_billing_badge_kind(billing),
            'as_billing_text': as_billing_state_text(billing),
            'as_received_date': _format_date(getattr(order, 'as_received_date', None)),
        }

    empty = {
        'as_bucket': 'unassigned',
        'as_bucket_label': AS_MAP_BUCKET_LABELS['unassigned'],
        'as_visit_date': None, 'as_visit_dday': None,
        'as_content_preview': '', 'as_recent_log_preview': '',
        'as_billing_badge': None, 'as_billing_text': as_billing_state_text(None),
        'as_received_date': None,
    }
    for item in list(snapshot['orders']) + list(snapshot['markers']):
        item.update(per_order.get(item['id'], empty))


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
    """DB geocode_status를 success|pending|failed 3상태로 정규화.

    ``address_error``(주소가 조회되지 않는 건, GEO-FAILKIND-01)는 ``failed`` 로 접는다 —
    화면 배지·필터가 아는 값은 3개뿐이고, 사용자에게 필요한 안내도 같다("주소 오류").
    """
    raw = canonicalize_status(getattr(order, 'geocode_status', None))
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


def build_measurement_snapshot(orders, manager_filter=None, measurement_manager_options=None,
                               use_manager_colors=True):
    """
    주문 리스트에서 canonical DTO 조립 (목록 + 마커 + 요약).

    Args:
        orders: Order 객체 리스트 (self_measurement_four_checks_done 제외된 상태)
        manager_filter: 담당자 필터 (부분 일치, None이면 미적용)
        measurement_manager_options: 실측 담당자 설정 목록 (테스트/호출자 주입용)
        use_manager_colors: False면 담당자 팔레트색 미부여(source='default') —
            AS 지도처럼 마커를 상태색으로 칠하는 표면용(실측 담당자 설정과 무관한 모집단)

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

    if use_manager_colors:
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
    else:
        manager_color_map = {}

    from foms.services.orders.as_availability import as_availability_label, get_as_availability

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
        # AS 방문 가능시간(있을 때만 값) — AS 지도 필터·팝업용, 타 대시보드에선 None
        avail = get_as_availability(getattr(order, 'structured_data', None))
        avail_label = as_availability_label(avail)

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
            'as_availability': avail,
            'as_availability_label': avail_label,
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
                'as_availability': avail,
                'as_availability_label': avail_label,
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
