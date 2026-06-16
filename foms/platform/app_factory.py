"""Factory for composing the root Flask app without changing entry contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from datetime import timedelta

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
    if url.endswith("/manifest.json") or url.split("?", 1)[0].endswith("/manifest.json"):
        headers["Cache-Control"] = "no-cache"
        return
    if url.endswith(".css") or url.endswith(".js"):
        headers["Cache-Control"] = "no-cache"


def _versioned_static_cache_middleware(wsgi_app: Any) -> Any:
    """버전 쿼리(``?v=``)가 있는 css/js 응답에 한해 단기 max-age 캐시를 부여한다.

    WhiteNoise는 파일 단위로 헤더를 미리 계산하므로 요청 쿼리(``?v=``)를 보지 못한다.
    그래서 모든 css/js를 ``no-cache``로 둘 수밖에 없었고(``@import`` 미버전 sub-file
    보호), 그 결과 브라우저가 **매 네비게이션마다** css/js를 재검증(304)한다 →
    적은 web 워커에서 정적 요청 폭주 → 탭전환 지연.

    이 미들웨어는 요청 단계에서 ``?v=``가 붙은 css/js에 한해 응답의 ``Cache-Control``을
    ``max-age``로 바꾼다. 버전 URL은 배포 시 ``?v=``가 바뀌어 새 URL이 되므로
    (캐시 미스→즉시 최신) 캐시해도 안전하고, 짧은 max-age(1시간)로 "버전 누락" 시의
    staleness도 길게 가지 않게 bound한다. 미버전(@import 등)은 그대로 ``no-cache``.

    Args:
        wsgi_app: 감쌀 WSGI 앱(여기서는 WhiteNoise).
    """
    _CACHE_VALUE = "public, max-age=3600"

    def _app(environ: Any, start_response: Any) -> Any:
        path = (environ.get("PATH_INFO") or "")
        qs = (environ.get("QUERY_STRING") or "")
        is_versioned_css_js = (
            path.startswith("/static/")
            and (path.endswith(".css") or path.endswith(".js"))
            and ("v=" in qs)
        )
        if not is_versioned_css_js:
            return wsgi_app(environ, start_response)

        def _start_response(status: Any, headers: Any, exc_info: Any = None) -> Any:
            new_headers = [(k, v) for (k, v) in headers if k.lower() != "cache-control"]
            new_headers.append(("Cache-Control", _CACHE_VALUE))
            return start_response(status, new_headers, exc_info)

        return wsgi_app(environ, _start_response)

    return _app


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
    # 버전된(?v=) css/js는 매 네비게이션 재검증(304) 대신 단기 캐시 → 정적 요청 폭주 완화.
    app.wsgi_app = _versioned_static_cache_middleware(app.wsgi_app)

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

    session_days = int(os.environ.get("FOMS_SESSION_DAYS", "30") or "30")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=max(1, session_days))
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

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
