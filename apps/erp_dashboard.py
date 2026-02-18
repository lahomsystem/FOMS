"""
ERP 메인 대시보드 (ERP-SLIM-4)
erp.py에서 분리: /erp/dashboard
"""
from flask import Blueprint, render_template, request, session
from db import get_db
from models import Order, User
from apps.auth import login_required, get_user_by_id
from sqlalchemy import text
from services.erp_permissions import can_edit_erp
from services.erp_policy import (
    STAGE_NAME_TO_CODE,
    DEFAULT_OWNER_TEAM_BY_STAGE,
    STAGE_LABELS,
    get_quest_template_for_stage,
    create_quest_from_template,
    get_required_approval_teams_for_stage,
    recommend_owner_team,
    can_modify_domain,
)
from services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_alerts,
    _erp_has_media,
)


erp_dashboard_bp = Blueprint('erp_dashboard', __name__, url_prefix='/erp')


@erp_dashboard_bp.route('/dashboard')
@login_required
def erp_dashboard():
    """ERP 프로세스 대시보드(MVP)"""
    db = get_db()
    is_admin = False
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    if current_user and current_user.role == 'ADMIN':
        is_admin = True
    can_edit_erp_flag = can_edit_erp(current_user)

    f_stage = (request.args.get('stage') or '').strip()
    f_urgent = (request.args.get('urgent') or '').strip()
    f_has_alert = (request.args.get('has_alert') or '').strip()
    f_alert_type = (request.args.get('alert_type') or '').strip()
    f_q = (request.args.get('q') or '').strip()
    f_team = (request.args.get('team') or '').strip()

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

    TEAM_LABELS = {
        'CS': '라홈팀',
        'SALES': '영업팀',
        'MEASURE': '실측팀',
        'DRAWING': '도면팀',
        'PRODUCTION': '생산팀',
        'CONSTRUCTION': '시공팀',
    }

    enriched = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        cnt = att_counts.get(o.id, 0)
        stage = _erp_get_stage(o, sd)
        alerts = _erp_alerts(o, sd, cnt)
        has_media = _erp_has_media(o, cnt)
        current_quest = None
        quests = sd.get('quests') or []
        if stage:
            stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
            stage_label_from_code = STAGE_LABELS.get(stage_code, stage)
            if stage_code != 'DRAWING':
                possible_stages = {stage, stage_code, stage_label_from_code}
                if stage in STAGE_NAME_TO_CODE:
                    possible_stages.add(STAGE_NAME_TO_CODE[stage])
                if stage_code in STAGE_LABELS:
                    possible_stages.add(STAGE_LABELS[stage_code])
                matching_quests = [q for q in quests if isinstance(q, dict) and q.get('stage') in possible_stages]
                if matching_quests:
                    open_quests = [q for q in matching_quests if str(q.get('status', 'OPEN')).upper() == 'OPEN']
                    sort_key = lambda x: (x.get('created_at') or x.get('updated_at') or '1970-01-01T00:00:00',)
                    (open_quests if open_quests else matching_quests).sort(key=sort_key, reverse=True)
                    current_quest = (open_quests if open_quests else matching_quests)[0]
                else:
                    quest_tpl = get_quest_template_for_stage(stage)
                    if quest_tpl:
                        temp_quest = create_quest_from_template(stage, None, sd)
                        if temp_quest:
                            current_quest = temp_quest
                        else:
                            team_approvals_template = {
                                str(team): {'approved': False, 'approved_by': None, 'approved_at': None}
                                for team in quest_tpl.get('required_approvals', []) if team
                            }
                            current_quest = {
                                'stage': stage,
                                'title': quest_tpl.get('title', ''),
                                'description': quest_tpl.get('description', ''),
                                'owner_team': quest_tpl.get('owner_team', ''),
                                'status': 'OPEN',
                                'team_approvals': team_approvals_template
                            }

        all_approved = False
        missing_teams = []
        team_approvals = {}
        required_teams = []
        if current_quest:
            quest_status = str(current_quest.get('status', 'OPEN')).upper()
            team_approvals_raw = current_quest.get('team_approvals', {})
            required_teams = get_required_approval_teams_for_stage(stage)
            if stage in ("실측", "MEASURE", "고객컨펌", "CONFIRM"):
                orderer_name = (((sd.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
                if orderer_name and "라홈" in orderer_name:
                    current_quest['owner_team'] = 'CS'
                    required_teams = ['CS']
                    existing_cs = current_quest.get('team_approvals', {}).get('CS', {})
                    approved = existing_cs.get('approved', False) if isinstance(existing_cs, dict) else bool(existing_cs)
                    current_quest['team_approvals'] = {
                        'CS': {
                            'approved': approved,
                            'approved_by': existing_cs.get('approved_by') if isinstance(existing_cs, dict) else None,
                            'approved_at': existing_cs.get('approved_at') if isinstance(existing_cs, dict) else None,
                        }
                    }
                    team_approvals_raw = current_quest.get('team_approvals', {})
            if quest_status == 'OPEN':
                missing_teams = required_teams.copy() if required_teams else []
                team_approvals = {team: False for team in required_teams}
            elif quest_status == 'COMPLETED':
                team_approvals = {team: True for team in required_teams}
            else:
                if not required_teams:
                    all_approved = (quest_status == 'COMPLETED')
                else:
                    team_approvals = {}
                    for team in required_teams:
                        ad = team_approvals_raw.get(str(team)) or team_approvals_raw.get(team)
                        team_approvals[team] = ad.get('approved', False) if isinstance(ad, dict) else bool(ad) if ad is not None else False
                    missing_teams = [t for t in required_teams if not team_approvals.get(t, False)]
                    all_approved = (len(missing_teams) == 0)

        stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
        responsible_team = DEFAULT_OWNER_TEAM_BY_STAGE.get(stage_code, None)
        if stage_code in ("MEASURE", "CONFIRM"):
            orderer_check = (((sd.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
            if orderer_check and "라홈" in orderer_check:
                responsible_team = 'CS'

        assignee_display_names = []
        can_assignee_approve = False
        if current_quest:
            approval_mode = current_quest.get('approval_mode') or ('assignee' if stage_code in ('MEASURE', 'DRAWING', 'CONFIRM') else 'team')
            if approval_mode == 'assignee':
                assignments = sd.get('assignments') or {}
                user_ids = []
                if stage_code in ('MEASURE', 'CONFIRM'):
                    user_ids = assignments.get('sales_assignee_user_ids') or []
                elif stage_code == 'DRAWING':
                    user_ids = assignments.get('drawing_assignee_user_ids') or []
                    if not user_ids:
                        for a in ((assignments.get('drawing_assignees') or []) + (sd.get('drawing_assignees') or [])):
                            if isinstance(a, dict) and a.get('id'):
                                user_ids.append(a['id'])
                user_ids = [int(uid) for uid in user_ids if isinstance(uid, (int, str)) and str(uid).isdigit()]
                if user_ids:
                    assignee_users = db.query(User).filter(User.id.in_(user_ids)).all()
                    assignee_display_names = [u.name for u in assignee_users if u.name]
                elif stage_code in ('MEASURE', 'CONFIRM'):
                    mgr = (((sd.get('parties') or {}).get('manager') or {}).get('name')) or o.manager_name or current_quest.get('owner_person') or ''
                    if str(mgr).strip():
                        assignee_display_names = [str(mgr).strip()]
                if current_user:
                    domain = 'DRAWING_DOMAIN' if stage_code == 'DRAWING' else ('SALES_DOMAIN' if stage_code in ('MEASURE', 'CONFIRM') else None)
                    if domain:
                        can_assignee_approve = can_modify_domain(current_user, o, domain, False, None)
                        if (not can_assignee_approve) and domain == 'SALES_DOMAIN' and not user_ids:
                            manager_names = set()
                            for src in [((sd.get('parties') or {}).get('manager') or {}).get('name'), o.manager_name, current_quest.get('owner_person')]:
                                if str(src or '').strip():
                                    manager_names.add(str(src).strip().lower())
                            un = (current_user.name or '').strip().lower()
                            uu = (current_user.username or '').strip().lower()
                            if un in manager_names or uu in manager_names:
                                can_assignee_approve = True

        quest_payload = None
        if current_quest:
            quest_payload = {
                'title': current_quest.get('title', ''),
                'description': current_quest.get('description', ''),
                'owner_team': current_quest.get('owner_team', ''),
                'status': current_quest.get('status', 'OPEN'),
                'all_approved': all_approved,
                'missing_teams': missing_teams,
                'required_approvals': required_teams,
                'team_approvals': team_approvals,
                'approval_mode': current_quest.get('approval_mode') or ('assignee' if stage_code in ('MEASURE', 'DRAWING', 'CONFIRM') else 'team'),
                'assignee_approval': current_quest.get('assignee_approval'),
                'assignee_display_names': assignee_display_names,
                'can_assignee_approve': can_assignee_approve,
            }
        parties = sd.get('parties') or {}
        site = sd.get('site') or {}
        schedule = sd.get('schedule') or {}
        enriched.append({
            'id': o.id,
            'is_erp_beta': o.is_erp_beta,
            'structured_data': sd,
            'customer_name': (parties.get('customer') or {}).get('name') or '-',
            'phone': (parties.get('customer') or {}).get('phone') or '-',
            'address': site.get('address_full') or site.get('address_main') or '-',
            'measurement_date': (schedule.get('measurement') or {}).get('date'),
            'construction_date': (schedule.get('construction') or {}).get('date'),
            'manager_name': (parties.get('manager') or {}).get('name') or '-',
            'orderer_name': (parties.get('orderer') or {}).get('name') or None,
            'owner_team': responsible_team,
            'stage': stage,
            'alerts': alerts,
            'has_media': has_media,
            'attachments_count': cnt,
            'recommended_owner_team': recommend_owner_team(sd) or None,
            'current_quest': quest_payload,
        })

    filtered = []
    for r in enriched:
        if f_stage:
            row_stage = (r.get('stage') or '').strip()
            req_stage = f_stage.strip()
            row_code = STAGE_NAME_TO_CODE.get(row_stage, row_stage)
            req_code = STAGE_NAME_TO_CODE.get(req_stage, req_stage)
            row_label = STAGE_LABELS.get(row_code, row_stage)
            req_label = STAGE_LABELS.get(req_code, req_stage)
            if req_stage not in {row_stage, row_code, row_label} and req_code not in {row_stage, row_code, row_label} and req_label not in {row_stage, row_code, row_label}:
                continue
        if f_urgent == '1' and not (r.get('alerts') or {}).get('urgent'):
            continue
        if f_has_alert == '1':
            a = r.get('alerts') or {}
            if not (a.get('urgent') or a.get('drawing_overdue') or a.get('measurement_d4') or a.get('construction_d3') or a.get('production_d2')):
                continue
        if f_alert_type:
            a = r.get('alerts') or {}
            if f_alert_type == 'urgent' and not a.get('urgent'):
                continue
            elif f_alert_type == 'measurement_d4' and not a.get('measurement_d4'):
                continue
            elif f_alert_type == 'construction_d3' and not a.get('construction_d3'):
                continue
            elif f_alert_type == 'production_d2' and not a.get('production_d2'):
                continue
        if f_q:
            hay = ' '.join([
                str(r.get('customer_name') or ''),
                str(r.get('phone') or ''),
                str(r.get('address') or ''),
                str(r.get('manager_name') or ''),
            ]).lower()
            if f_q.lower() not in hay:
                continue
        if f_team and not is_admin:
            quest = r.get('current_quest')
            if not quest:
                continue
            if f_team not in get_required_approval_teams_for_stage(r.get('stage')):
                continue
        filtered.append(r)

    kpis = {'urgent_count': 0, 'measurement_d4_count': 0, 'construction_d3_count': 0, 'production_d2_count': 0}
    step_stats = {k: {'count': 0, 'overdue': 0, 'imminent': 0} for k in [
        '주문접수', '해피콜', '실측', '도면', '고객컨펌', '생산', '시공', 'CS', '완료', 'AS처리'
    ]}
    for r in enriched:
        alerts = r.get('alerts') or {}
        stage = r.get('stage')
        if alerts.get('urgent'):
            kpis['urgent_count'] += 1
        if alerts.get('measurement_d4'):
            kpis['measurement_d4_count'] += 1
        if alerts.get('construction_d3'):
            kpis['construction_d3_count'] += 1
        if alerts.get('production_d2'):
            kpis['production_d2_count'] += 1
        if stage in step_stats:
            step_stats[stage]['count'] += 1
            if alerts.get('drawing_overdue'):
                step_stats[stage]['overdue'] += 1
            if alerts.get('measurement_d4') or alerts.get('construction_d3') or alerts.get('production_d2'):
                step_stats[stage]['imminent'] += 1

    process_steps = [
        {'label': '주문접수', **step_stats['주문접수']},
        {'label': '해피콜', **step_stats['해피콜']},
        {'label': '실측', **step_stats['실측']},
        {'label': '도면', **step_stats['도면']},
        {'label': '고객컨펌', **step_stats['고객컨펌']},
        {'label': '생산', **step_stats['생산']},
        {'label': '시공', **step_stats['시공']},
        {'label': '완료', **step_stats['완료']},
        {'label': 'CS', **step_stats['CS']},
        {'label': 'AS처리', **step_stats['AS처리']},
    ]

    return render_template(
        'erp_dashboard.html',
        orders=filtered,
        kpis=kpis,
        process_steps=process_steps,
        filters={
            'stage': f_stage,
            'urgent': f_urgent,
            'has_alert': f_has_alert,
            'alert_type': f_alert_type,
            'q': f_q,
            'team': f_team,
        },
        team_labels=TEAM_LABELS,
        stage_labels=STAGE_LABELS,
        is_admin=is_admin,
        can_edit_erp=can_edit_erp_flag,
    )
