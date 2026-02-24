"""
ERP AS 대시보드 페이지 (ERP-SLIM-8)
erp.py에서 분리: /erp/as
"""
from flask import Blueprint, render_template, request, session, redirect, url_for
from db import get_db
from models import Order
from apps.auth import login_required, get_user_by_id
from sqlalchemy import or_, and_, cast, String
import datetime

from services.erp_permissions import can_edit_erp
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders, get_today_kst
from services.erp_shipment_settings import is_order_mine_for_user


erp_as_page_bp = Blueprint('erp_as_page', __name__, url_prefix='/erp')


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


@erp_as_page_bp.route('/as')
@login_required
def erp_as_dashboard():
    """ERP Beta - AS 대시보드 (MVP: AS 상태 주문 리스트)"""
    db = get_db()
    status_filter = (request.args.get('status') or '').strip()
    search_q = (request.args.get('q') or request.args.get('manager') or '').strip()
    selected_date = request.args.get('date')
    open_map = request.args.get('open_map') == '1'

    if open_map:
        date_val = selected_date or get_today_kst().strftime('%Y-%m-%d')
        status_val = status_filter or 'ALL'
        return redirect(url_for('erp_map.map_view', date=date_val, status=status_val))

    query = db.query(Order).filter(Order.status != 'DELETED')

    if status_filter:
        query = query.filter(Order.status == status_filter)
    else:
        query = query.filter(Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']))

    query = _erp_order_search_filter(query, search_q)

    rows = query.order_by(Order.id.desc()).limit(300).all()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    erp_mine_only = request.args.get('mine') == '1'
    if erp_mine_only and current_user:
        rows = [r for r in rows if is_order_mine_for_user(r, current_user)]

    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)
    apply_erp_display_fields_to_orders(rows)
    return render_template(
        'erp_as_dashboard.html',
        status_filter=status_filter,
        search_q=search_q,
        selected_date=selected_date,
        rows=rows,
        can_edit_erp=can_edit_erp(current_user),
        erp_mine_only=erp_mine_only,
    )
