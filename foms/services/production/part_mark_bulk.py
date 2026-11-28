"""생산 파트 표시 쓰기 — 재단 일괄 기본([남은 N장 모두 기본], 설계서 §15.4 · 2026-11-23 §4-5 ~ §4-8).

:mod:`~foms.services.production.part_mark_write` 가 500줄 래칫에 닿아 일괄 기본 셋(주문 잠금 · 장 하나 판정 · 일괄 쓰기)을 여기로
옮겼다(2026-11-28 — 동작 그대로). 한 장 쓰기와 같은 검사 · 같은 빌더(``plan_write`` · ``flush_writes`` · ``apply_order_changes`` ·
``write_audit``)를 쓴다. 표시는 바뀐 주문을 모아 ``execute_order_mutation`` 한 번으로 쓴다(주문마다 버전 +1 한 번).
"""

from __future__ import annotations

from typing import Any, Optional

from foms.services.production.factory_scope import factory_gate
from foms.services.production.part_constants import BASIC_ALLOWED_PART
from foms.services.production.part_mark_decide import decide_mark
from foms.services.production.part_mark_gates import hand_step_gate, order_gate
from foms.services.production.part_mark_notes import actor_name
from foms.services.production.part_mark_rules import ACTION_BASIC, DECISION_APPLY, DECISION_CONFLICT, MarkSnapshot
from foms.services.production.part_mark_write import (
    MarkRefusal,
    MarkWrite,
    after_views,
    apply_order_changes,
    check_order,
    current_entry,
    flush_writes,
    mark_body,
    plan_write,
    step_note,
    write_audit,
)
from foms.services.production.part_marks_query import orders_with_current_run
from models import Order, ProductionPartMark


def lock_orders(db: Any, order_ids: list[int]) -> dict[int, Order]:
    """주문들을 id 순으로 한 번에 잠근다(교착 없는 순서 — ``execute_order_mutation`` 과 같은 규칙)."""
    rows = (db.query(Order).filter(Order.id.in_(sorted(set(order_ids)))).order_by(Order.id.asc())
            .populate_existing().with_for_update().all())
    return {int(o.id): o for o in rows}


def _bulk_one(user: Any, admin: bool, order: Optional[Order], key: str, row: Any,
              cut_rows: list[Any]) -> Optional[MarkWrite]:
    """일괄의 장 하나 — 한 장 쓰기와 같은 검사(남의 공장 · 보류 · 도면 고치는 중 · 손 체크 포함). → 쓸 것(이미 내가 기본이면 None).

    Raises:
        MarkRefusal: 이 장만 건너뛸 까닭(``reason`` = 코드).
    """
    order = check_order(order)
    entry = current_entry(order, key)
    decision = decide_mark(MarkSnapshot.from_row(row), action=ACTION_BASIC, seen="none", actor_id=user.id, admin=admin,
                           actor_name=actor_name(user))
    if decision.kind not in (DECISION_APPLY, DECISION_CONFLICT):
        return None
    gate = (factory_gate(user, order.structured_data, entry, action=ACTION_BASIC)
            or order_gate(order.structured_data, ACTION_BASIC, entry)
            or hand_step_gate(order.structured_data, cut_rows, BASIC_ALLOWED_PART))
    if gate is not None:
        raise MarkRefusal.from_gate(gate)
    if decision.kind == DECISION_CONFLICT:
        raise MarkRefusal(409, "MARK_CONFLICT", decision.message)
    return plan_write(order, entry, row, part=BASIC_ALLOWED_PART, target=decision.target, user=user,
                      action=ACTION_BASIC, override=False, decision=decision)


def bulk_basic(db: Any, user: Any, admin: bool, pairs: list[tuple[int, str]]) -> dict[str, Any]:
    """보낸 목록만 기본으로(일부 성공). 주문 잠금 · 표시 줄 읽기 · 회차 찾기 · 감사는 요청마다 한 번씩(장 수와 무관)."""
    orders = lock_orders(db, [oid for oid, _ in pairs])
    rows = (db.query(ProductionPartMark)
            .filter(ProductionPartMark.order_id.in_(sorted(orders)), ProductionPartMark.part == BASIC_ALLOWED_PART)
            .all()) if orders else []
    marks = {(int(m.order_id), str(m.drawing_key)): m for m in rows}
    by_order = after_views(rows, [])
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    writes: list[MarkWrite] = []
    changed: dict[int, list[str]] = {}
    for order_id, key in pairs:
        row = marks.get((order_id, key))
        try:
            write = _bulk_one(user, admin, orders.get(order_id), key, row, by_order.get(order_id, []))
        except MarkRefusal as refusal:
            skipped.append({"order_id": order_id, "drawing_key": key, "reason": refusal.code, "error": refusal.message,
                            "mark": mark_body(row, order_id, key, BASIC_ALLOWED_PART)})
            continue
        if write is not None:
            writes.append(write)
            changed.setdefault(order_id, []).append(key)
        view = write.view if write is not None else row
        applied.append({**mark_body(view, order_id, key, BASIC_ALLOWED_PART), "changed": write is not None})
    if not writes:
        return {"applied": applied, "skipped": skipped, "order_steps": [], "run_started": []}
    flush_writes(db, writes)
    starting = set(changed) - orders_with_current_run(db, list(changed))
    steps, started = apply_order_changes(db, [orders[oid] for oid in changed], after_views(rows, writes), user,
                                         parts=(BASIC_ALLOWED_PART,), starting=starting)
    only = orders[next(iter(changed))] if len(changed) == 1 else None
    start_tail = f" · 제작 시작 {len(started)}건" if started else ""
    write_audit(db, user, f"재단 기본 {len(writes)}장" + step_note(steps) + start_tail,
                {"part": BASIC_ALLOWED_PART, "to": "BASIC", "bulk": True, "order_steps": steps, "run_started": started,
                 "orders": [{"order_id": oid, "keys": keys} for oid, keys in changed.items()]},
                order=only, order_count=len(changed))
    return {"applied": applied, "skipped": skipped, "order_steps": steps, "run_started": started}
