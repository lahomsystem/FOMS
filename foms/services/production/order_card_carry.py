"""도면이 처음 올라올 때 '도면 없음' 카드를 새 도면 줄로 한 번 옮긴다(설계서 2026-11-28-production-my-steps-flow §3-5 '만드는 꼴' ·
사장님 답 27 "완료 그대로 둠" · 33 "새 도면 2장도 김재단 작업 중" · 35 "손으로 끝낸 것도 똑같이 완료 그대로").

언제(같은 tx · 주문 잠금 아래, 표시 줄 읽기 한 번):

* 도면 바로 반영 단계(생산 · 시공) 전달이 확정 도면을 **0장 → n장**으로 바꿀 때, 또는 확정 도면이 1장 이상인데 미정 아닌 ``@order`` 줄이
  남아 있을 때(:func:`leftover_order_card`) — ``drawing_fix_transfer.apply_fix_writes`` 가 부른다. 그 뒤 도면 쓰기가 늘 하는 공정 칸
  맞추기(``part_steps_sync.sync_steps_in_drawing_write`` — 생산 · 시공)가 새 줄을 읽어 칸을 켠 채 둔다.
* 주문이 **생산 단계로 들어가는** 쓰기에서 확정 도면이 1장 이상인데 미정 아닌 ``@order`` 줄이 남아 있을 때 — 생산 → 앞 단계로 강제
  되돌림 → 도면 받음(바로 반영 단계가 아니라 위 길을 안 탐) → 다시 생산(사장님 2026-11-28 "고침", ⓑ 검토 2).
  :func:`carry_on_production_entry` — 단계 쓰기 자리마다 부르는 ``drawing_fix_marks.release_on_stage_exit`` 가 부른다.

옮긴 ``@order`` 줄은 미정이 되므로 다시 타지 않는다(한 번).

무엇을:

* 미정이 아닌 ``@order`` 줄(완료 · 기본 · 작업 중 + 작업하는 사람 목록 · 완료한 사람 · 시각)을 새 도면 key 마다 같은 파트 줄로 넣는다 —
  완료 · 기본은 **모든 새 장**, 작업 중은 **1공장 장에만**(``drawing_factory.sheet_factory`` — '도면 없음' 카드는 1공장 카드라 2공장 장에
  옮기면 그 사람이 못 끝낸다, 1공장 장이 없으면 작업 중은 안 옮긴다). 그 key · 파트 줄이 이미 있으면 건드리지 않는다. 이벤트
  ``PRODUCTION_PART_MARKED``(카드 누름과 같은 꼴 · ``via: 'order_card'`` · ``by_name`` = 그 줄의 사람). ``@order`` 줄은 **미정으로** 돌린다(줄은
  기록으로 남긴다 — 표에서 지우는 길은 이 저장소에 없다, 그 기록 줄은 바뀐 기록 목록에서 뺀다). 미정이라 '작업 중 장 수'(공장을 바꾼
  사람 안내 · 아침 칩) · '카드를 쓴 파트'에 다시 세지 않는다.
* 반장이 손으로 체크한 파트(칸 켜짐 · 미정 아닌 ``@order`` 줄 없음)는 새 도면 key 마다 완료 줄로 풀어 적는다 — 지금 손 처리 풀어 쓰기 길
  (:func:`~foms.services.production.step_expand.expand_hand_step`, 칸을 켠 사람 · 칸 시각, ``via: 'step_expand'``). 안 풀면 새 장이 '안 봄'이라
  칸 맞추기가 그 칸을 끈다(지금 ``expand_hand_parts`` 가 모든 장이 새 장일 때 하는 일 — 35번 답과 어긋남).
  손 체크로 보는 파트는 칸이 켜졌고 ``@order`` · 쓰기 전 확정 도면(``before_keys``) 어디에도 미정 아닌 줄이 없는 파트다(0장 → n장이면 쓰기
  전 도면이 없어 ``@order`` 만 본다 — 도면이 n → 0장이 된 주문의 옛 판 줄은 안 센다).
* 나중에 그 도면이 **다시** 바뀌면(key1 → key1′) ``@order`` 줄이 이미 미정이라 이 길을 타지 않는다 — 지금 규칙 그대로(새 장 미정).
"""

from __future__ import annotations

import copy
import datetime
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy import insert, update

from foms.services.datetime_kst import now_utc_naive, parse_datetime_utc
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.confirm_drawing_gate import normalize_stage_code
from foms.services.orders.drawing_factory import sheet_factory
from foms.services.orders.drawing_fix_marks import STAGE_WRITE_HOOKS
from foms.services.orders.drawing_transfer import is_drawing_hotfix_stage
from foms.services.production import mark_crew as mc
from foms.services.production.factory_constants import DEFAULT_FACTORY
from foms.services.production.order_card import order_entry
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
from foms.services.production.part_marks_query import order_marks
from foms.services.production.part_progress import cards_used, marks_by_part, order_card_parts
from foms.services.production.step_expand import expand_hand_step
from foms.services.production.steps import step_done_map
from models import Order, OrderEvent, ProductionPartMark, User

_PRODUCTION = "PRODUCTION"
#: 이벤트 ``via`` · 옮긴 뒤 ``@order`` 줄을 미정으로 돌린 기록 줄의 ``action``(기록용 낱말 — 쓰기 API 가 받는 누름이 아니다).
VIA_ORDER_CARD = "order_card"
ACTION_ORDER_CARD = "order_card"
#: 옮긴 줄 이벤트의 ``action`` — 그 상태가 되는 누름(바뀐 기록이 "맡음" · "완료" · "기본"으로 읽는다).
_COPY_ACTIONS = {MARK_STATE_NEED: ACTION_TAKE, MARK_STATE_DONE: ACTION_DONE, MARK_STATE_BASIC: ACTION_BASIC}


def first_arrival(order: Any, sd: Any) -> bool:
    """이 쓰기가 도면 바로 반영 단계(생산 · 시공 — ``is_drawing_hotfix_stage``, 공정 칸 맞추기와 같은 판정) 주문의 확정 도면을
    0장 → n장으로 바꾸는지 — ``order.structured_data`` = 쓰기 전(잠근 행), ``sd`` = 쓸 사본.

    시공 단계도 본다: '도면 없음' 카드로 네 파트를 끝내 제작 완료한 주문에 도면이 처음 오면, 안 옮기면 칸 맞추기가 새 장(줄 없음)을
    보고 켜진 칸 넷을 다 끈다(2026-11-28 ⓑ 검토 1).
    """
    before = getattr(order, "structured_data", None)
    return (is_drawing_hotfix_stage(order) and not resolve_final_drawing_files(before if isinstance(before, dict) else {})
            and bool(resolve_final_drawing_files(sd if isinstance(sd, dict) else {})))


def leftover_order_card(sd: Any, marks: Iterable[Any]) -> bool:
    """확정 도면이 1장 이상인데 미정 아닌 ``@order`` 줄이 남았는지 — 바로 반영 단계 밖에서 도면을 받은 주문(ⓑ 검토 2, 쿼리 0)."""
    return bool(resolve_final_drawing_files(sd if isinstance(sd, dict) else {})) and bool(order_card_parts(marks))


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


def _hand_parts(db: Any, order: Any, sd: dict[str, Any], marks: list[Any], user: Any, now: datetime.datetime,
                before_keys: Iterable[str]) -> list[str]:
    """손으로 체크한 파트를 지금 도면 key 마다 완료로 풀어 적는다 — 칸을 켠 사람 · 칸 시각(35번 답).

    손 체크 = 공정 칸 켜짐 + 그 파트에 ``@order`` · 쓰기 전 확정 도면(``before_keys``) 어디에도 미정 아닌 줄 없음. 0장 → n장이면 쓰기 전
    도면이 없어 ``@order`` 만 본다(0장 주문의 ``part_progress.parts_in_use`` 와 같은 기준) — 도면이 n → 0장이 된 주문의 옛 판 줄은 세지 않는다.
    ``drawing_factory.hand_checked_parts``(옛 판 줄 포함 ``cards_used``)로 고르면 옛 판에서 끝낸 · 작업 중인 파트가 빠져 칸 맞추기가 켜진
    칸을 끈다(2026-11-28 ⓑ 검토 3). 쓰기 전 도면에서 카드를 쓴 파트는 손 체크가 아니다(그 도면 줄이 판정 — 칸 맞추기 몫).
    """
    production = sd.get("production") if isinstance(sd.get("production"), dict) else {}
    steps = {str(s.get("key")): s for s in production.get("steps") or [] if isinstance(s, dict)}
    counted = {ORDER_CARD_KEY, *before_keys}
    used = cards_used(m for m in marks if getattr(m, "drawing_key", None) in counted)
    done_map = step_done_map(sd)
    done: list[str] = []
    for part in (p for p in PRODUCTION_PART_KEYS if done_map.get(p) and p not in used):
        step = steps.get(part) or {}
        expand_hand_step(db, order, sd, marks, part, exclude_keys=(), user=user, done_by_name=str(step.get("by_name") or "").strip(),
                         done_at=_naive_utc(step.get("at")) or now)
        done.append(part)
    return done


def carry_order_card(db: Any, order: Any, sd: dict[str, Any], marks: Iterable[Any], *, user: Any,
                     before_keys: Iterable[str] = ()) -> list[str]:
    """도면이 처음 왔을 때 옮기기(모듈 머리말) — 부르는 쪽이 :func:`first_arrival` · :func:`leftover_order_card` 를 이미 봤다. 표마다 문
    한 번(장 · 파트 수와 무관).

    Args:
        db: 세션(같은 tx — 주문은 잠겨 있다).
        order: 잠근 주문.
        sd: 쓸 ``structured_data`` 사본(확정 도면이 들어 있다 — 읽기만).
        marks: 그 주문 표시 줄(잠금 아래에서 읽은 것 — 쓴 뒤 세션에서 만료시켜 뒤 칸 맞추기가 새 값을 다시 읽게 한다).
        user: 쓴 사람(보낸 사람 · 단계를 바꾼 사람 — 이벤트 사람).
        before_keys: 쓰기 전 확정 도면 key(손 체크 고르기 — :func:`_hand_parts`. 0장 → n장이면 빈 것).

    Returns:
        옮긴 파트 key 들(새 도면 줄을 한 줄이라도 넣은 ``@order`` 파트 · 손 체크, 공정 순서).
    """
    marks = list(marks)
    entries = resolve_final_drawing_files(sd)
    first_factory = [e for e in entries if sheet_factory(sd, e) == DEFAULT_FACTORY]
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
        # 작업 중은 1공장 장에만('도면 없음' 카드는 1공장 카드 — 2공장 장에 옮기면 그 사람이 못 끝내고 내 공정에도 안 나온다), 완료 · 기본은
        # 모든 장에(2026-11-28 ⓑ 검토 4). 1공장 장이 없으면 작업 중은 어디에도 안 옮기고 @order 줄만 미정으로 돌린다
        for entry in first_factory if str(src.state) == MARK_STATE_NEED else entries:
            if entry["key"] in rows or entry["key"] in keys:  # 이미 그 key · 파트 줄이 있으면 그대로(같은 key 두 번도 한 줄)
                continue
            values, event = _copy(order, src, entry, part, user, now)
            inserts.append(values)
            events.append(event)
            keys.append(entry["key"])
        clears.append(_clear(order, src, part, keys, user, now))
        if keys:
            carried.append(part)
    if inserts:
        db.execute(insert(ProductionPartMark), inserts)
    if clears:
        db.execute(update(ProductionPartMark), [{"id": w.row_id, **w.values} for w in clears])
        events += [w.event for w in clears]
    if events:
        db.execute(insert(OrderEvent), events)
    hand = _hand_parts(db, order, sd, marks, user, now, before_keys)
    if clears or hand:
        # 위 문들(@order 줄 미정 돌리기 · 손 체크 풀어 쓰기의 한 문장 넣기 · 고치기)은 세션에 든 줄 사본을 고치지 않는다. 부르는 쪽이 이
        # 줄 목록을 쥐고 있으면(전달 길 — worked_refusal 이 읽어 돌려준 줄을 라우트가 칸 맞추기 끝까지 쥔다) 뒤 칸
        # 맞추기(sync_steps_in_drawing_write)의 다시 읽기가 같은 세션의 그 줄을 옛 값 그대로 돌려준다 — 만료시켜 새 값을 읽게 한다
        # (안 하면 손 체크로 완료로 고친 지금 도면 줄이 옛 '미정'으로 읽혀 켜진 칸이 꺼진다 — 시험
        # test_leftover_order_card_on_a_hotfix_transfer_carries_and_keeps_steps_on)
        for row in marks:
            db.expire(row)
    return [part for part in PRODUCTION_PART_KEYS if part in carried or part in hand]


def carry_on_production_entry(db: Any, order_id: int, sd: Any, *, from_stage: Any, to_stage: Any, user_id: Any,
                              by_name: Optional[str] = None) -> list[str]:
    """주문이 생산 단계로 **들어가는** 쓰기 안(같은 tx · 주문 잠금 아래)에서 남은 '도면 없음' 카드 줄을 한 번 옮긴다(ⓑ 검토 2 — 사장님 "고침").

    단계 쓰기 자리마다 부르는 ``drawing_fix_marks.release_on_stage_exit`` 가 부른다(그 함수를 부르는 곳 = 상태 전이 엔진 ``transition_order``
    · 강제 단계 변경 한 건 · 일괄 · ``update_order_status`` · ``update_order_field``). 생산 → 생산 · 생산 밖으로 가는 쓰기 · 확정 도면 0장
    (주문 카드 그대로)은 쿼리 0. 그 밖은 표시 줄 읽기 1 — 미정 아닌 ``@order`` 줄이 없으면 거기서 끝(쓰기 0). 공정 칸은 바꾸지 않는다(옮긴 줄과
    지금 칸이 이미 같은 답 — 완료 줄 = 켜진 칸, 작업 중 = 꺼진 칸, 손 체크 = 켜진 칸을 완료 줄로).

    Args:
        db: 세션. order_id: 잠근 주문 id. sd: 쓰는 쪽 ``structured_data``(읽기만). from_stage · to_stage: 바뀌기 전 · 뒤 단계(영문 · 한글).
        user_id · by_name: 단계를 바꾼 사람(이벤트 사람 — 사용자 행은 보통 같은 세션에 있어 쿼리 0).

    Returns:
        옮긴 파트 key 들(없으면 빈 목록).
    """
    if normalize_stage_code(to_stage) != _PRODUCTION or normalize_stage_code(from_stage) == _PRODUCTION:
        return []
    entries = resolve_final_drawing_files(sd if isinstance(sd, dict) else {})
    if not entries:
        return []
    marks = order_marks(db, int(order_id))
    if not order_card_parts(marks):
        return []
    user = db.get(User, int(user_id)) if str(user_id or "").isdigit() else None
    actor = user if user is not None else SimpleNamespace(id=None, name=by_name or None, username=None)
    return carry_order_card(db, db.get(Order, int(order_id)), sd, marks, user=actor, before_keys=[e["key"] for e in entries])


# 단계 쓰기 자리마다 불리는 한 곳(release_on_stage_exit)에 건다 — 그 모듈이 이 모듈을 import 하면 앱 시작 때 돌고 돈다(drawing_fix_marks 머리글).
# 이 모듈이 다시 읽혀도(시험의 reload) 한 번만 걸리게 옛 것을 뺀다
STAGE_WRITE_HOOKS[:] = [hook for hook in STAGE_WRITE_HOOKS if getattr(hook, "__module__", None) != __name__] + [carry_on_production_entry]

__all__ = ["ACTION_ORDER_CARD", "VIA_ORDER_CARD", "carry_on_production_entry", "carry_order_card", "first_arrival",
           "leftover_order_card"]
