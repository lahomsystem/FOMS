"""HTTP/bootstrap helpers for the root Flask app entrypoint."""

from __future__ import annotations

import os
import time
from datetime import date
from typing import Any, Callable

from flask import Flask, current_app, g, jsonify, redirect, render_template, request, session, url_for


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
        ):
            return None
        if path.startswith("/erp/"):
            return redirect(
                url_for(
                    "erp_shipment_page.erp_shipment_dashboard",
                    date=date.today().strftime("%Y-%m-%d"),
                )
            )
        if (
            path == "/"
            or path.startswith("/?")
            or path.startswith("/trash")
            or path.startswith("/wdplanner")
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
                    date=date.today().strftime("%Y-%m-%d"),
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
        return render_template("partials/http_errors/error_500.html"), 500

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("partials/http_errors/error_404.html"), 404

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
