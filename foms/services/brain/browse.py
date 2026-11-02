"""'회사 지식' 화면 읽기 — 찾기(유형별 묶음) · 지식 표(유형 하나 · 거르기 · 정렬 · 쪽) · 유형 지도(설계서 7.5 화면 1 · 2 · 7).

**모든 질의 · 수는 보는 사람의 범위로 질의 단계에서 거른다**(:func:`.read.visible_clauses` — 4절 · 12절 첫 줄). 볼 수 없는
항목은 행에도, 유형별 수에도, 쪽 수에도 0 이다. 끝 날이 지난 항목도 같은 조건으로 빠진다(유효 기간으로 읽기 — D105). 목록은 쪽으로 자르고(상한 :data:`MAX_PER_PAGE`), 줄마다 따로 읽지 않는다
(N+1 없음 — '확인 필요'도 같은 질의의 상관 부분 질의).

- **확인 필요** = 그 항목에 열린 제안이 있다(엇갈림 · 고침 제안이 걸린 동안 — 3.1 규칙 4 · 7.5 '판 1 엔 엇갈림도 제안함에').
- **낡음** = 낡음 날(마지막 확인 + 유형별 주기, D103)이 오늘(한국 날짜)보다 앞이다.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from sqlalchemy import exists, func, or_, select

from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain.constants import (
    ALLOWED_LINKS, BRANDS, CHANGE_OPEN, CONFIDENCES, EXT_CALCULATOR, EXT_SETTING, GRADES, LAYERS, LINK_KINDS,
    OBJECT_STATUSES, TYPE_LAYERS, TYPES,
)
from foms.services.brain.display import TYPE_GROUPS, display_table
from foms.services.brain.read import (
    MAX_QUERY, count_items, effective_clauses, search_match, search_type_counts, visible_clauses,
)
from foms.services.brain.scope import Viewer
from foms.services.brain.conflicts import open_conflict_clause
from foms.services.brain.usage import usage_sum, usage_total

DEFAULT_PER_PAGE, MAX_PER_PAGE = 20, 50
SEARCH_PER_TYPE = 5
SORTS: tuple[str, ...] = ("usage", "checked", "name")
CHECKS: tuple[str, ...] = ("needs_check", "stale")
SNIPPET = 120


class TableQueryError(ValueError):
    """지식 표 물음 값이 정한 값 목록 밖이다(화면에는 정한 글만)."""


@dataclass(frozen=True)
class TableQuery:
    """지식 표 물음 — 유형 하나 + 거르기 + 정렬 + 쪽."""

    item_type: str
    layer: Optional[str] = None
    brand: Optional[str] = None
    status: Optional[str] = None
    grade: Optional[str] = None
    confidence: Optional[str] = None
    check: Optional[str] = None
    sort: str = "usage"
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE


_CHOICES: dict[str, tuple[str, ...]] = {
    "layer": LAYERS, "brand": BRANDS, "status": OBJECT_STATUSES, "grade": GRADES, "confidence": CONFIDENCES,
    "check": CHECKS, "sort": SORTS,
}


def _positive(value: Any, default: int, ceiling: int) -> int:
    """쪽 번호 · 쪽 크기(정수 아니면 기본, 1 ~ 상한)."""
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return default
    return max(1, min(number, ceiling))


def parse_table_query(args: Mapping[str, Any]) -> TableQuery:
    """요청 인자 → :class:`TableQuery`. 빈 값은 '거르지 않음', 목록 밖 값은 :class:`TableQueryError`."""
    item_type = str(args.get("type") or "").strip()
    if item_type not in TYPES:
        raise TableQueryError("type")
    picked: dict[str, Any] = {}
    for name, choices in _CHOICES.items():
        value = str(args.get(name) or "").strip()
        if not value:
            continue
        if value not in choices:
            raise TableQueryError(name)
        picked[name] = value
    return TableQuery(item_type=item_type, **picked, page=_positive(args.get("page"), 1, 10_000),
                      per_page=_positive(args.get("per_page"), DEFAULT_PER_PAGE, MAX_PER_PAGE))


def _open_change() -> Any:
    """'확인 필요' — 그 항목에 열린 제안이 있거나(상관 부분 질의 — ``ix_brain_changes_item_key`` 를 탄다) 열린 엇갈림이 그 항목에
    대한 것이다(:mod:`.conflicts` — 점검 '지금 8')."""
    return or_(exists(select(BrainChange.id).where(BrainChange.item_key == BrainObject.item_key,
                                                   BrainChange.status == CHANGE_OPEN)), open_conflict_clause(BrainObject))


def light_item(row: BrainObject, *, today: datetime.date, needs_check: bool = False,
               used: Optional[int] = None) -> dict[str, Any]:
    """목록 줄 하나(글은 앞 :data:`SNIPPET` 자만 · 실음 칸 없음). ``used`` = 따로 센 쓰인 수(:mod:`.usage`)."""
    text = (row.text or "").strip()
    return {"key": row.item_key, "name": row.name, "type": row.item_type, "layer": row.layer, "brand": row.brand,
            "status": row.status, "confidence": row.confidence, "grade": row.risk_grade, "version": row.version,
            "usage_count": int(row.usage_count or 0) + int(used or 0),
            "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            "stale_after": row.stale_after.isoformat() if row.stale_after else None,
            "stale": bool(row.stale_after and row.stale_after < today), "needs_check": bool(needs_check),
            "snippet": text[:SNIPPET] + ("…" if len(text) > SNIPPET else "")}


def search_grouped(session: Any, viewer: Viewer, query: str, *, today: datetime.date,
                   per_type: int = SEARCH_PER_TYPE) -> dict[str, Any]:
    """찾기(화면 1) — 유형별 묶음 ``{"query", "total", "groups": [{"type", "count", "items"}]}``.

    유형마다 앞 ``per_type`` 개(PostgreSQL 은 이름 비슷함 순, SQLite 는 이름 순)를 한 질의(창 함수)로 읽는다. 수는 유형별 전체.
    """
    text = (query or "").strip()[:MAX_QUERY]
    if not text:
        return {"query": "", "total": 0, "groups": []}
    counts = search_type_counts(session, viewer, text)
    match, postgres = search_match(session, text)
    order = ((func.similarity(BrainObject.name, text).desc(), BrainObject.item_key) if postgres
             else (BrainObject.name, BrainObject.item_key))
    rank = func.row_number().over(partition_by=BrainObject.item_type, order_by=order).label("rank")
    ranked = select(BrainObject.id, rank).where(*effective_clauses(viewer, today), match).subquery("ranked")
    rows = session.execute(select(BrainObject, _open_change().label("open"), usage_sum().label("used"))
                           .join(ranked, ranked.c.id == BrainObject.id)
                           .where(ranked.c.rank <= max(1, min(int(per_type), 20)))
                           .order_by(BrainObject.item_type, ranked.c.rank)).all()
    items: dict[str, list[dict[str, Any]]] = {}
    for row, is_open, used in rows:
        items.setdefault(row.item_type, []).append(light_item(row, today=today, needs_check=is_open, used=used))
    groups = [{"type": t, "count": counts[t], "items": items.get(t, [])} for t in TYPES if counts.get(t)]
    return {"query": text, "total": sum(counts.values()), "groups": groups}


def _table_conditions(query: TableQuery, viewer: Viewer, today: datetime.date) -> list[Any]:
    """지식 표 조건 — 지금 줄 · 볼 수 있는 범위 · 유형 · 거르기.

    유형이 들어갈 수 있는 층(``TYPE_LAYERS`` — 반영 동작이 강제)을 같이 걸어 지금 줄 부분 색인 ``(layer, item_type)`` 을 탄다
    (뜻은 같고, 유형만 걸면 앞 칸이 층인 색인을 못 써 표 전체를 읽는다).
    """
    layers = sorted(TYPE_LAYERS.get(query.item_type, ()))
    conditions = [*visible_clauses(viewer, today), BrainObject.layer.in_(layers), BrainObject.item_type == query.item_type]
    for name, column in (("layer", BrainObject.layer), ("brand", BrainObject.brand), ("status", BrainObject.status),
                         ("grade", BrainObject.risk_grade), ("confidence", BrainObject.confidence)):
        value = getattr(query, name)
        if value is not None:
            conditions.append(column == value)
    if query.check == "stale":
        conditions.append(BrainObject.stale_after < today)
    elif query.check == "needs_check":
        conditions.append(_open_change())
    return conditions


def _table_order(sort: str) -> tuple[Any, ...]:
    """정렬 — 쓰인 횟수 많은 순 · 오래 확인 안 한 순(확인 날 없음 먼저) · 이름 순. 끝은 늘 키(쪽이 흔들리지 않게)."""
    if sort == "checked":
        return BrainObject.checked_at.asc().nulls_first(), BrainObject.item_key
    if sort == "name":
        return BrainObject.name, BrainObject.item_key
    return usage_total().desc(), BrainObject.item_key


def table_page(session: Any, viewer: Viewer, query: TableQuery, *, today: datetime.date) -> dict[str, Any]:
    """지식 표(화면 2) — ``{"type", "rows", "total", "page", "pages", "per_page", "type_counts"}``."""
    conditions = _table_conditions(query, viewer, today)
    total = int(session.execute(select(func.count()).select_from(BrainObject).where(*conditions)).scalar_one())
    pages = max(1, -(-total // query.per_page))
    page = min(query.page, pages)
    rows = session.execute(select(BrainObject, _open_change().label("open"), usage_sum().label("used"))
                           .where(*conditions).order_by(*_table_order(query.sort))
                           .offset((page - 1) * query.per_page).limit(query.per_page)).all()
    return {"type": query.item_type, "rows": [light_item(row, today=today, needs_check=o, used=u) for row, o, u in rows],
            "total": total, "page": page, "pages": pages, "per_page": query.per_page,
            "type_counts": count_items(session, viewer, today=today)["types"]}


def _pairs(kind: str) -> list[list[str]]:
    """링크 종류의 허용 짝(시작 유형, 끝 유형) — 유형 차례대로."""
    order = (*TYPES, EXT_CALCULATOR, EXT_SETTING)
    starts, ends = ALLOWED_LINKS[kind]
    return [[a, b] for a in order if a in starts for b in order if b in ends]


def compress_types(types: list[str]) -> list[dict[str, str]]:
    """유형 목록 → 묶음을 통째로 덮으면 ``{"group": 키}`` 하나, 나머지는 ``{"type": 유형}``(목록 · 그림이 같은 꼴로 줄인다)."""
    wanted, out = set(types), []
    for key, _label, members in TYPE_GROUPS:
        if len(members) > 1 and set(members) <= wanted:
            out.append({"group": key})
            wanted -= set(members)
    order = (*TYPES, EXT_CALCULATOR, EXT_SETTING)
    return out + [{"type": t} for t in order if t in wanted]


def type_map_data(counts: Mapping[str, int]) -> dict[str, Any]:
    """유형 지도 자료(순수) — 유형 묶음 · 유형별 수 · 링크 종류별 허용 짝(줄인 시작 · 끝 포함) · 표시 표."""
    groups = []
    for key, label, types in TYPE_GROUPS:
        groups.append({"key": key, "label": label, "types": [
            {"type": t, "count": int(counts.get(t, 0)), "layers": sorted(TYPE_LAYERS.get(t, ())),
             "external": t in (EXT_CALCULATOR, EXT_SETTING)} for t in types]})
    links = []
    for kind in LINK_KINDS:
        pairs = _pairs(kind)
        starts = list(dict.fromkeys(a for a, _b in pairs))
        ends = list(dict.fromkeys(b for _a, b in pairs))
        links.append({"kind": kind, "pairs": pairs, "from": compress_types(starts), "to": compress_types(ends)})
    return {"groups": groups, "links": links, "total": int(sum(counts.values())), "display": display_table()}


def type_map(session: Any, viewer: Viewer) -> dict[str, Any]:
    """유형 지도(화면 7) — :func:`type_map_data` 에 유형별 수(볼 수 있는 것만)를 넣는다.

    유형 · 짝은 코드 상수(:mod:`.constants`)에서 오고 화면에서 고치지 않는다. 수만 DB 에서 센다.
    """
    return type_map_data(count_items(session, viewer)["types"])
