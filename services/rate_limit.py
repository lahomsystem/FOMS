"""Rate limiter 설정 (app.py에서 분리, Railway 배포용 services 배치)."""
import hashlib
import os
from flask import request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def init_limiter(app):
    """Rate limiter 초기화 및 반환."""
    redis_url = os.environ.get('REDIS_URL')

    def rate_limit_key():
        try:
            uid = session.get('user_id')
            if uid:
                return f"user:{uid}"
        except Exception:
            pass
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

    return Limiter(
        rate_limit_key,
        app=app,
        storage_uri=redis_url or "memory://",
        default_limits=default_limits
    )
