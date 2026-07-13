"""ERP 출고 대시보드 (ERP-SLIM-7; canonical, SFC-B11B). /erp/shipment."""
import time
from flask import Blueprint, abort, make_response, render_template, request, redirect, url_for, g
from db import get_db
from models import Order
from foms.web.auth import login_required
import datetime
import hashlib
import json
from sqlalchemy import or_, and_
from sqlalchemy.orm import load_only
from foms.services.common.business_calendar import get_holidays_kr
from foms.services.erp_permissions import can_edit_erp, is_order_related_to_user
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from foms.services.shipment_dashboard_helpers import (
    AS_SHIPMENT_STATUSES,
    extract_dashboard_target_dates,
    _normalize_worker_name,
    _get_order_spec_units,
    _get_order_construction_date,
)
from foms.services.erp_shipment_settings import (
    load_erp_shipment_settings,
    normalize_erp_shipment_workers,
)
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
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached
from foms.services.shipment_dashboard_filters import parse_shipment_dashboard_filters
from foms.services.shipment_read_model import (
    compute_shipment_panel_aggregates,
    compute_shipment_derived_template_payloads,
)
from foms.services.shipment_dashboard_display import (
    enrich_shipment_rows,
    sort_shipment_rows,
    build_shipment_mobile_queue_rows,
)
from foms.services.erp_dashboard_search import (
    SHIPMENT_SEARCH_FOCUS_SCHEDULE_HALF_RANGE_DAYS,
    erp_order_dashboard_search_predicate,
)
# 실행 계획 §3.1.1 shipment — read-model slices:
# - ``panel_aggregates``: construction_counts / assigned_workers / spec_units (JSON)
# - ``shipment_panel_derived_template_payloads``: 상단 패널 stat 카드 리스트 2종 (JSON)
# - 패널에서 파생되는 테이블 rows는 ORM 객체(§3.1.2) — ``panel_orders`` 집합은 aggregates 키의 panel_order_ids에 반영

erp_shipment_page_bp = Blueprint(
    'erp_shipment_page', __name__, url_prefix='/erp'
)


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
    # get_today_kst()는 datetime.date를 반환하므로 .date() 호출 없이 그대로 비교한다.
    today_d = today_kst
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


def _compute_tablet_ship_kpis(rows: list) -> dict:
    """태블릿 가로 상단 KPI 4종을 그리드 rows에서 계산한다(추가 쿼리 없음).

    Args:
        rows: erp_shipment_dashboard가 렌더하는 것과 동일한 Order ORM 객체 리스트.

    Returns:
        {'total_units': str(1-decimal), 'order_count': int,
         'team_count': int, 'unassigned': int}.
        total_units=행별 자수 합, order_count=행 수,
        team_count=행 전반에서 등장한 고유 시공팀명 수, unassigned=시공자 미배정 행 수.
    """
    total_units = 0.0
    teams: set[str] = set()
    unassigned = 0
    for r in rows:
        total_units += _get_order_spec_units(r)
        sd = r.structured_data if isinstance(r.structured_data, dict) else {}
        workers = (sd.get('shipment') or {}).get('construction_workers') or []
        names = [str(w).strip() for w in workers if str(w or '').strip()]
        if names:
            teams.update(names)
        else:
            unassigned += 1
    return {
        'total_units': f"{total_units:.1f}",
        'order_count': len(rows),
        'team_count': len(teams),
        'unassigned': unassigned,
    }


def _compute_shipment_team_group_meta(rows: list, worker_settings: list) -> dict:
    """태블릿 그룹 헤더용 시공팀별 집계(자수 합계·건수·capacity·잔여). 추가 쿼리 없음.

    이미 정렬·로드된 ``rows``와 ``worker_settings``만 사용한다. 그룹 키는 각 행의 첫
    유효 시공자(raw trim) — ``sort_shipment_rows``/템플릿 파스텔 인덱스와 동일 키다.
    capacity 는 정규화 이름 매칭으로 찾고, 잔여 = capacity − 그룹 자수합(현재 뷰 기준).
    설정에 없는 팀(임의 입력)·미배정('')은 capacity/remaining 을 None 으로 둔다.

    Args:
        rows: 그리드와 동일한 정렬된 Order 리스트.
        worker_settings: normalize_erp_shipment_workers 결과.

    Returns:
        {group_key: {'units': '12.5', 'count': 3,
                     'capacity': '40.0'|None, 'remaining': '27.5'|None}}.
        group_key 는 raw trim 시공자 문자열('' = 미배정).
    """
    cap_by_norm = {
        _normalize_worker_name(w['name']): float(w.get('capacity') or 0)
        for w in worker_settings if w.get('name')
    }
    acc: dict[str, dict] = {}
    for r in rows:
        sd = r.structured_data if isinstance(r.structured_data, dict) else {}
        workers = (sd.get('shipment') or {}).get('construction_workers') or []
        key = ''
        for w in workers:
            s = str(w or '').strip()
            if s:
                key = s
                break
        slot = acc.setdefault(key, {'units': 0.0, 'count': 0})
        slot['units'] += _get_order_spec_units(r)
        slot['count'] += 1
    meta: dict[str, dict] = {}
    for key, slot in acc.items():
        cap = cap_by_norm.get(_normalize_worker_name(key))
        entry: dict = {
            'units': f"{slot['units']:.1f}",
            'count': slot['count'],
            'capacity': None,
            'remaining': None,
        }
        if cap is not None:
            entry['capacity'] = f"{cap:.1f}"
            entry['remaining'] = f"{cap - slot['units']:.1f}"
        meta[key] = entry
    return meta


def compute_team_remaining_units_for_date(db, target_date: str | None, worker_settings: list) -> dict[str, float]:
    """target_date의 시공팀별 잔여 자수(capacity - 사용)를 계산한다.

    대시보드 잔여 패널과 동일 정의(잔여 = 팀 capacity - 사용 자수). 사용 자수는 해당
    날짜의 시공 주문(OrderScheduleDate.kind=='construction') 중 그 팀이 배정된 주문의
    자수 합이다. target_date의 주문을 1회 조회한다(N+1 없음).

    Args:
        db: SQLAlchemy 세션.
        target_date: 'YYYY-MM-DD' 시공일 문자열. None이면 각 팀 잔여=capacity.
        worker_settings: normalize_erp_shipment_workers 결과 리스트.

    Returns:
        {팀명: 잔여 자수(float)}.
    """
    remaining: dict[str, float] = {
        w['name']: float(w.get('capacity') or 0)
        for w in worker_settings if w.get('name')
    }
    if not target_date:
        return remaining
    from models import OrderScheduleDate
    name_by_norm = {
        _normalize_worker_name(w['name']): w['name']
        for w in worker_settings if w.get('name')
    }
    orders_on_date = (
        db.query(Order)
        .filter(Order.active_filter())
        .filter(_shipment_dashboard_order_scope())
        .join(OrderScheduleDate, Order.id == OrderScheduleDate.order_id)
        .filter(
            OrderScheduleDate.kind == 'construction',
            OrderScheduleDate.date == target_date,
        )
        .distinct()
        .options(load_only(Order.id, Order.structured_data, Order.is_erp_order))
        .all()
    )
    for o in orders_on_date:
        sd = o.structured_data if isinstance(o.structured_data, dict) else {}
        workers = (sd.get('shipment') or {}).get('construction_workers') or []
        units = _get_order_spec_units(o)
        seen: set[str] = set()
        for w in workers:
            norm = _normalize_worker_name(w)
            if norm and norm in name_by_norm and norm not in seen:
                seen.add(norm)
                remaining[name_by_norm[norm]] -= units
    return remaining


@erp_shipment_page_bp.route('/shipment')
@login_required
def erp_shipment_dashboard():
    """ERP Order - 출고 대시보드 (날짜별 순수 시공 건수, AS 제외, 출고일지 스타일)"""
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    today_kst = get_today_kst()
    today_date = today_kst.strftime('%Y-%m-%d')
    today_dt = today_kst
    # Batch 3: request.args 파싱·range/single-day 파생·is_construction/mine_only는
    # parse_shipment_dashboard_filters로 분리(동작 보존). 아래는 다운스트림 호환 로컬 바인딩.
    _sf = parse_shipment_dashboard_filters(request, current_user, today_kst)
    search_q = _sf.search_q
    date_from = _sf.date_from
    date_to = _sf.date_to
    req_date = _sf.req_date
    is_construction = _sf.is_construction
    mine_only = _sf.mine_only
    use_range = _sf.use_range
    use_single_day = _sf.use_single_day
    selected_date = _sf.selected_date
    user_locked_calendar_date = _sf.user_locked_calendar_date

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
        panel_orders = [
            o for o in panel_orders
            if is_order_related_to_user(o, current_user)
        ]
    
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

    # Batch 3: panel aggregates compute는 compute_shipment_panel_aggregates(read-model)로 분리(동작 보존).
    # cache 키(_agg_key)·fingerprint(_agg_fp)·get_or_compute는 라우트가 유지 → cache hit/miss 불변.
    _agg_blob = get_or_compute_dashboard_slice(
        _agg_key,
        TTL_PANEL_ROWS,
        lambda: compute_shipment_panel_aggregates(panel_orders, range_start, range_end, worker_name_map),
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
            today_d = today_kst  # datetime.date (get_today_kst)
            future_or_today = [
                d for d in dates_with_counts
                if datetime.datetime.strptime(d, '%Y-%m-%d').date() >= today_d
            ]
            past = [
                d for d in dates_with_counts
                if datetime.datetime.strptime(d, '%Y-%m-%d').date() < today_d
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

    # Batch 3: derived 패널 stat 카드 compute는 compute_shipment_derived_template_payloads(read-model)로 분리(동작 보존).
    # cache 키(_derived_key)·fingerprint(_derived_fp)·get_or_compute는 라우트가 유지 → cache hit/miss 불변.
    _derived_blob = get_or_compute_dashboard_slice(
        _derived_key,
        TTL_PANEL_ROWS,
        lambda: compute_shipment_derived_template_payloads(
            range_start, range_end, holiday_dates, construction_counts,
            selected_date, worker_settings, assigned_workers_by_date, spec_units_by_date,
        ),
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
            rows = [
                r for r in rows
                if is_order_related_to_user(r, current_user)
            ]
    rows = rows[:300]

    enrich_shipment_rows(rows)

    apply_erp_display_fields_to_orders(rows)

    sort_shipment_rows(rows)

    tablet_ship_kpis = _compute_tablet_ship_kpis(rows)
    shipment_team_group_meta = _compute_shipment_team_group_meta(rows, worker_settings)

    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )
    mobile_queue_rows = build_shipment_mobile_queue_rows(
        db, rows, current_user, mobile_v2_active=mobile_v2_active
    )

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
        tablet_ship_kpis=tablet_ship_kpis,
        shipment_team_group_meta=shipment_team_group_meta,
    )
    _render_ms = (time.perf_counter() - _t0) * 1000.0
    response = make_response(_body)
    apply_erp_shell_fragment_headers(response, request)
    apply_ept_b7_render_headers(response, route_id="erp_shipment_dashboard", render_ms=_render_ms)
    return response


@erp_shipment_page_bp.route('/shipment/tablet-sheet/<int:order_id>')
@login_required
def erp_shipment_tablet_sheet(order_id):
    """태블릿 가로 사이드 시트용 출고 배정 fragment (단건).

    행 탭 시 tablet-domain-sheets.js가 이 URL을 로드해 사이드 시트 본문에 넣는다.
    저장은 JS가 /api/erp/shipment/update/<id>로 POST하며(construction_workers/
    construction_time/site_extra), 시공팀 사용자는 그 API가 403으로 막으므로 시트는
    조회용으로 렌더한다(GET이라 별도 권한 차단 없음). 주문 미존재 시 404.
    """
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        abort(404)

    order.structured_data = _ensure_dict(order.structured_data)  # type: ignore[assignment]
    apply_erp_display_fields_to_orders([order])

    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    shipment = sd.get('shipment') or {}
    current_workers = [
        str(w).strip() for w in (shipment.get('construction_workers') or [])
        if str(w or '').strip()
    ]
    first_current_norm = _normalize_worker_name(current_workers[0]) if current_workers else ''
    construction_time = str(shipment.get('construction_time') or '')
    memo_parts = []
    for value in (shipment.get('site_extra') or []):
        text_value = (
            str(value.get('text') or '').strip()
            if isinstance(value, dict) else str(value or '').strip()
        )
        if text_value:
            memo_parts.append(text_value)
    site_memo = ' / '.join(memo_parts)

    units = _get_order_spec_units(order)
    construction_date_raw = _get_order_construction_date(order) or ''
    target_date = construction_date_raw.split(',')[0].strip() if construction_date_raw else ''

    settings = load_erp_shipment_settings()
    worker_settings = normalize_erp_shipment_workers(settings.get('construction_workers', []))
    remaining_by_team = compute_team_remaining_units_for_date(
        db, target_date or None, worker_settings
    )
    teams = []
    for w in worker_settings:
        name = w['name']
        remaining = remaining_by_team.get(name, float(w.get('capacity') or 0))
        teams.append({
            'name': name,
            'remaining': f"{remaining:.1f}",
            'is_current': bool(first_current_norm) and _normalize_worker_name(name) == first_current_norm,
            'is_short': remaining < units,
        })

    response = make_response(render_template(
        'shipment/partials/tablet_sheet.html',
        order=order,
        customer_name=order.customer_name or '-',
        product_label=order.product or '-',
        units=f"{units:.1f}",
        construction_time=construction_time,
        site_memo=site_memo,
        construction_date=target_date,
        teams=teams,
    ))
    apply_erp_shell_fragment_headers(response, request)
    return response
