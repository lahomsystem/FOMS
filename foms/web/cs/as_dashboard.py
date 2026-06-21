"""ERP AS 대시보드 (ERP-SLIM-8; canonical, SFC-B11B). /erp/as."""
import time
from flask import Blueprint, make_response, render_template, request, redirect, url_for, g
from db import get_db
from models import Order, OrderAttachment
from foms.web.auth import login_required
from sqlalchemy import or_, and_, cast, String, func, case
import datetime

from foms.services.erp_display import _normalize_for_search
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from foms.services.as_content_safety import sanitize_as_content_html
from foms.services.as_dashboard_display import (
    as_stage_badge_modifier,
    as_thumb_enabled,
    batch_resolve_as_thumbnail_urls,
)
from foms.services.feature_flags import is_enabled_for_user
from foms.services.common.erp_shell_http import (
    apply_erp_shell_fragment_headers,
    wants_erp_shell_tab_body,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.request_utils import get_search_query_arg


erp_as_page_bp = Blueprint('erp_as_page', __name__, url_prefix='/erp')


def _compact_search_text(value):
    """검색 비교용 문자열 정규화 (NFC + 공백 제거 + 소문자)."""
    normalized = _normalize_for_search(value)
    if not normalized:
        return ''
    return ''.join(normalized.split()).lower()


def _sql_compact(expr, *, use_postgres_regex=False):
    """DB 비교용 공백 제거 식."""
    expr = func.coalesce(cast(expr, String), '')
    if use_postgres_regex:
        return func.lower(func.regexp_replace(expr, r'\s+', '', 'g'))
    return func.lower(
        func.replace(
            func.replace(
                func.replace(
                    func.replace(expr, ' ', ''),
                    '\n', ''
                ),
                '\r', ''
            ),
            '\t', ''
        )
    )


def _json_text_expr(*path_parts, dialect_name=''):
    """DB dialect에 맞춰 JSON 경로의 텍스트 값을 추출."""
    if dialect_name == 'postgresql':
        return func.jsonb_extract_path_text(Order.structured_data, *path_parts)
    if dialect_name == 'sqlite':
        return func.json_extract(Order.structured_data, '$.' + '.'.join(path_parts))
    return cast(Order.structured_data, String)


def _as_content_expr(field_name='as_content', *, dialect_name='', use_postgres_regex=False):
    """structured_data.shipment AS 내용 필드 추출 (검색/탭 판정용)."""
    expr = _json_text_expr('shipment', field_name, dialect_name=dialect_name)
    expr = func.coalesce(cast(expr, String), '')
    if dialect_name == 'postgresql' and use_postgres_regex:
        expr = func.regexp_replace(expr, r'<[^>]+>', '', 'g')
    return expr


def _combined_as_content_expr(*, dialect_name='', use_postgres_regex=False):
    """AS 내용 1/2 탭을 합쳐 검색용 문자열로 반환."""
    primary = _as_content_expr(
        'as_content',
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres_regex,
    )
    secondary = _as_content_expr(
        'as_content_2',
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres_regex,
    )
    return func.trim(primary + case((secondary != '', ' '), else_='') + secondary)


def _sales_delivery_expr(*, dialect_name=''):
    """structured_data.shipment.sales_delivery 추출 (탭 분류용)."""
    return func.coalesce(
        cast(_json_text_expr('shipment', 'sales_delivery', dialect_name=dialect_name), String),
        'false'
    )


def _display_customer_name_expr(*, dialect_name=''):
    return func.coalesce(
        cast(_json_text_expr('parties', 'customer', 'name', dialect_name=dialect_name), String),
        Order.customer_name,
    )


def _display_manager_name_expr(*, dialect_name=''):
    return func.coalesce(
        cast(_json_text_expr('parties', 'manager', 'name', dialect_name=dialect_name), String),
        Order.manager_name,
    )


def _display_phone_expr(*, dialect_name=''):
    return func.coalesce(
        cast(_json_text_expr('parties', 'customer', 'phone', dialect_name=dialect_name), String),
        Order.phone,
    )


def _display_address_expr(*, dialect_name=''):
    address_full = cast(_json_text_expr('site', 'address_full', dialect_name=dialect_name), String)
    address_main = func.coalesce(cast(_json_text_expr('site', 'address_main', dialect_name=dialect_name), String), '')
    address_detail = func.coalesce(cast(_json_text_expr('site', 'address_detail', dialect_name=dialect_name), String), '')
    address_joined = func.trim(
        address_main + case((address_detail != '', ' '), else_='') + address_detail
    )
    return func.coalesce(address_full, func.nullif(address_joined, ''), Order.address)


def _is_sales_delivery_search(compact_q):
    """영업/택배 전용 검색어인지 판별."""
    return (compact_q or '').replace('/', '') == '영업택배'


def _sales_delivery_true_filter(sales_delivery_expr):
    """영업/택배 체크된 주문 필터."""
    return func.lower(cast(sales_delivery_expr, String)).in_(['true', '1', 'yes'])


def _as_pending_expr(*, dialect_name=''):
    """structured_data.shipment.as_pending 추출 (집계용)."""
    return func.coalesce(
        cast(_json_text_expr('shipment', 'as_pending', dialect_name=dialect_name), String),
        'false'
    )


def _as_visit_date_expr(*, dialect_name=''):
    """structured_data.schedule.as_visit.date 추출 (집계용)."""
    return func.coalesce(
        cast(_json_text_expr('schedule', 'as_visit', 'date', dialect_name=dialect_name), String),
        ''
    )


def _has_text_value(expr):
    """빈 문자열이 아닌 값 판정용 SQL 식."""
    return func.trim(func.coalesce(cast(expr, String), '')) != ''


def _order_is_sales_delivery(order):
    """주문이 영업/택배 탭 소속인지 판별."""
    sd = _ensure_dict(getattr(order, 'structured_data', None))
    shipment = sd.get('shipment') or {}
    return shipment.get('sales_delivery') is True


def _normalize_construction_worker_names(value):
    """Return display-ready construction worker names from legacy or ERP payloads."""
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value or '').replace('\n', ',').split(',')

    workers = []
    for item in raw_values:
        if isinstance(item, dict):
            raw_name = item.get('name') or item.get('text') or item.get('value') or ''
        else:
            raw_name = item
        name = str(raw_name or '').strip()
        if name and name not in workers:
            workers.append(name)
    return workers


def _erp_order_search_filter(query, q, *, dialect_name='', use_postgres_regex=False):
    """고객명·전화·주소·내용 전체 검색 (공백 무시 + AS 내용 포함)."""
    compact_q = _compact_search_text(q)
    if not compact_q:
        return query
    term = f'%{compact_q}%'
    as_content = _combined_as_content_expr(
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres_regex,
    )
    customer_name = _display_customer_name_expr(dialect_name=dialect_name)
    manager_name = _display_manager_name_expr(dialect_name=dialect_name)
    phone = _display_phone_expr(dialect_name=dialect_name)
    address = _display_address_expr(dialect_name=dialect_name)
    return query.filter(
        or_(
            _sql_compact(cast(Order.id, String), use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(customer_name, use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(manager_name, use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(phone, use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(address, use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(Order.product, use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(Order.notes, use_postgres_regex=use_postgres_regex).ilike(term),
            _sql_compact(as_content, use_postgres_regex=use_postgres_regex).ilike(term),
        )
    )


def _erp_as_tab_for_order(order):
    """주문이 기본적으로 속해야 하는 AS 상태 탭 계산."""
    if order.status == 'AS_COMPLETED' and order.as_completed_date not in (None, ''):
        return 'completed'
    if _order_is_sales_delivery(order):
        return 'sales_delivery'
    return 'incomplete'


def _erp_as_incomplete_filter(query):
    """AS 미완료 탭 공통 필터."""
    return query.filter(_erp_as_incomplete_condition())


def _erp_as_completed_condition():
    """AS 완료 탭 공통 조건."""
    return and_(
        Order.status == 'AS_COMPLETED',
        Order.as_completed_date.isnot(None),
        Order.as_completed_date != ''
    )


def _count_cases(query, *definitions):
    """여러 조건의 집계를 한 번에 계산한다."""
    columns = [
        func.coalesce(func.sum(case((condition, 1), else_=0)), 0).label(name)
        for name, condition in definitions
    ]
    row = query.with_entities(*columns).one()
    return {
        name: int(getattr(row, name) or 0)
        for name, _condition in definitions
    }


def _erp_as_incomplete_condition():
    """AS 미완료 탭 공통 조건."""
    return or_(
        Order.status == 'AS',
        Order.status == 'AS_RECEIVED',
        and_(
            Order.status == 'AS_COMPLETED',
            or_(
                Order.as_completed_date.is_(None),
                Order.as_completed_date == ''
            )
        )
    )


@erp_as_page_bp.route('/as')
@login_required
def erp_as_dashboard():
    """ERP Order - AS 대시보드 (MVP: AS 상태 주문 리스트)"""
    db = get_db()
    status_filter = (request.args.get('status') or '').strip()
    search_q = get_search_query_arg('q', 'search', 'manager')
    selected_date = request.args.get('date')
    open_map = request.args.get('open_map') == '1'
    tab = (request.args.get('tab') or 'incomplete').strip()
    
    if tab not in ('incomplete', 'completed', 'sales_delivery'):
        tab = 'incomplete'

    if open_map:
        date_val = selected_date or get_today_kst().strftime('%Y-%m-%d')
        status_val = status_filter or 'ALL'
        return redirect(url_for('erp_map.map_view', date=date_val, status=status_val))

    bind = db.get_bind() if hasattr(db, 'get_bind') else None
    dialect_name = ((bind.dialect.name or '') if bind and bind.dialect else '').lower()
    use_postgres = dialect_name == 'postgresql'
    sales_delivery = _sales_delivery_expr(dialect_name=dialect_name)
    sales_delivery_true = _sales_delivery_true_filter(sales_delivery)
    as_pending_true = _sales_delivery_true_filter(_as_pending_expr(dialect_name=dialect_name))
    as_visit_date_present = _has_text_value(_as_visit_date_expr(dialect_name=dialect_name))
    customer_name_expr = _display_customer_name_expr(dialect_name=dialect_name)

    base_query = db.query(Order).filter(Order.active_filter())
    base_query = base_query.filter(Order.status.in_(['AS', 'AS_RECEIVED', 'AS_COMPLETED']))

    if status_filter:
        base_query = base_query.filter(Order.status == status_filter)

    current_user = getattr(g, 'current_user', None)
    erp_mine_only = erp_mine_only_from_request(request)
    if erp_mine_only and current_user:
        u_name = (current_user.name or '').strip()
        u_username = (current_user.username or '').strip()
        manager_name_expr = func.coalesce(
            cast(_json_text_expr('parties', 'manager', 'name', dialect_name=dialect_name), String),
            ''
        )
        conds = []
        if u_name:
            conds.append(Order.manager_name.ilike(f"%{u_name}%"))
            conds.append(and_(Order.is_erp_order == True, manager_name_expr.ilike(f"%{u_name}%")))
        if u_username:
            conds.append(Order.manager_name.ilike(f"%{u_username}%"))
            conds.append(and_(Order.is_erp_order == True, manager_name_expr.ilike(f"%{u_username}%")))
        if conds:
            base_query = base_query.filter(or_(*conds))

    compact_q = _compact_search_text(search_q)
    focus_order_id = request.args.get('focus_order', type=int)
    if compact_q and focus_order_id is None and _is_sales_delivery_search(compact_q):
        return redirect(url_for(
            'erp_as_page.erp_as_dashboard',
            tab='sales_delivery',
            status='',
            q='',
            sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
            mine='1' if erp_mine_only else '',
        ))
    if compact_q and focus_order_id is None:
        # 이름 검색 단건은 "정확한 고객명 일치 1건"이면서 "전체 검색 결과도 1건"일 때만 자동 이동
        filtered_preview_rows = _erp_order_search_filter(
            base_query,
            search_q,
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres,
        ).order_by(Order.id.desc()).limit(2).all()
        name_match_rows = base_query.filter(
            _sql_compact(customer_name_expr, use_postgres_regex=use_postgres) == compact_q
        ).order_by(Order.id.desc()).limit(2).all()
        if (
            len(name_match_rows) == 1
            and len(filtered_preview_rows) == 1
            and int(name_match_rows[0].id) == int(filtered_preview_rows[0].id)  # type: ignore[arg-type]
        ):
            only_order = name_match_rows[0]
            target_tab = _erp_as_tab_for_order(only_order)
            return redirect(url_for(
                'erp_as_page.erp_as_dashboard',
                tab=target_tab,
                status=only_order.status or '',
                q=search_q,
                sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
                mine='1' if erp_mine_only else '',
                focus_order=only_order.id,
            ))

    if focus_order_id:
        focus_row = base_query.filter(Order.id == focus_order_id).first()
        if focus_row:
            target_tab = _erp_as_tab_for_order(focus_row)
            if tab != target_tab:
                return redirect(url_for(
                    'erp_as_page.erp_as_dashboard',
                    tab=target_tab,
                    status=status_filter,
                    q=search_q,
                    sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
                    mine='1' if erp_mine_only else '',
                    focus_order=focus_order_id,
                ))
        filtered_base_query = base_query.filter(Order.id == focus_order_id)
    elif compact_q:
        filtered_base_query = _erp_order_search_filter(
            base_query,
            search_q,
            dialect_name=dialect_name,
            use_postgres_regex=use_postgres,
        )
    else:
        filtered_base_query = base_query

    incomplete_non_sales_condition = and_(
        _erp_as_incomplete_condition(),
        ~sales_delivery_true,
    )
    sales_delivery_condition = and_(
        _erp_as_incomplete_condition(),
        sales_delivery_true,
    )

    # 미완료 stats 칩 → 버킷 필터(방문확정/미결/미정). 요약 집계와 필터가 같은 조건을
    # 단일 출처(SSOT)로 공유해 칩 카운트와 실제 목록 결과가 항상 일치하게 한다.
    incomplete_buckets = {
        'visit_confirmed': and_(incomplete_non_sales_condition, ~as_pending_true, as_visit_date_present),
        'pending': and_(incomplete_non_sales_condition, as_pending_true),
        'unassigned': and_(incomplete_non_sales_condition, ~as_pending_true, ~as_visit_date_present),
    }
    as_bucket = (request.args.get('bucket') or '').strip()
    if tab != 'incomplete' or as_bucket not in incomplete_buckets:
        as_bucket = ''  # 'total'·빈값·타 탭 → 버킷 필터 없음(전체 미완료)

    as_tab_counts = _count_cases(
        filtered_base_query,
        ('sales_delivery', sales_delivery_condition),
        ('incomplete', incomplete_non_sales_condition),
        ('completed', _erp_as_completed_condition()),
    )
    as_incomplete_summary = _count_cases(
        filtered_base_query,
        ('total', incomplete_non_sales_condition),
        ('visit_confirmed', incomplete_buckets['visit_confirmed']),
        ('pending', incomplete_buckets['pending']),
        ('unassigned', incomplete_buckets['unassigned']),
    )

    # 하단 탭: 완료 안된 건 vs 완료 된 건 vs 전체
    query = filtered_base_query
    if tab == 'completed':
        query = query.filter(_erp_as_completed_condition())
    elif tab == 'sales_delivery':
        query = query.filter(sales_delivery_condition)
    else:
        # 완료 안된 건(X): AS 미완료 중 영업/택배로 분류되지 않은 주문만 표시
        query = query.filter(incomplete_non_sales_condition)
        if as_bucket:
            # stats 칩에서 고른 버킷(방문확정/미결/미정)으로 추가 좁힘
            query = query.filter(incomplete_buckets[as_bucket])

    sort_dir = (request.args.get('sort_dir') or 'desc').strip().lower()
    if sort_dir != 'asc':
        sort_dir = 'desc'
    order_col = Order.as_received_date
    total_orders = int(as_tab_counts.get(tab, 0))
    if as_bucket:
        # 버킷 필터 시 헤더 건수·페이지 수도 좁혀진 결과 기준으로
        total_orders = int(as_incomplete_summary.get(as_bucket, 0))
    sort_clauses = []
    if focus_order_id:
        sort_clauses.append(case((Order.id == focus_order_id, 0), else_=1))
    if sort_dir == 'desc':
        sort_clauses.extend([order_col.desc().nullslast(), Order.id.desc()])
    else:
        sort_clauses.extend([order_col.asc().nullsfirst(), Order.id.desc()])
    query = query.order_by(*sort_clauses)

    # Pagination
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = 100
    total_pages = (total_orders + per_page - 1) // per_page
    if total_pages and page > total_pages:
        page = total_pages

    rows = query.offset((page - 1) * per_page).limit(per_page).all()

    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]
    apply_erp_display_fields_to_orders(rows)
    # AS 카테고리 첨부가 있는 주문 ID 집합 (버튼 색상: 있음=파란색, 없음=분홍 파스텔)
    order_ids = [r.id for r in rows]
    as_photo_order_ids = set()
    if order_ids:
        as_with_photos = db.query(OrderAttachment.order_id).filter(
            OrderAttachment.order_id.in_(order_ids),
            OrderAttachment.category == 'as'
        ).distinct().all()
        as_photo_order_ids = {x[0] for x in as_with_photos}
    mobile_v2_active = is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        current_user.id if current_user else None,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    thumb_flag = as_thumb_enabled(mobile_v2_active=mobile_v2_active)
    thumb_urls = batch_resolve_as_thumbnail_urls(order_ids, db) if order_ids else {}
    for r in rows:
        r.has_as_photos = r.id in as_photo_order_ids
        shipment = r.structured_data.get('shipment') or {}
        r.as_pending = shipment.get('as_pending') is True
        r.has_as_blueprint = shipment.get('as_blueprint') is True
        r.is_sales_delivery = shipment.get('sales_delivery') is True
        r.construction_workers = _normalize_construction_worker_names(
            shipment.get('construction_workers')
        )
        r.construction_workers_text = ', '.join(r.construction_workers)
        r.as_content_html = sanitize_as_content_html(shipment.get('as_content'))
        has_secondary_as_content = 'as_content_2' in shipment
        secondary_as_content_html = sanitize_as_content_html(shipment.get('as_content_2'))
        if not has_secondary_as_content and not secondary_as_content_html:
            secondary_as_content_html = sanitize_as_content_html(getattr(r, 'notes', '') or '')
        r.as_content_2_html = secondary_as_content_html
        r.as_thumb_enabled = thumb_flag
        r.thumbnail_url = thumb_urls.get(r.id) if thumb_flag else None
        r.stage_badge_modifier = as_stage_badge_modifier(
            status=str(r.status or ""),
            as_pending=bool(r.as_pending),
        )
    # 시공자가 아닌 사용자만 AS 카테고리 사진 조회 가능 (관리자 등)
    can_view_as_photos = not (current_user and (current_user.team or '').strip() == 'CONSTRUCTION')

    template_name = (
        'cs/partials/as_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'cs/as_dashboard.html'
    )
    _t0 = time.perf_counter()
    _body = render_template(
        template_name,
        status_filter=status_filter,
        search_q=search_q,
        selected_date=selected_date,
        rows=rows,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=erp_mine_only,
        can_view_as_photos=can_view_as_photos,
        sort_dir=sort_dir,
        as_tab=tab,
        as_tab_counts=as_tab_counts,
        as_incomplete_summary=as_incomplete_summary,
        as_bucket=as_bucket,
        compact_search_q=compact_q,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        total_orders=total_orders,
    )
    _render_ms = (time.perf_counter() - _t0) * 1000.0
    response = make_response(_body)
    apply_erp_shell_fragment_headers(response, request)
    apply_ept_b7_render_headers(response, route_id="erp_as_dashboard", render_ms=_render_ms)
    return response
