"""
ERP 실측 대시보드 페이지 (ERP-SLIM-6)
erp.py에서 분리: /erp/measurement
"""
from flask import Blueprint, render_template, request, redirect, url_for, g
from db import get_db
from models import Order, OrderScheduleDate
from apps.auth import login_required
import datetime
from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm import load_only, selectinload

from services.business_calendar import get_holidays_kr
from services.erp_permissions import can_edit_erp, build_mine_sql_filter
from services.erp_display import (
    _ensure_dict,
    _normalize_date_to_yyyymmdd,
    apply_erp_display_fields_to_orders,
    get_today_kst,
    normalize_manager_name,
    self_measurement_four_checks_done,
)
from services.erp_product_items import build_product_items_for_orders
from services.erp_shipment_settings import load_erp_shipment_settings

erp_measurement_dashboard_bp = Blueprint(
    'erp_measurement_dashboard', __name__, url_prefix='/erp'
)


def _erp_order_search_filter(query, q):
    """고객·담당자·시공자·주소 전체 검색 (Order 컬럼 + ERP Beta structured_data 텍스트)."""
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


def _append_unique_dates(target_dates, seen_dates, raw_value):
    if not raw_value:
        return
    for chunk in str(raw_value).split(','):
        normalized = _normalize_date_to_yyyymmdd(chunk.strip())
        if not normalized or normalized in seen_dates:
            continue
        seen_dates.add(normalized)
        target_dates.append(normalized)


def extract_all_measurement_dates(order):
    """주문에서 대표 실측일 + 항목별 실측일을 모두 추출.

    원칙:
    - 우선 schedule_dates read model을 읽는다.
    - stale/누락 데이터에 대비해 legacy 컬럼과 structured_data 원본도 합친다.
    """
    dates = []
    seen_dates = set()
    schedule_dates = getattr(order, 'schedule_dates', None)
    if schedule_dates is not None:
        for d in order.schedule_dates:
            if d.kind == 'measurement' and d.date:
                _append_unique_dates(dates, seen_dates, d.date)

    _append_unique_dates(dates, seen_dates, getattr(order, 'measurement_date', None))

    if getattr(order, 'is_erp_beta', False) and getattr(order, 'structured_data', None):
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        erp_date = (sd.get('schedule') or {}).get('measurement') or {}
        _append_unique_dates(dates, seen_dates, erp_date.get('date'))
        for it in sd.get('items') or []:
            if not isinstance(it, dict):
                continue
            _append_unique_dates(dates, seen_dates, it.get('measurement_date'))

    return dates


def _build_measurement_raw_match_filter(date_values):
    values = [str(v).strip() for v in date_values if str(v or '').strip()]
    if not values:
        return None

    conditions = []
    for value in values:
        conditions.append(Order.measurement_date.ilike(f'%{value}%'))
        conditions.append(Order.erp_measurement_date == value)
        conditions.append(
            and_(
                Order.is_erp_beta == True,
                cast(Order.structured_data, String).ilike(f'%{value}%')
            )
        )
    return or_(*conditions) if conditions else None


def _order_matches_measurement_window(order, selected_date='', date_from='', date_to=''):
    all_dates = extract_all_measurement_dates(order)
    if selected_date:
        return selected_date in all_dates
    if date_from and date_to:
        return any(date_from <= d <= date_to for d in all_dates)
    return bool(all_dates)


def _build_measurement_dates_for_display(order, selected_date='', date_from='', date_to=''):
    all_dates = extract_all_measurement_dates(order)
    if selected_date and selected_date in all_dates:
        return [selected_date] + [d for d in all_dates if d != selected_date]
    if date_from and date_to:
        matched = [d for d in all_dates if date_from <= d <= date_to]
        others = [d for d in all_dates if d not in matched]
        return matched + others
    return all_dates


@erp_measurement_dashboard_bp.route('/measurement')
@login_required
def erp_measurement_dashboard():
    """ERP Beta - 실측 대시보드 (structured_data 기반, MVP는 Order 컬럼 연동으로 운용)"""
    db = get_db()
    today_kst = get_today_kst()
    today_date = today_kst.strftime('%Y-%m-%d')
    search_q = (request.args.get('q') or request.args.get('manager') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    req_date = (request.args.get('date') or '').strip()
    open_map = request.args.get('open_map') == '1'

    # Phase H: 대시보드 운영 화면은 최근 활성 데이터만 조회 (과거 완료건 제외)
    base_query = db.query(Order).filter(Order.dashboard_active_filter(days=60))
    base_query = _erp_order_search_filter(base_query, search_q)
    # 자가실측·지방실측 제외(진짜 실측 필요한 것만 집계), 단 자가실측 주문은 실측 대시보드에 표시 후 4체크 완료 시 시공으로 이관
    base_query = base_query.filter(
        or_(
            and_(
                Order.is_regional != True,
                ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
            ),
            Order.is_self_measurement == True
        )
    )
    query = base_query

    use_range = bool(date_from and date_to)
    if use_range:
        try:
            datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            use_range = False
    use_single_day = bool(req_date) and not use_range
    if use_single_day:
        try:
            datetime.datetime.strptime(req_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            use_single_day = False
    # 기본 진입은 당일 주문만 로드한다. 전체 목록 로드는 대시보드 기본 동작에서 제외.
    if not use_range and not use_single_day:
        req_date = today_date
        use_single_day = True
    selected_date = req_date

    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)
    range_start_str = range_start.strftime('%Y-%m-%d')
    range_end_str = range_end.strftime('%Y-%m-%d')

    if use_range or use_single_day:
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(OrderScheduleDate.kind == 'measurement')
        
        if use_range:
            query = query.filter(OrderScheduleDate.date >= date_from, OrderScheduleDate.date <= date_to)
        elif use_single_day:
            query = query.filter(OrderScheduleDate.date == selected_date)
            
        # Due to one-to-many join, distinct is required to prevent duplicate order rows
        query = query.distinct()

    current_user = getattr(g, 'current_user', None)
    mine_filter_active = request.args.get('mine') == '1' and current_user

    # mine 필터를 SQL WHERE로 적용 (Python 루프 대신)
    if mine_filter_active:
        mine_conds = build_mine_sql_filter(current_user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))

    all_rows = query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(500).all()

    for r in all_rows:
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]

    panel_query = base_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
    panel_query = panel_query.filter(
        OrderScheduleDate.kind == 'measurement',
        OrderScheduleDate.date >= range_start_str,
        OrderScheduleDate.date <= range_end_str,
    ).distinct()
    if mine_filter_active:
        p_mine_conds = build_mine_sql_filter(current_user)
        if p_mine_conds:
            panel_query = panel_query.filter(or_(*p_mine_conds))
    panel_orders = panel_query.options(
        load_only(
            Order.id, Order.measurement_date, Order.structured_data, 
            Order.is_self_measurement, Order.is_erp_beta, Order.status,
            Order.measurement_completed, Order.regional_sales_order_upload,
            Order.regional_blueprint_sent, Order.regional_order_upload
        ),
        selectinload(Order.schedule_dates)
    ).order_by(Order.id.desc()).all()
        
    for o in panel_orders:
        o.structured_data = _ensure_dict(o.structured_data)  # type: ignore[assignment]

    panel_range_values = []
    current = range_start
    while current <= range_end:
        panel_range_values.append(current.strftime('%Y-%m-%d'))
        current += datetime.timedelta(days=1)

    panel_fallback_filter = _build_measurement_raw_match_filter(panel_range_values)
    if panel_fallback_filter is not None:
        panel_fallback_query = base_query.filter(panel_fallback_filter)
        if mine_filter_active:
            p_mine_conds = build_mine_sql_filter(current_user)
            if p_mine_conds:
                panel_fallback_query = panel_fallback_query.filter(or_(*p_mine_conds))
        panel_fallback_orders = panel_fallback_query.options(
            load_only(
                Order.id, Order.measurement_date, Order.structured_data,
                Order.is_self_measurement, Order.is_erp_beta, Order.status,
                Order.measurement_completed, Order.regional_sales_order_upload,
                Order.regional_blueprint_sent, Order.regional_order_upload
            ),
            selectinload(Order.schedule_dates)
        ).order_by(Order.id.desc()).limit(1500).all()
        panel_order_ids = {o.id for o in panel_orders}
        for order in panel_fallback_orders:
            order.structured_data = _ensure_dict(order.structured_data)  # type: ignore[assignment]
            if order.id in panel_order_ids:
                continue
            if not any(range_start_str <= d <= range_end_str for d in extract_all_measurement_dates(order)):
                continue
            panel_orders.append(order)
            panel_order_ids.add(order.id)

    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= get_holidays_kr(y)

    measurement_counts = {}
    for order in panel_orders:
        if self_measurement_four_checks_done(order):
            continue
        all_dates = extract_all_measurement_dates(order)
        for date_value in all_dates:
            try:
                d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
            except Exception:
                continue
            if d < range_start or d > range_end:
                continue
            key = d.strftime('%Y-%m-%d')
            measurement_counts[key] = measurement_counts.get(key, 0) + 1

    measurement_panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        measurement_panel_dates.append({
            'date': date_str,
            'count': measurement_counts.get(date_str, 0),
            'weekday': current.weekday(),
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_selected': date_str == selected_date
        })
        current += datetime.timedelta(days=1)

    rows = []
    for order in all_rows:
        if self_measurement_four_checks_done(order):
            continue
        if use_single_day and selected_date:
            # SQL WHERE OrderScheduleDate.date == selected_date 로 이미 필터됨
            # extract_all_measurement_dates 재호출은 불필요 중복 — 직접 포함
            rows.append(order)
        elif use_range and date_from and date_to:
            # SQL WHERE OrderScheduleDate.date BETWEEN date_from AND date_to 로 이미 필터됨
            # Python 날짜 재검증은 불필요 중복
            rows.append(order)
        else:
            rows.append(order)

    row_match_values = []
    if use_single_day and selected_date:
        row_match_values = [selected_date]
    elif use_range and date_from and date_to:
        start_dt = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
        end_dt = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
        current_dt = start_dt
        while current_dt <= end_dt and len(row_match_values) < 93:
            row_match_values.append(current_dt.strftime('%Y-%m-%d'))
            current_dt += datetime.timedelta(days=1)

    row_fallback_filter = _build_measurement_raw_match_filter(row_match_values)
    if row_fallback_filter is not None:
        row_fallback_query = base_query.filter(row_fallback_filter)
        if mine_filter_active:
            r_mine_conds = build_mine_sql_filter(current_user)
            if r_mine_conds:
                row_fallback_query = row_fallback_query.filter(or_(*r_mine_conds))
        fallback_rows = row_fallback_query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(1500).all()
        existing_row_ids = {o.id for o in rows}
        for order in fallback_rows:
            order.structured_data = _ensure_dict(order.structured_data)  # type: ignore[assignment]
            if order.id in existing_row_ids:
                continue
            if self_measurement_four_checks_done(order):
                continue
            if not _order_matches_measurement_window(order, selected_date=selected_date, date_from=date_from, date_to=date_to):
                continue
            rows.append(order)
            existing_row_ids.add(order.id)

    rows = rows[:300]
    for row in rows:
        row.measurement_dates_display = _build_measurement_dates_for_display(
            row,
            selected_date=selected_date if use_single_day else '',
            date_from=date_from if use_range else '',
            date_to=date_to if use_range else '',
        )
    apply_erp_display_fields_to_orders(rows)
    build_product_items_for_orders(db, rows)

    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = normalize_manager_name(
                (sd.get('parties') or {}).get('manager'),
                order.manager_name,
            )
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    _settings = load_erp_shipment_settings()
    measurement_manager_options = []
    measurement_manager_seen = set()
    for mm in (_settings.get('measurement_manager') or []):
        if isinstance(mm, dict):
            name = str(mm.get('name') or '').strip()
            sort_order = mm.get('sort_order', 999)
        else:
            name = str(mm or '').strip()
            sort_order = 999
        if not name:
            continue
        key = name.lower()
        if key in measurement_manager_seen:
            continue
        measurement_manager_seen.add(key)
        measurement_manager_options.append({
            'name': name,
            'sort_order': sort_order,
        })

    _mm_sort_map = {
        option['name'].strip().lower(): option.get('sort_order', 999)
        for option in measurement_manager_options
    }

    def _manager_sort_key(order):
        name = get_manager_name_for_sort(order)
        key = (name or '').strip().lower()
        sort_order = _mm_sort_map.get(key, 999)
        return (sort_order, name or 'ZZZ', order.id)

    rows.sort(key=_manager_sort_key)

    if open_map:
        # 실측 대시보드 지도는 항상 실측 주문만 표시한다.
        return redirect(url_for('erp_map.map_view', date=selected_date, status='ALL', dashboard='measurement', q=search_q))

    return render_template(
        'erp_measurement_dashboard.html',
        selected_date=selected_date,
        search_q=search_q,
        date_from=date_from,
        date_to=date_to,
        use_date_range=use_range,
        rows=rows,
        measurement_panel_dates=measurement_panel_dates,
        measurement_manager_options=measurement_manager_options,
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=mine_filter_active,
    )
