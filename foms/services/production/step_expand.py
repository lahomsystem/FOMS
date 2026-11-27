"""손 처리 파트를 도면별 표시로 풀어 적기(설계서 2026-11-25 §3-6 ②).

손 처리 파트가 있는 주문의 도면을 고쳐 보냄: 전달 쓰기 안에서 이번에 안 바뀐 장을 칸을 켠 사람 이름 · 칸 시각으로 ``DONE`` — D2 가
:func:`expand_hand_step` 을 부른다. 옛 ①(공정 칸 통째 작업에서 막힌 도면만 빼고 풀어 쓰기)은 2026-11-27 지웠다 — 도면이 1장이라도 있는
주문의 공정 칸 켜기는 공정 API 가 먼저 409 ``STEP_PER_SHEET`` 로 막아 그 길에 닿는 주문이 없었다.

그 순간 파트는 '카드를 쓴 파트'가 되어 공정 칸은 ``part_steps_sync`` 동기화가 맞춘다(막힌 장이 남아 꺼짐 → 그 장 새 판이 완료되면 저절로 켜짐).
줄 값 · 이벤트는 카드를 누를 때와 같은 빌더(``part_mark_write.plan_write`` — 이벤트 ``PRODUCTION_PART_MARKED``, payload ``via: 'step_expand'``)로
만든다. ``part_mark_write`` 가 ``part_steps_sync`` 를 부르므로 이 모듈을 따로 둔다(서로 부르지 않게).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import insert
from sqlalchemy.dialects import postgresql, sqlite

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production.part_constants import MARK_STATE_BASIC, MARK_STATE_DONE, MARK_STATE_NEED
from foms.services.production.part_mark_rules import ACTION_DONE, MARK_COLUMNS
from foms.services.production.part_mark_write import MarkWrite, plan_write
from foms.services.production.part_progress import mark_finished, marks_by_part
from models import OrderEvent, ProductionPartMark

#: 풀어 적었다는 표지(이벤트 · 감사 ``via``).
VIA_STEP_EXPAND = "step_expand"
#: 풀어 쓴 장의 "완료한 사람 모름" 표지(이벤트 payload) — 공정 칸에 이름이 없을 때. 바뀐 기록은 이 표지가 있을 때만 이름을 비운다
#: (이름 칸이 빈 옛 이벤트는 지금처럼 사용자 표 이름 — D2 셋째 판 3).
UNKNOWN_FINISHER = "by_unknown"
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
            if not done_by_name:
                write.event["payload"][UNKNOWN_FINISHER] = True
        write.event["payload"]["via"] = VIA_STEP_EXPAND
        writes.append(write)
    if writes:
        _upsert_marks(db, [w.values for w in writes])
        db.execute(insert(OrderEvent), [w.event for w in writes])
    return writes


__all__ = ["UNKNOWN_FINISHER", "VIA_STEP_EXPAND", "expand_hand_step"]
