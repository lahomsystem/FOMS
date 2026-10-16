"""CS·지방 주문 완료 정본 서비스 (ADMIN-OVERRIDE-01 C4).

어느 라우트로 들어오든(`cs/complete`, 일반 화면 상태 변경, 강제 단계 변경) 최종 COMPLETED 는
:func:`complete_order_as_cs` 를 지나야 한다. 그래야 "상태만 COMPLETED 이고 뒤가 빈" 주문이
생기지 않는다 — 전이와 함께 현재 시공 attempt 봉인·workflow.history·SecurityLog 가 같은
transaction 에서 일어난다.

지방 ERP 주문은 별도 REGIONAL_COMPLETE 정책으로 CS 단계·승인만 생략한다.
보류·진행 중 AS·전이 정합 검사는 유지하고, 남은 물류 상태도 같은 트랜잭션에서 종료한다.

게이트는 두 종류다.
* **업무 게이트(뚫을 수 있다)**: CS 단계 전제(`INVALID_STAGE`), CS 필수 승인
  (`QUEST_INCOMPLETE`), 보류(`HOLD_ACTIVE`), 진행 중 AS(`AS_ACTIVE`). ``override`` 가 주어지면
  건너뛰고, 건너뛴 코드를 ``punched`` 리스트에 적는다.
* **정합 게이트(못 뚫는다)**: If-Match(mutation_version), 잠금 아래 ``expected_from`` 재확인,
  ``to_values`` 위반. 전부 전이 엔진이 강제하며 이 모듈은 손대지 않는다.

``session.commit()`` 은 라우트가 소유한다(REV-00 규약).
"""
import copy
import hashlib
import json
from typing import Any, Optional

from flask import jsonify
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import _ensure_dict
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.erp_policy_quests import check_quest_approvals_complete
from foms.services.orders.complete_path_policy import uses_regional_completion
from foms.services.orders.stage_override import MAIN_PIPELINE_CODES
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    TransitionError,
    transition_order,
)
from foms.services.orders.revision import IdempotencyKeyConflictError, RevisionError
from foms.services.orders.state_axes import (
    AXIS_MAIN,
    read_as_status,
    read_hold,
    read_main_stage,
    read_logistics,
)
from models import Order, OrderConstructionAttempt, SecurityLog

POLICY_CS_COMPLETE = "STATE_CS_COMPLETE"
POLICY_REGIONAL_COMPLETE = "STATE_REGIONAL_COMPLETE"
CS_STAGES = ("CS",)

# CS 완료 = main CS→COMPLETED advance. STATE-CORE 엔진 파일은 import 만 하고 command 를
# registry 에 additive 등록한다(STATE-PROD-01 동형). 이 모듈을 import 하는 모든 소비자
# (cs/complete 라우트·상태 변경 라우트·강제 단계 변경)가 같은 command 를 쓴다.
COMMAND_REGISTRY.setdefault(
    "CS_COMPLETE",
    TransitionCommand(
        command_id="CS_COMPLETE",
        policy_id=POLICY_CS_COMPLETE,
        axis=AXIS_MAIN,
        from_values=("CS",),
        to_values=("COMPLETED",),
        event_type="CS_COMPLETED",
        effect_type="STAGE_NOTIFICATION",
    ),
)

COMMAND_REGISTRY.setdefault(
    "REGIONAL_COMPLETE",
    TransitionCommand(
        command_id="REGIONAL_COMPLETE", policy_id=POLICY_REGIONAL_COMPLETE, axis=AXIS_MAIN,
        # COMPLETED는 receipt 재전송 검증용이다. 신규 완료는 아래 업무 게이트에서 거부한다.
        from_values=MAIN_PIPELINE_CODES, to_values=("COMPLETED",),
        event_type="REGIONAL_ORDER_COMPLETED", effect_type="STAGE_NOTIFICATION",
    ),
)

# 업무 게이트 코드 → 사용자 문구. 코드 이름은 화면 재시도 화이트리스트와 같은 글자를 쓴다.
_GATE_MESSAGES = {
    "QUEST_INCOMPLETE": "CS 필수 승인이 완료되지 않아 완료할 수 없습니다.",
    "HOLD_ACTIVE": "보류 중인 주문은 완료할 수 없습니다.",
    "AS_ACTIVE": "진행 중인 AS 가 있어 완료할 수 없습니다.",
}


def scope_hash(command_id: str, order_id: int) -> str:
    """전이 scope 의 sha256 hex(receipt 저장용)."""
    return hashlib.sha256(f"{command_id}:{order_id}".encode("utf-8")).hexdigest()


def request_hash(body: dict[str, Any]) -> str:
    """요청 payload 의 sha256 hex(same-key/different-hash 감지용)."""
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _cs_quest_missing_teams(sd: dict[str, Any]) -> Optional[list]:
    """CS quest 가 존재하는데 미완이면 미승인 팀 목록, 아니면 None.

    CS quest 자체가 없으면(레거시/backfill 미완) 게이트하지 않는다(lock-out 방지).
    """
    quests = sd.get("quests")
    if not isinstance(quests, list) or not quests:
        return None
    if not any(isinstance(q, dict) and q.get("stage") in ("CS",) for q in quests):
        return None
    complete, missing = check_quest_approvals_complete(sd, "CS")
    if complete:
        return None
    return missing


def cs_gate_code(order: Order, sd: dict[str, Any]) -> Optional[tuple]:
    """CS 완료 업무 게이트 판정 — 막히면 ``(코드, 추가정보)``, 통과면 None.

    판정 순서는 quest → hold → AS 다(기존 라우트와 1:1).
    """
    missing = None if uses_regional_completion(order) else _cs_quest_missing_teams(sd)
    if missing is not None:
        return ("QUEST_INCOMPLETE", {"missing_teams": missing})
    if read_hold(order) == "HELD":
        return ("HOLD_ACTIVE", {})
    if read_as_status(order) in ("RECEIVED", "IN_PROGRESS"):
        return ("AS_ACTIVE", {})
    return None


def _cs_quest_block(sd: dict[str, Any]):
    """CS stage quest 가 존재하고 미완이면 409 QUEST_INCOMPLETE, 아니면 None."""
    missing = _cs_quest_missing_teams(sd)
    if missing is None:
        return None
    return (
        jsonify({
            "success": False, "code": "QUEST_INCOMPLETE",
            "message": _GATE_MESSAGES["QUEST_INCOMPLETE"], "missing_teams": missing,
        }),
        409,
    )


def _cs_gate_block(order: Order, sd: dict[str, Any]):
    """CS 완료 하드 게이트 — quest·hold·AS 순서로 판정(미충족 시 409, 아니면 None)."""
    hit = cs_gate_code(order, sd)
    if hit is None:
        return None
    code, extra = hit
    payload = {"success": False, "code": code, "message": _GATE_MESSAGES[code]}
    payload.update(extra)
    return jsonify(payload), 409


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
    note = "지방 주문 완료 -> 최종 완료" if uses_regional_completion(order) else "CS 완료 -> 최종 완료"
    hist.append({"stage": "COMPLETED",
                 "updated_at": wf.get("stage_updated_at") or now_utc_naive().isoformat(),
                 "updated_by": wf["stage_updated_by"], "note": note})
    wf["history"] = hist
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    db.add(SecurityLog(user_id=user_id, message=f"주문 #{order.id} {note}"))


def transition_error_response(exc: Exception):
    """전이 엔진/REV helper 예외를 route JSON 오류로 매핑(stage 불일치는 INVALID_STAGE)."""
    code = "INVALID_STAGE" if isinstance(exc, StageConflictError) else getattr(exc, "error_code", "TRANSITION_ERROR")
    status = getattr(exc, "status_code", 409)
    return jsonify({"success": False, "code": code, "message": str(exc)}), status


def cs_complete_replay(db: Any, actor_user_id: Any, idem_key: Optional[str],
                       policy_id: str = POLICY_CS_COMPLETE) -> bool:
    """(actor, CS_COMPLETE, key) receipt 존재 여부. 존재하면 replay(전제 게이트 skip)."""
    if not idem_key or actor_user_id is None:
        return False
    from models import OrderMutationReceipt

    return (
        db.query(OrderMutationReceipt.read_receipt_id)
        .filter(
            OrderMutationReceipt.actor_user_id == actor_user_id,
            OrderMutationReceipt.policy_id == policy_id,
            OrderMutationReceipt.idempotency_key == idem_key,
        )
        .first()
        is not None
    )


def _completion_gate(db: Any, order: Order, actor_id: Any, idem_key: Optional[str],
                     override: Any, punched: list, regional: bool) -> Optional[tuple[Any, int]]:
    """정책별 단계·승인 및 공통 보류·AS 검사 결과를 반환한다. receipt는 엔진에서 검증한다."""
    policy = POLICY_REGIONAL_COMPLETE if regional else POLICY_CS_COMPLETE
    if cs_complete_replay(db, actor_id, idem_key, policy):
        return None
    allowed = MAIN_PIPELINE_CODES[:-1] if regional else CS_STAGES
    if read_main_stage(order) not in allowed:
        if override is None:
            message = "진행 중인 지방 주문만 완료할 수 있습니다." if regional else "CS 상태에서만 완료할 수 있습니다."
            return jsonify({"success": False, "code": "INVALID_STAGE", "message": message}), 409
        punched.append("INVALID_STAGE")
    hit = cs_gate_code(order, _ensure_dict(order.structured_data))
    if hit is not None:
        if override is None:
            return _cs_gate_block(order, _ensure_dict(order.structured_data))
        punched.append(hit[0])
    return None


def _finish_regional_logistics(db: Any, order: Order, actor_id: Any) -> None:
    """지방 완료의 설치예정 물류 축을 정식 전이로 종료한다. 호출자 트랜잭션을 공유한다."""
    current = read_logistics(order)
    if current == "NONE":
        return
    transition_order(
        db, command_id="SET_LOGISTICS_STATUS", order_id=order.id, actor_user_id=actor_id,
        expected_from=current, target_value="NONE",
        scope_hash=scope_hash("SET_LOGISTICS_STATUS", order.id), request_hash=request_hash({}),
    )


def _validate_regional_replay(result: Any, order_id: int) -> None:
    """재전송 결과의 주문번호를 확인한다. 다른 주문이면 충돌 예외를 발생시킨다."""
    if result.replayed and not any(
        row.get("order_id") == order_id for row in result.mutation.body.get("resources", [])
    ):
        raise IdempotencyKeyConflictError("idempotency key belongs to another order.")


def complete_order_as_cs(
    db: Any,
    order: Order,
    *,
    actor_user: Any,
    actor_user_id: Any,
    body: dict[str, Any],
    idempotency_key: Optional[str] = None,
    override: Any = None,
    punched: Optional[list] = None,
    expected_version: Optional[int] = None,
):
    """CS/지방 정책으로 최종 완료한다. 성공은 None, 실패는 (JSON, status). 커밋은 호출자 소관."""
    if punched is None:
        punched = []
    order_id = order.id
    # 지방 판정·보류·AS를 잠금 아래 재확인한다. 전이 엔진도 같은 트랜잭션의 잠금을 쓴다.
    if uses_regional_completion(order):
        db.refresh(order, with_for_update=True)
        if order.status == "DELETED" or order.deleted_at is not None:
            return jsonify({"success": False, "message": "주문을 찾을 수 없습니다."}), 404
    regional = uses_regional_completion(order)
    command_id = "REGIONAL_COMPLETE" if regional else "CS_COMPLETE"
    receipt_body = {"order_id": order_id, "body": body} if regional else body
    from_stage = read_main_stage(order)
    failed = _completion_gate(db, order, actor_user_id, idempotency_key, override, punched, regional)
    if failed is not None:
        return failed

    try:
        result = transition_order(
            db, command_id=command_id, order_id=order_id, actor_user_id=actor_user_id,
            expected_from=from_stage, target_value="COMPLETED",
            scope_hash=scope_hash(command_id, order_id),
            request_hash=request_hash(receipt_body), idempotency_key=idempotency_key,
            expected_version=expected_version,
            emergency_override=bool(override),
            reason=(override.reason if override is not None else None),
        )
        if regional:
            _validate_regional_replay(result, order_id)
        if not result.replayed:
            if regional:
                _finish_regional_logistics(db, order, actor_user_id)
            _apply_cs_complete_side_effects(db, order, actor_user, actor_user_id)
    except (TransitionError, RevisionError) as exc:
        db.rollback()
        return transition_error_response(exc)

    return None


__all__ = [
    "complete_order_as_cs",
    "cs_gate_code",
    "cs_complete_replay",
    "transition_error_response",
    "scope_hash",
    "request_hash",
    "POLICY_CS_COMPLETE",
    "CS_STAGES",
]
