"""ERP 주문 CS 완료 API — canonical CS→COMPLETED 전이 (STATE-CONST-CS-01).

CS 단계 완료를 STATE-CORE :func:`transition_order` (CS_COMPLETE: CS→COMPLETED)로 정본화한다.
최종 COMPLETED 는 **CS quest gate + AS gate + hold gate** 를 모두 통과할 때만 도달한다
(SSOT §2.3: STAFF/CS, main CS, CS quest complete, hold inactive, AS cycle NONE/COMPLETED).
첨부 수 기반 generic upload count 완료 판정은 쓰지 않는다. 전이 후 same-tx 로 current
construction attempt 를 COMPLETED 로 봉인한다. version/receipt/event 는 한 tx 원자 보장
(commit 은 route 소유)이고 models·마이그레이션은 import 만 한다.
"""
import copy
import hashlib
import json
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, login_required
from foms.services.erp_display import _ensure_dict
from db import get_db
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_policy_quests import check_quest_approvals_complete
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    TransitionError,
    transition_order,
)
from foms.services.orders.revision import RevisionError
from foms.services.orders.state_axes import AXIS_MAIN, read_as_status, read_hold
from models import Order, OrderConstructionAttempt, SecurityLog

erp_orders_cs_bp = Blueprint(
    "erp_orders_cs",
    __name__,
    url_prefix="/api/orders",
)

_POLICY_CS_COMPLETE = "STATE_CS_COMPLETE"
_CS_STAGES = ("CS",)

# CS 완료 = main CS→COMPLETED advance. STATE-CORE 엔진 파일은 import 만 하고 command 를
# registry 에 additive 등록한다(STATE-PROD-01 동형).
COMMAND_REGISTRY.setdefault(
    "CS_COMPLETE",
    TransitionCommand(
        command_id="CS_COMPLETE",
        policy_id=_POLICY_CS_COMPLETE,
        axis=AXIS_MAIN,
        from_values=("CS",),
        to_values=("COMPLETED",),
        event_type="CS_COMPLETED",
        effect_type="STAGE_NOTIFICATION",
    ),
)


def _idempotency_key(body: dict[str, Any]) -> Optional[str]:
    """요청 idempotency key(헤더 우선, body fallback, ≤64자). 없으면 None."""
    key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    key = str(key).strip() if key is not None else ""
    return key[:64] if key else None


def _scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def _request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cs_quest_block(sd: dict[str, Any]):
    """CS stage quest 가 존재하고 미완이면 409 QUEST_INCOMPLETE, 아니면 None.

    CS quest 자체가 없으면(레거시/backfill 미완) 게이트하지 않는다(lock-out 방지) — 존재하는
    CS quest 의 필수 승인이 완료돼야만 전이한다(STATE-PROD-01 stage quest 게이트 동형).
    """
    quests = sd.get("quests")
    if not isinstance(quests, list) or not quests:
        return None
    if not any(isinstance(q, dict) and q.get("stage") in ("CS",) for q in quests):
        return None
    complete, missing = check_quest_approvals_complete(sd, "CS")
    if complete:
        return None
    return (
        jsonify({
            "success": False, "code": "QUEST_INCOMPLETE",
            "message": "CS 필수 승인이 완료되지 않아 완료할 수 없습니다.", "missing_teams": missing,
        }),
        409,
    )


def _cs_gate_block(order: Order, sd: dict[str, Any]):
    """CS 완료 하드 게이트 — quest·hold·AS 순서로 판정(미충족 시 409, 아니면 None).

    * CS quest complete(존재 시): 미완이면 QUEST_INCOMPLETE.
    * hold inactive: 보류 중이면 HOLD_ACTIVE.
    * AS cycle NONE/COMPLETED: RECEIVED/IN_PROGRESS(진행 중 AS)면 AS_ACTIVE.
    """
    blocked = _cs_quest_block(sd)
    if blocked is not None:
        return blocked
    if read_hold(order) == "HELD":
        return jsonify({"success": False, "code": "HOLD_ACTIVE",
                        "message": "보류 중인 주문은 완료할 수 없습니다."}), 409
    if read_as_status(order) in ("RECEIVED", "IN_PROGRESS"):
        return jsonify({"success": False, "code": "AS_ACTIVE",
                        "message": "진행 중인 AS 가 있어 완료할 수 없습니다."}), 409
    return None


def _apply_cs_complete_side_effects(db: Any, order: Order, user: Any, user_id: Any) -> None:
    """CS_COMPLETE 전이 후 same-tx: current construction attempt COMPLETED 봉인 + history append."""
    attempt = (
        db.query(OrderConstructionAttempt)
        .filter(
            OrderConstructionAttempt.order_id == order.id,
            OrderConstructionAttempt.is_current.is_(True),
        )
        .first()
    )
    if attempt is not None:
        attempt.status = "COMPLETED"
        attempt.is_current = False
        if attempt.completed_at is None:
            attempt.completed_at = now_utc_naive()
            attempt.completed_by = user.name if user else None
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    wf = sd.setdefault("workflow", {})
    wf["stage_updated_by"] = user.name if user else "Unknown"
    hist = wf.get("history") or []
    hist.append({"stage": "COMPLETED",
                 "updated_at": wf.get("stage_updated_at") or now_utc_naive().isoformat(),
                 "updated_by": wf["stage_updated_by"], "note": "CS 완료 -> 최종 완료"})
    wf["history"] = hist
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order.id} CS 완료 -> 최종 완료"))


def _transition_error_response(exc: Exception):
    """전이 엔진/REV helper 예외를 route JSON 오류로 매핑(stage 불일치는 INVALID_STAGE)."""
    code = "INVALID_STAGE" if isinstance(exc, StageConflictError) else getattr(exc, "error_code", "TRANSITION_ERROR")
    status = getattr(exc, "status_code", 409)
    return jsonify({"success": False, "code": code, "message": str(exc)}), status


@erp_orders_cs_bp.route("/<int:order_id>/cs/complete", methods=["POST"])
@login_required
@erp_edit_required
def api_cs_complete(order_id):
    """CS 단계 완료 → COMPLETED. CS quest + hold + AS gate 통과 시에만 전이.

    5단계 하드 게이트: 존재(404) → 팀 권한(데코레이터 403) → CS stage(INVALID_STAGE 409) →
    CS quest 완료 + 보류 해제 + AS cycle NONE/COMPLETED(각 409). 첨부 수(generic upload count)로
    완료를 판정하지 않는다. 전이는 STATE-CORE transition_order(CS_COMPLETE)로 원자 실행하고,
    전이 후 same-tx 로 current construction attempt 를 COMPLETED 로 봉인한다. same-key 재요청은
    전이/side-effect 없이 저장된 성공을 replay 한다.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if not order or order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404

        body = request.get_json(silent=True) or {}
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        sd = _ensure_dict(order.structured_data)

        # replay(같은 key 저장 receipt) 가 아니면 CS stage + quest/hold/AS 게이트를 검사한다.
        if not _cs_replay(db, user_id, idem_key):
            if order.erp_stage_code not in _CS_STAGES:
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "CS 상태에서만 완료할 수 있습니다."}), 409
            blocked = _cs_gate_block(order, sd)
            if blocked is not None:
                return blocked

        try:
            result = transition_order(
                db, command_id="CS_COMPLETE", order_id=order_id, actor_user_id=user_id,
                expected_from="CS", target_value="COMPLETED",
                scope_hash=_scope_hash("CS_COMPLETE", order_id),
                request_hash=_request_hash(body), idempotency_key=idem_key,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if not result.replayed:
            _apply_cs_complete_side_effects(db, order, user, user_id)
        db.commit()
        return jsonify({"success": True, "message": "CS가 완료되어 최종 완료 처리되었습니다.",
                        "new_status": "COMPLETED"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


def _cs_replay(db: Any, actor_user_id: Any, idem_key: Optional[str]) -> bool:
    """(actor, CS_COMPLETE, key) receipt 존재 여부. 존재하면 replay(전제 게이트 skip)."""
    if not idem_key or actor_user_id is None:
        return False
    from models import OrderMutationReceipt

    return (
        db.query(OrderMutationReceipt.read_receipt_id)
        .filter(
            OrderMutationReceipt.actor_user_id == actor_user_id,
            OrderMutationReceipt.policy_id == _POLICY_CS_COMPLETE,
            OrderMutationReceipt.idempotency_key == idem_key,
        )
        .first()
        is not None
    )


__all__ = ["erp_orders_cs_bp", "api_cs_complete"]
