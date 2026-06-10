"""ERP 출고 대시보드 (ERP-SLIM-7; canonical, SFC-B11B). /erp/shipment."""
import time
from flask import Blueprint, make_response, render_template, request, redirect, url_for, g
from db import get_db
from models import Order
from foms.web.auth import login_required
import datetime
import hashlib
import json
from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only
from foms.services.common.business_calendar import get_holidays_kr
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_template_filters import item_spec_w300_value
from foms.services.erp_shipment_settings import (
    load_erp_shipment_settings,
    normalize_erp_shipment_workers,
    is_order_mine_for_user,
)
from foms.services.as_content_safety import as_content_html_to_text
from foms.services.common.dashboard_cache import (
    TTL_PANEL_ROWS,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.common.erp_shell_http import (
    apply_erp_shell_fragment_headers,
    wants_erp_shell_tab_body,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.feature_flags import is_enabled_for_user
from foms.services.request_utils import get_search_query_arg
from foms.services.erp_dashboard_search import (
    SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS,
    erp_order_dashboard_search_predicate,
)
from foms.services.erp_mobile_order_display import build_mobile_queue_order_row
from foms.api.shipment.recommendations import SHREC_SOURCE

# 실행 계획 §3.1.1 shipment — read-model slices:
# - ``panel_aggregates``: construction_counts / assigned_workers / spec_units (JSON)
# - ``shipment_panel_derived_template_payloads``: 상단 패널 stat 카드 리스트 2종 (JSON)
# - 패널에서 파생되는 테이블 rows는 ORM 객체(§3.1.2) — ``panel_orders`` 집합은 aggregates 키의 panel_order_ids에 반영

AS_SHIPMENT_STATUSES = ('AS', 'AS_RECEIVED', 'AS_COMPLETED')


erp_shipment_page_bp = Blueprint(
    'erp_shipment_page', __name__, url_prefix='/erp'
)


def _normalize_worker_name(name):
    return str(name or '').strip().lower()


def _shipment_user_visibility_fingerprint(current_user) -> dict:
    """출고 대시보드 캐시 키용 사용자 식별."""
    if not current_user:
        return {"user_id": None, "role": None, "username": None, "team": None}
    return {
        "user_id": getattr(current_user, "id", None),
        "role": getattr(current_user, "role", None),
        "username": getattr(current_user, "username", None),
        "team": getattr(current_user, "team", None),
    }


def _get_order_construction_date(order):
    """출고 대시보드용 시공일 결정 로직."""
    date_value = None
    if order.is_erp_order and order.structured_data:
        sd = order.structured_data
        cons = (sd.get('schedule') or {}).get('construction') or {}
        cons_date = cons.get('date')
        if cons_date:
            date_value = str(cons_date)

    # Legacy(기존 주문) 또는 Beta Fallback: scheduled_date가 있으면 사용
    if not date_value and order.scheduled_date:
        date_value = str(order.scheduled_date)
    return date_value


def is_as_order(order):
    return getattr(order, 'status', None) in AS_SHIPMENT_STATUSES


def extract_as_visit_dates(order):
    dates = set()
    if getattr(order, 'schedule_dates', None) is not None:
        for d in order.schedule_dates:
            if d.kind == 'as_visit' and d.date:
                dates.add(str(d.date))
        if dates:
            return dates

    structured_data = getattr(order, 'structured_data', None)
    if isinstance(structured_data, dict):
        schedule = structured_data.get('schedule') or {}
        visit = (schedule.get('as_visit') or {}).get('date') or ''
        for d in str(visit).split(','):
            if d.strip():
                dates.add(d.strip())
    return dates


def extract_dashboard_target_dates(order):
    if is_as_order(order):
        dates = extract_as_visit_dates(order)
        dates.update(extract_all_construction_dates(order))
        return dates
    return extract_all_construction_dates(order)


def extract_all_construction_dates(order):
    """주문에서 대표 시공일 + 항목별 시공일을 모두 추출 (schedule_dates DB 기반)."""
    dates = set()
    if getattr(order, 'schedule_dates', None) is not None:
        for d in order.schedule_dates:
            if d.kind == 'construction' and d.date:
                dates.add(d.date)
    else:
        # Fallback to legacy behavior if not loaded
        base_date = _get_order_construction_date(order)
        if base_date:
            for d in str(base_date).split(','):
                if d.strip():
                    dates.add(d.strip())
        if is_erp_order_record(order) and getattr(order, 'structured_data', None):
            sd = order.structured_data if isinstance(order.structured_data, dict) else {}
            for it in sd.get('items') or []:
                if not isinstance(it, dict):
                    continue
                date_val = it.get('construction_date')
                if date_val:
                    for d in str(date_val).split(','):
                        if d.strip():
                            dates.add(d.strip())
    return dates


def _get_order_spec_units(order):
    """주문의 spec_w300 단위 합산. 항목별 W합/300 (spec_rows 있으면 W 합산 후 /300)."""
    if not order.is_erp_order or not order.structured_data:
        return 0.0
    sd = order.structured_data or {}
    items = sd.get('items') or []
    total = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        total += item_spec_w300_value(it)
    return total


def _shipment_dashboard_order_scope():
    """출고 대시보드 상단 패널·목록에 포함되는 주문 범위."""
    return or_(
        Order.is_erp_order == True,
        Order.status.in_(AS_SHIPMENT_STATUSES),
        and_(
            Order.is_erp_order == False,
            Order.scheduled_date != None,
            Order.scheduled_date != '',
        ),
    )


def _erp_order_search_filter(query, q):
    """고객·연락처·담당·주소·품목·주문번호·ERP 노출 필드·structured_data 전반."""
    if not q or not q.strip():
        return query
    term = f'%{q.strip()}%'
    return query.filter(
        erp_order_dashboard_search_predicate(
            term,
            include_structured_data_blob=True,
        )
    )


def _pick_shipment_search_focus_date(scoped_orders_query, today_kst):
    """
    검색어가 있을 때 14일 패널 밖의 시공·AS 방문 일정도 포함해 포커스 날짜를 고른다.

    Args:
        scoped_orders_query: active_filter + 검색 + _shipment_dashboard_order_scope()까지 적용된 쿼리.
        today_kst: 오늘(KST) 기준 datetime.

    Returns:
        'YYYY-MM-DD' 또는 매칭 일정이 없으면 None.
    """
    from models import OrderScheduleDate

    half = SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS
    past = (today_kst - datetime.timedelta(days=half)).strftime('%Y-%m-%d')
    future = (today_kst + datetime.timedelta(days=half)).strftime('%Y-%m-%d')
    q = scoped_orders_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id).filter(
        or_(
            and_(Order.status.in_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == 'as_visit'),
            OrderScheduleDate.kind == 'construction',
        ),
        OrderScheduleDate.date >= past,
        OrderScheduleDate.date <= future,
    ).with_entities(OrderScheduleDate.date).distinct()
    rows = q.all()
    dates = sorted({str(r[0]) for r in rows if r and r[0]})
    if not dates:
        return None
    today_d = today_kst.date()
    future_or_today = [
        d for d in dates
        if datetime.datetime.strptime(d, '%Y-%m-%d').date() >= today_d
    ]
    past_only = [
        d for d in dates
        if datetime.datetime.strptime(d, '%Y-%m-%d').date() < today_d
    ]
    if future_or_today:
        return min(future_or_today)
    return max(past_only)


@erp_shipment_page_bp.route('/shipment')
@login_required
def erp_shipment_dashboard():
    """ERP Order - 출고 대시보드 (날짜별 순수 시공 건수, AS 제외, 출고일지 스타일)"""
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    today_kst = get_today_kst()
    today_date = today_kst.strftime('%Y-%m-%d')
    today_dt = today_kst
    search_q = get_search_query_arg('q', 'search', 'manager')
    date_from = (request.args.get('date_from') or '').strip()
    date_to = (request.args.get('date_to') or '').strip()
    date_arg_raw = (request.args.get('date') or '').strip()
    req_date = date_arg_raw

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
    # 기본 진입은 당일 주문만 로드한다. 전체 목록 로드는 대시보드 기본 동작에서 제외.
    if not use_range and not use_single_day:
        req_date = today_date
        use_single_day = True
    selected_date = req_date

    user_locked_calendar_date = bool(date_arg_raw)

    base_query = db.query(Order).filter(Order.active_filter())
    base_query = _erp_order_search_filter(base_query, search_q)

    scoped_for_search = base_query.filter(_shipment_dashboard_order_scope())
    search_auto_date_applied = False
    if (
        search_q
        and search_q.strip()
        and not use_range
        and use_single_day
        and not user_locked_calendar_date
    ):
        picked = _pick_shipment_search_focus_date(scoped_for_search, today_kst)
        if picked:
            selected_date = picked
            req_date = picked
            search_auto_date_applied = True

    from models import OrderScheduleDate
    from sqlalchemy.orm import selectinload

    # 시공/출고 대시보드는 AS 및 시공 관련이므로 Order.status 필터를 적용
    panel_query = base_query.filter(_shipment_dashboard_order_scope())

    panel_range_start = today_kst.strftime('%Y-%m-%d')
    panel_range_end = (today_kst + datetime.timedelta(days=14)).strftime('%Y-%m-%d')
    panel_query = panel_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
    panel_query = panel_query.filter(
        or_(
            and_(Order.status.in_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == 'as_visit'),
            OrderScheduleDate.kind == 'construction',
        ),
        OrderScheduleDate.date >= panel_range_start,
        OrderScheduleDate.date <= panel_range_end,
    ).distinct()

    panel_orders = panel_query.options(
        load_only(
            Order.id, Order.scheduled_date, Order.as_received_date, Order.as_completed_date,
            Order.structured_data, Order.status, Order.is_erp_order,
            Order.customer_name, Order.manager_name, Order.phone, Order.address,
            Order.measurement_date,
        ),
        selectinload(Order.schedule_dates)
    ).order_by(Order.id.desc()).all()

    # 시공팀 또는 mine=1일 때만 목록/패널을 담당 주문으로 제한 (의도적 이중 필터: panel_orders + 아래 rows)
    if mine_only and current_user:
        panel_orders = [o for o in panel_orders if is_order_mine_for_user(o, current_user)]
    
    for o in panel_orders:
        o.structured_data = _ensure_dict(o.structured_data)  # type: ignore[assignment]
    
    settings = load_erp_shipment_settings()
    worker_settings = normalize_erp_shipment_workers(settings.get('construction_workers', []))
    worker_name_map = {_normalize_worker_name(w['name']): w for w in worker_settings if w.get('name')}

    range_start = today_kst
    range_end = today_kst + datetime.timedelta(days=14)
    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= get_holidays_kr(y)

    _agg_fp = {
        "v": 2,
        "user": _shipment_user_visibility_fingerprint(current_user),
        "filters": {
            "q": search_q,
            "mine_only": mine_only,
            "is_construction": bool(is_construction),
            "panel_range_start": panel_range_start,
            "panel_range_end": panel_range_end,
        },
        "panel_order_ids": sorted(o.id for o in panel_orders),
    }
    _agg_key = build_dashboard_cache_key("shipment", "panel_aggregates", _agg_fp)

    def _compute_shipment_panel_aggregates():
        cc = {}
        aw = {}
        su = {}
        for order in panel_orders:
            if is_as_order(order):
                continue

            for date_value in extract_all_construction_dates(order):
                try:
                    d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
                except Exception:
                    continue
                if d < range_start or d > range_end:
                    continue
                key = d.strftime('%Y-%m-%d')
                cc[key] = cc.get(key, 0) + 1

            all_construction_dates = extract_all_construction_dates(order)
            for date_value in all_construction_dates:
                try:
                    d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
                except Exception:
                    continue
                if d < range_start or d > range_end:
                    continue
                key = d.strftime('%Y-%m-%d')

                shipment = {}
                if order.structured_data and isinstance(order.structured_data, dict):  # type: ignore
                    shipment = (order.structured_data.get('shipment') or {})
                workers = shipment.get('construction_workers') or []
                for w in workers:
                    name_key = _normalize_worker_name(w)
                    if not name_key:
                        continue
                    if name_key in worker_name_map:
                        aw.setdefault(key, set()).add(name_key)

                su[key] = su.get(key, 0.0) + _get_order_spec_units(order)
        return {
            "construction_counts": cc,
            "assigned_workers_by_date": {k: sorted(list(v)) for k, v in aw.items()},
            "spec_units_by_date": su,
        }

    _agg_blob = get_or_compute_dashboard_slice(
        _agg_key,
        TTL_PANEL_ROWS,
        _compute_shipment_panel_aggregates,
        page="shipment",
        slice_name="panel_aggregates",
    )
    construction_counts = _agg_blob["construction_counts"]
    assigned_workers_by_date = {
        k: set(v) for k, v in _agg_blob["assigned_workers_by_date"].items()
    }
    spec_units_by_date = _agg_blob["spec_units_by_date"]

    # 검색 시 광범위 일정 조회가 실패했을 때만 14일 패널 집계로 포커스 날짜 보조
    if (
        search_q
        and search_q.strip()
        and not use_range
        and use_single_day
        and not user_locked_calendar_date
        and not search_auto_date_applied
    ):
        dates_with_counts = [d for d, c in construction_counts.items() if c > 0]
        if dates_with_counts:
            today_d = today_kst
            future_or_today = [
                d for d in dates_with_counts
                if datetime.datetime.strptime(d, '%Y-%m-%d').date() >= today_d.date()
            ]
            past = [
                d for d in dates_with_counts
                if datetime.datetime.strptime(d, '%Y-%m-%d').date() < today_d.date()
            ]
            if future_or_today:
                selected_date = min(future_or_today)
            else:
                selected_date = max(past)
            req_date = selected_date

    _ws_canon = json.dumps(worker_settings, sort_keys=True, ensure_ascii=False, default=str)
    _worker_settings_fp = hashlib.sha256(_ws_canon.encode("utf-8")).hexdigest()[:20]
    _derived_fp = {
        "v": 1,
        "user": _shipment_user_visibility_fingerprint(current_user),
        "filters": {
            "q": search_q,
            "mine_only": mine_only,
            "is_construction": bool(is_construction),
            "panel_range_start": panel_range_start,
            "panel_range_end": panel_range_end,
            "selected_date": selected_date,
            "date_from": date_from,
            "date_to": date_to,
            "use_range": use_range,
            "use_single_day": use_single_day,
        },
        "aggregates_key_suffix": _agg_key.rsplit(":", 1)[-1],
        "worker_settings_fp": _worker_settings_fp,
    }
    _derived_key = build_dashboard_cache_key(
        "shipment", "shipment_panel_derived_template_payloads", _derived_fp
    )

    def _compute_shipment_derived_template_payloads():
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
        return {
            "construction_panel_dates": construction_panel_dates,
            "remaining_panel_dates": remaining_panel_dates,
        }

    _derived_blob = get_or_compute_dashboard_slice(
        _derived_key,
        TTL_PANEL_ROWS,
        _compute_shipment_derived_template_payloads,
        page="shipment",
        slice_name="shipment_panel_derived_template_payloads",
    )
    construction_panel_dates = _derived_blob["construction_panel_dates"]
    remaining_panel_dates = _derived_blob["remaining_panel_dates"]

    # 패널 데이터에서 rows 추출 (쿼리 2회→1회 통합: panel_orders가 이미 14일치 + mine_only 필터 적용됨)
    # 검색 중에는 매칭이 14일 밖에 있어도 전체 rows 쿼리로 통합 (전체 검색 의미 유지)
    _derive_from_panel = False
    _search_active = bool(search_q and search_q.strip())
    if not _search_active:
        if use_single_day and panel_range_start <= selected_date <= panel_range_end:
            _derive_from_panel = True
        elif use_range and date_from >= panel_range_start and date_to <= panel_range_end:
            _derive_from_panel = True

    if _derive_from_panel:
        if use_single_day:
            rows = [o for o in panel_orders
                    if selected_date in {str(d) for d in extract_dashboard_target_dates(o)}]
        else:
            rows = [o for o in panel_orders
                    if any(date_from <= str(d) <= date_to
                           for d in extract_dashboard_target_dates(o))]
    else:
        # Edge case: 패널 범위(14일) 밖 날짜 → 별도 쿼리 (fallback)
        rows_query = base_query.filter(_shipment_dashboard_order_scope())
        if use_range or use_single_day:
            rows_query = rows_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
            rows_query = rows_query.filter(
                or_(
                    and_(Order.status.in_(AS_SHIPMENT_STATUSES), OrderScheduleDate.kind == 'as_visit'),
                    OrderScheduleDate.kind == 'construction',
                )
            )
            if use_range:
                rows_query = rows_query.filter(OrderScheduleDate.date >= date_from, OrderScheduleDate.date <= date_to)
            elif use_single_day:
                rows_query = rows_query.filter(OrderScheduleDate.date == selected_date)
            rows_query = rows_query.distinct()
        rows_query = rows_query.options(
            load_only(
                Order.id, Order.scheduled_date, Order.as_received_date, Order.as_completed_date,
                Order.structured_data, Order.status, Order.is_erp_order,
                Order.customer_name, Order.manager_name, Order.phone, Order.address,
                Order.measurement_date,
            ),
            selectinload(Order.schedule_dates)
        ).order_by(Order.id.desc()).limit(500)
        rows = rows_query.all()
        if mine_only and current_user:
            rows = [r for r in rows if is_order_mine_for_user(r, current_user)]
    rows = rows[:300]

    for r in rows:
        r.shipment_as_recommendation_link = None
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]
        sd = r.structured_data
        shipment = (sd.get('shipment') or {}) if isinstance(sd, dict) else {}
        r.as_content_text = as_content_html_to_text(shipment.get('as_content') or '')

        if is_as_order(r):
            sched = (sd.get("schedule") or {}) if isinstance(sd, dict) else {}
            av = sched.get("as_visit") if isinstance(sched, dict) else {}
            sr = av.get("shipment_recommendation") if isinstance(av, dict) else None
            if isinstance(sr, dict) and sr.get("source") == SHREC_SOURCE:
                sid_raw = sr.get("shipment_order_id")
                try:
                    sid_int = int(sid_raw) if sid_raw is not None else None
                except (TypeError, ValueError):
                    sid_int = None
                info_raw = sr.get("as_info_id")
                try:
                    info_int = int(info_raw) if info_raw is not None else None
                except (TypeError, ValueError):
                    info_int = None
                r.shipment_as_recommendation_link = {
                    "shipment_order_id": sid_int,
                    "as_order_id": r.id,
                    "as_info_id": info_int,
                    "applied_date": str(sr.get("applied_date") or av.get("date") or ""),
                }

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
        if order.is_erp_order and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    def get_construction_worker_key_for_sort(order):
        """시공자별 그룹·정렬용: 첫 번째 유효한 시공자 또는 빈 문자열."""
        if not order.is_erp_order or not order.structured_data:
            return ''
        shipment = (order.structured_data.get('shipment') or {})
        workers = shipment.get('construction_workers') or []
        for w in workers:
            w_str = str(w).strip() if w else ''
            if w_str:
                return w_str
        return ''

    rows.sort(key=lambda o: (
        1 if is_as_order(o) else 0,
        get_construction_worker_key_for_sort(o) or 'ZZZ',
        get_manager_name_for_sort(o) or 'ZZZ',
        o.id
    ))

    mobile_queue_rows = []
    mobile_v2_active = is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        current_user.id if current_user else None,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    if mobile_v2_active:
        for order in rows:
            row = build_mobile_queue_order_row(db, order, current_user)
            sd = order.structured_data if isinstance(order.structured_data, dict) else {}
            shipment = sd.get("shipment") or {}
            drawing_managers = [
                str(value).strip()
                for value in (shipment.get("drawing_managers") or [])
                if str(value or "").strip()
            ]
            if not drawing_managers and shipment.get("drawing_manager"):
                drawing_managers = [str(shipment.get("drawing_manager")).strip()]
            construction_workers = [
                str(value).strip()
                for value in (shipment.get("construction_workers") or [])
                if str(value or "").strip()
            ]
            site_extra = []
            for value in (shipment.get("site_extra") or []):
                if isinstance(value, dict):
                    text_value = str(value.get("text") or "").strip()
                else:
                    text_value = str(value or "").strip()
                if text_value:
                    site_extra.append(text_value)
            row["customer_name"] = row.get("customer_name") or order.customer_name or "-"
            if row["customer_name"] == "-":
                row["customer_name"] = order.customer_name or "-"
            row["phone"] = row.get("phone") if row.get("phone") not in (None, "", "-") else (order.phone or "-")
            row["address"] = row.get("address") if row.get("address") not in (None, "", "-") else (order.address or "-")
            row["manager_name"] = row.get("manager_name") if row.get("manager_name") not in (None, "", "-") else (order.manager_name or "-")
            row["orderer_name"] = row.get("orderer_name") or getattr(order, "orderer_name", None)
            row["product_subtitle"] = row.get("product_subtitle") or (getattr(order, "product", None) or "")
            row["shipment_meta"] = {
                "construction_time": shipment.get("construction_time") or "",
                "drawing_managers": drawing_managers,
                "construction_workers": construction_workers,
                "site_extra": site_extra,
                "spec_units": _get_order_spec_units(order),
                "is_as": is_as_order(order),
                "as_content_text": getattr(order, "as_content_text", "") or "",
                "recommendation_link": getattr(order, "shipment_as_recommendation_link", None),
            }
            mobile_queue_rows.append(row)

    template_name = (
        'shipment/partials/dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'shipment/dashboard.html'
    )
    _t0 = time.perf_counter()
    _body = render_template(
        template_name,
        selected_date=selected_date,
        search_q=search_q,
        date_from=date_from,
        date_to=date_to,
        use_date_range=use_range,
        rows=rows,
        mobile_queue_rows=mobile_queue_rows,
        construction_panel_dates=construction_panel_dates,
        remaining_panel_dates=remaining_panel_dates,
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=mine_only,
        is_construction_team=is_construction,
    )
    _render_ms = (time.perf_counter() - _t0) * 1000.0
    response = make_response(_body)
    apply_erp_shell_fragment_headers(response, request)
    apply_ept_b7_render_headers(response, route_id="erp_shipment_dashboard", render_ms=_render_ms)
    return response
