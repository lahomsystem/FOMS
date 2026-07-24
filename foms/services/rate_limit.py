"""Rate limiter setup helpers."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from flask import request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

__all__ = ["init_limiter"]


def init_limiter(app: Any) -> Limiter:
    """Initialize the Flask-Limiter instance for the current app."""
    redis_url = os.environ.get("REDIS_URL")

    def rate_limit_key() -> str:
        try:
            user_id = session.get("user_id")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

        try:
            cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
            raw_cookie = request.cookies.get(cookie_name, "").strip()
            if raw_cookie:
                cookie_hash = hashlib.sha1(raw_cookie.encode("utf-8")).hexdigest()[:16]
                return f"sess:{cookie_hash}"
        except Exception:
            pass

        # Canonical client IP only. request.remote_addr is set by ProxyFix from
        # exactly FOMS_TRUSTED_PROXY_HOPS trusted X-Forwarded-For hops (see
        # foms.platform.app_factory.apply_proxy_fix). Parsing the raw
        # X-Forwarded-For / X-Real-IP headers here would let a client spoof its
        # rate-limit key via the attacker-controlled left-most entry, so it is
        # deliberately not done.
        return get_remote_address()

    default_limits_raw = os.environ.get("FLASK_DEFAULT_RATE_LIMITS", "5000 per day,1200 per hour")
    default_limits = [value.strip() for value in default_limits_raw.split(",") if value.strip()]
    if not default_limits:
        default_limits = ["5000 per day", "1200 per hour"]

    # Fail open: a Redis outage must degrade to in-memory limiting, never 500s.
    storage_options = (
        {"socket_connect_timeout": 2, "socket_timeout": 2} if redis_url else {}
    )

    return Limiter(
        rate_limit_key,
        app=app,
        storage_uri=redis_url or "memory://",
        default_limits=default_limits,
        storage_options=storage_options,
        swallow_errors=True,
        in_memory_fallback_enabled=True,
    )
