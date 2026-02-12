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
from erp_policy import (
    STAGE_NAME_TO_CODE, DEFAULT_OWNER_TEAM_BY_STAGE, STAGE_LABELS,
    get_quest_template_for_stage, create_quest_from_template,
    get_required_approval_teams_for_stage, recommend_owner_team,
    can_modify_domain, get_assignee_ids
)
from storage import get_storage
from business_calendar import business_days_until
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


erp_beta_bp = Blueprint('erp_beta', __name__)

# -------------------------------------------------------------------------
# ERP Beta 수정 권한: 관리자, 라홈팀(CS), 하우드팀(CS), 영업팀(SALES)만 수정 가능
# -------------------------------------------------------------------------
ERP_EDIT_ALLOWED_TEAMS = ('CS', 'SALES')


def can_edit_erp_beta(user):
    """ERP Beta 페이지/API 수정 권한: 관리자 또는 CS/영업팀 소속만 True"""
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
        if not can_edit_erp_beta(user):
            return jsonify({
                'success': False,
                'message': 'ERP Beta 수정 권한이 없습니다. (관리자, 라홈팀, 하우드팀, 영업팀만 수정 가능)'
            }), 403
        return f(*args, **kwargs)
    return wrapped


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


# [중복 제거됨] _erp_get_urgent_flag 함수는 Line 350에 정의되어 있습니다.

# [중복 제거됨] _erp_get_stage 함수는 Line 356에 정의되어 있습니다.

# [중복 제거됨] _erp_has_media 함수는 Line 367에 정의되어 있습니다.

# [중복 제거됨] _erp_alerts 함수는 Line 371에 정의되어 있습니다.


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
    
    # 현재 사용자 확인 (관리자 여부, ERP 수정 권한)
    is_admin = False
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    if current_user and current_user.role == 'ADMIN':
        is_admin = True
    can_edit_erp_beta_flag = can_edit_erp_beta(current_user)
    
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
        {'label': '시공', **step_stats['시공']},
        {'label': 'CS', **step_stats['CS']},
        {'label': '완료', **step_stats['완료']},
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
        can_edit_erp_beta=can_edit_erp_beta_flag,
    )


@erp_beta_bp.route('/erp/drawing-workbench')
@login_required
def erp_drawing_workbench_dashboard():
    """도면 작업실 대시보드: 도면 단계 협업 전용 화면(목록형)"""
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

        if status_filter and drawing_status != status_filter:
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

    rows.sort(key=lambda r: (
        0 if r.get('my_todo') else 1,
        0 if r.get('is_overdue') else 1,
        -int(r.get('id') or 0),
    ))

    return render_template(
        'erp_drawing_workbench_dashboard.html',
        rows=rows,
        filters={
            'q': q_raw,
            'status': status_filter,
            'mine': '1' if mine_only else '',
            'unread': '1' if unread_only else '',
            'due_today': '1' if due_today_only else '',
            'assignee': assignee_filter_raw,
        },
        can_edit_erp_beta=can_edit_erp_beta(current_user),
        erp_beta_enabled=True,
    )


@erp_beta_bp.route('/erp/drawing-workbench/<int:order_id>')
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
        return redirect(url_for('erp_beta.erp_drawing_workbench_dashboard'))

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

    can_cancel_transfer = False
    if current_user and current_user.role == 'ADMIN':
        can_cancel_transfer = True
    elif can_transfer:
        can_cancel_transfer = True
    else:
        last_transfer = next((h for h in reversed(history_raw) if isinstance(h, dict) and h.get('action') == 'TRANSFER'), None)
        if last_transfer:
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
        can_edit_erp_beta=can_edit_erp_beta(current_user),
        my_id=(current_user.id if current_user else 0),
        my_role=(current_user.role if current_user else ''),
        my_team=(current_user.team if current_user else ''),
        my_name=(current_user.name if current_user else ''),
        history_json=history_raw,
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

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_measurement_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        measurement_panel_dates=measurement_panel_dates,
        today_date=today_date,
        can_edit_erp_beta=can_edit_erp_beta(current_user),
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
    if not req_date:
        return redirect(url_for('erp_beta.erp_shipment_dashboard', date=today_date, manager=manager_filter or None))
    try:
        datetime.datetime.strptime(req_date, '%Y-%m-%d').date()
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

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_shipment_dashboard.html',
        selected_date=selected_date,
        manager_filter=manager_filter,
        rows=rows,
        construction_panel_dates=construction_panel_dates,
        remaining_panel_dates=remaining_panel_dates,
        today_date=today_date,
        can_edit_erp_beta=can_edit_erp_beta(current_user),
    )

@erp_beta_bp.route('/erp/shipment-settings')
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def erp_shipment_settings():
    """ERP 출고 설정 페이지 (시공시간/도면담당자/시공자/현장주소 추가 목록 - 제품설정처럼)"""
    settings = load_erp_shipment_settings()
    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template('erp_shipment_settings.html', settings=settings, can_edit_erp_beta=can_edit_erp_beta(current_user))

@erp_beta_bp.route('/api/erp/shipment-settings', methods=['GET'])
@login_required
def api_erp_shipment_settings_get():
    """출고 설정 목록 조회"""
    settings = load_erp_shipment_settings()
    return jsonify({'success': True, 'settings': settings})

@erp_beta_bp.route('/api/erp/shipment-settings', methods=['POST'])
@login_required
@erp_edit_required
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
@erp_edit_required
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
@erp_edit_required
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

    current_user = get_user_by_id(session.get('user_id')) if session.get('user_id') else None
    return render_template(
        'erp_as_dashboard.html',
        status_filter=status_filter,
        manager_filter=manager_filter,
        selected_date=selected_date,
        rows=rows,
        can_edit_erp_beta=can_edit_erp_beta(current_user),
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

@erp_beta_bp.route('/erp/api/users', methods=['GET'])
@login_required
def api_erp_users_list():
    """ERP 사용자 목록 반환 (팀 필터링 가능)"""
    team_filter = request.args.get('team')
    query = get_db().query(User).filter(User.is_active == True)
    
    if team_filter:
        query = query.filter(User.team == team_filter)
    
    users = query.all()
    return jsonify({
        'success': True,
        'users': [{'id': u.id, 'name': u.name, 'team': u.team} for u in users]
    })


@erp_beta_bp.route('/api/generate_map')
@login_required
def api_generate_map():
    """지도 HTML 생성 API"""
    try:
        date_filter = request.args.get('date')
        status_filter = request.args.get('status')
        manager_filter = (request.args.get('manager') or '').strip()
        search_query = (request.args.get('q') or request.args.get('search') or '').strip()
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
            
            # 검색어 필터: 아파트명, 동명, 건물명, 주소, 고객명, 제품 등 포함 시만 표시
            if search_query:
                search_lower = _normalize_for_search(search_query).lower()
                searchable_parts = [
                    address_to_use,
                    order.address,
                    customer_name,
                    product,
                    order.notes,
                    manager_name,
                ]
                if order.is_erp_beta and order.structured_data:
                    sd = order.structured_data
                    site = sd.get('site') or {}
                    searchable_parts.extend([
                        site.get('address_full'),
                        site.get('address_main'),
                        site.get('address_detail'),
                        site.get('address_note'),
                    ])
                searchable = _normalize_for_search(' '.join(
                    str(p).strip() for p in searchable_parts if p
                )).lower()
                if not searchable or search_lower not in searchable:
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
                'notes': order.notes or '-',
                'geocode_failed': lat is None or lng is None,
                'conversion_status': status if (lat is None or lng is None) else 'success'
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

# -------------------------------------------------------------------------
# Update Order Address API (for Map View)
# -------------------------------------------------------------------------

@erp_beta_bp.route('/api/orders/<int:order_id>/update_address', methods=['POST'])
@login_required
@erp_edit_required
def api_update_order_address(order_id):
    """주문 주소를 수정하고 재-지오코딩"""
    try:
        data = request.get_json()
        new_address = (data.get('address') or '').strip()
        
        if not new_address:
            return jsonify({'success': False, 'message': '주소를 입력해주세요.'}), 400
        
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        # Update address based on order type
        if order.is_erp_beta and order.structured_data:
            # ERP Beta order - update structured_data
            sd = order.structured_data or {}
            if 'site' not in sd:
                sd['site'] = {}
            sd['site']['address_full'] = new_address
            sd['site']['address_main'] = new_address
            order.structured_data = sd
            flag_modified(order, 'structured_data')
        else:
            # Legacy order - update address field
            order.address = new_address
        
        db.commit()
        
        # Try geocoding with new address
        converter = FOMSAddressConverter()
        lat, lng, status = converter.convert_address(new_address)
        
        return jsonify({
            'success': True,
            'latitude': lat,
            'longitude': lng,
            'address': new_address,
            'conversion_status': status,
            'geocode_failed': lat is None or lng is None
        })
        
    except Exception as e:
        import traceback
        print(f"ERROR: update_address 에러 발생: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

# -------------------------------------------------------------------------
# Quick Status Change API (Fast Access)
# -------------------------------------------------------------------------

@erp_beta_bp.route('/api/orders/quick-search', methods=['GET'])
@login_required
def api_order_quick_search():
    """빠른 상태 변경용 주문 검색 (고객명/주문번호)"""
    try:
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify({'success': False, 'message': '검색어를 입력해주세요.'}), 400

        db = get_db()
        q_norm = _normalize_for_search(q).lower()

        # ERP Beta 주문은 고객명이 structured_data에만 있는 케이스가 있어
        # DB LIKE 한 번으로는 누락될 수 있으므로 최근 주문을 가져와 Python 필터링.
        rows = (
            db.query(Order)
            .filter(Order.deleted_at.is_(None))
            .order_by(Order.id.desc())
            .limit(500)
            .all()
        )

        def _customer_display(o):
            sd = _ensure_dict(o.structured_data)
            return (
                (((sd.get('parties') or {}).get('customer') or {}).get('name'))
                or o.customer_name
                or ''
            )

        def _manager_display(o):
            sd = _ensure_dict(o.structured_data)
            return (((sd.get('parties') or {}).get('manager') or {}).get('name')) or o.manager_name or ''

        def _phone_display(o):
            sd = _ensure_dict(o.structured_data)
            return (
                (((sd.get('parties') or {}).get('customer') or {}).get('phone'))
                or o.phone
                or ''
            )

        def _address_display(o):
            sd = _ensure_dict(o.structured_data)
            site = (sd.get('site') or {})
            return (
                site.get('address_full')
                or site.get('address_main')
                or o.address
                or ''
            )

        matched = []
        for o in rows:
            customer_display = _customer_display(o)
            manager_display = _manager_display(o)
            phone_display = _phone_display(o)
            address_display = _address_display(o)
            hay_fields = [
                str(o.id),
                customer_display,
                o.customer_name or '',
                phone_display,
                manager_display,
                o.manager_name or '',
                address_display,
                o.product or '',
            ]
            hay_norm = ' '.join([_normalize_for_search(x).lower() for x in hay_fields if x])
            if q_norm in hay_norm:
                matched.append((o, customer_display, manager_display, phone_display, address_display))
                if len(matched) >= 20:
                    break

        items = [{
            'id': o.id,
            'customer_name': customer_display or o.customer_name,
            'status': o.status,
            'product': o.product,
            'manager': manager_display,
            'address': address_display or o.address,
            'phone': phone_display or o.phone,
        } for (o, customer_display, manager_display, phone_display, address_display) in matched]

        return jsonify({'success': True, 'orders': items})
    except Exception as e:
        import traceback
        print(f"Quick Search Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/quick-info', methods=['GET'])
@login_required
def api_order_quick_info(order_id):
    """빠른 상태 변경용 주문 정보 조회"""
    try:
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        manager_display = (((sd.get('parties') or {}).get('manager') or {}).get('name')) or order.manager_name
            
        return jsonify({
            'success': True,
            'order': {
                'id': order.id,
                'customer_name': order.customer_name,
                'status': order.status,
                'product': order.product,
                'manager': manager_display,
                'address': order.address
            }
        })
    except Exception as e:
        import traceback
        print(f"Quick Info Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/quick-status', methods=['POST'])
@login_required
@erp_edit_required
def api_order_quick_status_update(order_id):
    """빠른 상태 변경 처리"""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        new_status = (data.get('status') or '').strip()
        note = data.get('note') # 선택 사항 (로그용)
        
        if not new_status:
            return jsonify({'success': False, 'message': '변경할 상태가 필요합니다.'}), 400

        # 레거시 상태값은 ERP 단계 코드로 정규화
        legacy_to_stage = {
            'MEASURED': 'MEASURE',
            'REGIONAL_MEASURED': 'MEASURE',
            'AS_RECEIVED': 'AS',
            'AS_COMPLETED': 'CS',
            'SCHEDULED': 'CONSTRUCTION',
            'SHIPPED_PENDING': 'PRODUCTION',
        }
        new_status = legacy_to_stage.get(new_status, new_status)
            
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        old_status = order.status
        
        if old_status == new_status:
             return jsonify({'success': True, 'message': '변경된 내용이 없습니다.'})

        # order.status와 workflow.stage를 동일 코드로 동기화
        order.status = new_status
        
        # [Quest 동기화] structured_data 업데이트
        import datetime as dt_mod
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        from erp_policy import create_quest_from_template
        
        sd = _ensure_dict(order.structured_data)
        user = get_user_by_id(session.get('user_id'))
        user_name = user.name if user else 'Unknown'
        wf = sd.get('workflow') or {}
        old_stage = wf.get('stage')
        
        # workflow.stage 업데이트
        wf['stage'] = new_status
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user_name
        
        # history 추가
        hist = wf.get('history') or []
        hist.append({
            'stage': new_status,
            'updated_at': wf['stage_updated_at'],
            'updated_by': user_name,
            'note': note or f'빠른 상태 변경: {old_status} → {new_status}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        # quests 동기화
        quests = sd.get('quests') or []
        
        # 기존 Quest 중 old_status에 해당하는 것을 SKIPPED로 처리
        for q in quests:
            if isinstance(q, dict) and q.get('stage') in (old_status, old_stage) and q.get('status') == 'OPEN':
                q['status'] = 'SKIPPED'
                q['updated_at'] = dt_mod.datetime.now().isoformat()
                q['note'] = f'빠른 상태 변경으로 건너뜀'
        
        # 새 단계의 Quest 생성
        new_quest = create_quest_from_template(new_status, user_name, sd)
        if new_quest:
            quests.append(new_quest)
        
        sd['quests'] = quests
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, 'structured_data')
        
        # 로그 기록
        from models import SecurityLog
        
        log_msg = f"빠른 상태 변경: {old_status} → {new_status}"
        if note:
            log_msg += f" (메모: {note})"
        
        # 현재 사용자 ID 가져오기 (세션 등에서)
        user_id = session.get('user_id')
        
        db.add(SecurityLog(
            user_id=user_id,
            message=f"주문 #{order_id} {log_msg}"
        ))
        
        db.commit()
        
        return jsonify({'success': True, 'message': '상태가 변경되었습니다.'})
        
    except Exception as e:
        if db is not None:
            db.rollback()
        import traceback
        print(f"Quick Status Update Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@erp_beta_bp.route('/api/orders/<int:order_id>/transfer-drawing', methods=['POST'])
@login_required
def api_order_transfer_drawing(order_id):
    """도면 전달 처리 (단계 변경 없이 전달 정보만 기록)
    
    Blueprint V3 기준:
    - 도면 전달은 도면팀에서 고객/영업팀에게 도면 완성을 알리는 역할
    - 단계 이동은 퀘스트 시스템의 팀 승인을 통해서만 가능
    - 도면 전달 시 영업팀/고객에게 알림 전송 (추후 구현)
    """
    try:
        from datetime import datetime
        data = request.get_json() or {}
        note = data.get('note', '')
        is_retransfer = bool(data.get('is_retransfer'))
        replace_target_key = (data.get('replace_target_key') or '').strip()
        emergency_override = bool(data.get('emergency_override'))
        override_reason = (data.get('override_reason') or '').strip()
        
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        # structured_data 안전하게 로드
        s_data = {}
        if order.structured_data:
            if isinstance(order.structured_data, dict):
                s_data = dict(order.structured_data)
            elif isinstance(order.structured_data, str):
                try:
                    import json
                    s_data = json.loads(order.structured_data)
                except:
                    s_data = {}

        # 1. 권한 체크: 담당자 미지정이면 도면 전달 불가
        current_user = get_user_by_id(session.get('user_id'))
        user_id = session.get('user_id')
        draw_assignee_ids = get_assignee_ids(order, 'DRAWING_DOMAIN')
        if not draw_assignee_ids:
            return jsonify({'success': False, 'message': '도면 담당자가 지정되지 않아 전달할 수 없습니다. 먼저 담당자를 지정해주세요.'}), 400

        if not current_user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 401
        can_transfer = can_modify_domain(current_user, order, 'DRAWING_DOMAIN', emergency_override, override_reason)
        if not can_transfer:
            msg = '도면 전달 권한이 없습니다. (지정된 도면 담당자만 가능)'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        
        # 전달 정보 생성
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        current_user = get_user_by_id(session.get('user_id'))
        user_name = current_user.name if current_user else 'Unknown'
        user_id = session.get('user_id')
        
        # 프론트엔드에서 업로드된 파일의 key/filename 목록을 받아옴 (재전송 시 삭제 위해)
        # 예: [{'key': 'orders/123/attachments/foo.pdf', 'filename': 'foo.pdf'}, ...]
        raw_new_files = data.get('files', [])
        new_files = []
        if isinstance(raw_new_files, list):
            for f in raw_new_files:
                if not isinstance(f, dict):
                    continue
                key = (f.get('key') or '').strip()
                if not key:
                    continue
                filename = (f.get('filename') or key.rsplit('/', 1)[-1]).strip()
                new_files.append({
                    'key': key,
                    'filename': filename,
                    'view_url': f"/api/files/view/{key}",
                    'download_url': f"/api/files/download/{key}",
                })
        
        old_files = list(s_data.get('drawing_current_files', []) or [])
        updated_files = list(old_files)
        replaced_target_number = None

        # 재전송(수정본 전달)에서는 새 파일이 필수
        if is_retransfer and not new_files:
            return jsonify({'success': False, 'message': '수정본 재전송 시 도면 파일 업로드가 필요합니다.'}), 400

        if new_files:
            # replace_target_key가 있으면 해당 번호만 교체 (삭제 후 새 파일 삽입)
            if replace_target_key:
                target_index = -1
                for i, f in enumerate(old_files):
                    if ((f or {}).get('key') or '').strip() == replace_target_key:
                        target_index = i
                        break
                if target_index < 0:
                    return jsonify({'success': False, 'message': '교체 대상 도면을 찾을 수 없습니다. 목록을 새로고침 후 다시 시도해주세요.'}), 400

                replaced_target_number = target_index + 1
                target_item = old_files[target_index] if target_index < len(old_files) else {}
                target_key = (target_item.get('key') or '').strip()
                storage = get_storage()
                if target_key:
                    # 스토리지 파일 삭제
                    try:
                        storage.delete_file(target_key)
                    except Exception:
                        pass
                    # DB 첨부 레코드/썸네일 정리
                    rows = db.query(OrderAttachment).filter(
                        OrderAttachment.order_id == order_id,
                        OrderAttachment.storage_key == target_key
                    ).all()
                    for row in rows:
                        try:
                            if row.thumbnail_key:
                                storage.delete_file(row.thumbnail_key)
                        except Exception:
                            pass
                        db.delete(row)

                updated_files = list(old_files)
                updated_files.pop(target_index)
                # 선택한 번호 위치에 새 파일 삽입 (다중 업로드 시 연속 삽입)
                for offset, nf in enumerate(new_files):
                    updated_files.insert(target_index + offset, nf)
            else:
                # 여러 장인데 재전송이면 대상 지정 필수
                if is_retransfer and len(old_files) > 1:
                    return jsonify({'success': False, 'message': '수정본 재전송 시 교체할 도면 번호를 선택해주세요.'}), 400
                # 기본 정책: 선택 안 하면 새 번호로 추가
                updated_files = list(old_files) + list(new_files)

            s_data['drawing_current_files'] = updated_files
            # 전달 성공 시점에 첨부 카테고리를 drawing으로 강제 정렬
            # (업로드 단계에서 레거시/예외로 measurement 저장된 경우를 보정)
            new_keys = [((f or {}).get('key') or '').strip() for f in new_files]
            new_keys = [k for k in new_keys if k]
            if new_keys:
                db.query(OrderAttachment).filter(
                    OrderAttachment.order_id == order_id,
                    OrderAttachment.storage_key.in_(new_keys)
                ).update(
                    {OrderAttachment.category: 'drawing'},
                    synchronize_session=False
                )
        
        transfer_info = {
            'action': 'TRANSFER',
            'transferred_at': now_str,
            'by_user_id': user_id,
            'by_user_name': user_name,
            'note': note,
            'files_count': len(new_files),
            'files': new_files,
            'mode': 'REPLACE' if replace_target_key else 'APPEND',
            'replace_target_key': replace_target_key or None,
            'replace_target_number': replaced_target_number,
        }
        
        # 히스토리 배열에 추가
        if 'drawing_transfer_history' not in s_data:
            s_data['drawing_transfer_history'] = []
            
        # 리스트 복사 후 append (SQLAlchemy 감지 유도)
        history = list(s_data['drawing_transfer_history'])
        history.append(transfer_info)
        s_data['drawing_transfer_history'] = history
        
        # 최신 상태 업데이트
        s_data['drawing_status'] = 'TRANSFERRED'
        s_data['drawing_transferred'] = True # Legacy support
        s_data['last_drawing_transfer'] = transfer_info

        
        # DB에 반영 (새로운 dict 할당)
        order.structured_data = s_data
        
        # === 알림 생성 ===
        # 담당자 이름 가져오기
        manager_name = (((s_data.get('parties') or {}).get('manager') or {}).get('name') or '').strip()
        print(f"[DEBUG] Drawing Transfer - Manager Name: '{manager_name}'")
        
        customer_name = (((s_data.get('parties') or {}).get('customer') or {}).get('name') or '').strip()
        
        # 담당자에 따라 알림 대상 결정
        from models import Notification
        
        target_team = None
        target_manager_name = None
        notification_message = f"주문 #{order_id}"
        if customer_name:
            notification_message += f" ({customer_name})"
        notification_message += f" 도면이 준비되었습니다."
        if note:
            notification_message += f" 메모: {note}"
        
        if '라홈' in manager_name:
            # 라홈팀(CS)에 알림
            target_team = 'CS'
        elif '하우드' in manager_name:
            # 하우드팀에 알림
            target_team = 'HAUDD'
        else:
            # 해당 영업사원에게 알림 (영업팀)
            target_team = 'SALES'
            target_manager_name = manager_name if manager_name else None
        
        notification = Notification(
            order_id=order_id,
            notification_type='DRAWING_TRANSFERRED',
            target_team=target_team,
            target_manager_name=target_manager_name,
            title='도면 전달됨',
            message=notification_message,
            created_by_user_id=user_id,
            created_by_name=user_name,
            is_read=False
        )
        db.add(notification)
            
        # 로그 기록
        from models import SecurityLog
        db.add(SecurityLog(
            user_id=user_id,
            message=f"주문 #{order_id} 도면 전달 완료: {note}"
        ))
        
        db.commit()
        
        # 알림 대상 정보 반환
        target_info = f"라홈팀" if target_team == 'CS' else (
            f"하우드팀" if target_team == 'HAUDD' else (
                f"영업팀 - {target_manager_name}" if target_manager_name else "영업팀"
            )
        )
        
        return jsonify({
            'success': True, 
            'message': f'도면이 전달되었습니다. [{target_info}]에 알림이 전송되었습니다. (확정 대기 상태)',
            'info': '담당자가 수령 확인을 하면 다음 단계로 진행됩니다.'
        })
        
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[ERROR] Transfer Drawing: {e}")
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500

@erp_beta_bp.route('/api/orders/<int:order_id>/cancel-transfer', methods=['POST'])
@login_required
def api_order_cancel_transfer(order_id):
    """도면 전달 취소 (도면팀/관리자)"""
    db = None
    try:
        from datetime import datetime
        data = request.get_json(silent=True) or {}
        note = data.get('note', '')
        
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        s_data = dict(order.structured_data or {})
        
        # 권한 체크: 관리자 / 지정 도면담당 / 마지막 전달 실행자(되돌리기)만 허용
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 401

        can_cancel = False
        if current_user.role == 'ADMIN':
            can_cancel = True
        elif can_modify_domain(current_user, order, 'DRAWING_DOMAIN', False, None):
            can_cancel = True
        else:
            latest_transfer = None
            for h in reversed(list(s_data.get('drawing_transfer_history', []) or [])):
                if isinstance(h, dict) and h.get('action') == 'TRANSFER':
                    latest_transfer = h
                    break
            if latest_transfer:
                try:
                    can_cancel = int(latest_transfer.get('by_user_id')) == int(current_user.id)
                except Exception:
                    can_cancel = False

        if not can_cancel:
            return jsonify({'success': False, 'message': '권한이 없습니다. (관리자/지정 도면담당/마지막 전달 실행자만 가능)'}), 403

        if s_data.get('drawing_status') != 'TRANSFERRED':
            return jsonify({'success': False, 'message': '확정 대기(\'TRANSFERRED\') 상태에서만 취소할 수 있습니다.'}), 400

        # 전달 취소 시, 현재 전달본 파일과 첨부 레코드도 함께 삭제
        current_files = list(s_data.get('drawing_current_files', []) or [])
        current_keys = []
        for f in current_files:
            if isinstance(f, dict):
                k = (f.get('key') or '').strip()
                if k:
                    current_keys.append(k)

        deleted_files_count = 0
        if current_keys:
            storage = get_storage()

            # DB 레코드 기준 삭제(썸네일까지 정리)
            rows = db.query(OrderAttachment).filter(
                OrderAttachment.order_id == order_id,
                OrderAttachment.storage_key.in_(current_keys)
            ).all()
            deleted_row_keys = set()
            for row in rows:
                try:
                    if row.storage_key:
                        if storage.delete_file(row.storage_key):
                            deleted_files_count += 1
                        deleted_row_keys.add(row.storage_key)
                    if row.thumbnail_key:
                        storage.delete_file(row.thumbnail_key)
                except Exception:
                    pass
                db.delete(row)

            # DB에 없던 키도 스토리지에서 정리 시도
            for key in current_keys:
                if key in deleted_row_keys:
                    continue
                try:
                    if storage.delete_file(key):
                        deleted_files_count += 1
                except Exception:
                    pass
            
        # 상태 복귀
        s_data['drawing_status'] = 'PENDING'
        s_data['drawing_transferred'] = False
        s_data['drawing_current_files'] = []
        s_data['last_drawing_transfer'] = None
        
        # 히스토리 정리:
        # 취소 시 창구에 남는 "도면 전달" 찌꺼기를 제거하기 위해
        # 최신 TRANSFER 항목을 찾아 삭제한다.
        history = list(s_data.get('drawing_transfer_history', []))
        removed_transfer = False
        current_key_set = set(current_keys)
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if not isinstance(h, dict):
                continue
            if h.get('action') != 'TRANSFER':
                continue

            transfer_files = h.get('files') if isinstance(h.get('files'), list) else []
            transfer_keys = set()
            for tf in transfer_files:
                if isinstance(tf, dict):
                    k = (tf.get('key') or '').strip()
                    if k:
                        transfer_keys.add(k)

            # current_keys가 있으면 키가 겹치는 항목 우선 삭제, 없으면 최신 TRANSFER 삭제
            if (not current_key_set) or (transfer_keys & current_key_set):
                history.pop(idx)
                removed_transfer = True
                break

        # 키 매칭 실패 시에도 최신 TRANSFER 하나는 제거
        if (not removed_transfer) and history:
            for idx in range(len(history) - 1, -1, -1):
                h = history[idx]
                if isinstance(h, dict) and h.get('action') == 'TRANSFER':
                    history.pop(idx)
                    removed_transfer = True
                    break

        s_data['drawing_transfer_history'] = history
        
        order.structured_data = s_data
        from models import SecurityLog
        db.add(SecurityLog(
            user_id=session.get('user_id'),
            message=f"주문 #{order_id} 도면 전달 취소 (파일 {deleted_files_count}개 삭제, 히스토리 정리: {'Y' if removed_transfer else 'N'})"
        ))
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'도면 전달이 취소되었습니다. (작업중 상태로 복귀, 전달 파일 {deleted_files_count}개 삭제)'
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        import traceback
        print(f"Cancel Transfer Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@erp_beta_bp.route('/api/orders/<int:order_id>/drawing-gateway-upload', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_gateway_upload(order_id):
    """도면 창구(수정요청) 파일 업로드 - 히스토리 표시용 파일만 저장."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '파일이 없습니다.'}), 400
        file = request.files['file']
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '파일명이 없습니다.'}), 400

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        storage = get_storage()
        folder = f"orders/{order_id}/drawing_gateway/revisions"
        result = storage.upload_file(file, file.filename, folder)
        if not result.get('success'):
            return jsonify({'success': False, 'message': '파일 업로드 실패'}), 500

        key = result.get('key')
        filename = file.filename
        file_type = storage._get_file_type(filename) if hasattr(storage, '_get_file_type') else 'file'
        if file_type not in ('image', 'video'):
            file_type = 'file'

        return jsonify({
            'success': True,
            'file': {
                'key': key,
                'filename': filename,
                'file_type': file_type,
                'view_url': f"/api/files/view/{key}",
                'download_url': f"/api/files/download/{key}",
            }
        })
    except Exception as e:
        import traceback
        print(f"Drawing gateway upload error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/request-revision', methods=['POST'])
@login_required
@erp_edit_required
def api_order_request_revision(order_id):
    """도면 수정 요청 (영업/담당자)"""
    try:
        from datetime import datetime
        data = request.get_json() or {}
        note = data.get('note', '')
        files = data.get('files', []) if isinstance(data.get('files', []), list) else []
        target_drawing_key = (data.get('target_drawing_key') or '').strip()
        
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        s_data = dict(order.structured_data or {})
        current_files = list(s_data.get('drawing_current_files', []) or [])

        # 권한 체크: 주문 담당(영업 도메인 assignee) 또는 관리자만 가능
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401
        if not _can_modify_sales_domain(current_user, order, s_data, False, None):
            msg = '도면 수정 요청 권한이 없습니다. (지정된 주문 담당자만 가능)'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        target_drawing_number = None
        if current_files:
            if not target_drawing_key and len(current_files) > 1:
                return jsonify({'success': False, 'message': '수정 요청할 도면 번호를 선택해주세요.'}), 400
            if target_drawing_key:
                for idx, f in enumerate(current_files):
                    if ((f or {}).get('key') or '').strip() == target_drawing_key:
                        target_drawing_number = idx + 1
                        break
                if target_drawing_number is None:
                    return jsonify({'success': False, 'message': '선택한 수정 대상 도면을 찾을 수 없습니다.'}), 400
            elif len(current_files) == 1:
                only_key = ((current_files[0] or {}).get('key') or '').strip()
                if only_key:
                    target_drawing_key = only_key
                    target_drawing_number = 1
        
        # 상태 체크: TRANSFERRED (확정대기) 상태여야 함
        if s_data.get('drawing_status') not in ['TRANSFERRED', 'CONFIRMED']: 
             # CONFIRMED 상태에서도 수정 요청 허용할지? 보통은 확정 후 제작 들어가면 안됨.
             # 일단 TRANSFERRED 상태만 허용
             return jsonify({'success': False, 'message': '도면 전달(확정 대기) 상태에서만 수정 요청 가능합니다.'}), 400
             
        # 상태 변경 -> RETURNED
        s_data['drawing_status'] = 'RETURNED'
        
        # 히스토리
        history = list(s_data.get('drawing_transfer_history', []))
        history.append({
            'action': 'REQUEST_REVISION',
            'by_user_id': session.get('user_id'),
            'by_user_name': current_user.name,
            'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': note,
            'files': files,
            'files_count': len(files),
            'target_drawing_key': target_drawing_key or None,
            'target_drawing_number': target_drawing_number,
        })
        s_data['drawing_transfer_history'] = history
        
        order.structured_data = s_data
        
        # 알림 전송 (도면팀에게)
        from models import Notification
        msg = f"주문 #{order_id} 도면 수정 요청이 접수되었습니다."
        if target_drawing_number:
            msg += f" 대상: {target_drawing_number}번 도면."
        msg += f" 메모: {note}"
        if files:
            msg += f" (첨부 {len(files)}건)"
        db.add(Notification(
            order_id=order_id,
            notification_type='DRAWING_REVISION',
            target_team='DRAWING', 
            title='도면 수정 요청',
            message=msg,
            created_by_user_id=session.get('user_id'),
            created_by_name=current_user.name
        ))
        from models import SecurityLog
        db.add(SecurityLog(user_id=session.get('user_id'), message=f"주문 #{order_id} 도면 수정 요청"))
        db.commit()
        
        return jsonify({'success': True, 'message': '도면 수정 요청이 전송되었습니다.'})
    except Exception as e:
        db.rollback()
        import traceback
        print(f"Request Revision Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/request-revision-check', methods=['POST'])
@login_required
def api_order_request_revision_check(order_id):
    """도면 수정요청 반영 체크 토글 (요청사항 탭 체크리스트 저장)"""
    db = None
    try:
        data = request.get_json(silent=True) or {}
        request_at = str(data.get('request_at') or '').strip()
        by_user_id_raw = data.get('by_user_id')
        checked = bool(data.get('checked'))

        if not request_at:
            return jsonify({'success': False, 'message': '요청 식별값(request_at)이 필요합니다.'}), 400

        by_user_id = None
        try:
            if by_user_id_raw not in (None, ''):
                by_user_id = int(by_user_id_raw)
        except (TypeError, ValueError):
            by_user_id = None

        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404

        s_data = _ensure_dict(order.structured_data)
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401

        can_toggle = (
            current_user.role == 'ADMIN'
            or can_modify_domain(current_user, order, 'DRAWING_DOMAIN', False, None)
            or _can_modify_sales_domain(current_user, order, s_data, False, None)
        )
        if not can_toggle:
            return jsonify({'success': False, 'message': '권한이 없습니다. (지정 담당자 또는 관리자만 가능)'}), 403

        history = list(s_data.get('drawing_transfer_history', []) or [])
        if not history:
            return jsonify({'success': False, 'message': '도면 창구 이력이 없습니다.'}), 404

        matched_idx = -1
        for i in range(len(history) - 1, -1, -1):
            h = history[i]
            if not isinstance(h, dict):
                continue
            if (h.get('action') or '') != 'REQUEST_REVISION':
                continue
            at_val = str(h.get('at') or h.get('transferred_at') or '').strip()
            if at_val != request_at:
                continue
            if by_user_id is not None:
                try:
                    h_uid = int(h.get('by_user_id'))
                except (TypeError, ValueError):
                    h_uid = None
                if h_uid != by_user_id:
                    continue
            matched_idx = i
            break

        if matched_idx < 0:
            return jsonify({'success': False, 'message': '해당 수정 요청을 찾을 수 없습니다.'}), 404

        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        target = dict(history[matched_idx] or {})
        target['review_check'] = {
            'checked': checked,
            'checked_at': now_str if checked else None,
            'checked_by_user_id': session.get('user_id') if checked else None,
            'checked_by_name': (current_user.name if current_user else '') if checked else None,
        }
        history[matched_idx] = target
        s_data['drawing_transfer_history'] = history

        import copy
        order.structured_data = copy.deepcopy(s_data)
        flag_modified(order, 'structured_data')

        from models import SecurityLog
        db.add(SecurityLog(
            user_id=session.get('user_id'),
            message=f"주문 #{order_id} 도면 수정요청 반영 체크 {'완료' if checked else '해제'}"
        ))
        db.commit()

        return jsonify({
            'success': True,
            'message': '요청 반영 체크가 저장되었습니다.' if checked else '요청 반영 체크가 해제되었습니다.'
        })
    except Exception as e:
        if db is not None:
            db.rollback()
        import traceback
        print(f"Request Revision Check Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/assign-draftsman', methods=['POST'])
@login_required
def api_order_assign_draftsman(order_id):
    """도면 담당자 지정 (다수 가능)"""
    try:
        from datetime import datetime
        data = request.get_json() or {}
        user_ids = data.get('user_ids', []) # List of user IDs
        emergency_override = data.get('emergency_override', False)
        override_reason = data.get('override_reason', '').strip()
        
        if not user_ids:
            return jsonify({'success': False, 'message': '담당자를 선택해주세요.'}), 400
            
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        # 권한 검사 (도면 담당자 지정은 DRAWING_DOMAIN)
        user_id = session.get('user_id')
        current_user = get_user_by_id(user_id)
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401
        
        # 권한 정책:
        # - ADMIN: 허용
        # - 도면팀(DRAWING): 허용 (실무에서 담당자 지정 필요)
        # - 그 외: 기존 엄격 담당제(can_modify_domain) 따름
        team_code = (current_user.team or '').strip()
        can_assign_drawing_assignee = (
            current_user.role == 'ADMIN'
            or team_code == 'DRAWING'
            or can_modify_domain(current_user, order, 'DRAWING_DOMAIN', emergency_override, override_reason)
        )
        if not can_assign_drawing_assignee:
            msg = '도면 담당자 지정 권한이 없습니다. (관리자/도면팀/지정 도면담당자만 가능)'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403
            
        # 도면 담당자는 도면팀(DRAWING) 소속만 지정 가능
        assigned_users = db.query(User).filter(User.id.in_(user_ids), User.is_active == True).all()
        non_drawing = [u for u in assigned_users if (u.team or '').strip() != 'DRAWING']
        if non_drawing:
            names = ', '.join([u.name for u in non_drawing])
            return jsonify({
                'success': False,
                'message': f'도면 담당자는 도면팀 소속만 지정할 수 있습니다. (도면팀이 아닌 사용자: {names})'
            }), 400
        if len(assigned_users) != len(user_ids):
            return jsonify({'success': False, 'message': '일부 사용자를 찾을 수 없거나 비활성 계정입니다.'}), 400
        
        assignee_list = [{'id': u.id, 'name': u.name, 'team': u.team} for u in assigned_users]
        
        # Save to structured_data
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        
        s_data = _ensure_dict(order.structured_data)
        
        # 기존 담당자 저장 (before)
        old_assignees = s_data.get('drawing_assignees', [])
        old_names = [a.get('name', '') for a in old_assignees if isinstance(a, dict)]
        old_ids = ((s_data.get('assignments') or {}).get('drawing_assignee_user_ids') or [])
        
        # 표준 키 업데이트
        if 'assignments' not in s_data:
            s_data['assignments'] = {}
        s_data['assignments']['drawing_assignee_user_ids'] = user_ids
        
        # 레거시 호환
        s_data['drawing_assignees'] = assignee_list
        
        # Sync to Shipment's drawing_managers (List of names)
        shipment = s_data.get('shipment') or {}
        shipment['drawing_managers'] = [u.name for u in assigned_users]
        s_data['shipment'] = shipment
        
        # Log
        wf = s_data.get('workflow') or {}
        hist = wf.get('history') or []
        names = ", ".join([u.name for u in assigned_users])
        hist.append({
            'stage': wf.get('stage', 'DRAWING'),
            'updated_at': datetime.now().isoformat(),
            'updated_by': current_user.name if current_user else 'Unknown',
            'note': f'도면 담당자 지정: {names}'
        })
        wf['history'] = hist
        s_data['workflow'] = wf
        
        order.structured_data = copy.deepcopy(s_data)
        flag_modified(order, "structured_data")
        
        # OrderEvent: 도면 담당자 지정
        event_payload = {
            'domain': 'DRAWING_DOMAIN',
            'action': 'DRAWING_ASSIGNEE_SET',
            'target': 'assignments.drawing_assignee_user_ids',
            'before': ', '.join(old_names) if old_names else 'None',
            'after': names,
            'before_ids': old_ids,
            'after_ids': user_ids,
            'assignee_names': [u.name for u in assigned_users],
            'assignee_user_ids': user_ids,
            'change_method': 'API',
            'source_screen': 'erp_drawing_dashboard',
            'reason': '도면 담당자 지정',
            'is_override': emergency_override,
            'override_reason': override_reason if emergency_override else None,
        }
        drawing_event = OrderEvent(
            order_id=order_id,
            event_type='DRAWING_ASSIGNEE_SET',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(drawing_event)
        db.commit()
        
        return jsonify({'success': True, 'message': f'도면 담당자가 지정되었습니다: {names}'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/confirm-drawing-receipt', methods=['POST'])
@login_required
@erp_edit_required
def api_order_confirm_drawing_receipt(order_id):
    """도면 수령 확인 (영업/담당자) -> 다음 단계(고객컨펌 등)로 자동 이동"""
    db = None
    try:
        from datetime import datetime
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        
        # 프론트에서 JSON body 없이 POST해도 예외 없이 처리
        data = request.get_json(silent=True) or {}
        emergency_override = data.get('emergency_override', False)
        override_reason = data.get('override_reason', '').strip()
        
        db = get_db()
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        s_data = _ensure_dict(order.structured_data)
        
        # 권한 체크: 영업 도메인 엄격 담당제
        current_user = get_user_by_id(session.get('user_id'))
        if not current_user:
            return jsonify({'success': False, 'message': '사용자를 찾을 수 없습니다.'}), 401
        
        can_confirm_receipt = can_modify_domain(
            current_user, order, 'SALES_DOMAIN', emergency_override, override_reason
        )

        # SALES_DOMAIN 호환 fallback:
        # assignments.sales_assignee_user_ids가 비어있는 레거시 주문은
        # 주문 담당자명(structured_data/order 컬럼/current_quest.owner_person) 일치 시 허용.
        if not can_confirm_receipt:
            sales_assignee_ids = get_assignee_ids(order, 'SALES_DOMAIN')
            if not sales_assignee_ids:
                manager_names = set()
                parties = (s_data.get('parties') or {}) if isinstance(s_data, dict) else {}
                manager_name_sd = ((parties.get('manager') or {}).get('name') or '').strip()
                if manager_name_sd:
                    manager_names.add(manager_name_sd.lower())

                manager_name_col = (order.manager_name or '').strip()
                if manager_name_col:
                    manager_names.add(manager_name_col.lower())

                wf_tmp = (s_data.get('workflow') or {}) if isinstance(s_data, dict) else {}
                current_quest = (wf_tmp.get('current_quest') or {})
                owner_person = (current_quest.get('owner_person') or '').strip()
                if owner_person:
                    manager_names.add(owner_person.lower())

                user_name = (current_user.name or '').strip().lower()
                user_username = (current_user.username or '').strip().lower()
                if user_name in manager_names or user_username in manager_names:
                    can_confirm_receipt = True

        if not can_confirm_receipt:
            msg = '도면 수령 확인은 지정된 영업 담당자만 가능합니다.'
            if current_user.role == 'MANAGER':
                msg += ' (긴급 오버라이드가 필요합니다.)'
            return jsonify({'success': False, 'message': msg}), 403

        # Update Status
        old_drawing_status = s_data.get('drawing_status', 'UNKNOWN')
        s_data['drawing_status'] = 'CONFIRMED'
        s_data['drawing_confirmed_at'] = datetime.now().isoformat()
        s_data['drawing_confirmed_by'] = current_user.name
        
        # Advance Stage Logic (Move to CONFIRM or whatever is next)
        # Assuming next stage is 'CONFIRM' (Customer Confirm)
        next_stage = 'CONFIRM' 
        
        wf = s_data.get('workflow') or {}
        old_stage = wf.get('stage', 'DRAWING')
        wf['stage'] = next_stage
        wf['stage_updated_at'] = datetime.now().isoformat()
        wf['stage_updated_by'] = current_user.name
        
        hist = wf.get('history') or []
        hist.append({
            'stage': next_stage,
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '도면 수령 확인 및 단계 이동'
        })
        wf['history'] = hist
        s_data['workflow'] = wf
        
        order.structured_data = copy.deepcopy(s_data)
        flag_modified(order, "structured_data")
        order.status = next_stage # Sync with model status if applicable
        
        # OrderEvent: 도면 수령 확인
        event_payload = {
            'domain': 'SALES_DOMAIN',
            'action': 'DRAWING_STATUS_CHANGED',
            'target': 'drawing_status',
            'before': old_drawing_status,
            'after': 'CONFIRMED',
            'change_method': 'API',
            'source_screen': 'erp_drawing_dashboard',
            'reason': '도면 수령 확인',
            'is_override': emergency_override,
            'override_reason': override_reason if emergency_override else None,
        }
        drawing_confirm_event = OrderEvent(
            order_id=order_id,
            event_type='DRAWING_STATUS_CHANGED',
            payload=event_payload,
            created_by_user_id=current_user.id
        )
        db.add(drawing_confirm_event)
        
        # Log
        from models import SecurityLog
        db.add(SecurityLog(user_id=current_user.id, message=f"주문 #{order_id} 도면 확정 및 단계 이동 ({old_stage} -> {next_stage})"))
        
        db.commit()
        
        return jsonify({'success': True, 'message': '도면이 확정되었습니다. 다음 단계로 이동합니다.', 'new_stage': next_stage})
        
    except Exception as e:
        if db is not None:
            db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/erp/production/dashboard')
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
            'current_quest': None, # Quest logic simplified for production dashboard
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
        can_edit_erp_beta=can_edit_erp_beta(current_user),
    )

@erp_beta_bp.route('/api/orders/<int:order_id>/production/start', methods=['POST'])
@login_required
@erp_edit_required
def api_production_start(order_id):
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        # Update Stage
        import datetime as dt_mod
        wf['stage'] = 'PRODUCTION'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        # Add History
        hist = wf.get('history') or []
        hist.append({
            'stage': 'PRODUCTION',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '제작 시작'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        # Update DB
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        order.structured_data = copy.deepcopy(sd) # Force update
        flag_modified(order, "structured_data")
        order.status = 'PRODUCTION' # Legacy Sync
        
        # Log
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 시작 (PRODUCTION)"))
        db.commit()
        
        return jsonify({'success': True, 'message': '제작이 시작되었습니다.', 'new_status': 'PRODUCTION'})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@erp_beta_bp.route('/api/orders/<int:order_id>/production/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_production_complete(order_id):
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
            
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        # Update Stage -> CONSTRUCTION (시공 대기 / 출고 대기)
        import datetime as dt_mod
        wf['stage'] = 'CONSTRUCTION'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        # Add History
        hist = wf.get('history') or []
        hist.append({
            'stage': 'CONSTRUCTION',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '제작 완료 (시공/출고 대기)'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        # Update DB
        import copy
        from sqlalchemy.orm.attributes import flag_modified
        order.structured_data = copy.deepcopy(sd) # Force update
        flag_modified(order, "structured_data")
        order.status = 'CONSTRUCTION' # Legacy Sync
        
        # OrderEvent: 생산 완료
        event_payload = {
            'domain': 'PRODUCTION_DOMAIN',
            'action': 'PRODUCTION_COMPLETED',
            'target': 'workflow.stage',
            'before': 'PRODUCTION',
            'after': 'CONSTRUCTION',
            'change_method': 'API',
            'source_screen': 'erp_production_dashboard',
            'reason': '제작 완료 (시공 대기)'
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='PRODUCTION_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)
        
        # Log
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 제작 완료 (CONSTRUCTION)"))
        db.commit()
        
        return jsonify({'success': True, 'message': '제작이 완료되었습니다. (시공 대기 상태로 변경)', 'new_status': 'CONSTRUCTION'})
        
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/erp/construction/dashboard')
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
        can_edit_erp_beta=can_edit_erp_beta(current_user),
    )

@erp_beta_bp.route('/api/orders/<int:order_id>/construction/start', methods=['POST'])
@login_required
@erp_edit_required
def api_construction_start(order_id):
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order: return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        # Log only, stay in CONSTRUCTION (but marked as started via log)
        hist = wf.get('history') or []
        hist.append({
            'stage': 'CONSTRUCTION',
            'updated_at': dt_mod.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': '시공 시작'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        db.commit()
        
        # Log
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 시작"))
        db.commit()
        
        return jsonify({'success': True, 'message': '시공이 시작되었습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@erp_beta_bp.route('/api/orders/<int:order_id>/construction/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_construction_complete(order_id):
    """
    시공 완료 처리
    원본 요구사항: 시공(G) 완료 후 → CS(H) 단계로 이동
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order: return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        # Update Stage -> CS (원본 요구사항: 시공 후 CS 단계)
        wf['stage'] = 'CS'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        hist = wf.get('history') or []
        hist.append({
            'stage': 'CS',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': '시공 완료 → CS 단계 진입'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'CS'  # 원본 요구사항 기반: 시공 후 CS
        
        # OrderEvent: 시공 완료
        event_payload = {
            'domain': 'CONSTRUCTION_DOMAIN',
            'action': 'CONSTRUCTION_COMPLETED',
            'target': 'workflow.stage',
            'before': 'CONSTRUCTION',
            'after': 'CS',
            'change_method': 'API',
            'source_screen': 'erp_construction_dashboard',
            'reason': '시공 완료 → CS 단계 진입'
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='CONSTRUCTION_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)
        
        # Log
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 완료 → CS 단계 진입"))
        db.commit()
        
        return jsonify({'success': True, 'message': '시공이 완료되었습니다. CS 단계로 이동합니다.', 'new_status': 'CS'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# =============================================================================
# CS(H) 단계 관련 API - 원본 요구사항 기반 추가
# =============================================================================

@erp_beta_bp.route('/api/orders/<int:order_id>/cs/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_cs_complete(order_id):
    """
    CS 단계 완료 처리
    원본 요구사항: CS(H) 완료 후 → COMPLETED(최종 완료) 단계로 이동
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        wf['stage'] = 'COMPLETED'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        hist = wf.get('history') or []
        hist.append({
            'stage': 'COMPLETED',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': 'CS 완료 → 최종 완료'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'COMPLETED'
        
        # OrderEvent: CS 완료
        event_payload = {
            'domain': 'CS_DOMAIN',
            'action': 'CS_COMPLETED',
            'target': 'workflow.stage',
            'before': 'CS',
            'after': 'COMPLETED',
            'change_method': 'API',
            'source_screen': 'erp_cs_dashboard',
            'reason': 'CS 완료 → 최종 완료'
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='CS_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} CS 완료 → 최종 완료"))
        db.commit()
        
        return jsonify({'success': True, 'message': 'CS가 완료되었습니다.', 'new_status': 'COMPLETED'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/as/start', methods=['POST'])
@login_required
@erp_edit_required
def api_as_start(order_id):
    """AS 시작 (CS 단계에서 AS가 필요한 경우)"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        as_reason = data.get('reason', '')
        as_description = data.get('description', '')
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        as_info = sd.get('as_info') or []
        as_entry = {
            'id': len(as_info) + 1,
            'started_at': dt_mod.datetime.now().isoformat(),
            'started_by': user.name if user else 'Unknown',
            'reason': as_reason,
            'description': as_description,
            'status': 'OPEN',
            'visit_date': None,
            'completed_at': None
        }
        as_info.append(as_entry)
        sd['as_info'] = as_info
        
        wf['stage'] = 'AS'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        hist = wf.get('history') or []
        hist.append({
            'stage': 'AS',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': f'AS 시작: {as_reason}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'AS'
        
        # OrderEvent: AS 시작
        event_payload = {
            'domain': 'AS_DOMAIN',
            'action': 'AS_STARTED',
            'target': 'workflow.stage',
            'before': 'CS',
            'after': 'AS',
            'change_method': 'API',
            'source_screen': 'erp_cs_dashboard',
            'reason': f'AS 시작: {as_reason}',
            'as_id': as_entry['id'],
            'as_description': as_description
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='AS_STARTED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 시작: {as_reason}"))
        db.commit()
        
        return jsonify({'success': True, 'message': 'AS가 시작되었습니다.', 'new_status': 'AS', 'as_id': as_entry['id']})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/as/complete', methods=['POST'])
@login_required
@erp_edit_required
def api_as_complete(order_id):
    """AS 완료 → CS 복귀"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        as_id = data.get('as_id')
        completion_note = data.get('note', '')
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        as_info = sd.get('as_info') or []
        for entry in as_info:
            if isinstance(entry, dict) and (entry.get('id') == as_id or as_id is None):
                if entry.get('status') == 'OPEN':
                    entry['status'] = 'COMPLETED'
                    entry['completed_at'] = dt_mod.datetime.now().isoformat()
                    entry['completed_by'] = user.name if user else 'Unknown'
                    entry['completion_note'] = completion_note
                    break
        sd['as_info'] = as_info
        
        wf['stage'] = 'CS'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        hist = wf.get('history') or []
        hist.append({
            'stage': 'CS',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': f'AS 완료 → CS 복귀'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'CS'
        
        # OrderEvent: AS 완료
        event_payload = {
            'domain': 'AS_DOMAIN',
            'action': 'AS_COMPLETED',
            'target': 'workflow.stage',
            'before': 'AS',
            'after': 'CS',
            'change_method': 'API',
            'source_screen': 'erp_as_dashboard',
            'reason': 'AS 완료 → CS 복귀',
            'as_id': as_id,
            'completion_note': completion_note
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type='AS_COMPLETED',
            payload=event_payload,
            created_by_user_id=user_id
        )
        db.add(order_event)
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 완료 → CS 복귀"))
        db.commit()
        
        return jsonify({'success': True, 'message': 'AS가 완료되었습니다.', 'new_status': 'CS'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/as/schedule', methods=['POST'])
@login_required
@erp_edit_required
def api_as_schedule(order_id):
    """AS 방문일 확정"""
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        as_id = data.get('as_id')
        visit_date = data.get('visit_date')
        visit_time = data.get('visit_time', '')
        
        if not visit_date:
            return jsonify({'success': False, 'message': '방문일을 입력해주세요.'}), 400
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        
        as_info = sd.get('as_info') or []
        for entry in as_info:
            if isinstance(entry, dict) and (entry.get('id') == as_id or as_id is None):
                if entry.get('status') == 'OPEN':
                    entry['visit_date'] = visit_date
                    entry['visit_time'] = visit_time
                    entry['scheduled_by'] = user.name if user else 'Unknown'
                    entry['scheduled_at'] = dt_mod.datetime.now().isoformat()
                    break
        sd['as_info'] = as_info
        
        schedule = sd.get('schedule') or {}
        construction = schedule.get('construction') or {}
        construction['date'] = visit_date
        construction['time'] = visit_time
        construction['type'] = 'AS'
        schedule['construction'] = construction
        sd['schedule'] = schedule
        
        wf = sd.get('workflow') or {}
        hist = wf.get('history') or []
        hist.append({
            'stage': 'AS',
            'updated_at': dt_mod.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': f'AS 방문일 확정: {visit_date}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} AS 방문일 확정: {visit_date}"))
        db.commit()
        
        return jsonify({'success': True, 'message': f'AS 방문일이 {visit_date}로 확정되었습니다.', 'visit_date': visit_date})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# =============================================================================
# 시공 불가 / 도면 피드백 API - Blueprint V3 기준
# =============================================================================

@erp_beta_bp.route('/api/orders/<int:order_id>/construction/fail', methods=['POST'])
@login_required
@erp_edit_required
def api_construction_fail(order_id):
    """
    시공 불가 처리
    Blueprint V3: 시공 불가 시 → 시공 철수 → 원인별 재작업 단계로 이동
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        reason = data.get('reason', 'site_issue')  # drawing_error, measurement_error, product_defect, site_issue
        detail = data.get('detail', '')
        reschedule_date = data.get('reschedule_date')
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        wf = sd.get('workflow') or {}
        
        # 시공 실패 이력 저장
        fail_info = sd.get('construction_fail_history') or []
        fail_entry = {
            'id': len(fail_info) + 1,
            'failed_at': dt_mod.datetime.now().isoformat(),
            'failed_by': user.name if user else 'Unknown',
            'reason': reason,
            'detail': detail,
            'reschedule_date': reschedule_date,
            'previous_stage': 'CONSTRUCTION'
        }
        fail_info.append(fail_entry)
        sd['construction_fail_history'] = fail_info
        
        # 원인별 재작업 단계 결정
        reason_stage_map = {
            'drawing_error': 'DRAWING',      # 도면 오류 → 도면 단계로
            'measurement_error': 'MEASURE',  # 실측 오류 → 실측 단계로
            'product_defect': 'PRODUCTION',  # 제품 불량 → 생산 단계로
            'site_issue': 'CONSTRUCTION'     # 현장 문제 → 시공 단계 유지 (재일정)
        }
        new_stage = reason_stage_map.get(reason, 'CONSTRUCTION')
        
        wf['stage'] = new_stage
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        wf['rework_reason'] = reason
        
        hist = wf.get('history') or []
        reason_labels = {
            'drawing_error': '도면 오류',
            'measurement_error': '실측 오류',
            'product_defect': '제품 불량',
            'site_issue': '현장 문제'
        }
        hist.append({
            'stage': new_stage,
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': f'시공 불가 → {reason_labels.get(reason, reason)}: {detail}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        # 재시공 일정 설정
        if reschedule_date:
            schedule = sd.get('schedule') or {}
            construction = schedule.get('construction') or {}
            construction['date'] = reschedule_date
            construction['rescheduled'] = True
            construction['reschedule_reason'] = reason
            schedule['construction'] = construction
            sd['schedule'] = schedule
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = new_stage
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 불가: {reason_labels.get(reason, reason)}"))
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': f'시공 불가로 처리되었습니다. {reason_labels.get(reason, reason)}로 인해 {new_stage} 단계로 이동합니다.',
            'new_status': new_stage,
            'reason': reason
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/drawing/request-revision', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_request_revision(order_id):
    """
    도면 수정 요청 (고객 컨펌 또는 생산 단계에서)
    Blueprint V3: 수정 필요 시 → 도면팀 전달 → 수정 → 재전달
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        feedback = data.get('feedback', '')
        requested_by = data.get('requested_by', 'customer')  # customer, production
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        
        # 도면 수정 이력 저장
        blueprint = sd.get('blueprint') or {}
        revisions = blueprint.get('revisions') or []
        
        revision_entry = {
            'id': len(revisions) + 1,
            'requested_at': dt_mod.datetime.now().isoformat(),
            'requested_by': requested_by,
            'requester_name': user.name if user else 'Unknown',
            'feedback': feedback,
            'status': 'PENDING',  # PENDING, IN_PROGRESS, COMPLETED
            'revised_at': None,
            'revised_by': None
        }
        revisions.append(revision_entry)
        blueprint['revisions'] = revisions
        blueprint['revision_count'] = len(revisions)
        blueprint['has_pending_revision'] = True
        sd['blueprint'] = blueprint
        
        # workflow history 추가
        wf = sd.get('workflow') or {}
        hist = wf.get('history') or []
        requester_labels = {'customer': '고객', 'production': '생산팀'}
        hist.append({
            'stage': wf.get('stage', 'CONFIRM'),
            'updated_at': dt_mod.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': f'도면 수정 요청 ({requester_labels.get(requested_by, requested_by)}): {feedback}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 도면 수정 요청: {feedback[:50]}..."))
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': '도면 수정 요청이 등록되었습니다. 도면팀에서 확인 후 수정됩니다.',
            'revision_id': revision_entry['id']
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/drawing/complete-revision', methods=['POST'])
@login_required
@erp_edit_required
def api_drawing_complete_revision(order_id):
    """
    도면 수정 완료 (도면팀에서 수정 후)
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        revision_id = data.get('revision_id')
        revision_note = data.get('note', '')
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        blueprint = sd.get('blueprint') or {}
        revisions = blueprint.get('revisions') or []
        
        # 해당 revision 찾아서 완료 처리
        for rev in revisions:
            if isinstance(rev, dict) and (rev.get('id') == revision_id or revision_id is None):
                if rev.get('status') == 'PENDING':
                    rev['status'] = 'COMPLETED'
                    rev['revised_at'] = dt_mod.datetime.now().isoformat()
                    rev['revised_by'] = user.name if user else 'Unknown'
                    rev['revision_note'] = revision_note
                    break
        
        # 대기중인 수정이 더 있는지 확인
        pending_count = sum(1 for r in revisions if isinstance(r, dict) and r.get('status') == 'PENDING')
        blueprint['has_pending_revision'] = pending_count > 0
        blueprint['revisions'] = revisions
        sd['blueprint'] = blueprint
        
        wf = sd.get('workflow') or {}
        hist = wf.get('history') or []
        hist.append({
            'stage': wf.get('stage', 'DRAWING'),
            'updated_at': dt_mod.datetime.now().isoformat(),
            'updated_by': user.name if user else 'Unknown',
            'note': f'도면 수정 완료: {revision_note}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 도면 수정 완료"))
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': '도면 수정이 완료되었습니다.',
            'pending_revisions': pending_count
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/api/orders/<int:order_id>/confirm/customer', methods=['POST'])
@login_required
@erp_edit_required
def api_customer_confirm(order_id):
    """
    고객 컨펌 완료 처리
    Blueprint V3: 컨펌 완료 → FOMS 상태 업데이트 → 생산 단계로 이동
    """
    db = get_db()
    try:
        order = db.query(Order).get(order_id)
        if not order:
            return jsonify({'success': False, 'message': '주문을 찾을 수 없습니다.'}), 404
        
        data = request.get_json() or {}
        confirmation_note = data.get('note', '')
        
        user_id = session.get('user_id')
        user = get_user_by_id(user_id)
        
        import copy
        import datetime as dt_mod
        from sqlalchemy.orm.attributes import flag_modified
        
        sd = _ensure_dict(order.structured_data)
        
        # 고객 컨펌 정보 저장
        blueprint = sd.get('blueprint') or {}
        blueprint['customer_confirmed'] = True
        blueprint['confirmed_at'] = dt_mod.datetime.now().isoformat()
        blueprint['confirmed_by'] = user.name if user else 'Unknown'
        blueprint['confirmation_note'] = confirmation_note
        sd['blueprint'] = blueprint
        
        # PRODUCTION 단계로 이동
        wf = sd.get('workflow') or {}
        wf['stage'] = 'PRODUCTION'
        wf['stage_updated_at'] = dt_mod.datetime.now().isoformat()
        wf['stage_updated_by'] = user.name if user else 'Unknown'
        
        hist = wf.get('history') or []
        hist.append({
            'stage': 'PRODUCTION',
            'updated_at': wf['stage_updated_at'],
            'updated_by': wf['stage_updated_by'],
            'note': f'고객 컨펌 완료 → 생산 단계로 이동: {confirmation_note}'
        })
        wf['history'] = hist
        sd['workflow'] = wf
        
        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")
        order.status = 'PRODUCTION'
        
        from models import SecurityLog
        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 고객 컨펌 완료 → 생산 단계"))
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': '고객 컨펌이 완료되었습니다. 생산 단계로 이동합니다.',
            'new_status': 'PRODUCTION'
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# =============================================
# 알림 시스템 API
# =============================================

def _parse_history_time(value):
    """도면 히스토리 문자열 시각을 datetime으로 파싱."""
    if not value:
        return None
    try:
        return datetime.datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def _build_drawing_event_key(idx, event):
    action = str((event or {}).get('action') or '')
    at = str((event or {}).get('at') or (event or {}).get('transferred_at') or '')
    by_user_id = str((event or {}).get('by_user_id') or '')
    return f"{idx}:{action}:{at}:{by_user_id}"


def _resolve_notification_deep_link(notification, order_structured_data):
    """알림 -> 도면 작업실 상세 딥링크 정보(event_id/target_no/tab) 계산."""
    n_type = str(getattr(notification, 'notification_type', '') or '').upper()
    if n_type not in ('DRAWING_TRANSFERRED', 'DRAWING_REVISION'):
        return {
            'deep_tab': None,
            'deep_event_id': None,
            'deep_target_no': None,
            'deep_link_url': None,
        }

    target_action = 'TRANSFER' if n_type == 'DRAWING_TRANSFERRED' else 'REQUEST_REVISION'
    target_tab = 'timeline' if n_type == 'DRAWING_TRANSFERRED' else 'requests'
    history = list(((order_structured_data or {}).get('drawing_transfer_history', []) or []))
    if not history:
        return {
            'deep_tab': target_tab,
            'deep_event_id': None,
            'deep_target_no': None,
            'deep_link_url': f"/erp/drawing-workbench/{notification.order_id}?tab={target_tab}",
        }

    created_at = getattr(notification, 'created_at', None)
    matched = None
    matched_idx = -1
    best_score = None

    for idx, h in enumerate(history):
        if not isinstance(h, dict):
            continue
        if str(h.get('action') or '') != target_action:
            continue
        h_dt = _parse_history_time(h.get('at') or h.get('transferred_at'))
        if created_at and h_dt:
            score = abs((created_at - h_dt).total_seconds())
        else:
            score = float('inf')
        if best_score is None or score < best_score:
            best_score = score
            matched = h
            matched_idx = idx

    if matched is None:
        for idx in range(len(history) - 1, -1, -1):
            h = history[idx]
            if isinstance(h, dict) and str(h.get('action') or '') == target_action:
                matched = h
                matched_idx = idx
                break

    deep_event_id = _build_drawing_event_key(matched_idx, matched) if matched is not None and matched_idx >= 0 else None
    deep_target_no = None
    if isinstance(matched, dict):
        try:
            deep_target_no = int(matched.get('target_drawing_number') or matched.get('replace_target_number') or 0) or None
        except (TypeError, ValueError):
            deep_target_no = None

    query_parts = [f"tab={target_tab}"]
    if deep_event_id:
        query_parts.append(f"event_id={quote(str(deep_event_id), safe='')}")
    if deep_target_no:
        query_parts.append(f"target_no={deep_target_no}")
    deep_link_url = f"/erp/drawing-workbench/{notification.order_id}?{'&'.join(query_parts)}"
    return {
        'deep_tab': target_tab,
        'deep_event_id': deep_event_id,
        'deep_target_no': deep_target_no,
        'deep_link_url': deep_link_url,
    }


@erp_beta_bp.route('/erp/api/notifications', methods=['GET'])
@login_required
def api_notifications_list():
    """현재 사용자의 알림 목록 조회
    
    Query params:
    - unread_only: true면 읽지 않은 알림만
    - limit: 최대 개수 (기본 20)
    """
    try:
        from models import Notification, User
        
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 404
        
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 20))
        
        # 사용자 팀/이름에 따라 알림 필터링
        query = db.query(Notification)
        
        # 팀 기반 필터링 또는 영업사원명 기반 필터링
        user_team = user.team.upper() if user.team else None
        user_name = user.name.strip() if user.name else None
        
        print(f"[DEBUG] Notification Check - User: '{user_name}', Team: '{user_team}'")
        
        # 조건: (target_team이 사용자 팀과 일치) OR (target_manager_name이 사용자 이름과 일치) OR (ADMIN은 모든 알림)
        if user.role == 'ADMIN':
            # ADMIN은 모든 알림 조회 가능
            pass
        else:
            from sqlalchemy import or_
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                query = query.filter(or_(*conditions))
            else:
                # 매칭 조건 없으면 빈 결과
                return jsonify({'success': True, 'notifications': [], 'unread_count': 0})
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        notifications = query.all()
        
        # 읽지 않은 알림 수
        unread_query = db.query(Notification).filter(Notification.is_read == False)
        if user.role != 'ADMIN':
            from sqlalchemy import or_
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                unread_query = unread_query.filter(or_(*conditions))
        unread_count = unread_query.count()
        
        order_ids = list({int(n.order_id) for n in notifications if getattr(n, 'order_id', None)})
        order_map = {}
        if order_ids:
            order_rows = db.query(Order.id, Order.structured_data).filter(Order.id.in_(order_ids)).all()
            for oid, sd in order_rows:
                order_map[int(oid)] = _ensure_dict(sd)

        notif_payloads = []
        for n in notifications:
            row = n.to_dict()
            deep = _resolve_notification_deep_link(n, order_map.get(int(n.order_id), {}))
            row.update(deep)
            notif_payloads.append(row)

        return jsonify({
            'success': True,
            'notifications': notif_payloads,
            'unread_count': unread_count
        })
    except Exception as e:
        import traceback
        print(f"Notification List Error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/erp/api/notifications/badge', methods=['GET'])
@login_required
def api_notifications_badge():
    """알림 배지 카운트 조회 (읽지 않은 알림 수)"""
    try:
        from models import Notification, User
        
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'success': True, 'count': 0})
        
        user_team = user.team.upper() if user.team else None
        user_name = user.name
        
        query = db.query(Notification).filter(Notification.is_read == False)
        
        if user.role != 'ADMIN':
            from sqlalchemy import or_
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                query = query.filter(or_(*conditions))
            else:
                return jsonify({'success': True, 'count': 0})
        
        count = query.count()
        
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': True, 'count': 0})


@erp_beta_bp.route('/erp/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def api_notification_mark_read(notification_id):
    """알림 읽음 처리"""
    try:
        from models import Notification
        import datetime as dt_mod
        
        db = get_db()
        user_id = session.get('user_id')
        
        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notification:
            return jsonify({'success': False, 'message': '알림을 찾을 수 없습니다.'}), 404
        
        notification.is_read = True
        notification.read_at = dt_mod.datetime.now()
        notification.read_by_user_id = user_id
        
        db.commit()
        
        return jsonify({'success': True, 'message': '알림을 읽음 처리했습니다.'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@erp_beta_bp.route('/erp/api/notifications/read-all', methods=['POST'])
@login_required
def api_notifications_mark_all_read():
    """모든 알림 읽음 처리"""
    try:
        from models import Notification, User
        import datetime as dt_mod
        
        db = get_db()
        user_id = session.get('user_id')
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return jsonify({'success': False, 'message': '사용자 정보를 찾을 수 없습니다.'}), 404
        
        user_team = user.team.upper() if user.team else None
        user_name = user.name
        
        query = db.query(Notification).filter(Notification.is_read == False)
        
        if user.role != 'ADMIN':
            from sqlalchemy import or_
            conditions = []
            if user_team:
                conditions.append(Notification.target_team == user_team)
            if user_name:
                conditions.append(Notification.target_manager_name == user_name)
            if conditions:
                query = query.filter(or_(*conditions))
        
        now = dt_mod.datetime.now()
        updated = query.update({
            Notification.is_read: True,
            Notification.read_at: now,
            Notification.read_by_user_id: user_id
        }, synchronize_session='fetch')
        
        db.commit()
        
        return jsonify({'success': True, 'message': f'{updated}개 알림을 읽음 처리했습니다.', 'count': updated})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
