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
* 풀어 쓰기(설계서 2026-11-25 §3-6): :func:`expand_hand_step` — 손 처리(카드 0장) 파트를 도면별 ``DONE`` 표시로 풀어 적는다(한 문장).
  ① 막힌 도면이 있는 주문의 통째 작업(공정 API — :func:`step_expand_plan` · :func:`apply_step_expand`) · ② 손 처리 파트가 있는 주문의
  도면을 고쳐 보냄(전달 쓰기 — D2 가 부른다). 그 순간 파트는 '카드를 쓴 파트'가 되어 칸은 위 동기화가 맞춘다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy import insert
from sqlalchemy.dialects import postgresql, sqlite

from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_factory import current_factories
from foms.services.orders.drawing_fix import expand_plan
from foms.services.orders.drawing_transfer import is_drawing_hotfix_stage
from foms.services.production.factory_constants import FACTORIES
from foms.services.production.part_constants import MARK_STATE_BASIC, MARK_STATE_DONE, PRODUCTION_PART_KEYS
from foms.services.production.part_mark_rules import MARK_COLUMNS, next_mark_values
from foms.services.production.part_progress import cards_used, mark_finished, marks_by_part, part_progress
from foms.services.production.steps import STEP_VIA_PART_MARKS, set_production_step, step_done_map
from models import OrderEvent, ProductionPartMark

STEP_EVENT = "PRODUCTION_STEP_CHECKED"
#: 이벤트 payload · 공정 칸 ``via`` — 공정 칸을 사람이 아니라 파트 카드 동기화가 바꿨다는 표지.
VIA_PART_MARKS = STEP_VIA_PART_MARKS
#: 도면 쓰기 셋의 ``trigger``(표시 API 길은 trigger 없음).
TRIGGER_TRANSFER = "drawing_transfer"
TRIGGER_TRANSFER_CANCEL = "drawing_transfer_cancel"
TRIGGER_ITEM_CANCEL = "item_cancel_after_confirm"
#: 통째 작업을 도면별 표시로 풀어 적었다는 표지(이벤트 payload ``via``, 2026-11-25 설계서 §3-6).
VIA_STEP_EXPAND = "step_expand"
#: 한 문장 넣기 · 고치기(``INSERT … ON CONFLICT``) — 운영 PostgreSQL · 시험 SQLite.
_UPSERT_BUILDERS = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
_UNIQUE_MARK = ("order_id", "drawing_key", "part")


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


# --------------------------------------------------------------------------- #
# 통째 작업에서 한 장 빼기 · 손 처리 파트의 도면을 고쳐 보냄(2026-11-25 설계서 §3-6 — 같은 함수 하나)
# --------------------------------------------------------------------------- #
def _upsert_marks(db: Any, values: list[dict[str, Any]]) -> None:
    """표시 줄을 **한 문장**으로 넣거나 고친다(``INSERT … ON CONFLICT (order_id, drawing_key, part) DO UPDATE``) — 줄 수와 무관.

    이미 끝(DONE · BASIC)인 줄은 고치지 않는다(``WHERE`` — 읽은 뒤 그사이 누가 끝냈어도 덮지 않음).
    """
    builder = _UPSERT_BUILDERS.get(db.get_bind().dialect.name)
    if builder is None:
        raise RuntimeError(f"한 문장 넣기 · 고치기를 모르는 DB: {db.get_bind().dialect.name}")
    table = ProductionPartMark.__table__
    stmt = builder(table).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=list(_UNIQUE_MARK),
        set_={column: stmt.excluded[column] for column in MARK_COLUMNS if column not in _UNIQUE_MARK},
        where=table.c.state.notin_((MARK_STATE_DONE, MARK_STATE_BASIC)),
    )
    db.execute(stmt)


def expand_hand_step(db: Any, sd: Any, marks: Iterable[Any], part: str, *, order_id: int, exclude_keys: Iterable[str],
                     by_user_id: Optional[int], by_name: Optional[str], at: datetime.datetime,
                     updated_by_user_id: Optional[int] = None, factories: Iterable[int] = FACTORIES) -> list[dict[str, Any]]:
    """그 파트를 도면별 표시로 풀어 적는다 — 지금 도면 중 ``exclude_keys`` 밖 · ``factories`` 안의 장을 ``DONE``(§3-6).

    이미 끝(DONE · 재단 BASIC)인 장은 건드리지 않고 '안 봄' · '작업 필요' 줄만 쓴다(설계서 §12 — 기본 장을 덮지 않음). 줄은 이름 · 시각
    스냅샷이라 날짜 줄 "재단 완료 · 박반장"이 지금처럼 보인다. 쓰기는 :func:`_upsert_marks` 한 문장(N+1 없음). 공정 칸은 건드리지 않는다
    — 그 파트는 이제 '카드를 쓴 파트'라 칸은 동기화(:func:`plan_part_step_changes`)가 맞춘다.

    Args:
        db: 세션(같은 tx — 주문은 이미 잠겨 있다).
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄(잠금 아래에서 읽은 것).
        part: 파트 key.
        order_id: 주문 id.
        exclude_keys: 빼는 장 key(①: 막힌 장 · ②: 이번에 바뀐 장).
        by_user_id · by_name: 완료한 사람(①: 누른 반장 · ②: 칸을 켠 사람 이름 스냅샷, id 는 없을 수 있음).
        at: 완료 시각(UTC naive — ①: 지금 · ②: 칸 시각).
        updated_by_user_id: 줄을 쓴 사람(②: 보낸 도면팀원, 없으면 ``by_user_id``).
        factories: 쓸 수 있는 공장(반장은 자기 공장 장만 — ``factory_gate`` 와 같은 규칙).

    Returns:
        쓴 줄 값(:data:`MARK_COLUMNS` 꼴 dict, 쓴 것이 없으면 빈 목록).
    """
    rows = marks_by_part(list(marks)).get(part, {})
    skip, allowed = set(exclude_keys), set(factories)
    values = []
    for entry, factory in current_factories(sd):
        key = entry["key"]
        row = rows.get(key)
        if key in skip or factory not in allowed or mark_finished(part, getattr(row, "state", None)):
            continue
        value = next_mark_values(row, order_id=int(order_id), drawing_key=key, part=part, sheet_id=entry.get("sheet_id"),
                                 target=MARK_STATE_DONE, actor_id=by_user_id, actor_name=by_name, now=at)
        value["updated_by_user_id"] = updated_by_user_id if updated_by_user_id is not None else by_user_id
        values.append(value)
    if values:
        _upsert_marks(db, values)
    return values


def with_written_marks(marks: Iterable[Any], values: Iterable[dict[str, Any]]) -> list[Any]:
    """읽은 표시 줄 위에 방금 쓴 값을 덮은 모습(다시 읽지 않는다 — 응답 · 동기화 판정용)."""
    views = {(str(getattr(m, "drawing_key", "")), str(getattr(m, "part", ""))): m for m in marks}
    for value in values:
        views[(str(value["drawing_key"]), str(value["part"]))] = SimpleNamespace(**value)
    return list(views.values())


def step_expand_plan(sd: Any, marks: Iterable[Any], part: str, *, factories: Iterable[int]) -> Optional[dict[str, Any]]:
    """공정 칸 켜기(``POST …/production/steps`` done=true)를 풀어 적을지(§3-6 ①) — 그 파트 카드 0장 · 칸이 꺼짐 · 막힌 도면 1장 이상.

    Returns:
        :func:`~foms.services.orders.drawing_fix.expand_plan` 값 또는 None(지금처럼 칸만 켬 — 막힌 도면이 없거나 카드를 쓴 파트).
    """
    if part in cards_used(list(marks)) or step_done_map(sd).get(part, False):
        return None
    return expand_plan(sd, factories)


def apply_step_expand(db: Any, order: Any, sd: dict[str, Any], marks: list[Any], part: str, plan: dict[str, Any], *,
                      user_id: Optional[int], user_name: Optional[str],
                      factories: Iterable[int] = FACTORIES) -> tuple[list[Any], dict[str, Any]]:
    """통째 작업 풀어 쓰기 — 표시 줄 한 문장 + 이벤트 ``PRODUCTION_STEP_CHECKED``(``via: 'step_expand'`` · ``expanded_keys``) + 칸 동기화.

    Args:
        db: 세션(같은 tx). order: 잠근 주문. sd: 고칠 사본(동기화로 칸이 바뀌면 제자리 — 부르는 쪽이 재대입 · ``flag_modified``).
        marks: 잠금 아래에서 읽은 표시 줄. part: 파트. plan: :func:`step_expand_plan` 값(``keys`` 가 비어 있지 않음).
        user_id · user_name: 누른 반장 · 관리자. factories: 누른 사람이 쓸 수 있는 공장(계획을 만들 때와 같은 값).

    Returns:
        (쓴 뒤 표시 줄 모습, 응답 ``expanded`` = ``{part, done_n, skipped_numbers, total_n}``).
    """
    written = expand_hand_step(db, sd, marks, part, order_id=int(order.id), exclude_keys=plan["skip_keys"],
                               by_user_id=user_id, by_name=user_name, at=now_utc_naive(), factories=factories)
    views = with_written_marks(marks, written)
    changes = plan_part_step_changes(sd, views, (part,))
    apply_part_step_changes(sd, changes, at_iso=datetime.datetime.now(datetime.timezone.utc).isoformat())
    events = step_event_rows(order.id, changes, actor_user_id=user_id, actor_name=user_name)
    payload = {"key": part, "done": True, "domain": "PRODUCTION_DOMAIN", "action": STEP_EVENT, "via": VIA_STEP_EXPAND,
               "by_name": user_name, "expanded_keys": [v["drawing_key"] for v in written], "skipped_numbers": plan["numbers"]}
    events.append({"order_id": int(order.id), "event_type": STEP_EVENT, "payload": payload, "created_by_user_id": user_id,
                   "created_at": now_utc_naive()})
    db.execute(insert(OrderEvent), events)
    progress = part_progress(sd, views, part)
    return views, {"part": part, "done_n": progress["done_n"], "total_n": progress["total_n"],
                   "skipped_numbers": plan["numbers"]}

