"""파트 카드 표시 → 주문 공정 칸 동기화(설계서 §15.5 — 총괄 안 그대로).

규칙: 한 주문 · 한 파트에서 지금 확정 도면(:func:`resolve_final_drawing_files`)의 **모든 장**이 끝이면 그 공정 칸을
켜고, 하나라도 끝이 아니면(되돌리기 · 새 도면 · 아무도 안 고른 장 — D57 '아직') 끈다. 끝 = 재단은 DONE 또는 BASIC,
그 밖 파트는 DONE. 확정 도면이 0장이면 건드리지 않는다. **카드로 일한 파트만** — 그 주문 · 그 파트에 표시 줄이
하나라도 있을 때(옛 key · NONE 포함)만 맞춘다. 카드를 안 쓴 주문은 손으로 켠 값을 그대로 둔다.

* 순수 계산: :func:`part_steps_after` · :func:`plan_part_step_changes` · :func:`apply_part_step_changes` ·
  :func:`step_event_rows` — DB · commit 없이 sd dict 와 표시 줄 모습만 본다. 칸 바꾸기는 지금 공정 API 와 같은
  :func:`foms.services.production.steps.set_production_step` 이다.
* 도면 쓰기 셋 잇기: :func:`sync_steps_in_drawing_write` — 전달 · 전달 취소 되살리기 · 확정 뒤 품목 취소가 생산 ·
  시공 단계 주문에서 돌 때, 이미 고치는 deepcopy 안에서 공정 칸만 더 바꾼다(표시 읽기 쿼리 1, 주문 JSON 다시 쓰기 0).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import insert

from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_transfer import is_drawing_hotfix_stage
from foms.services.production.part_constants import (
    BASIC_ALLOWED_PART,
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    PRODUCTION_PART_KEYS,
)
from foms.services.production.steps import set_production_step, step_done_map
from models import OrderEvent, ProductionPartMark

STEP_EVENT = "PRODUCTION_STEP_CHECKED"
#: 이벤트 payload ``via`` — 공정 칸을 사람이 아니라 파트 카드 동기화가 바꿨다는 표지.
VIA_PART_MARKS = "part_marks"
#: 도면 쓰기 셋의 ``trigger``(표시 API 길은 trigger 없음).
TRIGGER_TRANSFER = "drawing_transfer"
TRIGGER_TRANSFER_CANCEL = "drawing_transfer_cancel"
TRIGGER_ITEM_CANCEL = "item_cancel_after_confirm"


@dataclass(frozen=True)
class StepChange:
    """공정 칸 하나의 바뀜 — 켤 때 ``by_name`` = 그 파트에서 마지막으로 끝낸 사람."""

    key: str
    done: bool
    by_name: Optional[str] = None


def _finished(part: str, state: Optional[str]) -> bool:
    if part == BASIC_ALLOWED_PART:
        return state in (MARK_STATE_DONE, MARK_STATE_BASIC)
    return state == MARK_STATE_DONE


def _marks_by_part(marks: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """파트 → (장 key → 표시 줄). 모르는 파트는 버린다."""
    out: dict[str, dict[str, Any]] = {}
    for mark in marks:
        part = getattr(mark, "part", None)
        if part in PRODUCTION_PART_KEYS:
            out.setdefault(part, {})[str(getattr(mark, "drawing_key", "") or "")] = mark
    return out


def part_steps_after(sd: Any, marks: Iterable[Any]) -> dict[str, bool]:
    """카드로 일한 파트마다 공정 칸이 있어야 할 값.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문의 표시 줄들(``part`` · ``drawing_key`` · ``state`` 를 읽는다 — ORM 줄 또는 같은 모양).

    Returns:
        ``{파트 key: done}`` — 표시 줄이 있는 파트만. 확정 도면이 0장이면 빈 dict(건드리지 않음).
    """
    keys = [entry["key"] for entry in resolve_final_drawing_files(sd)]
    if not keys:
        return {}
    by_part = _marks_by_part(marks)
    return {
        part: all(_finished(part, getattr(by_part[part].get(key), "state", None)) for key in keys)
        for part in PRODUCTION_PART_KEYS if part in by_part
    }


def _last_finisher(sd: Any, marks: dict[str, Any]) -> Optional[str]:
    """지금 확정 도면 장들 중 마지막으로 끝낸 사람 이름(``done_at`` 가장 늦은 줄)."""
    keys = [entry["key"] for entry in resolve_final_drawing_files(sd)]
    rows = [marks[k] for k in keys if k in marks and getattr(marks[k], "done_by_name", None)]
    if not rows:
        return None
    floor = datetime.datetime.min
    return getattr(max(rows, key=lambda r: getattr(r, "done_at", None) or floor), "done_by_name", None)


def plan_part_step_changes(sd: Any, marks: Iterable[Any]) -> list[StepChange]:
    """지금 칸과 다른 것만 — 바꿀 칸이 없으면 빈 목록(부르는 쪽은 쓰지 않는다 · 버전 그대로)."""
    marks = list(marks)
    wanted = part_steps_after(sd, marks)
    if not wanted:
        return []
    current = step_done_map(sd)
    by_part = _marks_by_part(marks)
    return [
        StepChange(part, done, _last_finisher(sd, by_part[part]) if done else None)
        for part, done in wanted.items() if current.get(part, False) != done
    ]


def apply_part_step_changes(sd: dict[str, Any], changes: Iterable[StepChange], *, at_iso: str) -> None:
    """바뀜을 sd 에 제자리 적용(호출자가 deepcopy 한 dict) — 지금 공정 API 와 같은 칸 바꾸기 함수."""
    for change in changes:
        set_production_step(sd, change.key, change.done, by_name=change.by_name, at_iso=at_iso)


def step_event_rows(order_id: int, changes: Iterable[StepChange], *, actor_user_id: Optional[int],
                    trigger: Optional[str] = None) -> list[dict[str, Any]]:
    """``PRODUCTION_STEP_CHECKED`` 이벤트 줄(칸마다 하나, payload ``via: 'part_marks'``)."""
    now = now_utc_naive()
    rows = []
    for change in changes:
        payload = {"key": change.key, "done": change.done, "domain": "PRODUCTION_DOMAIN", "action": STEP_EVENT,
                   "via": VIA_PART_MARKS}
        if trigger:
            payload["trigger"] = trigger
        rows.append({"order_id": int(order_id), "event_type": STEP_EVENT, "payload": payload,
                     "created_by_user_id": actor_user_id, "created_at": now})
    return rows


def step_change_body(order_id: int, change: StepChange) -> dict[str, Any]:
    """응답 ``order_step`` 한 칸."""
    return {"order_id": int(order_id), "key": change.key, "done": change.done}


def sync_steps_in_drawing_write(db: Any, order: Any, sd: dict[str, Any], *, actor_user_id: Optional[int],
                                trigger: str) -> list[dict[str, Any]]:
    """도면 쓰기 셋이 고치는 같은 deepcopy(``sd``) 안에서 공정 칸만 더 맞춘다.

    생산 · 시공 단계(도면 바로 반영 단계) 주문에서만 표시 줄을 한 번 읽는다(그 밖 단계는 쿼리 0). 칸이 바뀌면
    이벤트 ``PRODUCTION_STEP_CHECKED``(``via: 'part_marks'`` · ``trigger``)를 같은 tx 에 싣는다. 재대입 ·
    ``flag_modified`` · 버전은 도면 쓰기가 이미 하는 것을 그대로 쓴다.

    Args:
        db: 세션(같은 tx).
        order: 잠근 주문(단계 판정).
        sd: 쓸 structured_data 사본(제자리 수정).
        actor_user_id: 누른 사람.
        trigger: :data:`TRIGGER_TRANSFER` 등.

    Returns:
        바뀐 칸 ``[{order_id, key, done}]``.
    """
    if not is_drawing_hotfix_stage(order):
        return []
    marks = db.query(ProductionPartMark).filter(ProductionPartMark.order_id == order.id).all()
    changes = plan_part_step_changes(sd, marks)
    if not changes:
        return []
    apply_part_step_changes(sd, changes, at_iso=datetime.datetime.now(datetime.timezone.utc).isoformat())
    db.execute(insert(OrderEvent), step_event_rows(order.id, changes, actor_user_id=actor_user_id, trigger=trigger))
    return [step_change_body(order.id, change) for change in changes]
