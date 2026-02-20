import warnings
# warnings.filterwarnings("ignore", category=DeprecationWarning, module="eventlet")
# import eventlet
# eventlet.monkey_patch()
import os
import hashlib
import datetime
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, g, session, send_from_directory, current_app
from flask_compress import Compress
from whitenoise import WhiteNoise
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

# ProxyFix: Railway/Reverse Proxy 뒤에서만 적용 (직접 접속 시 ERR_TOO_MANY_REDIRECTS 방지)
# - LAN IP(172.30.x.x) 또는 localhost 직접 접속 시 X-Forwarded-* 헤더 오염으로 리다이렉트 루프 발생
# - TRUST_PROXY=1 또는 FLASK_ENV=production 일 때만 활성화
_trust_proxy = os.environ.get('TRUST_PROXY', '').lower() in ('1', 'true', 'yes')
if _trust_proxy or _is_production:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Import Apps Blueprints
from apps.auth import auth_bp, login_required, role_required, ROLES, TEAMS, log_access, get_user_by_id
app.register_blueprint(auth_bp)

# ERP Beta Blueprint
from apps.erp import erp_bp, apply_erp_display_fields_to_orders
from services.erp_permissions import can_edit_erp
app.register_blueprint(erp_bp)
from apps.erp_dashboard import erp_dashboard_bp
app.register_blueprint(erp_dashboard_bp)
from apps.erp_drawing_workbench import erp_drawing_workbench_bp
app.register_blueprint(erp_drawing_workbench_bp)
from apps.erp_measurement_dashboard import erp_measurement_dashboard_bp
app.register_blueprint(erp_measurement_dashboard_bp)
from apps.erp_shipment_page import erp_shipment_page_bp
app.register_blueprint(erp_shipment_page_bp)
from apps.erp_as_page import erp_as_page_bp
app.register_blueprint(erp_as_page_bp)
from apps.erp_production_page import erp_production_page_bp
app.register_blueprint(erp_production_page_bp)
from apps.erp_construction_page import erp_construction_page_bp
app.register_blueprint(erp_construction_page_bp)

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
from apps.order_edit import order_edit_bp
app.register_blueprint(order_edit_bp)
from apps.order_trash import order_trash_bp
app.register_blueprint(order_trash_bp)
from apps.excel_import import excel_bp
app.register_blueprint(excel_bp)
from apps.calendar_page import calendar_bp
app.register_blueprint(calendar_bp)
from apps.wdplanner_page import wdplanner_bp
app.register_blueprint(wdplanner_bp)
from apps.api.debug import debug_bp
app.register_blueprint(debug_bp)

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

# Security & Scalability (Quest 14): Rate Limiter → services/rate_limit.py (Railway 배포 시 config 미포함 대비)
redis_url = os.environ.get('REDIS_URL')
from services.rate_limit import init_limiter
limiter = init_limiter(app)

# SocketIO Initialization with Redis & CORS Control
# Use threading mode for Windows WebSocket support & Stability
socketio = None
if SOCKETIO_AVAILABLE:
    try:
        from flask_socketio import SocketIO as _SocketIO
        # CORS 도메인 제한 (환경변수 없으면 모든 도메인 허용 - 개발 편의성)
        allowed_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '*').split(',')
        
        # Redis가 설정되어 있으면 Message Queue로 사용 (Scale-out 지원)
        if redis_url:
            print(f"[INFO] Socket.IO connecting to Redis Message Queue: {redis_url}")
            socketio = _SocketIO(
                app,
                cors_allowed_origins=allowed_origins,
                async_mode='threading',
                message_queue=redis_url
            )
            print("[INFO] Socket.IO initialized in threading mode with Redis.")
        else:
            print("[WARN] REDIS_URL not found. Socket.IO running in single-worker mode (Memory).")
            socketio = _SocketIO(
                app,
                cors_allowed_origins=allowed_origins,
                async_mode='threading'
            )
            print("[INFO] Socket.IO initialized in threading mode (Universal Stable).")

    except Exception as e:
        # fallback
        print(f"[WARN] Socket.IO init failed: {e}")
        from flask_socketio import SocketIO as _SocketIO
        socketio = _SocketIO(app, cors_allowed_origins="*", async_mode='threading')

if SOCKETIO_AVAILABLE and socketio:
    register_chat_socketio_handlers(socketio)
    app.config['SOCKETIO_AVAILABLE'] = True
    app.config['_SOCKETIO_INSTANCE'] = socketio
else:
    app.config['SOCKETIO_AVAILABLE'] = False
    app.config['_SOCKETIO_INSTANCE'] = None

# (선택) SOCKETIO_CLIENT_ENABLED=true 시 클라이언트 강제 허용. 기본은 SOCKETIO_AVAILABLE 따라감(로컬 socketio.run / 원격 gunicorn gevent)
app.config['SOCKETIO_CLIENT_ENABLED'] = (
    os.environ.get('SOCKETIO_CLIENT_ENABLED', '').lower() in ('true', '1', 'yes')
)

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
# allowed_file, allowed_erp_media_file → services/file_utils.py

# Context processors → services/context_processors.py
from services.context_processors import register_context_processors
register_context_processors(app)

# Routes
@app.route('/favicon.ico')
def favicon():
    """favicon 요청 처리 (404 방지)"""
    return '', 204  # No Content

# WSGI 기동 시 DB 자동 초기화 (gunicorn 등). python app.py 시에는 run.py에서 처리
if __name__ != '__main__':
    from services.app_init import run_auto_init
    run_auto_init(app)

if __name__ == '__main__':
    from run import main
    main()
