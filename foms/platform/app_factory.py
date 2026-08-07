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
from .logging_setup import configure_logging
from .realtime import init_realtime_bootstrap
from .sentry_setup import init_sentry
from .request_limits import FomsRequest, GLOBAL_BODY_CAP, register_request_limits

from foms.services.context_processors import register_context_processors
from foms.services.rate_limit import init_limiter
from foms.services.request_write_guard import register_write_guard
from foms.services.orders.order_mutation_policy import register_order_mutation_policy
from foms.services.security.signing.signing_keys import (
    install_rotating_session_interface,
    resolve_legacy_secret,
)


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


def apply_proxy_fix(app: Flask) -> None:
    """Trust exactly ``FOMS_TRUSTED_PROXY_HOPS`` ``X-Forwarded-For`` hops.

    ProxyFix rewrites ``request.remote_addr`` to the address recorded ``hops``
    positions from the *right* of ``X-Forwarded-For`` — i.e. the client IP that
    our own trusted edge proxy observed. Any left-most entries a client injects
    fall outside the trusted window and are ignored, so ``remote_addr`` (and the
    rate-limit key derived from it) cannot be spoofed by a forged header.

    Args:
        app: The Flask app whose WSGI stack is wrapped in place.

    Returns:
        None. ``app.wsgi_app`` is replaced with the ProxyFix-wrapped callable.

    The hop count is parameterized via the ``FOMS_TRUSTED_PROXY_HOPS`` env var
    (default ``1`` = single Railway edge proxy, preserving the prior ``x_for=1``).
    A non-integer value falls back to ``1``; negatives are floored to ``0``
    (trust no proxy). Only ``x_for`` is parameterized — ``x_proto``/``x_host``/
    ``x_prefix`` stay at ``1`` (proto/host trust is out of this packet's scope).

    MERGE-GATE: set ``FOMS_TRUSTED_PROXY_HOPS`` to the *measured* Railway
    proxy-chain hop count before merging. Shipping the default without confirming
    the real chain length risks trusting one hop too few (breaks legitimate
    client-IP resolution) or too many (re-opens the spoof this packet closes).
    """
    from werkzeug.middleware.proxy_fix import ProxyFix

    raw = os.environ.get("FOMS_TRUSTED_PROXY_HOPS", "1") or "1"
    try:
        hops = max(0, int(raw))
    except ValueError:
        hops = 1
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=1, x_host=1, x_prefix=1)


def build_app(*, socketio_available: bool) -> AppFactoryResult:
    """Build the root Flask app while preserving the existing runtime order."""
    # AUDIT-LOG T1: gunicorn 경로(app.py → build_app)에는 지금까지 로깅 설정이
    # 없어 INFO가 전량 소실됐다. 멱등이라 run.py 선호출/재초기화와 안전하게 겹친다.
    configure_logging()
    # AUDIT-LOG T10: SENTRY_DSN env가 있을 때만 초기화(없으면 sentry_sdk import조차
    # 하지 않는 완전 no-op). FlaskIntegration은 Flask 시그널에 붙으므로 앱 생성 전
    # 초기화로 충분하다.
    init_sentry()

    app = Flask("app")

    # ERP 셸 fragment 조건부 304(erp_shell_http.apply_erp_shell_fragment_headers)는
    # 압축 응답에서 Flask-Compress의 ETag 재작성("abc"→"abc:br")+조건부 재평가에
    # 의존한다. 이 값이 꺼지면 하트비트 304가 소리 없이 영구 200(641KB 재전송)으로
    # 퇴화하므로 명시 고정한다.
    app.config["COMPRESS_EVALUATE_CONDITIONAL_REQUEST"] = True
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

    # P0-22: deployed(Railway/production) 에서 SECRET_KEY 가 absent/known-default/short 이면
    # 하드코딩 fallback 없이 기동을 막는다. 비-deployed dev 만 dev key 를 허용한다.
    is_railway = bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    app.secret_key = resolve_legacy_secret(deployed=(is_production or is_railway))
    # SESSION-SIGNING-SECRET-01: 상태기계 기반 rotating session interface 배선. runtime 이
    # 아직 미engaged(FOMS_SIGNING_KEY_CURRENT 부재)이면 legacy raw-key 로 byte-identical 동작.
    install_rotating_session_interface(app)

    app.config["SESSION_COOKIE_NAME"] = "session_staging"
    if is_production or is_railway:
        app.config["SESSION_COOKIE_SECURE"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    session_days = int(os.environ.get("FOMS_SESSION_DAYS", "30") or "30")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=max(1, session_days))
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    trust_proxy = os.environ.get("TRUST_PROXY", "").lower() in ("1", "true", "yes")
    if trust_proxy or is_production:
        apply_proxy_fix(app)

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
    # REQUEST-LIMIT-01 (P1-31): global body ceiling 50 MiB + 256 KiB overhead
    # (was 500 MiB) plus per-route pre-parse caps and leak-free form parsing.
    app.config["MAX_CONTENT_LENGTH"] = GLOBAL_BODY_CAP
    app.request_class = FomsRequest
    register_request_limits(app)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    register_http_bootstrap(
        app,
        get_user_by_id=blueprint_bindings.get_user_by_id,
        is_production=is_production,
        close_db=close_db,
        close_wdcalculator_db=close_wdcalculator_db,
        register_context_processors=register_context_processors,
    )

    # WRITE-GUARD-01: 공용 CSRF+Origin before_request 가드 + csrf_token context processor.
    # (manifest 부재 시 여기서 loud fail — startup 차단.)
    register_write_guard(app)

    # AUTH-01: §2.1 권한 정책 before_request 가드 + policy_can template helper.
    # (URL-map manifest 부재 시 loud fail — startup 차단.)
    register_order_mutation_policy(app)

    return AppFactoryResult(app=app, socketio=realtime_bindings.socketio)
