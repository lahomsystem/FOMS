"""잘못 찍은 제품 '시공 끝' 되돌리기 API (제품마다 '시공 끝' 2단계, N9).

``POST /api/orders/<id>/items/<uid>/construction-done/undo`` body ``{"reason": "..."}``.
``structured_data['item_construction_done'][uid]`` 하나를 지운다. 봉인한 방문 줄
(``OrderConstructionAttempt``)은 그대로 둔다 — 기록은 지우지 않는다(설계서 5.4).

* 권한: 관리자 · 매니저 · CS(정책 ``ITEM_CONSTRUCTION_DONE_UNDO``). 사유 필수.
* 주문이 생산 · 시공 단계일 때만(잠금 아래에서 다시 본다).
* 쓰기는 REV-00 :func:`execute_order_mutation` 한 거래(행 잠금 · 버전 · 영수증 · OrderEvent · 감사).

레이어 방향 래칫 때문에 ``foms.web.auth`` 를 import 하지 않는다 — 사용자는 ``g.current_user``,
감사는 ``SecurityLog`` 를 본 거래에 직접 싣는다(``measurement_visit.py`` 와 같은 방식).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any, List, Mapping, Optional

from flask import g, jsonify, request, session
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from foms.services.audit_message_display import describe_order_action
from foms.services.audit_writer import normalize_security_detail
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.orders.construction_visit import names_for_uids
from foms.services.orders.item_construction_done import remove_done_mark
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.revision import RevisionError, execute_order_mutation
from foms.services.orders.state_axes import read_main_stage
from models import Order, OrderEvent, SecurityLog

logger = logging.getLogger(__name__)

ITEM_CONSTRUCTION_DONE_UNDO_POLICY_ID = "ITEM_CONSTRUCTION_DONE_UNDO"
ITEM_CONSTRUCTION_DONE_UNDONE = "ITEM_CONSTRUCTION_DONE_UNDONE"

#: 되돌리기를 받는 단계(N9) — 생산 · 시공.
_UNDO_STAGES = ("PRODUCTION", "CONSTRUCTION")
_REASON_MAX = 200

_ERR_REASON = "되돌리는 이유를 적어 주세요."
_ERR_NOT_FOUND = "주문을 찾을 수 없습니다."
_ERR_NOT_DONE = "시공 끝 표시가 없는 제품이에요."
_ERR_STAGE = "생산 · 시공 단계 주문만 되돌릴 수 있어요."
_ERR_IF_MATCH = "If-Match 형식이 올바르지 않습니다."
_ERR_SERVER = "시공 끝 표시를 되돌리지 못했어요."


class _UndoRejected(Exception):
    """잠금 아래에서 본 상태가 되돌리기를 받지 않는다 — 쓰기 없이 되감고 그 응답을 돌려준다."""

    def __init__(self, error: str, status: int, code: str) -> None:
        super().__init__(error)
        self.error, self.status, self.code = error, status, code


def _fail(error: str, status: int, **extra: Any):
    payload: dict = {"success": False, "data": None, "error": error}
    payload.update(extra)
    return jsonify(payload), status


def _hashes(order_id: int, uid: str, reason: str) -> tuple[str, str]:
    scope = hashlib.sha256(f"{ITEM_CONSTRUCTION_DONE_UNDO_POLICY_ID}:{order_id}:{uid}".encode()).hexdigest()
    body = json.dumps({"uid": uid, "reason": reason}, sort_keys=True, ensure_ascii=False)
    return scope, hashlib.sha256(body.encode()).hexdigest()


def _add_audit(sess: Any, *, order: Order, user_id: Any, uid: str, name: str, reason: str,
               record: dict) -> None:
    """감사행을 본 거래에 싣는다(되돌리기가 되감기면 감사도 함께 되감긴다)."""
    ctx = order_audit_context(order)
    detail = normalize_security_detail({
        "uid": uid, "name": name, "reason": reason, "done_date": record.get("date"),
        "attempt_id": record.get("attempt_id"), **ctx,
    })
    message = describe_order_action(
        order_id=order.id, action=ITEM_CONSTRUCTION_DONE_UNDONE, note=f"{name} · {reason}", **ctx)
    sess.add(SecurityLog(
        user_id=user_id, message=message, action=ITEM_CONSTRUCTION_DONE_UNDONE,
        target_type="order", target_id=int(order.id), detail=detail,
    ))


def item_construction_done_undo_response(order_id: int, uid: str) -> Any:
    """제품 하나의 '시공 끝' 표시를 지운다. 실패하면 아무것도 바꾸지 않는다."""
    user = getattr(g, "current_user", None)
    decision = evaluate_policy(POLICY_REGISTRY[ITEM_CONSTRUCTION_DONE_UNDO_POLICY_ID], user)
    if not decision.allowed:
        return _fail(decision.reason, decision.status, message=decision.reason, code=decision.code)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    reason = str(body.get("reason") or "").strip()[:_REASON_MAX]
    if not reason:
        return _fail(_ERR_REASON, 400, code="REASON_REQUIRED")
    uid = str(uid or "").strip()

    if_match_raw = (request.headers.get("If-Match") or "").strip().strip('"')
    expected_versions: Optional[Mapping[int, int]] = None
    if if_match_raw:
        try:
            expected_versions = {order_id: int(if_match_raw)}
        except ValueError:
            return _fail(_ERR_IF_MATCH, 400)
    idempotency_key = (request.headers.get("Idempotency-Key") or "").strip() or None

    db: Session = get_db()
    if db.query(Order.id).filter(Order.id == order_id, Order.not_deleted_filter()).first() is None:
        return _fail(_ERR_NOT_FOUND, 404)

    user_id = session.get("user_id") or getattr(user, "id", None)
    scope_hash, request_hash = _hashes(order_id, uid, reason)

    def _mutate(sess: Session, orders: List[Order]) -> Mapping[int, List[str]]:
        o = orders[0]
        if read_main_stage(o) not in _UNDO_STAGES:
            raise _UndoRejected(_ERR_STAGE, 409, "INVALID_STAGE")
        sd = copy.deepcopy(o.structured_data) if isinstance(o.structured_data, dict) else {}
        name = (names_for_uids(sd, [uid]) or ["제품"])[0]
        record = remove_done_mark(sd, uid)
        if record is None:
            raise _UndoRejected(_ERR_NOT_DONE, 404, "NOT_DONE")
        o.structured_data = sd
        flag_modified(o, "structured_data")
        sess.add(OrderEvent(
            order_id=o.id, event_type=ITEM_CONSTRUCTION_DONE_UNDONE,
            payload={"uid": uid, "name": name, "reason": reason, "record": record},
            created_by_user_id=user_id,
        ))
        _add_audit(sess, order=o, user_id=user_id, uid=uid, name=name, reason=reason, record=record)
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        outcome = execute_order_mutation(
            db, actor_user_id=user_id, policy_id=ITEM_CONSTRUCTION_DONE_UNDO_POLICY_ID,
            order_ids=[order_id], expected_versions=expected_versions, idempotency_key=idempotency_key,
            scope_hash=scope_hash, request_hash=request_hash, mutation=_mutate,
        )
        db.commit()
    except _UndoRejected as rejected:
        db.rollback()
        return _fail(rejected.error, rejected.status, code=rejected.code)
    except RevisionError as rev:
        db.rollback()
        return _fail(str(rev), rev.status_code, code=rev.error_code)
    except Exception:  # noqa: BLE001 - 롤백 후 고정 문구 500
        db.rollback()
        logger.exception("[ORDERS] item construction-done undo 오류 order_id=%s", order_id)
        return _fail(_ERR_SERVER, 500)

    resp = jsonify({"success": True, "data": {"uid": uid}, "error": None})
    for header, value in outcome.headers.items():
        resp.headers[header] = value
    return resp


__all__ = [
    "ITEM_CONSTRUCTION_DONE_UNDO_POLICY_ID",
    "ITEM_CONSTRUCTION_DONE_UNDONE",
    "item_construction_done_undo_response",
]
