"""Internal order views: partner preference, SQL scope and lazy header menu."""
from __future__ import annotations

from typing import Any

from flask import g, request, url_for
from sqlalchemy import true

from db import get_db
from models import Order, PartnerOrg

PARTNER_FILTER_KEY = "partner_org"
PARTNER_FILTER_COOKIE = "foms_partner_org"
PARTNER_FILTER_PATHS = frozenset({"/", "/erp/dashboard", "/erp/dashboard/", "/erp/history/"})


def partner_filter_value(req: Any) -> str:
    """Resolve query before cookie; return empty, all, a positive ID or -1 (invalid)."""
    raw = str(req.args.get(PARTNER_FILTER_KEY, req.cookies.get(PARTNER_FILTER_COOKIE, ""))).strip()
    if raw in ("", "all"):
        return raw
    try:
        value = int(raw)
    except ValueError:
        return "-1"
    return str(value) if 0 < value <= 2147483647 else "-1"


def partner_order_clause(value: str) -> Any:
    """Return the partner FK predicate for a normalized selection (empty means all orders)."""
    if not value:
        return true()
    if value == "all":
        return Order.partner_org_id.isnot(None)
    return Order.partner_org_id == int(value)


def partner_filter_args(req: Any) -> dict[str, str]:
    """Return explicit navigation arguments, including an explicit preference opt-out."""
    value = partner_filter_value(req)
    return {PARTNER_FILTER_KEY: value} if value or PARTNER_FILTER_KEY in req.args else {}


def persist_partner_filter(response: Any) -> Any:
    """Persist an explicit preference after an authenticated successful supported GET."""
    user = getattr(g, "current_user", None)
    if (request.method != "GET" or request.path not in PARTNER_FILTER_PATHS
            or PARTNER_FILTER_KEY not in request.args or not user
            or str(getattr(user, "role", "")).upper() == "PARTNER"
            or not 200 <= response.status_code < 400):
        return response
    value = partner_filter_value(request)
    response.set_cookie(PARTNER_FILTER_COOKIE, value, max_age=2592000 if value else 0,
                        httponly=True, secure=request.is_secure, samesite="Lax", path="/")
    return response


def partner_filter_menu() -> dict[str, Any]:
    """Load the small organization menu only when a full authenticated header renders."""
    selected = partner_filter_value(request)
    orgs = get_db().query(PartnerOrg.id, PartnerOrg.name).order_by(PartnerOrg.name).all()
    choices = [("", "전체 주문"), ("all", "협력사 전체")]
    choices.extend((str(org.id), org.name) for org in orgs)
    label = dict(choices).get(selected, "없는 협력사")
    supported = request.path in PARTNER_FILTER_PATHS
    endpoint = request.endpoint if supported else "erp_dashboard.erp_dashboard"
    args = request.args.to_dict() if supported else {}
    for key in ("page", "order", "focus_order", "view", "mobile_chunk", "from_history", "from_dashboard"):
        args.pop(key, None)
    items = []
    for value, name in choices:
        href = url_for(endpoint, **{**args, PARTNER_FILTER_KEY: value})
        items.append({"value": value, "name": name, "href": href, "selected": value == selected})
    return {"active": bool(selected), "label": label, "items": items}


def inject_partner_filter() -> dict[str, Any]:
    """Expose the lazy menu without reading inputs or querying on fragment responses."""
    return {"partner_filter_menu": partner_filter_menu}
