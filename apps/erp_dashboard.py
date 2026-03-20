"""
ERP 메인 대시보드 (ERP-SLIM-4)
erp.py에서 분리: /erp/dashboard
"""
import datetime
from flask import Blueprint, render_template, request, g
from db import get_db
from models import Order, User
from apps.auth import login_required
from sqlalchemy import text
from services.erp_permissions import can_edit_erp
from services.erp_policy import (
    STAGE_NAME_TO_CODE,
    DEFAULT_OWNER_TEAM_BY_STAGE,
    STAGE_LABELS,
    STAGE_SQL_FILTER_MAP,
    STAGES_REQUIRING_TEAM,
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
from services.erp_order_detail import attach_order_detail_payloads
from services.erp_shipment_settings import is_order_mine_for_user
from constants import BULK_ACTION_STATUS


erp_dashboard_bp = Blueprint('erp_dashboard', __name__, url_prefix='/erp')


@erp_dashboard_bp.route('/dashboard')
@login_required
def erp_dashboard():
    """ERP 프로세스 대시보드(MVP)"""
    db = get_db()
    is_admin = False
    current_user = getattr(g, 'current_user', None)
    if current_user and current_user.role == 'ADMIN':
        is_admin = True
    can_edit_erp_flag = can_edit_erp(current_user)

    f_stage = (request.args.get('stage') or '').strip()
    # 레거시 호환: MEASURED -> MEASURE
    if f_stage == 'MEASURED':
        f_stage = 'MEASURE'
    f_urgent = (request.args.get('urgent') or '').strip()
    f_has_alert = (request.args.get('has_alert') or '').strip()
    f_alert_type = (request.args.get('alert_type') or '').strip()
    f_q = (request.args.get('q') or '').strip()
    f_team = (request.args.get('team') or '').strip()

    _q = db.query(Order).filter(Order.active_filter(), Order.is_erp_beta.is_(True))

    from sqlalchemy import or_, and_, cast, String
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

    if request.args.get('mine') == '1' and current_user:
        u_name = (current_user.name or '').strip()
        u_username = (current_user.username or '').strip()
        conds = []
        if u_name:
            conds.append(Order.manager_name.ilike(f"%{u_name}%"))
            conds.append(cast(Order.structured_data, String).ilike(f'%"{u_name}"%'))
        if u_username:
            conds.append(Order.manager_name.ilike(f"%{u_username}%"))
            conds.append(cast(Order.structured_data, String).ilike(f'%"{u_username}"%'))
        if conds:
            _q = _q.filter(or_(*conds))

    # C. f_team SQL 필터
    if f_team and not is_admin:
        team_stages = STAGES_REQUIRING_TEAM.get(f_team)
        if team_stages is not None:
            if not team_stages:
                from sqlalchemy import false
                _q = _q.filter(false())
            else:
                # Phase D: 플랫 컬럼 사용 (따옴표 제거된 정규화 코드 배열로 변환)
                flat_target_stages = [s.strip('"\'') for s in team_stages]
                _q = _q.filter(Order.erp_stage_code.in_(flat_target_stages))

    # --- 분기 시점: 집계용 base query 복제 (f_stage, f_urgent 적용 전) ---
    _q_stats = _q.order_by(None)

    # A-1. f_stage SQL 필터
    if f_stage:
        target_stages = STAGE_SQL_FILTER_MAP.get(f_stage, [])
        if target_stages:
            flat_target_stages = [s.strip('"\'') for s in target_stages]
            _q = _q.filter(Order.erp_stage_code.in_(flat_target_stages))

    # A-2. f_urgent SQL 필터
    if f_urgent == '1':
        _q = _q.filter(Order.erp_urgent == True)

    # B-4. D-day SQL 후보군 필터 (1차)
    if f_alert_type in ('measurement_d4', 'construction_d3', 'production_d2'):
        today_date = datetime.date.today()
        
        if f_alert_type == 'measurement_d4':
            cutoff = (today_date + datetime.timedelta(days=12)).isoformat()
            _q = _q.filter(
                Order.erp_measurement_date.isnot(None),
                Order.erp_measurement_date >= today_date.isoformat(),
                Order.erp_measurement_date <= cutoff
            )
        elif f_alert_type == 'construction_d3':
            cutoff = (today_date + datetime.timedelta(days=10)).isoformat()
            _q = _q.filter(
                Order.erp_construction_date.isnot(None),
                Order.erp_construction_date >= today_date.isoformat(),
                Order.erp_construction_date <= cutoff
            )
        elif f_alert_type == 'production_d2':
            cutoff = (today_date + datetime.timedelta(days=8)).isoformat()
            _q = _q.filter(
                Order.erp_construction_date.isnot(None),
                Order.erp_construction_date >= today_date.isoformat(),
                Order.erp_construction_date <= cutoff,
                Order.erp_stage_code != 'CONSTRUCTION'
            )

    # 순수 DB 정렬: 실측/시공 단계 진입 시 해당 날짜 내림차순 정렬 우선
    if f_stage:
        _req_code = STAGE_NAME_TO_CODE.get(f_stage, f_stage)
        if _req_code == 'MEASURE':
            _q = _q.order_by(Order.erp_measurement_date.desc().nullslast(), Order.created_at.desc())
        elif _req_code == 'CONSTRUCTION':
            _q = _q.order_by(Order.erp_construction_date.desc().nullslast(), Order.created_at.desc())
        else:
            _q = _q.order_by(Order.created_at.desc())
    else:
        _q = _q.order_by(Order.created_at.desc())

    # Phase D: DB 레벨 페이지네이션
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    per_page = 50

    # f_has_alert, f_alert_type 등의 메모리 필터가 완벽하지 않으므로 (SQL 후보군),
    # count는 SQL count를 그대로 사용 (약간의 오차 허용)
    total_orders = _q.count()
    total_pages = (total_orders + per_page - 1) // per_page

    orders = _q.offset((page - 1) * per_page).limit(per_page).all()

    TEAM_LABELS = {
        'CS': '라홈팀',
        'SALES': '영업팀',
        'MEASURE': '실측팀',
        'DRAWING': '도면팀',
        'PRODUCTION': '생산팀',
        'CONSTRUCTION': '시공팀',
    }

    # AS 파이프라인: 'AS처리' 클릭 시 AS접수·AS처리 표시 ('AS완료'는 '완료' 타일로 이동)
    AS_STAGE_GROUP = ('AS접수', 'AS처리')

    # 페이징된 50건에 대해서만 파이썬 필터(CS 오버라이드 및 정확한 alert 체크) 수행
    # 단, DB 페이지네이션을 썼으므로 필터링 후 50건이 안 될 수 있음.
    filtered = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage = _erp_get_stage(o, sd)
        alerts = _erp_alerts(o, sd, 0)
        
        if f_has_alert == '1':
            if not (alerts.get('urgent') or alerts.get('drawing_overdue') or alerts.get('measurement_d4') or alerts.get('construction_d3') or alerts.get('production_d2')):
                continue
        if f_alert_type:
            if f_alert_type == 'urgent' and not alerts.get('urgent'):
                continue
            elif f_alert_type == 'measurement_d4' and not alerts.get('measurement_d4'):
                continue
            elif f_alert_type == 'construction_d3' and not alerts.get('construction_d3'):
                continue
            elif f_alert_type == 'production_d2' and not alerts.get('production_d2'):
                continue
        
        # --- C: f_team 인메모리 2차 확인 (CS 오버라이드 보완) ---
        if f_team and not is_admin:
            stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
            if stage_code in ('MEASURE', 'CONFIRM'):
                orderer_name = (((sd or {}).get("parties") or {}).get("orderer") or {}).get("name") or ""
                is_lahom = "라홈" in orderer_name.strip()
                if is_lahom:
                    if f_team not in ('CS', 'MEASURE'):
                        continue
                else:
                    if f_team not in ('SALES', 'MEASURE'):
                        continue

        filtered.append({
            '_order': o,
            '_sd': sd,
            'stage': stage,
            'alerts': alerts,
        })

    # --- A-0. kpis / step_stats 집계 (limit 무관하게 _q_stats에서 산출) ---
    kpis = {'urgent_count': 0, 'measurement_d4_count': 0, 'construction_d3_count': 0, 'production_d2_count': 0}
    step_stats = {k: {'count': 0, 'overdue': 0, 'imminent': 0} for k in [
        '주문접수', '실측', '도면', '고객컨펌', '생산', '시공', 'CS', '완료', 'AS처리'
    ]}

    from sqlalchemy import func, case as sql_case
    
    # Phase D: 플랫 컬럼을 활용한 집계
    stage_bucket_expr = sql_case(
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('주문접수', [])]), '주문접수'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('실측', [])]), '실측'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('도면', [])]), '도면'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('고객컨펌', [])]), '고객컨펌'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('생산', [])]), '생산'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('시공', [])]), '시공'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('CS', [])]), 'CS'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('완료', [])]), '완료'),
        (Order.erp_stage_code.in_([s.strip('"\'') for s in STAGE_SQL_FILTER_MAP.get('AS처리', [])]), 'AS처리'),
        else_='기타'
    )
    
    stats_rows = (
        _q_stats
        .with_entities(stage_bucket_expr.label('bucket'), func.count(Order.id).label('cnt'))
        .group_by(stage_bucket_expr)
        .all()
    )
    for row in stats_rows:
        if row.bucket in step_stats:
            step_stats[row.bucket]['count'] = row.cnt

    # KPI 집계 (SQL 활용 및 타겟 대상만 파이썬 연산)
    kpis['urgent_count'] = _q_stats.filter(Order.erp_urgent == True).count()

    today_date = datetime.date.today()
    
    # measurement_d4 candidates
    m_cutoff = (today_date + datetime.timedelta(days=12)).isoformat()
    m_cands = _q_stats.filter(
        Order.erp_measurement_date.isnot(None),
        Order.erp_measurement_date >= today_date.isoformat(),
        Order.erp_measurement_date <= m_cutoff
    ).with_entities(Order.id, Order.structured_data).all()
    
    # construction_d3 & production_d2 candidates
    c_cutoff = (today_date + datetime.timedelta(days=10)).isoformat()
    c_cands = _q_stats.filter(
        Order.erp_construction_date.isnot(None),
        Order.erp_construction_date >= today_date.isoformat(),
        Order.erp_construction_date <= c_cutoff
    ).with_entities(Order.id, Order.structured_data).all()
    
    # drawing overdue candidates (stage DRAWING/CONFIRM)
    d_cands = _q_stats.filter(
        Order.erp_stage_code.in_(['DRAWING', 'CONFIRM'])
    ).with_entities(Order.id, Order.structured_data).all()

    # 합집합 후보군에 대해서만 alerts 연산
    cand_dict = {row.id: row.structured_data for row in m_cands + c_cands + d_cands}
    for oid, sd in cand_dict.items():
        sd = _ensure_dict(sd)
        alerts = _erp_alerts(None, sd, 0)
        stage = _erp_get_stage(None, sd)
        
        if alerts.get('measurement_d4'):
            kpis['measurement_d4_count'] += 1
        if alerts.get('construction_d3'):
            kpis['construction_d3_count'] += 1
        if alerts.get('production_d2'):
            kpis['production_d2_count'] += 1
            
        if stage in ('AS접수', 'AS처리'):
            bucket = 'AS처리'
        elif stage == 'AS완료':
            bucket = '완료'
        else:
            bucket = stage

        if bucket in step_stats:
            if alerts.get('drawing_overdue'):
                step_stats[bucket]['overdue'] += 1
            if alerts.get('measurement_d4') or alerts.get('construction_d3') or alerts.get('production_d2'):
                step_stats[bucket]['imminent'] += 1

    process_steps = [
        {'label': '주문접수', **step_stats['주문접수']},
        {'label': '실측', **step_stats['실측']},
        {'label': '도면', **step_stats['도면']},
        {'label': '고객컨펌', **step_stats['고객컨펌']},
        {'label': '생산', **step_stats['생산']},
        {'label': '시공', **step_stats['시공']},
        {'label': '완료', **step_stats['완료']},
        {'label': 'CS', **step_stats['CS']},
        {'label': 'AS처리', **step_stats['AS처리']},
    ]

    page_slice = filtered

    # 표시용 50건: Order 객체 참조로 full enrichment
    page_orders = [item['_order'] for item in page_slice]
    page_sds = {item['_order'].id: item['_sd'] for item in page_slice}

    # att_counts: 50건만 배치 조회 (원래 1000건 → 50건)
    att_counts = {}
    if page_orders:
        try:
            from models import OrderAttachment
            from sqlalchemy import func
            order_ids = [o.id for o in page_orders]
            rows = db.query(OrderAttachment.order_id, func.count(OrderAttachment.id).label('cnt')) \
                     .filter(OrderAttachment.order_id.in_(order_ids)) \
                     .group_by(OrderAttachment.order_id).all()
            for r in rows:
                att_counts[int(r.order_id)] = int(r.cnt)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("att_counts query failed: %s", e)
            att_counts = {}

    # user_map: 50건 assignee만 조회 (원래 1000건 전체 → 50건으로 절감)
    all_assignee_ids: set[int] = set()
    for o in page_orders:
        sd = page_sds[o.id]
        stage = _erp_get_stage(o, sd)
        stage_key = stage if isinstance(stage, str) else ''
        stage_code = STAGE_NAME_TO_CODE.get(stage_key, stage_key)
        if stage_code in ('MEASURE', 'DRAWING', 'CONFIRM'):
            assignments = sd.get('assignments') or {}
            if stage_code in ('MEASURE', 'CONFIRM'):
                uids = assignments.get('sales_assignee_user_ids') or []
            else:
                uids = assignments.get('drawing_assignee_user_ids') or []
                if not uids:
                    for a in ((assignments.get('drawing_assignees') or []) + (sd.get('drawing_assignees') or [])):
                        if isinstance(a, dict) and a.get('id'):
                            uids.append(a['id'])
            for uid in uids:
                try:
                    all_assignee_ids.add(int(uid))
                except (TypeError, ValueError):
                    pass
    user_map: dict[int, str] = {}
    if all_assignee_ids:
        users = db.query(User).filter(User.id.in_(all_assignee_ids)).all()
        for u in users:
            user_id = getattr(u, 'id', None)
            user_name = getattr(u, 'name', None)
            if isinstance(user_id, int) and isinstance(user_name, str) and user_name:
                user_map[user_id] = user_name

    # Full enrichment: 50건만 (quest_payload, assignee_names, can_modify_domain 등 표시 필드)
    enriched = []
    for o in page_orders:
        sd = page_sds[o.id]
        cnt = att_counts.get(o.id, 0)
        stage = _erp_get_stage(o, sd)
        alerts = _erp_alerts(o, sd, cnt)
        has_media = _erp_has_media(o, cnt)
        current_quest = None
        quests = sd.get('quests') or []
        if stage:
            stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
            stage_label_from_code = STAGE_LABELS.get(stage_code, stage)
            if stage_code == 'CONSTRUCTION':
                pass  # 시공 단계 퀘스트는 시공 대시보드에서만 처리
            elif stage_code != 'DRAWING':
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

        stage_key = stage if isinstance(stage, str) else ''
        stage_code = STAGE_NAME_TO_CODE.get(stage_key, stage_key)
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
                    assignee_display_names = []
                    for uid in user_ids:
                        mapped_name = user_map.get(uid)
                        if isinstance(mapped_name, str) and mapped_name:
                            assignee_display_names.append(mapped_name)
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
            'is_self_measurement': getattr(o, 'is_self_measurement', False),
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

    paginated_orders = enriched
    attach_order_detail_payloads(db, paginated_orders)

    return render_template(
        'erp_dashboard.html',
        orders=paginated_orders,
        kpis=kpis,
        process_steps=process_steps,
        filters={
            'stage': f_stage,
            'urgent': f_urgent,
            'has_alert': f_has_alert,
            'alert_type': f_alert_type,
            'q': f_q,
            'team': f_team,
            'mine': request.args.get('mine') or '',
        },
        team_labels=TEAM_LABELS,
        stage_labels=STAGE_LABELS,
        is_admin=is_admin,
        can_edit_erp=can_edit_erp_flag,
        status_choices=list(BULK_ACTION_STATUS.items()) + [('DELETED', '삭제(휴지통)')],
        page=page,
        total_pages=total_pages,
        total_orders=total_orders,
    )
