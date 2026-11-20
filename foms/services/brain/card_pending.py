"""지식 카드 오른쪽 '승인 대기' 상자의 누가 · 언제 · 무엇(설계서 2026-11-14-foms-graft 5.4 · 판 ⑧ · 점검 w2-01) — **읽기만**.

카드 머리 수(:func:`.card.open_change_count`)는 그대로 두고, 그 항목의 열린 제안 가운데 **이 사람이 승인 대기 화면에서 보는
제안**의 처음 것(오래된 것) 한 건만 글로 만든다. 볼 권한은 승인 대기와 같은 판정을 그대로 쓴다(:mod:`.inbox` — 결정할 수 있는
제안 · 보기 범위 · 이번 주 AI 자리). 볼 수 있는 제안이 없으면 ``None`` — 화면은 지금처럼 수만 보인다.

글: 누가(만든 이 화면 이름 — 사람 · 에이전트) · 언제(한국 날 'MM-DD') · 무엇(칸마다 '이름 전 → 후', 둘까지) · 까닭(사람이 쓴 글
앞부분). 값은 제안에 있는 것만 — 새로 읽는 글은 없다. card.py 가 inbox.py 를 부르면 서로 부르는 꼴이 되어 따로 둔다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import aliased

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.card import actor_label, people_names
from foms.services.brain.constants import CHANGE_OPEN, OP_CREATE, OP_DELETE, OP_RETIRE, UNCAPPED_AI_ACTIONS, UNCAPPED_AI_PROPOSERS
from foms.services.brain.display import FIELD_LABELS
from foms.services.brain.inbox import current_join, decidable, decidable_clause, shown_ai_ids, visible_clause
from foms.services.brain.review_rules import is_agent, value_text
from foms.services.brain.schemas import diff_rows
from foms.services.brain.scope import Viewer
from foms.services.datetime_kst import format_datetime_kst

__all__ = ["pending_change"]

SCAN = 20  # 한 항목의 열린 제안을 읽는 줄 수(한 카드로 묶이는 수 — 넘는 일은 드물다)
FIELDS_SHOWN = 2
VALUE_CHARS, REASON_CHARS = 30, 80
_OP_TEXT = {OP_RETIRE: "은퇴", OP_DELETE: "지우기", OP_CREATE: "새로 만들기"}


def _short(text: str, size: int) -> str:
    """앞 ``size`` 자 + 넘으면 '…'."""
    value = " ".join(text.split())
    return value if len(value) <= size else value[:size] + "…"


def _capped(change: BrainChange) -> bool:
    """주 상한을 받는 AI 제안인가(:func:`.inbox.capped_clause` 와 같은 판정)."""
    return (is_agent(change.proposed_by) and (change.action or "") not in UNCAPPED_AI_ACTIONS
            and change.proposed_by not in UNCAPPED_AI_PROPOSERS)


def _what(change: BrainChange) -> str:
    """무엇 — 칸마다 '이름 전 → 후'(둘까지 · 더 있으면 '그 밖 N칸'). 은퇴 · 지우기는 그 말."""
    if change.op in (OP_RETIRE, OP_DELETE):
        return _OP_TEXT[change.op]
    rows = diff_rows(change.item_type, change.fields or {})
    parts = []
    for row in rows[:FIELDS_SHOWN]:
        label = row.get("label") or FIELD_LABELS.get(row["field"], row["field"])
        unit = f" {row['unit']}" if row.get("unit") else ""
        before, after = value_text(row.get("before")), value_text(row.get("after"))
        before_text = _short(before, VALUE_CHARS) + unit if before else "없음"
        parts.append(f"{label} {before_text} → {_short(after, VALUE_CHARS) + unit if after else '없음'}")
    if len(rows) > FIELDS_SHOWN:
        parts.append(f"그 밖 {len(rows) - FIELDS_SHOWN}칸")
    return " · ".join(parts) or _OP_TEXT.get(change.op, "고침")


def pending_change(session: Any, viewer: Viewer, key: str, *, now: datetime.datetime) -> Optional[dict[str, Any]]:
    """이 항목의 열린 제안 가운데 이 사람이 승인 대기에서 보는 처음 것 — ``{"who", "day", "what", "reason", "more"}`` 또는 ``None``.

    Args:
        session: DB 세션(읽기만).
        viewer: 카드를 연 사람의 보기 범위.
        key: 지식 항목 키.
        now: 지금(UTC naive — 이번 주 AI 자리 · 4주 닫힘 판정).

    Returns:
        볼 수 있는 제안이 없으면 ``None``. ``more`` 는 그 밖에 볼 수 있는 열린 제안 수.
    """
    cur = aliased(BrainObject)
    rows = session.execute(
        select(BrainChange).outerjoin(cur, current_join(cur))
        .where(BrainChange.status == CHANGE_OPEN, BrainChange.item_key == key, decidable_clause(viewer),
               visible_clause(viewer, cur))
        .order_by(BrainChange.created_at, BrainChange.id).limit(SCAN)).scalars().all()
    rows = [change for change in rows if decidable(viewer, change)]
    if any(_capped(change) for change in rows):
        shown = set(shown_ai_ids(session, now))
        rows = [change for change in rows if not _capped(change) or change.id in shown]
    if not rows:
        return None
    first = rows[0]
    who = first.proposed_by or ""
    ids = {int(who[5:])} if who.startswith("user:") and who[5:].isdigit() else set()
    reason = _short(first.reason or "", REASON_CHARS)
    return {"who": actor_label(who, people_names(session, ids)),
            "day": format_datetime_kst(first.created_at, "%m-%d") if first.created_at else "",
            "what": _what(first), "reason": reason, "more": len(rows) - 1}
