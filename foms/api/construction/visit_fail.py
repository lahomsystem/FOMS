"""제품마다 '시공 끝' — 지난 방문 사진 다시 쓰기 막기 · 생산 단계 방문의 [시공 불가].

설계: ``docs/specs/2026-11-21-item-construction-done_SPEC.md`` 4.2 (N3 · N6). 스위치가 켜진 나눠 시공
주문에만 걸린다 — 아니면 지금과 같다.

* [증빙 등록]: 이 주문의 닫힌 방문 줄(VISITED · REWORKED · COMPLETED · READY) 봉인 사본에 이미 든 첨부는
  이번 방문 증빙으로 받지 않는다(첫날 사진으로 마지막 날 완료를 통과시키지 못하게).
* [시공 불가]: 생산 단계 + 열린 방문이면 방문 줄만 REWORKED 로 닫는다. 단계 · 상태 · 사유별 되돌림은 없다.

``orders`` 가 위 헬퍼(:func:`_apply_fail_side_effects` 등)를 다 정의한 뒤 모듈 중간에서 이 모듈을 가져온다.
"""
from __future__ import annotations

from typing import Any, Optional

from flask import jsonify

from foms.api.construction.item_done import _PRODUCTION_STAGES, _remember_response, _replayed
from foms.api.construction.orders import (
    _REWORK_LABELS,
    _apply_fail_side_effects,
    _audit_construction,
    _current_attempt,
    _idempotency_key,
    _idempotency_receipt_exists,
    _request_hash,
    _scope_hash,
)
from foms.services.orders.construction_visit import VISITED_STATUS, split_flow_active
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.orders.state_axes import read_main_stage
from models import Order, OrderConstructionAttempt, OrderEvent

__all__ = ["evidence_reuse_blocked", "production_visit_fail_applies", "visit_fail_response"]

#: 생산 단계 나눠 시공 방문의 [시공 불가] — 방문만 닫는다(단계 되돌림 없음).
_POLICY_CONSTRUCTION_VISIT_FAIL = "STATE_CONSTRUCTION_VISIT_FAIL"
#: 봉인된(닫힌) 방문 줄 — 이 줄들의 사진 · 서명 사본은 다음 방문 증빙으로 다시 쓰지 못한다.
_SEALED_STATUSES = (VISITED_STATUS, "REWORKED", "COMPLETED", "READY")


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sealed_attachment_ids(db: Any, order_id: int) -> set[int]:
    """이 주문의 닫힌 방문 줄 봉인 사본에 든 첨부 id(전 · 후 사진 · 서명)."""
    rows = (db.query(OrderConstructionAttempt.evidence)
            .filter(OrderConstructionAttempt.order_id == order_id,
                    OrderConstructionAttempt.status.in_(_SEALED_STATUSES)).all())
    ids: set[int] = set()
    for (evidence,) in rows:
        if not isinstance(evidence, dict):
            continue
        for value in list(evidence.get("before") or []) + list(evidence.get("after") or []):
            ids.add(_as_int(value))
        ids.add(_as_int(evidence.get("signature_att_id")))
    ids.discard(None)
    return ids


def evidence_reuse_blocked(db: Any, order: Order, attachment_id: int) -> bool:
    """나눠 시공 주문에서 지난 방문에 봉인된 첨부를 이번 방문 증빙으로 다시 걸려 하나(스위치 켜짐일 때만)."""
    if not split_flow_active(order.structured_data):
        return False
    return int(attachment_id) in _sealed_attachment_ids(db, order.id)


def production_visit_fail_applies(db: Any, order: Order, user_id: Any, idem_key: Optional[str]) -> bool:
    """[시공 불가]가 방문만 닫는 경우인가 — 스위치 켜짐 · 나눠 시공 · 생산 단계 · 열린 방문(또는 그 다시 보내기)."""
    if order.erp_stage_code not in _PRODUCTION_STAGES or not split_flow_active(order.structured_data):
        return False
    return (_current_attempt(db, order.id) is not None
            or _idempotency_receipt_exists(db, user_id, _POLICY_CONSTRUCTION_VISIT_FAIL, idem_key))


def visit_fail_response(db: Any, order_id: int, *, data: dict[str, Any], user: Any, user_id: Any,
                        reason: str, detail: str, reschedule_date: Any):
    """생산 단계 방문의 [시공 불가] — 방문 줄만 REWORKED 로 닫고 사진 · 서명 칸을 비운다.

    단계 · 상태 · 사유별 되돌림은 없다. 다시 잡기 날이 오면 지금 [시공 불가]의 다시 잡기 길
    (:func:`_apply_fail_side_effects`)을 그대로 탄다. 쓰기는 REV-00 한 거래다.
    """
    reason_label = _REWORK_LABELS.get(reason, reason)
    captured: dict[str, Any] = {}

    def _mutate(sess: Any, orders: list[Order]) -> dict[int, list[str]]:
        o = orders[0]
        stage = read_main_stage(o) or "PRODUCTION"
        attempt_id = _apply_fail_side_effects(sess, o, user, user_id, reason, detail, reschedule_date,
                                              keep_stage=stage)
        sess.add(OrderEvent(
            order_id=o.id, event_type="CONSTRUCTION_REWORKED",
            payload={"from": stage, "to": stage, "visit_only": True, "attempt_id": attempt_id,
                     "reason": f"{reason_label}: {detail}" if detail else reason_label},
            created_by_user_id=user_id,
        ))
        captured.update(attempt_id=attempt_id, stage=stage)
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        result = execute_order_mutation(
            db, actor_user_id=user_id, policy_id=_POLICY_CONSTRUCTION_VISIT_FAIL, order_ids=[order_id],
            scope_hash=_scope_hash("CONSTRUCTION_VISIT_FAIL", order_id), request_hash=_request_hash(data),
            mutation=_mutate, idempotency_key=_idempotency_key(data),
        )
    except RevisionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc), "code": exc.error_code}), exc.status_code

    stage = captured.get("stage", "PRODUCTION")
    payload = {
        "success": True, "message": f"시공 불가로 처리했어요. {reason_label} — 단계는 그대로예요.",
        "new_status": stage, "reason": reason,
        "data": {"mode": "visit", "attempt_id": captured.get("attempt_id")}, "error": None,
    }
    if result.replayed:
        return _replayed(db, result.body, payload)
    order = db.get(Order, order_id)
    _audit_construction(
        order, "CONSTRUCTION_REWORK_REQUESTED", user_id, note=reason_label,
        extra={"reason": reason, "detail": detail or None, "new_stage": stage,
               "attempt_id": captured.get("attempt_id"), "visit_only": True},
    )
    _remember_response(db, result.read_receipt_id, payload)
    db.commit()
    return jsonify(payload)
