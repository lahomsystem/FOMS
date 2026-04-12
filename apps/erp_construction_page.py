"""
ERP 시공 대시보드 페이지 (ERP-SLIM-10)
erp.py에서 분리: /erp/construction/dashboard
"""
import logging
from flask import Blueprint, render_template, request, g
from db import get_db
from models import Order
from apps.auth import login_required
from sqlalchemy import text, bindparam, cast, String, or_

from foms.services.erp_permissions import can_edit_erp, build_mine_sql_filter
from foms.services.erp_policy import STAGE_LABELS
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
    self_measurement_four_checks_done,
)
from foms.services.erp_order_detail import attach_order_detail_payloads


erp_construction_page_bp = Blueprint(
    'erp_construction_page', __name__, url_prefix='/erp'
)


TEAM_LABELS = {
    'CS': '라홈팀',
    'SALES': '영업팀',
    'MEASURE': '실측팀',
    'DRAWING': '도면팀',
    'PRODUCTION': '생산팀',
    'CONSTRUCTION': '시공팀',
}


@erp_construction_page_bp.route('/construction/dashboard')
@login_required
def erp_construction_dashboard():
    """시공 대시보드"""
    db = get_db()
    user = getattr(g, 'current_user', None)
    is_admin = user and user.role == 'ADMIN'

    f_stage = (request.args.get('stage') or '').strip()
    f_q = (request.args.get('q') or '').strip()
    is_construction = user and getattr(user, 'team', None) == 'CONSTRUCTION'
    mine_only = is_construction or (request.args.get('mine') == '1')

    query = (
        db.query(Order)
        .filter(Order.dashboard_active_filter(days=60), Order.is_erp_beta.is_(True))
    )

    # mine 필터를 SQL WHERE로 적용 — Python 루프보다 선행하여 limit 누락 방지
    if mine_only and user:
        mine_conds = build_mine_sql_filter(user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))

    # --- A-3: 타일/KPI 집계 쿼리 분리 (limit 300 적용 전 전체 데이터 기준) ---
    kpi_rows = query.order_by(None).with_entities(Order.id, Order.structured_data, Order.is_self_measurement).all()
    step_stats = {
        '시공대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }
    kpis = {
        'urgent_count': 0,
        'construction_d3_count': 0,
        'measurement_d4_count': 0,
        'production_d2_count': 0,
    }

    def _display_stage_for_order(o, sd):
        stage = _erp_get_stage(o, sd)
        hist = (sd.get('workflow') or {}).get('history') or []
        is_started = any(str(h.get('note')).strip() == '시공 시작' for h in hist)
        if stage in ('CONSTRUCTION', '시공'):
            return '시공중' if is_started else '시공대기'
        if stage in ('COMPLETED', '완료', 'AS_WAIT') or stage == 'CS':
            return '시공완료'
        if stage == 'CONSTRUCTING':
            return '시공중'
        return None

    for r in kpi_rows:
        if r.is_self_measurement and not self_measurement_four_checks_done(r):
            continue
        sd = _ensure_dict(r.structured_data)
        display_stage = _display_stage_for_order(r, sd)
        if not display_stage:
            continue
        
        alerts = _erp_alerts(r, sd, 0)
        
        if display_stage in step_stats:
            step_stats[display_stage]['count'] += 1
            if alerts.get('construction_d3'):
                step_stats[display_stage]['imminent'] += 1
                
        if alerts.get('urgent'):
            kpis['urgent_count'] += 1
        if alerts.get('construction_d3'):
            kpis['construction_d3_count'] += 1

    # --- SQL 필터 선적용 ---
    # f_stage 최적화: 시공대기/시공중은 CONSTRUCTION 단계, 시공완료는 COMPLETED/CS 등
    if f_stage:
        stage_col = cast(Order.structured_data['workflow']['stage'], String)
        if f_stage in ('시공대기', '시공중'):
            query = query.filter(stage_col.in_(['"CONSTRUCTION"', '"시공"', '"CONSTRUCTING"']))
        elif f_stage == '시공완료':
            query = query.filter(stage_col.in_(['"COMPLETED"', '"완료"', '"AS_WAIT"', '"CS"']))

    # SQL 정렬 및 300건 제한
    orders = query.order_by(Order.created_at.desc()).limit(300).all()

    att_counts = {}
    if orders:
        try:
            order_ids = [o.id for o in orders]
            stmt = text("SELECT order_id, COUNT(*) AS cnt FROM order_attachments WHERE order_id = ANY(:order_ids) GROUP BY order_id")
            stmt = stmt.bindparams(bindparam('order_ids', value=order_ids))
            rows = db.execute(stmt).fetchall()
            for r in rows:
                att_counts[int(r.order_id)] = int(r.cnt)
        except Exception as e:
            logging.getLogger(__name__).warning("att_counts query failed: %s", e)
            att_counts = {}

    # 2) 목록: f_stage / f_q 적용하여 표시할 주문만 enriched에 추가
    enriched = []
    for o in orders:
        if getattr(o, 'is_self_measurement', False) and not self_measurement_four_checks_done(o):
            continue
        sd = _ensure_dict(o.structured_data)
        display_stage = _display_stage_for_order(o, sd)
        if not display_stage:
            continue
        if f_stage and display_stage != f_stage:
            continue
        if f_q:
            hay = ' '.join([
                str((((sd.get('parties') or {}).get('customer') or {}).get('name')) or ''),
                str((((sd.get('parties') or {}).get('customer') or {}).get('phone')) or ''),
                str((((sd.get('site') or {}).get('address_full')) or ((sd.get('site') or {}).get('address_main'))) or ''),
            ]).lower()
            if f_q.lower() not in hay:
                continue

        alerts = _erp_alerts(o, sd, att_counts.get(o.id, 0))
        is_self = getattr(o, 'is_self_measurement', False)

        enriched.append({
            'id': o.id,
            'is_erp_beta': o.is_erp_beta,
            'is_self_measurement': is_self,
            'structured_data': sd,
            'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
            'address': (((sd.get('site') or {}).get('address_full')) or ((sd.get('site') or {}).get('address_main'))) or '-',
            'stage': display_stage,
            'alerts': alerts,
            'has_media': _erp_has_media(o, att_counts.get(o.id, 0)),
            'attachments_count': att_counts.get(o.id, 0),
            'orderer_name': (((sd.get('parties') or {}).get('orderer') or {}).get('name') or '').strip() or None,
            'owner_team': 'CONSTRUCTION',
            'measurement_date': (((sd.get('schedule') or {}).get('measurement') or {}).get('date')),
            'construction_date': (((sd.get('schedule') or {}).get('construction') or {}).get('date')),
            'manager_name': (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-',
            'phone': (((sd.get('parties') or {}).get('customer') or {}).get('phone')) or '-',
            'as_received_date': getattr(o, 'as_received_date', None) or '',
            'as_received_done': bool((getattr(o, 'as_received_date', None) or '').strip()),
        })

    process_steps = [
        {'label': '시공대기', 'display': '시공대기', **step_stats['시공대기']},
        {'label': '시공중', 'display': '시공중', **step_stats['시공중']},
        {'label': '시공완료', 'display': '시공완료', **step_stats['시공완료']},
    ]

    # 페이지네이션: payload는 현재 페이지 표시 건수에만 주입 (전체 enriched 대신)
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = 50
    total_orders = len(enriched)
    total_pages = (total_orders + per_page - 1) // per_page
    paginated_orders = enriched[(page - 1) * per_page: page * per_page]
    attach_order_detail_payloads(db, paginated_orders)

    return render_template(
        'erp_construction_dashboard.html',
        orders=paginated_orders,
        kpis=kpis,
        process_steps=process_steps,
        filters={'stage': f_stage, 'q': f_q},
        team_labels=TEAM_LABELS,
        stage_labels=STAGE_LABELS,
        is_admin=is_admin,
        can_edit_erp=can_edit_erp(user),
        erp_mine_only=mine_only,
        page=page,
        total_pages=total_pages,
        total_orders=total_orders,
    )
