"""HTMX HTML fragments for P1 new surfaces (P2-01). Does not alter erp-shell.js swap flow."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, make_response, render_template, request, session

from db import get_db
from models import Order
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_permissions import can_edit_erp
from foms.services.order_edit_view_context import build_order_edit_get_context
from foms.services.request_utils import get_preserved_filter_args
from foms.web.auth import get_user_by_id, login_required, role_required

foms_fragment_bp = Blueprint("foms_fragment", __name__, url_prefix="/api/foms/fragment")


def _order_edit_fragment_response(order_id: int) -> Any:
    """
    Render edit-order body HTML for tablet split HTMX swap.

    Args:
        order_id: Primary key of the order row.

    Returns:
        Flask response with HTML fragment and no-store cache headers.
    """
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.not_deleted_filter()).first()
    if order is None:
        abort(404)

    if is_erp_order_record(order):
        user = get_user_by_id(session.get("user_id"))
        if not can_edit_erp(user):
            abort(403)

    ctx = build_order_edit_get_context(order)
    ctx["preserved_args"] = get_preserved_filter_args(request.args)
    body = render_template(
        "partials/shared/foms_order_detail_fragment.html",
        **ctx,
    )
    response = make_response(body)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-FOMS-Fragment"] = "1"
    return response


@foms_fragment_bp.route("/order/<int:order_id>/edit", methods=["GET"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def order_edit_fragment(order_id: int) -> Any:
    """HTMX fragment: order edit body for tablet split-view detail pane."""
    return _order_edit_fragment_response(order_id)
