"""
ERP 주문 시공 API. (Phase 4-5g)
erp.py에서 분리: construction/start, construction/complete, construction/fail.
"""

import copy
import datetime

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from foms.services.erp_display import _ensure_dict
from foms.services.feature_flags import env_bool
from db import get_db
from foms.services.erp_permissions import erp_construction_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns
from models import Order, OrderAttachment, OrderEvent, SecurityLog

erp_orders_construction_bp = Blueprint("erp_orders_construction", __name__, url_prefix="/api/orders")


@erp_orders_construction_bp.route("/<int:order_id>/construction/start", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_start(order_id):
    """시공 시작 (히스토리 기록)"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if (
            not order
            or getattr(order, "status", None) == "DELETED"
            or getattr(order, "deleted_at", None) is not None
        ):
            return jsonify({"success": False, "message": "Order not found"}), 404

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get("workflow") or {}
        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "CONSTRUCTION",
                "updated_at": datetime.datetime.now().isoformat(),
                "updated_by": user.name if user else "Unknown",
                "note": "시공 시작",
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        setattr(order, "structured_data", copy.deepcopy(sd))
        flag_modified(order, "structured_data")

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 시작"))
        db.commit()
        return jsonify({"success": True, "message": "시공이 시작되었습니다."})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_construction_bp.route("/<int:order_id>/construction/complete", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_complete(order_id):
    """시공 완료 → 완료(COMPLETED) 단계로 이동 (ERP 프로세스 맵에서 '완료'로 표시)"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if (
            not order
            or getattr(order, "status", None) == "DELETED"
            or getattr(order, "deleted_at", None) is not None
        ):
            return jsonify({"success": False, "message": "Order not found"}), 404

        # B5 시공 완료 게이트: FOMS_CONSTRUCTION_GATE_ENABLED 켜졌을 때만 증빙 요건 강제.
        # 기본 off = 기존 완료 동작 100% 불변(운영 무파괴, 스테이징에서 켜서 검증).
        if env_bool("FOMS_CONSTRUCTION_GATE_ENABLED", default=False):
            gate_sd = _ensure_dict(order.structured_data)
            evidence = ((gate_sd.get("construction") or {}).get("evidence")) or {}
            missing = []
            if len(evidence.get("after") or []) < 2:
                missing.append("after")
            if not evidence.get("signature_att_id"):
                missing.append("signature")
            if missing:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "완료 요건 미충족",
                            "message": "완료 요건 미충족",
                            "data": {"missing": missing},
                        }
                    ),
                    400,
                )

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        payload = request.get_json(silent=True) or {}
        completion_note = (payload.get("completion_note") or "").strip()

        sd = _ensure_dict(order.structured_data)
        wf = sd.get("workflow") or {}
        wf["stage"] = "COMPLETED"
        wf["stage_updated_at"] = datetime.datetime.now().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"
        wf["completion_note"] = completion_note

        note_suffix = (" | 코멘트: " + completion_note[:100]) if completion_note else ""
        hist = wf.get("history") or []
        hist.append(
            {
                "stage": "COMPLETED",
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": "시공 완료 → 완료" + note_suffix,
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        setattr(order, "structured_data", copy.deepcopy(sd))
        flag_modified(order, "structured_data")
        setattr(order, "status", "COMPLETED")
        sync_erp_flat_columns(order, sd)

        event_payload = {
            "domain": "CONSTRUCTION_DOMAIN",
            "action": "CONSTRUCTION_COMPLETED",
            "target": "workflow.stage",
            "before": "CONSTRUCTION",
            "after": "COMPLETED",
            "change_method": "API",
            "source_screen": "erp_construction_dashboard",
            "reason": "시공 완료 → 완료",
        }
        order_event = OrderEvent(
            order_id=order_id,
            event_type="CONSTRUCTION_COMPLETED",
            payload=event_payload,
            created_by_user_id=user_id,
        )
        db.add(order_event)

        db.add(SecurityLog(user_id=user_id, message=f"주문 #{order_id} 시공 완료 → 완료"))
        db.commit()
        return jsonify(
            {
                "success": True,
                "message": "시공이 완료되었습니다. 완료 단계로 이동합니다.",
                "new_status": "COMPLETED",
            }
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_construction_bp.route("/<int:order_id>/construction/evidence", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_evidence(order_id):
    """시공 완료 증빙(before/after 사진·서명) 참조 등록. (B5 완료 게이트)

    이미 업로드된 첨부(category=construction)를 sd['construction']['evidence']에
    참조로 연결한다. 사진 바이너리는 기존 멀티파트 업로드 API가 담당하고, 이 API는
    분류(before/after/signature)만 기록한다.

    Args:
        order_id: 대상 주문 id (URL path).

    Request JSON:
        kind: 'before' | 'after' | 'signature'.
        attachment_id: 이 주문 소속 + category=construction 인 첨부 id.

    Returns:
        (flask.Response, int): 성공 시 200 ``{success, data: evidence}``,
        검증 실패 시 400/404, 서버 오류 시 500.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if (
            not order
            or getattr(order, "status", None) == "DELETED"
            or getattr(order, "deleted_at", None) is not None
        ):
            return jsonify({"success": False, "error": "주문을 찾을 수 없습니다."}), 404

        payload = request.get_json(silent=True) or {}
        kind = (payload.get("kind") or "").strip()
        if kind not in ("before", "after", "signature"):
            return jsonify({"success": False, "error": "kind 값이 올바르지 않습니다."}), 400
        try:
            attachment_id = int(payload.get("attachment_id"))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "attachment_id 가 필요합니다."}), 400

        attachment = db.get(OrderAttachment, attachment_id)
        if (
            not attachment
            or attachment.order_id != order_id
            or (attachment.category or "") != "construction"
        ):
            return (
                jsonify({"success": False, "error": "유효한 시공 첨부가 아닙니다."}),
                400,
            )

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = copy.deepcopy(_ensure_dict(order.structured_data))
        construction = sd.get("construction") or {}
        evidence = construction.get("evidence") or {}
        before = list(evidence.get("before") or [])
        after = list(evidence.get("after") or [])

        if kind == "before":
            if attachment_id not in before:
                before.append(attachment_id)
        elif kind == "after":
            if attachment_id not in after:
                after.append(attachment_id)
        else:  # signature
            evidence["signature_att_id"] = attachment_id
            evidence["signed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            evidence["signed_by_name"] = user.name if user else "Unknown"

        evidence["before"] = before
        evidence["after"] = after
        construction["evidence"] = evidence
        sd["construction"] = construction

        setattr(order, "structured_data", sd)
        flag_modified(order, "structured_data")

        db.add(
            OrderEvent(
                order_id=order_id,
                event_type="CONSTRUCTION_EVIDENCE_ADDED",
                payload={"kind": kind, "attachment_id": attachment_id},
                created_by_user_id=user_id,
            )
        )
        db.commit()
        return jsonify({"success": True, "data": evidence})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


@erp_orders_construction_bp.route("/<int:order_id>/construction/fail", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_fail(order_id):
    """시공 불가 → 원인별 재작업 단계로 이동"""
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if (
            not order
            or getattr(order, "status", None) == "DELETED"
            or getattr(order, "deleted_at", None) is not None
        ):
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        data = request.get_json() or {}
        reason = data.get("reason", "site_issue")
        detail = data.get("detail", "")
        reschedule_date = data.get("reschedule_date")

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        sd = _ensure_dict(order.structured_data)
        wf = sd.get("workflow") or {}

        fail_info = sd.get("construction_fail_history") or []
        fail_entry = {
            "id": len(fail_info) + 1,
            "failed_at": datetime.datetime.now().isoformat(),
            "failed_by": user.name if user else "Unknown",
            "reason": reason,
            "detail": detail,
            "reschedule_date": reschedule_date,
            "previous_stage": "CONSTRUCTION",
        }
        fail_info.append(fail_entry)
        sd["construction_fail_history"] = fail_info

        reason_stage_map = {
            "drawing_error": "DRAWING",
            "measurement_error": "MEASURE",
            "product_defect": "PRODUCTION",
            "site_issue": "CONSTRUCTION",
        }
        new_stage = reason_stage_map.get(reason, "CONSTRUCTION")

        wf["stage"] = new_stage
        wf["stage_updated_at"] = datetime.datetime.now().isoformat()
        wf["stage_updated_by"] = user.name if user else "Unknown"
        wf["rework_reason"] = reason

        reason_labels = {
            "drawing_error": "도면 오류",
            "measurement_error": "실측 오류",
            "product_defect": "제품 불량",
            "site_issue": "현장 문제",
        }
        hist = wf.get("history") or []
        hist.append(
            {
                "stage": new_stage,
                "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": f"시공 불가 → {reason_labels.get(reason, reason)}: {detail}",
            }
        )
        wf["history"] = hist
        sd["workflow"] = wf

        if reschedule_date:
            schedule = sd.get("schedule") or {}
            construction = schedule.get("construction") or {}
            construction["date"] = reschedule_date
            construction["rescheduled"] = True
            construction["reschedule_reason"] = reason
            schedule["construction"] = construction
            sd["schedule"] = schedule

        setattr(order, "structured_data", copy.deepcopy(sd))
        flag_modified(order, "structured_data")
        sync_erp_flat_columns(order, sd)
        setattr(order, "status", new_stage)

        db.add(
            SecurityLog(
                user_id=user_id,
                message=f"주문 #{order_id} 시공 불가: {reason_labels.get(reason, reason)}",
            )
        )
        db.commit()
        return jsonify(
            {
                "success": True,
                "message": f"시공 불가로 처리되었습니다. {reason_labels.get(reason, reason)}로 인해 {new_stage} 단계로 이동합니다.",
                "new_status": new_stage,
                "reason": reason,
            }
        )
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500
