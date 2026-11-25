"""손 처리 파트를 도면별 표시로 풀어 적기(설계서 2026-11-25 §3-6 — 같은 함수 하나를 두 곳에서 부른다).

① 통째 작업에서 한 장 빼기: 막힌 도면이 있는 주문에서 반장 · 관리자가 카드를 한 장도 안 쓴 파트의 공정 칸을 켜면(``POST …/production/steps``)
   칸은 켜지 않고 막히지 않은 지금 도면 **전부**를 ``DONE`` 표시로 쓴다(공장을 가리지 않음 — 공정 칸이 주문에 값 하나라 막힌 도면이 없으면
   반장 한 번에 두 공장 장이 모두 완료되는 지금 규칙과 같은 범위, 2026-11-25 D1 검토 판결 A) — :func:`step_expand_plan` · :func:`apply_step_expand`.
② 손 처리 파트가 있는 주문의 도면을 고쳐 보냄: 전달 쓰기 안에서 이번에 안 바뀐 장을 칸을 켠 사람 이름 · 칸 시각으로 ``DONE`` — D2 가
   :func:`expand_hand_step` 을 부른다.

그 순간 파트는 '카드를 쓴 파트'가 되어 공정 칸은 ``part_steps_sync`` 동기화가 맞춘다(막힌 장이 남아 꺼짐 → 그 장 새 판이 완료되면 저절로 켜짐).
줄 값 · 이벤트는 카드를 누를 때와 같은 빌더(``part_mark_write.plan_write`` — 이벤트 ``PRODUCTION_PART_MARKED``, payload ``via: 'step_expand'``)로
만든다. ``part_mark_write`` 가 ``part_steps_sync`` 를 부르므로 이 모듈을 따로 둔다(서로 부르지 않게).
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy import insert
from sqlalchemy.dialects import postgresql, sqlite

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_fix import expand_plan, expanded_words, numbers_text
from foms.services.production.part_constants import (
    MARK_STATE_BASIC,
    MARK_STATE_DONE,
    MARK_STATE_NEED,
    PART_INSPECT,
    PRODUCTION_PART_LABELS,
)
from foms.services.production.part_mark_gates import GateRefusal, inspect_gate
from foms.services.production.part_mark_rules import ACTION_DONE, MARK_COLUMNS
from foms.services.production.part_mark_write import MarkWrite, actor_name, plan_write, step_note, write_audit
from foms.services.production.part_progress import cards_used, mark_finished, marks_by_part, part_progress
from foms.services.production.part_steps_sync import (
    apply_part_step_changes,
    plan_part_step_changes,
    step_change_body,
    step_event_rows,
)
from foms.services.production.steps import step_done_map
from models import OrderEvent, ProductionPartMark

#: 풀어 적었다는 표지(이벤트 · 감사 ``via``).
VIA_STEP_EXPAND = "step_expand"
#: 한 문장 넣기 · 고치기(``INSERT … ON CONFLICT``) — 운영 PostgreSQL · 시험 SQLite.
_UPSERT_BUILDERS = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
_UNIQUE_MARK = ("order_id", "drawing_key", "part")


def _upsert_marks(db: Any, values: list[dict[str, Any]]) -> None:
    """표시 줄을 **한 문장**으로 넣거나 고친다(``INSERT … ON CONFLICT (order_id, drawing_key, part) DO UPDATE``) — 줄 수와 무관.

    이미 끝(DONE · BASIC)인 줄은 고치지 않는다(``WHERE`` — 읽은 뒤 그사이 누가 끝냈어도 덮지 않음). 값 줄은 key 마다 하나여야 한다
    (PostgreSQL 은 한 문장이 같은 줄을 두 번 건드리면 거절한다 — 부르는 쪽이 key 로 거른다).
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


def expand_hand_step(db: Any, order: Any, sd: Any, marks: Iterable[Any], part: str, *, exclude_keys: Iterable[str], user: Any,
                     done_by_name: Optional[str] = None, done_by_user_id: Optional[int] = None,
                     done_at: Optional[datetime.datetime] = None) -> list[MarkWrite]:
    """그 파트를 도면별 표시로 풀어 적는다 — 지금 도면 중 ``exclude_keys`` 밖 장 **전부**(공장을 가리지 않음)를 ``DONE``(§3-6).

    이미 끝(DONE · 재단 BASIC)인 장은 건드리지 않고 '안 봄' · '작업 필요' 줄만 쓴다(설계서 §12 — 기본 장을 덮지 않음). 같은 key 가 지금
    도면에 두 번 있어도 줄은 key 마다 하나다. 줄은 :func:`_upsert_marks` 한 문장, 이벤트(카드와 같은 꼴 + ``via``)는 INSERT 한 문장.

    Args:
        db: 세션(같은 tx — 주문은 이미 잠겨 있다).
        order: 잠근 주문(``id``).
        sd: 주문 ``structured_data``(읽기만).
        marks: 그 주문 표시 줄(잠금 아래에서 읽은 것).
        part: 파트 key.
        exclude_keys: 빼는 장 key(①: 막힌 장 · ②: 이번에 바뀐 장).
        user: 쓴 사람(①: 누른 반장 · ②: 보낸 도면팀원) — ``updated_by_user_id`` · 이벤트 사람.
        done_by_name · done_by_user_id · done_at: 완료한 사람 스냅샷(②: 칸을 켠 사람 이름 · 칸 시각). 이름을 안 주면(None) ``user`` ·
            지금, 빈 글이면 이름 없음(None — 기록 이벤트 ``by_name`` 도 None).

    Returns:
        쓴 표시(:class:`~foms.services.production.part_mark_write.MarkWrite` — 값 · 이벤트, 쓴 것이 없으면 빈 목록).
    """
    rows = marks_by_part(list(marks)).get(part, {})
    skip, seen, writes = set(exclude_keys), set(), []
    for entry in resolve_final_drawing_files(sd):
        key, row = entry["key"], rows.get(entry["key"])
        if key in skip or key in seen or mark_finished(part, getattr(row, "state", None)):
            continue
        seen.add(key)
        holder = getattr(row, "picked_by_user_id", None) if getattr(row, "state", None) == MARK_STATE_NEED else None
        write = plan_write(order, entry, row, part=part, target=MARK_STATE_DONE, user=user, action=ACTION_DONE,
                           override=holder is not None and holder != getattr(user, "id", None))
        if done_by_name is not None:
            # 빈 이름("")은 "모름" — 이름 칸은 빈 채(None), 누른 사람으로 채우지 않는다(D2 검토 F)
            write.values.update(done_by_user_id=done_by_user_id, done_by_name=done_by_name or None,
                                done_at=done_at or write.values["done_at"])
            # 장별 기록(part-history 는 payload ``by_name`` 을 먼저 읽는다)이 표시 줄과 같은 사람(칸을 켠 사람)을 말하게(D2 검토)
            write.event["payload"]["by_name"] = done_by_name or None
        write.event["payload"]["via"] = VIA_STEP_EXPAND
        writes.append(write)
    if writes:
        _upsert_marks(db, [w.values for w in writes])
        db.execute(insert(OrderEvent), [w.event for w in writes])
    return writes


def with_written_marks(marks: Iterable[Any], values: Iterable[dict[str, Any]]) -> list[Any]:
    """읽은 표시 줄 위에 방금 쓴 값을 덮은 모습(다시 읽지 않는다 — 응답 · 동기화 판정용)."""
    views = {(str(getattr(m, "drawing_key", "")), str(getattr(m, "part", ""))): m for m in marks}
    for value in values:
        views[(str(value["drawing_key"]), str(value["part"]))] = SimpleNamespace(**value)
    return list(views.values())


def step_expand_plan(sd: Any, marks: Iterable[Any], part: str) -> Optional[dict[str, Any]]:
    """공정 칸 켜기(done=true)를 풀어 적을지(§3-6 ①) — 그 파트 카드 0장 · 칸이 꺼짐 · 막힌 도면 1장 이상.

    Returns:
        :func:`~foms.services.orders.drawing_fix.expand_plan` 값 또는 None(지금처럼 칸만 켬 — 막힌 도면이 없거나 카드를 쓴 파트).
    """
    if part in cards_used(list(marks)) or step_done_map(sd).get(part, False):
        return None
    return expand_plan(sd)


def _check_inspect_ready(sd: Any, marks: list[Any], part: str, keys: Iterable[str]) -> None:
    """검수 풀어 쓰기 전 장마다 지금 검수 문(:func:`~foms.services.production.part_mark_gates.inspect_gate` — 카드 검수 완료와 같은
    판정). 하나라도 막히면 그 거절로 멈춘다(쓰기 0). 재단 · 엣지 · 조립은 검사 없음(지금 카드 규칙과 같다)."""
    if part != PART_INSPECT:
        return
    for key in keys:
        gate = inspect_gate(sd, marks, key, PART_INSPECT, ACTION_DONE)
        if gate is not None:
            raise GateRefusal(gate)


def apply_step_expand(db: Any, order: Any, sd: dict[str, Any], marks: list[Any], part: str, plan: dict[str, Any], *,
                      user: Any) -> tuple[list[Any], dict[str, Any]]:
    """통째 작업 풀어 쓰기 — 장마다 표시 줄 + 이벤트 · 감사 한 줄 · 칸 동기화.

    공정 칸 이벤트(``PRODUCTION_STEP_CHECKED``)는 동기화가 칸을 **정말** 바꿀 때만 남는다(칸이 꺼진 채 ``done: True`` 이벤트 없음 —
    판결 E). 감사 줄은 카드 쓰기와 같은 '생산 파트 체크'(칸이 바뀌면 꼬리 " · 공정 재단 켬").

    Args:
        db: 세션(같은 tx). order: 잠근 주문. sd: 고칠 사본(동기화로 칸이 바뀌면 제자리 — 부르는 쪽이 재대입 · ``flag_modified``).
        marks: 잠금 아래에서 읽은 표시 줄. part: 파트. plan: :func:`step_expand_plan` 값(``keys`` 가 비어 있지 않음).
        user: 누른 반장 · 관리자.

    Returns:
        (쓴 뒤 표시 줄 모습, 응답 ``expanded`` = ``{part, part_label, done_n, total_n, skipped_numbers, tail, hold}``).

    Raises:
        GateRefusal: 검수를 풀어 쓸 때 쓸 장 중 하나라도 검수 준비가 안 됨(409 ``INSPECT_NOT_READY`` — 카드로 누를 때와 같은 판정 ·
            같은 글, 둘째 판 3). 아무것도 쓰지 않는다.
    """
    _check_inspect_ready(sd, marks, part, plan["keys"])
    writes = expand_hand_step(db, order, sd, marks, part, exclude_keys=plan["skip_keys"], user=user)
    views = with_written_marks(marks, [w.values for w in writes])
    changes = plan_part_step_changes(sd, views, (part,))
    apply_part_step_changes(sd, changes, at_iso=datetime.datetime.now(datetime.timezone.utc).isoformat())
    if changes:
        db.execute(insert(OrderEvent), step_event_rows(order.id, changes, actor_user_id=getattr(user, "id", None),
                                                       actor_name=actor_name(user)))
    label = PRODUCTION_PART_LABELS[part]
    steps = [step_change_body(order.id, change) for change in changes]
    write_audit(db, user, f"{label} 완료 {len(writes)}장 · 도면 {numbers_text(plan['numbers'])} 뺌" + step_note(steps),
                {"part": part, "to": MARK_STATE_DONE, "via": VIA_STEP_EXPAND, "keys": [w.values["drawing_key"] for w in writes],
                 "skipped_numbers": plan["numbers"], "order_steps": steps}, order=order)
    progress = part_progress(sd, views, part)
    return views, {"part": part, "part_label": label, "done_n": progress["done_n"], "total_n": progress["total_n"],
                   "skipped_numbers": plan["numbers"], **expanded_words(plan["numbers"])}


__all__ = ["VIA_STEP_EXPAND", "apply_step_expand", "expand_hand_step", "step_expand_plan", "with_written_marks"]
