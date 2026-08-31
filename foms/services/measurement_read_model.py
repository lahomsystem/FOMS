"""ERP 실측 대시보드 read-model (Batch 3 measurement 구조-추출, 동작 보존).

`erp_measurement_dashboard()`의 panel assembly(날짜창 카운트/요약 카드) compute slice와
공유 raw-match 필터를 분리한다. cache 키·fingerprint·get_or_compute는 라우트가 유지하고,
이 모듈은 캐시 미스 시 동일 결과를 산출한다(panel은 lambda 위임).

flat 모듈로 둔다(`measurement_dates.py`/`measurement_dashboard_filters.py`와 동일 관행;
subpackage `foms.services.measurement` __init__의 standalone 순환 import 회피).
"""
from __future__ import annotations

import datetime
import logging

from sqlalchemy import or_, and_, cast, String
from sqlalchemy.orm import load_only, selectinload

from models import Order, OrderScheduleDate
from foms.services.erp_display import _ensure_dict, self_measurement_four_checks_done, apply_erp_display_fields_to_orders

logger = logging.getLogger(__name__)
from foms.services.measurement_dates import extract_all_measurement_dates
from foms.services.common.business_calendar import get_holidays_kr


def apply_measurement_dashboard_order_scope(query):
    """실측 대시보드·지도·summary API 공통 주문 범위 필터.

    자가실측 상태(SELF_MEASUREMENT/SELF_MEASURED)는 is_self_measurement 또는
    is_regional 플래그가 있는 주문만 포함한다. 지방주문(is_regional)도 실측 대시보드에 표시.
    """
    return query.filter(
        or_(
            and_(
                Order.is_regional != True,
                ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED']),
            ),
            Order.is_self_measurement == True,
            Order.is_regional == True,
        )
    )


def measurement_schedule_on_dates(dates) -> object:
    """실측 일정이 ``dates`` 중 하루라도 걸리는 주문 EXISTS 술어.

    날짜 술어의 정본은 **복수 일정을 행으로 펼친** ``order_schedule_dates`` 다
    (싱크 컬럼 ``measurement_date`` 는 콤마 복수 중 첫 날짜만 담는다). 같은 술어를
    관제탑이 이미 쓴다 — `foms.services.orders.dashboard_control_tower._sched_any`.
    행은 `order_date_sync` 리스너가 쓰기마다 갱신하고, 부분 인덱스
    ``(date, order_id) WHERE kind='measurement'`` 가 이 조회를 받는다.

    ``date`` 컬럼이 varchar 라 범위 비교 대신 **정확 일치 IN** 을 쓴다 — 컬럼에 섞인
    비-ISO 오염값('미정' 등)이 술어에 걸리지 않는다.

    Args:
        dates: 'YYYY-MM-DD' 문자열 목록.

    Returns:
        SQLAlchemy EXISTS 술어.
    """
    return Order.schedule_dates.any(
        and_(
            OrderScheduleDate.kind == "measurement",
            OrderScheduleDate.date.in_(list(dates)),
        )
    )


def _order_is_regional_for_panel(order) -> bool:
    """패널 건수 분류용 지방주문 여부."""
    return getattr(order, 'is_regional', False) is True


def _accumulate_measurement_panel_date_counts(
    measurement_counts: dict,
    regional_counts: dict,
    metro_counts: dict,
    order,
    date_key: str,
) -> None:
    """날짜별 전체·지방·수도권 건수를 누적한다."""
    measurement_counts[date_key] = measurement_counts.get(date_key, 0) + 1
    if _order_is_regional_for_panel(order):
        regional_counts[date_key] = regional_counts.get(date_key, 0) + 1
    else:
        metro_counts[date_key] = metro_counts.get(date_key, 0) + 1


def panel_date_count_fields(
    measurement_counts: dict,
    regional_counts: dict,
    metro_counts: dict,
    date_str: str,
) -> dict:
    """패널 row/API 공통 count 필드."""
    total = measurement_counts.get(date_str, 0)
    regional = regional_counts.get(date_str, 0)
    metro = metro_counts.get(date_str, 0)
    return {
        'count': total,
        'count_regional': regional,
        'count_metro': metro,
    }


# 메인 목록 표시 상한(정책) + seed 캡. 둘은 항상 같은 값이어야 한다 — seed 가 더 작으면
# 표시 상한에 닿기 전에 행이 사라지고, 더 크면 뽑아놓고 버린다.
MEASUREMENT_MAIN_DISPLAY_CAP = 300
MEASUREMENT_MAIN_SEED_LIMIT = MEASUREMENT_MAIN_DISPLAY_CAP


def fetch_measurement_main_seed_rows(list_query) -> list:
    """Seed rows for main table (cap matches [:300] display cut)."""
    rows = (
        list_query.options(selectinload(Order.schedule_dates))
        .order_by(Order.id.desc())
        .limit(MEASUREMENT_MAIN_SEED_LIMIT)
        .all()
    )
    for row in rows:
        row.structured_data = _ensure_dict(row.structured_data)  # type: ignore[assignment]
    return rows


def compute_measurement_main_rows_blob(
    db,
    base_query,
    list_query,
    current_user,
    mine_filter_active,
    selected_date,
    use_range,
    use_single_day,
    date_from,
    date_to,
    focus_order_id,
) -> dict:
    """JSON DTO for measurement main_rows micro-cache.

    ``total_count`` 는 표시 상한(:data:`MEASUREMENT_MAIN_DISPLAY_CAP`) 적용 **전** 모집단이다.
    3개월 범위 조회처럼 모집단이 상한을 넘으면 화면이 조용히 잘리므로(운영 실측: 92일
    조회 1069건 중 300건), 잘렸다는 사실을 화면과 로그에 남기기 위해 함께 캐시한다.
    """
    total_count = int(list_query.order_by(None).count() or 0)
    if total_count > MEASUREMENT_MAIN_DISPLAY_CAP:
        logger.warning(
            "[measurement] 메인 목록 표시 상한 발동: 모집단 %s건 > 상한 %s건",
            total_count, MEASUREMENT_MAIN_DISPLAY_CAP,
        )
    seed_rows = fetch_measurement_main_seed_rows(list_query)
    rows, row_fallback_added_ids = build_measurement_main_rows(
        db,
        base_query,
        seed_rows,
        current_user,
        mine_filter_active,
        selected_date,
        use_range,
        use_single_day,
        date_from,
        date_to,
        focus_order_id,
    )
    return {
        "order_ids": [int(o.id) for o in rows],
        "row_fallback_added_ids": [int(x) for x in row_fallback_added_ids],
        "total_count": total_count,
    }


def hydrate_measurement_main_rows(
    base_query,
    blob: dict,
    *,
    selected_date: str,
    use_range: bool,
    use_single_day: bool,
    date_from: str,
    date_to: str,
) -> tuple[list, list[int]]:
    """Rehydrate cached main rows via base_query (not date-joined list_query).

    Blob order_ids are authoritative on cache hit — focus_order deep-links may sit
    outside the selected date window and must not be dropped by schedule join filters.
    """
    order_ids = [int(x) for x in (blob.get("order_ids") or [])]
    row_fallback_added_ids = [int(x) for x in (blob.get("row_fallback_added_ids") or [])]
    if not order_ids:
        return [], row_fallback_added_ids
    fetched = (
        base_query.order_by(None)
        .filter(Order.id.in_(order_ids))
        .options(selectinload(Order.schedule_dates))
        .all()
    )
    by_id = {int(o.id): o for o in fetched}
    rows = []
    for oid in order_ids:
        order = by_id.get(oid)
        if order is None:
            continue
        order.structured_data = _ensure_dict(order.structured_data)  # type: ignore[assignment]
        rows.append(order)
    hydrated_ids = {int(o.id) for o in rows}
    row_fallback_added_ids = [x for x in row_fallback_added_ids if x in hydrated_ids]
    for row in rows:
        row.measurement_dates_display = _build_measurement_dates_for_display(
            row,
            selected_date=selected_date if use_single_day else '',
            date_from=date_from if use_range else '',
            date_to=date_to if use_range else '',
        )
    apply_erp_display_fields_to_orders(rows)
    return rows, row_fallback_added_ids


def _build_measurement_raw_match_filter(date_values):
    values = [str(v).strip() for v in date_values if str(v or '').strip()]
    if not values:
        return None

    conditions = []
    for value in values:
        conditions.append(Order.measurement_date.ilike(f'%{value}%'))  # perf-ok: bounded measurement date filter cold path
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
            Order.is_regional,
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
                Order.is_regional,
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
    regional_counts = {}
    metro_counts = {}
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
            _accumulate_measurement_panel_date_counts(
                measurement_counts, regional_counts, metro_counts, order, key
            )

    out_panel_dates = []
    cur2 = range_start
    while cur2 <= range_end:
        date_str = cur2.strftime('%Y-%m-%d')
        is_weekend = cur2.weekday() >= 5
        is_holiday = date_str in holiday_dates
        out_panel_dates.append({
            'date': date_str,
            **panel_date_count_fields(
                measurement_counts, regional_counts, metro_counts, date_str
            ),
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

    rows = rows[:MEASUREMENT_MAIN_DISPLAY_CAP]
    for row in rows:
        row.measurement_dates_display = _build_measurement_dates_for_display(
            row,
            selected_date=selected_date if use_single_day else '',
            date_from=date_from if use_range else '',
            date_to=date_to if use_range else '',
        )
    apply_erp_display_fields_to_orders(rows)
    return rows, row_fallback_added_ids
