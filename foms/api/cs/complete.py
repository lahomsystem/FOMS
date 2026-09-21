"""ERP 주문 CS 완료 API — canonical CS→COMPLETED 전이 (STATE-CONST-CS-01).

본체는 :mod:`foms.services.orders.cs_complete_service` 로 옮겼다(ADMIN-OVERRIDE-01 C4) —
완료로 가는 길이 여러 라우트에 흩어지면 "상태만 COMPLETED 이고 뒤가 빈" 주문이 생기기
때문이다. 이 파일은 요청을 읽고 서비스를 부르고 커밋하는 얇은 라우트다.

관리자는 `admin_override` 로 업무 게이트(CS 단계 전제·필수 승인·보류·진행 중 AS)를 뚫을 수
있고, 뚫린 요청은 성공했을 때만 `ADMIN_OVERRIDE_USED` 이벤트 1행을 남긴다. 정합 축
(If-Match·잠금 아래 expected_from 재확인·to_values)은 관리자도 못 뚫는다.
"""
from typing import Any, Optional

from flask import Blueprint, jsonify, request, session

from foms.web.auth import get_user_by_id, login_required
from db import get_db
from foms.services.erp_permissions import erp_edit_required
from foms.services.orders.admin_override import (
    admin_override_error,
    log_admin_override_denied,
    record_admin_override_event,
    resolve_admin_override,
)
from foms.services.orders.cs_complete_service import (
    CS_STAGES,
    POLICY_CS_COMPLETE,
    _apply_cs_complete_side_effects,
    _cs_gate_block,
    _cs_quest_block,
    complete_order_as_cs,
    cs_complete_replay,
    request_hash as _request_hash,
    scope_hash as _scope_hash,
    transition_error_response as _transition_error_response,
)
from foms.services.orders.state_axes import read_main_stage
from models import Order

erp_orders_cs_bp = Blueprint(
    "erp_orders_cs",
    __name__,
    url_prefix="/api/orders",
)

_POLICY_CS_COMPLETE = POLICY_CS_COMPLETE
_CS_STAGES = CS_STAGES


def _idempotency_key(body: dict[str, Any]) -> Optional[str]:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


@erp_orders_cs_bp.route("/<int:order_id>/cs/complete", methods=["POST"])
@login_required
@erp_edit_required
def api_cs_complete(order_id):
    """CS 단계 완료 → COMPLETED. CS quest + hold + AS gate 통과 시에만 전이.

    5단계 하드 게이트: 존재(404) → 팀 권한(데코레이터 403) → CS stage(INVALID_STAGE 409) →
    CS quest 완료 + 보류 해제 + AS cycle NONE/COMPLETED(각 409). 관리자가 `admin_override` 를
    켜면 이 업무 게이트들만 건너뛴다. same-key 재요청은 전이/side-effect 없이 replay 한다.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        # 권한 축 판정은 업무 게이트보다 먼저 — 비관리자가 게이트 코드 대신 정확한 오답을 받는다.
        err = admin_override_error(user, body)
        if err is not None:
            log_admin_override_denied(
                db, order_id=order_id, gate=err[0].get_json().get("code"),
                route="erp_orders_cs.api_cs_complete", user=user)
            return err
        override = resolve_admin_override(user, body)

        punched: list = []
        from_stage = read_main_stage(order)
        failed = complete_order_as_cs(
            db, order, actor_user=user, actor_user_id=user_id, body=body,
            idempotency_key=_idempotency_key(body), override=override, punched=punched,
        )
        if failed is not None:
            return failed

        if override is not None and punched:
            record_admin_override_event(
                db, order, override=override, gates=punched,
                route="erp_orders_cs.api_cs_complete", axis="MAIN",
                from_value=from_stage, to_value="COMPLETED",
            )
        db.commit()
        return jsonify({"success": True, "message": "CS가 완료되어 최종 완료 처리되었습니다.",
                        "new_status": "COMPLETED"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


def _cs_replay(db: Any, actor_user_id: Any, idem_key: Optional[str]) -> bool:
    """(actor, CS_COMPLETE, key) receipt 존재 여부. 서비스 모듈 구현을 그대로 쓴다."""
    return cs_complete_replay(db, actor_user_id, idem_key)


__all__ = ["erp_orders_cs_bp", "api_cs_complete"]
