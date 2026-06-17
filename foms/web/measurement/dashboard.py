"""
ERP 실측 대시보드 페이지 (canonical: foms.web.measurement.dashboard)
erp.py에서 분리: /erp/measurement
"""
from flask import Blueprint, make_response, render_template, request, redirect, url_for, g
from db import get_db
from models import Order, OrderScheduleDate
from foms.web.auth import login_required
import datetime
from datetime import date, timedelta
from sqlalchemy import or_, and_, cast, String, func
from sqlalchemy.orm import load_only, selectinload

from foms.services.common.business_calendar import get_holidays_kr
from foms.services.erp_permissions import can_edit_erp, build_mine_sql_filter
from foms.services.erp_display import (
    _ensure_dict,
    _normalize_date_to_yyyymmdd,
    apply_erp_display_fields_to_orders,
    get_today_kst,
    normalize_manager_name,
    self_measurement_four_checks_done,
)
from foms.services.erp_product_items import build_product_items_for_orders
from foms.services.erp_shipment_settings import load_erp_shipment_settings
from foms.services.measurement_manager_colors import build_measurement_manager_color_map
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.orders.status_constants import STATUS
from foms.services.common.dashboard_cache import (
    TTL_PANEL_ROWS,
    TTL_PAYLOAD_ASSEMBLY,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.common.erp_shell_http import (
    apply_erp_shell_fragment_headers,
    wants_erp_shell_tab_body,
)
from foms.services.request_utils import get_search_query_arg

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
                Order.is_erp_order == True,
                cast(Order.structured_data, String).ilike(term)  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )
    )


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
                Order.is_erp_order == True,
                cast(Order.structured_data, String).ilike(f'%{value}%')  # perf-ok: ix_orders_structured_data_text_trgm
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


def _measurement_user_visibility_fingerprint(current_user) -> dict:
    """실측 대시보드 캐시 키용 사용자·팀 식별."""
    if not current_user:
        return {"user_id": None, "role": None, "username": None, "team": None}
    return {
        "user_id": getattr(current_user, "id", None),
        "role": getattr(current_user, "role", None),
        "username": getattr(current_user, "username", None),
        "team": getattr(current_user, "team", None),
    }


@erp_measurement_dashboard_bp.route('/measurement')
@login_required
def erp_measurement_dashboard():
    """ERP Order - 실측 대시보드 (structured_data 기반, MVP는 Order 컬럼 연동으로 운용)"""
    db = get_db()
    today_kst = get_today_kst()
    today_date = today_kst.strftime('%Y-%m-%d')
    search_q = get_search_query_arg('q', 'search', 'manager')
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
        mine_conds = build_mine_sql_filter(current_user, scope="sales")
        if mine_conds:
            query = query.filter(or_(*mine_conds))

    all_rows = query.options(selectinload(Order.schedule_dates)).order_by(Order.id.desc()).limit(500).all()

    for r in all_rows:
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]

    _panel_fp = {
        "v": 1,
        "user": _measurement_user_visibility_fingerprint(current_user),
        "filters": {
            "q": search_q,
            "mine": "1" if mine_filter_active else "",
            "range_start": range_start_str,
            "range_end": range_end_str,
            "panel_anchor": today_date,
            "selected_date": selected_date,
        },
    }
    # 실행 계획 §3.1.1 measurement: panel rows + panel summary/stat + (below) fallback/product slices
    _panel_key = build_dashboard_cache_key(
        "measurement", "measurement_panel_assembly", _panel_fp
    )

    def _compute_measurement_panel_assembly():
        panel_query = base_query.join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        panel_query = panel_query.filter(
            OrderScheduleDate.kind == 'measurement',
            OrderScheduleDate.date >= range_start_str,
            OrderScheduleDate.date <= range_end_str,
        ).distinct()
        if mine_filter_active:
            p_mine_conds = build_mine_sql_filter(current_user, scope="sales")
            if p_mine_conds:
                panel_query = panel_query.filter(or_(*p_mine_conds))
        panel_orders = panel_query.options(
            load_only(
                Order.id, Order.measurement_date, Order.structured_data,
                Order.is_self_measurement, Order.is_erp_order, Order.status,
                Order.measurement_completed, Order.regional_sales_order_upload,
                Order.regional_blueprint_sent, Order.regional_order_upload
            ),
            selectinload(Order.schedule_dates)
        ).order_by(Order.id.desc()).all()

        for o in panel_orders:
            o.structured_data = _ensure_dict(o.structured_data)  # type: ignore[assignment]

        panel_range_values = []
        cur = range_start
        while cur <= range_end:
            panel_range_values.append(cur.strftime('%Y-%m-%d'))
            cur += datetime.timedelta(days=1)

        panel_order_ids = {o.id for o in panel_orders}
        panel_fallback_supplement_ids: list[int] = []
        panel_fallback_filter = _build_measurement_raw_match_filter(panel_range_values)
        if panel_fallback_filter is not None:
            panel_fallback_query = base_query.filter(panel_fallback_filter)
            if mine_filter_active:
                p_mine_conds = build_mine_sql_filter(current_user, scope="sales")
                if p_mine_conds:
                    panel_fallback_query = panel_fallback_query.filter(or_(*p_mine_conds))
            panel_fallback_orders = panel_fallback_query.options(
                load_only(
                    Order.id, Order.measurement_date, Order.structured_data,
                    Order.is_self_measurement, Order.is_erp_order, Order.status,
                    Order.measurement_completed, Order.regional_sales_order_upload,
                    Order.regional_blueprint_sent, Order.regional_order_upload
                ),
                selectinload(Order.schedule_dates)
            ).order_by(Order.id.desc()).limit(1500).all()
            for order in panel_fallback_orders:
                order.structured_data = _ensure_dict(order.structured_data)  # type: ignore[assignment]
                if order.id in panel_order_ids:
                    continue
                if not any(range_start_str <= d <= range_end_str for d in extract_all_measurement_dates(order)):
                    continue
                panel_orders.append(order)
                panel_order_ids.add(order.id)
                panel_fallback_supplement_ids.append(order.id)

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

        out_panel_dates = []
        cur2 = range_start
        while cur2 <= range_end:
            date_str = cur2.strftime('%Y-%m-%d')
            is_weekend = cur2.weekday() >= 5
            is_holiday = date_str in holiday_dates
            out_panel_dates.append({
                'date': date_str,
                'count': measurement_counts.get(date_str, 0),
                'weekday': cur2.weekday(),
                'is_weekend': is_weekend,
                'is_holiday': is_holiday,
                'is_selected': date_str == selected_date
            })
            cur2 += datetime.timedelta(days=1)
        return {
            "panel_summary_stat_cards": out_panel_dates,
            "panel_row_ids": sorted(panel_order_ids),
            "panel_fallback_supplement_ids": sorted(panel_fallback_supplement_ids),
        }

    _panel_blob = get_or_compute_dashboard_slice(
        _panel_key,
        TTL_PANEL_ROWS,
        _compute_measurement_panel_assembly,
        page="measurement",
        slice_name="measurement_panel_assembly",
    )
    measurement_panel_dates = _panel_blob["panel_summary_stat_cards"]

    rows = []
    for order in all_rows:
        if self_measurement_four_checks_done(order):
            continue
        if use_single_day and selected_date:
            if _order_matches_measurement_window(order, selected_date=selected_date):
                rows.append(order)
        elif use_range and date_from and date_to:
            if _order_matches_measurement_window(
                order,
                date_from=date_from,
                date_to=date_to,
            ):
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

    row_fallback_added_ids: list[int] = []
    row_fallback_filter = _build_measurement_raw_match_filter(row_match_values)
    if row_fallback_filter is not None:
        row_fallback_query = base_query.filter(row_fallback_filter)
        if mine_filter_active:
            r_mine_conds = build_mine_sql_filter(current_user, scope="sales")
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
            row_fallback_added_ids.append(order.id)

    rows = rows[:300]
    for row in rows:
        row.measurement_dates_display = _build_measurement_dates_for_display(
            row,
            selected_date=selected_date if use_single_day else '',
            date_from=date_from if use_range else '',
            date_to=date_to if use_range else '',
        )
    apply_erp_display_fields_to_orders(rows)

    _pi_fp = {
        "v": 1,
        "user": _measurement_user_visibility_fingerprint(current_user),
        "filters": {
            "q": search_q,
            "mine": "1" if mine_filter_active else "",
            "date_from": date_from,
            "date_to": date_to,
            "selected_date": selected_date,
            "use_range": use_range,
            "use_single_day": use_single_day,
        },
        "order_ids": sorted(o.id for o in rows),
    }
    _pi_key = build_dashboard_cache_key(
        "measurement", "measurement_product_items_build", _pi_fp
    )

    def _compute_measurement_product_items_build():
        build_product_items_for_orders(db, rows)
        return {
            "product_items_by_id": {
                str(o.id): (getattr(o, "product_items", None) or []) for o in rows
            },
            "main_table_fallback_row_ids": sorted(row_fallback_added_ids),
        }

    _pi_blob = get_or_compute_dashboard_slice(
        _pi_key,
        TTL_PAYLOAD_ASSEMBLY,
        _compute_measurement_product_items_build,
        page="measurement",
        slice_name="measurement_product_items_build",
    )
    _pi_by_id = _pi_blob.get("product_items_by_id") or {}
    for o in rows:
        o.product_items = _pi_by_id.get(str(o.id), [])

    def get_manager_name_for_sort(order):
        if order.is_erp_order and order.structured_data:
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
    measurement_manager_color_map = build_measurement_manager_color_map(
        [
            {
                'manager_name': get_manager_name_for_sort(order),
                'order_id': order.id,
            }
            for order in rows
        ],
        measurement_manager_options,
    )

    if open_map:
        # 실측 대시보드 지도는 항상 실측 주문만 표시한다.
        return redirect(url_for('erp_map.map_view', date=selected_date, status='ALL', dashboard='measurement', q=search_q))

    # 모바일 v2 큐: 홈과 동일한 깔끔한 queue-card-v2용 view-model (cohort에서만 계산)
    from foms.services.feature_flags import is_enabled_for_user
    from foms.services.erp_mobile_order_display import build_mobile_queue_order_row
    mobile_v2_active = is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        current_user.id if current_user else None,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    mobile_queue_rows = []
    if mobile_v2_active:
        for _o in rows:
            _row = build_mobile_queue_order_row(db, _o, current_user)
            # 실측은 담당이 user id로 저장되는 케이스가 있어 표시명으로 정규화
            _mgr = normalize_manager_name(
                ((_o.structured_data or {}).get('parties') or {}).get('manager'),
                getattr(_o, 'manager_name', None),
            )
            if _mgr:
                _row['manager_name'] = _mgr
            mobile_queue_rows.append(_row)

    template_name = (
        'measurement/partials/dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'measurement/dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            selected_date=selected_date,
            search_q=search_q,
            date_from=date_from,
            date_to=date_to,
            use_date_range=use_range,
            rows=rows,
            mobile_queue_rows=mobile_queue_rows,
            measurement_panel_dates=measurement_panel_dates,
            measurement_manager_options=measurement_manager_options,
            measurement_manager_color_map=measurement_manager_color_map,
            today_date=today_date,
            can_edit_erp=can_edit_erp(current_user),
            erp_mine_only=mine_filter_active,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response


# -----------------------------------------------------------------------------
# SLG-B3: public measurement dashboards (legacy ``foms.web.dashboards``)
# /regional_dashboard, /metropolitan_dashboard, /self_measurement_dashboard
# -----------------------------------------------------------------------------
dashboards_bp = Blueprint("dashboards", __name__, url_prefix="")


@dashboards_bp.route("/regional_dashboard")
@login_required
def regional_dashboard():
    """지방 주문 관리 대시보드."""
    db = get_db()
    search_query = request.args.get("search_query", "").strip()

    base_query = db.query(Order).filter(
        Order.is_regional == True,
        Order.active_filter(),
    )

    if search_query:
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            search_id = int(search_query)
            id_conditions.append(Order.id == search_id)
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))

        base_query = base_query.filter(
            or_(
                Order.customer_name.ilike(search_term),
                Order.phone.ilike(search_term),
                Order.address.ilike(search_term),
                Order.product.ilike(search_term),
                Order.regional_memo.ilike(search_term),
                Order.notes.ilike(search_term),
                *id_conditions,
            )
        )

    all_regional_orders = base_query.order_by(Order.id.desc()).all()
    apply_erp_display_fields_to_orders(all_regional_orders)
    today = get_today_kst()

    completed_orders = [o for o in all_regional_orders if o.status == "COMPLETED"]
    scheduled_orders = [o for o in all_regional_orders if o.status == "SCHEDULED"]
    hold_orders = [o for o in all_regional_orders if o.status == "ON_HOLD"]

    shipping_alerts = []
    for order in all_regional_orders:
        if (
            getattr(order, "measurement_completed", False)
            and order.shipping_scheduled_date
            and order.shipping_scheduled_date.strip()
            and order.status not in ["COMPLETED", "ON_HOLD"]
        ):
            try:
                shipping_date = datetime.datetime.strptime(
                    order.shipping_scheduled_date, "%Y-%m-%d"
                ).date()
                if shipping_date >= today:
                    shipping_alerts.append(order)
            except (ValueError, TypeError):
                pass

    shipping_completed_orders = []
    for order in all_regional_orders:
        if (
            order.shipping_scheduled_date
            and order.shipping_scheduled_date.strip()
            and order.status not in ["COMPLETED", "ON_HOLD"]
        ):
            try:
                shipping_date = datetime.datetime.strptime(
                    order.shipping_scheduled_date, "%Y-%m-%d"
                ).date()
                if shipping_date < today:
                    shipping_completed_orders.append(order)
            except (ValueError, TypeError):
                pass

    shipping_alert_ids = {o.id for o in shipping_alerts}
    shipping_completed_ids = {o.id for o in shipping_completed_orders}
    pending_orders = [
        o
        for o in all_regional_orders
        if (
            o.status not in ["COMPLETED", "ON_HOLD", "SCHEDULED"]
            and o.id not in shipping_alert_ids
            and o.id not in shipping_completed_ids
            and (
                not getattr(o, "measurement_completed", False)
                or not o.shipping_scheduled_date
                or not o.shipping_scheduled_date.strip()
            )
        )
    ]

    shipping_alerts.sort(
        key=lambda x: datetime.datetime.strptime(
            x.shipping_scheduled_date, "%Y-%m-%d"
        ).date()
    )
    shipping_completed_orders.sort(
        key=lambda x: datetime.datetime.strptime(
            x.shipping_scheduled_date, "%Y-%m-%d"
        ).date()
    )

    return render_template(
        "measurement/regional_dashboard.html",
        pending_orders=pending_orders,
        scheduled_orders=scheduled_orders,
        completed_orders=completed_orders,
        hold_orders=hold_orders,
        shipping_alerts=shipping_alerts,
        shipping_completed_orders=shipping_completed_orders,
        STATUS=STATUS,
        search_query=search_query,
        today=today.strftime("%Y-%m-%d"),
        tomorrow=(today + timedelta(days=1)).strftime("%Y-%m-%d"),
    )


@dashboards_bp.route("/metropolitan_dashboard")
@login_required
def metropolitan_dashboard():
    """수도권 주문 대시보드."""
    db = get_db()
    search_query = request.args.get("search_query", "").strip()

    def get_filtered_orders(q):
        if not search_query:
            return q
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            id_conditions.append(Order.id == int(search_query))
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))
        return q.filter(
            or_(
                Order.customer_name.ilike(search_term),
                Order.phone.ilike(search_term),
                Order.address.ilike(search_term),
                Order.product.ilike(search_term),
                Order.notes.ilike(search_term),
                Order.manager_name.ilike(search_term),
                *id_conditions,
            )
        )

    base_query = db.query(Order).filter(Order.is_regional == False)
    today_str = get_today_kst().strftime("%Y-%m-%d")

    def _measurement_dates_include_today(order):
        if not getattr(order, "measurement_date", None):
            return False
        for d in str(order.measurement_date).split(","):
            try:
                if d.strip() == today_str:
                    return True
            except Exception:
                pass
        return False

    def _measurement_dates_any_lt_today(order):
        if not getattr(order, "measurement_date", None):
            return False
        for d in str(order.measurement_date).split(","):
            try:
                if d.strip() and datetime.datetime.strptime(
                    d.strip(), "%Y-%m-%d"
                ).date() < get_today_kst():
                    return True
            except Exception:
                pass
        return False

    def _measurement_dates_any_gt_today(order):
        if not getattr(order, "measurement_date", None):
            return False
        for d in str(order.measurement_date).split(","):
            try:
                if d.strip() and datetime.datetime.strptime(
                    d.strip(), "%Y-%m-%d"
                ).date() > get_today_kst():
                    return True
            except Exception:
                pass
        return False

    def _scheduled_dates_any_lt_today(order):
        if not getattr(order, "scheduled_date", None):
            return False
        for d in str(order.scheduled_date).split(","):
            try:
                if d.strip() and datetime.datetime.strptime(
                    d.strip(), "%Y-%m-%d"
                ).date() < get_today_kst():
                    return True
            except Exception:
                pass
        return False

    urgent_candidates = get_filtered_orders(
        base_query.filter(
            Order.status.in_(["MEASURED"]),
            Order.measurement_date != None,
            Order.measurement_date != "",
        )
    ).order_by(Order.measurement_date.asc()).all()
    urgent_alerts = [o for o in urgent_candidates if _measurement_dates_include_today(o)]

    measurement_candidates = get_filtered_orders(
        base_query.filter(
            Order.status.in_(["MEASURED"]),
            Order.measurement_date != None,
            Order.measurement_date != "",
            or_(Order.scheduled_date == None, Order.scheduled_date == ""),
        )
    ).order_by(Order.measurement_date.asc()).all()
    measurement_alerts = [o for o in measurement_candidates if _measurement_dates_any_lt_today(o)]

    pre_candidates = get_filtered_orders(
        base_query.filter(
            or_(
                and_(
                    Order.status.in_(["RECEIVED", "MEASURED"]),
                    Order.measurement_date != None,
                    Order.measurement_date != "",
                ),
                and_(
                    Order.status == "RECEIVED",
                    or_(Order.measurement_date == None, Order.measurement_date == ""),
                ),
            )
        )
    ).order_by(Order.measurement_date.asc()).all()
    pre_measurement_alerts = [
        o
        for o in pre_candidates
        if not getattr(o, "measurement_date", None)
        or getattr(o, "measurement_date", "") == ""
        or _measurement_dates_any_gt_today(o)
    ]

    installation_candidates = get_filtered_orders(
        base_query.filter(
            Order.status.in_(["SCHEDULED", "SHIPPED_PENDING"]),
            Order.scheduled_date != None,
            Order.scheduled_date != "",
        )
    ).order_by(Order.scheduled_date.asc()).all()
    installation_alerts = [
        o for o in installation_candidates if _scheduled_dates_any_lt_today(o)
    ]

    alert_ids = {
        o.id
        for o in urgent_alerts
        + measurement_alerts
        + pre_measurement_alerts
        + installation_alerts
    }

    as_orders = get_filtered_orders(
        db.query(Order).filter(
            Order.status == "AS_RECEIVED",
            Order.is_regional == False,
        )
    ).order_by(Order.created_at.desc()).all()

    hold_orders = get_filtered_orders(
        db.query(Order).filter(
            Order.status == "ON_HOLD",
            Order.is_regional == False,
        )
    ).order_by(Order.created_at.desc()).all()

    normal_orders = get_filtered_orders(
        db.query(Order).filter(
            Order.status.notin_(
                ["COMPLETED", "DELETED", "AS_RECEIVED", "AS_COMPLETED", "ON_HOLD"]
            ),
            ~Order.id.in_(alert_ids),
            Order.is_regional == False,
        )
    ).order_by(Order.created_at.desc()).limit(20).all()

    completed_orders = get_filtered_orders(
        db.query(Order).filter(
            Order.status.in_(["COMPLETED", "AS_COMPLETED"]),
            Order.is_regional == False,
        )
    ).order_by(Order.completion_date.desc()).limit(50).all()

    all_metro = (
        urgent_alerts
        + measurement_alerts
        + pre_measurement_alerts
        + installation_alerts
        + as_orders
        + hold_orders
        + normal_orders
        + completed_orders
    )
    apply_erp_display_fields_to_orders(all_metro)

    return render_template(
        "measurement/metropolitan_dashboard.html",
        urgent_alerts=urgent_alerts,
        measurement_alerts=measurement_alerts,
        pre_measurement_alerts=pre_measurement_alerts,
        installation_alerts=installation_alerts,
        as_orders=as_orders,
        hold_orders=hold_orders,
        normal_orders=normal_orders,
        completed_orders=completed_orders,
        STATUS=STATUS,
        search_query=search_query,
    )


@dashboards_bp.route("/self_measurement_dashboard")
@login_required
def self_measurement_dashboard():
    """자가실측 대시보드."""
    db = get_db()
    search_query = request.args.get("search_query", "").strip()

    base_query = db.query(Order).filter(
        Order.is_self_measurement == True,
        Order.active_filter(),
    )

    if search_query:
        search_term = f"%{search_query}%"
        id_conditions = []
        try:
            id_conditions.append(Order.id == int(search_query))
        except ValueError:
            id_conditions.append(func.cast(Order.id, String).ilike(search_term))
        base_query = base_query.filter(
            or_(
                Order.customer_name.ilike(search_term),
                Order.phone.ilike(search_term),
                Order.address.ilike(search_term),
                Order.product.ilike(search_term),
                Order.notes.ilike(search_term),
                *id_conditions,
            )
        )

    all_orders = base_query.order_by(Order.id.desc()).all()
    apply_erp_display_fields_to_orders(all_orders)

    as_orders = [o for o in all_orders if o.status == "AS_RECEIVED"]
    completed_orders = [o for o in all_orders if o.status in ["COMPLETED", "AS_COMPLETED"]]
    scheduled_orders = [o for o in all_orders if o.status == "SCHEDULED"]
    pending_orders = [
        o
        for o in all_orders
        if o.status not in ["COMPLETED", "AS_COMPLETED", "SCHEDULED", "AS_RECEIVED"]
    ]

    return render_template(
        "measurement/self_measurement_dashboard.html",
        pending_orders=pending_orders,
        scheduled_orders=scheduled_orders,
        as_orders=as_orders,
        completed_orders=completed_orders,
        search_query=search_query,
        STATUS=STATUS,
    )
