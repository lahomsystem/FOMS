"""HTTP/bootstrap helpers for the root Flask app entrypoint."""

from __future__ import annotations

import os
import time
from typing import Any, Callable

from foms.services.datetime_kst import get_today_kst

from flask import Flask, current_app, g, jsonify, redirect, request, session, url_for

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
    def _erp_construction_team_restrict() -> Any | None:
        """Restrict construction-team access to shipment/construction dashboards."""
        path = (request.path or "").strip()
        if (
            path.startswith("/static/")
            or path.startswith("/login")
            or path.startswith("/logout")
            or path.startswith("/register")
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

    @app.errorhandler(500)
    def internal_error(error):
        import traceback

        if app.debug or not is_production:
            return f"<pre>500 Error: {str(error)}\n\n{traceback.format_exc()}</pre>", 500

        app.logger.error(
            "Internal Server Error: %s\n%s",
            str(error),
            traceback.format_exc(),
        )
        return _INLINE_HTML_500, 500

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
