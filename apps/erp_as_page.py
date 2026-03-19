"""
ERP AS 대시보드 페이지 (ERP-SLIM-8)
erp.py에서 분리: /erp/as
"""
from flask import Blueprint, render_template, request, redirect, url_for, g
from db import get_db
from models import Order, OrderAttachment
from apps.auth import login_required
from sqlalchemy import or_, and_, cast, String, func, case
import datetime

from apps.erp import _normalize_for_search
from services.erp_permissions import can_edit_erp
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from services.as_content_safety import sanitize_as_content_html


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


def _as_content_expr(*, dialect_name='', use_postgres_regex=False):
    """structured_data.shipment.as_content 추출 (검색/탭 판정용)."""
    expr = _json_text_expr('shipment', 'as_content', dialect_name=dialect_name)
    expr = func.coalesce(cast(expr, String), '')
    if dialect_name == 'postgresql' and use_postgres_regex:
        expr = func.regexp_replace(expr, r'<[^>]+>', '', 'g')
    return expr


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


def _order_is_sales_delivery(order):
    """주문이 영업/택배 탭 소속인지 판별."""
    sd = _ensure_dict(getattr(order, 'structured_data', None))
    shipment = sd.get('shipment') or {}
    return shipment.get('sales_delivery') is True


def _erp_order_search_filter(query, q, *, dialect_name='', use_postgres_regex=False):
    """고객명·전화·주소·내용 전체 검색 (공백 무시 + AS 내용 포함)."""
    compact_q = _compact_search_text(q)
    if not compact_q:
        return query
    term = f'%{compact_q}%'
    as_content = _as_content_expr(
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
    return query.filter(
        or_(
            Order.status == 'AS_RECEIVED',
            and_(
                Order.status == 'AS_COMPLETED',
                or_(
                    Order.as_completed_date.is_(None),
                    Order.as_completed_date == ''
                )
            )
        )
    )


@erp_as_page_bp.route('/as')
@login_required
def erp_as_dashboard():
    """ERP Beta - AS 대시보드 (MVP: AS 상태 주문 리스트)"""
    db = get_db()
    status_filter = (request.args.get('status') or '').strip()
    search_q = (request.args.get('q') or request.args.get('manager') or '').strip()
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
    customer_name_expr = _display_customer_name_expr(dialect_name=dialect_name)

    base_query = db.query(Order).filter(Order.active_filter())
    base_query = base_query.filter(Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']))

    if status_filter:
        base_query = base_query.filter(Order.status == status_filter)

    current_user = getattr(g, 'current_user', None)
    erp_mine_only = request.args.get('mine') == '1'
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
            conds.append(and_(Order.is_erp_beta == True, manager_name_expr.ilike(f"%{u_name}%")))
        if u_username:
            conds.append(Order.manager_name.ilike(f"%{u_username}%"))
            conds.append(and_(Order.is_erp_beta == True, manager_name_expr.ilike(f"%{u_username}%")))
        if conds:
            base_query = base_query.filter(or_(*conds))

    compact_q = _compact_search_text(search_q)
    if compact_q and request.args.get('focus_order') is None and _is_sales_delivery_search(compact_q):
        return redirect(url_for(
            'erp_as_page.erp_as_dashboard',
            tab='sales_delivery',
            status='',
            q='',
            sort_dir=(request.args.get('sort_dir') or 'desc').strip().lower(),
            mine='1' if request.args.get('mine') == '1' else '',
        ))
    if compact_q and request.args.get('focus_order') is None:
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
                mine='1' if request.args.get('mine') == '1' else '',
                focus_order=only_order.id,
            ))

    # 하단 탭: 완료 안된 건 vs 완료 된 건 vs 전체
    query = base_query
    if tab == 'completed':
        query = query.filter(
            Order.status == 'AS_COMPLETED',
            Order.as_completed_date.isnot(None),
            Order.as_completed_date != ''
        )
    elif tab == 'sales_delivery':
        query = _erp_as_incomplete_filter(query).filter(
            sales_delivery_true
        )
    else:
        # 완료 안된 건(X): AS 미완료 중 영업/택배로 분류되지 않은 주문만 표시
        query = _erp_as_incomplete_filter(query).filter(~sales_delivery_true)

    query = _erp_order_search_filter(
        query,
        search_q,
        dialect_name=dialect_name,
        use_postgres_regex=use_postgres,
    )

    sort_dir = (request.args.get('sort_dir') or 'desc').strip().lower()
    if sort_dir != 'asc':
        sort_dir = 'desc'
    order_col = Order.as_received_date
    focus_order_id = request.args.get('focus_order', type=int)
    total_orders = query.order_by(None).count()
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
    for r in rows:
        r.has_as_photos = r.id in as_photo_order_ids
        shipment = r.structured_data.get('shipment') or {}
        r.as_pending = shipment.get('as_pending') is True
        r.is_sales_delivery = shipment.get('sales_delivery') is True
        r.as_content_html = sanitize_as_content_html(shipment.get('as_content'))
    # 시공자가 아닌 사용자만 AS 카테고리 사진 조회 가능 (관리자 등)
    can_view_as_photos = not (current_user and (current_user.team or '').strip() == 'CONSTRUCTION')
    return render_template(
        'erp_as_dashboard.html',
        status_filter=status_filter,
        search_q=search_q,
        selected_date=selected_date,
        rows=rows,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=erp_mine_only,
        can_view_as_photos=can_view_as_photos,
        sort_dir=sort_dir,
        as_tab=tab,
        compact_search_q=compact_q,
        page=page,
        total_pages=total_pages,
        total_orders=total_orders,
    )
