from flask import Blueprint, render_template, request, jsonify, session, url_for, redirect, flash
from db import get_db
from models import Order, User, OrderEvent, OrderAttachment
from apps.auth import login_required, role_required, get_user_by_id
import datetime
import re
import json
import os
import math
from urllib.parse import quote
from sqlalchemy import or_, and_, func, String
from sqlalchemy.orm.attributes import flag_modified
from foms_address_converter import FOMSAddressConverter
from foms_map_generator import FOMSMapGenerator
from services.erp_policy import (
    STAGE_NAME_TO_CODE, DEFAULT_OWNER_TEAM_BY_STAGE, STAGE_LABELS,
    get_quest_template_for_stage, create_quest_from_template,
    get_required_approval_teams_for_stage, recommend_owner_team,
    can_modify_domain, get_assignee_ids
)
from services.storage import get_storage
from services.business_calendar import business_days_until
from services.erp_shipment_settings import (
    load_erp_shipment_settings,
    save_erp_shipment_settings,
    normalize_erp_shipment_workers,
)
from sqlalchemy import text
import pytz
import unicodedata


def _normalize_for_search(s):
    """검색 매칭용 문자열 정규화 (유니코드 NFC, 공백 정리)"""
    if s is None:
        return ''
    s = str(s).strip()
    if not s:
        return ''
    return unicodedata.normalize('NFC', s)


erp_bp = Blueprint('erp', __name__)
ERP_BETA_DEBUG = os.environ.get('ERP_BETA_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')

# -------------------------------------------------------------------------
# ERP Beta 수정 권한: 관리자, 라홈팀(CS), 하우드팀(CS), 영업팀(SALES)만 수정 가능
# -------------------------------------------------------------------------
ERP_EDIT_ALLOWED_TEAMS = ('CS', 'SALES')


def can_edit_erp(user):
    """ERP 페이지/API 수정 권한: 관리자 또는 CS/영업팀 소속만 True"""
    if not user:
        return False
    if user.role == 'ADMIN':
        return True
    return (user.team or '').strip() in ERP_EDIT_ALLOWED_TEAMS


def erp_edit_required(f):
    """ERP Beta 수정 API용 데코레이터: 수정 권한 없으면 403"""
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        user = get_user_by_id(session.get('user_id'))
        if not user:
            return jsonify({'success': False, 'message': '로그인이 필요합니다.'}), 401
        if not can_edit_erp(user):
            return jsonify({
                'success': False,
                'message': 'ERP Beta 수정 권한이 없습니다. (관리자, 라홈팀, 하우드팀, 영업팀만 수정 가능)'
            }), 403
        return f(*args, **kwargs)
    return wrapped


# -------------------------------------------------------------------------
# Template Filters
# -------------------------------------------------------------------------
@erp_bp.app_template_filter('split_count')
def split_count_filter(s, sep=','):
    """문자열을 sep로 나눈 비어있지 않은 항목 개수 (출고 대시보드 제품 수 fallback용)"""
    if not s:
        return 0
    return max(1, len([x for x in str(s).split(sep) if str(x).strip()]))

@erp_bp.app_template_filter('split_list')
def split_list_filter(s, sep=','):
    """문자열을 sep로 나눈 리스트 (공백 제거, 출고 대시보드 제품 가로 스태킹용)"""
    if not s:
        return []
    return [x.strip() for x in str(s).split(sep) if x.strip()]

@erp_bp.app_template_filter('strip_product_w')
def strip_product_w_filter(value):
    """제품 표시에서 뒤에 붙는 숫자(W) 및 넓이 추종 숫자 제거.
    예: '제품명 120W' -> '제품명', '몰딩여닫이 3600 3600' -> '몰딩여닫이 3600'
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return value
    s = str(value).strip()

    def process_part(p: str) -> str:
        p = re.sub(r'\s*\d+W\s*$', '', p).strip()
        # 끝의 중복 숫자 제거 (넓이 추종): "이름 3600 3600" -> "이름 3600"
        p = re.sub(r'\s+(\d+)\s+\1\s*$', r' \1', p)
        return p.strip()

    parts = [process_part(p) for p in s.split(',')]
    result = ', '.join(p for p in parts if p)
    return result if result else s

@erp_bp.app_template_filter('spec_w300')
def spec_w300_filter(value):
    """실제 길이(W)/300 숫자로 표시 (예: 3600 -> 12). 복합규격(3600x600)이면 첫 숫자 사용"""
    if value is None or value == '':
        return ''
    s = str(value).strip().replace(',', '')
    try:
        # 첫 번째 숫자만 사용 (W)
        m = re.search(r'[\d.]+', s)
        if not m:
            return ''
        n = float(m.group())
        return round(n / 300, 1) if n else ''
    except (ValueError, TypeError):
        return ''

@erp_bp.app_template_filter('format_phone')
def format_phone_filter(value):
    """전화번호 포맷 (01012345678 -> 010-1234-5678)"""
    if not value:
        return '-'
    digits = re.sub(r'[^0-9]', '', str(value))
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return value

# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------
def spec_w300_value(value):
    """규격(W)/300 수치 계산 (숫자 반환). 복합규격이면 첫 숫자 사용"""
    if value is None or value == '':
        return 0.0
    s = str(value).strip().replace(',', '')
    try:
        m = re.search(r'[\d.]+', s)
        if not m:
            return 0.0
        n = float(m.group())
        return round(n / 300, 1) if n else 0.0
    except (ValueError, TypeError):
        return 0.0

def _ensure_dict(data):
    """JSONB 필드가 문자열로 오인될 경우를 대비해 딕셔너리로 확실히 변환"""
    if not data:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except:
            return {}
    return {}

# [중복 제거됨] _erp_get_urgent_flag 함수는 Line 350에 정의되어 있습니다.

# [중복 제거됨] _erp_get_stage 함수는 Line 356에 정의되어 있습니다.

# [중복 제거됨] _erp_has_media 함수는 Line 367에 정의되어 있습니다.

# [중복 제거됨] _erp_alerts 함수는 Line 371에 정의되어 있습니다.


def apply_erp_display_fields(order):
    if not order or not order.structured_data:
        return
    sd = order.structured_data
    if not isinstance(sd, dict):
        return

    # ERP Beta 주문이거나 AS 주문, 또는 구조화된 데이터가 있는 경우 기초 데이터 반영
    # (사용자 요청: erp 대시보드 기초 데이터는 ERPbeta이다)
    parties = sd.get('parties') or {}
    
    # 고객명
    customer = (parties.get('customer') or {}).get('name')
    if customer:
        order.customer_name = customer

    # 전화번호
    phone = (parties.get('customer') or {}).get('phone')
    if phone:
        order.phone = phone

    # 담당자
    manager_name = (parties.get('manager') or {}).get('name')
    if manager_name:
        order.manager_name = manager_name
        
    # 발주사 (임시 속성으로 추가하여 템플릿에서 사용 가능하게 함)
    orderer = (parties.get('orderer') or {}).get('name')
    if orderer:
        order.orderer_name = orderer

    # 주소
    site = sd.get('site') or {}
    address_full = site.get('address_full')
    address_main = site.get('address_main')
    address_detail = site.get('address_detail')
    if address_full:
        order.address = address_full
    elif address_main:
        order.address = f"{address_main} {address_detail}".strip() if address_detail else address_main

    # 제품명
    items = sd.get('items') or []
    if isinstance(items, list) and items:
        product_parts = []
        for item in items:
            if not isinstance(item, dict):
                continue
            product_name = item.get('product_name')
            if isinstance(product_name, str):
                product_name = product_name.strip()
            else:
                product_name = None
            if not product_name:
                continue
            product_parts.append(product_name)
        if product_parts:
            order.product = ", ".join(product_parts)

    # 일정
    schedule = sd.get('schedule') or {}
    
    # 실측
    measurement = schedule.get('measurement') or {}
    measurement_date = measurement.get('date')
    if measurement_date:
        order.measurement_date = str(measurement_date)
    measurement_time = measurement.get('time')
    if measurement_time:
        order.measurement_time = measurement_time

    # 시공/방문
    construction = schedule.get('construction') or {}
    construction_date = construction.get('date')
    if construction_date:
        order.scheduled_date = str(construction_date)


def _erp_get_urgent_flag(structured_data):
    try:
        return bool((structured_data or {}).get('flags', {}).get('urgent'))
    except Exception:
        return False

def _erp_get_stage(order, structured_data):
    # Canonical: structured_data.workflow.stage 우선
    try:
        st = ((structured_data or {}).get('workflow') or {}).get('stage')
        if st:
            # 영문 코드인 경우 STAGE_LABELS에서 한글 레이블 반환
            if st in STAGE_LABELS:
                return STAGE_LABELS.get(st)
            # 한글 레이블인 경우, 영문 코드로 변환 후 STAGE_LABELS에서 한글 레이블 반환
            stage_code = STAGE_NAME_TO_CODE.get(st, None)
            if stage_code and stage_code in STAGE_LABELS:
                return STAGE_LABELS.get(stage_code)
            # '해피콜(CS)' 같은 레거시 값 처리
            for code, label in STAGE_LABELS.items():
                if st.startswith(label) or label.startswith(st.replace('(CS)', '')):
                    return label
            # 그 외 경우 원본 값 반환
            return st
    except Exception:
        pass
    # ERP Beta 테스트 기준: 레거시(Order 컬럼)로 추정하지 않음
    return '주문접수'

def _erp_has_media(order, attachments_count: int):
    # ERP Beta 테스트 기준: 레거시(Order 컬럼) 첨부(blueprint_image_url)로 판단하지 않음
    return attachments_count > 0

def _erp_alerts(order, structured_data, attachments_count: int):
    """
    경보 규칙(영업일 기준, 오늘 기준):
    - 도면 48h: MVP에서는 도면 업로드 시각 정보가 없어 '도면있고 컨펌 미완' 등을 추후 고도화 필요.
      여기서는 structured_updated_at이 있고 blueprint가 있으면 48h 체크용으로 사용(보수적).
    - 실측 D-4: measurement_date 기준 오늘부터 영업일 계산
    - 시공 D-3: construction_date 기준 오늘부터 영업일 계산
    - 생산 D-2: construction_date 기준 오늘부터 영업일 계산
    - 긴급 발주: structured_data.flags.urgent
    - '오늘'은 한국(KST) 기준으로 계산 (서버가 UTC일 때 자정~오전9시에도 한국 오늘로 D- 표기)
    """
    urgent = _erp_get_urgent_flag(structured_data)
    meas_date = (((structured_data or {}).get('schedule') or {}).get('measurement') or {}).get('date')
    cons_date = (((structured_data or {}).get('schedule') or {}).get('construction') or {}).get('date')

    # 오늘 = 한국(KST) 기준 날짜 (서버 UTC 시 0~9시에도 한국 자정~오전9시는 같은 '오늘')
    try:
        today_kst = datetime.datetime.now(pytz.timezone('Asia/Seoul')).date()
    except Exception:
        today_kst = datetime.date.today()
    # 영업일 D- 계산: 한국 오늘 기준
    meas_d = business_days_until(meas_date, today=today_kst) if meas_date else None
    cons_d = business_days_until(cons_date, today=today_kst) if cons_date else None

    # 실측 D-4: 실측일 기준 오늘부터 영업일 0~4일 이내
    measurement_d4 = meas_d is not None and 0 <= meas_d <= 4
    # 시공 D-3: 시공일 기준 오늘부터 영업일 0~3일 이내
    construction_d3 = cons_d is not None and 0 <= cons_d <= 3
    # 생산 D-2: 시공일 기준 오늘부터 영업일 0~2일 이내, 아직 시공 단계가 아니면 생산 준비 경보로 간주(MVP)
    try:
        stage = ((structured_data or {}).get('workflow') or {}).get('stage')
    except Exception:
        stage = None
    production_d2 = cons_d is not None and 0 <= cons_d <= 2 and stage not in ('CONSTRUCTION',)

    drawing_overdue = False
    try:
        wf = (structured_data or {}).get('workflow') or {}
        stage = wf.get('stage')
        stage_updated_at = wf.get('stage_updated_at')
        if stage in ('DRAWING', 'CONFIRM') and stage_updated_at:
            ts = datetime.datetime.fromisoformat(str(stage_updated_at))
            delta = datetime.datetime.now() - ts
            drawing_overdue = delta.total_seconds() >= (48 * 3600)
    except Exception:
        drawing_overdue = False

    return {
        'urgent': urgent,
        'measurement_d4': measurement_d4,
        'measurement_days': meas_d,  # 실제 D-값 표시용
        'construction_d3': construction_d3,
        'construction_days': cons_d,  # 실제 D-값 표시용
        'production_d2': production_d2,
        'production_days': cons_d,  # 생산도 시공일 기준
        'drawing_overdue': drawing_overdue
    }


def _sales_domain_fallback_match(user, order, structured_data) -> bool:
    """SALES_DOMAIN 레거시 fallback: assignee 미지정 시 주문 담당자명 일치 허용."""
    if not user:
        return False
    try:
        sales_assignee_ids = get_assignee_ids(order, 'SALES_DOMAIN')
    except Exception:
        sales_assignee_ids = []
    if sales_assignee_ids:
        return False

    manager_names = set()
    parties = (structured_data.get('parties') or {}) if isinstance(structured_data, dict) else {}
    manager_name_sd = ((parties.get('manager') or {}).get('name') or '').strip()
    if manager_name_sd:
        manager_names.add(manager_name_sd.lower())

    manager_name_col = (order.manager_name or '').strip()
    if manager_name_col:
        manager_names.add(manager_name_col.lower())

    wf_tmp = (structured_data.get('workflow') or {}) if isinstance(structured_data, dict) else {}
    current_quest = (wf_tmp.get('current_quest') or {})
    owner_person = (current_quest.get('owner_person') or '').strip()
    if owner_person:
        manager_names.add(owner_person.lower())

    user_name = (user.name or '').strip().lower()
    user_username = (user.username or '').strip().lower()
    return (user_name in manager_names) or (user_username in manager_names)


def _can_modify_sales_domain(user, order, structured_data, emergency_override=False, override_reason=None) -> bool:
    if not user:
        return False
    if can_modify_domain(user, order, 'SALES_DOMAIN', emergency_override, override_reason):
        return True
    return _sales_domain_fallback_match(user, order, structured_data)


def _drawing_status_label(status: str) -> str:
    code = (status or '').upper()
    return {
        'PENDING': '작업중',
        'TRANSFERRED': '확정 대기',
        'RETURNED': '수정 요청됨',
        'CONFIRMED': '완료',
        'DONE': '완료',
    }.get(code, code or '-')


def _drawing_next_action_text(drawing_status: str, has_assignee: bool) -> str:
    s = (drawing_status or 'PENDING').upper()
    if not has_assignee:
        return '도면 담당자 지정 필요'
    if s == 'TRANSFERRED':
        return '주문 담당 수령 확정 또는 수정 요청'
    if s == 'RETURNED':
        return '도면 담당 수정본 재전달 필요'
    if s in ('CONFIRMED', 'DONE'):
        return '도면 완료 · 다음 단계 확인'
    return '도면 담당 전달 진행'


def apply_erp_display_fields_to_orders(orders, processed_ids=None):
    if not orders:
        return
    if processed_ids is None:
        processed_ids = set()
    for order in orders:
        if order and order.id not in processed_ids:
            apply_erp_display_fields(order)

# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------

@erp_bp.route('/erp/dashboard')
@login_required
def erp_dashboard():
    """ERP 프로세스 대시보드(MVP)"""
    db = get_db()
    
    # 현재 사용자 확인 (관리자 여부, ERP 수정 권한)
    is_admin = False
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    if current_user and current_user.role == 'ADMIN':
        is_admin = True
    can_edit_erp_flag = can_edit_erp(current_user)
    
    # filters (query params)
    f_stage = (request.args.get('stage') or '').strip()
    f_urgent = (request.args.get('urgent') or '').strip()  # '1'
    f_has_alert = (request.args.get('has_alert') or '').strip()  # '1'
    f_alert_type = (request.args.get('alert_type') or '').strip()  # 'urgent', 'measurement_d4', 'construction_d3', 'production_d2'
    f_q = (request.args.get('q') or '').strip()
    f_team = (request.args.get('team') or '').strip()  # 팀 필터 추가

    # ERP 대시보드: ERP Beta로 생성된 주문만 표시
    orders = (
        db.query(Order)
        .filter(Order.deleted_at.is_(None), Order.is_erp_beta.is_(True))
        .order_by(Order.created_at.desc())
        .limit(300)
        .all()
    )

    # order_attachments count map
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

        # Quest 정보 가져오기
        current_quest = None
        quests = sd.get('quests') or []
        if stage:
            CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}
            stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
            stage_label_from_code = STAGE_LABELS.get(stage_code, stage)
            # 도면 단계는 퀘스트 승인 흐름 비활성화
            if stage_code != 'DRAWING':
                # 모든 가능한 stage 값을 체크
                possible_stages = {stage, stage_code, stage_label_from_code}
                # 한글 레이블의 영문 코드 역매핑 추가
                if stage in STAGE_NAME_TO_CODE:
                    possible_stages.add(STAGE_NAME_TO_CODE[stage])
                # 영문 코드의 한글 레이블 추가
                if stage_code in STAGE_LABELS:
                    possible_stages.add(STAGE_LABELS[stage_code])
                
                matching_quests = []
                for q in quests:
                    if isinstance(q, dict):
                        quest_stage = q.get('stage')
                        if quest_stage in possible_stages:
                            matching_quests.append(q)
                
                if matching_quests:
                    open_quests = [q for q in matching_quests if str(q.get('status', 'OPEN')).upper() == 'OPEN']
                    if open_quests:
                        open_quests.sort(key=lambda x: (
                            x.get('created_at') or x.get('updated_at') or '1970-01-01T00:00:00',
                        ), reverse=True)
                        current_quest = open_quests[0]
                    else:
                        matching_quests.sort(key=lambda x: (
                            x.get('created_at') or x.get('updated_at') or '1970-01-01T00:00:00',
                        ), reverse=True)
                        current_quest = matching_quests[0]
                
                if not current_quest:
                    quest_tpl = get_quest_template_for_stage(stage)
                    if quest_tpl:
                        # create_quest_from_template을 사용하여 동적 팀 할당 적용
                        temp_quest = create_quest_from_template(stage, None, sd)
                        if temp_quest:
                            current_quest = temp_quest
                        else:
                            team_approvals_template = {}
                            for team in quest_tpl.get('required_approvals', []):
                                if team:
                                    team_approvals_template[str(team)] = {
                                        'approved': False,
                                        'approved_by': None,
                                        'approved_at': None,
                                    }
                            current_quest = {
                                'stage': stage,
                                'title': quest_tpl.get('title', ''),
                                'description': quest_tpl.get('description', ''),
                                'owner_team': quest_tpl.get('owner_team', ''),
                                'status': 'OPEN',
                                'team_approvals': team_approvals_template
                            }

        # Quest 승인 상태 확인
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
                    existing_cs_approval = current_quest.get('team_approvals', {}).get('CS', {})
                    if isinstance(existing_cs_approval, dict):
                        approved_status = existing_cs_approval.get('approved', False)
                    else:
                        approved_status = bool(existing_cs_approval)
                    
                    current_quest['team_approvals'] = {
                        'CS': {
                            'approved': approved_status,
                            'approved_by': existing_cs_approval.get('approved_by') if isinstance(existing_cs_approval, dict) else None,
                            'approved_at': existing_cs_approval.get('approved_at') if isinstance(existing_cs_approval, dict) else None,
                        }
                    }
                    team_approvals_raw = current_quest.get('team_approvals', {})
            
            if quest_status == 'OPEN':
                all_approved = False
                missing_teams = required_teams.copy() if required_teams else []
                team_approvals = {}
                for team in required_teams:
                    team_approvals[team] = False
            elif quest_status == 'COMPLETED':
                all_approved = True
                missing_teams = []
                team_approvals = {}
                for team in required_teams:
                    team_approvals[team] = True
            else:
                if not required_teams:
                    all_approved = (quest_status == 'COMPLETED')
                    missing_teams = []
                    team_approvals = {}
                else:
                    team_approvals = {}
                    for team in required_teams:
                        team_key = str(team)
                        approval_data = team_approvals_raw.get(team_key) or team_approvals_raw.get(team)
                        if approval_data is None:
                            team_approvals[team] = False
                        elif isinstance(approval_data, dict):
                            team_approvals[team] = approval_data.get('approved', False)
                        else:
                            team_approvals[team] = bool(approval_data)
                    missing_teams = [t for t in required_teams if not team_approvals.get(t, False)]
                    all_approved = (len(missing_teams) == 0)

        # 담당팀
        stage_code = STAGE_NAME_TO_CODE.get(stage, stage)
        responsible_team = DEFAULT_OWNER_TEAM_BY_STAGE.get(stage_code, None)
        if stage_code in ("MEASURE", "CONFIRM"):
            orderer_name_check = (((sd.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
            if orderer_name_check and "라홈" in orderer_name_check:
                responsible_team = 'CS'
        
        # 담당자 기반 승인 시 지정 담당자 이름 목록 (승인 방식 영역에 표시)
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
                        # 레거시 호환: assignments/root 모두 확인
                        for a in ((assignments.get('drawing_assignees') or []) + (sd.get('drawing_assignees') or [])):
                            if isinstance(a, dict) and a.get('id'):
                                user_ids.append(a['id'])
                # 타입 정규화
                norm_user_ids = []
                for uid in user_ids:
                    try:
                        norm_user_ids.append(int(uid))
                    except (TypeError, ValueError):
                        continue
                user_ids = norm_user_ids

                if user_ids:
                    assignee_users = db.query(User).filter(User.id.in_(user_ids)).all()
                    assignee_display_names = [u.name for u in assignee_users if u.name]
                elif stage_code in ('MEASURE', 'CONFIRM'):
                    # 호환 fallback: sales_assignee_user_ids 미지정 시 주문 담당자명을 표시
                    manager_name_fallback = (
                        (((sd.get('parties') or {}).get('manager') or {}).get('name'))
                        or o.manager_name
                        or current_quest.get('owner_person')
                        or ''
                    )
                    manager_name_fallback = str(manager_name_fallback).strip()
                    if manager_name_fallback:
                        assignee_display_names = [manager_name_fallback]

                # 담당자 승인 가능 여부 계산 (UI 버튼 표시용)
                if current_user:
                    domain = 'DRAWING_DOMAIN' if stage_code == 'DRAWING' else ('SALES_DOMAIN' if stage_code in ('MEASURE', 'CONFIRM') else None)
                    if domain:
                        can_assignee_approve = can_modify_domain(current_user, o, domain, False, None)
                        # SALES_DOMAIN 호환 fallback: assignee ids 비어 있고 담당자명이 현재 사용자와 일치하면 허용
                        if (not can_assignee_approve) and domain == 'SALES_DOMAIN' and not user_ids:
                            manager_names = set()
                            manager_name_sd = (((sd.get('parties') or {}).get('manager') or {}).get('name') or '').strip()
                            if manager_name_sd:
                                manager_names.add(manager_name_sd.lower())
                            manager_name_col = (o.manager_name or '').strip()
                            if manager_name_col:
                                manager_names.add(manager_name_col.lower())
                            owner_person = (current_quest.get('owner_person') or '').strip()
                            if owner_person:
                                manager_names.add(owner_person.lower())
                            user_name = (current_user.name or '').strip().lower()
                            user_username = (current_user.username or '').strip().lower()
                            if user_name in manager_names or user_username in manager_names:
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
        
        enriched.append({
            'id': o.id,
            'is_erp_beta': o.is_erp_beta,
            'structured_data': sd,
            'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
            'phone': (((sd.get('parties') or {}).get('customer') or {}).get('phone')) or '-',
            'address': (((sd.get('site') or {}).get('address_full')) or ((sd.get('site') or {}).get('address_main'))) or '-',
            'measurement_date': (((sd.get('schedule') or {}).get('measurement') or {}).get('date')),
            'construction_date': (((sd.get('schedule') or {}).get('construction') or {}).get('date')),
            'manager_name': (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-',
            'orderer_name': (((sd.get('parties') or {}).get('orderer') or {}).get('name') or '').strip() or None,
            'owner_team': responsible_team,
            'stage': stage,
            'alerts': alerts,
            'has_media': has_media,
            'attachments_count': cnt,
            'recommended_owner_team': recommend_owner_team(sd) or None,
            'current_quest': quest_payload,
        })

    # apply filters
    filtered = []
    for r in enriched:
        if f_stage:
            row_stage = (r.get('stage') or '').strip()
            req_stage = f_stage.strip()

            # 코드/라벨 혼용 입력 대응 (예: COMPLETED <-> 완료, AS <-> AS처리)
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
            required_teams = get_required_approval_teams_for_stage(r.get('stage'))
            if f_team not in required_teams:
                continue
        filtered.append(r)

    kpis = {
        'urgent_count': 0,
        'measurement_d4_count': 0,
        'construction_d3_count': 0,
        'production_d2_count': 0,
    }

    step_stats = {
        '주문접수': {'count': 0, 'overdue': 0, 'imminent': 0},
        '해피콜': {'count': 0, 'overdue': 0, 'imminent': 0},
        '실측': {'count': 0, 'overdue': 0, 'imminent': 0},
        '도면': {'count': 0, 'overdue': 0, 'imminent': 0},
        '고객컨펌': {'count': 0, 'overdue': 0, 'imminent': 0},
        '생산': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공': {'count': 0, 'overdue': 0, 'imminent': 0},
        'CS': {'count': 0, 'overdue': 0, 'imminent': 0},
        '완료': {'count': 0, 'overdue': 0, 'imminent': 0},
        'AS처리': {'count': 0, 'overdue': 0, 'imminent': 0},
    }

    # 상단 KPI 카드/프로세스 맵은 항상 전체 주문(enriched) 기준으로 집계
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
        # [순서 변경] 시공, 완료, CS, AS처리
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


@erp_bp.route('/erp/drawing-workbench')
@login_required
def erp_drawing_workbench_dashboard():
    """도면 작업실 대시보드: 도면 단계 협업 전용 화면(목록형)
    
    Phase 3: 정렬/페이지네이션 추가
    """
    db = get_db()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None

    q_raw = (request.args.get('q') or '').strip()
    q = q_raw.lower()
    status_filter = (request.args.get('status') or '').strip().upper()
    mine_only = (request.args.get('mine') or '').strip() == '1'
    unread_only = (request.args.get('unread') or '').strip() == '1'
    due_today_only = (request.args.get('due_today') or '').strip() == '1'
    assignee_filter_raw = (request.args.get('assignee') or '').strip()
    assignee_filter = assignee_filter_raw.lower()
    
    # Phase 3: 정렬/페이지네이션 파라미터
    sort_by = (request.args.get('sort') or '').strip().lower()
    page = 1
    try:
        page = max(1, int(request.args.get('page') or '1'))
    except (TypeError, ValueError):
        page = 1
    per_page = 25

    orders = (
        db.query(Order)
        .filter(Order.deleted_at.is_(None), Order.is_erp_beta.is_(True))
        .order_by(Order.created_at.desc())
        .limit(500)
        .all()
    )

    rows = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage_raw = _erp_get_stage(o, sd)
        # Convert label to code if necessary (e.g. '도면' -> 'DRAWING')
        stage_code = STAGE_NAME_TO_CODE.get(stage_raw, stage_raw)
        
        drawing_obj = sd.get('drawing') or {}
        drawing_status = (drawing_obj.get('status') or sd.get('drawing_status') or 'PENDING').upper()

        # [Connection Logic Improved]
        # Include order if:
        # 1. Current Stage is 'DRAWING'
        # 2. OR Drawing Status is 'RETURNED' (Revision Requested even in later stages like CONFIRM)
        is_drawing_stage = (stage_code == 'DRAWING')
        is_active_revision = (drawing_status == 'RETURNED')

        if not (is_drawing_stage or is_active_revision):
            continue

        customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-'
        manager_name = (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-'
        drawing_files = list(sd.get('drawing_current_files', []) or [])
        history = list(sd.get('drawing_transfer_history', []) or [])
        last_event = history[-1] if history else {}

        assignees = list(sd.get('drawing_assignees', []) or [])
        assignee_names = []
        for a in assignees:
            if isinstance(a, dict):
                n = (a.get('name') or '').strip()
                if n:
                    assignee_names.append(n)
            elif isinstance(a, str) and a.strip():
                assignee_names.append(a.strip())
        assignee_text = ', '.join(assignee_names) if assignee_names else '미지정'

        draw_assignee_ids = get_assignee_ids(o, 'DRAWING_DOMAIN')
        has_assignee = bool(draw_assignee_ids)
        user_id = current_user.id if current_user else None
        is_drawing_assignee = bool(user_id and user_id in draw_assignee_ids)
        can_sales = _can_modify_sales_domain(current_user, o, sd, False, None)
        my_todo = (
            (drawing_status in ('PENDING', 'RETURNED') and is_drawing_assignee)
            or (drawing_status == 'TRANSFERRED' and can_sales)
        )

        if mine_only and not my_todo:
            continue

        unchecked_requests = 0
        for h in history:
            if not isinstance(h, dict) or h.get('action') != 'REQUEST_REVISION':
                continue
            review = h.get('review_check') if isinstance(h.get('review_check'), dict) else {}
            if not bool(review.get('checked')):
                unchecked_requests += 1
        if unread_only and unchecked_requests <= 0:
            continue

        alerts = _erp_alerts(o, sd, 0)
        due_today = (
            alerts.get('measurement_days') == 0
            or alerts.get('construction_days') == 0
        )
        if due_today_only and not due_today:
            continue

        if assignee_filter:
            if assignee_filter not in (assignee_text or '').lower():
                continue

        if q:
            hay = ' '.join([
                str(o.id),
                str(customer_name),
                str(manager_name),
                str(assignee_text),
                str((last_event or {}).get('note') or ''),
            ]).lower()
            if q not in hay:
                continue

        latest_request_no = None
        for h in reversed(history):
            if isinstance(h, dict) and (h.get('action') == 'REQUEST_REVISION'):
                try:
                    latest_request_no = int(h.get('target_drawing_number'))
                except Exception:
                    latest_request_no = None
                break

        h_action = (last_event or {}).get('action') or ''
        h_action_label = {
            'TRANSFER': '도면 전달',
            'REQUEST_REVISION': '수정 요청',
            'CANCEL_TRANSFER': '전달 취소',
            'CONFIRM_RECEIPT': '수령 확정',
        }.get(h_action, h_action or '-')

        sla_level = '지연' if alerts.get('drawing_overdue') else ('오늘 마감' if due_today else '정상')
        rows.append({
            'id': o.id,
            'customer_name': customer_name,
            'manager_name': manager_name,
            'assignee_text': assignee_text,
            'drawing_status': drawing_status,
            'drawing_status_label': _drawing_status_label(drawing_status),
            'file_count': len(drawing_files),
            'target_no': latest_request_no,
            'next_action': _drawing_next_action_text(drawing_status, has_assignee),
            'latest_event_at': (last_event or {}).get('transferred_at') or (last_event or {}).get('at') or '-',
            'latest_event_label': h_action_label,
            'latest_event_note': (last_event or {}).get('note') or '',
            'sla_level': sla_level,
            'is_overdue': bool(alerts.get('drawing_overdue')),
            'due_today': due_today,
            'unread_count': unchecked_requests,
            'my_todo': my_todo,
        })

    # 프로세스맵 타일 숫자: status 필터 없이 항상 전체 단계별 건수 표시 (ERP 프로세스 대시보드와 동일)
    stats = {
        'total': len(rows),
        'WAITING': 0,
        'IN_PROGRESS': 0,
        'RETURNED': 0,
        'TRANSFERRED': 0,
        'CONFIRMED': 0,
        'overdue': 0,
        'unread': 0,
    }
    for r in rows:
        status = (r.get('drawing_status') or 'WAITING').upper()
        if status == 'PENDING':
            status = 'WAITING'
        if status in stats:
            stats[status] += 1
        if r.get('is_overdue'):
            stats['overdue'] += 1
        if r.get('unread_count', 0) > 0:
            stats['unread'] += 1

    # 타일 클릭 시: 해당 단계만 목록에 표시 (status_filter 적용)
    if status_filter:
        def _match_status(row_status: str) -> bool:
            s = (row_status or '').upper()
            if status_filter == 'WAITING':
                return s in ('WAITING', 'PENDING')
            return s == status_filter
        rows = [r for r in rows if _match_status(r.get('drawing_status') or '')]

    rows.sort(key=lambda r: (
        0 if r.get('my_todo') else 1,
        0 if r.get('is_overdue') else 1,
        -int(r.get('id') or 0),
    ))
    
    # Phase 3: 정렬 적용
    if sort_by:
        reverse = False
        if sort_by.startswith('-'):
            reverse = True
            sort_by = sort_by[1:]
        
        if sort_by == 'sla':
            # SLA: 지연 > 오늘마감 > 정상
            rows.sort(key=lambda r: (
                0 if r.get('is_overdue') else (1 if r.get('due_today') else 2),
                -int(r.get('id') or 0)
            ), reverse=reverse)
        elif sort_by == 'status':
            # 상태순: RETURNED > TRANSFERRED > IN_PROGRESS > WAITING > CONFIRMED
            status_order = {'RETURNED': 1, 'TRANSFERRED': 2, 'IN_PROGRESS': 3, 'WAITING': 4, 'CONFIRMED': 5}
            rows.sort(key=lambda r: (
                status_order.get(r.get('drawing_status'), 99),
                -int(r.get('id') or 0)
            ), reverse=reverse)
        elif sort_by == 'updated_at':
            # 최근 업데이트순
            rows.sort(key=lambda r: r.get('latest_event_at') or '', reverse=not reverse)
        elif sort_by == 'unread':
            # 미확인 요청순
            rows.sort(key=lambda r: (
                -int(r.get('unread_count') or 0),
                -int(r.get('id') or 0)
            ), reverse=reverse)
        elif sort_by == 'id':
            # 주문번호순
            rows.sort(key=lambda r: int(r.get('id') or 0), reverse=reverse)

    total_count = len(rows)
    # Phase 3: 페이지네이션
    total_pages = (total_count + per_page - 1) // per_page if per_page > 0 else 1
    page = min(page, total_pages) if total_pages > 0 else 1
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    rows = rows[start_idx:end_idx]

    return render_template(
        'erp_drawing_workbench_dashboard.html',
        rows=rows,
        stats=stats,  # Phase 2: 통계 추가
        pagination={  # Phase 3: 페이지네이션 추가
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
        },
        sort_by=request.args.get('sort') or '',  # Phase 3: 현재 정렬 상태
        filters={
            'q': q_raw,
            'status': status_filter,
            'mine': '1' if mine_only else '',
            'unread': '1' if unread_only else '',
            'due_today': '1' if due_today_only else '',
            'assignee': assignee_filter_raw,
        },
        can_edit_erp=can_edit_erp(current_user),
        erp_beta_enabled=True,
    )


@erp_bp.route('/erp/drawing-workbench/<int:order_id>')
@login_required
def erp_drawing_workbench_detail(order_id):
    """도면 작업실 상세: 도면팀↔주문담당 협업 실행판."""
    db = get_db()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.deleted_at.is_(None),
        Order.is_erp_beta.is_(True)
    ).first()
    if not order:
        flash('주문을 찾을 수 없습니다.', 'warning')
        return redirect(url_for('erp.erp_drawing_workbench_dashboard'))

    s_data = _ensure_dict(order.structured_data)
    stage = _erp_get_stage(order, s_data)
    drawing_status = ((s_data.get('drawing') or {}).get('status') or s_data.get('drawing_status') or 'PENDING').upper()
    drawing_files = list(s_data.get('drawing_current_files', []) or [])
    history_raw = list(s_data.get('drawing_transfer_history', []) or [])

    history = []
    for idx, h in enumerate(history_raw):
        if not isinstance(h, dict):
            continue
        h_action = (h.get('action') or '').strip()
        event_key = f"{idx}:{h_action}:{h.get('at') or h.get('transferred_at') or ''}:{h.get('by_user_id') or ''}"
        history.append({
            **h,
            'event_key': event_key,
            'action_label': {
                'TRANSFER': '도면 전달',
                'REQUEST_REVISION': '수정 요청',
                'CANCEL_TRANSFER': '전달 취소',
                'CONFIRM_RECEIPT': '수령 확정',
            }.get(h_action, h_action or '-'),
            'at_text': h.get('transferred_at') or h.get('at') or '-',
            'by_text': h.get('by_user_name') or '-',
            'target_no': h.get('target_drawing_number') or h.get('replace_target_number'),
            'files': list(h.get('files') or []) if isinstance(h.get('files'), list) else [],
        })

    revision_requests = [h for h in history if (h.get('action') == 'REQUEST_REVISION')]
    revision_requests.reverse()
    unread_count = 0
    for h in revision_requests:
        review = h.get('review_check') if isinstance(h.get('review_check'), dict) else {}
        if not bool(review.get('checked')):
            unread_count += 1

    transfer_events = [h for h in history if (h.get('action') == 'TRANSFER')]
    latest_transfer = transfer_events[-1] if transfer_events else None
    prev_transfer = transfer_events[-2] if len(transfer_events) > 1 else None

    # 수정본 파일 마킹 (최근 수정 요청 이후에 전달된 파일)
    if latest_transfer and revision_requests:
        latest_req = revision_requests[0]  # revision_requests는 이미 reverse() 되어 있음 -> 0번이 가장 최신
        tf_at = latest_transfer.get('at') or latest_transfer.get('transferred_at') or ''
        req_at = latest_req.get('at') or latest_req.get('transferred_at') or ''

        if tf_at > req_at:
            # 이 전달본은 수정 요청에 대한 응답임
            latest_keys = set()
            for f in (latest_transfer.get('files') or []):
                if isinstance(f, dict):
                    k = f.get('key')
                    if k:
                        latest_keys.add(k)

            for df in drawing_files:
                if isinstance(df, dict) and df.get('key') in latest_keys:
                    df['is_revision'] = True

    active_tab = (request.args.get('tab') or 'timeline').strip().lower()
    if active_tab not in ('timeline', 'requests', 'compare'):
        active_tab = 'timeline'
    highlight_event_id = (request.args.get('event_id') or '').strip()
    highlight_target_no = request.args.get('target_no')
    try:
        highlight_target_no = int(highlight_target_no) if highlight_target_no not in (None, '') else None
    except (TypeError, ValueError):
        highlight_target_no = None

    for h in history:
        h['is_highlight'] = bool(highlight_event_id) and (h.get('event_key') == highlight_event_id)
    for h in revision_requests:
        h['is_highlight'] = bool(highlight_event_id) and (h.get('event_key') == highlight_event_id)
        if highlight_target_no and int(h.get('target_no') or 0) == int(highlight_target_no):
            h['is_highlight'] = True

    draw_assignee_ids = get_assignee_ids(order, 'DRAWING_DOMAIN')
    has_assignee = bool(draw_assignee_ids)
    current_user_id = current_user.id if current_user else None
    is_drawing_assignee = bool(current_user_id and current_user_id in draw_assignee_ids)
    can_transfer = bool(has_assignee and (
        (current_user and current_user.role == 'ADMIN') or is_drawing_assignee
    ))

    can_sales_domain = _can_modify_sales_domain(current_user, order, s_data, False, None)
    can_request_revision = can_sales_domain
    can_confirm_receipt = bool(can_sales_domain and drawing_status == 'TRANSFERRED')

    # 전달 취소 버튼: 도면 전달(TRANSFER)이 한 번이라도 있을 때만 표시
    can_cancel_transfer = False
    if latest_transfer is not None:
        if current_user and current_user.role == 'ADMIN':
            can_cancel_transfer = True
        elif can_transfer:
            can_cancel_transfer = True
        else:
            last_transfer = latest_transfer
            try:
                can_cancel_transfer = int(last_transfer.get('by_user_id')) == int(current_user_id)
            except Exception:
                can_cancel_transfer = False

    customer_name = (((s_data.get('parties') or {}).get('customer') or {}).get('name')) or '-'
    manager_name = (((s_data.get('parties') or {}).get('manager') or {}).get('name')) or (order.manager_name or '-') or '-'
    assignee_names = []
    for uid in draw_assignee_ids:
        u = db.query(User).filter(User.id == uid).first()
        if u and u.name:
            assignee_names.append(u.name)
    assignee_text = ', '.join(assignee_names) if assignee_names else '미지정'
    next_action = _drawing_next_action_text(drawing_status, has_assignee)
    status_label = _drawing_status_label(drawing_status)

    checklist = [
        {'label': '도면 담당자 지정', 'ok': has_assignee},
        {'label': '최신 전달본 확인', 'ok': bool(drawing_files)},
        {'label': '요청사항 확인', 'ok': unread_count == 0},
    ]

    # 제품 정보: items를 기본으로, legacy/products 키도 fallback 허용
    raw_product_items = (
        s_data.get('items')
        or s_data.get('products')
        or s_data.get('product_items')
        or []
    )
    if isinstance(raw_product_items, dict):
        raw_product_items = [raw_product_items]
    product_items = []
    for it in list(raw_product_items):
        if not isinstance(it, dict):
            continue
        item = dict(it)
        item['width'] = item.get('width') or item.get('spec_width') or ''
        item['depth'] = item.get('depth') or item.get('spec_depth') or ''
        item['height'] = item.get('height') or item.get('spec_height') or ''
        item['measurement_images'] = []
        product_items.append(item)
    
    # 실측 사진 (ERP Beta 실측=measurement, legacy measure_photo/photo 포함)
    measure_photos = []
    common_measure_photos = []
    attachments = db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.category.in_(['measurement', 'measure_photo', 'photo'])
    ).order_by(OrderAttachment.created_at.desc()).all()
    for att in attachments:
        item_index_raw = getattr(att, 'item_index', None)
        try:
            item_index = int(item_index_raw) if item_index_raw is not None else None
            if item_index is not None and item_index < 0:
                item_index = None
        except (TypeError, ValueError):
            item_index = None

        photo = {
            'filename': att.filename,
            'view_url': f'/api/files/view/{att.storage_key}',
            'download_url': f'/api/files/download/{att.storage_key}',
            'key': att.storage_key,
            'item_index': item_index,
        }
        measure_photos.append(photo)
        if item_index is not None and 0 <= item_index < len(product_items):
            product_items[item_index].setdefault('measurement_images', []).append(photo)
        else:
            common_measure_photos.append(photo)

    return render_template(
        'erp_drawing_workbench_detail.html',
        order=order,
        stage=stage,
        drawing_status=drawing_status,
        drawing_status_label=status_label,
        next_action=next_action,
        customer_name=customer_name,
        manager_name=manager_name,
        assignee_text=assignee_text,
        drawing_files=drawing_files,
        history=history,
        revision_requests=revision_requests,
        latest_transfer=latest_transfer,
        prev_transfer=prev_transfer,
        active_tab=active_tab,
        highlight_event_id=highlight_event_id,
        highlight_target_no=highlight_target_no,
        unread_count=unread_count,
        checklist=checklist,
        can_transfer=can_transfer,
        can_request_revision=can_request_revision,
        can_confirm_receipt=can_confirm_receipt,
        can_cancel_transfer=can_cancel_transfer,
        can_edit_erp=can_edit_erp(current_user),
        my_id=(current_user.id if current_user else 0),
        my_role=(current_user.role if current_user else ''),
        my_team=(current_user.team if current_user else ''),
        my_name=(current_user.name if current_user else ''),
        history_json=history_raw,
        product_items=product_items,
        measure_photos=measure_photos,
        common_measure_photos=common_measure_photos,
    )


@erp_bp.route('/erp/measurement')
@login_required
def erp_measurement_dashboard():
    """ERP Beta - 실측 대시보드 (structured_data 기반, MVP는 Order 컬럼 연동으로 운용)"""
    db = get_db()
    selected_date = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    manager_filter = (request.args.get('manager') or '').strip()
    open_map = request.args.get('open_map') == '1'

    base_query = db.query(Order).filter(Order.status != 'DELETED')
    
    if manager_filter:
        base_query = base_query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    query = base_query

    # 날짜 필터: ERP Beta 주문은 Order.measurement_date가 null일 수 있으므로
    if selected_date:
        # 넓은 범위로 가져오기: measurement_date 또는 received_date가 필터 날짜와 일치
        try:
            filter_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
            date_start = filter_date - datetime.timedelta(days=30)
            date_end = filter_date + datetime.timedelta(days=30)
        except:
            date_start = None
            date_end = None
        
        date_conditions = [
            Order.measurement_date == selected_date,
            Order.received_date == selected_date,
            Order.scheduled_date == selected_date,
            Order.completion_date == selected_date,
            Order.as_received_date == selected_date,
            Order.as_completed_date == selected_date
        ]
        
        # ERP Beta 주문도 포함 (최근 범위로 제한)
        # received_date는 String 타입이므로 문자열로 비교 (명시적 캐스팅)
        if date_start and date_end:
            date_start_str = date_start.strftime('%Y-%m-%d')
            date_end_str = date_end.strftime('%Y-%m-%d')
            date_conditions.append(
                and_(
                    Order.is_erp_beta == True,
                    func.cast(Order.received_date, String) >= date_start_str,
                    func.cast(Order.received_date, String) <= date_end_str
                )
            )
        else:
            date_conditions.append(Order.is_erp_beta == True)
        
        query = query.filter(or_(*date_conditions))

    # 먼저 더 많은 주문을 가져온 후 Python에서 필터링
    all_rows = query.order_by(Order.id.desc()).limit(500).all()
    
    # 구조화된 데이터 보정 및 표시 정보 반영
    for r in all_rows:
        r.structured_data = _ensure_dict(r.structured_data)
    apply_erp_display_fields_to_orders(all_rows)

    # 패널 집계는 날짜 필터와 무관하게 계산
    panel_orders = base_query.order_by(Order.id.desc()).limit(1500).all()

    # 날짜별 실측 건수 패널 데이터 생성
    def load_holidays_for_year(year):
        try:
            file_path = os.path.join('data', f'holidays_kr_{year}.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return set(data.get('dates', []))
        except Exception:
            return set()

    try:
        base_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
    except Exception:
        base_date = datetime.date.today()

    today_only = datetime.date.today()
    # 실측: 오늘부터 2주 후까지만 표기
    range_start = today_only
    range_end = today_only + datetime.timedelta(days=14)
    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= load_holidays_for_year(y)

    measurement_counts = {}
    for order in panel_orders:
        date_value = None
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
            if erp_measurement_date:
                date_value = str(erp_measurement_date)
        if not date_value and order.measurement_date:
            date_value = str(order.measurement_date)
        if not date_value:
            continue
        try:
            d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
        except Exception:
            continue
        if d < range_start or d > range_end:
            continue
        key = d.strftime('%Y-%m-%d')
        measurement_counts[key] = measurement_counts.get(key, 0) + 1

    measurement_panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        measurement_panel_dates.append({
            'date': date_str,
            'count': measurement_counts.get(date_str, 0),
            'weekday': current.weekday(),
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_selected': date_str == selected_date
        })
        current += datetime.timedelta(days=1)
    
    # Python 레벨에서 정확한 필터링
    rows = []
    for order in all_rows:
        if selected_date:
            should_include = False
            
            # ERP Beta 주문: structured_data.measurement_date 우선 확인
            if order.is_erp_beta and order.structured_data:
                sd = order.structured_data
                erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if erp_measurement_date and str(erp_measurement_date) == selected_date:
                    should_include = True
                elif order.measurement_date and str(order.measurement_date) == selected_date:
                    should_include = True
            else:
                if order.measurement_date and str(order.measurement_date) == selected_date:
                    should_include = True
            
            if should_include:
                rows.append(order)
        else:
            rows.append(order)
    
    # 최종 결과를 300개로 제한
    rows = rows[:300]

    # ERP Beta 주문의 제품 표시값을 structured_data 기준으로 보정
    apply_erp_display_fields_to_orders(rows)
    
    # 담당자 기준으로 정렬 (같은 담당자끼리 그룹화)
    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''
    
    rows.sort(key=lambda o: (get_manager_name_for_sort(o) or 'ZZZ', o.id))

    # 지도 보기 요청이면 기존 map_view를 date/status 파라미터로 오픈하도록 리다이렉트
    if open_map:
        return redirect(url_for('map_view', date=selected_date, status='MEASURED'))

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_measurement_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        measurement_panel_dates=measurement_panel_dates,
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
    )

@erp_bp.route('/erp/shipment')
@login_required
def erp_shipment_dashboard():
    """ERP Beta - 출고 대시보드 (날짜별 시공 건수, AS 포함, 출고일지 스타일)"""
    db = get_db()
    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    today_dt = datetime.datetime.strptime(today_date, '%Y-%m-%d').date()
    manager_filter = (request.args.get('manager') or '').strip()
    
    req_date = request.args.get('date')
    if not req_date:
        return redirect(url_for('erp.erp_shipment_dashboard', date=today_date, manager=manager_filter or None))
    try:
        datetime.datetime.strptime(req_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return redirect(url_for('erp.erp_shipment_dashboard', date=today_date, manager=manager_filter or None))
    selected_date = req_date

    base_query = db.query(Order).filter(Order.status != 'DELETED')
    if manager_filter:
        base_query = base_query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    # 패널용: ERP Beta + AS 주문 넓게 (날짜별 시공 건수 집계)
    panel_orders = base_query.filter(
        or_(
            Order.is_erp_beta == True,
            Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED'])
        )
    ).order_by(Order.id.desc()).limit(1500).all()

    settings = load_erp_shipment_settings()
    worker_settings = normalize_erp_shipment_workers(settings.get('construction_workers', []))

    def normalize_worker_name(name):
        return str(name or '').strip().lower()

    worker_name_map = {normalize_worker_name(w['name']): w for w in worker_settings if w.get('name')}

    def get_order_construction_date(order):
        date_value = None
        if order.status in ('AS_RECEIVED', 'AS_COMPLETED'):
            if order.scheduled_date:
                date_value = str(order.scheduled_date)
            elif order.as_received_date and str(order.as_received_date) != '':
                date_value = str(order.as_received_date)
            elif not date_value and order.as_completed_date:
                date_value = str(order.as_completed_date)
        
        if not date_value and order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            cons = (sd.get('schedule') or {}).get('construction') or {}
            cons_date = cons.get('date')
            if cons_date:
                date_value = str(cons_date)
                
        if not date_value and order.is_erp_beta and order.scheduled_date:
            date_value = str(order.scheduled_date)
        return date_value

    def get_order_spec_units(order):
        if not order.is_erp_beta or not order.structured_data:
            return 0.0
        sd = order.structured_data or {}
        items = sd.get('items') or []
        total = 0.0
        for it in items:
            if not isinstance(it, dict):
                continue
            w_raw = (it.get('spec_width') or it.get('spec') or '')
            total += spec_w300_value(w_raw)
        return total

    def load_holidays_for_year(year):
        try:
            file_path = os.path.join('data', f'holidays_kr_{year}.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return set(data.get('dates', []))
        except Exception:
            return set()

    try:
        base_date = datetime.datetime.strptime(selected_date, '%Y-%m-%d').date()
    except Exception:
        base_date = datetime.date.today()

    range_start = today_dt
    range_end = today_dt + datetime.timedelta(days=14)
    years = {range_start.year, range_end.year}
    holiday_dates = set()
    for y in years:
        holiday_dates |= load_holidays_for_year(y)

    construction_counts = {}
    assigned_workers_by_date = {}
    spec_units_by_date = {}
    for order in panel_orders:
        date_value = get_order_construction_date(order)
        if not date_value:
            continue
        try:
            d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
        except Exception:
            continue
        if d < range_start or d > range_end:
            continue
        key = d.strftime('%Y-%m-%d')
        construction_counts[key] = construction_counts.get(key, 0) + 1

        shipment = {}
        if order.structured_data and isinstance(order.structured_data, dict):
            shipment = (order.structured_data.get('shipment') or {})
        workers = shipment.get('construction_workers') or []
        for w in workers:
            name_key = normalize_worker_name(w)
            if not name_key:
                continue
            if name_key in worker_name_map:
                assigned_workers_by_date.setdefault(key, set()).add(name_key)

        spec_units_by_date[key] = spec_units_by_date.get(key, 0.0) + get_order_spec_units(order)

    construction_panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        construction_panel_dates.append({
            'date': date_str,
            'count': construction_counts.get(date_str, 0),
            'weekday': current.weekday(),
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_selected': date_str == selected_date
        })
        current += datetime.timedelta(days=1)

    remaining_panel_dates = []
    current = range_start
    while current <= range_end:
        date_str = current.strftime('%Y-%m-%d')
        is_weekend = current.weekday() >= 5
        is_holiday = date_str in holiday_dates
        available_workers = []
        for w in worker_settings:
            if date_str in (w.get('off_dates') or []):
                continue
            available_workers.append(w)
        base_worker_count = len(available_workers)
        base_capacity = sum((w.get('capacity') or 0) for w in available_workers)
        assigned_names = assigned_workers_by_date.get(date_str, set())
        assigned_count = 0
        for w in available_workers:
            if normalize_worker_name(w.get('name')) in assigned_names:
                assigned_count += 1
        remaining_workers = max(base_worker_count - assigned_count, 0)
        used_capacity = spec_units_by_date.get(date_str, 0.0)
        remaining_capacity = max(base_capacity - used_capacity, 0)
        remaining_panel_dates.append({
            'date': date_str,
            'remaining_capacity': round(remaining_capacity, 1),
            'remaining_workers': remaining_workers,
            'total_capacity': round(base_capacity, 1),
            'total_workers': base_worker_count,
            'used_capacity': round(used_capacity, 1),
            'assigned_workers': assigned_count,
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'is_selected': date_str == selected_date,
            'alert_capacity': remaining_capacity <= 40,
            'alert_workers': remaining_workers <= 3
        })
        current += datetime.timedelta(days=1)

    # 선택 날짜에 해당하는 주문만: ERP Beta(시공일) 또는 AS(접수/완료일)
    all_candidates = base_query.filter(
        or_(
            Order.is_erp_beta == True,
            Order.status.in_(['AS_RECEIVED', 'AS_COMPLETED'])
        )
    ).order_by(Order.id.desc()).limit(500).all()
    rows = []
    for order in all_candidates:
        match = False
        if order.status in ('AS_RECEIVED', 'AS_COMPLETED'):
            if (order.scheduled_date and str(order.scheduled_date) == selected_date) or \
               (order.as_received_date and str(order.as_received_date) == selected_date) or \
               (order.as_completed_date and str(order.as_completed_date) == selected_date):
                match = True
        if not match and order.is_erp_beta:
            sd = order.structured_data or {}
            cons = (sd.get('schedule') or {}).get('construction') or {}
            if cons.get('date') and str(cons.get('date')) == selected_date:
                match = True
            if not match and order.scheduled_date and str(order.scheduled_date) == selected_date:
                match = True
        if match:
            rows.append(order)

    rows = rows[:300]
    
    # [추가] 생산 단계 퀘스트 승인 여부 확인
    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)
        sd = r.structured_data
        
        # 생산 단계(PRODUCTION, '생산') 퀘스트의 승인 여부 확인
        r.is_production_approved = False
        quests = sd.get('quests') or []
        production_quest = next((q for q in quests if q.get('stage') in ('PRODUCTION', '생산')), None)
        
        if production_quest:
            # 퀘스트 상태가 COMPLETED인지 확인
            quest_status = production_quest.get('status', 'OPEN')
            if quest_status == 'COMPLETED':
                r.is_production_approved = True
            else:
                # 또는 모든 팀 승인이 완료되었는지 확인
                team_approvals = production_quest.get('team_approvals') or {}
                required_teams = production_quest.get('required_approvals') or []
                if required_teams:
                    all_approved = all(
                        (team_approvals.get(team, {}).get('approved') if isinstance(team_approvals.get(team), dict) else team_approvals.get(team))
                        for team in required_teams
                    )
                    r.is_production_approved = all_approved
    
    apply_erp_display_fields_to_orders(rows)

    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    rows.sort(key=lambda o: (get_manager_name_for_sort(o) or 'ZZZ', o.id))

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_shipment_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        construction_panel_dates=construction_panel_dates,
        remaining_panel_dates=remaining_panel_dates,
        today_date=today_date,
        can_edit_erp=can_edit_erp(current_user),
    )

@erp_bp.route('/erp/as')
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
        return redirect(url_for('map_view', date=date_val, status=status_val))

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

@erp_bp.route('/erp/production/dashboard')
@login_required
def erp_production_dashboard():
    """생산 대시보드"""
    db = get_db()
    
    # User / Admin check
    user_id = session.get('user_id')
    user = get_user_by_id(user_id) if user_id else None
    is_admin = user and user.role == 'ADMIN'
    # 생산팀 필터링? (필요시 추가)

    # Filters
    f_stage = (request.args.get('stage') or '').strip()
    f_q = (request.args.get('q') or '').strip()
    
    # Orders Query
    orders = (
        db.query(Order)
        .filter(Order.deleted_at.is_(None), Order.is_erp_beta.is_(True))
        .order_by(Order.created_at.desc())
        .limit(300)
        .all()
    )
    
    # Attachments Count
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

    step_stats = {
        '제작대기': {'count': 0, 'overdue': 0, 'imminent': 0}, # 고객컨펌
        '제작중': {'count': 0, 'overdue': 0, 'imminent': 0},    # 생산
        '제작완료': {'count': 0, 'overdue': 0, 'imminent': 0},  # 시공
    }
    
    enriched = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage = _erp_get_stage(o, sd)
        
        # Filter logic: only relevant stages
        if stage not in ['고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION']:
            continue
            
        stage_label = stage
        if stage == 'CONFIRM' or stage == '고객컨펌': stage_label = '제작대기'
        if stage == 'PRODUCTION' or stage == '생산': stage_label = '제작중'
        if stage == 'CONSTRUCTION' or stage == '시공': stage_label = '제작완료'
        
        # [수정] 제작대기(고객컨펌) 단계에서 담당자 승인 여부 체크 (필터링하지 않고 플래그만 설정)
        is_sales_approved = False
        active_quest = None
        if stage_label == '제작대기':
            quests = sd.get('quests') or []
            # 현재 퀘스트 찾기 (OPEN, IN_PROGRESS, COMPLETED 모두 확인)
            active_quest = next((q for q in quests if q.get('stage') in ('CONFIRM', '고객컨펌')), None)
            
            if active_quest:
                # 담당자 기반 승인 확인 (assignee_approval)
                assignee_approval = active_quest.get('assignee_approval') or {}
                if isinstance(assignee_approval, dict):
                    is_sales_approved = assignee_approval.get('approved') is True
                else:
                    is_sales_approved = bool(assignee_approval)
                
                # 팀 기반 승인 확인 (team_approvals) - fallback
                if not is_sales_approved:
                    team_approvals = active_quest.get('team_approvals') or {}
                    # SALES 또는 영업팀 승인 확인
                    sales_val = team_approvals.get('SALES') or team_approvals.get('영업팀')
                    if isinstance(sales_val, dict):
                        is_sales_approved = sales_val.get('approved') is True
                    else:
                        is_sales_approved = bool(sales_val)

        # Search Filter
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
        
        # Enrich
        alerts = _erp_alerts(o, sd, att_counts.get(o.id, 0))
        
        # Stats update
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
        # {'label': '제작완료', 'display': '제작완료', **step_stats['제작완료']},
    ]
    
    kpis = {
        'urgent_count': sum(1 for r in enriched if (r.get('alerts') or {}).get('urgent')),
        'production_d2_count': sum(1 for r in enriched if (r.get('alerts') or {}).get('production_d2')),
        'measurement_d4_count': 0, # Not used here
        'construction_d3_count': 0, # Not used here
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

@erp_bp.route('/erp/construction/dashboard')
@login_required
def erp_construction_dashboard():
    """시공 대시보드"""
    db = get_db()
    user_id = session.get('user_id')
    user = get_user_by_id(user_id) if user_id else None
    is_admin = user and user.role == 'ADMIN'

    # Filters
    f_stage = (request.args.get('stage') or '').strip()
    f_q = (request.args.get('q') or '').strip()
    
    orders = (
        db.query(Order)
        .filter(Order.deleted_at.is_(None), Order.is_erp_beta.is_(True))
        .order_by(Order.created_at.desc())
        .limit(300)
        .all()
    )
    
    # Attachments Count
    att_counts = {}
    try:
        rows = db.execute(text("SELECT order_id, COUNT(*) AS cnt FROM order_attachments GROUP BY order_id")).fetchall()
        for r in rows:
            att_counts[int(r.order_id)] = int(r.cnt)
    except Exception:
        att_counts = {}

    TEAM_LABELS = {
        'CS': '라홈팀', 'SALES': '영업팀', 'MEASURE': '실측팀',
        'DRAWING': '도면팀', 'PRODUCTION': '생산팀', 'CONSTRUCTION': '시공팀',
    }

    step_stats = {
        '시공대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '시공완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }
    
    enriched = []
    for o in orders:
        sd = _ensure_dict(o.structured_data)
        stage = _erp_get_stage(o, sd)
        
        # Determine Display Stage
        display_stage = None
        
        # Check logs for "Started"
        hist = (sd.get('workflow') or {}).get('history') or []
        is_started = any(str(h.get('note')).strip() == '시공 시작' for h in hist)
        
        if stage == 'CONSTRUCTION' or stage == '시공':
            if is_started:
                display_stage = '시공중'
            else:
                display_stage = '시공대기'
        elif stage == 'COMPLETED' or stage == '완료' or stage == 'AS_WAIT':
            display_stage = '시공완료'
        elif stage == 'CONSTRUCTING': # Future proof
            display_stage = '시공중'
            
        if not display_stage:
            continue
            
        # Search Filter
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
        'measurement_d4_count': 0, 'production_d2_count': 0
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

