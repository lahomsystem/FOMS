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
from apps.excel_import import excel_bp
app.register_blueprint(excel_bp)
from apps.calendar_page import calendar_bp
app.register_blueprint(calendar_bp)
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

# index, add_order, edit_order -> order_pages_bp
# upload, download_excel -> excel_bp
# calendar -> calendar_bp
# map_view -> erp_map_bp

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

# calculate_route, address_suggestions, add_address_learning, validate_address, map_view -> erp_map_bp
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
        link = url_for('order_pages.edit_order', order_id=oid)
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
