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
from sqlalchemy import or_, and_, func, String

from services.erp_permissions import can_edit_erp
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders


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


@erp_measurement_dashboard_bp.route('/measurement')
@login_required
def erp_measurement_dashboard():
    """ERP Beta - 실측 대시보드 (structured_data 기반, MVP는 Order 컬럼 연동으로 운용)"""
    db = get_db()
    selected_date = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    manager_filter = (request.args.get('manager') or '').strip()
    open_map = request.args.get('open_map') == '1'

    base_query = db.query(Order).filter(Order.status != 'DELETED')

    if manager_filter:
        base_query = base_query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    query = base_query

    # 날짜 필터: ERP Beta 주문은 Order.measurement_date가 null일 수 있으므로
    if selected_date:
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

    all_rows = query.order_by(Order.id.desc()).limit(500).all()

    for r in all_rows:
        r.structured_data = _ensure_dict(r.structured_data)
    apply_erp_display_fields_to_orders(all_rows)

    panel_orders = base_query.order_by(Order.id.desc()).limit(1500).all()

    try:
        base_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
    except Exception:
        base_date = datetime.date.today()

    today_only = datetime.date.today()
    range_start = today_only
    range_end = today_only + datetime.timedelta(days=14)
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
        if selected_date:
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

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_measurement_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        measurement_panel_dates=measurement_panel_dates,
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
    )
