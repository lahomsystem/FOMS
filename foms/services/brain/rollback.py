"""판 되돌리기(설계서 6절 '되돌리기 — 판 단위 · 층 단위. 되돌린 판도 이력에 남는다' · 7.5 화면 6) — **ADMIN 만**.

한 판의 한 층(:class:`BrainRelease` 줄)에서 반영된 제안을 거꾸로 되돌린다. **정본은 여기서 직접 쓰지 않는다** — 되돌릴
것마다 '옛 값' 제안을 만들고(사람 제안 · ``rollback_of_version``) 곧바로 반영 동작(:func:`.apply.apply_change`)으로 넣는다.
그래서 되돌림도 새 판 줄 · 하루 판 · 감사 줄을 그대로 남기고, 되돌린 판 줄은 지우지 않고 ``diff.rollback`` 표시만 붙는다.

- 차례: ① 그 판에서 **더한 링크 빼기** ② 항목(만든 것은 지우기 · 고친 · 은퇴한 · 지운 것은 그 판 앞 판으로) ③ 그 판에서
  **뺀 링크 · 지우기가 함께 닫은 링크 다시 더하기**(끝 항목이 먼저 돌아와 있어야 해서 마지막).
- **뒤 판이 같은 항목 · 링크를 또 고쳤으면 통째로 막는다**(:class:`BrainRollbackBlockedError`) — 뒤 고침을 덮지 않게, 그때는
  항목마다 '옛 값을 새 제안으로'(:func:`.proposals.propose_rollback`).
- 되돌림은 **새 판 번호**에 붙는다(되돌린 판과 섞이지 않게 — 그날 그 뒤 반영도 그 새 번호에 붙는다).
- 판 0(지식 문서에서 옮겨 온 판)은 되돌리지 않는다(지식 전체를 지우는 일이라 — 항목마다 길로).
커밋은 호출자 몫이다.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainChange, BrainLink, BrainRelease
from foms.services.brain import releases
from foms.services.brain.apply import apply_change
from foms.services.brain.constants import (
    CHANGE_APPLIED, LAYERS, LINK_OPS, OP_CREATE, OP_DELETE, OP_LINK_ADD, OP_LINK_REMOVE,
)
from foms.services.brain.errors import (
    BrainPermissionError, BrainRollbackBlockedError, BrainShapeError, BrainTargetError,
)
from foms.services.brain.proposals import Proposer, propose_delete, propose_link, propose_rollback
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import LINK_FIELDS, current_link, current_object, kst_day, values_of
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog

#: 이 되돌림이 만든 제안 · 결정의 액션 이름(:mod:`.actions`).
ACTION = "release_rollback"


def _ident(change: BrainChange) -> tuple:
    """되돌릴 것의 정체 — 항목 키 또는 (링크 종류, 시작, 끝)."""
    if change.op in LINK_OPS:
        return ("link", change.link_kind, change.link_from, change.link_to)
    return ("item", change.item_key)


def _release_row(session: Any, number: int, layer: str) -> BrainRelease:
    """되돌릴 판 줄(잠금) — 없으면 대상 오류, 이미 되돌렸으면 대상 오류."""
    row = session.execute(select(BrainRelease).where(BrainRelease.number == number, BrainRelease.layer == layer)
                          .with_for_update()).scalar_one_or_none()
    if row is None:
        raise BrainTargetError(f"없는 판이다: {number} {layer}")
    if (row.diff or {}).get("rollback"):
        raise BrainTargetError("이미 되돌린 판이다")
    return row


def _groups(session: Any, number: int, layer: str) -> dict[tuple, list[BrainChange]]:
    """그 판 · 층에서 반영된 제안을 정체마다(반영 차례)."""
    changes = session.execute(select(BrainChange).where(
        BrainChange.status == CHANGE_APPLIED, BrainChange.release_no == number, BrainChange.layer == layer)
        .order_by(BrainChange.id)).scalars().all()
    groups: dict[tuple, list[BrainChange]] = {}
    for change in changes:
        groups.setdefault(_ident(change), []).append(change)
    return groups


def _blocked(session: Any, groups: dict[tuple, list[BrainChange]]) -> int:
    """뒤에 같은 정체를 또 고친 반영이 있는 정체 수(한 질의)."""
    first = min(c.id for cs in groups.values() for c in cs)
    items = sorted({k[1] for k in groups if k[0] == "item"})
    froms = sorted({k[2] for k in groups if k[0] == "link"})
    later = session.execute(select(BrainChange).where(
        BrainChange.status == CHANGE_APPLIED, BrainChange.id > first,
        or_(BrainChange.item_key.in_(items), BrainChange.link_from.in_(froms)))).scalars().all()
    last = {ident: max(c.id for c in cs) for ident, cs in groups.items()}
    hit = {_ident(c) for c in later if _ident(c) in last and c.id > last[_ident(c)]}
    return len(hit)


def _apply(session: Any, change: BrainChange, actor: Any, now: datetime.datetime, number: int) -> None:
    """되돌림 제안 하나를 반영 동작으로 넣는다(감사 줄에 되돌린 판 번호)."""
    apply_change(session, change.id, actor=actor, now=now, detail={"release_rollback": number},
                 action="release_rollback")


def _undo_item(session: Any, changes: list[BrainChange], ctx: dict[str, Any]) -> int:
    """항목 하나를 그 판 앞으로 — 만든 것은 지우고, 그 밖은 앞 판 값을 새 제안으로. 넣은 수."""
    first, key = changes[0], changes[0].item_key
    current = current_object(session, key)
    if first.op == OP_CREATE:
        if current is None:
            return 0
        change = propose_delete(session, key=key, base_version=current.version, reason=ctx["reason"],
                                proposer=ctx["proposer"], now=ctx["now"], rollback_of=0, action=ACTION)
    else:
        try:
            change = propose_rollback(session, key=key, to_version=int(first.base_version), reason=ctx["reason"],
                                      proposer=ctx["proposer"], now=ctx["now"], action=ACTION)
        except BrainTargetError as exc:
            if str(exc) != "바뀐 칸이 없다":
                raise
            return 0
    _apply(session, change, ctx["actor"], ctx["now"], ctx["number"])
    return 1


def _link_row(session: Any, ident: tuple, version: int) -> Optional[BrainLink]:
    """그 링크의 그 판 줄."""
    _tag, kind, start, end = ident
    return session.execute(select(BrainLink).where(BrainLink.kind == kind, BrainLink.from_key == start,
                                                   BrainLink.to_key == end, BrainLink.version == version)
                           ).scalar_one_or_none()


def _readd_link(session: Any, row: BrainLink, ctx: dict[str, Any]) -> int:
    """닫힌 링크 판을 다시 더한다(이미 지금 링크가 있거나 끝이 없으면 건너뜀)."""
    if current_link(session, row.kind, row.from_key, row.to_key) is not None:
        return 0
    values = {k: v for k, v in values_of(row, LINK_FIELDS).items() if v is not None}
    try:
        change = propose_link(session, op=OP_LINK_ADD, kind=row.kind, from_key=row.from_key, to_key=row.to_key,
                              reason=ctx["reason"], proposer=ctx["proposer"], values=values, now=ctx["now"],
                              rollback_of=row.version, action=ACTION)
    except BrainTargetError:
        return 0  # 끝 항목이 지금 없다 — 링크만 되살릴 수 없다
    _apply(session, change, ctx["actor"], ctx["now"], ctx["number"])
    return 1


def _remove_added_link(session: Any, ident: tuple, ctx: dict[str, Any]) -> int:
    """그 판에서 더한 링크를 뺀다."""
    _tag, kind, start, end = ident
    link = current_link(session, kind, start, end)
    if link is None:
        return 0
    change = propose_link(session, op=OP_LINK_REMOVE, kind=kind, from_key=start, to_key=end, reason=ctx["reason"],
                          proposer=ctx["proposer"], base_version=link.version, now=ctx["now"], rollback_of=0,
                          action=ACTION)
    _apply(session, change, ctx["actor"], ctx["now"], ctx["number"])
    return 1


def _closed_by_deletes(session: Any, changes: list[BrainChange]) -> list[BrainLink]:
    """그 항목 지우기가 함께 닫은 링크 판(지우기 반영 시각에 닫힌 것)."""
    rows: list[BrainLink] = []
    for change in changes:
        if change.op != OP_DELETE or change.decided_at is None:
            continue
        rows += session.execute(select(BrainLink).where(
            BrainLink.superseded_at == change.decided_at,
            or_(BrainLink.from_key == change.item_key, BrainLink.to_key == change.item_key))).scalars().all()
    return rows


def _new_release(session: Any, layer: str, actor_id: int, now: datetime.datetime) -> int:
    """되돌림이 붙을 새 판 번호 줄을 먼저 만든다(그날 뒤 반영도 이 번호에 붙는다)."""
    number = int(session.execute(select(func.max(BrainRelease.number))).scalar() or 0) + 1
    releases.ensure_row(session, number, layer, day=kst_day(now), actor_id=actor_id, now=now)
    return number


def rollback_release(session: Any, number: Any, layer: Any, *, actor: Any, confirm_number: Any,
                     now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """한 판의 한 층을 되돌린다(ADMIN 만) — ``{"number", "layer", "into", "steps"}``.

    Raises:
        BrainPermissionError · BrainShapeError · BrainTargetError · BrainRollbackBlockedError · BrainConflictError.
    """
    now = now or now_utc_naive()
    viewer = viewer_of(actor)
    if not viewer.is_admin or viewer.user_id is None:
        raise BrainPermissionError("판 되돌리기는 사장님(ADMIN)만 한다")
    if not isinstance(number, int) or isinstance(number, bool) or layer not in LAYERS or confirm_number != number:
        raise BrainShapeError(["number · layer · confirm_number: 판 번호 · 층 · 같은 판 번호 확인이어야 한다"])
    if number == releases.IMPORT_RELEASE:
        raise BrainTargetError("옮겨 온 판 0 은 되돌리지 않는다")
    row = _release_row(session, number, layer)
    groups = _groups(session, number, layer)
    if not groups:
        raise BrainTargetError("되돌릴 반영이 없다")
    blocked = _blocked(session, groups)
    if blocked:
        raise BrainRollbackBlockedError(blocked)
    into = _new_release(session, layer, viewer.user_id, now)
    ctx = {"actor": actor, "now": now, "number": number, "reason": f"판 {number} 되돌리기",
           "proposer": Proposer.user(viewer.user_id)}
    steps = sum(_remove_added_link(session, ident, ctx) for ident, cs in groups.items()
                if ident[0] == "link" and cs[0].op == OP_LINK_ADD)
    steps += sum(_undo_item(session, cs, ctx) for ident, cs in groups.items() if ident[0] == "item")
    readd = [r for ident, cs in groups.items() if ident[0] == "link" and cs[0].op == OP_LINK_REMOVE
             for r in [_link_row(session, ident, int(cs[0].base_version))] if r is not None]
    readd += [r for ident, cs in groups.items() if ident[0] == "item" for r in _closed_by_deletes(session, cs)]
    steps += sum(_readd_link(session, r, ctx) for r in readd)
    diff = copy.deepcopy(row.diff or {})
    diff["rollback"] = {"by": viewer.user_id, "at": now.isoformat(timespec="seconds"), "into": into, "steps": steps}
    row.diff = diff
    flag_modified(row, "diff")
    session.add(SecurityLog(user_id=viewer.user_id, action="BRAIN_RELEASE_ROLLBACK", target_type="brain_release",
                            target_id=row.id, timestamp=now,
                            message=f"BRAIN_RELEASE_ROLLBACK release={number} layer={layer} steps={steps} into={into}",
                            detail={"release": number, "layer": layer, "steps": steps, "into": into}))
    session.flush()
    return {"number": number, "layer": layer, "into": into, "steps": steps}

