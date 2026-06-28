"""ERP AS 대시보드 (ERP-SLIM-8; canonical, SFC-B11B). /erp/as."""
import time
from flask import Blueprint, make_response, render_template, request, redirect, url_for, g
from db import get_db
from models import Order, OrderAttachment
from foms.web.auth import login_required
from sqlalchemy import or_, and_, cast, String, case
import datetime

from foms.services.erp_display import _normalize_for_search
from foms.services.common.erp_mine_filter import erp_mine_only_from_request
from foms.services.erp_permissions import build_mine_sql_filter, can_edit_erp
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
from foms.services.as_dashboard_filters import parse_as_dashboard_filters
from foms.services.as_dashboard_helpers import (
    _as_pending_expr,
    _as_visit_date_expr,
    _combined_as_content_expr,
    _display_address_expr,
    _display_customer_name_expr,
    _display_manager_name_expr,
    _display_phone_expr,
    _erp_as_completed_condition,
    _erp_as_incomplete_condition,
    _has_text_value,
    _sales_delivery_expr,
    _sales_delivery_true_filter,
    _sql_compact,
)
from foms.services.as_dashboard_read_model import build_as_tab_count_context


erp_as_page_bp = Blueprint('erp_as_page', __name__, url_prefix='/erp')


def _compact_search_text(value):
    """검색 비교용 문자열 정규화 (NFC + 공백 제거 + 소문자)."""
    normalized = _normalize_for_search(value)
    if not normalized:
        return ''
    return ''.join(normalized.split()).lower()


def _is_sales_delivery_search(compact_q):
    """영업/택배 전용 검색어인지 판별."""
    return (compact_q or '').replace('/', '') == '영업택배'


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


@erp_as_page_bp.route('/as')
@login_required
def erp_as_dashboard():
    """ERP Order - AS 대시보드 (MVP: AS 상태 주문 리스트)"""
    db = get_db()
    # Batch 5: 상단 request.args 파싱·tab 화이트리스트는 parse_as_dashboard_filters로 분리(동작 보존).
    _af = parse_as_dashboard_filters(request)
    status_filter = _af.status_filter
    search_q = _af.search_q
    selected_date = _af.selected_date
    open_map = _af.open_map
    tab = _af.tab

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
        conds = build_mine_sql_filter(current_user)
        if conds:
            base_query = base_query.filter(or_(*conds))
        else:
            base_query = base_query.filter(Order.id == -1)

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

    as_count_context = build_as_tab_count_context(
        filtered_base_query,
        tab=tab,
        bucket=request.args.get('bucket'),
        incomplete_non_sales_condition=incomplete_non_sales_condition,
        sales_delivery_condition=sales_delivery_condition,
        as_pending_true=as_pending_true,
        as_visit_date_present=as_visit_date_present,
    )
    incomplete_buckets = as_count_context["incomplete_buckets"]
    as_bucket = as_count_context["as_bucket"]
    as_tab_counts = as_count_context["as_tab_counts"]
    as_incomplete_summary = as_count_context["as_incomplete_summary"]

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
