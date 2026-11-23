"""파트 카드 표시 → 주문 공정 칸 동기화(설계서 §15.5 — 총괄 안 그대로).

규칙: 한 주문 · 한 파트에서 지금 확정 도면(:func:`resolve_final_drawing_files`)의 **모든 장**이 끝이면 그 공정 칸을
켜고, 하나라도 끝이 아니면(되돌리기 · 새 도면 · 아무도 안 고른 장 — D57 '아직') 끈다. 끝 = 재단은 DONE 또는 BASIC,
그 밖 파트는 DONE. 확정 도면이 0장이면 건드리지 않는다. **카드를 쓴 파트만** — 그 주문 · 그 파트에 상태가 NONE 이
아닌 표시 줄이 하나라도 있을 때(옛 key 포함)만 맞춘다(설계서 2026-11-23 §4-2 B5′ — 2026-11-13 판은 NONE 줄만 있어도
맞춰서 맡기만 해도 손으로 켠 칸이 꺼졌다). 카드를 안 쓴 파트는 손으로 켠 값을 그대로 둔다. 켤 때 칸 ``via`` =
``'part_marks'``.

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
from foms.services.production.part_constants import PRODUCTION_PART_KEYS
from foms.services.production.part_progress import cards_used, mark_finished, marks_by_part
from foms.services.production.steps import STEP_VIA_PART_MARKS, set_production_step, step_done_map
from models import OrderEvent, ProductionPartMark

STEP_EVENT = "PRODUCTION_STEP_CHECKED"
#: 이벤트 payload · 공정 칸 ``via`` — 공정 칸을 사람이 아니라 파트 카드 동기화가 바꿨다는 표지.
VIA_PART_MARKS = STEP_VIA_PART_MARKS
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


def part_steps_after(sd: Any, marks: Iterable[Any], parts: Optional[Iterable[str]] = None) -> dict[str, bool]:
    """카드를 쓴 파트마다 공정 칸이 있어야 할 값.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문의 표시 줄들(``part`` · ``drawing_key`` · ``state`` 를 읽는다 — ORM 줄 또는 같은 모양).
        parts: 맞출 파트만(None = 네 파트). 표시 쓰기는 누른 파트만 맞춘다 — 옛 칸은 그 파트의 다음 카드 쓰기 때(§4-2).

    Returns:
        ``{파트 key: done}`` — 카드를 쓴 파트만. 확정 도면이 0장이면 빈 dict(건드리지 않음).
    """
    keys = [entry["key"] for entry in resolve_final_drawing_files(sd)]
    if not keys:
        return {}
    marks = list(marks)
    used = cards_used(marks)
    wanted = set(PRODUCTION_PART_KEYS if parts is None else parts)
    by_part = marks_by_part(marks)
    return {
        part: all(mark_finished(part, getattr(by_part[part].get(key), "state", None)) for key in keys)
        for part in PRODUCTION_PART_KEYS if part in used and part in wanted
    }


def _last_finisher(sd: Any, marks: dict[str, Any]) -> Optional[str]:
    """지금 확정 도면 장들 중 마지막으로 끝낸 사람 이름(``done_at`` 가장 늦은 줄)."""
    keys = [entry["key"] for entry in resolve_final_drawing_files(sd)]
    rows = [marks[k] for k in keys if k in marks and getattr(marks[k], "done_by_name", None)]
    if not rows:
        return None
    return getattr(max(rows, key=_finish_order), "done_by_name", None)


def _finish_order(row: Any) -> tuple[datetime.datetime, bool, int]:
    """'누가 마지막에 끝냈나' 순서 — ``done_at`` → 이번 요청이 막 쓴 줄 → 줄 id.

    시계 눈금이 거칠면(Windows 약 15ms) 두 사람의 ``done_at`` 이 같다. 그때 ``max`` 는 첫 줄을 돌려줘 먼저 끝낸
    사람 이름이 적혔다. 표시 API 는 이번 쓰기를 저장 전 모습(``id`` 없음)으로 넘기므로, id 가 없는 줄은 저장된
    어떤 줄보다 늦다(방금 쓴 것). 저장된 줄끼리는 id(만든 차례)로 가른다.
    """
    row_id = getattr(row, "id", None)
    return (getattr(row, "done_at", None) or datetime.datetime.min, row_id is None, row_id or 0)


def plan_part_step_changes(sd: Any, marks: Iterable[Any], parts: Optional[Iterable[str]] = None) -> list[StepChange]:
    """지금 칸과 다른 것만 — 바꿀 칸이 없으면 빈 목록(부르는 쪽은 쓰지 않는다 · 버전 그대로). ``parts`` 는
    :func:`part_steps_after` 와 같다."""
    marks = list(marks)
    wanted = part_steps_after(sd, marks, parts)
    if not wanted:
        return []
    current = step_done_map(sd)
    by_part = marks_by_part(marks)
    return [
        StepChange(part, done, _last_finisher(sd, by_part[part]) if done else None)
        for part, done in wanted.items() if current.get(part, False) != done
    ]


def apply_part_step_changes(sd: dict[str, Any], changes: Iterable[StepChange], *, at_iso: str) -> None:
    """바뀜을 sd 에 제자리 적용(호출자가 deepcopy 한 dict) — 지금 공정 API 와 같은 칸 바꾸기 함수."""
    for change in changes:
        set_production_step(sd, change.key, change.done, by_name=change.by_name, at_iso=at_iso, via=VIA_PART_MARKS)


def step_event_rows(order_id: int, changes: Iterable[StepChange], *, actor_user_id: Optional[int],
                    trigger: Optional[str] = None, actor_name: Optional[str] = None) -> list[dict[str, Any]]:
    """``PRODUCTION_STEP_CHECKED`` 이벤트 줄(칸마다 하나, payload ``via: 'part_marks'``).

    ``actor_name`` 을 주면 payload ``by_name``(누른 사람 이름 스냅샷 — 바뀐 기록 목록이 사용자 표를 다시 읽지 않게)."""
    now = now_utc_naive()
    rows = []
    for change in changes:
        payload = {"key": change.key, "done": change.done, "domain": "PRODUCTION_DOMAIN", "action": STEP_EVENT,
                   "via": VIA_PART_MARKS}
        if actor_name:
            payload["by_name"] = actor_name
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
