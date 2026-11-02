"""연결 개수 규칙(설계서 7.7 · 사장님 D105) — 최대는 반영 때 막고, 최소는 '빠진 링크'로 알린다.

규칙 표는 :data:`foms.services.brain.constants.LINK_CARDINALITY`((시작 유형, 링크 종류) → (최소, 최대)). 세는 것은 그 항목에서
**나가는** 지금 · 유효 기간 안(D105) 링크다.

- **최대**(:func:`check_link_limit`): 반영 동작이 링크 더하기 때 부른다. 데이터 규칙이라 보는 사람과 무관하게 모든 링크를 센다.
  같은 때 두 반영이 같은 항목에 더하지 못하게 시작 항목 줄을 잠근 뒤 센다(PostgreSQL).
- **최소**(:func:`missing_links` — 카드 · :func:`quality_counts` — 품질 수 API): 막지 않고 알린다. 보는 사람이 볼 수 없는 끝으로
  가는 링크는 세지 않는다(볼 수 없는 항목이 있다는 것조차 새지 않게 — 4절 '모아 센 수에도 범위'). 바깥 정본 끝
  (``calc:`` · ``setting:``)은 늘 센다. 수도 볼 수 있는 · 유효 기간 안 항목만 센다.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.constants import EXTERNAL_PREFIXES, LINK_CARDINALITY, cardinality
from foms.services.brain.errors import BrainLinkLimitError
from foms.services.brain.scope import Viewer, scope_clause
from foms.services.brain.store import in_force, is_current


def out_degree(session: Any, key: str, kind: str, today: datetime.date) -> int:
    """그 항목에서 나가는 지금 · 유효 기간 안 그 종류 링크 수(모든 끝)."""
    return int(session.execute(select(func.count()).select_from(BrainLink).where(
        BrainLink.from_key == key, BrainLink.kind == kind, is_current(BrainLink), in_force(BrainLink, today),
    )).scalar_one())


def check_link_limit(session: Any, source: BrainObject, kind: str, today: datetime.date) -> None:
    """링크 하나를 더해도 최대를 넘지 않나(반영 동작 — 링크 더하기).

    Raises:
        BrainLinkLimitError: 이미 최대만큼 이어져 있다.
    """
    _low, high = cardinality(source.item_type, kind)
    if high is not None and out_degree(session, source.item_key, kind, today) >= high:
        raise BrainLinkLimitError(kind, high)


def _seen_links(viewer: Viewer, today: datetime.date, owner: Any, kind: str) -> Any:
    """``owner`` 항목에서 나가는, 보는 사람이 셀 수 있는 그 종류 링크 수(상관 부분 질의)."""
    target = aliased(BrainObject)
    seen_target = select(target.item_key).where(target.item_key == BrainLink.to_key, is_current(target),
                                                *_owner_clauses(viewer, today, target)).exists()
    external = or_(*(BrainLink.to_key.like(prefix + "%") for prefix in EXTERNAL_PREFIXES))
    return (select(func.count()).select_from(BrainLink)
            .where(BrainLink.from_key == owner.item_key, BrainLink.kind == kind, is_current(BrainLink),
                   in_force(BrainLink, today), or_(external, seen_target))
            .correlate(owner).scalar_subquery())


def missing_links(session: Any, viewer: Viewer, item: dict[str, Any], *,
                  today: datetime.date) -> list[dict[str, Any]]:
    """카드 '빠진 링크' — 최소에 못 미치는 종류 ``[{"kind", "min", "max", "have"}]``(최소 규칙이 없으면 빈 목록)."""
    rules = [(kind, low, high) for (item_type, kind), (low, high) in LINK_CARDINALITY.items()
             if item_type == item["type"] and low > 0]
    if not rules:
        return []
    owner = aliased(BrainObject)
    out = []
    for kind, low, high in rules:
        have = session.execute(select(_seen_links(viewer, today, owner, kind)).where(
            owner.item_key == item["key"], is_current(owner))).scalar_one_or_none() or 0
        if have < low:
            out.append({"kind": kind, "min": low, "max": high, "have": int(have)})
    return out


def quality_counts(session: Any, viewer: Viewer, *, today: datetime.date) -> dict[str, Any]:
    """품질 수(7.5 화면 11 의 앞 조각) — 규칙마다 볼 수 있는 항목 수 · 최소 미달 수 · 최대 넘음 수.

    Returns:
        ``{"rules": [{"type", "kind", "min", "max", "items", "missing", "over"}], "missing_total", "over_total"}``.
    """
    rows = []
    for (item_type, kind), (low, high) in LINK_CARDINALITY.items():
        owner = aliased(BrainObject)
        seen = _seen_links(viewer, today, owner, kind)
        visible = [owner.item_type == item_type, is_current(owner), *_owner_clauses(viewer, today, owner)]
        items = int(session.execute(select(func.count()).select_from(owner).where(*visible)).scalar_one())
        missing = int(session.execute(select(func.count()).select_from(owner).where(*visible, seen < low))
                      .scalar_one()) if low > 0 and items else 0
        over = int(session.execute(select(func.count()).select_from(owner).where(*visible, seen > high))
                   .scalar_one()) if high is not None and items else 0
        rows.append({"type": item_type, "kind": kind, "min": low, "max": high, "items": items, "missing": missing,
                     "over": over})
    return {"rules": rows, "missing_total": sum(r["missing"] for r in rows), "over_total": sum(r["over"] for r in rows)}


def _owner_clauses(viewer: Viewer, today: datetime.date, owner: Any) -> list[Any]:
    """별칭 항목 표에 같은 보기 범위 · 유효 기간 조건(:func:`.read.visible_clauses` 와 같은 뜻)."""
    return [scope_clause(viewer, owner.visibility), in_force(owner, today)]


def item_rules(item_type: Optional[str]) -> list[dict[str, Any]]:
    """그 유형의 연결 개수 규칙(화면 안내용)."""
    return [{"kind": kind, "min": low, "max": high} for (t, kind), (low, high) in LINK_CARDINALITY.items()
            if t == item_type]
