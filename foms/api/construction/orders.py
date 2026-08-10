"""ERP 주문 시공 API — canonical construction attempt 전이 (STATE-CONST-CS-01).

시공 시작/증빙/완료/재작업을 :class:`~models.OrderConstructionAttempt`
(CONSTRUCTION-BACKFILL-00) 상태기계로 정본화한다:

* **시공 시작**: 새 UUID attempt(``IN_PROGRESS``·``is_current``)를 발급한다. 새 attempt 는
  빈 evidence 로 시작하고 시공 evidence 블록(``construction.evidence``)도 초기화해 **이전
  attempt evidence 혼입 0**(격리)을 보장한다.
* **시공 완료**: 현재 attempt 를 ``IN_PROGRESS→READY`` 로 전이하고 main stage 를
  ``CONSTRUCTION→CS`` 로 advance 한다(**direct CONSTRUCTION→COMPLETED 금지** — 최종
  COMPLETED 는 CS 단계 ``cs/complete`` 의 quest+AS gate 소관). live evidence 블록을 그
  attempt 의 스냅샷으로 봉인한다.
* **재작업(시공 불가)**: 현재 attempt 를 ``REWORKED``(``is_current=False``·terminal)로 봉인하고
  사유별 이전 단계로 되돌린다. 과거 attempt 는 **immutable**(is_current attempt 만 write 대상)
  이고, 재작업은 다음 시공 시작이 **새 attempt 를 append** 한다(override 0).

version/receipt/event 는 REV-00 :func:`execute_order_mutation` (시작/재작업/증빙)과 STATE-CORE
:func:`transition_order` (완료의 main advance)로 한 tx 원자 보장한다(commit 은 route 소유).
models·마이그레이션은 건드리지 않고 import 만 한다.
"""

import copy
import datetime
import hashlib
import json
import uuid
from typing import Any, Optional

from foms.services.datetime_kst import now_utc_naive

from flask import Blueprint, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from foms.web.auth import get_user_by_id, log_access, login_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.erp_display import _ensure_dict
from foms.services.feature_flags import env_bool
from db import get_db
from foms.services.erp_permissions import erp_construction_edit_required
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.orders.order_transition_service import (
    COMMAND_REGISTRY,
    StageConflictError,
    TransitionCommand,
    TransitionError,
    transition_order,
)
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.orders.state_axes import AXIS_MAIN
from models import (
    Order,
    OrderAttachment,
    OrderConstructionAttempt,
    OrderEvent,
    OrderMutationReceipt,
)

erp_orders_construction_bp = Blueprint("erp_orders_construction", __name__, url_prefix="/api/orders")

# REV-00 receipt idempotency scope 식별자(POLICY_REGISTRY 와 무관 — STATE-PROD/AS 관례).
_POLICY_CONSTRUCTION_START = "STATE_CONSTRUCTION_START"
_POLICY_CONSTRUCTION_COMPLETE = "STATE_CONSTRUCTION_COMPLETE"
_POLICY_CONSTRUCTION_REWORK = "STATE_CONSTRUCTION_REWORK"

_CONSTRUCTION_STAGES = ("시공", "CONSTRUCTION")

# 시공 완료 = main CONSTRUCTION→CS advance(direct COMPLETED 금지). STATE-CORE 엔진 파일은
# import 만 하고, 이 command 를 registry 에 additive 등록한다(STATE-PROD-01 동형).
COMMAND_REGISTRY.setdefault(
    "CONSTRUCTION_COMPLETE",
    TransitionCommand(
        command_id="CONSTRUCTION_COMPLETE",
        policy_id=_POLICY_CONSTRUCTION_COMPLETE,
        axis=AXIS_MAIN,
        from_values=("CONSTRUCTION",),
        to_values=("CS",),
        event_type="CONSTRUCTION_COMPLETED",
        effect_type="STAGE_NOTIFICATION",
    ),
)


# --------------------------------------------------------------------------- #
# REV-00 조립 헬퍼(idempotency/scope/receipt) — STATE-PROD-01 관례 복제(파일 로컬)
# --------------------------------------------------------------------------- #
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


def _idempotency_receipt_exists(
    db: Any, actor_user_id: Any, policy_id: str, idem_key: Optional[str]
) -> bool:
    """(actor, policy, key) receipt 존재 여부. 존재하면 이 요청은 replay(전제 게이트 skip)."""
    if not idem_key or actor_user_id is None:
        return False
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


def _transition_error_response(exc: Exception):
    """전이 엔진/REV helper 예외를 route JSON 오류로 매핑(stage 불일치는 INVALID_STAGE)."""
    code = "INVALID_STAGE" if isinstance(exc, StageConflictError) else getattr(exc, "error_code", "TRANSITION_ERROR")
    status = getattr(exc, "status_code", 409)
    return jsonify({"success": False, "code": code, "message": str(exc)}), status


# --------------------------------------------------------------------------- #
# construction attempt 헬퍼(OrderConstructionAttempt DB registry)
# --------------------------------------------------------------------------- #
def _current_attempt(db: Any, order_id: int) -> Optional[OrderConstructionAttempt]:
    """주문의 current(is_current) construction attempt(없으면 None)."""
    return (
        db.query(OrderConstructionAttempt)
        .filter(
            OrderConstructionAttempt.order_id == order_id,
            OrderConstructionAttempt.is_current.is_(True),
        )
        .first()
    )


def _fresh_evidence() -> dict[str, Any]:
    """새 attempt 의 빈 evidence 블록(격리 — 이전 attempt evidence 미상속)."""
    return {"before": [], "after": []}


def _live_evidence(sd: dict[str, Any]) -> dict[str, Any]:
    """live 시공 evidence 블록(``construction.evidence``)의 deepcopy 스냅샷(없으면 빈 블록)."""
    construction = sd.get("construction") if isinstance(sd.get("construction"), dict) else {}
    evidence = construction.get("evidence") if isinstance(construction.get("evidence"), dict) else {}
    snapshot = copy.deepcopy(evidence)
    snapshot.setdefault("before", [])
    snapshot.setdefault("after", [])
    return snapshot


def _scheduled_date(sd: dict[str, Any]) -> Optional[str]:
    """``schedule.construction.date`` 시공 예정일 스냅샷(없으면 None)."""
    schedule = sd.get("schedule") if isinstance(sd.get("schedule"), dict) else {}
    construction = schedule.get("construction") if isinstance(schedule.get("construction"), dict) else {}
    value = construction.get("date")
    return str(value) if value else None


def _evidence_gate_missing(order: Order) -> list[str]:
    """완료 게이트 미충족 항목(after<2·signature 없음). live evidence 블록 기준."""
    sd = _ensure_dict(order.structured_data)
    evidence = ((sd.get("construction") or {}).get("evidence")) or {}
    missing: list[str] = []
    if len(evidence.get("after") or []) < 2:
        missing.append("after")
    if not evidence.get("signature_att_id"):
        missing.append("signature")
    return missing


@erp_orders_construction_bp.route("/<int:order_id>/construction/start", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_start(order_id):
    """시공 시작 — 새 UUID attempt(IN_PROGRESS·is_current) 발급 + evidence 격리.

    시공중(CONSTRUCTION) 단계이고 현재 열린 attempt 가 없어야 한다(있으면 409 ALREADY_STARTED
    — 새 attempt override 금지). 새 attempt 는 빈 evidence 로 발급하고 live evidence 블록도
    초기화해 이전(재작업) attempt evidence 혼입을 0으로 만든다. version/receipt/event 는 REV-00
    execute_order_mutation 이 원자 보장한다. same-key 재요청은 replay(중복 발급 0).
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if (
            not order
            or getattr(order, "status", None) == "DELETED"
            or getattr(order, "deleted_at", None) is not None
        ):
            return jsonify({"success": False, "message": "Order not found"}), 404

        body = request.get_json(silent=True) or {}
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        if not _idempotency_receipt_exists(db, user_id, _POLICY_CONSTRUCTION_START, idem_key):
            if order.erp_stage_code not in _CONSTRUCTION_STAGES:
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "시공 대기 상태에서만 시공을 시작할 수 있습니다."}), 409
            if _current_attempt(db, order_id) is not None:
                return jsonify({"success": False, "code": "ALREADY_STARTED",
                                "message": "이미 진행 중인 시공 attempt 가 있습니다."}), 409

        captured: dict[str, Any] = {}

        def _mutate(sess: Any, orders: list[Order]) -> dict[int, list[str]]:
            o = orders[0]
            now = now_utc_naive()
            sd = copy.deepcopy(_ensure_dict(o.structured_data))
            # 이전 attempt evidence 격리: live 블록을 새 attempt 기준으로 초기화.
            construction = sd.get("construction")
            if not isinstance(construction, dict):
                construction = {}
                sd["construction"] = construction
            construction["evidence"] = _fresh_evidence()
            wf = sd.get("workflow") or {}
            hist = wf.get("history") or []
            hist.append({"stage": "CONSTRUCTION", "updated_at": now.isoformat(),
                         "updated_by": user.name if user else "Unknown", "note": "시공 시작"})
            wf["history"] = hist
            sd["workflow"] = wf
            o.structured_data = sd
            flag_modified(o, "structured_data")

            attempt = OrderConstructionAttempt(
                id=str(uuid.uuid4()), order_id=o.id, status="IN_PROGRESS", is_current=True,
                evidence=_fresh_evidence(), started_at=now,
                started_by=user.name if user else None, scheduled_date=_scheduled_date(sd),
            )
            sess.add(attempt)
            sess.add(OrderEvent(
                order_id=o.id, event_type="CONSTRUCTION_STARTED",
                payload={"attempt_id": attempt.id, "domain": "CONSTRUCTION_DOMAIN",
                         "action": "CONSTRUCTION_STARTED"},
                created_by_user_id=user_id,
            ))
            captured["attempt_id"] = attempt.id
            return {o.id: []}

        try:
            execute_order_mutation(
                db, actor_user_id=user_id, policy_id=_POLICY_CONSTRUCTION_START,
                order_ids=[order_id], scope_hash=_scope_hash("CONSTRUCTION_START", order_id),
                request_hash=_request_hash(body), mutation=_mutate, idempotency_key=idem_key,
            )
        except RevisionError as exc:
            db.rollback()
            return jsonify({"success": False, "error": str(exc), "code": exc.error_code}), exc.status_code

        _audit_construction(order, "CONSTRUCTION_STARTED", user_id)
        db.commit()
        return jsonify({"success": True, "message": "시공이 시작되었습니다.",
                        "attempt_id": captured.get("attempt_id")})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


def _audit_construction(
    order: Order,
    action: str,
    user_id: Any,
    note: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """시공 행위 1건을 구조화 감사로 남긴다(문장은 표시 SSOT 가 만든다).

    라우트가 뒤에서 ``db.commit()`` 하므로 같은 트랜잭션에 싣는다(``auto_commit=False``) —
    시공 상태 전이와 감사 기록이 함께 커밋되거나 함께 사라진다.

    :param order: 대상 :class:`~models.Order`.
    :param action: 행위 코드(``CONSTRUCTION_STARTED`` 등).
    :param user_id: 행위자 user id.
    :param note: 문장 뒤에 붙일 짧은 부연(완료 코멘트·재작업 사유 등).
    :param extra: ``detail`` 에 추가로 담을 구조화 값.
    """
    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action=action, note=note, **context),
        user_id,
        auto_commit=False,
        action=action, target_type="order", target_id=int(order.id),
        detail={**(extra or {}), **context},
    )


def _apply_complete_side_effects(db: Any, order: Order, user: Any, user_id: Any, completion_note: str) -> None:
    """CONSTRUCTION_COMPLETE 전이 후 same-tx: current attempt READY 봉인 + history append."""
    attempt = _current_attempt(db, order.id)
    sd = copy.deepcopy(_ensure_dict(order.structured_data))
    if attempt is not None:
        attempt.evidence = _live_evidence(sd)  # live evidence 를 attempt 스냅샷으로 봉인.
        attempt.status = "READY"
        attempt.completed_at = now_utc_naive()
        attempt.completed_by = user.name if user else None
        if completion_note:
            attempt.completion_note = completion_note
    wf = sd.setdefault("workflow", {})
    wf["stage_updated_by"] = user.name if user else "Unknown"
    note = "시공 완료 → CS" + ((" | 코멘트: " + completion_note[:100]) if completion_note else "")
    hist = wf.get("history") or []
    hist.append({"stage": "CS", "updated_at": wf.get("stage_updated_at") or now_utc_naive().isoformat(),
                 "updated_by": wf["stage_updated_by"], "note": note})
    wf["history"] = hist
    order.structured_data = sd
    flag_modified(order, "structured_data")
    sync_erp_flat_columns(order, sd)
    _audit_construction(
        order, "CONSTRUCTION_COMPLETED", user_id,
        note=completion_note or None,
        extra={"new_stage": "CS", "completion_note": completion_note or None},
    )


@erp_orders_construction_bp.route("/<int:order_id>/construction/complete", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_complete(order_id):
    """시공 완료 — 현재 attempt IN_PROGRESS→READY + main CONSTRUCTION→CS(direct COMPLETED 금지).

    시공중 stage 에서만 완료할 수 있고, 목표는 항상 CS 다(최종 COMPLETED 는 CS 단계
    ``cs/complete`` 의 quest+AS gate 소관). ``FOMS_CONSTRUCTION_GATE_ENABLED`` 가 켜지면 live
    evidence(after≥2·signature) 요건을 강제한다(기본 off = 요건 미강제). 전이는 STATE-CORE
    transition_order 로 원자 실행하고, 전이 후 same-tx 로 current attempt 를 READY 로 봉인한다.
    """
    db = get_db()
    try:
        order = db.get(Order, order_id)
        if (
            not order
            or getattr(order, "status", None) == "DELETED"
            or getattr(order, "deleted_at", None) is not None
        ):
            return jsonify({"success": False, "message": "Order not found"}), 404

        if env_bool("FOMS_CONSTRUCTION_GATE_ENABLED", default=False):
            missing = _evidence_gate_missing(order)
            if missing:
                return (
                    jsonify({"success": False, "error": "완료 요건 미충족",
                             "message": "완료 요건 미충족", "data": {"missing": missing}}),
                    400,
                )

        body = request.get_json(silent=True) or {}
        completion_note = (body.get("completion_note") or "").strip()
        idem_key = _idempotency_key(body)
        user_id = session.get("user_id")
        user = get_user_by_id(user_id)

        if not _idempotency_receipt_exists(db, user_id, _POLICY_CONSTRUCTION_COMPLETE, idem_key):
            if order.erp_stage_code not in _CONSTRUCTION_STAGES:
                return jsonify({"success": False, "code": "INVALID_STAGE",
                                "message": "시공중 상태에서만 시공을 완료할 수 있습니다."}), 409

        try:
            result = transition_order(
                db, command_id="CONSTRUCTION_COMPLETE", order_id=order_id,
                actor_user_id=user_id, expected_from="CONSTRUCTION", target_value="CS",
                scope_hash=_scope_hash("CONSTRUCTION_COMPLETE", order_id),
                request_hash=_request_hash(body), idempotency_key=idem_key,
            )
        except (TransitionError, RevisionError) as exc:
            db.rollback()
            return _transition_error_response(exc)

        if not result.replayed:
            _apply_complete_side_effects(db, order, user, user_id, completion_note)
        db.commit()
        return jsonify({"success": True, "message": "시공이 완료되었습니다. CS 단계로 이동합니다.",
                        "new_status": "CS"})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500


@erp_orders_construction_bp.route("/<int:order_id>/construction/evidence", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_evidence(order_id):
    """시공 완료 증빙(before/after 사진·서명) 참조 등록. (B5 완료 게이트)

    이미 업로드된 첨부(category=construction)를 live ``construction.evidence`` 블록에 분류
    참조로 연결한다. 이 블록은 현재 attempt 의 live evidence 이며, 시공 완료/재작업 시 그 attempt
    의 스냅샷으로 봉인되고 다음 시공 시작이 블록을 초기화한다(attempt 별 격리).

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
        _audit_construction(order, "CONSTRUCTION_EVIDENCE_UPDATED", user_id, note=kind,
                            extra={"kind": kind, "attachment_id": attachment_id})
        db.commit()
        return jsonify({"success": True, "data": evidence})
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "error": str(exc)}), 500


_REWORK_STAGE_MAP = {
    "drawing_error": "DRAWING",
    "measurement_error": "MEASURE",
    "product_defect": "PRODUCTION",
    "site_issue": "CONSTRUCTION",
}
_REWORK_LABELS = {
    "drawing_error": "도면 오류",
    "measurement_error": "실측 오류",
    "product_defect": "제품 불량",
    "site_issue": "현장 문제",
}


@erp_orders_construction_bp.route("/<int:order_id>/construction/fail", methods=["POST"])
@login_required
@erp_construction_edit_required
def api_construction_fail(order_id):
    """시공 불가(재작업) — 현재 attempt REWORKED 봉인 + 사유별 이전 단계 되돌림.

    현재 attempt 를 ``REWORKED``(``is_current=False``·terminal)로 봉인하고 live evidence 를 그
    attempt 스냅샷으로 남긴다. 과거 attempt 는 immutable(is_current attempt 만 write 대상)이므로
    재작업은 override 가 아니라 다음 시공 시작이 **새 attempt 를 append** 한다. main stage 는 사유
    (drawing/measurement/product/site)별 이전 단계로 되돌린다. version/receipt/event 는 REV-00
    execute_order_mutation 이 원자 보장한다.
    """
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
        idem_key = _idempotency_key(data)
        new_stage = _REWORK_STAGE_MAP.get(reason, "CONSTRUCTION")

        user_id = session.get("user_id")
        user = get_user_by_id(user_id)
        captured: dict[str, Any] = {}

        def _mutate(sess: Any, orders: list[Order]) -> dict[int, list[str]]:
            o = orders[0]
            now = now_utc_naive()
            sd = copy.deepcopy(_ensure_dict(o.structured_data))

            # 현재(열린) attempt 만 REWORKED 로 봉인 — 과거 terminal attempt 는 손대지 않는다.
            attempt = _current_attempt(sess, o.id)
            if attempt is not None:
                attempt.evidence = _live_evidence(sd)
                attempt.status = "REWORKED"
                attempt.is_current = False
                attempt.fail_reason = reason
                attempt.fail_detail = detail
                captured["attempt_id"] = attempt.id

            fail_info = sd.get("construction_fail_history") or []
            fail_info.append({
                "id": len(fail_info) + 1, "failed_at": now.isoformat(),
                "failed_by": user.name if user else "Unknown", "reason": reason,
                "detail": detail, "reschedule_date": reschedule_date, "previous_stage": "CONSTRUCTION",
            })
            sd["construction_fail_history"] = fail_info

            wf = sd.get("workflow") or {}
            wf["stage"] = new_stage
            wf["stage_updated_at"] = now.isoformat()
            wf["stage_updated_by"] = user.name if user else "Unknown"
            wf["rework_reason"] = reason
            hist = wf.get("history") or []
            hist.append({
                "stage": new_stage, "updated_at": wf["stage_updated_at"],
                "updated_by": wf["stage_updated_by"],
                "note": f"시공 불가 → {_REWORK_LABELS.get(reason, reason)}: {detail}",
            })
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

            o.structured_data = sd
            flag_modified(o, "structured_data")
            sync_erp_flat_columns(o, sd)
            o.status = new_stage
            sess.add(OrderEvent(
                order_id=o.id, event_type="CONSTRUCTION_REWORKED",
                payload={"reason": reason, "detail": detail, "new_stage": new_stage,
                         "attempt_id": captured.get("attempt_id"),
                         "domain": "CONSTRUCTION_DOMAIN", "action": "CONSTRUCTION_REWORKED"},
                created_by_user_id=user_id,
            ))
            return {o.id: []}

        try:
            execute_order_mutation(
                db, actor_user_id=user_id, policy_id=_POLICY_CONSTRUCTION_REWORK,
                order_ids=[order_id], scope_hash=_scope_hash("CONSTRUCTION_REWORK", order_id),
                request_hash=_request_hash(data), mutation=_mutate, idempotency_key=idem_key,
            )
        except RevisionError as exc:
            db.rollback()
            return jsonify({"success": False, "error": str(exc), "code": exc.error_code}), exc.status_code

        _audit_construction(
            order, "CONSTRUCTION_REWORK_REQUESTED", user_id,
            note=_REWORK_LABELS.get(reason, reason),
            extra={"reason": reason, "detail": detail or None, "new_stage": new_stage},
        )
        db.commit()
        return jsonify({
            "success": True,
            "message": f"시공 불가로 처리되었습니다. {_REWORK_LABELS.get(reason, reason)}로 인해 {new_stage} 단계로 이동합니다.",
            "new_status": new_stage,
            "reason": reason,
        })
    except Exception as exc:
        db.rollback()
        return jsonify({"success": False, "message": str(exc)}), 500
