"""읽기 — 지금 항목 · 이력 · 이웃 · 찾기 · 개수. **모든 읽기는 보는 사람의 범위를 받아 질의 단계에서 거른다**(모아 센 수 포함 —
설계서 4절 · 12절 첫 줄). 볼 수 없는 항목은 결과에도 수에도 0 이고, 이웃 따라가기도 그 항목을 지나가지 않는다.

- 이웃(:func:`neighbours`)은 지금 링크를 양쪽으로 따라가는 재귀 CTE(걸음 ≤ 2 · 종류 거르기 · 상한)다(7.5 '이 크기에서 충분').
  바깥 정본 자리(``calc:`` · ``setting:``)는 brain 항목이 아니라 이웃에 넣지 않는다. 닿은 항목 사이의 선(종류 · 양 끝)도 같이
  준다(이웃 지도 · 뇌 보기 — 7.5 화면 9 · 7.6).
- **유효 기간으로 읽기**(7.7 · D105): 끝 날(``valid_to``)이 지난 항목 · 링크는 찾기 · 표 · 이웃 · 모아 센 수에서 뺀다
  (:func:`foms.services.brain.store.in_force`). 키로 바로 읽는 :func:`current_item` 만 끝난 항목도 돌려주고 ``ended`` 를 단다
  (카드가 '기간 끝남'으로 흐리게 보인다). 이력은 모든 판 그대로.
- 찾기(:func:`search`)는 첫 판 자리만 — 이름 · 글 부분 일치(PostgreSQL 은 pg_trgm 색인이 받는 ILIKE + 이름 비슷함 순).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Any, Iterable, Optional

from sqlalchemy import Integer, String, cast, func, literal, or_, select, union_all

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.constants import (
    LINK_KINDS, MAX_NEIGHBOUR_DEPTH, MAX_NEIGHBOUR_EDGES, MAX_NEIGHBOUR_LIMIT, MAX_SEARCH_LIMIT,
)
from foms.services.brain.scope import Viewer, scope_clause
from foms.services.brain.store import in_force, is_current, is_ended, values_of
from foms.services.datetime_kst import get_today_kst

MAX_QUERY = 100


def _item(row: BrainObject, today: Optional[datetime.date] = None) -> dict[str, Any]:
    """줄 → 읽기 dict(정체 · 값 칸 · 판 정보 · 끝 날이 지났나)."""
    return {"key": row.item_key, "ended": is_ended(row.valid_to, today or get_today_kst()), "version": row.version, "brand": row.brand, "layer": row.layer,
            "type": row.item_type, **values_of(row), "stale_after": row.stale_after.isoformat() if row.stale_after else None,
            "usage_count": row.usage_count, "evidence_count": row.evidence_count, "created_by": row.created_by,
            "human_approver_id": row.human_approver_id, "release_no": row.release_no,
            "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
            "superseded_at": row.superseded_at.isoformat() if row.superseded_at else None}


def visible_clauses(viewer: Viewer, today: Optional[datetime.date] = None) -> tuple[Any, ...]:
    """지금 줄 + 볼 수 있는 범위 + 유효 기간 안(D105) 조건 — 화면 읽기 모듈도 같은 조건을 쓴다."""
    return (is_current(BrainObject), scope_clause(viewer, BrainObject.visibility),
            in_force(BrainObject, today or get_today_kst()))


_visible = visible_clauses


def current_item(session: Any, viewer: Viewer, key: str,
                 today: Optional[datetime.date] = None) -> Optional[dict[str, Any]]:
    """키의 지금 판(볼 수 없거나 없으면 ``None`` — 둘을 가르지 않는다). 키로 바로 읽기라 끝난 항목도 돌려준다(``ended``)."""
    row = session.execute(select(BrainObject).where(
        BrainObject.item_key == key, is_current(BrainObject), scope_clause(viewer, BrainObject.visibility),
    )).scalar_one_or_none()
    return _item(row, today) if row is not None else None


def item_history(session: Any, viewer: Viewer, key: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """키의 판들(새 것부터) — 판마다 범위로 거른다(범위가 바뀐 옛 판도 그 범위대로)."""
    query = (select(BrainObject).where(BrainObject.item_key == key, scope_clause(viewer, BrainObject.visibility))
             .order_by(BrainObject.version.desc()).limit(max(1, min(int(limit), MAX_SEARCH_LIMIT))))
    return [_item(row) for row in session.execute(query).scalars()]


def count_items(session: Any, viewer: Viewer, *, layer: Optional[str] = None,
                today: Optional[datetime.date] = None) -> dict[str, Any]:
    """지금 항목 수 — 유형별(볼 수 있는 것 · 유효 기간 안만)."""
    query = select(BrainObject.item_type, func.count()).where(*_visible(viewer, today)).group_by(BrainObject.item_type)
    if layer is not None:
        query = query.where(BrainObject.layer == layer)
    types = {item_type: int(n) for item_type, n in session.execute(query)}
    return {"total": sum(types.values()), "types": dict(sorted(types.items()))}


def _like(text: str) -> str:
    """부분 일치 꼴(``%`` · ``_`` · 역슬래시는 글자로)."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search_match(session: Any, text: str) -> tuple[Any, bool]:
    """찾기 조건 — 이름 · 글 부분 일치(PostgreSQL 은 이름 trgm 비슷함 ``%`` 도) · PostgreSQL 인가."""
    postgres = session.get_bind().dialect.name == "postgresql"
    match = or_(BrainObject.name.ilike(_like(text), escape="\\"), BrainObject.text.ilike(_like(text), escape="\\"))
    if postgres:
        match = or_(match, BrainObject.name.op("%")(text))
    return match, postgres


def search_type_counts(session: Any, viewer: Viewer, query: str) -> dict[str, int]:
    """찾기 결과 수 — 유형별(볼 수 있는 것만 · 상한과 무관)."""
    text = (query or "").strip()[:MAX_QUERY]
    if not text:
        return {}
    match, _postgres = search_match(session, text)
    rows = session.execute(select(BrainObject.item_type, func.count()).where(*_visible(viewer), match)
                           .group_by(BrainObject.item_type))
    return {item_type: int(n) for item_type, n in rows}


def search(session: Any, viewer: Viewer, query: str, *, limit: int = 20,
           item_type: Optional[str] = None) -> dict[str, Any]:
    """이름 · 글 찾기 — ``{"items": [...], "total": n}``(수도 볼 수 있는 것만)."""
    text = (query or "").strip()[:MAX_QUERY]
    if not text:
        return {"items": [], "total": 0}
    match, postgres = search_match(session, text)
    conditions = [*_visible(viewer), match] + ([BrainObject.item_type == item_type] if item_type else [])
    total = session.execute(select(func.count()).select_from(BrainObject).where(*conditions)).scalar_one()
    order = (func.similarity(BrainObject.name, text).desc(), BrainObject.item_key) if postgres else (
        BrainObject.name, BrainObject.item_key)
    rows = session.execute(select(BrainObject).where(*conditions).order_by(*order)
                           .limit(max(1, min(int(limit), MAX_SEARCH_LIMIT)))).scalars()
    return {"items": [_item(row) for row in rows], "total": int(total)}


def _walk(viewer: Viewer, key: str, kinds: tuple[str, ...], depth: int, today: datetime.date) -> Any:
    """재귀 CTE — (닿은 키, 걸음, 마지막 링크 종류). 볼 수 있는 · 유효 기간 안 지금 항목과 유효 기간 안 링크만 지나간다."""
    visible = select(BrainObject.item_key).where(*_visible(viewer, today))
    live = (is_current(BrainLink), in_force(BrainLink, today), BrainLink.kind.in_(kinds))
    edges = union_all(
        select(BrainLink.from_key.label("src"), BrainLink.to_key.label("dst"), BrainLink.kind.label("kind")).where(*live),
        select(BrainLink.to_key.label("src"), BrainLink.from_key.label("dst"), BrainLink.kind.label("kind")).where(*live),
    ).subquery("edges")
    walk = select(cast(literal(key), String(120)).label("node"), cast(literal(0), Integer).label("depth"),
                  cast(literal(""), String(16)).label("via")).cte("walk", recursive=True)
    previous = walk.alias("previous")
    step = (select(edges.c.dst, previous.c.depth + 1, edges.c.kind)
            .join(previous, edges.c.src == previous.c.node)
            .where(previous.c.depth < depth, edges.c.dst.in_(visible)))
    return walk.union(step)


def _edges(session: Any, nodes: list[str], kinds: tuple[str, ...], today: datetime.date) -> list[dict[str, str]]:
    """닿은 항목들 사이의 선(지금 · 유효 기간 안 · 고른 종류) — 양 끝이 모두 ``nodes`` 안(볼 수 있는 것)인 것만."""
    if len(nodes) < 2:
        return []
    rows = session.execute(select(BrainLink.kind, BrainLink.from_key, BrainLink.to_key).where(
        is_current(BrainLink), in_force(BrainLink, today), BrainLink.kind.in_(kinds), BrainLink.from_key.in_(nodes),
        BrainLink.to_key.in_(nodes)).order_by(BrainLink.from_key, BrainLink.kind, BrainLink.to_key)
        .limit(MAX_NEIGHBOUR_EDGES)).all()
    return [{"kind": kind, "from": src, "to": dst} for kind, src, dst in rows]


def neighbours(session: Any, viewer: Viewer, key: str, *, kinds: Optional[Iterable[str]] = None, depth: int = 1,
               limit: int = 50, today: Optional[datetime.date] = None) -> Optional[dict[str, Any]]:
    """한 항목 둘레(걸음 1 ~ 2) — ``{"items", "edges", "counts": {종류: 수}, "total"}``. 시작 항목을 볼 수 없으면 ``None``.

    ``items`` 는 걸음 → 키 순으로 ``limit`` 개(각 항목에 ``depth`` · 닿은 링크 종류 ``via``). ``counts`` · ``total`` 은 상한 앞
    전체 수(볼 수 있는 · 유효 기간 안 것만). ``edges`` 는 시작 항목 + 실은 항목 사이의 선. 시작 항목은 키로 바로 연 것이라
    끝났어도 둘레를 본다(둘레의 끝난 항목 · 링크는 빠진다).
    """
    today = today or get_today_kst()
    if current_item(session, viewer, key, today) is None:
        return None
    chosen = tuple(k for k in LINK_KINDS if kinds is None or k in set(kinds))
    walk = _walk(viewer, key, chosen, max(1, min(int(depth), MAX_NEIGHBOUR_DEPTH)), today)
    reached: dict[str, int] = {}  # 키 → 가장 짧은 걸음
    node_vias: dict[str, set[str]] = defaultdict(set)  # 키 → 그 걸음에 닿은 링크 종류
    kind_nodes: dict[str, set[str]] = defaultdict(set)  # 링크 종류 → 닿은 키
    rows = session.execute(select(walk.c.node, walk.c.depth, walk.c.via).where(walk.c.depth > 0, walk.c.node != key))
    for node, step, via in sorted(rows, key=lambda r: (r[1], r[0], r[2])):
        reached.setdefault(node, step)
        kind_nodes[via].add(node)
        if reached[node] == step:
            node_vias[node].add(via)
    picked = sorted(reached, key=lambda n: (reached[n], n))[:max(1, min(int(limit), MAX_NEIGHBOUR_LIMIT))]
    found = {row.item_key: row for row in session.execute(
        select(BrainObject).where(BrainObject.item_key.in_(picked), *_visible(viewer, today))).scalars()}
    items = [{**_item(found[n], today), "depth": reached[n], "via": sorted(node_vias[n])} for n in picked if n in found]
    counts = {kind: len(nodes) for kind, nodes in sorted(kind_nodes.items())}
    return {"items": items, "edges": _edges(session, [key, *(i["key"] for i in items)], chosen, today),
            "counts": counts, "total": len(reached)}
