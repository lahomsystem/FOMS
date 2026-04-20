import os

# Gunicorn / Gevent 구동 시 IO 함수(socket 등)가 worker thread를 블로킹하지 않도록 몽키 패치 적용
if os.environ.get('SERVER_SOFTWARE', '').startswith('gunicorn') or os.environ.get('GUNICORN_CMD_ARGS'):
    try:
        import gevent.monkey  # type: ignore[import-untyped]
        _ = gevent.monkey.patch_all()
        try:
            import psycogreen.gevent  # type: ignore[import-untyped]
            psycogreen.gevent.patch_psycopg()
            print("[INFO] psycogreen patch 적용 완료 (PostgreSQL 비동기 활성화)")
        except ImportError:
            print("[WARN] psycogreen not installed. PostgreSQL queries may block gevent workers.")
        print("[INFO] gevent monkey patch 적용 완료 (비동기 IO 활성화)")
    except ImportError:
        print("[WARN] gevent not installed. Gunicorn gevent worker patches were not applied.")

import sys
import hashlib
from werkzeug import security as _werkzeug_security

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

from foms.platform.app_factory import build_app
from foms.services.context_processors import register_context_processors
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_policy import (
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
from foms.services.rate_limit import init_limiter
from foms.services.storage import get_storage

# SocketIO Import (Quest 5)
_socketio_available: bool = False
try:
    import flask_socketio as _flask_socketio  # noqa: F401

    _socketio_available = True
except ImportError:
    print("[WARN] Flask-SocketIO not installed. pip install flask-socketio python-socketio eventlet")

SOCKETIO_AVAILABLE = _socketio_available

_app_factory_result = build_app(socketio_available=SOCKETIO_AVAILABLE)
app = _app_factory_result.app
socketio = _app_factory_result.socketio

# WSGI 기동 시 DB 자동 초기화 (gunicorn 등). python app.py 시에는 run.py에서 처리
if __name__ != '__main__':
    from foms.services.app_init import run_auto_init
    run_auto_init(app)

if __name__ == '__main__':
    from run import main
    main()
