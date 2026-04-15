"""
ERP 주문 고객 컨펌 API. (Phase 4-5h)
erp.py에서 분리: confirm/customer.
"""
import copy
import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from foms.web.erp import _ensure_dict
from db import get_db
from foms.services.erp_permissions import erp_edit_required
from models import Order, SecurityLog

erp_orders_confirm_bp = Blueprint(
    "erp_orders_confirm",
    __name__,
    url_prefix="/api/orders",
)


@erp_orders_confirm_bp.route("/<int:order_id>/confirm/customer", methods=["POST"])
@login_required
@erp_edit_required
def api_customer_confirm(order_id):
    """
    고객 컨펌 완료 처리
    Blueprint V3: 컨펌 완료 -> FOMS 상태 업데이트 (CONFIRM 유지, 생산팀 제작 시작 시 PRODUCTION 이동)
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json() or {}
        confirmation_note = data.get("note", "")

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)

        blueprint = sd.get("blueprint") or {}
        blueprint["customer_confirmed"] = True
        blueprint["confirmed_at"] = datetime.datetime.now().isoformat()
        blueprint["confirmed_by"] = user.name if user else "Unknown"
        blueprint["confirmation_note"] = confirmation_note
        sd["blueprint"] = blueprint

        wf = sd.get("workflow") or {}
        hist = wf.get("history") or []
        hist.append({
            "stage": wf.get("stage", "CONFIRM"),
            "updated_at": datetime.datetime.now().isoformat(),
            "updated_by": user.name if user else "Unknown",
            "note": f"고객 컨펌 완료 (담당자 승인): {confirmation_note}",
        })
        wf["history"] = hist
        sd["workflow"] = wf

        order.structured_data = copy.deepcopy(sd)
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 고객 컨펌 완료 (담당자 승인)"))
        db.commit()

        return jsonify({
            "success": True,
            "message": "고객 컨펌이 완료되었습니다.",
            "new_status": "CONFIRM",
        })
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


__all__ = ["erp_orders_confirm_bp", "api_customer_confirm"]
