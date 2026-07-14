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
from sqlalchemy import String, cast, or_, and_, func

from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.erp_permissions import (
    build_mine_sql_filter,
    can_edit_erp,
)
from foms.services.erp_display import (
    _ensure_dict,
    _normalize_date_to_yyyymmdd,
    apply_erp_display_fields_to_orders,
    get_today_kst,
    normalize_manager_name,
    self_measurement_four_checks_done,
)
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
from foms.services.measurement_dashboard_filters import parse_measurement_dashboard_filters
from foms.services.measurement_read_model import (
    apply_measurement_dashboard_order_scope,
    compute_measurement_panel_assembly,
    compute_measurement_product_items_build,
    compute_measurement_main_rows_blob,
    hydrate_measurement_main_rows,
)
from foms.services.erp_dashboard_search import (
    LEGACY_DASHBOARD_ORDER_LIMIT,
    apply_legacy_dashboard_search_filter,
    erp_measurement_main_search_predicate,
)

erp_measurement_dashboard_bp = Blueprint(
    'erp_measurement_dashboard', __name__, url_prefix='/erp'
)


def _erp_order_search_filter(query, q):
    """고객·담당자·주소 + ERP Beta structured_data blob (전화 제외)."""
    if not q or not q.strip():
        return query
    term = f'%{q.strip()}%'
    return query.filter(erp_measurement_main_search_predicate(term))


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
    # Batch 3: request.args 파싱·use_range/use_single_day 파생·날짜창은
    # parse_measurement_dashboard_filters로 분리(동작 보존). 아래는 다운스트림 호환 로컬 바인딩.
    _mf = parse_measurement_dashboard_filters(request, today_kst)
    search_q = _mf.search_q
    date_from = _mf.date_from
    date_to = _mf.date_to
    open_map = _mf.open_map
    use_range = _mf.use_range
    use_single_day = _mf.use_single_day
    selected_date = _mf.selected_date
    range_start = _mf.range_start
    range_end = _mf.range_end
    range_start_str = _mf.range_start_str
    range_end_str = _mf.range_end_str
    manager_filter = _mf.manager_filter

    # Phase H: 대시보드 운영 화면은 최근 활성 데이터만 조회 (과거 완료건 제외)
    def _build_measurement_base(days: int):
        """days 창 기준 실측 대시보드 base_query 조립(검색+scope 동일 적용)."""
        q = db.query(Order).filter(Order.dashboard_active_filter(days=days))
        q = _erp_order_search_filter(q, search_q)
        # 자가실측 상태는 플래그 있는 주문만 포함. 지방주문(is_regional)도 실측 대시보드에 표시.
        return apply_measurement_dashboard_order_scope(q)

    # 패널용 base는 항상 60일 창 유지(패널 fingerprint에 date_from 없음 → 넓히면 캐시 오염).
    base_query = _build_measurement_base(60)
    # 리스트 계보 전용: 과거 range 조회 시 완료 60일 컷오프로 완료건이 누락되지 않게 창을 넓힌다.
    # (_main_fp/_pi_fp에는 date_from/date_to가 포함되어 리스트 캐시는 안전.)
    list_base_query = base_query
    if use_range and date_from:
        try:
            _df_date = datetime.datetime.strptime(date_from, '%Y-%m-%d').date()
            _list_days = max(60, (today_kst - _df_date).days + 1)
        except (ValueError, TypeError):
            _list_days = 60
        if _list_days > 60:
            list_base_query = _build_measurement_base(_list_days)
    query = list_base_query

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
    mine_filter_active = erp_mine_only_from_request(request) and current_user

    # mine 필터를 SQL WHERE로 적용 (Python 루프 대신)
    if mine_filter_active:
        mine_conds = build_mine_sql_filter(current_user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))

    list_query = query

    _panel_fp = {
        "v": 3,
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

    # Batch 3: panel assembly compute는 compute_measurement_panel_assembly(read-model)로 분리(동작 보존).
    # cache 키(_panel_key)·fingerprint(_panel_fp)·get_or_compute는 라우트가 유지 → cache hit/miss 불변.
    _panel_blob = get_or_compute_dashboard_slice(
        _panel_key,
        TTL_PANEL_ROWS,
        lambda: compute_measurement_panel_assembly(
            base_query, current_user, mine_filter_active, selected_date,
            range_start, range_end, range_start_str, range_end_str,
        ),
        page="measurement",
        slice_name="measurement_panel_assembly",
    )
    measurement_panel_dates = _panel_blob["panel_summary_stat_cards"]

    focus_order_id = request.args.get('focus_order', type=int)
    _main_fp = {
        "v": 3,
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
        "focus_order": focus_order_id,
    }
    _main_key = build_dashboard_cache_key("measurement", "main_rows", _main_fp)
    _main_blob = get_or_compute_dashboard_slice(
        _main_key,
        TTL_PANEL_ROWS,
        lambda: compute_measurement_main_rows_blob(
            db,
            list_base_query,
            list_query,
            current_user,
            mine_filter_active,
            selected_date,
            use_range,
            use_single_day,
            date_from,
            date_to,
            focus_order_id,
        ),
        page="measurement",
        slice_name="main_rows",
    )
    rows, row_fallback_added_ids = hydrate_measurement_main_rows(
        list_base_query,
        _main_blob,
        selected_date=selected_date,
        use_range=use_range,
        use_single_day=use_single_day,
        date_from=date_from,
        date_to=date_to,
    )

    # 담당자 필터: rows hydrate 후 Python 적용(담당자 값이 structured_data.parties.manager와
    # Order.manager_name에 분산되고 normalize_manager_name으로 정규화되므로 SQL 필터는 부정확).
    # _pi_fp(order_ids 포함) 계산 전에 적용해야 product_items 캐시 키가 올바르게 좁혀진다.
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

    if manager_filter:
        _mf_key = manager_filter.strip().lower()
        rows = [
            o for o in rows
            if (get_manager_name_for_sort(o) or '').strip().lower() == _mf_key
        ]

    _pi_fp = {
        "v": 3,
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

    # Batch 3: product_items 빌드 compute는 compute_measurement_product_items_build(read-model)로 분리(동작 보존).
    # cache 키(_pi_key)·fingerprint(_pi_fp)·get_or_compute는 라우트가 유지 → cache hit/miss 불변.
    _pi_blob = get_or_compute_dashboard_slice(
        _pi_key,
        TTL_PAYLOAD_ASSEMBLY,
        lambda: compute_measurement_product_items_build(db, rows, row_fallback_added_ids),
        page="measurement",
        slice_name="measurement_product_items_build",
    )
    _pi_by_id = _pi_blob.get("product_items_by_id") or {}
    for o in rows:
        o.product_items = _pi_by_id.get(str(o.id), [])

    # get_manager_name_for_sort는 담당자 필터 적용 지점(hydrate 직후)에서 이미 정의됨.
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
    from foms.services.feature_flags import (
        is_mobile_v2_shell,
        resolve_shell_variant_cached,
    )
    from foms.services.erp_mobile_order_display import (
        build_mobile_queue_batch_context,
        build_mobile_queue_order_row,
    )
    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )
    mobile_queue_rows = []
    if mobile_v2_active:
        # W2-3(N+1 제거): 행당 ~5쿼리(첨부/미리보기/타임라인/담당자) 대신 배치 1회 조회.
        # 출고 대시보드(build_shipment_mobile_queue_rows)와 동일 패턴. mobile_v2 비활성이면
        # 이 블록 자체가 실행되지 않아 불필요 쿼리가 없다.
        _batch_ctx = build_mobile_queue_batch_context(db, rows)
        for _o in rows:
            _row = build_mobile_queue_order_row(db, _o, current_user, batch_ctx=_batch_ctx)
            # 실측은 담당이 user id로 저장되는 케이스가 있어 표시명으로 정규화
            _mgr = normalize_manager_name(
                ((_o.structured_data or {}).get('parties') or {}).get('manager'),
                getattr(_o, 'manager_name', None),
            )
            if _mgr:
                _row['manager_name'] = _mgr
            mobile_queue_rows.append(_row)

    # 태블릿 가로 코호트 좌측 큐(W12): 스테이지 색배지 + 날짜버킷(오늘/주간/미확정) + 완료 dim.
    # 이미 로드된 rows만 재사용(신규 쿼리 0). split 표시 게이트(erp_mobile_v2_enabled +
    # coarse-landscape MQ)와 독립적으로 항상 파생한다 — 코호트 판정이 컨텍스트 프로세서(request
    # 반영)와 라우트(mobile_v2_active)에서 미세하게 갈릴 수 있어, split 이 렌더되면 배지·버킷이
    # 항상 존재하도록 무조건 계산한다. 스테이지 색은 SSOT(stage_badge_modifier) 재사용.
    from foms.services.erp_display import _erp_get_stage
    from foms.services.erp_mobile_order_display import (
        stage_badge_label as _stage_badge_label,
        stage_badge_modifier as _stage_badge_modifier,
    )
    tablet_card_view: dict[int, dict] = {}
    tablet_bucket_counts = {"all": 0, "today": 0, "week": 0, "undated": 0}
    for _o in rows:
        _stage = _erp_get_stage(_o, _o.structured_data or {})
        _mdate_raw = getattr(_o, "measurement_date", None)
        _days = None
        if _mdate_raw:
            try:
                _d = datetime.datetime.strptime(
                    str(_mdate_raw).split(",")[0].strip(), "%Y-%m-%d"
                ).date()
                _days = (_d - today_kst).days
            except (ValueError, TypeError):
                _days = None
        tablet_card_view[_o.id] = {
            "stage_modifier": _stage_badge_modifier(_stage),
            "stage_label": _stage_badge_label(_stage),
            "days": _days,
            "completed": bool(
                getattr(_o, "measurement_completed", False)
                or getattr(_o, "status", "") in ("COMPLETED", "AS_COMPLETED")
            ),
        }
        tablet_bucket_counts["all"] += 1
        if _days is None:
            tablet_bucket_counts["undated"] += 1
        else:
            if _days == 0:
                tablet_bucket_counts["today"] += 1
            if 0 <= _days <= 6:
                tablet_bucket_counts["week"] += 1

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
            manager_filter=manager_filter,
            rows=rows,
            mobile_queue_rows=mobile_queue_rows,
            tablet_card_view=tablet_card_view,
            tablet_bucket_counts=tablet_bucket_counts,
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


# 지방 대시보드 "상차 예정 알림" 지역(시/도) 정렬용 상수.
# export JS(static/js/measurement/regional-shipping-export.js)의
# REGION_ORDER/REGION_CANON을 그대로 포팅 — 화면 대시보드와 이미지 저장이
# 같은 순서를 내도록 한 기준으로 통일한다. 순서가 어긋나면 두 출력이 갈리므로
# export JS 상수를 정본으로 삼아 동일하게 유지해야 한다.
_REGIONAL_REGION_ORDER = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
]
_REGIONAL_REGION_CANON = {
    "서울": "서울", "서울특별시": "서울",
    "부산": "부산", "부산광역시": "부산",
    "대구": "대구", "대구광역시": "대구",
    "인천": "인천", "인천광역시": "인천",
    "광주": "광주", "광주광역시": "광주",
    "대전": "대전", "대전광역시": "대전",
    "울산": "울산", "울산광역시": "울산",
    "세종": "세종", "세종시": "세종", "세종특별자치시": "세종",
    "경기": "경기", "경기도": "경기",
    "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북",
    "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북",
    "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북",
    "경남": "경남", "경상남도": "경남",
    "제주": "제주", "제주도": "제주", "제주특별자치도": "제주",
}


def _regional_region_index(address: str | None) -> int:
    """주소 첫 공백토큰 → 시/도(canonical) → 정렬 인덱스. 미인식·빈주소는 999.

    export JS regionOf+regionIndex와 동일 규칙(양쪽 정렬 순서 일치 필수).

    :param address: 주문 주소 문자열(None 가능).
    :returns: REGION_ORDER 인덱스(0~16), 미인식/빈값은 999.
    """
    stripped = str(address).strip() if address else ""
    if not stripped:
        return 999
    canon = _REGIONAL_REGION_CANON.get(stripped.split()[0])
    if canon is None:
        return 999
    return _REGIONAL_REGION_ORDER.index(canon)


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
        base_query = apply_legacy_dashboard_search_filter(
            base_query,
            search_query,
            extra_columns=(Order.product, Order.regional_memo, Order.notes),
            include_phone=True,
            include_manager=False,
        )

    all_regional_orders = (
        base_query.order_by(Order.id.desc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()
    )
    apply_erp_display_fields_to_orders(all_regional_orders)
    today = get_today_kst()

    completed_orders = [o for o in all_regional_orders if o.status == "COMPLETED"]
    scheduled_orders = [o for o in all_regional_orders if o.status == "SCHEDULED"]
    hold_orders = [o for o in all_regional_orders if o.status == "ON_HOLD"]
    excluded_from_shipping_buckets = ["COMPLETED", "ON_HOLD", "SCHEDULED"]

    shipping_alerts = []
    for order in all_regional_orders:
        is_as_rework_shipping = order.status == "AS_RECEIVED"
        if (
            (getattr(order, "measurement_completed", False) or is_as_rework_shipping)
            and order.shipping_scheduled_date
            and order.shipping_scheduled_date.strip()
            and order.status not in excluded_from_shipping_buckets
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
            and order.status not in excluded_from_shipping_buckets
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
            o.status not in excluded_from_shipping_buckets
            and o.id not in shipping_alert_ids
            and o.id not in shipping_completed_ids
            and (
                not getattr(o, "measurement_completed", False)
                or not o.shipping_scheduled_date
                or not o.shipping_scheduled_date.strip()
            )
        )
    ]

    def _shipping_alert_sort_key(order) -> tuple:
        """상차 예정 알림 정렬 키: 상차일→지역→설치일→주소.

        export JS(regional-shipping-export.js) collectVisibleRows와 동일 기준으로
        화면·이미지 저장 정렬을 통일한다. 상차일/설치일은 YYYY-MM-DD 문자열 사전순
        비교(상차일은 필터로 이미 유효). 빈 설치일은 그룹 맨 뒤('9999-12-31'),
        주소 None은 빈 문자열로 방어한다.

        :param order: Order (문자열 속성 shipping_scheduled_date/scheduled_date/address).
        :returns: (상차일, 지역인덱스, 설치일키, 주소) 튜플.
        """
        scheduled = (order.scheduled_date or "").strip() or "9999-12-31"
        return (
            order.shipping_scheduled_date or "",
            _regional_region_index(order.address),
            scheduled,
            order.address or "",
        )

    shipping_alerts.sort(key=_shipping_alert_sort_key)
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
        return apply_legacy_dashboard_search_filter(
            q,
            search_query,
            extra_columns=(Order.product, Order.notes),
            include_phone=True,
            include_manager=True,
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
    ).order_by(Order.measurement_date.asc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()
    urgent_alerts = [o for o in urgent_candidates if _measurement_dates_include_today(o)]

    measurement_candidates = get_filtered_orders(
        base_query.filter(
            Order.status.in_(["MEASURED"]),
            Order.measurement_date != None,
            Order.measurement_date != "",
            or_(Order.scheduled_date == None, Order.scheduled_date == ""),
        )
    ).order_by(Order.measurement_date.asc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()
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
    ).order_by(Order.measurement_date.asc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()
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
    ).order_by(Order.scheduled_date.asc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()
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
    ).order_by(Order.created_at.desc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()

    hold_orders = get_filtered_orders(
        db.query(Order).filter(
            Order.status == "ON_HOLD",
            Order.is_regional == False,
        )
    ).order_by(Order.created_at.desc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()

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
        base_query = apply_legacy_dashboard_search_filter(
            base_query,
            search_query,
            extra_columns=(Order.product, Order.notes),
            include_phone=True,
            include_manager=False,
        )

    all_orders = base_query.order_by(Order.id.desc()).limit(LEGACY_DASHBOARD_ORDER_LIMIT).all()
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
