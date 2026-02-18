"""
ERP 시공 대시보드 페이지 (ERP-SLIM-10)
erp.py에서 분리: /erp/construction/dashboard
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
        '시공대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }

    enriched = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage = _erp_get_stage(o, sd)

        display_stage = None
        hist = (sd.get('workflow') or {}).get('history') or []
        is_started = any(str(h.get('note')).strip() == '시공 시작' for h in hist)

        if stage in ('CONSTRUCTION', '시공'):
            display_stage = '시공중' if is_started else '시공대기'
        elif stage in ('COMPLETED', '완료', 'AS_WAIT'):
            display_stage = '시공완료'
        elif stage == 'CONSTRUCTING':
            display_stage = '시공중'

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

        if display_stage in step_stats:
            step_stats[display_stage]['count'] += 1
            if alerts.get('construction_d3'):
                step_stats[display_stage]['imminent'] += 1

        enriched.append({
            'id': o.id,
            'is_erp_beta': o.is_erp_beta,
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
        })

    process_steps = [
        {'label': '시공대기', 'display': '시공대기', **step_stats['시공대기']},
        {'label': '시공중', 'display': '시공중', **step_stats['시공중']},
        {'label': '시공완료', 'display': '시공완료', **step_stats['시공완료']},
    ]

    kpis = {
        'urgent_count': sum(1 for r in enriched if (r.get('alerts') or {}).get('urgent')),
        'construction_d3_count': sum(1 for r in enriched if (r.get('alerts') or {}).get('construction_d3')),
        'measurement_d4_count': 0,
        'production_d2_count': 0,
    }

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_construction_dashboard.html',
        orders=enriched,
        kpis=kpis,
        process_steps=process_steps,
        filters={'stage': f_stage, 'q': f_q},
        team_labels=TEAM_LABELS,
        stage_labels=STAGE_LABELS,
        is_admin=is_admin,
        can_edit_erp=can_edit_erp(current_user),
    )
