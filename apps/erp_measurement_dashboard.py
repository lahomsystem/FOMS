"""
ERP 실측 대시보드 페이지 (ERP-SLIM-6)
erp.py에서 분리: /erp/measurement
"""
from flask import Blueprint, render_template, request, session, redirect, url_for
from db import get_db
from models import Order
from apps.auth import login_required, get_user_by_id
import datetime
import json
import os
from sqlalchemy import or_, and_, func, cast, String

from services.erp_permissions import can_edit_erp
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst, self_measurement_four_checks_done
from sqlalchemy.orm import load_only
from services.erp_shipment_settings import is_order_mine_for_user
from services.erp_product_items import build_product_items_for_order, build_product_items_for_orders

erp_measurement_dashboard_bp = Blueprint(
    'erp_measurement_dashboard', __name__, url_prefix='/erp'
)


def _load_holidays_for_year(year):
    """해당 연도 휴일 집합 반환 (실측 패널용)."""
    try:
        file_path = os.path.join('data', f'holidays_kr_{year}.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('dates', []))
    except Exception:
        return set()


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


def extract_all_measurement_dates(order):
    """주문에서 대표 실측일 + 항목별 실측일을 모두 추출 (schedule_dates DB 기반)"""
    dates = set()
    if getattr(order, 'schedule_dates', None) is not None:
        for d in order.schedule_dates:
            if d.kind == 'measurement' and d.date:
                dates.add(d.date)
    else:
        # Fallback to legacy behavior if not loaded (should not happen with selectinload)
        if getattr(order, 'measurement_date', None):
            for d in str(order.measurement_date).split(','):
                if d.strip():
                    dates.add(d.strip())
        if getattr(order, 'is_erp_beta', False) and getattr(order, 'structured_data', None):
            sd = order.structured_data if isinstance(order.structured_data, dict) else {}
            erp_date = (sd.get('schedule') or {}).get('measurement') or {}
            if erp_date.get('date'):
                for d in str(erp_date['date']).split(','):
                    if d.strip():
                        dates.add(d.strip())
            for it in sd.get('items') or []:
                if not isinstance(it, dict):
                    continue
                date_val = it.get('measurement_date')
                if date_val:
                    for d in str(date_val).split(','):
                        if d.strip():
                            dates.add(d.strip())
    return dates


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

    base_query = db.query(Order).filter(Order.active_filter())
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

    from models import OrderScheduleDate
    if use_range or use_single_day:
        query = query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        query = query.filter(OrderScheduleDate.kind == 'measurement')
        
        if use_range:
            query = query.filter(OrderScheduleDate.date >= date_from, OrderScheduleDate.date <= date_to)
        elif use_single_day:
            query = query.filter(OrderScheduleDate.date == selected_date)
            
        # Due to one-to-many join, distinct is required to prevent duplicate order rows
        query = query.distinct()

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    mine_filter_active = request.args.get('mine') == '1' and current_user

    from sqlalchemy.orm import selectinload
    all_rows = query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(500).all()
    if mine_filter_active:
        all_rows = [r for r in all_rows if is_order_mine_for_user(r, current_user)]

    for r in all_rows:
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]
    apply_erp_display_fields_to_orders(all_rows)

    panel_query = base_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
    panel_query = panel_query.filter(
        OrderScheduleDate.kind == 'measurement',
        OrderScheduleDate.date >= range_start_str,
        OrderScheduleDate.date <= range_end_str,
    ).distinct()
    panel_orders = panel_query.options(
        load_only(
            Order.id, Order.measurement_date, Order.structured_data, 
            Order.is_self_measurement, Order.is_erp_beta, Order.status,
            Order.measurement_completed, Order.regional_sales_order_upload,
            Order.regional_blueprint_sent, Order.regional_order_upload
        ),
        selectinload(Order.schedule_dates)
    ).order_by(Order.id.desc()).all()
    if mine_filter_active:
        panel_orders = [o for o in panel_orders if is_order_mine_for_user(o, current_user)]
        
    for o in panel_orders:
        o.structured_data = _ensure_dict(o.structured_data)  # type: ignore[assignment]

    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= _load_holidays_for_year(y)

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
            should_include = selected_date in extract_all_measurement_dates(order)
            if should_include:
                rows.append(order)
        elif use_range and date_from and date_to:
            try:
                d_from = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
                d_to = datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                d_from = d_to = None
            if d_from is not None and d_to is not None:
                all_meas = extract_all_measurement_dates(order)
                for d_str in all_meas:
                    try:
                        d = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
                        if d_from <= d <= d_to:
                            rows.append(order)
                            break
                    except (ValueError, TypeError):
                        pass
            else:
                rows.append(order)
        else:
            rows.append(order)

    rows = rows[:300]
    apply_erp_display_fields_to_orders(rows)
    build_product_items_for_orders(db, rows)

    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    rows.sort(key=lambda o: (get_manager_name_for_sort(o) or 'ZZZ', o.id))

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
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=mine_filter_active,
    )
