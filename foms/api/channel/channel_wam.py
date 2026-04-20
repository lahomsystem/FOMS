from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, make_response, redirect, render_template, request, url_for

from foms.services.channel_identity import get_user_by_manager_id
from foms.services.channel_security import (
    generate_wam_entry_token,
    generate_wam_session_token,
    verify_wam_entry_token,
    verify_wam_session_token,
    verify_wam_short_link_token,
)
from foms.services.channel_wam_attachments import (
    get_scoped_attachment,
    list_attachment_groups,
    resolve_attachment_redirect_url,
)
from foms.services.channel_wam_service import (
    build_legacy_wam_context,
    build_wam_bootstrap,
    build_wam_page,
    build_wam_request_context,
    get_wam_feature_flags,
)
from foms.services.channel_wam_telemetry import record_wam_telemetry

channel_wam_bp = Blueprint("channel_wam", __name__, url_prefix="/channel/wam")
channel_wam_api_bp = Blueprint("channel_wam_api", __name__, url_prefix="/channel/wam/api")
channel_shortlink_bp = Blueprint("channel_shortlink", __name__)

WAM_SESSION_COOKIE = "wam_session"
WAM_SESSION_MAX_AGE = 300


def _is_api_request() -> bool:
    return request.blueprint == "channel_wam_api"


def _wam_error(message: str, status_code: int, error_code: str):
    payload = {
        "ok": False,
        "error": {"code": error_code, "message": message},
        "error_code": error_code,
        "message": message,
        "status": status_code,
    }
    if _is_api_request():
        return jsonify(payload), status_code
    return render_template("channel/wam_error.html", message=message), status_code


def _ensure_wam_enabled():
    if not get_wam_feature_flags().get("wam_enabled", True):
        return _wam_error("WAM is disabled", 404, "wam_disabled")
    return None


def _ensure_attachments_enabled():
    if not get_wam_feature_flags().get("attachments_enabled", True):
        return _wam_error("Attachments are disabled", 404, "attachments_disabled")
    return None


def _ensure_telemetry_enabled():
    if not get_wam_feature_flags().get("telemetry_enabled", False):
        return _wam_error("Telemetry is disabled", 404, "telemetry_disabled")
    return None


def _apply_manager_binding(payload: dict):
    manager_id = payload.get("manager_id")
    if not manager_id or manager_id == "wam_viewer":
        payload["mapped_foms_user_id"] = None
        return None

    user = get_user_by_manager_id(str(manager_id))
    if not user:
        return _wam_error("Manager binding is not configured", 403, "manager_binding_missing")

    mapped_foms_user_id = payload.get("mapped_foms_user_id")
    if mapped_foms_user_id not in (None, user.id):
        return _wam_error("Manager binding mismatch", 403, "manager_binding_mismatch")

    payload["mapped_foms_user_id"] = user.id
    return None


def _store_wam_context(payload: dict, request_token: str = ""):
    context = build_wam_request_context(payload, request_token)
    if not context:
        return _wam_error("Missing order_id", 400, "missing_order_id")

    request.wam_payload = payload
    g.wam_payload = payload
    g.wam_context = context
    return None


def _verify_html_request_token():
    session_token = request.cookies.get(WAM_SESSION_COOKIE)
    entry_ticket = request.args.get("entry_ticket")

    g.wam_session_token = None
    g.wam_should_clean_redirect = False

    if session_token:
        payload = verify_wam_session_token(session_token)
        if not payload:
            return _wam_error("Invalid or expired session token", 401, "invalid_session_token")
    elif entry_ticket:
        payload = verify_wam_entry_token(entry_ticket)
        if not payload:
            return _wam_error("Invalid or expired entry ticket", 401, "invalid_entry_ticket")

        binding_error = _apply_manager_binding(payload)
        if binding_error:
            return binding_error

        session_token = generate_wam_session_token(
            payload.get("manager_id") or "wam_viewer",
            int(payload.get("order_id")),
            scopes=payload.get("scopes"),
            allowed_sections=payload.get("allowed_sections"),
            attachment_scope=payload.get("attachment_scope"),
            mapped_foms_user_id=payload.get("mapped_foms_user_id"),
        )
        session_payload = verify_wam_session_token(session_token)
        if not session_payload:
            return _wam_error("Failed to issue session ticket", 500, "session_issue_failed")
        payload = session_payload
        g.wam_session_token = session_token
        g.wam_should_clean_redirect = True
    else:
        return _wam_error("Missing entry_ticket", 401, "missing_entry_ticket")

    binding_error = _apply_manager_binding(payload)
    if binding_error:
        return binding_error

    return _store_wam_context(payload)


def _verify_api_request_token():
    session_token = request.cookies.get(WAM_SESSION_COOKIE)
    if not session_token:
        return _wam_error("Missing session ticket", 401, "missing_session_token")

    payload = verify_wam_session_token(session_token)
    if not payload:
        return _wam_error("Invalid or expired session token", 401, "invalid_session_token")

    binding_error = _apply_manager_binding(payload)
    if binding_error:
        return binding_error

    return _store_wam_context(payload)


@channel_wam_bp.before_request
def verify_wam_html_token():
    gate_error = _ensure_wam_enabled()
    if gate_error:
        return gate_error
    return _verify_html_request_token()


@channel_wam_api_bp.before_request
def verify_wam_api_token():
    gate_error = _ensure_wam_enabled()
    if gate_error:
        return gate_error
    return _verify_api_request_token()


def _require_wam_scope(scope: str):
    context = getattr(g, "wam_context", None)
    if not context or not context.allows(scope):
        return _wam_error("Forbidden", 403, "forbidden")
    return None


def _resolve_html_template() -> str:
    if not get_wam_feature_flags().get("wam_v2", True):
        return "channel/wam_index.html"
    return "channel/wam/index.html"


def _set_session_cookie(response):
    if not g.get("wam_session_token"):
        return response

    response.set_cookie(
        WAM_SESSION_COOKIE,
        g.wam_session_token,
        max_age=WAM_SESSION_MAX_AGE,
        httponly=True,
        secure=not current_app.config.get("TESTING", False),
        samesite="Lax",
        path="/channel/wam",
    )
    return response


@channel_wam_bp.route("/")
def wam_index():
    scope_error = _require_wam_scope("page")
    if scope_error:
        return scope_error

    if g.get("wam_should_clean_redirect"):
        response = make_response(redirect(url_for("channel_wam.wam_index")))
        return _set_session_cookie(response)

    context = g.wam_context
    flags = get_wam_feature_flags()

    if not flags.get("wam_v2", True):
        legacy_context = build_legacy_wam_context(context)
        if not legacy_context:
            return _wam_error("Order not found", 404, "order_not_found")
        response = make_response(render_template(_resolve_html_template(), **legacy_context))
        return _set_session_cookie(response)

    page_vm = build_wam_page(context)
    if not page_vm:
        return _wam_error("Order not found", 404, "order_not_found")

    response = make_response(
        render_template(
            _resolve_html_template(),
            page_vm=page_vm.to_dict(),
            bootstrap_payload=build_wam_bootstrap(context, page_vm),
            flags=page_vm.flags,
        )
    )
    return _set_session_cookie(response)


@channel_wam_api_bp.route("/bootstrap")
def wam_bootstrap():
    scope_error = _require_wam_scope("page")
    if scope_error:
        return scope_error

    page_vm = build_wam_page(g.wam_context)
    if not page_vm:
        return _wam_error("Order not found", 404, "order_not_found")
    return jsonify(build_wam_bootstrap(g.wam_context, page_vm))


@channel_wam_api_bp.route("/telemetry", methods=["POST"])
def wam_telemetry():
    scope_error = _require_wam_scope("page")
    if scope_error:
        return scope_error

    gate_error = _ensure_telemetry_enabled()
    if gate_error:
        return gate_error

    payload = request.get_json(silent=True) or {}
    event_name = payload.get("event_name") or payload.get("eventName")
    if not event_name:
        return jsonify({"ok": False, "error_code": "missing_event_name"}), 400

    record_wam_telemetry(g.wam_context, str(event_name), payload)
    return "", 204


@channel_wam_api_bp.route("/attachments")
def wam_attachments():
    attachments_gate_error = _ensure_attachments_enabled()
    if attachments_gate_error:
        return attachments_gate_error

    scope_error = _require_wam_scope("attachments")
    if scope_error:
        return scope_error

    groups = list_attachment_groups(g.wam_context)
    serialized_groups = []
    total_count = 0

    for group in groups:
        group_dict = group.to_dict()
        preview = [
            {
                "id": item["id"],
                "label": item["name"],
                "name": item["name"],
                "kind_label": "IMAGE" if item["file_type"] == "image" else "FILE",
                "file_type": item["file_type"],
                "category": item["category_label"],
                "open_url": item["open_url"],
                "download_url": item["download_url"],
                "thumbnail_url": item.get("thumbnail_url"),
            }
            for item in group_dict.get("preview_items") or []
        ]
        items = [
            {
                "id": item["id"],
                "label": item["name"],
                "name": item["name"],
                "file_type": item["file_type"],
                "category": item["category_label"],
                "open_url": item["open_url"],
                "download_url": item["download_url"],
                "thumbnail_url": item.get("thumbnail_url"),
                "url": item["open_url"],
            }
            for item in group_dict.get("items") or []
        ]
        total_count += group_dict.get("count", 0)
        serialized_groups.append(
            {
                "key": group_dict.get("key"),
                "title": group_dict.get("title"),
                "label": group_dict.get("title"),
                "count": group_dict.get("count", 0),
                "preview": preview,
                "items": items,
            }
        )

    return jsonify(
        {
            "ok": True,
            "order_id": g.wam_context.order_id,
            "groups": serialized_groups,
            "total_count": total_count,
        }
    )


@channel_wam_api_bp.route("/attachments/<int:attachment_id>/open")
def wam_attachment_open(attachment_id: int):
    attachments_gate_error = _ensure_attachments_enabled()
    if attachments_gate_error:
        return attachments_gate_error

    scope_error = _require_wam_scope("attachments")
    if scope_error:
        return scope_error

    if not get_scoped_attachment(g.wam_context, attachment_id):
        return _wam_error("Attachment not found", 404, "attachment_not_found")

    redirect_url = resolve_attachment_redirect_url(g.wam_context, attachment_id, "open")
    if not redirect_url:
        return _wam_error("Attachment URL is unavailable", 404, "attachment_not_found")
    return redirect(redirect_url)


@channel_wam_api_bp.route("/attachments/<int:attachment_id>/download")
def wam_attachment_download(attachment_id: int):
    attachments_gate_error = _ensure_attachments_enabled()
    if attachments_gate_error:
        return attachments_gate_error

    scope_error = _require_wam_scope("attachments")
    if scope_error:
        return scope_error

    if not get_scoped_attachment(g.wam_context, attachment_id):
        return _wam_error("Attachment not found", 404, "attachment_not_found")

    redirect_url = resolve_attachment_redirect_url(g.wam_context, attachment_id, "download")
    if not redirect_url:
        return _wam_error("Attachment URL is unavailable", 404, "attachment_not_found")
    return redirect(redirect_url)


@channel_shortlink_bp.route("/w/<token>")
def redirect_short_wam_link(token):
    gate_error = _ensure_wam_enabled()
    if gate_error:
        return gate_error

    payload = verify_wam_short_link_token(token)
    if not payload:
        return render_template("channel/wam_error.html", message="Invalid or expired link"), 401

    binding_error = _apply_manager_binding(payload)
    if binding_error:
        return binding_error

    entry_ticket = generate_wam_entry_token(
        payload.get("manager_id") or "wam_viewer",
        int(payload["order_id"]),
        scopes=payload.get("scopes"),
        allowed_sections=payload.get("allowed_sections"),
        attachment_scope=payload.get("attachment_scope"),
        mapped_foms_user_id=payload.get("mapped_foms_user_id"),
    )
    return redirect(url_for("channel_wam.wam_index", entry_ticket=entry_ticket))
