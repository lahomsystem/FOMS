"""ERP 실측 대시보드 read-model (Batch 3 measurement 구조-추출, 동작 보존).

`erp_measurement_dashboard()`의 panel assembly(날짜창 카운트/요약 카드) compute slice와
공유 raw-match 필터를 분리한다. cache 키·fingerprint·get_or_compute는 라우트가 유지하고,
이 모듈은 캐시 미스 시 동일 결과를 산출한다(panel은 lambda 위임).

flat 모듈로 둔다(`measurement_dates.py`/`measurement_dashboard_filters.py`와 동일 관행;
subpackage `foms.services.measurement` __init__의 standalone 순환 import 회피).
"""
from __future__ import annotations

import datetime

from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm import load_only, selectinload

from models import Order, OrderScheduleDate
from foms.services.erp_display import _ensure_dict, self_measurement_four_checks_done, apply_erp_display_fields_to_orders
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.common.business_calendar import get_holidays_kr


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


def compute_measurement_panel_assembly(
    base_query,
    current_user,
    mine_filter_active,
    selected_date,
    range_start,
    range_end,
    range_start_str,
    range_end_str,
):
    """실측 패널(14일 창 날짜별 카운트/요약 카드) 집계 (구 _compute_measurement_panel_assembly).

    Batch 3: 라우트 캐시 슬라이스 compute closure를 read-model로 분리(동작 보존).
    cache 키·fingerprint·get_or_compute는 라우트가 유지한다.

    Returns:
        {"panel_summary_stat_cards": [...], "panel_row_ids": [...],
         "panel_fallback_supplement_ids": [...]} — 원본 closure와 동일 형태.
    """
    # lazy import: erp_permissions canonical path (namespace 계약 + circular 회피)
    from foms.services.erp_permissions import build_mine_sql_filter

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
            p_mine_conds = build_mine_sql_filter(current_user)
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


def compute_measurement_product_items_build(db, rows, row_fallback_added_ids):
    """실측 메인 행 product_items 빌드 (구 _compute_measurement_product_items_build).

    Batch 3: 라우트 캐시 슬라이스 compute closure를 read-model로 분리(동작 보존).
    cache 키·fingerprint·get_or_compute는 라우트가 유지한다.
    build_product_items_for_orders는 rows에 product_items 속성을 in-place로 채운다(원본과 동일).

    Args:
        db: 요청 스코프 DB 세션.
        rows: 표시 대상 Order 객체 리스트(상위 300건).
        row_fallback_added_ids: raw-match fallback으로 보충된 order id 리스트.

    Returns:
        {"product_items_by_id": {str(order_id): items},
         "main_table_fallback_row_ids": [...]} — 원본 closure와 동일 형태.
    """
    # lazy import: foms.services 패키지 standalone 순환 회피(원본은 라우트 top import).
    from foms.services.erp_product_items import build_product_items_for_orders

    build_product_items_for_orders(db, rows)
    return {
        "product_items_by_id": {
            str(o.id): (getattr(o, "product_items", None) or []) for o in rows
        },
        "main_table_fallback_row_ids": sorted(row_fallback_added_ids),
    }


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


def build_measurement_main_rows(
    db,
    base_query,
    all_rows,
    current_user,
    mine_filter_active,
    selected_date,
    use_range,
    use_single_day,
    date_from,
    date_to,
    focus_order_id,
):
    """실측 메인 목록 rows 조립 (구 route main-rows 블록). 동작 보존.

    필터 매칭 + raw-match fallback + focus 딥링크 주입(절단 전) + [:300] 절단 +
    날짜 표시 가공을 원본과 1:1로 수행한다. focus_order_id는 라우트가 파싱해 전달한다.

    Returns:
        (rows, row_fallback_added_ids)
    """
    # lazy import: erp_permissions canonical path(namespace 계약 + circular 회피)
    from foms.services.erp_permissions import is_order_related_to_user, build_mine_sql_filter

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
            row_fallback_added_ids.append(order.id)

    # 검색 카드 딥링크(?focus_order=)는 실측 날짜창과 무관하게 해당 주문이 항상 큐에 착지해야 한다.
    # orders/construction/cs/as 대시보드와 동일한 deep-link SSOT:
    # q는 검색창 표시용이고, focus_order는 날짜 필터만 우회한다.
    # 전역 mine이 켜져 있으면 타인 주문을 강제 포함하지 않는다.
    if focus_order_id and focus_order_id not in {o.id for o in rows}:
        focus_row = (
            db.query(Order)
            .filter(Order.id == focus_order_id, Order.active_filter())
            .options(selectinload(Order.schedule_dates))
            .first()
        )
        if focus_row is not None and (
            not mine_filter_active
            or is_order_related_to_user(focus_row, current_user)
        ):
            focus_row.structured_data = _ensure_dict(focus_row.structured_data)  # type: ignore[assignment]
            # [:300] 절단보다 앞에 두어 큐가 가득 차도 검색 카드가 누락되지 않게 한다.
            rows.insert(0, focus_row)

    rows = rows[:300]
    for row in rows:
        row.measurement_dates_display = _build_measurement_dates_for_display(
            row,
            selected_date=selected_date if use_single_day else '',
            date_from=date_from if use_range else '',
            date_to=date_to if use_range else '',
        )
    apply_erp_display_fields_to_orders(rows)
    return rows, row_fallback_added_ids
