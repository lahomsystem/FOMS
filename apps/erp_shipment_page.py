"""
ERP 출고 대시보드 페이지 (ERP-SLIM-7)
erp.py에서 분리: /erp/shipment
"""
from flask import Blueprint, render_template, request, session, redirect, url_for
from db import get_db
from models import Order
from apps.auth import login_required, get_user_by_id
import datetime
import json
import os
from sqlalchemy import or_, and_, cast, String

from services.erp_permissions import can_edit_erp
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from services.erp_template_filters import item_spec_w300_value
from services.erp_shipment_settings import (
    load_erp_shipment_settings,
    normalize_erp_shipment_workers,
    is_order_mine_for_user,
)


erp_shipment_page_bp = Blueprint(
    'erp_shipment_page', __name__, url_prefix='/erp'
)


def _load_holidays_for_year(year):
    """해당 연도 휴일 집합 반환."""
    try:
        file_path = os.path.join('data', f'holidays_kr_{year}.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('dates', []))
    except Exception:
        return set()


def _normalize_worker_name(name):
    return str(name or '').strip().lower()


def _get_order_construction_date(order):
    """출고 대시보드용 시공일 결정 로직."""
    date_value = None
    if order.status in ('AS_RECEIVED', 'AS_COMPLETED'):
        if order.scheduled_date:
            date_value = str(order.scheduled_date)
        elif order.as_received_date and str(order.as_received_date) != '':
            date_value = str(order.as_received_date)
        elif not date_value and order.as_completed_date:
            date_value = str(order.as_completed_date)

    if not date_value and order.is_erp_beta and order.structured_data:
        sd = order.structured_data
        cons = (sd.get('schedule') or {}).get('construction') or {}
        cons_date = cons.get('date')
        if cons_date:
            date_value = str(cons_date)

    # Legacy(기존 주문) 또는 Beta Fallback: scheduled_date가 있으면 사용
    if not date_value and order.scheduled_date:
        date_value = str(order.scheduled_date)
    return date_value


def _get_order_spec_units(order):
    """주문의 spec_w300 단위 합산. 항목별 W합/300 (spec_rows 있으면 W 합산 후 /300)."""
    if not order.is_erp_beta or not order.structured_data:
        return 0.0
    sd = order.structured_data or {}
    items = sd.get('items') or []
    total = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        total += item_spec_w300_value(it)
    return total


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


@erp_shipment_page_bp.route('/shipment')
@login_required
def erp_shipment_dashboard():
    """ERP Beta - 출고 대시보드 (날짜별 시공 건수, AS 포함, 출고일지 스타일)"""
    db = get_db()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    today_kst = get_today_kst()
    today_date = today_kst.strftime('%Y-%m-%d')
    today_dt = today_kst
    search_q = (request.args.get('q') or request.args.get('manager') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    req_date = request.args.get('date') or ''

    is_construction = current_user and getattr(current_user, 'team', None) == 'CONSTRUCTION'
    mine_only = is_construction or (request.args.get('mine') == '1')

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
    if not use_range and not use_single_day:
        req_date = today_date
    selected_date = req_date

    base_query = db.query(Order).filter(Order.status != 'DELETED')
    base_query = _erp_order_search_filter(base_query, search_q)

    panel_orders = base_query.filter(
        or_(
            Order.is_erp_beta == True,
            Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']),
            and_(
                Order.is_erp_beta == False,
                Order.scheduled_date != None,
                Order.scheduled_date != ''
            )
        )
    ).order_by(Order.id.desc()).limit(1500).all()
    # 시공팀 또는 mine=1일 때만 목록/패널을 담당 주문으로 제한 (의도적 이중 필터: panel_orders + 아래 rows)
    if mine_only and current_user:
        panel_orders = [o for o in panel_orders if is_order_mine_for_user(o, current_user)]

    settings = load_erp_shipment_settings()
    worker_settings = normalize_erp_shipment_workers(settings.get('construction_workers', []))
    worker_name_map = {_normalize_worker_name(w['name']): w for w in worker_settings if w.get('name')}

    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)
    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= _load_holidays_for_year(y)

    construction_counts = {}
    assigned_workers_by_date = {}
    spec_units_by_date = {}
    for order in panel_orders:
        date_value = _get_order_construction_date(order)
        if not date_value:
            continue
        try:
            d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
        except Exception:
            continue
        if d < range_start or d > range_end:
            continue
        key = d.strftime('%Y-%m-%d')
        construction_counts[key] = construction_counts.get(key, 0) + 1

        shipment = {}
        if order.structured_data and isinstance(order.structured_data, dict):  # type: ignore
            shipment = (order.structured_data.get('shipment') or {})
        workers = shipment.get('construction_workers') or []
        for w in workers:
            name_key = _normalize_worker_name(w)
            if not name_key:
                continue
            if name_key in worker_name_map:
                assigned_workers_by_date.setdefault(key, set()).add(name_key)

        spec_units_by_date[key] = spec_units_by_date.get(key, 0.0) + _get_order_spec_units(order)

    construction_panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        construction_panel_dates.append({
            'date': date_str,
            'count': construction_counts.get(date_str, 0),
            'weekday': current.weekday(),
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_selected': date_str == selected_date
        })
        current += datetime.timedelta(days=1)

    remaining_panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        available_workers = []
        for w in worker_settings:
            if date_str in (w.get('off_dates') or []):
                continue
            available_workers.append(w)
        base_worker_count = len(available_workers)
        base_capacity = sum((w.get('capacity') or 0) for w in available_workers)
        assigned_names = assigned_workers_by_date.get(date_str, set())
        assigned_count = 0
        for w in available_workers:
            if _normalize_worker_name(w.get('name')) in assigned_names:
                assigned_count += 1
        remaining_workers = max(base_worker_count - assigned_count, 0)
        used_capacity = spec_units_by_date.get(date_str, 0.0)
        remaining_capacity = max(base_capacity - used_capacity, 0)
        remaining_panel_dates.append({
            'date': date_str,
            'remaining_capacity': round(remaining_capacity, 1),
            'remaining_workers': remaining_workers,
            'total_capacity': round(base_capacity, 1),
            'total_workers': base_worker_count,
            'used_capacity': round(used_capacity, 1),
            'assigned_workers': assigned_count,
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_selected': date_str == selected_date,
            'alert_capacity': remaining_capacity <= 40,
            'alert_workers': remaining_workers <= 3
        })
        current += datetime.timedelta(days=1)

    # SQL 레벨에서 날짜 필터링 (최적화 + Limit으로 인한 누락 방지)
    if use_range:
        all_candidates = base_query.filter(
            or_(
                Order.is_erp_beta == True,
                Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']),
                and_(
                    Order.is_erp_beta == False,
                    Order.scheduled_date != None,
                    Order.scheduled_date != ''
                )
            )
        ).order_by(Order.id.desc()).limit(1500).all()
        rows = []
        for order in all_candidates:
            date_value = _get_order_construction_date(order)
            if not date_value:
                continue
            if date_from <= date_value <= date_to:
                rows.append(order)
    elif use_single_day:
        date_keyword = f'"{selected_date}"'
        all_candidates = base_query.filter(
            or_(
                and_(
                    Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']),
                    or_(
                        Order.scheduled_date == selected_date,
                        Order.as_received_date == selected_date,
                        Order.as_completed_date == selected_date
                    )
                ),
                and_(
                    Order.is_erp_beta == False,
                    Order.status.notin_(['AS_RECEIVED', 'AS_COMPLETED']),
                    Order.scheduled_date == selected_date
                ),
                and_(
                    Order.is_erp_beta == True,
                    or_(
                        Order.scheduled_date == selected_date,
                        cast(Order.structured_data, String).like(f'%{date_keyword}%')
                    )
                )
            )
        ).order_by(Order.id.desc()).all()
        rows = []
        for order in all_candidates:
            match = False
            if order.status in ('AS_RECEIVED', 'AS_COMPLETED'):
                if (order.scheduled_date and str(order.scheduled_date) == selected_date) or \
                   (order.as_received_date and str(order.as_received_date) == selected_date) or \
                   (order.as_completed_date and str(order.as_completed_date) == selected_date):  # type: ignore
                    match = True
            if not match and order.is_erp_beta:  # type: ignore
                sd = order.structured_data or {}
                cons = (sd.get('schedule') or {}).get('construction') or {}
                if cons.get('date') and str(cons.get('date')) == selected_date:
                    match = True
                if not match and order.scheduled_date and str(order.scheduled_date) == selected_date:  # type: ignore
                    match = True
            if not match and not order.is_erp_beta and order.status not in ('AS_RECEIVED', 'AS_COMPLETED'):  # type: ignore
                if order.scheduled_date and str(order.scheduled_date) == selected_date:  # type: ignore
                    match = True
            if match:
                rows.append(order)
    else:
        # 전체 기간: 날짜 필터 없음 (검색어만)
        all_candidates = base_query.filter(
            or_(
                Order.is_erp_beta == True,
                Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']),
                and_(
                    Order.is_erp_beta == False,
                    Order.scheduled_date != None,
                    Order.scheduled_date != ''
                )
            )
        ).order_by(Order.id.desc()).limit(500).all()
        rows = all_candidates

    # 시공팀 또는 mine=1일 때만 당일 목록(rows)도 담당 주문으로 제한
    if mine_only and current_user:
        rows = [r for r in rows if is_order_mine_for_user(r, current_user)]
    rows = rows[:300]

    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)
        sd = r.structured_data

        r.is_production_approved = False
        quests = sd.get('quests') or []
        production_quest = next((q for q in quests if q.get('stage') in ('PRODUCTION', '생산')), None)

        if production_quest:
            quest_status = production_quest.get('status', 'OPEN')
            if quest_status == 'COMPLETED':
                r.is_production_approved = True
            else:
                team_approvals = production_quest.get('team_approvals') or {}
                required_teams = production_quest.get('required_approvals') or []
                if required_teams:
                    all_approved = all(
                        (team_approvals.get(team, {}).get('approved') if isinstance(team_approvals.get(team), dict) else team_approvals.get(team))
                        for team in required_teams
                    )
                    r.is_production_approved = all_approved

    apply_erp_display_fields_to_orders(rows)

    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    def get_construction_worker_key_for_sort(order):
        """시공자별 그룹·정렬용: 첫 번째 유효한 시공자 또는 빈 문자열."""
        if not order.is_erp_beta or not order.structured_data:
            return ''
        shipment = (order.structured_data.get('shipment') or {})
        workers = shipment.get('construction_workers') or []
        for w in workers:
            w_str = str(w).strip() if w else ''
            if w_str:
                return w_str
        return ''

    def is_as_order(order):
        return order.status in ('AS_RECEIVED', 'AS_COMPLETED')

    rows.sort(key=lambda o: (
        1 if is_as_order(o) else 0,
        get_construction_worker_key_for_sort(o) or 'ZZZ',
        get_manager_name_for_sort(o) or 'ZZZ',
        o.id
    ))

    return render_template(
        'erp_shipment_dashboard.html',
        selected_date=selected_date,
        search_q=search_q,
        date_from=date_from,
        date_to=date_to,
        use_date_range=use_range,
        rows=rows,
        construction_panel_dates=construction_panel_dates,
        remaining_panel_dates=remaining_panel_dates,
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=mine_only,
        is_construction_team=is_construction,
    )
