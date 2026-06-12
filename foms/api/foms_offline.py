"""P2-03 offline queue snapshot API for Service Worker cache."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify

from db import get_db
from foms.web.auth import login_required
from models import Order

foms_offline_bp = Blueprint("foms_offline", __name__, url_prefix="/api/foms/offline")


@foms_offline_bp.route("/queue", methods=["GET"])
@login_required
def offline_queue_snapshot() -> tuple[Any, int]:
    """
    Return the latest ERP queue rows for offline stale-while-revalidate cache.

    Returns:
        JSON list capped at 20 orders with mobile-card fields.
    """
    db = get_db()
    rows = (
        db.query(Order)
        .filter(Order.not_deleted_filter())
        .order_by(Order.id.desc())
        .limit(20)
        .all()
    )
    payload = [
        {
            "id": o.id,
            "customer_name": o.customer_name,
            "phone": o.phone,
            "address": o.address,
            "status": o.status,
            "erp_stage_code": getattr(o, "erp_stage_code", None),
        }
        for o in rows
    ]
    return jsonify({"success": True, "data": payload}), 200
