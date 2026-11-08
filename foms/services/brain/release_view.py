"""판 화면(설계서 7.5 화면 6) — 판 목록 · 판 차이 요약 · 층마다 되돌림 표시. 되돌리기 동작은 :mod:`.rollback`(ADMIN 만) —
여기는 읽기만.

판 줄(``brain_releases``)의 동작별 수 · 바뀐 키는 모든 범위를 섞어 센 값이라 그대로 보이면 볼 수 없는 항목 수가 샌다
(4절 '모아 센 수에도 범위'). 그래서 화면 수는 **반영된 제안(``brain_changes``)을 보는 사람의 범위로 질의 단계에서 거른 뒤**
센다:

- 항목 동작(만들기 · 고침 · 은퇴 · 지우기) — 그 제안이 만든 판 줄(지우기는 지운 판 줄)의 보기 범위로 거른다.
- 링크 동작 — ADMIN 은 모두, 그 밖은 양 끝(바깥 정본 키는 늘 보임)의 지금 줄을 모두 볼 수 있을 때만.

판 날짜는 판 줄에서 읽는다. 볼 수 있는 바뀜이 하나도 없는 판은 목록에 나오지 않는다(ADMIN 은 모두 본다).
차이 줄의 지식 이름(``title`` · ``link_to_title``)은 카드 제목과 같은 규칙 — 실음 칸 한글 이름(``pref_label``)이 있으면 그것,
없으면 이름(:func:`.inbox.card_title_of` 와 같다 — 영어 키 이름을 앞에 두지 않는다).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import String, and_, cast, distinct, func, literal, or_, select, union_all
from sqlalchemy.orm import aliased

from foms.persistence.brain.models import BrainChange, BrainObject, BrainRelease
from foms.services.brain.constants import CHANGE_APPLIED, EXTERNAL_PREFIXES, LINK_OPS, OBJECT_OPS
from foms.services.brain.releases import IMPORT_RELEASE
from foms.services.brain.scope import Viewer, allowed_scopes, scope_clause
from foms.services.brain.store import is_current

DEFAULT_PER_PAGE, MAX_PER_PAGE = 10, 30
MAX_DIFF_ROWS = 200
PREF_LABEL = "pref_label"


def shown_name(label: Any, name: Optional[str]) -> Optional[str]:
    """화면 이름 — 한글 대표 이름(실음 칸 ``pref_label``)이 있으면 그것, 없으면 이름(카드 제목 규칙)."""
    return label.strip() if isinstance(label, str) and label.strip() else name


def _object_changes(viewer: Viewer) -> Any:
    """반영된 항목 동작 — 그 동작의 판 줄 범위로 거른다."""
    row = aliased(BrainObject)
    version = func.coalesce(BrainChange.result_version, BrainChange.base_version)
    return (select(BrainChange.id.label("change_id"), BrainChange.release_no.label("release_no"),
                   BrainChange.layer.label("layer"), BrainChange.op.label("op"),
                   BrainChange.item_key.label("item_key"), row.name.label("name"),
                   row.payload[PREF_LABEL].as_string().label("label"), row.item_type.label("item_type"),
                   cast(literal(None), String(16)).label("link_kind"), cast(literal(None), String(120)).label("link_to"))
            .join(row, and_(row.item_key == BrainChange.item_key, row.version == version))
            .where(BrainChange.status == CHANGE_APPLIED, BrainChange.op.in_(OBJECT_OPS),
                   scope_clause(viewer, row.visibility)))


def _link_changes(viewer: Viewer) -> Any:
    """반영된 링크 동작 — ADMIN 이 아니면 양 끝의 지금 줄을 볼 수 있을 때만."""
    query = (select(BrainChange.id.label("change_id"), BrainChange.release_no.label("release_no"),
                    BrainChange.layer.label("layer"), BrainChange.op.label("op"),
                    BrainChange.link_from.label("item_key"), cast(literal(None), String(200)).label("name"),
                    cast(literal(None), String(200)).label("label"),
                    cast(literal(None), String(32)).label("item_type"), BrainChange.link_kind.label("link_kind"),
                    BrainChange.link_to.label("link_to"))
             .where(BrainChange.status == CHANGE_APPLIED, BrainChange.op.in_(LINK_OPS)))
    if allowed_scopes(viewer) is None:
        return query
    seen = select(BrainObject.item_key).where(is_current(BrainObject), scope_clause(viewer, BrainObject.visibility))
    outside = [BrainChange.link_to.like(prefix + "%") for prefix in EXTERNAL_PREFIXES]
    return query.where(BrainChange.link_from.in_(seen), or_(*outside, BrainChange.link_to.in_(seen)))


def visible_changes(viewer: Viewer) -> Any:
    """보는 사람이 볼 수 있는 반영된 바뀜(부분 질의)."""
    return union_all(_object_changes(viewer), _link_changes(viewer)).subquery("visible_changes")


def _days(session: Any, numbers: list[int]) -> dict[int, str]:
    """판 번호 → 날짜(그 번호의 아무 층 줄 — 같은 번호는 같은 날)."""
    if not numbers:
        return {}
    rows = session.execute(select(BrainRelease.number, func.min(BrainRelease.day))
                           .where(BrainRelease.number.in_(numbers)).group_by(BrainRelease.number))
    return {int(number): day.isoformat() for number, day in rows if day is not None}


def _rollbacks(session: Any, numbers: list[int]) -> dict[tuple[int, str], dict[str, Any]]:
    """(판 번호, 층) → 되돌림 표시(되돌린 판도 이력에 남는다 — 숫자 · 날만)."""
    if not numbers:
        return {}
    rows = session.execute(select(BrainRelease.number, BrainRelease.layer, BrainRelease.diff)
                           .where(BrainRelease.number.in_(numbers)))
    out = {}
    for number, layer, diff in rows:
        mark = (diff or {}).get("rollback") if isinstance(diff, dict) else None
        if mark:
            out[(int(number), layer)] = {"into": mark.get("into"), "at": str(mark.get("at") or "")[:10]}
    return out


def release_page(session: Any, viewer: Viewer, *, page: int = 1,
                 per_page: int = DEFAULT_PER_PAGE) -> dict[str, Any]:
    """판 목록 ``{"items": [{"number", "day", "import", "layers": [{"layer", "counts", "total"}]}], "total", ...}``."""
    per_page = max(1, min(int(per_page), MAX_PER_PAGE))
    changes = visible_changes(viewer)
    total = int(session.execute(select(func.count(distinct(changes.c.release_no)))).scalar_one())
    pages = max(1, -(-total // per_page))
    page = max(1, min(int(page), pages))
    numbers = [int(n) for n in session.execute(
        select(changes.c.release_no).distinct().order_by(changes.c.release_no.desc())
        .offset((page - 1) * per_page).limit(per_page)).scalars()]
    layers: dict[int, dict[str, dict[str, int]]] = {n: {} for n in numbers}
    if numbers:
        rows = session.execute(select(changes.c.release_no, changes.c.layer, changes.c.op, func.count())
                               .where(changes.c.release_no.in_(numbers))
                               .group_by(changes.c.release_no, changes.c.layer, changes.c.op))
        for number, layer, op, count in rows:
            layers[int(number)].setdefault(layer or "", {})[op] = int(count)
    days = _days(session, numbers)
    marks = _rollbacks(session, numbers)
    items = [{"number": n, "day": days.get(n), "import": n == IMPORT_RELEASE,
              "layers": [{"layer": layer, "counts": dict(sorted(counts.items())), "total": sum(counts.values()),
                          "rollback": marks.get((n, layer))}
                         for layer, counts in sorted(layers[n].items())]} for n in numbers]
    return {"items": items, "total": total, "page": page, "pages": pages, "per_page": per_page}


def _current_names(session: Any, viewer: Viewer, keys: set[str]) -> dict[str, tuple[str, Optional[str]]]:
    """링크 끝 키 → (지금 이름, 화면 이름)(볼 수 있는 것만 — 한 질의)."""
    if not keys:
        return {}
    rows = session.execute(select(BrainObject.item_key, BrainObject.name,
                                  BrainObject.payload[PREF_LABEL].as_string()).where(
        BrainObject.item_key.in_(sorted(keys)), is_current(BrainObject), scope_clause(viewer, BrainObject.visibility)))
    return {key: (name, shown_name(label, name)) for key, name, label in rows}


def release_diff(session: Any, viewer: Viewer, number: int, *, limit: int = MAX_DIFF_ROWS) -> Optional[dict[str, Any]]:
    """한 판의 차이 요약 — 층마다 바뀐 것(볼 수 있는 것만 · 상한). 볼 수 있는 바뀜이 없으면 ``None``."""
    changes = visible_changes(viewer)
    counts = {layer or "": int(n) for layer, n in session.execute(
        select(changes.c.layer, func.count()).where(changes.c.release_no == int(number)).group_by(changes.c.layer))}
    if not counts:
        return None
    rows = session.execute(select(changes).where(changes.c.release_no == int(number))
                           .order_by(changes.c.layer, changes.c.op, changes.c.item_key, changes.c.change_id)
                           .limit(max(1, min(int(limit), MAX_DIFF_ROWS)))).all()
    names = _current_names(session, viewer, {r.item_key for r in rows if r.link_kind} | {
        r.link_to for r in rows if r.link_kind and r.link_to})
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        start, end = names.get(r.item_key, (None, None)), names.get(r.link_to or "", (None, None))
        by_layer.setdefault(r.layer or "", []).append({
            "op": r.op, "key": r.item_key, "name": r.name or start[0],
            "title": shown_name(r.label, r.name) if r.name else start[1], "type": r.item_type,
            "link_kind": r.link_kind, "link_to": r.link_to, "link_to_name": end[0], "link_to_title": end[1]})
    layers = [{"layer": layer, "total": total, "changes": by_layer.get(layer, []),
               "more": max(0, total - len(by_layer.get(layer, [])))} for layer, total in sorted(counts.items())]
    return {"number": int(number), "day": _days(session, [int(number)]).get(int(number)),
            "import": int(number) == IMPORT_RELEASE, "layers": layers}
