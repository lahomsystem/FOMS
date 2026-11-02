"""다시 확인(설계서 7.5 화면 5 · '다시 확인' · 사장님 D103) — 낡음 날이 지났거나 다가오는 항목 묶음, 쓰인 횟수 순, '아직 맞음' 한 번.

- **목록**: 지금 줄 · 반영 상태 · 낡음 날(:data:`.constants.STALE_DAYS` 주기)이 오늘 + :data:`RECHECK_SOON_DAYS` 안. 이 사람이
  결정할 수 있는 항목만(제안함과 같은 규칙 — 사장님 몫 유형 · 공통 바탕은 ADMIN) · 보기 범위 안의 것만(질의 단계 · 수 포함).
- **'아직 맞음'**(:func:`confirm_still_true`): 마지막 확인 날만 오늘로 바꾸는 **제안을 만들고 곧바로 반영 동작으로 넣는다** —
  다른 고침과 같은 길(권한 · 기준 판 다시 확인 · 새 판 · 하루 판 · 감사 한 줄 ``recheck=1``). 낡음 날은 반영 동작이 주기로 다시
  센다. 그 항목에 열린 제안이 있으면 막는다(제안함에서 먼저 결정 — 넣으면 그 제안의 기준 판이 바뀌므로).
- **예외**는 카드의 '고칠 말 제안'(제안함 길)으로.
- **묶음 알림 한 줄**(:func:`recheck_counts` · :func:`summary_line`) — 폰 알림은 아직 없다(수 API 만 — 나중에 붙인다).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import and_, case, false, func, select, true

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.access import approver_layers
from foms.services.brain.apply import ApplyResult, apply_change
from foms.services.brain.constants import CHANGE_OPEN, OWNER_ONLY_TYPES, RECHECK_SOON_DAYS, STATUS_ACTIVE
from foms.services.brain.errors import BrainConflictError, BrainOpenProposalError, BrainPermissionError
from foms.services.brain.proposals import Proposer, propose_update
from foms.services.brain.read import visible_clauses
from foms.services.brain.usage import usage_sum, usage_total
from foms.services.brain.review_rules import clamp_ms
from foms.services.brain.scope import Viewer, viewer_of
from foms.services.brain.store import kst_day
from foms.services.datetime_kst import now_utc_naive

RECHECK_REASON = "다시 확인 — 아직 맞음"
MAX_ROWS = 100


def _decidable(viewer: Viewer) -> Any:
    """이 사람이 고침을 결정할 수 있는 항목(질의 조건 — 제안함과 같은 규칙)."""
    layers = approver_layers(viewer)
    if layers is None:
        return true()
    if not layers:
        return false()
    return and_(BrainObject.layer.in_(layers), BrainObject.item_type.notin_(sorted(OWNER_ONLY_TYPES)))


def _conditions(viewer: Viewer, today: datetime.date) -> list[Any]:
    """다시 볼 항목 조건 — 지금 줄 · 볼 수 있음 · 반영 · 낡음 날이 오늘 + 다가오는 날 수 안 · 결정할 수 있음."""
    horizon = today + datetime.timedelta(days=RECHECK_SOON_DAYS)
    return [*visible_clauses(viewer), BrainObject.status == STATUS_ACTIVE, BrainObject.stale_after.is_not(None),
            BrainObject.stale_after <= horizon, _decidable(viewer)]


def _open_change() -> Any:
    """그 항목에 열린 제안이 있나(상관 부분 질의)."""
    return select(BrainChange.id).where(BrainChange.item_key == BrainObject.item_key,
                                        BrainChange.status == CHANGE_OPEN).exists()


def recheck_counts(session: Any, viewer: Viewer, *, today: datetime.date) -> dict[str, Any]:
    """묶음 알림 재료 — ``{"overdue", "soon", "total", "line"}``(보기 범위 · 결정 가능으로 거른 수)."""
    overdue = func.sum(case((BrainObject.stale_after < today, 1), else_=0))
    row = session.execute(select(func.count(), overdue).where(*_conditions(viewer, today))).one()
    total, late = int(row[0] or 0), int(row[1] or 0)
    counts = {"overdue": late, "soon": total - late, "total": total}
    return {**counts, "line": summary_line(counts)}


def summary_line(counts: dict[str, int]) -> str:
    """묶음 알림 한 줄(폰 알림이 붙으면 이 글 하나만 보낸다)."""
    if not counts.get("total"):
        return "다시 볼 항목이 없어요."
    return (f"다시 볼 항목 {counts['total']}개 — 확인 날 지남 {counts['overdue']}개 · "
            f"{RECHECK_SOON_DAYS}일 안 {counts['soon']}개")


def recheck_list(session: Any, viewer: Viewer, *, today: datetime.date, limit: int = MAX_ROWS) -> dict[str, Any]:
    """다시 확인 목록 — 쓰인 횟수 많은 순(같으면 낡음 날 이른 순). 줄마다 열린 제안 여부(같은 질의)."""
    rows = session.execute(select(BrainObject, _open_change().label("open"), usage_sum().label("used"))
                           .where(*_conditions(viewer, today))
                           .order_by(usage_total().desc(), BrainObject.stale_after, BrainObject.item_key)
                           .limit(max(1, min(int(limit), MAX_ROWS)))).all()
    items = [{"key": row.item_key, "name": row.name, "type": row.item_type, "layer": row.layer, "brand": row.brand,
              "version": row.version, "usage_count": int(row.usage_count or 0) + int(used or 0),
              "checked_at": row.checked_at.isoformat() if row.checked_at else None,
              "stale_after": row.stale_after.isoformat(), "overdue": row.stale_after < today,
              "days": (row.stale_after - today).days, "open": bool(is_open), "snippet": (row.text or "")[:120]}
             for row, is_open, used in rows]
    return {"items": items, "counts": recheck_counts(session, viewer, today=today)}


def confirm_still_true(session: Any, key: str, *, actor: Any, version: Any, view_ms: Any = None,
                       now: Optional[datetime.datetime] = None) -> Optional[ApplyResult]:
    """'아직 맞음' — 확인 날만 오늘로 바꾸는 제안을 만들고 반영 동작으로 넣는다. 오늘 이미 확인했으면 ``None``.

    Raises:
        BrainPermissionError: 볼 수 없거나 없는 항목(호출자가 404).
        BrainConflictError: 화면의 판이 지금 판과 다르다.
        BrainOpenProposalError: 열린 제안이 있다(제안함에서 먼저).
    """
    now = now or now_utc_naive()
    viewer = viewer_of(actor)
    current = session.execute(select(BrainObject).where(BrainObject.item_key == key, *visible_clauses(viewer))
                              .with_for_update()).scalar_one_or_none()
    if current is None or viewer.user_id is None:
        raise BrainPermissionError("볼 수 없는 항목이다")
    if version != current.version:
        raise BrainConflictError(current.version)
    if session.execute(select(BrainChange.id).where(BrainChange.item_key == key,
                                                    BrainChange.status == CHANGE_OPEN).limit(1)).first():
        raise BrainOpenProposalError("열린 제안이 있다 — 제안함에서 먼저 결정한다")
    today = kst_day(now)
    if current.checked_at == today:
        return None
    change = propose_update(session, key=key, base_version=current.version, after={"checked_at": today.isoformat()},
                            reason=RECHECK_REASON, proposer=Proposer.user(viewer.user_id), now=now, known="",
                            action="recheck")
    detail = {"recheck": 1, **({"ms": clamp_ms(view_ms)} if clamp_ms(view_ms) is not None else {})}
    return apply_change(session, change.id, actor=actor, now=now, detail=detail, action="recheck")
