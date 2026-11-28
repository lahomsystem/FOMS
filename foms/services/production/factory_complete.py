"""공장마다 제작 완료 API 본문(설계서 2026-11-23 §4-4 · §4-14 · §7 ``POST /api/orders/<id>/production/factory-done``, 3단계 ⑥).

판정 · 쓰기 순서(주문 행 잠금 아래 — 두 공장 마지막 검수가 동시에 와도 한쪽만 '마지막'):
공장 문(:func:`~foms.services.production.part_access.can_finish_factory` — 403 ``FACTORY_FORBIDDEN``) → 완료 취소면 반장 · 관리자
문(:func:`~foms.services.production.part_access.can_revert_completed` — 403 ``LEAD_REQUIRED`` "[2공장 완료 취소]는 반장이나 관리자만 할
수 있어요.", 사장님 2026-11-28 · 공장 범위는 앞 문 그대로) → 그 공장 장이 있음
(409 ``NO_FACTORY_SHEETS``) → 생산 단계(409 ``INVALID_STAGE`` — 이미 시공 대기면 "그사이 윤검수가 제작 완료했어요. …") →
완료 취소면 그 공장 표지만 지움 → 이미 살아 있으면 같은 사람 200(바뀜 없음) · 다른 사람 409 ``FACTORY_DONE_ALREADY`` → 보류(409
``HOLD_ACTIVE``) → 도면 고치는 중(409 ``DRAWING_REVISING`` — 사장님 2026-11-25 "제작 완료도 막기", 보류와 같은 자리 · 같은 꼴 · 글은
``REVISING_MESSAGE``, 완료 취소는 보류처럼 된다. 2026-11-25 설계서 §4-3: 주문 통째 또는 그 공장에 막힌 도면 · 마지막 공장이면 막힌 도면
하나라도 — 도면별이면 ``numbers``) → 그 공장 장 네 파트 완료(409 ``FACTORY_NOT_READY`` + ``left``) → 다른 있는 공장이 모두 살아 있으면 **마지막** =
제작 완료 길 그대로(:func:`~foms.services.production.complete_order._apply_complete_side_effects` 가 남은 표지를 같이 씀) → 시공
대기, 아니면 표지만(버전 +1 · 이벤트 ``PRODUCTION_FACTORY_COMPLETED``).

응답 ``{success, data: {factory_done: {"1": 표지|None, "2": …}, stage, final, changed}, error}``. 거절은 ``data.code``.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from flask import jsonify
from sqlalchemy.orm.attributes import flag_modified

from foms.services.erp_display import _ensure_dict
from foms.services.orders.drawing_fix import blocked, factory_complete_blocked, per_drawing_numbers
from foms.services.orders.drawing_factory import factory_done_entry, present_factories
from foms.services.orders.order_transition_service import TransitionError
from foms.services.orders.revision import RevisionError, execute_order_mutation, lock_order_row
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.complete_order import (
    FACTORY_COMPLETED_EVENT,
    FACTORY_UNCOMPLETED_EVENT,
    POLICY_FACTORY_DONE,
    AuditFn,
    _apply_complete_side_effects,
    _done_table,
    _transition_complete,
    clear_factory_marks,
    write_factory_done,
)
from foms.services.production.factory_constants import factory_label
from foms.services.production.factory_home import factory_left_message
from foms.services.production.order_write_helpers import (
    _hold_active,
    _is_rework_completion,
    _request_hash,
    _scope_hash,
    _stage_quest_block,
    _steps_incomplete_block,
    _transition_error_response,
)
from foms.services.production.part_access import (
    LEAD_ONLY_STEPS_CODE,
    can_finish_factory,
    can_revert_completed,
    factory_uncomplete_lead_only_message,
)
from foms.services.production.part_mark_gates import DRAWING_REVISING, HOLD_MESSAGE, REVISING_MESSAGE
from foms.services.production.part_mark_rules import subject_particle
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import complete_state
from models import Order, OrderEvent

logger = logging.getLogger(__name__)


def _fail(status: int, code: str, message: str, **extra: Any) -> Any:
    return jsonify({"success": False, "data": {"code": code, **extra}, "error": message}), status


def _done_by_other_message(sd: dict[str, Any], factory: Optional[int] = None) -> str:
    """그사이 남이 완료(§4-4) — "그사이 윤검수가 제작 완료했어요. 더 할 일은 없어요." · 공장이면 "그사이 강검수가 2공장 제작 완료했어요. …"."""
    if factory is not None:
        name = str((factory_done_entry(sd, factory) or {}).get("by_name") or "").strip()
        what = f"{factory_label(factory)} 제작 완료"
    else:
        history = ((sd.get("workflow") or {}).get("history") or []) if isinstance(sd.get("workflow"), dict) else []
        last = next((h for h in reversed(history) if isinstance(h, dict) and h.get("stage") == "CONSTRUCTION"), {})
        name, what = str(last.get("updated_by") or "").strip(), "제작 완료"
    who = f"{subject_particle(name)} " if name else ""
    return f"그사이 {who}{what}했어요. 더 할 일은 없어요."


def _revising_fail(sd: dict[str, Any], factory: int, final: bool) -> Optional[Any]:
    """도면 고치는 중 막힘 — 주문 통째(지금 그대로) · 그 공장에 막힌 도면 · 마지막 공장이면 막힌 도면 하나라도(= [제작 완료] 판정,
    2026-11-25 설계서 §4-3 지휘 풀이). 도면별 막힘은 자료에 ``numbers``(막힌 장 번호)를 싣는다. 안 막히면 None."""
    block = blocked(sd)
    if block.whole:
        return _fail(409, DRAWING_REVISING, REVISING_MESSAGE)
    if not factory_complete_blocked(sd, factory, final=final, block=block):
        return None
    numbers = per_drawing_numbers(sd, block=block, factory=None if final else factory)
    return _fail(409, DRAWING_REVISING, REVISING_MESSAGE, factory=factory, numbers=numbers)


def factory_done_payload(sd: Any) -> dict[str, Any]:
    """응답 ``factory_done`` — 있는 공장마다 살아 있는 표지(없으면 None)."""
    return {str(f): factory_done_entry(sd, f) for f in present_factories(sd)}


def _factory_gate(db: Any, order: Optional[Order], user: Any, factory: int, done: bool) -> Optional[Any]:
    """공장 완료 전 게이트(잠금 아래) — 막히면 응답 튜플."""
    if order is None or order.status == "DELETED" or order.deleted_at is not None:
        return _fail(404, "NOT_FOUND", "주문을 찾을 수 없어요.")
    if not can_finish_factory(user, factory):
        return _fail(403, "FACTORY_FORBIDDEN", f"{factory_label(factory)} 제작 완료는 {factory_label(factory)} 계정이나 관리자만 할 수 있어요.",
                     factory=factory)
    if not done and not can_revert_completed(user):  # 공장 완료 취소 = 반장 · 관리자만(사장님 2026-11-28, [완료 취소]와 같은 함수)
        return _fail(403, LEAD_ONLY_STEPS_CODE, factory_uncomplete_lead_only_message(factory), factory=factory)
    sd =_ensure_dict(order.structured_data)
    if factory not in present_factories(sd):
        return _fail(409, "NO_FACTORY_SHEETS", f"이 주문에는 {factory_label(factory)} 도면이 없어요.", factory=factory)
    stage = read_main_stage(order)
    if stage != "PRODUCTION":
        later = order.erp_stage_code in ("시공", "CONSTRUCTION") or stage in ("CONSTRUCTION", "CS", "COMPLETED")
        message = _done_by_other_message(sd) if later and done else "생산 단계 주문이 아니에요. 다시 받아 주세요."
        return _fail(409, "INVALID_STAGE", message, stage=stage)
    return None


def _write_mark(db: Any, order: Order, user: Any, factory: int, done: bool, body: dict[str, Any],
                idem_key: Optional[str], audit: AuditFn) -> Any:
    """마지막이 아닌 공장 완료 · 공장 완료 취소 — 표지만(단계 그대로, 버전 +1, 이벤트 · 감사). 다시 보냄(replay)은 바뀜 없음 · 감사 0."""
    order_id = int(order.id)
    user_id = getattr(user, "id", None)
    label = factory_label(factory)

    def _mutate(sess: Any, locked: list[Order]) -> dict[int, list[str]]:
        target = locked[0]
        sd = copy.deepcopy(_ensure_dict(target.structured_data))
        entry = write_factory_done(sd, factory, user) if done else None
        if not done:
            clear_factory_marks(sd, (factory,))
        target.structured_data = sd
        flag_modified(target, "structured_data")
        payload = {"factory": factory, "domain": "PRODUCTION_DOMAIN", "by_name": getattr(user, "name", None),
                   "action": FACTORY_COMPLETED_EVENT if done else FACTORY_UNCOMPLETED_EVENT}
        if entry is not None:
            payload["keys"] = entry["keys"]
        sess.add(OrderEvent(order_id=order_id, event_type=payload["action"], payload=payload, created_by_user_id=user_id))
        return {order_id: [f"ORDER_DETAIL:{order_id}", "ORDERS_INDEX"]}

    try:
        result = execute_order_mutation(db, actor_user_id=user_id, policy_id=POLICY_FACTORY_DONE, order_ids=[order_id],
                                        scope_hash=_scope_hash(f"PRODUCTION_FACTORY_DONE:{factory}", order_id),
                                        request_hash=_request_hash(body), idempotency_key=idem_key, mutation=_mutate)
    except RevisionError as exc:
        db.rollback()
        return _transition_error_response(exc)
    if not result.replayed:  # 같은 멱등 열쇠로 다시 온 요청(쓰기 0)은 감사 줄을 더 쓰지 않는다
        audit(order, FACTORY_COMPLETED_EVENT if done else FACTORY_UNCOMPLETED_EVENT, user_id,
              note=f"{label} 제작 완료" if done else f"{label} 완료 취소", extra={"factory": factory})
    db.commit()
    sd = _ensure_dict(order.structured_data)
    return jsonify({"success": True, "data": {"factory_done": factory_done_payload(sd), "stage": "PRODUCTION", "final": False,
                                              "changed": not result.replayed}, "error": None})


def _final_complete(db: Any, order: Order, user: Any, sd: dict[str, Any], marks: list[Any], body: dict[str, Any],
                    idem_key: Optional[str], audit: AuditFn) -> Any:
    """마지막 공장 완료 = 지금 제작 완료 길(승인 · 남은 단계 게이트 → 전이 → 곁일이 남은 표지를 같은 deepcopy 에 씀) → 시공 대기."""
    for blocked in (_stage_quest_block(sd, "PRODUCTION", "생산"), _steps_incomplete_block(sd, marks)):
        if blocked is not None:
            return blocked
    user_id = getattr(user, "id", None)
    try:
        result = _transition_complete(db, int(order.id), user_id, read_main_stage(order), body, idem_key, None)
    except (TransitionError, RevisionError) as exc:
        db.rollback()
        return _transition_error_response(exc)
    if not result.replayed:
        _apply_complete_side_effects(db, order, user, user_id, False, False, _is_rework_completion(sd), result.event_id,
                                     audit=audit)
    db.commit()
    sd = _ensure_dict(order.structured_data)
    return jsonify({"success": True, "data": {"factory_done": factory_done_payload(sd), "stage": "CONSTRUCTION", "final": True,
                                              "changed": True}, "error": None})


def finish_factory(db: Any, order_id: int, user: Any, body: dict[str, Any], idem_key: Optional[str], *, factory: int,
                   done: bool, audit: AuditFn) -> Any:
    """공장 제작 완료 · 완료 취소(§4-14) — 응답 튜플. 잠금 아래에서 판정(두 공장 마지막 검수가 동시에 와도 한쪽만 '마지막').

    Args:
        db: 세션(커밋은 여기서).
        order_id: 주문.
        user: 누른 사람(이미 읽은 행).
        body: 요청 몸(영수증 hash).
        idem_key: 멱등 열쇠(없으면 None).
        factory: 1 · 2.
        done: True = 공장 완료, False = 공장 완료 취소.
        audit: 감사 한 줄 함수(API 층).
    """
    try:
        order = lock_order_row(db, order_id)
        blocked = _factory_gate(db, order, user, factory, done)
        if blocked is not None:
            return blocked
        sd = _ensure_dict(order.structured_data)
        alive = factory_done_entry(sd, factory)
        if not done:
            if str(factory) not in _done_table(sd):
                return jsonify({"success": True, "data": {"factory_done": factory_done_payload(sd), "stage": "PRODUCTION",
                                                          "final": False, "changed": False}, "error": None})
            return _write_mark(db, order, user, factory, False, body, idem_key, audit)
        if alive is not None:
            if alive.get("by_user_id") not in (None, getattr(user, "id", None)):
                return _fail(409, "FACTORY_DONE_ALREADY", _done_by_other_message(sd, factory), factory=factory)
            return jsonify({"success": True, "data": {"factory_done": factory_done_payload(sd), "stage": "PRODUCTION",
                                                      "final": False, "changed": False}, "error": None})
        if _hold_active(sd)[0]:
            return _fail(409, "HOLD_ACTIVE", HOLD_MESSAGE)
        others = [f for f in present_factories(sd) if f != factory]
        final = all(factory_done_entry(sd, f) is not None for f in others)
        revising = _revising_fail(sd, factory, final)  # 보류와 같은 자리(2026-11-25) — 마지막 공장(= 주문 제작 완료)도 여기서 막힌다
        if revising is not None:
            return revising
        marks = order_marks(db, order_id)
        state = complete_state(sd, marks, factory=factory)
        if not state["ready"]:
            return _fail(409, "FACTORY_NOT_READY", factory_left_message(factory, state), factory=factory, left=state["left"])
        if final:
            return _final_complete(db, order, user, sd, marks, body, idem_key, audit)
        return _write_mark(db, order, user, factory, True, body, idem_key, audit)
    except Exception:  # noqa: BLE001 - 최종 방어(구체 예외는 위에서 매핑) — 되감고 로그를 남긴 뒤 해요체 한 문장
        db.rollback()
        logger.exception("[PRODUCTION] factory-done failed order=%s factory=%s", order_id, factory)
        return _fail(500, "SAVE_FAILED", "저장하지 못했어요. 잠시 뒤 다시 해 주세요.")
