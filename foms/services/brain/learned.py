"""AI 가 배운 것 — 사람 승인 없이 바로 반영된 학습을 사장님이 나중에 살펴보고 '맞아요' · 고치기 · 지우기(사장님 2026-11-19
'매번 승인 대신 … 즉시 반영, 내가 확인하고 추후 수정 및 삭제 할 수 있게').

대상은 배운 것 바로 반영 길(:class:`.apply.AutoLearn`)로 닫힌 제안 줄이다 — 닫은 액션 이름이 :data:`.apply.AUTO_ACTION`
(아직 안 봄) · :data:`SEEN`(봤음) · :data:`UNDONE`(지움). 표를 새로 만들지 않고 제안 줄의 닫은 액션 · 결정한 사람 칸에 남긴다.
**ADMIN 만** 보고 누른다(그 밖은 없는 것과 같다).

- :func:`learned_list` — 새 것부터. 줄마다 AI 가 넣은 글 · 고치기 앞 글 · 까닭 · 넣은 때 · 지금 상태(``live`` 그대로 ·
  ``changed`` 그 뒤 사람이 또 고침 · ``gone`` 없음).
- :func:`mark_seen` — '맞아요'. 지식은 그대로, 봤다는 것만 남긴다(결정한 사람 = 누른 사람).
- :func:`fix` — 글 · 이름을 고친다. 사람 제안 → 곧바로 반영 동작(사람 승인자 · 확신 '확정'이 된다).
- :func:`undo` — 지운다. 새로 만든 항목은 지우기, 고친 항목은 고치기 앞 판으로 되돌리기(그 뒤 또 바뀌었으면 막는다 — 뒤 고침을
  덮지 않게), 이은 링크는 빼기. 모두 사람 제안 → 곧바로 반영 동작이라 판 · 감사 줄 · 지식 문서 다시 쓰기가 그대로 돈다.

커밋은 호출자 몫이다. 결과 · 감사 줄에는 번호 · 코드만 싣는다.
"""

from __future__ import annotations

import datetime
from typing import Any, Mapping, Optional

from sqlalchemy import func, select

from foms.persistence.brain.models import BrainChange
from foms.services.brain.apply import AUTO_ACTION, apply_change
from foms.services.brain.constants import CHANGE_APPLIED, OBJECT_OPS, OP_CREATE, OP_LINK_ADD, OP_LINK_REMOVE, OP_UPDATE
from foms.services.brain.errors import BrainPermissionError, BrainShapeError, BrainTargetError
from foms.services.brain.inbox import card_title, card_title_of
from foms.services.brain.proposals import (
    Proposer, after_values, propose_delete, propose_link, propose_rollback, propose_update,
)
from foms.services.brain.scope import Viewer, viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.datetime_kst import format_datetime_kst
from models import SecurityLog

__all__ = ["LIST_LIMIT", "SEEN", "UNDONE", "fix", "learned_counts", "learned_list", "mark_seen", "undo"]

SEEN, UNDONE = "auto_learn_seen", "auto_learn_undone"
LIST_LIMIT = 200
REASON_FIX, REASON_UNDO = "AI 가 배운 것 — 사장님이 고침", "AI 가 배운 것 — 사장님이 지움"
FIX_FIELDS: frozenset[str] = frozenset({"name", "text"})
KIND_WORDS: dict[str, str] = {OP_CREATE: "새 지식", OP_UPDATE: "고침", OP_LINK_ADD: "잇기"}


def _admin(actor: Any) -> Viewer:
    """켜진 내부 ADMIN 만(그 밖은 권한 오류 — 화면은 없는 것과 같이 답한다)."""
    viewer = viewer_of(actor)
    if not viewer.internal or viewer.user_id is None or not viewer.is_admin:
        raise BrainPermissionError("사장님(ADMIN)만 살펴본다")
    return viewer


def _learned(session: Any, change_id: Any, states: tuple[str, ...]) -> BrainChange:
    """바로 반영된 제안 줄(잠금) — 없거나 그 상태가 아니면 대상 오류."""
    change = session.execute(select(BrainChange).where(BrainChange.id == int(change_id)).with_for_update()
                             ).scalar_one_or_none()
    if change is None or change.status != CHANGE_APPLIED or change.decided_action not in states:
        raise BrainTargetError("AI 가 바로 넣은 지식이 아니거나 이미 처리했다")
    return change


def _close(session: Any, change: BrainChange, verb: str, state: str, actor_id: int, now: datetime.datetime,
           **detail: Any) -> None:
    """살펴본 결과를 제안 줄에 남기고 감사 한 줄."""
    change.decided_action, change.decided_by = state, actor_id
    session.add(SecurityLog(user_id=actor_id, action=f"BRAIN_LEARNED_{verb}", target_type="brain_change",
                            target_id=change.id, timestamp=now,
                            message=f"BRAIN_LEARNED_{verb} change={change.id} op={change.op} key={change.item_key}",
                            detail={"op": change.op, **detail}))
    session.flush()


def learned_counts(session: Any, viewer: Viewer) -> dict[str, int]:
    """아직 안 본 수 · 본 수(ADMIN 아니면 0)."""
    if not viewer.is_admin:
        return {"new": 0, "seen": 0}
    rows = dict(session.execute(select(BrainChange.decided_action, func.count(BrainChange.id)).where(
        BrainChange.status == CHANGE_APPLIED, BrainChange.decided_action.in_((AUTO_ACTION, SEEN))
    ).group_by(BrainChange.decided_action)).all())
    return {"new": int(rows.get(AUTO_ACTION, 0)), "seen": int(rows.get(SEEN, 0))}


def _text_of(values: Mapping[str, Any], before: Mapping[str, Any]) -> str:
    """AI 가 넣은 것의 글 — 글 칸, 없으면 더한 다른 이름."""
    if isinstance(values.get("text"), str) and values["text"].strip():
        return values["text"]
    new = (values.get("payload") or {}).get("aliases") if isinstance(values.get("payload"), dict) else None
    old = (before.get("payload") or {}).get("aliases") if isinstance(before.get("payload"), dict) else None
    added = [str(a) for a in (new or []) if a not in (old or [])]
    return f"손님이 쓰는 다른 이름: {', '.join(added)}" if added else ""


def _row(session: Any, change: BrainChange) -> dict[str, Any]:
    """목록 한 줄."""
    values = after_values(change.fields)
    before = {name: (entry or {}).get("before") for name, entry in (change.fields or {}).items()}
    base = {"id": change.id, "op": change.op, "kind": KIND_WORDS.get(change.op, change.op), "type": change.item_type,
            "why": change.reason or "", "at": format_datetime_kst(change.decided_at, "%m-%d %H:%M") or "",
            "seen": change.decided_action == SEEN}
    if change.op not in OBJECT_OPS:
        link = current_link(session, change.link_kind, change.link_from, change.link_to)
        ends = [current_object(session, key) for key in (change.link_from, change.link_to)]
        names = [card_title_of(row) if row is not None else key for row, key in zip(ends, (change.link_from, change.link_to))]
        return {**base, "key": change.link_from, "title": names[0], "text": f"{names[0]} → {names[1]}", "before": "",
                "now": "", "state": "live" if link is not None and link.change_id == change.id else "gone",
                "can_fix": False}
    current = current_object(session, change.item_key)
    state = "gone" if current is None else "live" if current.change_id == change.id else "changed"
    old = before.get("text") if isinstance(before.get("text"), str) else ""
    name = str(values.get("name") or (current.name if current is not None else "") or change.item_key)
    return {**base, "key": change.item_key, "title": card_title(change, current, name),
            "text": _text_of(values, before), "before": old if change.op == OP_UPDATE else "",
            "now": (current.text or "") if state == "changed" else "", "state": state,
            "can_fix": current is not None and bool((current.text or "").strip())}


def learned_list(session: Any, viewer: Viewer, *, limit: int = LIST_LIMIT) -> Optional[dict[str, Any]]:
    """AI 가 바로 넣은 지식 목록(아직 안 본 것 먼저 · 새 것부터) — ADMIN 아니면 ``None``."""
    if not viewer.is_admin:
        return None
    rows = session.execute(select(BrainChange).where(
        BrainChange.status == CHANGE_APPLIED, BrainChange.decided_action.in_((AUTO_ACTION, SEEN))
    ).order_by(BrainChange.decided_action, BrainChange.decided_at.desc(), BrainChange.id.desc()).limit(limit)).scalars()
    counts = learned_counts(session, viewer)
    line = (f"아직 안 본 것 {counts['new']}개 · 본 것 {counts['seen']}개" if counts["new"] or counts["seen"]
            else "AI 가 바로 넣은 지식이 아직 없어요.")
    return {"items": [_row(session, change) for change in rows], "counts": {**counts, "line": line}}


def mark_seen(session: Any, change_id: Any, *, actor: Any, now: datetime.datetime) -> dict[str, Any]:
    """'맞아요' — 지식은 그대로, 봤다는 것만 남긴다."""
    viewer = _admin(actor)
    change = _learned(session, change_id, (AUTO_ACTION,))
    _close(session, change, "SEEN", SEEN, int(viewer.user_id or 0), now)
    return {"change_id": change.id, "message": "확인했어요."}


def fix(session: Any, change_id: Any, *, actor: Any, after: Mapping[str, Any], now: datetime.datetime) -> dict[str, Any]:
    """글 · 이름을 고쳐 곧바로 반영한다(사람 승인자 · 확신 '확정')."""
    viewer = _admin(actor)
    change = _learned(session, change_id, (AUTO_ACTION, SEEN))
    wanted = {name: value for name, value in after.items() if name in FIX_FIELDS and isinstance(value, str) and value.strip()}
    if change.op not in OBJECT_OPS or not wanted or set(after) - FIX_FIELDS:
        raise BrainShapeError(["after: 이름 · 글만 고칠 수 있다"])
    current = current_object(session, change.item_key)
    if current is None:
        raise BrainTargetError("그 지식이 이미 없다")
    actor_id = int(viewer.user_id or 0)
    made = propose_update(session, key=current.item_key, base_version=current.version, after=wanted, reason=REASON_FIX,
                          proposer=Proposer.user(actor_id), now=now, action="learned_fix")
    result = apply_change(session, made.id, actor=actor, now=now, action="learned_fix")
    _close(session, change, "FIX", SEEN, actor_id, now, fixed_by=made.id)
    return {"change_id": change.id, "version": result.version, "message": "고쳤어요 — 이제 이 글로 써요."}


def undo(session: Any, change_id: Any, *, actor: Any, now: datetime.datetime) -> dict[str, Any]:
    """지운다(모듈 설명) — 새로 만든 항목은 지우기 · 고친 항목은 앞 판으로 · 이은 링크는 빼기."""
    viewer = _admin(actor)
    change = _learned(session, change_id, (AUTO_ACTION, SEEN))
    actor_id = int(viewer.user_id or 0)
    common = dict(reason=REASON_UNDO, proposer=Proposer.user(actor_id), now=now)
    made = None
    if change.op == OP_LINK_ADD:
        link = current_link(session, change.link_kind, change.link_from, change.link_to)
        if link is not None:
            made = propose_link(session, op=OP_LINK_REMOVE, kind=change.link_kind, from_key=change.link_from,
                                to_key=change.link_to, base_version=link.version, action="learned_undo", **common)
    else:
        current = current_object(session, change.item_key)
        if current is not None and change.op == OP_CREATE:
            made = propose_delete(session, key=current.item_key, base_version=current.version, action="learned_undo",
                                  **common)
        elif current is not None:
            if current.change_id != change.id or change.base_version is None:
                raise BrainTargetError("그 뒤에 또 바뀐 지식이다 — 회사 지식에서 직접 고친다")
            made = propose_rollback(session, key=current.item_key, to_version=int(change.base_version),
                                    action="learned_undo", **common)
    if made is not None:
        apply_change(session, made.id, actor=actor, now=now, action="learned_undo")
    _close(session, change, "UNDO", UNDONE, actor_id, now, undone_by=made.id if made is not None else None)
    return {"change_id": change.id, "message": "지웠어요 — AI 가 더는 이 지식을 쓰지 않아요."}
