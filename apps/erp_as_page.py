"""
ERP AS 대시보드 페이지 (ERP-SLIM-8)
erp.py에서 분리: /erp/as
"""
from flask import Blueprint, render_template, request, session, redirect, url_for
from db import get_db
from models import Order
from apps.auth import login_required, get_user_by_id
import datetime

from services.erp_permissions import can_edit_erp
from services.erp_display import _ensure_dict, apply_erp_display_fields_to_orders


erp_as_page_bp = Blueprint('erp_as_page', __name__, url_prefix='/erp')


@erp_as_page_bp.route('/as')
@login_required
def erp_as_dashboard():
    """ERP Beta - AS 대시보드 (MVP: AS 상태 주문 리스트)"""
    db = get_db()
    status_filter = (request.args.get('status') or '').strip()
    manager_filter = (request.args.get('manager') or '').strip()
    selected_date = request.args.get('date')
    open_map = request.args.get('open_map') == '1'

    if open_map:
        date_val = selected_date or datetime.datetime.now().strftime('%Y-%m-%d')
        status_val = status_filter or 'ALL'
        return redirect(url_for('erp_map.map_view', date=date_val, status=status_val))

    query = db.query(Order).filter(Order.status != 'DELETED')

    if status_filter:
        query = query.filter(Order.status == status_filter)
    else:
        query = query.filter(Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED']))

    if manager_filter:
        query = query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    rows = query.order_by(Order.id.desc()).limit(300).all()

    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)
    apply_erp_display_fields_to_orders(rows)

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_as_dashboard.html',
        status_filter=status_filter,
        manager_filter=manager_filter,
        selected_date=selected_date,
        rows=rows,
        can_edit_erp=can_edit_erp(current_user),
    )
