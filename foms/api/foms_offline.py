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
    resp = jsonify({"success": True, "data": payload})
    # PII 봉쇄: 이 스냅샷은 고객명/전화/주소(PII)를 담는다. Service Worker(및 브라우저 HTTP
    # 캐시)가 CacheStorage 에 저장하지 못하도록 no-store 를 명시한다 — 공유 기기에서 이전
    # 사용자 PII 가 다음 사용자에게 노출되는 것을 원천 차단한다(SW responseForbidsStore 게이트).
    resp.headers["Cache-Control"] = "no-store"
    return resp, 200
