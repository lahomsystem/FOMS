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
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from services.erp_shipment_settings import is_order_mine_for_user


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
    selected_date = (request.args.get('date') or '').strip()
    open_map = request.args.get('open_map') == '1'

    # 패널 표시용 기준일 (날짜 범위/단일일 없으면 오늘; 전체 기간이면 쿼리만 날짜 미적용)
    if not selected_date:
        selected_date = date_from or today_date

    base_query = db.query(Order).filter(Order.status != 'DELETED')
    base_query = _erp_order_search_filter(base_query, search_q)
    query = base_query

    use_range = bool(date_from and date_to)
    has_explicit_date = bool(request.args.get('date', '').strip())
    use_single_day = bool(has_explicit_date and selected_date and not use_range)

    if use_range:
        try:
            datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            datetime.datetime.strptime(date_to, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            use_range = False
            use_single_day = True
            selected_date = today_date

    if use_range:
        date_conditions = [
            and_(Order.measurement_date >= date_from, Order.measurement_date <= date_to),
            and_(Order.received_date >= date_from, Order.received_date <= date_to),
            and_(Order.scheduled_date >= date_from, Order.scheduled_date <= date_to),
            and_(Order.completion_date >= date_from, Order.completion_date <= date_to),
            and_(Order.as_received_date >= date_from, Order.as_received_date <= date_to),
            and_(Order.as_completed_date >= date_from, Order.as_completed_date <= date_to),
        ]
        date_conditions.append(
            and_(
                Order.is_erp_beta == True,
                func.cast(Order.received_date, String) >= date_from,
                func.cast(Order.received_date, String) <= date_to
            )
        )
        query = query.filter(or_(*date_conditions))
    elif use_single_day:
        try:
            filter_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
            date_start = filter_date - datetime.timedelta(days=30)
            date_end = filter_date + datetime.timedelta(days=30)
        except Exception:
            date_start = None
            date_end = None

        date_conditions = [
            Order.measurement_date == selected_date,
            Order.received_date == selected_date,
            Order.scheduled_date == selected_date,
            Order.completion_date == selected_date,
            Order.as_received_date == selected_date,
            Order.as_completed_date == selected_date
        ]
        if date_start and date_end:
            date_start_str = date_start.strftime('%Y-%m-%d')
            date_end_str = date_end.strftime('%Y-%m-%d')
            date_conditions.append(
                and_(
                    Order.is_erp_beta == True,
                    func.cast(Order.received_date, String) >= date_start_str,
                    func.cast(Order.received_date, String) <= date_end_str
                )
            )
        else:
            date_conditions.append(Order.is_erp_beta == True)
        query = query.filter(or_(*date_conditions))

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    mine_filter_active = request.args.get('mine') == '1' and current_user

    all_rows = query.order_by(Order.id.desc()).limit(500).all()
    if mine_filter_active:
        all_rows = [r for r in all_rows if is_order_mine_for_user(r, current_user)]

    for r in all_rows:
        r.structured_data = _ensure_dict(r.structured_data)
    apply_erp_display_fields_to_orders(all_rows)

    panel_orders = base_query.order_by(Order.id.desc()).limit(1500).all()
    if mine_filter_active:
        panel_orders = [o for o in panel_orders if is_order_mine_for_user(o, current_user)]

    try:
        base_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
    except Exception:
        base_date = today_kst

    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)
    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= _load_holidays_for_year(y)

    measurement_counts = {}
    for order in panel_orders:
        date_value = None
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
            if erp_measurement_date:
                date_value = str(erp_measurement_date)
        if not date_value and order.measurement_date:
            date_value = str(order.measurement_date)
        if not date_value:
            continue
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
        if use_single_day and selected_date:
            should_include = False
            if order.is_erp_beta and order.structured_data:
                sd = order.structured_data
                erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if erp_measurement_date and str(erp_measurement_date) == selected_date:
                    should_include = True
                elif order.measurement_date and str(order.measurement_date) == selected_date:
                    should_include = True
            else:
                if order.measurement_date and str(order.measurement_date) == selected_date:
                    should_include = True
            if should_include:
                rows.append(order)
        else:
            rows.append(order)

    rows = rows[:300]
    apply_erp_display_fields_to_orders(rows)

    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    rows.sort(key=lambda o: (get_manager_name_for_sort(o) or 'ZZZ', o.id))

    if open_map:
        return redirect(url_for('erp_map.map_view', date=selected_date, status='MEASURED'))

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
