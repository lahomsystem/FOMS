from flask import Blueprint, render_template, request, jsonify, session, url_for, redirect, flash
from db import get_db
from models import Order, User
from apps.auth import login_required, role_required, get_user_by_id
import datetime
import re
import json
import os
import math
from sqlalchemy import or_, and_, func, String
from foms_address_converter import FOMSAddressConverter
from foms_map_generator import FOMSMapGenerator
from erp_policy import (
    STAGE_NAME_TO_CODE, DEFAULT_OWNER_TEAM_BY_STAGE, STAGE_LABELS,
    get_quest_template_for_stage, create_quest_from_template,
    get_required_approval_teams_for_stage, recommend_owner_team
)
from business_calendar import business_days_until
from sqlalchemy import text
import pytz


erp_beta_bp = Blueprint('erp_beta', __name__)

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------
ERP_SHIPMENT_SETTINGS_PATH = os.path.join('data', 'erp_shipment_settings.json')
DEFAULT_ERP_WORKER_CAPACITY = 10

# -------------------------------------------------------------------------
# Template Filters
# -------------------------------------------------------------------------
@erp_beta_bp.app_template_filter('split_count')
def split_count_filter(s, sep=','):
    """문자열을 sep로 나눈 비어있지 않은 항목 개수 (출고 대시보드 제품 수 fallback용)"""
    if not s:
        return 0
    return max(1, len([x for x in str(s).split(sep) if str(x).strip()]))

@erp_beta_bp.app_template_filter('split_list')
def split_list_filter(s, sep=','):
    """문자열을 sep로 나눈 리스트 (공백 제거, 출고 대시보드 제품 가로 스태킹용)"""
    if not s:
        return []
    return [x.strip() for x in str(s).split(sep) if x.strip()]

@erp_beta_bp.app_template_filter('strip_product_w')
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

@erp_beta_bp.app_template_filter('spec_w300')
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

@erp_beta_bp.app_template_filter('format_phone')
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

def normalize_erp_shipment_workers(workers):
    """출고 설정 시공자 목록 정규화 (name, capacity, off_dates)"""
    normalized = []
    if not isinstance(workers, list):
        return normalized
    for w in workers:
        if isinstance(w, dict):
            name = str(w.get('name') or w.get('text') or '').strip()
            cap_raw = w.get('capacity', w.get('daily_capacity', DEFAULT_ERP_WORKER_CAPACITY))
            try:
                capacity = int(cap_raw)
            except (ValueError, TypeError):
                capacity = DEFAULT_ERP_WORKER_CAPACITY
            if capacity < 0:
                capacity = DEFAULT_ERP_WORKER_CAPACITY
            off_raw = w.get('off_dates') or w.get('offDays') or []
            if not isinstance(off_raw, list):
                off_raw = []
            off_dates = []
            seen = set()
            for d in off_raw:
                ds = str(d).strip()
                if ds and ds not in seen:
                    seen.add(ds)
                    off_dates.append(ds)
        else:
            name = str(w).strip()
            capacity = DEFAULT_ERP_WORKER_CAPACITY
            off_dates = []
        
        if name:
            normalized.append({
                'name': name,
                'capacity': capacity,
                'off_dates': off_dates
            })
    return normalized

def load_erp_shipment_settings():
    """ERP 출고 설정(시공시간/도면담당자/시공자/현장주소 추가 목록) JSON 파일에서 로드"""
    try:
        if os.path.exists(ERP_SHIPMENT_SETTINGS_PATH):
            with open(ERP_SHIPMENT_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'construction_time': data.get('construction_time', []),
                    'drawing_manager': data.get('drawing_manager', []),
                    'construction_workers': normalize_erp_shipment_workers(data.get('construction_workers', [])),
                    'site_extra': data.get('site_extra', []),
                }
        return {'construction_time': [], 'drawing_manager': [], 'construction_workers': [], 'site_extra': []}
    except Exception as e:
        print(f"Error loading ERP shipment settings: {e}")
        return {'construction_time': [], 'drawing_manager': [], 'construction_workers': [], 'site_extra': []}

def save_erp_shipment_settings(settings):
    """ERP 출고 설정 저장"""
    try:
        os.makedirs(os.path.dirname(ERP_SHIPMENT_SETTINGS_PATH), exist_ok=True)
        with open(ERP_SHIPMENT_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving ERP shipment settings: {e}")
        return False


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
            return STAGE_LABELS.get(st, '주문접수')
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


def apply_erp_beta_display_fields(order):
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
            return STAGE_LABELS.get(st, '주문접수')
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


def apply_erp_beta_display_fields_to_orders(orders, processed_ids=None):
    if not orders:
        return
    if processed_ids is None:
        processed_ids = set()
    for order in orders:
        if order and order.id not in processed_ids:
            apply_erp_beta_display_fields(order)

# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------

@erp_beta_bp.route('/erp/dashboard')
@login_required
def erp_dashboard():
    """ERP 프로세스 대시보드(MVP)"""
    db = get_db()
    
    # 현재 사용자 확인 (관리자 여부 체크)
    is_admin = False
    if 'user_id' in session:
        user = get_user_by_id(session['user_id'])
        if user and user.role == 'ADMIN':
            is_admin = True
    
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
            
            matching_quests = []
            for q in quests:
                if isinstance(q, dict):
                    quest_stage = q.get('stage')
                    if quest_stage == stage or quest_stage == stage_code:
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
            'current_quest': {
                'title': current_quest.get('title', '') if current_quest else '',
                'description': current_quest.get('description', '') if current_quest else '',
                'owner_team': current_quest.get('owner_team', '') if current_quest else '',
                'status': current_quest.get('status', 'OPEN') if current_quest else 'OPEN',
                'all_approved': all_approved,
                'missing_teams': missing_teams,
                'required_approvals': required_teams,
                'team_approvals': team_approvals,
            } if current_quest else None,
        })

    # apply filters
    filtered = []
    for r in enriched:
        if f_stage and r.get('stage') != f_stage:
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
    }

    for r in filtered:
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
    )


@erp_beta_bp.route('/erp/measurement')
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
    apply_erp_beta_display_fields_to_orders(all_rows)

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
    apply_erp_beta_display_fields_to_orders(rows)
    
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

    return render_template(
        'erp_measurement_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        measurement_panel_dates=measurement_panel_dates,
        today_date=today_date
    )

@erp_beta_bp.route('/erp/shipment')
@login_required
def erp_shipment_dashboard():
    """ERP Beta - 출고 대시보드 (날짜별 시공 건수, AS 포함, 출고일지 스타일)"""
    db = get_db()
    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    today_dt = datetime.datetime.strptime(today_date, '%Y-%m-%d').date()
    manager_filter = (request.args.get('manager') or '').strip()
    
    req_date = request.args.get('date')
    # Use erp_beta.erp_shipment_dashboard for self-redirect within blueprint? 
    # Usually url_for('.erp_shipment_dashboard') is safer inside blueprint.
    # But since we register blueprint as 'erp_beta', url_for('erp_beta.erp_shipment_dashboard') works.
    if not req_date:
        return redirect(url_for('erp_beta.erp_shipment_dashboard', date=today_date, manager=manager_filter or None))
    try:
        req_dt = datetime.datetime.strptime(req_date, '%Y-%m-%d').date()
        if req_dt < today_dt:
            return redirect(url_for('erp_beta.erp_shipment_dashboard', date=today_date, manager=manager_filter or None))
    except (ValueError, TypeError):
        return redirect(url_for('erp_beta.erp_shipment_dashboard', date=today_date, manager=manager_filter or None))
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
    
    for r in rows:
        r.structured_data = _ensure_dict(r.structured_data)
    apply_erp_beta_display_fields_to_orders(rows)

    def get_manager_name_for_sort(order):
        if order.is_erp_beta and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    rows.sort(key=lambda o: (get_manager_name_for_sort(o) or 'ZZZ', o.id))

    return render_template(
        'erp_shipment_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        construction_panel_dates=construction_panel_dates,
        remaining_panel_dates=remaining_panel_dates,
        today_date=today_date
    )

@erp_beta_bp.route('/erp/shipment-settings')
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def erp_shipment_settings():
    """ERP 출고 설정 페이지 (시공시간/도면담당자/시공자/현장주소 추가 목록 - 제품설정처럼)"""
    settings = load_erp_shipment_settings()
    return render_template('erp_shipment_settings.html', settings=settings)

@erp_beta_bp.route('/api/erp/shipment-settings', methods=['GET'])
@login_required
def api_erp_shipment_settings_get():
    """출고 설정 목록 조회"""
    settings = load_erp_shipment_settings()
    return jsonify({'success': True, 'settings': settings})

@erp_beta_bp.route('/api/erp/shipment-settings', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_shipment_settings_save():
    """출고 설정 저장"""
    try:
        payload = request.get_json(silent=True) or {}
        current = load_erp_shipment_settings()
        for key in ('construction_time', 'drawing_manager', 'construction_workers', 'site_extra'):
            if key in payload and isinstance(payload[key], list):
                if key == 'construction_workers':
                    current[key] = normalize_erp_shipment_workers(payload[key])
                elif key == 'site_extra':
                    cleaned = []
                    for x in payload[key]:
                        if isinstance(x, dict):
                            text = str(x.get('text', '')).strip()
                        else:
                            text = str(x).strip()
                        if text:
                            cleaned.append(text)
                    current[key] = cleaned
                else:
                    current[key] = [str(x).strip() for x in payload[key] if str(x).strip()]
        if save_erp_shipment_settings(current):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '저장 실패'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@erp_beta_bp.route('/api/erp/shipment/update/<int:order_id>', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_shipment_update(order_id):
    """출고 대시보드 업데이트"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404
        if not order.is_erp_beta and order.status not in ('AS_RECEIVED', 'AS_COMPLETED'):
            return jsonify({'success': False, 'error': 'ERP Beta 또는 AS 주문만 수정할 수 있습니다.'}), 400

        payload = request.get_json(silent=True) or {}
        structured_data = dict(order.structured_data or {})

        if 'shipment' not in structured_data:
            structured_data['shipment'] = {}

        shipment = structured_data['shipment']

        if 'site_extra' in payload:
            site_extra = payload.get('site_extra')
            if isinstance(site_extra, list):
                normalized = []
                for x in site_extra:
                    if isinstance(x, dict):
                        text = (x.get('text') or '').strip()
                        color = (x.get('color') or 'black').strip() or 'black'
                        if text:
                            normalized.append({'text': text, 'color': color})
                    else:
                        t = str(x).strip()
                        if t:
                            normalized.append({'text': t, 'color': 'black'})
                shipment['site_extra'] = normalized
            else:
                shipment['site_extra'] = []
        if 'construction_time' in payload:
            shipment['construction_time'] = str(payload.get('construction_time', '')).strip()
        if 'drawing_manager' in payload:
            shipment['drawing_manager'] = str(payload.get('drawing_manager', '')).strip()
        if 'drawing_managers' in payload:
            dms = payload.get('drawing_managers')
            if isinstance(dms, list):
                shipment['drawing_managers'] = [str(x).strip() for x in dms if str(x).strip()]
            else:
                shipment['drawing_managers'] = []
        if 'construction_workers' in payload:
            workers = payload.get('construction_workers')
            if isinstance(workers, list):
                shipment['construction_workers'] = [str(x).strip() for x in workers]
            else:
                shipment['construction_workers'] = []

        structured_data['shipment'] = shipment
        order.structured_data = structured_data
        order.structured_updated_at = datetime.datetime.now()
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(order, 'structured_data')
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERP_SHIPMENT] 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@erp_beta_bp.route('/api/erp/measurement/update/<int:order_id>', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_erp_measurement_update(order_id):
    """실측 대시보드 업데이트"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
        if not order:
            return jsonify({'success': False, 'error': '주문을 찾을 수 없습니다.'}), 404
        
        if not order.is_erp_beta:
            return jsonify({'success': False, 'error': 'ERP Beta 주문만 수정할 수 있습니다.'}), 400
        
        payload = request.get_json(silent=True) or {}
        field = payload.get('field')
        value = payload.get('value', '').strip()
        
        if not field:
            return jsonify({'success': False, 'error': '필드명이 필요합니다.'}), 400
        
        structured_data = order.structured_data or {}
        
        if field == 'manager':
            if 'parties' not in structured_data:
                structured_data['parties'] = {}
            if 'manager' not in structured_data['parties']:
                structured_data['parties']['manager'] = {}
            structured_data['parties']['manager']['name'] = value
            order.manager_name = value
        
        elif field == 'address':
            if 'site' not in structured_data:
                structured_data['site'] = {}
            structured_data['site']['address_full'] = value
            parts = value.split(' ', 1)
            if len(parts) >= 2:
                structured_data['site']['address_main'] = parts[0]
                structured_data['site']['address_detail'] = parts[1]
            else:
                structured_data['site']['address_main'] = value
                structured_data['site']['address_detail'] = ''
            order.address = value
        
        elif field == 'phone':
            if 'parties' not in structured_data:
                structured_data['parties'] = {}
            if 'customer' not in structured_data['parties']:
                structured_data['parties']['customer'] = {}
            structured_data['parties']['customer']['phone'] = value
            order.phone = value
        
        else:
            return jsonify({'success': False, 'error': f'지원하지 않는 필드: {field}'}), 400
        
        order.structured_data = structured_data
        order.structured_updated_at = datetime.datetime.now()
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(order, 'structured_data')
        
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"[ERP_MEASUREMENT] 업데이트 오류: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@erp_beta_bp.route('/api/erp/measurement/route')
@login_required
def api_erp_measurement_route():
    """ERP Beta - 실측 동선 추천 (MVP)"""
    db = get_db()
    date_filter = request.args.get('date') or datetime.datetime.now().strftime('%Y-%m-%d')
    manager_filter = (request.args.get('manager') or '').strip()
    limit = int(request.args.get('limit', 20))
    limit = max(1, min(limit, 30))

    query = db.query(Order).filter(Order.status != 'DELETED')
    
    if date_filter:
        date_conditions = [Order.measurement_date == date_filter]
        query = query.filter(or_(*date_conditions))
    
    if manager_filter:
        query = query.filter(Order.manager_name.ilike(f'%{manager_filter}%'))

    all_orders = query.order_by(Order.measurement_time.asc().nullslast(), Order.id.asc()).limit(limit * 2).all()
    
    orders = []
    for order in all_orders:
        if date_filter:
            if order.is_erp_beta and order.structured_data:
                sd = order.structured_data
                erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if (erp_measurement_date and str(erp_measurement_date) == date_filter) or \
                   (order.measurement_date and str(order.measurement_date) == date_filter):
                    orders.append(order)
            else:
                if order.measurement_date and str(order.measurement_date) == date_filter:
                    orders.append(order)
        else:
            orders.append(order)
    
    orders = orders[:limit]

    converter = FOMSAddressConverter()
    points = []
    for o in orders:
        address_to_use = o.address
        customer_name = o.customer_name
        phone = o.phone
        
        if o.is_erp_beta and o.structured_data:
            sd = o.structured_data
            erp_address_full = (sd.get('site') or {}).get('address_full')
            erp_address_main = (sd.get('site') or {}).get('address_main')
            erp_address_detail = (sd.get('site') or {}).get('address_detail')
            
            if erp_address_full and erp_address_full.strip() and erp_address_full != '-':
                address_to_use = erp_address_full.strip()
            elif erp_address_main and erp_address_main.strip():
                if erp_address_detail and erp_address_detail.strip() and erp_address_detail != '-':
                    address_to_use = f"{erp_address_main.strip()} {erp_address_detail.strip()}"
                else:
                    address_to_use = erp_address_main.strip()
            
            erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
            if erp_customer_name:
                customer_name = erp_customer_name
            
            erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
            if erp_phone:
                phone = erp_phone
        
        lat, lng, status = converter.convert_address(address_to_use)
        if lat is None or lng is None:
            continue
        points.append({
            "id": o.id,
            "customer_name": customer_name,
            "phone": phone,
            "address": address_to_use,
            "measurement_time": o.measurement_time,
            "manager_name": o.manager_name,
            "status": o.status,
            "lat": float(lat),
            "lng": float(lng),
            "geo_status": status
        })

    if len(points) <= 1:
        return jsonify({
            "success": True,
            "date": date_filter,
            "manager": manager_filter,
            "total_points": len(points),
            "route": points,
            "total_distance_km": 0
        })

    def haversine_km(a, b):
        R = 6371.0
        lat1 = math.radians(a["lat"])
        lon1 = math.radians(a["lng"])
        lat2 = math.radians(b["lat"])
        lon2 = math.radians(b["lng"])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    remaining = points[:]
    route = [remaining.pop(0)]
    total_km = 0.0

    while remaining:
        last = route[-1]
        best_i = 0
        best_d = float("inf")
        for i, cand in enumerate(remaining):
            d = haversine_km(last, cand)
            if d < best_d:
                best_d = d
                best_i = i
        next_pt = remaining.pop(best_i)
        total_km += best_d
        route.append(next_pt)

    km_h = 0.0
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        d_h = haversine_km(a, b)
        km_h += d_h

    return jsonify({
        "success": True,
        "date": date_filter,
        "manager": manager_filter,
        "total_points": len(points),
        "route": route,
        "total_distance_km": round(km_h, 2)
    })

@erp_beta_bp.route('/erp/as')
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
    apply_erp_beta_display_fields_to_orders(rows)

    return render_template(
        'erp_as_dashboard.html',
        status_filter=status_filter,
        manager_filter=manager_filter,
        selected_date=selected_date,
        rows=rows
    )

@erp_beta_bp.route('/api/map_data')
@login_required
def api_map_data():
    """지도 표시용 주문 데이터 API"""
    try:
        date_filter = request.args.get('date')
        status_filter = request.args.get('status')
        limit = int(request.args.get('limit', 100))
        
        db = get_db()
        query = db.query(Order).filter(Order.status != 'DELETED')
        
        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )
        
        if status_filter and status_filter != 'ALL':
            query = query.filter(Order.status == status_filter)
        
        if date_filter:
            try:
                filter_date = datetime.datetime.strptime(date_filter, '%Y-%m-%d').date()
                date_start = filter_date - datetime.timedelta(days=30)
                date_end = filter_date + datetime.timedelta(days=30)
            except:
                date_start = None
                date_end = None
            
            date_conditions = [
                Order.measurement_date == date_filter,
                Order.received_date == date_filter,
                Order.scheduled_date == date_filter,
                Order.completion_date == date_filter,
                Order.as_received_date == date_filter,
                Order.as_completed_date == date_filter
            ]
            
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
        
        orders = query.order_by(Order.id.desc()).limit(limit * 5).all()
        
        if date_filter:
            filtered_orders = []
            for order in orders:
                should_include = False
                if order.is_erp_beta and order.structured_data:
                    sd = order.structured_data
                    erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                    if erp_measurement_date and str(erp_measurement_date) == date_filter:
                        should_include = True
                    elif order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True
                else:
                    if order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True
                
                if should_include:
                    filtered_orders.append(order)
            orders = filtered_orders[:limit]
        
        converter = FOMSAddressConverter()
        map_data = []
        for order in orders:
            customer_name = order.customer_name
            phone = order.phone
            address_to_use = order.address
            product = order.product
            
            if order.is_erp_beta and order.structured_data:
                sd = order.structured_data
                erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
                if erp_customer_name:
                    customer_name = erp_customer_name
                
                erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
                if erp_phone:
                    phone = erp_phone
                
                erp_address_full = (sd.get('site') or {}).get('address_full')
                erp_address_main = (sd.get('site') or {}).get('address_main')
                erp_address_detail = (sd.get('site') or {}).get('address_detail')
                
                if erp_address_full and erp_address_full.strip() and erp_address_full != '-':
                    address_to_use = erp_address_full.strip()
                elif erp_address_main and erp_address_main.strip():
                    if erp_address_detail and erp_address_detail.strip() and erp_address_detail != '-':
                        address_to_use = f"{erp_address_main.strip()} {erp_address_detail.strip()}"
                    else:
                        address_to_use = erp_address_main.strip()
                
                items = sd.get('items') or []
                if items and len(items) > 0:
                    first_item = items[0]
                    product_name = first_item.get('product_name') or first_item.get('name')
                    if product_name:
                        if len(items) > 1:
                            product = f"{product_name} 외 {len(items) - 1}개"
                        else:
                            product = product_name
            
            lat, lng, status = converter.convert_address(address_to_use)
            if lat is not None and lng is not None:
                map_data.append({
                    'id': order.id,
                    'customer_name': customer_name,
                    'phone': phone,
                    'address': address_to_use,
                    'product': product,
                    'status': order.status,
                    'received_date': order.received_date,
                    'latitude': lat,
                    'longitude': lng,
                    'conversion_status': status
                })
        
        return jsonify({
            'success': True,
            'data': map_data,
            'total_orders': len(orders),
            'converted_orders': len(map_data)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@erp_beta_bp.route('/api/generate_map')
@login_required
def api_generate_map():
    """지도 HTML 생성 API"""
    try:
        date_filter = request.args.get('date')
        status_filter = request.args.get('status')
        manager_filter = (request.args.get('manager') or '').strip()
        title = request.args.get('title', '주문 위치 지도')
        
        db = get_db()
        query = db.query(Order).filter(Order.status != 'DELETED')
        
        query = query.filter(
            Order.is_regional != True,
            ~Order.status.in_(['SELF_MEASUREMENT', 'SELF_MEASURED'])
        )
        
        if status_filter and status_filter != 'ALL':
            query = query.filter(Order.status == status_filter)
        
        if date_filter:
            try:
                filter_date = datetime.datetime.strptime(date_filter, '%Y-%m-%d').date()
                date_start = filter_date - datetime.timedelta(days=30)
                date_end = filter_date + datetime.timedelta(days=30)
            except:
                date_start = None
                date_end = None
            
            date_conditions = [
                Order.measurement_date == date_filter,
                Order.received_date == date_filter,
                Order.scheduled_date == date_filter,
                Order.completion_date == date_filter,
                Order.as_received_date == date_filter,
                Order.as_completed_date == date_filter
            ]
            
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
        
        orders = query.order_by(Order.id.desc()).limit(500).all()
        
        if date_filter:
            filtered_orders = []
            for order in orders:
                should_include = False
                if order.is_erp_beta and order.structured_data:
                    sd = order.structured_data
                    erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                    if erp_measurement_date and str(erp_measurement_date) == date_filter:
                        should_include = True
                    elif order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True
                else:
                    if order.measurement_date and str(order.measurement_date) == date_filter:
                        should_include = True
                
                if should_include:
                    filtered_orders.append(order)
            orders = filtered_orders[:100]
        
        converter = FOMSAddressConverter()
        map_data = []
        orders_list = []
        
        for order in orders:
            customer_name = order.customer_name
            phone = order.phone
            address_to_use = order.address
            product = order.product
            measurement_date = order.measurement_date
            scheduled_date = order.scheduled_date
            manager_name = order.manager_name or '-'
            
            if order.is_erp_beta and order.structured_data:
                sd = order.structured_data
                erp_customer_name = ((sd.get('parties') or {}).get('customer') or {}).get('name')
                if erp_customer_name:
                    customer_name = erp_customer_name
                erp_phone = ((sd.get('parties') or {}).get('customer') or {}).get('phone')
                if erp_phone:
                    phone = erp_phone
                
                erp_address_full = (sd.get('site') or {}).get('address_full')
                erp_address_main = (sd.get('site') or {}).get('address_main')
                erp_address_detail = (sd.get('site') or {}).get('address_detail')
                
                if erp_address_full and erp_address_full.strip() and erp_address_full != '-':
                    address_to_use = erp_address_full.strip()
                elif erp_address_main and erp_address_main.strip():
                    if erp_address_detail and erp_address_detail.strip() and erp_address_detail != '-':
                        address_to_use = f"{erp_address_main.strip()} {erp_address_detail.strip()}"
                    else:
                        address_to_use = erp_address_main.strip()
                
                items = sd.get('items') or []
                if items and len(items) > 0:
                    first_item = items[0]
                    product_name = first_item.get('product_name') or first_item.get('name')
                    if product_name:
                        if len(items) > 1:
                            product = f"{product_name} 외 {len(items) - 1}개"
                        else:
                            product = product_name
                
                erp_measurement_date = (((sd.get('schedule') or {}).get('measurement') or {}).get('date'))
                if erp_measurement_date:
                    measurement_date = erp_measurement_date
                
                erp_scheduled_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
                if erp_scheduled_date:
                    scheduled_date = erp_scheduled_date
                
                erp_manager_name = ((sd.get('parties') or {}).get('manager') or {}).get('name')
                if erp_manager_name:
                    manager_name = erp_manager_name

            if manager_filter:
                manager_name_str = str(manager_name or '')
                if manager_filter.lower() not in manager_name_str.lower():
                    continue
            
            lat, lng, status = converter.convert_address(address_to_use)
            
            def format_date(date_value):
                if date_value is None:
                    return None
                if isinstance(date_value, str):
                    return date_value
                if hasattr(date_value, 'strftime'):
                    return date_value.strftime('%Y-%m-%d')
                return str(date_value)
            
            order_list_item = {
                'id': order.id,
                'customer_name': customer_name,
                'phone': phone,
                'address': address_to_use,
                'product': product,
                'status': order.status,
                'received_date': format_date(order.received_date),
                'measurement_date': format_date(measurement_date),
                'scheduled_date': format_date(scheduled_date),
                'completion_date': format_date(order.completion_date),
                'manager_name': manager_name,
                'notes': order.notes or '-'
            }
            orders_list.append(order_list_item)
            
            if lat is not None and lng is not None:
                map_data.append({
                    'id': order.id,
                    'customer_name': customer_name,
                    'phone': phone,
                    'address': address_to_use,
                    'product': product,
                    'status': order.status,
                    'received_date': order.received_date,
                    'latitude': lat,
                    'longitude': lng
                })
        
        map_generator = FOMSMapGenerator()
        
        if map_data:
            folium_map = map_generator.create_map(map_data, title)
            if folium_map:
                map_html = folium_map._repr_html_()
            else:
                map_html = '<div class="error-message">지도를 생성할 수 없습니다.</div>'
            
            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': len(map_data),
                'orders': orders_list
            })
        
        empty_map = map_generator.create_empty_map(title)
        if empty_map:
            map_html = empty_map._repr_html_()
            return jsonify({
                'success': True,
                'map_html': map_html,
                'total_orders': 0,
                'orders': [],
                'message': f'{title}에 해당하는 주문이 없습니다.'
            })
        
        return jsonify({'success': False, 'error': '지도를 생성할 수 없습니다.'})
        
    except Exception as e:
        import traceback
        print(f"ERROR: generate_map 에러 발생: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500
