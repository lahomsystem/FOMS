import warnings
# warnings.filterwarnings("ignore", category=DeprecationWarning, module="eventlet")
# import eventlet
# eventlet.monkey_patch()
import os
import hashlib
import datetime
import json
import pandas as pd
import re
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g, session, send_file, send_from_directory, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress
from whitenoise import WhiteNoise
from markupsafe import Markup
from werkzeug.utils import secure_filename
from werkzeug import security as _werkzeug_security
import sys
# Python 3.12+: hmac.new() requires digestmod=; older Werkzeug passes method as 3rd pos arg.
# pbkdf2/scrypt는 원래 구현(pbkdf2_hmac 등)을 사용해야 하므로 위임하고, 나머지만 HMAC 패치 적용.
if sys.version_info >= (3, 12) and hasattr(_werkzeug_security, '_hash_internal'):
    import hmac as _hmac
    _original_hash_internal = _werkzeug_security._hash_internal
    def _hash_internal_py312(method, salt, password):
        if isinstance(method, str) and (method.startswith('pbkdf2') or method.startswith('scrypt')):
            return _original_hash_internal(method, salt, password)
        digestmod = getattr(hashlib, method, None) if isinstance(method, str) else method
        if digestmod is None:
            digestmod = hashlib.sha256
        key = salt.encode('utf-8') if isinstance(salt, str) else salt
        msg = password.encode('utf-8') if isinstance(password, str) else password
        return _hmac.new(key, msg, digestmod=digestmod).hexdigest(), method
    _werkzeug_security._hash_internal = _hash_internal_py312
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, and_, text, func, String
from sqlalchemy.orm.attributes import flag_modified
import copy
import json
import threading
from datetime import date, timedelta

# 데이터베이스 관련 임포트
from db import get_db, close_db, init_db, db_session
from models import Order, User, SecurityLog, ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment, OrderAttachment, OrderEvent, OrderTask, Notification
from apps.auth import is_password_strong, get_user_by_username
from services.business_calendar import add_business_days
from services.erp_policy import (
    recommend_owner_team, 
    get_required_task_keys_for_stage, 
    STAGE_NAME_TO_CODE,
    get_quest_templates,
    get_quest_template_for_stage,
    get_required_approval_teams_for_stage,
    get_next_stage_for_completed_quest,
    get_stage,
    DEFAULT_OWNER_TEAM_BY_STAGE,
    can_modify_domain,
    get_assignee_ids,
)

# 견적 계산기 독립 데이터베이스 임포트
from wdcalculator_db import close_wdcalculator_db, init_wdcalculator_db

# 지도/주소 API는 erp_map_bp에서 처리

# 스토리지 시스템 임포트 (Quest 2)
from services.storage import get_storage
from map_config import KAKAO_REST_API_KEY
from services.business_calendar import business_days_until
from services.order_display_utils import format_options_for_display, _ensure_dict
from constants import STATUS, BULK_ACTION_STATUS, CABINET_STATUS, UPLOAD_FOLDER, ALLOWED_EXTENSIONS, CHAT_ALLOWED_EXTENSIONS, ERP_MEDIA_ALLOWED_EXTENSIONS

# SocketIO Import (Quest 5)
try:
    from flask_socketio import SocketIO, emit, join_room, leave_room
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    print("[WARN] Flask-SocketIO not installed. pip install flask-socketio python-socketio eventlet")

# Initialize Flask app
app = Flask(__name__)

# ==========================================
# Data Optimization (Quest 14)
# ==========================================

# 1. Gzip Compression (Reduce JSON/HTML size by ~70%)
Compress(app)

# 2. WhiteNoise (Fast Static File Serving & Caching)
# Railway/Heroku 배포 시 필수 최적화
_is_production = (os.environ.get('FLASK_ENV') == 'production')
app.wsgi_app = WhiteNoise(
    app.wsgi_app,
    root='static/',
    prefix='static/',
    # 개발 모드에서 정적 파일 변경 시 Content-Length 캐시 불일치 방지
    autorefresh=not _is_production,
    max_age=31536000 if _is_production else 0,
)

# Secret Key from environment variable (CRITICAL: Never hardcode in production!)
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    # Development fallback (MUST set SECRET_KEY in production!)
    if os.environ.get('FLASK_ENV') == 'production':
        raise ValueError("SECRET_KEY environment variable must be set in production!")
    app.secret_key = 'dev-secret-key-CHANGE-IN-PRODUCTION'
    print("[WARN] Using development secret key. Set SECRET_KEY environment variable for production!")

# Session cookie configuration (prevent conflicts with other Flask apps on same domain)
app.config['SESSION_COOKIE_NAME'] = 'session_staging'  # Different from port 5000 (session_dev)

# Fix for Railway/Load Balancer (HTTPS redirect loop)
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Import Apps Blueprints
from apps.auth import auth_bp, login_required, role_required, ROLES, TEAMS, log_access, get_user_by_id
app.register_blueprint(auth_bp)

# ERP Beta Blueprint
from apps.erp import erp_bp, apply_erp_display_fields_to_orders, can_edit_erp
app.register_blueprint(erp_bp)

# API Files Blueprint
from apps.api.files import files_bp, build_file_view_url, build_file_download_url
app.register_blueprint(files_bp)

# API Address Blueprint
from apps.api.address import address_bp
app.register_blueprint(address_bp)

# API Orders Blueprint
from apps.api.orders import orders_bp
app.register_blueprint(orders_bp)

# API Notifications Blueprint (ERP 알림, Phase 4-1)
from apps.api.notifications import notifications_bp
app.register_blueprint(notifications_bp)

# ERP 출고 설정 Blueprint (Phase 4-2)
from apps.api.erp_shipment_settings import erp_shipment_bp
app.register_blueprint(erp_shipment_bp)
from apps.api.erp_measurement import erp_measurement_bp
app.register_blueprint(erp_measurement_bp)
from apps.api.erp_map import erp_map_bp
app.register_blueprint(erp_map_bp)
from apps.api.erp_orders_quick import erp_orders_quick_bp
app.register_blueprint(erp_orders_quick_bp)
from apps.api.erp_orders_drawing import erp_orders_drawing_bp
app.register_blueprint(erp_orders_drawing_bp)
from apps.api.erp_orders_revision import erp_orders_revision_bp
app.register_blueprint(erp_orders_revision_bp)
from apps.api.erp_orders_draftsman import erp_orders_draftsman_bp
app.register_blueprint(erp_orders_draftsman_bp)
from apps.api.erp_orders_production import erp_orders_production_bp
app.register_blueprint(erp_orders_production_bp)
from apps.api.erp_orders_construction import erp_orders_construction_bp
app.register_blueprint(erp_orders_construction_bp)
from apps.api.erp_orders_cs import erp_orders_cs_bp
app.register_blueprint(erp_orders_cs_bp)
from apps.api.erp_orders_as import erp_orders_as_bp
app.register_blueprint(erp_orders_as_bp)
from apps.api.erp_orders_confirm import erp_orders_confirm_bp
app.register_blueprint(erp_orders_confirm_bp)
from apps.storage_dashboard import storage_dashboard_bp
app.register_blueprint(storage_dashboard_bp)
from apps.api.chat import chat_bp, register_chat_socketio_handlers
app.register_blueprint(chat_bp)
from apps.api.wdcalculator import wdcalculator_bp
app.register_blueprint(wdcalculator_bp)
from apps.api.backup import backup_bp
app.register_blueprint(backup_bp)
from apps.admin import admin_bp
app.register_blueprint(admin_bp)
from apps.user_pages import user_pages_bp
app.register_blueprint(user_pages_bp)
from apps.dashboards import dashboards_bp
app.register_blueprint(dashboards_bp)
from apps.api.attachments import attachments_bp, ensure_order_attachments_category_column, ensure_order_attachments_item_index_column
app.register_blueprint(attachments_bp)
from apps.api.tasks import tasks_bp
app.register_blueprint(tasks_bp)
from apps.api.events import events_bp
app.register_blueprint(events_bp)
from apps.api.quest import quest_bp
app.register_blueprint(quest_bp)
from apps.api.erp_orders_blueprint import erp_orders_blueprint_bp
app.register_blueprint(erp_orders_blueprint_bp)
from apps.api.erp_orders_structured import erp_orders_structured_bp
app.register_blueprint(erp_orders_structured_bp)
from apps.order_pages import order_pages_bp
app.register_blueprint(order_pages_bp)
from apps.order_trash import order_trash_bp
app.register_blueprint(order_trash_bp)
from services.request_utils import get_preserved_filter_args

# Error handler with production safety
@app.errorhandler(500)
def internal_error(error):
    import traceback
    # Only show detailed errors in development
    if app.debug or os.environ.get('FLASK_ENV') != 'production':
        return f"<pre>500 Error: {str(error)}\n\n{traceback.format_exc()}</pre>", 500
    else:
        # Production: Log error but show generic message
        app.logger.error(f"Internal Server Error: {str(error)}\n{traceback.format_exc()}")
        return render_template('error_500.html'), 500


@app.get('/__build')
def build_info():
    return jsonify({
        'build': '20260215-uxfix-03',
        'cwd': os.getcwd(),
        'template': 'templates/layout.html',
    })

# ==========================================
# Security & Scalability Configuration (Quest 14)
# ==========================================

# 1. Redis Configuration
redis_url = os.environ.get('REDIS_URL')

# 2. Rate Limiter (DDoS Protection)
# Redis가 있으면 Redis를 저장소로, 없으면 메모리 사용
# NOTE:
# - Railway/Reverse proxy 환경에서는 get_remote_address()가 내부 IP로 고정될 수 있어
#   사용자들이 같은 rate-limit bucket을 공유하게 됩니다.
# - 인증 사용자(user_id) -> 세션쿠키 해시 -> X-Forwarded-For -> Remote Addr 순서로 key를 선택해
#   불필요한 429를 줄입니다.
def rate_limit_key():
    try:
        uid = session.get('user_id')
        if uid:
            return f"user:{uid}"
    except Exception:
        pass

    # 로그인 세션이 있으나 user_id를 복원하지 못한 경우(예: 세션 초기화 타이밍/리다이렉트 직후)
    # 동일 IP 공유로 bucket 충돌이 발생하지 않도록 세션쿠키 해시를 key로 사용
    try:
        cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
        raw_cookie = request.cookies.get(cookie_name, '').strip()
        if raw_cookie:
            cookie_hash = hashlib.sha1(raw_cookie.encode('utf-8')).hexdigest()[:16]
            return f"sess:{cookie_hash}"
    except Exception:
        pass

    xff = request.headers.get('X-Forwarded-For', '')
    if xff:
        client_ip = xff.split(',')[0].strip()
        if client_ip:
            return client_ip

    x_real_ip = request.headers.get('X-Real-IP', '').strip()
    if x_real_ip:
        return x_real_ip

    return get_remote_address()

_default_limits_raw = os.environ.get('FLASK_DEFAULT_RATE_LIMITS', '5000 per day,1200 per hour')
default_limits = [x.strip() for x in _default_limits_raw.split(',') if x.strip()]
if not default_limits:
    default_limits = ["5000 per day", "1200 per hour"]

limiter = Limiter(
    rate_limit_key,
    app=app,
    storage_uri=redis_url or "memory://",
    default_limits=default_limits
)

# 3. SocketIO Initialization with Redis & CORS Control
# Use threading mode for Windows WebSocket support & Stability
if SOCKETIO_AVAILABLE:
    try:
        # CORS 도메인 제한 (환경변수 없으면 모든 도메인 허용 - 개발 편의성)
        allowed_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '*').split(',')
        
        # Redis가 설정되어 있으면 Message Queue로 사용 (Scale-out 지원)
        if redis_url:
            print(f"[INFO] Socket.IO connecting to Redis Message Queue: {redis_url}")
            socketio = SocketIO(
                app, 
                cors_allowed_origins=allowed_origins, 
                async_mode='threading',
                message_queue=redis_url
            )
            print("[INFO] Socket.IO initialized in threading mode with Redis.")
        else:
            print("[WARN] REDIS_URL not found. Socket.IO running in single-worker mode (Memory).")
            socketio = SocketIO(
                app, 
                cors_allowed_origins=allowed_origins, 
                async_mode='threading'
            )
            print("[INFO] Socket.IO initialized in threading mode (Universal Stable).")
            
    except Exception as e:
        # fallback
        print(f"[WARN] Socket.IO init failed: {e}")
        socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
else:
    socketio = None

if SOCKETIO_AVAILABLE and socketio:
    register_chat_socketio_handlers(socketio)
    app.config['SOCKETIO_AVAILABLE'] = True
    app.config['_SOCKETIO_INSTANCE'] = socketio
else:
    app.config['SOCKETIO_AVAILABLE'] = False
    app.config['_SOCKETIO_INSTANCE'] = None

# 템플릿 캐시 비활성화 (개발 중 변경사항 즉시 반영)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Extensions config moved to constants.py

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
from flask import Response
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB (Restore video support for Pro Plan)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 데이터베이스 연결 설정
app.teardown_appcontext(close_db)
app.teardown_appcontext(close_wdcalculator_db)  # 견적 계산기 독립 DB

# Function to check if file has allowed extension
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_erp_media_file(filename):
    """ERP Beta 첨부(사진/동영상) 확장자 검증"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ERP_MEDIA_ALLOWED_EXTENSIONS


# Status constants moved to constants.py

@app.template_filter('parse_json_string')
def parse_json_string(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return {}

@app.context_processor
def inject_statuses():
    return dict(
        ALL_STATUS=STATUS,
        BULK_ACTION_STATUS=BULK_ACTION_STATUS
    )

# Auth logic moved to apps/auth.py

# Auth helper functions moved to apps/auth.py

# role_required moved to apps/auth.py

# ============================================
# ERP Process Dashboard (Palantir-style)
# _ensure_dict, format_options_for_display → services.order_display_utils

# Context Processors
@app.context_processor
def inject_status_list():
    """상태 목록과 현재 사용자 정보를 템플릿에 주입"""
    # 삭제됨(DELETED) 상태를 제외한 상태 목록
    display_status = {k: v for k, v in STATUS.items() if k != 'DELETED'}
    
    # 일괄 작업용 상태 목록 (삭제됨 제외)
    bulk_action_status = {k: v for k, v in STATUS.items() if k != 'DELETED'}
    
    # 현재 로그인한 사용자 추가
    current_user = None
    if 'user_id' in session:
        current_user = get_user_by_id(session['user_id'])

    # 관리자 전용: 드롭다운 아이디 이동용 사용자 목록 / 전환 중인지 여부
    admin_switch_users = []
    impersonating_from_id = session.get('impersonating_from')
    if current_user and current_user.role == 'ADMIN':
        db = get_db()
        admin_switch_users = db.query(User).filter(
            User.is_active == True,
            User.id != current_user.id
        ).order_by(User.name).all()

    # ERP Beta 플래그 (기본: 활성) - 필요 시 환경변수로 OFF 가능
    erp_beta_enabled = str(os.getenv('ERP_BETA_ENABLED', 'true')).lower() in ['1', 'true', 'yes', 'y', 'on']
    
    return dict(
        STATUS=display_status, 
        BULK_ACTION_STATUS=bulk_action_status,
        ALL_STATUS=STATUS, 
        ROLES=ROLES,
        current_user=current_user,
        admin_switch_users=admin_switch_users,
        impersonating_from_id=impersonating_from_id,
        erp_beta_enabled=erp_beta_enabled
    )

def parse_json_string(json_string):
    if not json_string:
        return None
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        return None

@app.context_processor
def utility_processor():
    return dict(parse_json_string=parse_json_string)



# Routes
@app.route('/favicon.ico')
def favicon():
    """favicon 요청 처리 (404 방지)"""
    return '', 204  # No Content

@app.route('/debug-db')
def debug_db():
    """Database Connection Check Route (Temporary)"""
    try:
        from sqlalchemy import text
        db = get_db()
        # 1. Simple Select
        result = db.execute(text("SELECT 1")).fetchone()
        
        # 2. Check Tables
        tables_query = text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [row[0] for row in db.execute(tables_query).fetchall()]
        
        status = "SUCCESS"
        message = f"Connected! Result: {result}, Tables: {tables}"
        
        # Check specific table
        if 'users' in tables:
            user_count = db.query(User).count()
            message += f" | Users count: {user_count}"
        else:
            status = "WARNING"
            message += " | 'users' table MISSING"
            
        return jsonify({"status": status, "message": message, "env_db_url_set": bool(os.environ.get('DATABASE_URL'))})
        
    except Exception as e:
        import traceback
        return jsonify({
            "status": "ERROR", 
            "error": str(e), 
            "traceback": traceback.format_exc()
        }), 500

# index, add_order -> order_pages_bp


@app.route('/edit/<int:order_id>', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def edit_order(order_id):
    db = get_db()
    
    order = db.query(Order).filter(Order.id == order_id, Order.status != 'DELETED').first()
    
    if not order:
        flash('주문을 찾을 수 없거나 이미 삭제되었습니다.', 'error')
        return redirect(url_for('order_pages.index'))
    
    # ERP Beta 주문의 경우 수정 권한 검사
    if order.is_erp_beta:
        user = get_user_by_id(session['user_id'])
        if not can_edit_erp(user):
            flash('ERP Beta 주문 수정 권한이 없습니다. (관리자, CS, 영업팀만 가능)', 'error')
            return redirect(url_for('order_pages.index'))
    
    # 옵션 데이터 처리를 위한 변수 초기화
    option_type = 'online'  # 기본 옵션 타입
    online_options = ""     # 온라인 옵션 텍스트
    direct_options = {      # 직접 입력 옵션 필드
        'product_name': '', 
        'standard': '', 
        'internal': '',
        'color': '',
        'option_detail': '',
        'handle': '',
        'misc': '',
        'quote': ''
    }
    
    # 주문 옵션 데이터 처리
    if order.options:
        try:
            # 옵션 데이터 파싱 시도
            options_data = json.loads(order.options)
            
            # 옵션 데이터가 객체고 option_type 필드가 있는 경우
            if isinstance(options_data, dict):
                # 1. option_type 필드가 있는 경우 
                if 'option_type' in options_data:
                    option_type = options_data['option_type']
                    
                    if option_type == 'direct' and 'details' in options_data:
                        # 새로운 형식: "details" 객체에서 직접 값 추출
                        details = options_data['details']
                        for key in direct_options.keys():
                            if key in details:
                                direct_options[key] = details[key]
                    elif option_type == 'online' and 'online_options_summary' in options_data:
                        online_options = options_data['online_options_summary']
                
                # 2. 구형식 - option_type 없이 직접 키가 있는 경우
                elif any(key in options_data for key in direct_options.keys()):
                    option_type = 'direct'
                    for key in direct_options.keys():
                        if key in options_data:
                            direct_options[key] = options_data[key]
                
                # 3. 한글 키 대응
                elif any(key in options_data for key in ['제품명', '규격', '내부', '색상', '상세옵션', '손잡이', '기타', '견적내용']):
                    option_type = 'direct'
                    key_mapping = {
                        '제품명': 'product_name',
                        '규격': 'standard', 
                        '내부': 'internal',
                        '색상': 'color',
                        '상세옵션': 'option_detail',
                        '손잡이': 'handle',
                        '기타': 'misc',
                        '견적내용': 'quote'
                    }
                    for k_kor, k_eng in key_mapping.items():
                        if k_kor in options_data:
                            direct_options[k_eng] = options_data[k_kor]
                
                # 4. 이외의 경우 online으로 처리하고 문자열로 표시
                else:
                    option_type = 'online'
                    online_options = order.options  # 원래 문자열 그대로 표시
            
            # 객체가 아닌 경우 온라인 옵션으로 처리
            else:
                option_type = 'online'
                online_options = order.options
                
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 온라인 옵션으로 처리
            option_type = 'online'
            online_options = order.options if order.options else ""
    
    if request.method == 'POST':
        try:
            # 폼 데이터 처리
            
            # 폼에서 넘어온 값들을 가져올 때, 해당 필드가 폼에 없으면 기존 order 객체의 값을 기본값으로 사용
            received_date = request.form.get('received_date', order.received_date)
            received_time = request.form.get('received_time', order.received_time)
            customer_name = request.form.get('customer_name', order.customer_name)
            phone = request.form.get('phone', order.phone)
            address = request.form.get('address', order.address)
            product = request.form.get('product', order.product)
            notes = request.form.get('notes', order.notes)
            status = request.form.get('status', order.status) # 상태가 없으면 기존 상태 유지
            
            measurement_date = request.form.get('measurement_date', order.measurement_date)
            measurement_time = request.form.get('measurement_time', order.measurement_time)
            completion_date = request.form.get('completion_date', order.completion_date)
            manager_name = request.form.get('manager_name', order.manager_name)

            # 새로 추가한 필드들 (기존 값 유지)
            scheduled_date = request.form.get('scheduled_date', order.scheduled_date)
            as_received_date = request.form.get('as_received_date', order.as_received_date)
            as_completed_date = request.form.get('as_completed_date', order.as_completed_date)
            shipping_scheduled_date = request.form.get('shipping_scheduled_date', order.shipping_scheduled_date) # 상차 예정일 추가

            # 옵션 데이터 처리 (폼에 option_type이 있을 때만 업데이트)
            options_data_json_to_save = order.options # 기본적으로 기존 옵션 유지
            if 'option_type' in request.form:
                current_option_type = request.form.get('option_type')
            
                if current_option_type == 'direct':
                    direct_details = {
                        'product_name': request.form.get('direct_product_name', ''),
                        'standard': request.form.get('direct_standard', ''),
                        'internal': request.form.get('direct_internal', ''),
                        'color': request.form.get('direct_color', ''),
                        'option_detail': request.form.get('direct_option_detail', ''),
                        'handle': request.form.get('direct_handle', ''),
                        'misc': request.form.get('direct_misc', ''),
                        'quote': request.form.get('direct_quote', '')
                    }
                    options_to_save_dict = {
                        "option_type": "direct",
                        "details": direct_details
                    }
                    options_data_json_to_save = json.dumps(options_to_save_dict, ensure_ascii=False)
                else:  # 'online'
                    online_summary = request.form.get('options_online', '')
                    options_to_save_dict = {
                        "option_type": "online",
                        "online_options_summary": online_summary
                    }
                    options_data_json_to_save = json.dumps(options_to_save_dict, ensure_ascii=False)
            
            # ... (기존 POST 로직의 변경 감지 및 DB 업데이트 부분) ...
            changes = {}
            if order.received_date != received_date: changes['received_date'] = {'old': order.received_date, 'new': received_date}
            if order.received_time != received_time: changes['received_time'] = {'old': order.received_time, 'new': received_time}
            if order.customer_name != customer_name: changes['customer_name'] = {'old': order.customer_name, 'new': customer_name}
            if order.phone != phone: changes['phone'] = {'old': order.phone, 'new': phone}
            if order.address != address: changes['address'] = {'old': order.address, 'new': address}
            if order.product != product: changes['product'] = {'old': order.product, 'new': product}
            if order.options != options_data_json_to_save: changes['options'] = {'old': order.options, 'new': options_data_json_to_save}
            if order.notes != notes: changes['notes'] = {'old': order.notes, 'new': notes}
            if order.status != status: changes['status'] = {'old': order.status, 'new': status}
            if order.measurement_date != measurement_date: changes['measurement_date'] = {'old': order.measurement_date, 'new': measurement_date}
            if order.measurement_time != measurement_time: changes['measurement_time'] = {'old': order.measurement_time, 'new': measurement_time}
            if order.completion_date != completion_date: changes['completion_date'] = {'old': order.completion_date, 'new': completion_date}
            if order.manager_name != manager_name: changes['manager_name'] = {'old': order.manager_name, 'new': manager_name}
            
            # 새 필드들 변경 감지
            if order.scheduled_date != scheduled_date: changes['scheduled_date'] = {'old': order.scheduled_date, 'new': scheduled_date}
            if order.as_received_date != as_received_date: changes['as_received_date'] = {'old': order.as_received_date, 'new': as_received_date}
            if order.as_completed_date != as_completed_date: changes['as_completed_date'] = {'old': order.as_completed_date, 'new': as_completed_date}
            if order.shipping_scheduled_date != shipping_scheduled_date: changes['shipping_scheduled_date'] = {'old': order.shipping_scheduled_date, 'new': shipping_scheduled_date} # 상차 예정일 변경 감지
            
            # 지방 주문 관련 필드 변경 감지
            is_regional_new = 'is_regional' in request.form
            if order.is_regional != is_regional_new: changes['is_regional'] = {'old': order.is_regional, 'new': is_regional_new}
            
            # 자가실측 관련 필드 변경 감지
            is_self_measurement_new = 'is_self_measurement' in request.form
            if order.is_self_measurement != is_self_measurement_new: changes['is_self_measurement'] = {'old': order.is_self_measurement, 'new': is_self_measurement_new}
            
            measurement_completed_new = 'measurement_completed' in request.form
            if order.measurement_completed != measurement_completed_new: changes['measurement_completed'] = {'old': order.measurement_completed, 'new': measurement_completed_new}
            
            construction_type_new = request.form.get('construction_type', order.construction_type)
            if order.construction_type != construction_type_new: changes['construction_type'] = {'old': order.construction_type, 'new': construction_type_new}
            
            # payment_amount 업데이트 및 변경 감지
            new_payment_amount = order.payment_amount # 기본적으로 기존 결제금액 유지
            if 'payment_amount' in request.form:
                payment_amount_str = request.form.get('payment_amount', '').replace(',', '') # 콤마 제거
                if payment_amount_str: # 빈 문자열이 아닌 경우에만 변환 시도
                    try:
                        new_payment_amount = int(payment_amount_str) 
                    except ValueError:
                        flash('결제금액은 숫자만 입력해주세요.', 'error')
                        raise ValueError("Invalid payment amount")
                else: # 빈 문자열로 넘어오면 0으로 처리 (또는 None으로 처리할 수도 있음)
                    new_payment_amount = 0
            
            if order.payment_amount != new_payment_amount:
                changes['payment_amount'] = {'old': order.payment_amount, 'new': new_payment_amount}
            # order.payment_amount = new_payment_amount # 아래에서 한꺼번에 업데이트

            # Update order object
            order.received_date = received_date
            order.received_time = received_time
            order.customer_name = customer_name
            order.phone = phone
            order.address = address
            order.product = product
            order.options = options_data_json_to_save
            order.notes = notes
            order.status = status
            order.measurement_date = measurement_date
            order.measurement_time = measurement_time
            order.completion_date = completion_date
            order.manager_name = manager_name
            
            # 새 필드 값 업데이트
            order.scheduled_date = scheduled_date
            order.as_received_date = as_received_date
            order.as_completed_date = as_completed_date
            order.shipping_scheduled_date = shipping_scheduled_date # 상차 예정일 업데이트
            order.payment_amount = new_payment_amount # 최종 결제금액 업데이트
            
            # 지방 주문 여부 사용자 선택 (체크박스는 체크되지 않으면 폼에 포함되지 않음)
            order.is_regional = is_regional_new
            
            # 자가실측 여부 사용자 선택 (체크박스는 체크되지 않으면 폼에 포함되지 않음)
            order.is_self_measurement = is_self_measurement_new
            
            # 수납장 여부 사용자 선택 (체크박스는 체크되지 않으면 폼에 포함되지 않음)
            is_cabinet_new = 'is_cabinet' in request.form
            if order.is_cabinet != is_cabinet_new:
                changes['is_cabinet'] = {'old': order.is_cabinet, 'new': is_cabinet_new}
            order.is_cabinet = is_cabinet_new
            
            # 수납장 상태 업데이트 (수납장으로 설정되면 기본 상태를 RECEIVED로 설정)
            if is_cabinet_new and not order.cabinet_status:
                order.cabinet_status = 'RECEIVED'
            elif not is_cabinet_new:
                order.cabinet_status = None

            # 시공 구분 업데이트
            order.construction_type = construction_type_new
            
            # 지방 주문 체크박스 필드 업데이트
            if order.is_regional:
                regional_fields = [
                    'measurement_completed',
                    'regional_sales_order_upload',
                    'regional_blueprint_sent',
                    'regional_order_upload',
                    'regional_cargo_sent',
                    'regional_construction_info_sent'
                ]
                
                for field in regional_fields:
                    if field in request.form:
                        # 체크박스는 체크된 경우에만 폼 데이터에 포함됨
                        setattr(order, field, True)
                    else:
                        # 폼에 없으면 체크되지 않은 것으로 간주
                        setattr(order, field, False)
            
            db.commit()
            
            # 필드 레이블 정의 (필드명 -> 한글 레이블 매핑)
            field_labels = {
                'received_date': '접수일',
                'received_time': '접수시간',
                'customer_name': '고객명',
                'phone': '전화번호',
                'address': '주소',
                'product': '제품',
                'options': '옵션 상세',
                'notes': '비고',
                'status': '상태',
                'measurement_date': '실측일',
                'measurement_time': '실측시간',
                'completion_date': '설치완료일',
                'manager_name': '담당자',
                'payment_amount': '결제금액',
                'is_regional': '지방 주문',
                'is_self_measurement': '자가실측',
                'is_cabinet': '수납장',
                'measurement_completed': '실측완료',
                'construction_type': '시공 구분',
                'regional_sales_order_upload': '영업발주 업로드',
                'regional_blueprint_sent': '도면 발송',
                'regional_order_upload': '발주 업로드',
                'regional_cargo_sent': '화물 발송',
                'regional_construction_info_sent': '시공정보 발송',
                'shipping_scheduled_date': '상차 예정일' # 로그용 레이블 추가
            }
            
            # 변경된 필드만 필터링하여 로그 메시지 구성
            change_descriptions = []
            for field, values in changes.items():
                if field in field_labels:
                    # None 값 안전하게 처리
                    old_val = values.get('old', '') or '없음'
                    new_val = values.get('new', '') or '없음'
                    
                    # 옵션은 JSON 문자열이므로 특별 처리
                    if field == 'options':
                        try:
                            old_json = json.loads(old_val) if old_val != '없음' and old_val else None
                            new_json = json.loads(new_val) if new_val != '없음' and new_val else None
                            
                            # 두 JSON이 실질적으로 동일한 값을 가지는지 확인
                            if old_json and new_json:
                                # 온라인 옵션 요약 비교
                                old_option_type = old_json.get('option_type', '')
                                new_option_type = new_json.get('option_type', '')
                                
                                # 타입이 다르면 변경된 것으로 간주
                                if old_option_type != new_option_type:
                                    if old_option_type == 'online':
                                        old_display = old_json.get('online_options_summary', '') or '없음'
                                    elif old_option_type == 'direct':
                                        details = old_json.get('details', {})
                                        old_display = '직접입력: ' + (details.get('product_name', '') or details.get('color', '') or '옵션')
                                    else:
                                        old_display = '옵션 있음'
                                        
                                    if new_option_type == 'online':
                                        new_display = new_json.get('online_options_summary', '') or '없음'
                                    elif new_option_type == 'direct':
                                        details = new_json.get('details', {})
                                        new_display = '직접입력: ' + (details.get('product_name', '') or details.get('color', '') or '옵션')
                                    else:
                                        new_display = '옵션 있음'
                                # 타입이 같고 온라인 옵션인 경우    
                                elif old_option_type == 'online':
                                    old_summary = old_json.get('online_options_summary', '')
                                    new_summary = new_json.get('online_options_summary', '')
                                    
                                    # 내용이 같으면 건너뛰기
                                    if old_summary == new_summary:
                                        continue
                                        
                                    old_display = old_summary or '없음'
                                    new_display = new_summary or '없음'
                                # 타입이 같고 직접 입력 옵션인 경우
                                elif old_option_type == 'direct':
                                    old_details = old_json.get('details', {})
                                    new_details = new_json.get('details', {})
                                    
                                    # 주요 필드만 비교 (product_name, color)
                                    old_key_values = old_details.get('product_name', '') + ' ' + old_details.get('color', '')
                                    new_key_values = new_details.get('product_name', '') + ' ' + new_details.get('color', '')
                                    
                                    # 내용이 같으면 건너뛰기
                                    if old_key_values.strip() == new_key_values.strip():
                                        continue
                                        
                                    old_display = old_details.get('product_name', '') or old_details.get('color', '') or '옵션 있음'
                                    new_display = new_details.get('product_name', '') or new_details.get('color', '') or '옵션 있음'
                                else:
                                    # 기타 경우는 간단하게 표시
                                    old_display = '옵션 있음'
                                    new_display = '옵션 있음'
                                    
                                    # 내용이 같아 보이면 건너뛰기
                                    if json.dumps(old_json, sort_keys=True) == json.dumps(new_json, sort_keys=True):
                                        continue
                            elif not old_json and not new_json:
                                # 둘 다 없거나 빈 값이면 건너뛰기
                                continue
                            else:
                                # 한쪽만 값이 있는 경우 (추가 또는 삭제)
                                if old_json:
                                    if old_json.get('option_type') == 'online':
                                        old_display = old_json.get('online_options_summary', '') or '옵션 있음'
                                    elif old_json.get('option_type') == 'direct':
                                        details = old_json.get('details', {})
                                        old_display = details.get('product_name', '') or details.get('color', '') or '직접입력 옵션'
                                    else:
                                        old_display = '옵션 있음'
                                else:
                                    old_display = '없음'
                                    
                                if new_json:
                                    if new_json.get('option_type') == 'online':
                                        new_display = new_json.get('online_options_summary', '') or '옵션 있음'
                                    elif new_json.get('option_type') == 'direct':
                                        details = new_json.get('details', {})
                                        new_display = details.get('product_name', '') or details.get('color', '') or '직접입력 옵션'
                                    else:
                                        new_display = '옵션 있음'
                                else:
                                    new_display = '없음'
                        except Exception as e:
                            # JSON 파싱 실패 시 원본 값 비교
                            old_display = old_val if old_val != '없음' else '없음'
                            new_display = new_val if new_val != '없음' else '없음'
                            
                            # 값이 같거나 둘 다 빈 값이면 건너뛰기
                            if old_display == new_display or (not old_display.strip() and not new_display.strip()):
                                continue
                    else:
                        # 다른 필드들은 문자열로 변환하여 비교
                        old_display = str(old_val).strip() if old_val != '없음' else '없음'
                        new_display = str(new_val).strip() if new_val != '없음' else '없음'
                        
                        # 값이 같으면 건너뛰기 (공백 제거 후 비교)
                        if old_display == new_display:
                            continue
                        
                        # 상태 코드를 한글 상태명으로 변환
                        if field == 'status':
                            old_display = STATUS.get(old_display, old_display)
                            new_display = STATUS.get(new_display, new_display)
                    
                    # 실제 값이 변경된 경우에만 표시 (위에서 필터링 이미 됨)
                    change_descriptions.append(f"{field_labels[field]}: {old_display} ⇒ {new_display}")
            
            # 주문 번호와 고객명은 필수로 포함
            user_for_log = get_user_by_id(session['user_id'])
            user_name_for_log = user_for_log.name if user_for_log else "Unknown user"
            log_message_prefix = f"주문 #{order_id} ({customer_name}) 수정 - 담당자: {user_name_for_log} (ID: {session.get('user_id')})"
            
            # 변경 내역이 있으면 추가
            if change_descriptions:
                log_message = f"{log_message_prefix} | 변경내용: {'; '.join(change_descriptions)}"
            else:
                log_message = f"{log_message_prefix} | 변경내용 없음"
            
            # 로그 저장
            log_access(log_message, session.get('user_id'))
            
            flash('주문이 성공적으로 수정되었습니다.', 'success')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success'})
            
            # 수정 후 원래 보던 페이지로 리디렉션
            referrer = request.form.get('referrer')
            if referrer:
                # Basic check to prevent open redirection vulnerabilities
                from urllib.parse import urlparse
                if urlparse(referrer).netloc == request.host:
                    return redirect(referrer)
            
            # Fallback to the main index page
            return redirect(url_for('order_pages.index'))
        except ValueError as e:
            db.rollback()
            flash(f'입력 데이터 오류: {str(e)}', 'error')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': str(e)})
        except Exception as e:
            db.rollback()
            flash(f'주문 수정 중 오류가 발생했습니다: {str(e)}', 'error')
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'error', 'message': '시스템 오류가 발생했습니다.'})
            
            # 오류 발생 시 현재 데이터로 페이지 다시 로드
            return render_template(
                'edit_order.html', 
                order=order,
                option_type=option_type,
                online_options=online_options,
                direct_options=direct_options
            )
    
    # GET 요청에 대한 최종 반환 - 미리 처리된 옵션 데이터를 직접 템플릿에 전달
    # 현재 URL 쿼리 파라미터를 템플릿에 전달하여 필터 상태 유지
    preserved_args = get_preserved_filter_args(request.args)
    return render_template(
        'edit_order.html', 
        order=order,
        option_type=option_type,
        online_options=online_options,
        direct_options=direct_options,
        preserved_args=preserved_args
    )

@app.route('/upload', methods=['GET', 'POST'])
@login_required
@role_required(['ADMIN', 'MANAGER'])
def upload_excel():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'excel_file' not in request.files:
            flash('파일이 선택되지 않았습니다.', 'error')
            log_access(f"엑셀 업로드 실패: 파일이 선택되지 않음", session.get('user_id'))
            return redirect(request.url)
        
        file = request.files['excel_file']
        
        if file.filename == '':
            flash('파일이 선택되지 않았습니다.', 'error')
            log_access(f"엑셀 업로드 실패: 빈 파일명", session.get('user_id'))
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            db = get_db() # db 변수를 try 블록 외부에서도 사용 가능하도록 이동
            try:
                # Process the Excel file with pandas
                df = pd.read_excel(file_path)
                
                # Check for required columns (한글 컬럼명으로 변경)
                required_columns = ['접수일', '고객명', '전화번호', '주소', '제품']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    missing_cols_str = ", ".join(missing_columns)
                    flash(f'엑셀 파일에 필수 컬럼이 누락되었습니다: {missing_cols_str}', 'error')
                    log_access(f"엑셀 업로드 실패: 필수 컬럼 누락 ({missing_cols_str}) - 파일명: {filename}", session.get('user_id'))
                    # 파일 삭제 로직 추가 (오류 시)
                    try:
                        os.remove(file_path)
                    except OSError as e: # 구체적인 에러 타입 명시
                        # 업로드된 파일 삭제 오류 (무시)
                        log_access(f"업로드된 파일 삭제 오류: {file_path} - {e}", session.get('user_id'),
                                   {"filename": file_path, "error": str(e)})
                    return redirect(request.url)
                
                # Connect to database (이미 위에서 get_db() 호출)
                
                # Process each row
                order_count = 0
                added_order_ids = []
                
                for index, row in df.iterrows():
                    # Convert fields to the right format and provide defaults (한글 컬럼명 사용)
                    
                    # 날짜 필드 처리 (pd.to_datetime 사용)
                    received_date_dt = pd.to_datetime(row['접수일'], errors='coerce')
                    received_date = received_date_dt.strftime('%Y-%m-%d') if pd.notna(received_date_dt) else datetime.datetime.now().strftime('%Y-%m-%d')

                    measurement_date_dt = pd.to_datetime(row.get('실측일'), errors='coerce') # .get으로 안전하게 접근
                    measurement_date = measurement_date_dt.strftime('%Y-%m-%d') if pd.notna(measurement_date_dt) else None
                    
                    completion_date_dt = pd.to_datetime(row.get('설치완료일'), errors='coerce') # .get으로 안전하게 접근
                    completion_date = completion_date_dt.strftime('%Y-%m-%d') if pd.notna(completion_date_dt) else None

                    # 시간 필드 처리 (다양한 입력 형식 고려)
                    received_time_raw = row.get('접수시간') # .get으로 안전하게 접근
                    received_time = None
                    if pd.notna(received_time_raw):
                        if isinstance(received_time_raw, datetime.time):
                            received_time = received_time_raw.strftime('%H:%M')
                        elif isinstance(received_time_raw, datetime.datetime): # datetime 객체로 읽혔을 경우
                            received_time = received_time_raw.strftime('%H:%M')
                        elif isinstance(received_time_raw, str):
                            # 간단한 형식 검사 (예: HH:MM) - 필요시 정규식 등으로 강화
                            if re.match(r'^\d{1,2}:\d{2}$', received_time_raw.strip()):
                                received_time = received_time_raw.strip()
                            else:
                                try: # 엑셀에서 0.xxxx 와 같은 숫자형식으로 시간을 읽는 경우 대비
                                    time_float = float(received_time_raw)
                                    hours = int(time_float * 24)
                                    minutes = int((time_float * 24 * 60) % 60)
                                    received_time = f"{hours:02d}:{minutes:02d}"
                                except (ValueError, TypeError):
                                    # Warning: Invalid time format for 접수시간 (using default)
                                    received_time = None # 유효하지 않으면 None
                        # 추가: Excel에서 시간 형식이 숫자로 (예: 0.5 = 12:00 PM) 읽히는 경우 처리
                        elif isinstance(received_time_raw, (int, float)):
                            try:
                                # 소수점 형태의 시간을 HH:MM으로 변환
                                total_seconds = int(received_time_raw * 24 * 60 * 60)
                                hours = total_seconds // 3600
                                minutes = (total_seconds % 3600) // 60
                                received_time = f"{hours:02d}:{minutes:02d}"
                            except Exception:
                                                                   # Warning: Could not convert numeric time for 접수시간 (using default)
                                 received_time = None


                    measurement_time_raw = row.get('실측시간') # .get으로 안전하게 접근
                    measurement_time = None
                    if pd.notna(measurement_time_raw):
                        if isinstance(measurement_time_raw, datetime.time):
                            measurement_time = measurement_time_raw.strftime('%H:%M')
                        elif isinstance(measurement_time_raw, datetime.datetime):
                            measurement_time = measurement_time_raw.strftime('%H:%M')
                        elif isinstance(measurement_time_raw, str):
                            if re.match(r'^\d{1,2}:\d{2}$', measurement_time_raw.strip()):
                                measurement_time = measurement_time_raw.strip()
                            else:
                                try:
                                    time_float = float(measurement_time_raw)
                                    hours = int(time_float * 24)
                                    minutes = int((time_float * 24 * 60) % 60)
                                    measurement_time = f"{hours:02d}:{minutes:02d}"
                                except (ValueError, TypeError):
                                    # Warning: Invalid time format for 실측시간 (using default)
                                    measurement_time = None
                        elif isinstance(measurement_time_raw, (int, float)):
                            try:
                                total_seconds = int(measurement_time_raw * 24 * 60 * 60)
                                hours = total_seconds // 3600
                                minutes = (total_seconds % 3600) // 60
                                measurement_time = f"{hours:02d}:{minutes:02d}"
                            except Exception:
                                 # Warning: Could not convert numeric time for 실측시간 (using default)
                                 measurement_time = None
                    
                    # Handle options column if it exists (한글 컬럼명 '옵션')
                    options_raw = row.get('옵션') # .get으로 안전하게 접근
                    options = str(options_raw) if pd.notna(options_raw) else None # 어떤 형식이든 문자열로 저장
                    
                    # Handle notes column if it exists (한글 컬럼명 '비고')
                    notes_raw = row.get('비고') # .get으로 안전하게 접근
                    notes = str(notes_raw) if pd.notna(notes_raw) else None # 문자열로 저장

                    manager_name_raw = row.get('담당자') # .get으로 안전하게 접근
                    manager_name = str(manager_name_raw) if pd.notna(manager_name_raw) else None

                    # payment_amount 처리 (숫자형으로, 콤마 제거)
                    payment_amount_raw = row.get('결제금액')
                    payment_amount = 0 # 기본값 0
                    if pd.notna(payment_amount_raw):
                        try:
                            # 문자열일 경우 콤마 제거 후 정수 변환
                            if isinstance(payment_amount_raw, str):
                                payment_amount_str = payment_amount_raw.replace(',', '')
                                payment_amount = int(float(payment_amount_str)) # 소수점도 고려하여 float으로 먼저 변환
                            elif isinstance(payment_amount_raw, (int, float)):
                                payment_amount = int(payment_amount_raw)
                        except ValueError:
                            # Warning: Invalid payment amount format for 결제금액 (defaulting to 0)
                            payment_amount = 0 # 변환 실패 시 0

                    new_order = Order(
                        customer_name=str(row['고객명']) if pd.notna(row['고객명']) else '', # 문자열로 명시적 변환
                        phone=str(row['전화번호']) if pd.notna(row['전화번호']) else '', # 문자열로 명시적 변환
                        address=str(row['주소']) if pd.notna(row['주소']) else '', # 문자열로 명시적 변환
                        product=str(row['제품']) if pd.notna(row['제품']) else '', # 문자열로 명시적 변환
                        options=options,
                        notes=notes,
                        received_date=received_date,
                        received_time=received_time,
                        status='RECEIVED',  # Default status
                        measurement_date=measurement_date,
                        measurement_time=measurement_time,
                        completion_date=completion_date,
                        manager_name=manager_name,
                        payment_amount=payment_amount, # 추가
                        # 추가된 상태별 날짜 필드
                        scheduled_date=request.form.get('scheduled_date'),
                        as_received_date=request.form.get('as_received_date'),
                        as_completed_date=request.form.get('as_completed_date'),
                        # 지방 주문 여부 기본값은 False (사용자가 수동으로 변경해야 함)
                        is_regional=False
                    )
                    
                    db.add(new_order)
                    db.flush() # ID 할당을 위해 flush
                    added_order_ids.append(new_order.id) # 추가된 주문 ID 저장
                    order_count += 1
                
                db.commit()
                flash(f'{order_count}개의 주문이 성공적으로 등록되었습니다.', 'success')
                log_access(f"엑셀 업로드 성공: {filename} 파일에서 {order_count}개 주문 추가", session.get('user_id'), 
                           {"filename": filename, "orders_added": order_count, "order_ids": added_order_ids})
                
            except Exception as e:
                if db: # db 객체가 초기화된 경우에만 롤백 시도
                    db.rollback()
                error_message = f'엑셀 파일 처리 중 오류가 발생했습니다: {str(e)}'
                flash(error_message, 'error')
                log_access(f"엑셀 업로드 실패: {filename} 파일 처리 중 오류 - {str(e)}", session.get('user_id'),
                           {"filename": filename, "error": str(e)})
            
            # Delete the file after processing (성공/실패 여부와 관계없이)
            try:
                os.remove(file_path)
            except OSError as e: # 구체적인 에러 타입 명시
                # Error deleting uploaded file (ignored)
                log_access(f"업로드된 파일 삭제 오류: {file_path} - {e}", session.get('user_id'),
                           {"filename": file_path, "error": str(e)})

            return redirect(url_for('order_pages.index'))
        else:
            flash('허용되지 않은 파일 형식입니다. .xlsx 또는 .xls 파일만 업로드 가능합니다.', 'error')
            log_access(f"엑셀 업로드 실패: 허용되지 않은 파일 형식 - {file.filename}", session.get('user_id'),
                       {"filename": file.filename})
            return redirect(request.url)
    
    return render_template('upload.html')

@app.route('/download_excel')
@login_required
def download_excel():
    db = get_db()
    status_filter = request.args.get('status')
    search_query = request.args.get('search', '').strip()
    sort_column = request.args.get('sort', 'id') # 정렬 기준
    sort_direction = request.args.get('direction', 'desc') # 정렬 방향
    
    # 기본 쿼리 생성 (삭제되지 않은 주문만)
    query = db.query(Order).filter(Order.deleted_at.is_(None))
    
    # 상태 필터 적용
    if status_filter:
        # 접수 탭에서는 RECEIVED와 ON_HOLD 상태를 모두 표시
        if status_filter == 'RECEIVED':
            query = query.filter(Order.status.in_(['RECEIVED', 'ON_HOLD']))
        else:
            query = query.filter(Order.status == status_filter)
    
    # 검색어 필터 적용 (index 함수와 동일하게)
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter( 
            or_(
                Order.id.cast(String).like(search_term),  # integer 타입을 String으로 캐스팅
                Order.received_date.like(search_term),
                Order.received_time.like(search_term),
                Order.customer_name.like(search_term),
                Order.phone.like(search_term),
                Order.address.like(search_term),
                Order.product.like(search_term),
                Order.options.like(search_term),
                Order.notes.like(search_term),
                Order.status.like(search_term),
                Order.measurement_date.like(search_term),
                Order.measurement_time.like(search_term),
                Order.completion_date.like(search_term),
                Order.manager_name.like(search_term),
                # payment_amount는 숫자형이므로 캐스팅 필요
                func.cast(Order.payment_amount, String).like(search_term)
            )
        )

    # 컬럼별 입력 필터 적용 (index 함수와 동일한 로직으로 변경)
    filterable_columns = [
        'id', 'received_date', 'received_time', 'customer_name', 'phone', 
        'address', 'product', 'options', 'notes', 'status', 
        'measurement_date', 'measurement_time', 'completion_date', 'manager_name', 'payment_amount'
    ]
    for column_name in filterable_columns:
        filter_value = request.args.get(f'filter_{column_name}', '').strip() # get 대신 getlist 사용하지 않음
        if filter_value:
            if hasattr(Order, column_name):
                try:
                    column_attr = getattr(Order, column_name)
                    # 숫자 타입 컬럼일 경우 문자열로 캐스팅 후 LIKE 적용
                    if isinstance(column_attr.type.python_type(), (int, float)):
                         query = query.filter(column_attr.cast(String).like(f"%{filter_value}%"))
                    else:
                         query = query.filter(column_attr.like(f"%{filter_value}%"))
                except AttributeError:
                    # 컬럼이 없거나 LIKE 사용 불가 시 경고 (index 함수와 동일)
                    # Warning: Column not found or cannot be filtered with LIKE in download_excel
                    pass
            else:
                 # Warning: Column not found in Order model in download_excel
                 pass
                
    # 정렬 적용 (루프 바깥으로 이동)
    if hasattr(Order, sort_column):
        column_to_sort = getattr(Order, sort_column)
        if sort_direction == 'asc':
            query = query.order_by(column_to_sort.asc())
        else:
            query = query.order_by(column_to_sort.desc())
    else:
        query = query.order_by(Order.id.desc()) # 기본 정렬

    orders = query.all()
    
    # 다운로드할 주문 ID 목록
    downloaded_order_ids = [order.id for order in orders] if orders else []

    if not orders:
        flash('다운로드할 데이터가 없습니다.', 'warning')
        return redirect(request.referrer or url_for('order_pages.index'))
    
    # 데이터를 Pandas DataFrame으로 변환
    orders_data = []
    for order in orders:
        order_dict = order.to_dict()
        # 옵션을 한글로 변환하는 로직 추가
        order_dict['options'] = format_options_for_display(order.options) # 전역 함수 호출
        orders_data.append(order_dict)

    df = pd.DataFrame(orders_data)
    
    # 상태 코드를 한글 이름으로 변경
    if 'status' in df.columns:
        df['status'] = df['status'].map(STATUS).fillna(df['status'])
        
    # 필요한 컬럼 선택 및 순서 지정
    excel_columns = [
        'id', 'received_date', 'received_time', 'customer_name', 'phone', 'address', 
        'product', 'options', 'notes', 'payment_amount',
        'measurement_date', 'measurement_time', 'completion_date', 
        'manager_name', 'status'
    ]
    # DataFrame에 없는 컬럼이 excel_columns에 포함되어 있을 경우 KeyError 발생 방지
    df_excel_columns = [col for col in excel_columns if col in df.columns]
    df_excel = df[df_excel_columns]
    
    # 컬럼명 한글로 변경
    column_mapping_korean = {
        'id': '번호', 'received_date': '접수일', 'received_time': '접수시간', 
        'customer_name': '고객명', 'phone': '연락처', 'address': '주소', 
        'product': '제품', 'options': '옵션', 'notes': '비고', 
        'payment_amount': '결제금액', 'measurement_date': '실측일', 
        'measurement_time': '실측시간', 'completion_date': '설치완료일', 
        'manager_name': '담당자', 'status': '상태'
    }
    df_excel.rename(columns=column_mapping_korean, inplace=True)
    
    # 엑셀 파일 생성
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"furniture_orders_{timestamp}.xlsx"
    excel_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_filename)
    
    df_excel.to_excel(excel_path, index=False, engine='openpyxl')
    
    # 로그 기록
    log_access(f"엑셀 다운로드: {excel_filename}", session.get('user_id'))
    
    # 파일을 사용자에게 전송 (다운로드 후 서버에서 파일 삭제 옵션 추가 가능)
    return send_file(excel_path, as_attachment=True)

@app.route('/calendar')
@login_required
def calendar():
    return render_template('calendar.html')

@app.route('/wdplanner')
@login_required
def wdplanner():
    """WDPlanner - 붙박이장 3D 설계 프로그램 (FOMS 레이아웃 포함)"""
    # FOMS 레이아웃을 유지하면서 iframe으로 WDPlanner를 표시
    return render_template('wdplanner.html')

# WDPlanner 정적 파일 서빙 - Flask의 기본 static 폴더 활용
@app.route('/wdplanner/app/<path:filename>')
@login_required
def wdplanner_static(filename):
    """WDPlanner 정적 파일 서빙 (JS, CSS, assets 등)"""
    # static/wdplanner/ 경로에서 파일 서빙
    return send_from_directory('static/wdplanner', filename)

@app.route('/wdplanner/app')
@login_required
def wdplanner_app():
    """WDPlanner 앱 자체 (iframe 내부에서 로드)"""
    wdplanner_index = os.path.join('static', 'wdplanner', 'index.html')
    if os.path.exists(wdplanner_index):
        # index.html 파일을 직접 반환 (Content-Type 자동 설정)
        return send_from_directory('static/wdplanner', 'index.html')
    else:
        return render_template('wdplanner_setup.html')

@app.route('/map_view')
@login_required
def map_view():
    """지도 보기 페이지"""
    return render_template('map_view.html')


# calculate_route, address_suggestions, add_address_learning, validate_address -> erp_map_bp
# /api/orders (캘린더) -> orders_bp


def translate_dict_keys(d, key_map):
    if not isinstance(d, dict):
        return d
    new_dict = {}
    for k, v in d.items():
        translated_key = key_map.get(k, k)
        if isinstance(v, dict):
            new_dict[translated_key] = translate_dict_keys(v, key_map)
        elif isinstance(v, list):
            new_dict[translated_key] = [translate_dict_keys(item, key_map) for item in v]
        else:
            new_dict[translated_key] = v
    return new_dict

def format_value_for_log(value):
    if value is None:
        return "없음"
    if isinstance(value, str) and not value.strip(): # 빈 문자열
        return "없음"
    return str(value)

def load_menu_config():
    try:
        if os.path.exists('menu_config.json'):
            with open('menu_config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    # Default menu configuration
    return {
        'main_menu': [
            {'id': 'calendar', 'name': '캘린더', 'url': '/calendar'},
            {'id': 'order_list', 'name': '전체 주문', 'url': '/'},
            {'id': 'received', 'name': '접수', 'url': '/?status=RECEIVED'},
            {'id': 'measured', 'name': '실측', 'url': '/?status=MEASURED'},
            {'id': 'metro_orders', 'name': '수도권 주문', 'url': '/?region=metro'},
            {'id': 'regional_orders', 'name': '지방 주문', 'url': '/?region=regional'},
            {'id': 'storage_dashboard', 'name': '수납장 대시보드', 'url': '/storage_dashboard'},
            {'id': 'regional_dashboard', 'name': '지방 주문 대시보드', 'url': '/regional_dashboard'},
            {'id': 'self_measurement_dashboard', 'name': '자가실측 대시보드', 'url': '/self_measurement_dashboard'},
            {'id': 'metropolitan_dashboard', 'name': '수도권 주문 대시보드', 'url': '/metropolitan_dashboard'},
            {'id': 'trash', 'name': '휴지통', 'url': '/trash'},
            {'id': 'chat', 'name': '채팅', 'url': '/chat'}
        ],
        'admin_menu': [
            {'id': 'user_management', 'name': '사용자 관리', 'url': '/admin/users'},
            {'id': 'security_logs', 'name': '보안 로그', 'url': '/admin/security-logs'}
        ]
    }

@app.context_processor
def inject_menu():
    menu_config = load_menu_config()

    # ERP Beta: 실측/AS/출고는 ERP 대시보드 서브 내비로 이동 (메인 메뉴에는 추가하지 않음)

    return dict(menu=menu_config)

# Jinja 필터: 메시지 내 "주문 #<번호>"를 클릭 가능한 링크로 변환
@app.template_filter('order_link')
def order_link_filter(s):
    import re
    from flask import url_for
    def repl(m):
        oid = m.group(1)
        link = url_for('edit_order', order_id=oid)
        return Markup(f'<a href="{link}">주문 #{oid}</a>')
    return Markup(re.sub(r'주문 #(\d+)', repl, s))

# 도면 관리 API -> apps.api.erp_orders_blueprint
# ERP Structured/Draft API -> apps.api.erp_orders_structured

# /chat 페이지 및 SocketIO 핸들러는 apps.api.chat으로 이동됨

# Production: Auto-initialize Database Tables
# This runs when a WSGI server imports 'app' (e.g. gunicorn/uwsgi),
# and should not run for `python app.py` because __main__ has its own startup flow.
_should_run_auto_init = (__name__ != '__main__')
if _should_run_auto_init:
    try:
        with app.app_context():
            print("[AUTO-INIT] Checking database tables...")
            from db import init_db
            from wdcalculator_db import init_wdcalculator_db
            
            # Initialize Main DB
            init_db()
            ensure_order_attachments_category_column()
            ensure_order_attachments_item_index_column()
            
            # Initialize WDCalculator DB
            init_wdcalculator_db()
            
            print("[AUTO-INIT] Tables checked/created successfully.")
            
            # Check/Create Admin User
            from models import User
            from werkzeug.security import generate_password_hash
            db_session = get_db()
            try:
                admin = db_session.query(User).filter_by(username='admin').first()
                if not admin:
                    print("[AUTO-INIT] Creating default admin user (admin/admin1234)...")
                    new_admin = User(
                        username='admin',
                        password=generate_password_hash('admin1234'),
                        name='관리자',
                        role='ADMIN',
                        is_active=True
                    )
                    db_session.add(new_admin)
                    db_session.commit()
                else:
                    print("[AUTO-INIT] Admin user exists.")
            except Exception as e:
                print(f"[AUTO-INIT] Failed to create admin user: {e}")
                db_session.rollback()
                
    except Exception as e:
        print(f"[AUTO-INIT] Database initialization failed: {e}")

if __name__ == '__main__':
    _use_reloader = (os.environ.get('FLASK_USE_RELOADER', '1') == '1')
    _is_reloader_child = (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')
    _should_run_startup_tasks = (not _use_reloader) or _is_reloader_child

    # 안전한 시작 프로세스 실행 (SystemExit 방지)
    try:
        import logging
        import sys
        
        # 로깅 설정
        logging.basicConfig(
            level=logging.INFO, 
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('app_startup.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        logger = logging.getLogger('FOMS_Startup')

        if _should_run_startup_tasks:
            logger.info("[START] FOMS 애플리케이션 시작 중...")
            startup_success = True

            # 1. 데이터베이스 초기화 시도
            try:
                init_db()
                # get_db()를 사용하는 자동 컬럼 보정은 Flask 앱 컨텍스트 내에서 실행해야 한다.
                with app.app_context():
                    ensure_order_attachments_category_column()
                    ensure_order_attachments_item_index_column()
                logger.info("[OK] FOMS 데이터베이스 초기화 완료")
            except Exception as e:
                logger.error(f"[ERROR] FOMS 데이터베이스 초기화 실패: {str(e)}")
                startup_success = False

            # 1-1. 견적 계산기 독립 데이터베이스 초기화 시도
            try:
                with app.app_context():
                    init_wdcalculator_db()
                logger.info("[OK] 견적 계산기 데이터베이스 초기화 완료")
            except Exception as e:
                logger.warning(f"[WARN] 견적 계산기 데이터베이스 초기화 실패 (견적 기능 제한): {str(e)}")
                # 견적 계산기 DB 실패는 전체 시스템에 영향 없음

            # 2. 안전한 스키마 마이그레이션 시도
            try:
                from safe_schema_migration import run_safe_migration

                # Flask 앱 컨텍스트 내에서 마이그레이션 실행
                with app.app_context():
                    migration_success = run_safe_migration(app.app_context())
                    if migration_success:
                        logger.info("[OK] 스키마 마이그레이션 완료")
                    else:
                        logger.warning("[WARN] 스키마 마이그레이션 실패 - 기존 스키마로 계속 진행")
                        startup_success = False
            except Exception as e:
                logger.error(f"[ERROR] 스키마 마이그레이션 중 예외: {str(e)}")
                startup_success = False

            # 3. 시작 결과 요약
            if startup_success:
                logger.info("[SUCCESS] 모든 시작 프로세스가 성공적으로 완료되었습니다!")
                print("[OK] FOMS 시스템이 준비되었습니다!")
            else:
                logger.warning("[WARN] 일부 시작 프로세스에서 오류가 발생했지만 앱은 정상적으로 시작됩니다.")
                print("[WARN] 일부 기능에 제한이 있을 수 있습니다. 로그를 확인해주세요.")
        else:
            logger.info("[SKIP] 리로더 부모 프로세스에서는 시작 초기화를 건너뜁니다.")

        # 4. Flask 웹 서버 시작 (안전한 설정)
        if _should_run_startup_tasks:
            print("[START] 웹 서버를 시작합니다...")
            print(f"[INFO] SOCKETIO_AVAILABLE: {SOCKETIO_AVAILABLE}")
            print(f"[INFO] socketio 객체 존재: {socketio is not None}")

        if SOCKETIO_AVAILABLE and socketio:
            # SocketIO 사용 시 socketio.run() 사용
            if _should_run_startup_tasks:
                print("[INFO] Socket.IO 모드로 서버를 시작합니다...")
            socketio.run(
                app,
                host='0.0.0.0',
                port=5000,
                debug=True,
                use_reloader=_use_reloader,
                allow_unsafe_werkzeug=True,
            )
        else:
            # 일반 Flask 실행
            if _should_run_startup_tasks:
                print("[WARN] Socket.IO가 비활성화되어 일반 Flask 모드로 시작합니다...")
            app.run(
                host='0.0.0.0',
                port=5000,
                debug=True,
                use_reloader=_use_reloader,
            )
        
    except KeyboardInterrupt:
        print("\n[STOP] 사용자에 의해 서버가 중단되었습니다.")
    except Exception as e:
        print(f"[ERROR] 서버 시작 중 오류: {str(e)}")
        print("[INFO] 로그 파일(app_startup.log)을 확인해주세요.")
        # SystemExit 대신 정상 종료
    finally:
        if _should_run_startup_tasks:
            print("[END] FOMS 시스템을 종료합니다.")
