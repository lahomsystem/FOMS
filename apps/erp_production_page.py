"""
ERP 생산 대시보드 페이지 (ERP-SLIM-9)
erp.py에서 분리: /erp/production/dashboard
"""
from flask import Blueprint, render_template, request, session
from db import get_db
from models import Order
from apps.auth import login_required, get_user_by_id
from sqlalchemy import text

from services.erp_permissions import can_edit_erp
from services.erp_policy import STAGE_LABELS
from services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
)


erp_production_page_bp = Blueprint(
    'erp_production_page', __name__, url_prefix='/erp'
)


TEAM_LABELS = {
    'CS': '라홈팀',
    'SALES': '영업팀',
    'MEASURE': '실측팀',
    'DRAWING': '도면팀',
    'PRODUCTION': '생산팀',
    'CONSTRUCTION': '시공팀',
}


@erp_production_page_bp.route('/production/dashboard')
@login_required
def erp_production_dashboard():
    """생산 대시보드"""
    db = get_db()

    user_id = session.get('user_id')
    user = get_user_by_id(user_id) if user_id else None
    is_admin = user and user.role == 'ADMIN'

    f_stage = (request.args.get('stage') or '').strip()
    f_q = (request.args.get('q') or '').strip()

    orders = (
        db.query(Order)
        .filter(Order.deleted_at.is_(None), Order.is_erp_beta.is_(True))
        .order_by(Order.created_at.desc())
        .limit(300)
        .all()
    )

    att_counts = {}
    try:
        rows = db.execute(text("SELECT order_id, COUNT(*) AS cnt FROM order_attachments GROUP BY order_id")).fetchall()
        for r in rows:
            att_counts[int(r.order_id)] = int(r.cnt)
    except Exception:
        att_counts = {}

    step_stats = {
        '제작대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }

    enriched = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage = _erp_get_stage(o, sd)

        if stage not in ['고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION']:
            continue

        stage_label = stage
        if stage in ('CONFIRM', '고객컨펌'):
            stage_label = '제작대기'
        if stage in ('PRODUCTION', '생산'):
            stage_label = '제작중'
        if stage in ('CONSTRUCTION', '시공'):
            stage_label = '제작완료'

        is_sales_approved = False
        active_quest = None
        if stage_label == '제작대기':
            quests = sd.get('quests') or []
            active_quest = next((q for q in quests if q.get('stage') in ('CONFIRM', '고객컨펌')), None)

            if active_quest:
                assignee_approval = active_quest.get('assignee_approval') or {}
                if isinstance(assignee_approval, dict):
                    is_sales_approved = assignee_approval.get('approved') is True
                else:
                    is_sales_approved = bool(assignee_approval)

                if not is_sales_approved:
                    team_approvals = active_quest.get('team_approvals') or {}
                    sales_val = team_approvals.get('SALES') or team_approvals.get('영업팀')
                    if isinstance(sales_val, dict):
                        is_sales_approved = sales_val.get('approved') is True
                    else:
                        is_sales_approved = bool(sales_val)

        if f_stage and stage_label != f_stage:
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

        if stage_label in step_stats:
            step_stats[stage_label]['count'] += 1
            if alerts.get('production_d2'):
                step_stats[stage_label]['imminent'] += 1

        enriched.append({
            'id': o.id,
            'is_erp_beta': o.is_erp_beta,
            'structured_data': sd,
            'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
            'address': (((sd.get('site') or {}).get('address_full')) or ((sd.get('site') or {}).get('address_main'))) or '-',
            'stage': stage_label,
            'alerts': alerts,
            'has_media': _erp_has_media(o, att_counts.get(o.id, 0)),
            'attachments_count': att_counts.get(o.id, 0),
            'orderer_name': (((sd.get('parties') or {}).get('orderer') or {}).get('name') or '').strip() or None,
            'current_quest': active_quest if stage_label == '제작대기' else None,
            'is_sales_approved': is_sales_approved if stage_label == '제작대기' else True,
            'owner_team': 'PRODUCTION',
            'measurement_date': (((sd.get('schedule') or {}).get('measurement') or {}).get('date')),
            'construction_date': (((sd.get('schedule') or {}).get('construction') or {}).get('date')),
            'manager_name': (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-',
            'phone': (((sd.get('parties') or {}).get('customer') or {}).get('phone')) or '-',
        })

    process_steps = [
        {'label': '제작대기', 'display': '제작대기', **step_stats['제작대기']},
        {'label': '제작중', 'display': '제작중', **step_stats['제작중']},
    ]

    kpis = {
        'urgent_count': sum(1 for r in enriched if (r.get('alerts') or {}).get('urgent')),
        'production_d2_count': sum(1 for r in enriched if (r.get('alerts') or {}).get('production_d2')),
        'measurement_d4_count': 0,
        'construction_d3_count': 0,
    }

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_production_dashboard.html',
        orders=enriched,
        kpis=kpis,
        process_steps=process_steps,
        filters={'stage': f_stage, 'q': f_q},
        team_labels=TEAM_LABELS,
        stage_labels=STAGE_LABELS,
        is_admin=is_admin,
        can_edit_erp=can_edit_erp(current_user),
    )
