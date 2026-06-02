"""Factory for composing the root Flask app without changing entry contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from flask import Flask
from flask_compress import Compress
from whitenoise import WhiteNoise

from foms.services.files.storage_paths import UPLOAD_FOLDER
from db import close_db
from wdcalculator_db import close_wdcalculator_db

from .blueprints import register_blueprints
from .http import register_http_bootstrap
from .realtime import init_realtime_bootstrap

from foms.services.context_processors import register_context_processors
from foms.services.rate_limit import init_limiter


@dataclass(frozen=True)
class AppFactoryResult:
    """Bundled runtime objects produced by the app factory."""

    app: Flask
    socketio: Any


def _add_static_response_headers(headers: Any, path: str, url: str) -> None:
    """Attach per-file headers to WhiteNoise-served static assets.

    Two concerns:

    1. PWA service worker (`/static/sw.js`) is registered with `scope: "/"` so it
       can control every ERP route, but its script lives under `/static/`. A
       browser only allows a scope above the script's own directory when the
       script response carries `Service-Worker-Allowed`. Without it the
       registration fails with "The path of the provided scope ('/') is not under
       the max scope allowed ('/static/')". Serving the header here is the
       spec-sanctioned fix and keeps the script URL (P2 gate) unchanged.

    2. Cache freshness. WhiteNoise serves every asset as 1-year immutable
       (`max_age`). That is correct only for content-addressed URLs, but FOMS
       CSS/JS are NOT hashed: top-level links carry a `?v=` query, yet the CSS
       files `@import` each other with plain unversioned URLs. So an edit to an
       `@import`-ed sub-file (or any unversioned asset) stays stranded in browser
       and service-worker caches for up to a year — deploys silently fail to
       apply. CSS/JS (and the SW controller) must revalidate instead. `no-cache`
       forces an ETag conditional request (304 when unchanged, so still cheap)
       while guaranteeing every deploy reaches clients. Images/fonts keep the
       long immutable cache.

    Args:
        headers: WSGI ``Headers`` instance for the outgoing static response.
        path: Absolute filesystem path of the asset (unused).
        url: Request URL path for the asset, e.g. ``/static/sw.js``.
    """
    if url == "/static/sw.js":
        headers["Service-Worker-Allowed"] = "/"
        headers["Cache-Control"] = "no-cache"
        return
    if url.endswith(".css") or url.endswith(".js"):
        headers["Cache-Control"] = "no-cache"


def build_app(*, socketio_available: bool) -> AppFactoryResult:
    """Build the root Flask app while preserving the existing runtime order."""
    app = Flask("app")

    Compress(app)

    is_production = (
        os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("RAILWAY_ENVIRONMENT") == "production"
    )
    app.wsgi_app = WhiteNoise(
        app.wsgi_app,
        root="static/",
        prefix="static/",
        autorefresh=not is_production,
        max_age=31536000 if is_production else 0,
        add_headers_function=_add_static_response_headers,
    )

    app.secret_key = os.environ.get("SECRET_KEY")
    if not app.secret_key:
        if is_production:
            raise ValueError("SECRET_KEY environment variable must be set in production!")
        app.secret_key = "dev-secret-key-CHANGE-IN-PRODUCTION"
        print(
            "[WARN] Using development secret key. Set SECRET_KEY environment variable for production!"
        )

    app.config["SESSION_COOKIE_NAME"] = "session_staging"
    is_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    if is_production or is_railway:
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    trust_proxy = os.environ.get("TRUST_PROXY", "").lower() in ("1", "true", "yes")
    if trust_proxy or is_production:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    blueprint_bindings = register_blueprints(app)

    realtime_bindings = init_realtime_bootstrap(
        app,
        redis_url=os.environ.get("REDIS_URL"),
        socketio_available=socketio_available,
        init_limiter=init_limiter,
        register_chat_socketio_handlers=blueprint_bindings.register_chat_socketio_handlers,
    )

    app.config["TEMPLATES_AUTO_RELOAD"] = not (is_production or is_railway)
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    register_http_bootstrap(
        app,
        get_user_by_id=blueprint_bindings.get_user_by_id,
        is_production=is_production,
        close_db=close_db,
        close_wdcalculator_db=close_wdcalculator_db,
        register_context_processors=register_context_processors,
    )

    return AppFactoryResult(app=app, socketio=realtime_bindings.socketio)
