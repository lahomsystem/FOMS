"""이웃 찾기(Search Around — 설계서 7.7 · D105) · 뇌 보기 바탕 점(7.6) — 이웃 지도 탭(7.5 화면 9) · 뇌 보기 탭이 읽는다.

- :func:`search_around` — 한 항목 둘레(링크 종류 · 걸음 1 ~ 2 · 상한)의 점 · 선 · 종류별 수. 엔진은 :func:`.read.neighbours`
  (재귀 CTE)이고 여기는 물음 꼴 검사와 화면용 가벼운 줄(글 · 실음 칸 없음)만 맡는다. **보기 범위는 점 · 선 · 수 모두에**
  걸린다(볼 수 없는 항목은 지나가지도 않는다 — 4절 · 12절). 끝 날이 지난 항목 · 링크도 빠진다(D105).
- :func:`brain_points` — 볼 수 있는 · 유효 기간 안 지금 항목 전체의 **키 · 유형 · 상태 표시 · 쓰인 횟수만**(이름 · 글 없음).
  뇌 보기는 키 해시로 자리를 정하므로(7.6) 자리 칸이 따로 없다. 상한 :data:`.constants.MAX_BRAIN_POINTS`(쓰인 횟수 많은 순).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from sqlalchemy import func, select

from foms.persistence.brain.models import BrainObject
from foms.services.brain.constants import (
    KEY_RE, LINK_KINDS, MAX_BRAIN_POINTS, MAX_NEIGHBOUR_DEPTH, MAX_NEIGHBOUR_LIMIT, STATUS_DRAFT, STATUS_RETIRED, TYPES,
)
from foms.services.brain.labels import pref_of
from foms.services.brain.read import current_item, neighbours, visible_clauses
from foms.services.brain.scope import Viewer
from foms.services.brain.usage import usage_total

DEFAULT_LIMIT = 60
#: 바탕 점 상태 표시(비트) — 초안 · 은퇴 · 낡음.
FLAG_DRAFT, FLAG_RETIRED, FLAG_STALE = 1, 2, 4


class AroundQueryError(ValueError):
    """이웃 찾기 물음 값이 정한 꼴 밖이다(화면에는 정한 글만)."""


@dataclass(frozen=True)
class AroundQuery:
    """이웃 찾기 물음 — 시작 키 · 링크 종류(``None`` = 모두) · 걸음 · 상한."""

    key: str
    kinds: Optional[tuple[str, ...]] = None
    depth: int = 1
    limit: int = DEFAULT_LIMIT


def _number(value: Any, default: int, low: int, high: int, name: str) -> int:
    """정수 칸(없으면 기본 · 범위 밖이면 꼴 오류)."""
    text = str(value or "").strip()
    if not text:
        return default
    if not text.isdigit() or not low <= int(text) <= high:
        raise AroundQueryError(name)
    return int(text)


def parse_around(args: Mapping[str, Any]) -> AroundQuery:
    """요청 인자(``key`` · ``kinds=a,b`` · ``depth`` · ``limit``) → :class:`AroundQuery`. 꼴 밖이면 :class:`AroundQueryError`."""
    key = str(args.get("key") or "").strip()
    if not KEY_RE.fullmatch(key):
        raise AroundQueryError("key")
    raw = str(args.get("kinds") or "").strip()
    kinds = tuple(dict.fromkeys(k.strip() for k in raw.split(",") if k.strip())) if raw else None
    if kinds is not None and (not kinds or any(k not in LINK_KINDS for k in kinds)):
        raise AroundQueryError("kinds")
    return AroundQuery(key=key, kinds=kinds, depth=_number(args.get("depth"), 1, 1, MAX_NEIGHBOUR_DEPTH, "depth"),
                       limit=_number(args.get("limit"), DEFAULT_LIMIT, 1, MAX_NEIGHBOUR_LIMIT, "limit"))


def light(item: Mapping[str, Any], today: datetime.date) -> dict[str, Any]:
    """그림 · 목록 줄 하나(글 · 실음 칸 · 사람 칸 없음). 이름은 카드 제목과 같은 규칙(한글 이름표 먼저 — 읽은 줄의 실음 칸에서)."""
    stale_after = item.get("stale_after")
    return {"key": item["key"], "name": pref_of(item["name"], item.get("payload")), "type": item["type"],
            "layer": item["layer"], "status": item["status"], "confidence": item.get("confidence"),
            "usage_count": int(item.get("usage_count") or 0), "ended": bool(item.get("ended")),
            "stale": bool(stale_after and datetime.date.fromisoformat(stale_after) < today)}


def search_around(session: Any, viewer: Viewer, query: AroundQuery, *,
                  today: datetime.date) -> Optional[dict[str, Any]]:
    """한 항목 둘레 — ``{"start", "items", "edges", "counts", "total", "depth", "limit", "kinds", "truncated"}``.

    시작 항목을 볼 수 없거나 없으면 ``None``(화면 · API 404 — 둘을 가르지 않는다). ``counts`` 는 종류별로 닿은 항목 수(상한 앞 ·
    볼 수 있는 것만), ``items`` 는 걸음 → 키 순 상한까지, ``edges`` 는 시작 + 실은 항목 사이의 선.
    """
    start = current_item(session, viewer, query.key, today)
    if start is None:
        return None
    found = neighbours(session, viewer, query.key, kinds=query.kinds, depth=query.depth, limit=query.limit,
                       today=today)
    if found is None:
        return None
    items = [{**light(item, today), "depth": item["depth"], "via": item["via"]} for item in found["items"]]
    return {"start": light(start, today), "items": items, "edges": found["edges"], "counts": found["counts"],
            "total": found["total"], "depth": query.depth, "limit": query.limit,
            "kinds": list(query.kinds) if query.kinds else list(LINK_KINDS),
            "truncated": found["total"] > len(items)}


def brain_points(session: Any, viewer: Viewer, *, today: datetime.date,
                 cap: int = MAX_BRAIN_POINTS) -> dict[str, Any]:
    """뇌 보기 바탕 점 — ``{"types": [...], "rows": [[키, 유형 번호, 표시, 쓰인 횟수]], "total", "capped"}``.

    볼 수 있는 · 유효 기간 안 지금 항목만(수도 같은 조건). 이름 · 글은 싣지 않는다(이름표는 고른 항목 · 이웃만 — 7.6).
    """
    conditions = visible_clauses(viewer, today)
    total = int(session.execute(select(func.count()).select_from(BrainObject).where(*conditions)).scalar_one())
    rows = session.execute(select(BrainObject.item_key, BrainObject.item_type, BrainObject.status,
                                  BrainObject.stale_after, usage_total().label("used"))
                           .where(*conditions).order_by(usage_total().desc(), BrainObject.item_key)
                           .limit(max(1, min(int(cap), MAX_BRAIN_POINTS)))).all()
    index = {t: i for i, t in enumerate(TYPES)}
    out = []
    for key, item_type, status, stale_after, usage in rows:
        flags = (FLAG_DRAFT if status == STATUS_DRAFT else 0) | (FLAG_RETIRED if status == STATUS_RETIRED else 0)
        flags |= FLAG_STALE if stale_after is not None and stale_after < today else 0
        out.append([key, index.get(item_type, -1), flags, int(usage or 0)])
    return {"types": list(TYPES), "rows": out, "total": total, "capped": total > len(out)}
