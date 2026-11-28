"""도면이 처음 올라올 때 '도면 없음' 카드를 새 도면 줄로 한 번 옮긴다(설계서 2026-11-28-production-my-steps-flow §3-5 '만드는 꼴' ·
사장님 답 27 "완료 그대로 둠" · 33 "새 도면 2장도 김재단 작업 중" · 35 "손으로 끝낸 것도 똑같이 완료 그대로").

언제: 생산 단계 주문의 확정 도면이 **0장 → n장**이 되는 쓰기 안(같은 tx · 주문 잠금 아래). 지금 그 길은 생산 단계 바로 반영 전달
하나다(``drawing_fix_transfer.apply_fix_writes`` 가 :func:`first_arrival` 일 때 부른다 — 길 전수는 보고서). 그 뒤 도면 쓰기가 늘 하는 공정 칸
맞추기(``part_steps_sync.sync_steps_in_drawing_write``)가 새 줄을 읽어 칸을 켠 채 둔다.

무엇을:

* 미정이 아닌 ``@order`` 줄(완료 · 기본 · 작업 중 + 작업하는 사람 목록 · 완료한 사람 · 시각)을 **새 도면 key 마다** 같은 파트 줄로 넣는다 —
  그 key · 파트 줄이 이미 있으면 건드리지 않는다. 이벤트 ``PRODUCTION_PART_MARKED``(카드 누름과 같은 꼴 · ``via: 'order_card'`` · ``by_name`` =
  그 줄의 사람). 옮긴 ``@order`` 줄은 **미정으로** 돌린다(줄은 기록으로 남긴다 — 표에서 지우는 길은 이 저장소에 없다). 미정이라 '작업 중
  장 수'(공장을 바꾼 사람 안내 · 아침 칩) · '카드를 쓴 파트'에 다시 세지 않는다.
* 반장이 손으로 체크한 파트(칸 켜짐 · 카드 안 씀)는 새 도면 key 마다 완료 줄로 풀어 적는다 — 지금 손 처리 풀어 쓰기 길
  (:func:`~foms.services.production.step_expand.expand_hand_step`, 칸을 켠 사람 · 칸 시각, ``via: 'step_expand'``). 안 풀면 새 장이 '안 봄'이라
  칸 맞추기가 그 칸을 끈다(지금 ``expand_hand_parts`` 가 모든 장이 새 장일 때 하는 일 — 35번 답과 어긋남).
* 나중에 그 도면이 **다시** 바뀌면(key1 → key1′) 확정 도면이 이미 있어 이 길을 타지 않는다 — 지금 규칙 그대로(새 장 미정).
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import insert, update

from foms.services.datetime_kst import now_utc_naive, parse_datetime_utc
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_factory import hand_checked_parts
from foms.services.orders.state_axes import read_main_stage
from foms.services.production import mark_crew as mc
from foms.services.production.order_card import STAGE_PRODUCTION, order_entry
from foms.services.production.part_constants import (
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    MARK_STATE_NONE,
    ORDER_CARD_KEY,
    PRODUCTION_PART_KEYS,
)
from foms.services.production.part_mark_notes import event_payload
from foms.services.production.part_mark_rules import ACTION_BASIC, ACTION_DONE, ACTION_TAKE, MARK_COLUMNS, MarkSnapshot
from foms.services.production.part_mark_write import PART_MARK_EVENT, MarkWrite, plan_write
from foms.services.production.part_progress import marks_by_part
from foms.services.production.step_expand import expand_hand_step
from models import OrderEvent, ProductionPartMark

#: 이벤트 ``via`` · 옮긴 뒤 ``@order`` 줄을 미정으로 돌린 기록 줄의 ``action``(기록용 낱말 — 쓰기 API 가 받는 누름이 아니다).
VIA_ORDER_CARD = "order_card"
ACTION_ORDER_CARD = "order_card"
#: 옮긴 줄 이벤트의 ``action`` — 그 상태가 되는 누름(바뀐 기록이 "맡음" · "완료" · "기본"으로 읽는다).
_COPY_ACTIONS = {MARK_STATE_NEED: ACTION_TAKE, MARK_STATE_DONE: ACTION_DONE, MARK_STATE_BASIC: ACTION_BASIC}


def first_arrival(order: Any, sd: Any) -> bool:
    """이 쓰기가 생산 단계 주문의 확정 도면을 0장 → n장으로 바꾸는지 — ``order.structured_data`` = 쓰기 전(잠근 행), ``sd`` = 쓸 사본."""
    before = getattr(order, "structured_data", None)
    return (read_main_stage(order) == STAGE_PRODUCTION and not resolve_final_drawing_files(before if isinstance(before, dict) else {})
            and bool(resolve_final_drawing_files(sd if isinstance(sd, dict) else {})))


def _worker_name(row: Any) -> Optional[str]:
    """옮긴 줄 이벤트의 ``by_name`` — 완료 · 기본 = 완료한 사람, 작업 중 = 맡은 사람(목록 첫 사람)."""
    if str(row.state) in (MARK_STATE_DONE, MARK_STATE_BASIC):
        return row.done_by_name or None
    return row.picked_by_name or None


def _copy(order: Any, src: Any, entry: dict[str, Any], part: str, user: Any, now: datetime.datetime) -> tuple[dict, dict]:
    """``@order`` 줄 → 새 도면 key 줄 값 · 이벤트(사람 · 시각 · 목록 그대로, 쓴 사람 · 쓴 때만 이번 쓰기)."""
    values = {column: getattr(src, column, None) for column in MARK_COLUMNS}
    values.update(order_id=int(order.id), drawing_key=entry["key"], sheet_id=entry.get("sheet_id"), part=part,
                  holders=copy.deepcopy(src.holders), updated_by_user_id=getattr(user, "id", None), updated_at=now)
    state = str(src.state)
    payload = event_payload(entry, MarkSnapshot(), part=part, target=state, user=user, action=_COPY_ACTIONS[state], override=False,
                            crew_after=mc.crew_of(src))
    payload.update(via=VIA_ORDER_CARD, by_name=_worker_name(src))
    event = {"order_id": int(order.id), "event_type": PART_MARK_EVENT, "created_by_user_id": getattr(user, "id", None),
             "created_at": now, "payload": payload}
    return values, event


def _clear(order: Any, src: Any, part: str, keys: list[str], user: Any, now: datetime.datetime) -> MarkWrite:
    """옮긴 ``@order`` 줄을 미정으로(같은 빌더 — 수정 제작의 미정 돌리기와 같은 꼴), 이벤트에 옮긴 key 들."""
    write = plan_write(order, order_entry(), src, part=part, target=MARK_STATE_NONE, user=user, action=ACTION_ORDER_CARD,
                       override=False, now=now)
    write.event["payload"].update(via=VIA_ORDER_CARD, to_keys=keys)
    return write


def _naive_utc(raw: Any) -> Optional[datetime.datetime]:
    aware = parse_datetime_utc(raw) if raw else None
    return aware.replace(tzinfo=None) if aware is not None else None


def _hand_parts(db: Any, order: Any, sd: dict[str, Any], marks: list[Any], user: Any, now: datetime.datetime) -> list[str]:
    """손으로 체크한 파트(칸 켜짐 · 카드 안 씀)를 새 도면 key 마다 완료로 풀어 적는다 — 칸을 켠 사람 · 칸 시각(35번 답)."""
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = {str(s.get("key")): s for s in production.get("steps") or [] if isinstance(s, dict)}
    done: list[str] = []
    for part in hand_checked_parts(sd, marks):
        step = steps.get(part) or {}
        expand_hand_step(db, order, sd, marks, part, exclude_keys=(), user=user, done_by_name=str(step.get("by_name") or "").strip(),
                         done_at=_naive_utc(step.get("at")) or now)
        done.append(part)
    return done


def carry_order_card(db: Any, order: Any, sd: dict[str, Any], marks: Iterable[Any], *, user: Any) -> list[str]:
    """도면이 처음 왔을 때 옮기기(모듈 머리말) — 부르는 쪽이 :func:`first_arrival` 을 이미 봤다. 표마다 문 한 번(장 · 파트 수와 무관).

    Args:
        db: 세션(같은 tx — 주문은 잠겨 있다).
        order: 잠근 주문.
        sd: 쓸 ``structured_data`` 사본(새 확정 도면이 들어 있다 — 읽기만).
        marks: 그 주문 표시 줄(잠금 아래에서 읽은 것 — 쓴 뒤 세션에서 만료시켜 뒤 칸 맞추기가 새 값을 다시 읽게 한다).
        user: 보낸 사람(쓴 사람 · 이벤트 사람).

    Returns:
        옮긴 파트 key 들(``@order`` 줄 · 손 체크, 공정 순서).
    """
    marks = list(marks)
    entries = resolve_final_drawing_files(sd)
    by_part = marks_by_part(marks)
    now = now_utc_naive()
    inserts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    clears: list[MarkWrite] = []
    carried: list[str] = []
    for part in PRODUCTION_PART_KEYS:
        rows = by_part.get(part, {})
        src = rows.get(ORDER_CARD_KEY)
        if src is None or str(src.state or MARK_STATE_NONE) not in _COPY_ACTIONS:
            continue
        keys: list[str] = []
        for entry in entries:
            if entry["key"] in rows or entry["key"] in keys:  # 이미 그 key · 파트 줄이 있으면 그대로(같은 key 두 번도 한 줄)
                continue
            values, event = _copy(order, src, entry, part, user, now)
            inserts.append(values)
            events.append(event)
            keys.append(entry["key"])
        clears.append(_clear(order, src, part, keys, user, now))
        carried.append(part)
    if inserts:
        db.execute(insert(ProductionPartMark), inserts)
    if clears:
        db.execute(update(ProductionPartMark), [{"id": w.row_id, **w.values} for w in clears])
        events += [w.event for w in clears]
    if events:
        db.execute(insert(OrderEvent), events)
    hand = _hand_parts(db, order, sd, marks, user, now)
    if carried or hand:
        for row in marks:  # 표 문은 세션 사본을 모른다 — 뒤 칸 맞추기(sync_steps_in_drawing_write)가 다시 읽을 때 새 값을 보게
            db.expire(row)
    return [part for part in PRODUCTION_PART_KEYS if part in carried or part in hand]


__all__ = ["ACTION_ORDER_CARD", "VIA_ORDER_CARD", "carry_order_card", "first_arrival"]
