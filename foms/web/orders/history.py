"""ERP history dashboard (canonical; SFC-B11B)."""

from copy import deepcopy

from flask import Blueprint, make_response, render_template, request, g
from db import get_db
from models import Order
from foms.web.auth import login_required
from foms.services.orders.status_constants import STATUS
from foms.services.erp_order_flags import is_erp_order_record
from sqlalchemy import or_, cast, String

from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body

erp_history_bp = Blueprint('erp_history', __name__, url_prefix='/erp/history')

@erp_history_bp.route('/')
@login_required
def history_dashboard():
    """ERP 과거 이력 조회 화면 (Inquiry)"""
    db = get_db()
    
    # 1. 필수 필터 여부 확인 (무차별 Full Scan 방지)
    f_q = (request.args.get('q') or '').strip()
    f_stage = (request.args.get('stage') or '').strip()
    f_date_from = (request.args.get('date_from') or '').strip()
    f_date_to = (request.args.get('date_to') or '').strip()
    
    has_filter = bool(f_q or f_stage or f_date_from or f_date_to)

    # soft-delete 제외한 활성 주문 전체 (레거시 + ERP Order).
    # ERP Order는 DB 컬럼이 초안 플레이스홀더('ERP Order', 000-…)인 채로 두고 실제 값이 structured_data에만
    # 있는 경우가 많음 → 목록 표시 시 apply_erp_display_fields로 동기화(메인 주문 목록과 동일).
    _q = db.query(Order).filter(Order.active_filter())
    
    if f_q:
        search_term = f"%{f_q}%"
        _q = _q.filter(
            or_(
                Order.id.cast(String).ilike(search_term),
                Order.customer_name.ilike(search_term),
                Order.phone.ilike(search_term),
                Order.address.ilike(search_term),
                Order.manager_name.ilike(search_term),
                cast(Order.structured_data, String).ilike(search_term)
            )
        )
        
    if f_stage:
        # ERP: erp_stage_code / 레거시: status (값이 MEASURE·MEASURED 등으로 다를 수 있음)
        stage_or = [
            Order.erp_stage_code == f_stage,
            Order.status == f_stage,
        ]
        if f_stage == "MEASURE":
            stage_or.append(Order.status.in_(("MEASURE", "MEASURED", "REGIONAL_MEASURED")))
        _q = _q.filter(or_(*stage_or))
        
    if f_date_from:
        _q = _q.filter(Order.created_at >= f"{f_date_from} 00:00:00")
        
    if f_date_to:
        _q = _q.filter(Order.created_at <= f"{f_date_to} 23:59:59")
        
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    per_page = 50
    
    total_orders = 0
    orders = []
    
    if has_filter:
        total_orders = _q.count()
        orders = _q.order_by(Order.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
    total_pages = (total_orders + per_page - 1) // per_page
    
    from foms.services.erp_display import _ensure_dict, _erp_get_stage, apply_erp_display_fields
    from foms.services.erp_product_items import build_product_items_for_orders

    enriched = []
    display_orders = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        if is_erp_order_record(o):
            stage = _erp_get_stage(o, sd)
        else:
            stage = STATUS.get(o.status, o.status or "-")

        # ERP Order: Order 행 컬럼이 플레이스홀더인 경우 structured_data 기준으로 표시용 복제
        display_o = o
        if is_erp_order_record(o) and o.structured_data:
            display_o = deepcopy(o)
            apply_erp_display_fields(display_o)
        
        display_orders.append(display_o)

        enriched.append({
            '_order': o,
            '_sd': sd,
            'stage': stage,
            'display_o': display_o,
        })
    
    # N+1 방지를 위해 1번의 쿼리로 전체 표시 주문들의 첨부/제품 항목 매핑
    build_product_items_for_orders(db, display_orders)

    template_name = (
        'orders/partials/history_dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'orders/history_dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_orders=total_orders,
            has_filter=has_filter,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
