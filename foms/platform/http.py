"""HTTP/bootstrap helpers for the root Flask app entrypoint."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Callable

from werkzeug.exceptions import HTTPException

from db import get_db
from foms.services.datetime_kst import get_today_kst
from foms.services.error_logging import install_protected_logging
from foms.services.user_activity import touch_last_seen

from flask import Flask, current_app, g, jsonify, redirect, request, session, url_for

# Fixed, non-leaking message for any unexpected 500 (API-ERROR-01 / P1-28).
_INTERNAL_ERROR_MESSAGE = "요청을 처리하는 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."


def _current_request_id() -> str:
    """Return this request's id, assigning one if the before_request hook missed it."""
    rid = getattr(g, "request_id", None)
    if not rid:
        rid = uuid.uuid4().hex
        g.request_id = rid
    return rid


def _contained_error_payload(request_id: str) -> dict[str, Any]:
    """Build the safe INTERNAL_ERROR JSON body (no str(e)/traceback/path/SQL).

    A top-level ``message`` is kept for backward compatibility with existing
    frontend code that reads ``data.message`` on failure.
    """
    return {
        "success": False,
        "message": _INTERNAL_ERROR_MESSAGE,
        "error": {
            "code": "INTERNAL_ERROR",
            "message": _INTERNAL_ERROR_MESSAGE,
            "request_id": request_id,
        },
    }


def _wants_json() -> bool:
    """Whether the current request should receive a JSON (vs HTML) error."""
    path = request.path or ""
    if path.startswith("/api") or "/api/" in path or path.startswith("/erp/api"):
        return True
    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.accept_mimetypes
    return accept["application/json"] > 0 and accept["application/json"] >= accept["text/html"]

# Inline HTML for global 404/500 (spec: no templates/errors or templates/partials/http_errors).
_INLINE_ERROR_THEME_SCRIPT = """<script>(function(){try{var k='foms-theme',s=localStorage.getItem(k),d=(s==='dark'||(s!=='light'&&window.matchMedia('(prefers-color-scheme:dark)').matches));if(d){document.documentElement.setAttribute('data-theme','dark');document.documentElement.style.colorScheme='dark';}}catch(e){}})();</script>"""

_INLINE_ERROR_STYLE = """
        :root {
            --err-page-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --err-card-bg: #ffffff;
            --err-code: #667eea;
            --err-title: #333333;
            --err-body: #666666;
            --err-btn: #667eea;
            --err-btn-hover: #5568d3;
            --err-btn-text: #ffffff;
        }

        [data-theme='dark'] {
            --err-page-bg: #0a0c10;
            --err-card-bg: #14171c;
            --err-code: #7882f0;
            --err-title: #f7f8fa;
            --err-body: #9aa3af;
            --err-btn: #5a67d8;
            --err-btn-hover: #7882f0;
            --err-btn-text: #ffffff;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: var(--err-page-bg);
            color: var(--err-title);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }

        .error-container {
            background: var(--err-card-bg);
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            text-align: center;
            max-width: 500px;
        }

        .error-code {
            font-size: 72px;
            font-weight: bold;
            color: var(--err-code);
            margin: 0;
        }

        .error-message {
            font-size: 24px;
            color: var(--err-title);
            margin: 10px 0 20px;
        }

        .error-description {
            color: var(--err-body);
            margin-bottom: 30px;
            line-height: 1.6;
        }

        .btn-home {
            display: inline-block;
            padding: 12px 30px;
            background: var(--err-btn);
            color: var(--err-btn-text);
            text-decoration: none;
            border-radius: 6px;
            transition: background 0.3s;
        }

        .btn-home:hover {
            background: var(--err-btn-hover);
        }
"""

_INLINE_HTML_404 = f"""<!DOCTYPE html>
<html lang="ko">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>페이지를 찾을 수 없습니다 - FOMS</title>
    {_INLINE_ERROR_THEME_SCRIPT}
    <style>{_INLINE_ERROR_STYLE}
    </style>
</head>

<body>
    <div class="error-container">
        <h1 class="error-code">404</h1>
        <h2 class="error-message">페이지를 찾을 수 없습니다</h2>
        <p class="error-description">
            요청하신 페이지가 삭제되었거나, 잘못된 주소입니다.<br>
            입력하신 주소가 정확한지 다시 한번 확인해 주세요.
        </p>
        <a href="/" class="btn-home">홈으로 돌아가기</a>
    </div>
</body>

</html>"""

_INLINE_HTML_500 = f"""<!DOCTYPE html>
<html lang="ko">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>서버 오류 - FOMS</title>
    {_INLINE_ERROR_THEME_SCRIPT}
    <style>{_INLINE_ERROR_STYLE}
    </style>
</head>

<body>
    <div class="error-container">
        <h1 class="error-code">500</h1>
        <h2 class="error-message">서버 오류가 발생했습니다</h2>
        <p class="error-description">
            죄송합니다. 요청을 처리하는 중 문제가 발생했습니다.<br>
            잠시 후 다시 시도해 주세요.
        </p>
        <a href="/" class="btn-home">홈으로 돌아가기</a>
    </div>
</body>

</html>"""


def register_http_bootstrap(
    app: Flask,
    *,
    get_user_by_id: Callable[..., Any],
    is_production: bool,
    close_db: Callable[..., Any],
    close_wdcalculator_db: Callable[..., Any],
    register_context_processors: Callable[[Flask], None],
) -> None:
    """Register app-wide request hooks, routes, handlers, and teardown wiring."""

    install_protected_logging(app)

    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = uuid.uuid4().hex

    @app.before_request
    def _record_request_start() -> None:
        g._request_start = time.perf_counter()

    @app.before_request
    def _set_current_user() -> None:
        g.current_user = None
        user_id = session.get("user_id")
        if user_id:
            session.permanent = True
            g.current_user = get_user_by_id(user_id)

    @app.before_request
    def _touch_last_seen() -> None:
        """Keep `User.last_login` following the user's real activity (LAST-SEEN-01).

        Sessions are permanent and refresh on every request, so the login route
        alone leaves the admin user list months stale. Writes are throttled per
        session, and static assets never trigger one.
        """
        path = request.path or ""
        if path.startswith("/static/") or request.method == "OPTIONS":
            return
        user = getattr(g, "current_user", None)
        if user is None:
            return
        touch_last_seen(get_db(), user)

    @app.before_request
    def _erp_construction_team_restrict() -> Any | None:
        """Restrict construction-team access to shipment/construction dashboards.

        이 가드는 **페이지 이동 제한**이지 인가 경계가 아니다 — API 네임스페이스는 제외한다.
        ``/api``·``/erp/api`` 는 권한 실패도 302 가 아니라 403 JSON 이어야 한다는 불변식이
        이미 있고(P1-13/P1-18, :func:`~foms.services.orders.order_mutation_policy` 참조),
        여기서 302 를 돌려주면 fetch 가 HTML 로그인/대시보드 문서를 받아 ``JSON.parse`` 로
        죽는다. 실제로 CONSTRUCTION 팀은 벨 알림 목록·배지·읽음처리와 **웹 푸시 구독**
        (``/erp/api/notifications/push/subscribe``)이 전부 이 302 에 막혀 무음이었다.
        각 엔드포인트는 자체 권한 가드를 그대로 유지한다(send·users/list=ADMIN/MANAGER 403,
        urgent-*=``user_can_read_order``, notifications=본인 ``user_states`` scope).
        """
        path = (request.path or "").strip()
        if (
            path.startswith("/static/")
            or path.startswith("/login")
            or path.startswith("/logout")
            or path.startswith("/register")
            or path.startswith("/api/")
            or path.startswith("/erp/api/")
        ):
            return None
        user = getattr(g, "current_user", None)
        if not user or getattr(user, "team", None) != "CONSTRUCTION":
            return None
        if (
            path.startswith("/erp/shipment")
            or path.startswith("/erp/construction")
            or path.startswith("/erp/completion")
            or path.startswith("/erp/history")
        ):
            return None
        if path.startswith("/erp/"):
            return redirect(
                url_for(
                    "erp_shipment_page.erp_shipment_dashboard",
                    date=get_today_kst().strftime("%Y-%m-%d"),
                )
            )
        if (
            path == "/"
            or path.startswith("/?")
            or path.startswith("/trash")
            or path.startswith("/wdcalculator")
            or path.startswith("/storage_dashboard")
            or path.startswith("/regional_dashboard")
            or path.startswith("/self_measurement_dashboard")
            or path.startswith("/metropolitan_dashboard")
            or path.startswith("/admin")
        ):
            return redirect(
                url_for(
                    "erp_shipment_page.erp_shipment_dashboard",
                    date=get_today_kst().strftime("%Y-%m-%d"),
                )
            )
        return None

    @app.after_request
    def _contain_error_responses(response: Any) -> Any:
        """Attach X-Request-ID and scrub any JSON 500 body at the boundary.

        This is the single choke point that neutralises the P1-28 leak: every
        handler that returns ``str(e)`` in a 500 body (handled or not) is
        replaced here with the fixed INTERNAL_ERROR payload. Domain 4xx and
        non-JSON responses are untouched, so expected mappings are preserved.
        """
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers.setdefault("X-Request-ID", rid)
        if (
            response.status_code == 500
            and response.mimetype == "application/json"
            and not response.direct_passthrough
        ):
            payload = _contained_error_payload(rid or _current_request_id())
            response.set_data(json.dumps(payload, ensure_ascii=False))
        return response

    @app.after_request
    def _log_request_duration(response: Any) -> Any:
        if hasattr(g, "_request_start"):
            duration_ms = (time.perf_counter() - g._request_start) * 1000
            endpoint = request.endpoint or request.path
            if duration_ms > 400:
                current_app.logger.info(
                    "req_duration endpoint=%s duration_ms=%s status=%s",
                    endpoint,
                    int(duration_ms),
                    response.status_code,
                )
        return response

    def _handle_internal_error(error: Any) -> Any:
        """Log the unexpected exception once (protected, with stack) and return
        the contained response. Never exposes str(e)/traceback/path/SQL."""
        rid = _current_request_id()
        exc = getattr(error, "original_exception", None)
        current_app.logger.error(
            "unhandled exception request_id=%s endpoint=%s",
            rid,
            request.endpoint or request.path,
            exc_info=exc or True,
        )
        if _wants_json():
            response = jsonify(_contained_error_payload(rid))
            response.status_code = 500
            return response
        marker = '<a href="/" class="btn-home">홈으로 돌아가기</a>'
        html = _INLINE_HTML_500.replace(
            marker,
            f'{marker}\n        <p style="margin-top:16px;color:var(--err-body);'
            f'font-size:12px;">오류 코드: {rid}</p>',
        )
        return html, 500

    @app.errorhandler(500)
    def internal_error(error):
        return _handle_internal_error(error)

    @app.errorhandler(Exception)
    def unhandled_exception(error):
        # Preserve expected domain mappings (400/403/404/409/422, ...): let
        # Flask render the HTTPException as-is; only truly unexpected
        # (non-HTTP) exceptions get the contained 500 treatment.
        if isinstance(error, HTTPException):
            return error
        return _handle_internal_error(error)

    @app.errorhandler(404)
    def not_found_error(error):
        return _INLINE_HTML_404, 404

    @app.route("/favicon.ico")
    def favicon():
        """공용 favicon 자산을 반환한다."""
        return current_app.send_static_file("favicon.png")

    @app.get("/__build")
    def build_info():
        return jsonify(
            {
                "build": "20260215-uxfix-03",
                "cwd": os.getcwd(),
                "template": "templates/orders/layout.html+partials/shared/*",
            }
        )

    app.teardown_appcontext(close_db)
    app.teardown_appcontext(close_wdcalculator_db)
    register_context_processors(app)
