"""항목 카드(설계서 7.5 화면 3) — 이름 · 유형 · 상태 · 확신, 핵심 칸, 링크 종류 · 방향별 '관련(수)', 근거 · 만든 이 · 승인자,
바깥 정본 칩(``calc:`` · ``setting:`` — 있음 여부 · 지금 값은 **볼 수 있는 사람에게만**, :mod:`.external`), 사본 목록, 이력(판들),
빠진 링크(연결 개수 최소 — :mod:`.quality`).

- **알림**(7.8): 근거 종류가 빈 가격 규칙 · 번호가 빈 옮긴 결정(:func:`.schemas.empty_notices`) · 은퇴 항목을 가리키는 지금
  링크(:func:`.quality.retired_targets`)를 ``warnings`` 로 단다(막지 않는다).
- **유효 기간으로 읽기**(7.7 · D105): 끝 날이 지난 링크 · 끝 항목은 '관련'에서 빠진다. 키로 바로 연 항목 자신은 끝났어도
  보이고 ``ended`` 가 붙는다(화면이 '기간 끝남'으로 흐리게).

- 시작 항목을 볼 수 없거나 없으면 ``None``(둘을 가르지 않는다 — 화면 · API 404).
- 링크 끝 항목도 보는 사람의 범위로 **질의 단계에서** 거른다 — 볼 수 없는 끝은 목록에도 수에도 0(4절 · 12절).
- 링크는 방향마다 한 질의(끝 항목과 묶어 읽기 — 줄마다 다시 읽지 않는다), 사람 이름은 한 질의.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.orm import aliased

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain.conflicts import open_conflict_counts
from foms.services.brain.constants import CHANGE_OPEN, EXTERNAL_PREFIXES, LINK_KINDS, external_type
from foms.services.brain.external import ref_cards
from foms.services.brain.quality import item_rules, missing_links, retired_targets
from foms.services.brain.read import current_item, effect_state, item_history
from foms.services.brain.schemas import get as schema_get
from foms.services.brain.schemas import empty_notices, key_fields, payload_props
from foms.services.brain.scope import Viewer, scope_clause
from foms.services.brain.store import OBJECT_FIELDS, in_force, is_current
from foms.services.brain.usage import usage_by_reader
from foms.services.datetime_kst import format_datetime_kst
from models import User

MAX_LINKS_PER_GROUP = 30
MAX_EXTERNAL = 30
HISTORY_LIMIT = 20
IMPORT_ACTOR = "import"


def _link_query(viewer: Viewer, key: str, direction: str, today: datetime.date) -> Any:
    """한 방향 링크 + 끝 항목(지금 줄 · 볼 수 있는 것만) — (종류, 방향, 끝 키, 이름, 유형, 상태, 낡음 날, 링크 확신)."""
    other = aliased(BrainObject)
    near, far = (BrainLink.from_key, BrainLink.to_key) if direction == "out" else (BrainLink.to_key, BrainLink.from_key)
    return (select(BrainLink.kind.label("kind"), literal(direction).label("direction"), other.item_key.label("key"),
                   other.name.label("name"), other.item_type.label("type"), other.status.label("status"),
                   other.stale_after.label("stale_after"), BrainLink.confidence.label("confidence"))
            .join(other, and_(other.item_key == far, is_current(other)))
            .where(near == key, is_current(BrainLink), scope_clause(viewer, other.visibility),
                   in_force(BrainLink, today), in_force(other, today)))


def _ranked_links(session: Any, viewer: Viewer, key: str, today: datetime.date) -> list[Any]:
    """두 방향 링크를 (종류, 방향)마다 앞 :data:`MAX_LINKS_PER_GROUP` 개 + 그 묶음 전체 수로 읽는다(한 질의)."""
    both = union_all(_link_query(viewer, key, "out", today), _link_query(viewer, key, "in", today)).subquery("both")
    group = (both.c.kind, both.c.direction)
    rank = func.row_number().over(partition_by=group, order_by=(both.c.name, both.c.key)).label("rank")
    size = func.count().over(partition_by=group).label("size")
    ranked = select(both, rank, size).subquery("ranked")
    return session.execute(select(ranked).where(ranked.c.rank <= MAX_LINKS_PER_GROUP)
                           .order_by(ranked.c.kind, ranked.c.direction, ranked.c.rank)).all()


def link_groups(session: Any, viewer: Viewer, key: str, *, today: datetime.date) -> list[dict[str, Any]]:
    """링크 종류 · 방향별 묶음 ``[{"kind", "direction", "count", "items": [...]}]`` — 종류 차례대로."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _ranked_links(session, viewer, key, today):
        entry = groups.setdefault((row.kind, row.direction), {"kind": row.kind, "direction": row.direction,
                                                              "count": int(row.size), "items": []})
        entry["items"].append({"key": row.key, "name": row.name, "type": row.type, "status": row.status,
                               "stale": bool(row.stale_after and row.stale_after < today),
                               "confidence": row.confidence})
    order = {kind: i for i, kind in enumerate(LINK_KINDS)}
    return sorted(groups.values(), key=lambda g: (order.get(g["kind"], 99), g["direction"] != "out"))


def external_chips(session: Any, key: str, today: Optional[datetime.date] = None) -> list[dict[str, Any]]:
    """바깥 자리 칩 — 이 항목이 가리키는 계산기 id · 설정 키(+ 칸) · ERP 단계 · 사본 자리(키 · 사본 링크의 확인 날만 — 있음 ·
    값은 :func:`.external.ref_cards`. 사본 링크의 글 지문은 싣지 않는다)."""
    starts = [BrainLink.to_key.like(prefix + "%") for prefix in EXTERNAL_PREFIXES]
    live = [in_force(BrainLink, today)] if today is not None else []
    rows = session.execute(select(BrainLink.kind, BrainLink.to_key, BrainLink.payload)
                           .where(BrainLink.from_key == key, is_current(BrainLink), or_(*starts), *live)
                           .order_by(BrainLink.to_key).limit(MAX_EXTERNAL)).all()
    return [{"kind": kind, "ref": ref, "ext_type": external_type(ref),
             "checked_at": payload.get("checked_at") if isinstance(payload, dict) else None}
            for kind, ref, payload in rows]


def _user_ids(*values: Any) -> set[int]:
    """'user:<id>' 글 · 정수 id 에서 사람 번호만."""
    ids: set[int] = set()
    for value in values:
        if isinstance(value, int):
            ids.add(value)
        elif isinstance(value, str) and value.startswith("user:") and value[5:].isdigit():
            ids.add(int(value[5:]))
    return ids


def people_names(session: Any, ids: Iterable[int]) -> dict[int, str]:
    """사람 번호 → 이름(한 질의). 지운 계정은 빠진다(호출자가 '지운 계정'으로 보인다)."""
    wanted = sorted({int(i) for i in ids})
    if not wanted:
        return {}
    return {int(uid): name for uid, name in session.execute(select(User.id, User.name).where(User.id.in_(wanted)))}


def actor_label(created_by: Optional[str], names: dict[int, str]) -> str:
    """만든 이 글 → 화면 이름(사람 · 에이전트 · 옮김)."""
    value = created_by or ""
    if value == IMPORT_ACTOR:
        return "지식 문서에서 옮김"
    if value.startswith("agent:"):
        return "에이전트 " + value[6:]
    ids = _user_ids(value)
    if ids:
        return names.get(next(iter(ids)), "지운 계정")
    return value or "모름"


def approver_label(item: dict[str, Any], names: dict[int, str]) -> str:
    """사람 승인자 — 웹 승인 동작만 채운다(R10-18). 옮긴 확정 항목은 '옮김'(D102), 없으면 '승인 전'."""
    approver = item.get("human_approver_id")
    if approver is not None:
        return names.get(int(approver), "지운 계정")
    if item.get("created_by") == IMPORT_ACTOR:
        return "옮김(사장님이 이미 승인한 기준)"
    return "사람 승인 없음"


def _changed_fields(newer: dict[str, Any], older: Optional[dict[str, Any]]) -> list[str]:
    """두 판 사이에 바뀐 값 칸 이름(첫 판은 빈 목록)."""
    if older is None:
        return []
    return [name for name in OBJECT_FIELDS if newer.get(name) != older.get(name)]


def history_rows(session: Any, viewer: Viewer, key: str, names: dict[int, str]) -> list[dict[str, Any]]:
    """이력 탭 — 판마다(새 것부터) 시각 · 상태 · 만든 이 · 승인자 · 판 번호 · 바뀐 칸."""
    versions = item_history(session, viewer, key, limit=HISTORY_LIMIT)
    rows = []
    for index, item in enumerate(versions):
        older = versions[index + 1] if index + 1 < len(versions) else None
        rows.append({"version": item["version"], "name": item["name"], "status": item["status"],
                     "confidence": item["confidence"], "release_no": item["release_no"],
                     "recorded_at": _kst(item.get("recorded_at")), "superseded_at": _kst(item.get("superseded_at")),
                     "created_by": actor_label(item.get("created_by"), names),
                     "approver": approver_label(item, names), "changed": _changed_fields(item, older)})
    return rows


def _kst(value: Optional[str]) -> Optional[str]:
    """ISO UTC naive 글 → 한국 시각 'YYYY-MM-DD HH:MM'."""
    if not value:
        return None
    return format_datetime_kst(datetime.datetime.fromisoformat(value), "%Y-%m-%d %H:%M")


def open_change_count(session: Any, key: str) -> int:
    """이 항목에 걸린 열린 제안 수('확인 필요' 표시)."""
    return int(session.execute(select(func.count()).select_from(BrainChange).where(
        BrainChange.item_key == key, BrainChange.status == CHANGE_OPEN)).scalar_one())


def item_card(session: Any, viewer: Viewer, key: str, *, today: datetime.date) -> Optional[dict[str, Any]]:
    """카드 한 덩어리 — 볼 수 없거나 없으면 ``None``."""
    item = current_item(session, viewer, key, today)
    if item is None:
        return None
    versions = item_history(session, viewer, key, limit=HISTORY_LIMIT)
    names = people_names(session, _user_ids(*(v.get("created_by") for v in versions),
                                            *(v.get("human_approver_id") for v in versions)))
    stale_after = item.get("stale_after")
    keys = key_fields(item, item["type"])  # 유형 속성 틀의 '눈에 띄는 칸'(7.7 · D104)
    payload_values = {p.path: schema_get(item, p.path) for p in payload_props(item["type"])}
    gaps = missing_links(session, viewer, item, today=today)  # 가격 규칙은 근거 종류로 갈린다(실음 칸을 빼기 전에)
    rules = item_rules(item["type"], item.get("payload"))
    warnings = empty_notices(item, item["type"]) + [
        {"code": "retired_target:" + t["key"], "text": f"은퇴 항목을 가리킴 — {t['name']}", "key": t["key"]}
        for t in retired_targets(session, viewer, key, today=today)]
    item.pop("payload", None)  # 실음 칸 통째(지식 문서 꼴 · 내부 값)는 싣지 않는다 — 틀 칸만 위 두 묶음으로
    open_changes = open_change_count(session, key)
    conflicts = open_conflict_counts(session, [key], today).get(key, 0)  # 이 항목에 대한 열린 엇갈림(점검 지금 8)
    readers = usage_by_reader(session, key)  # 쓰인 횟수 — 판 줄 칸 + 따로 센 수(챗봇 · 상담 두뇌 — D105)
    return {
        "item": {**item, "stale": bool(stale_after and datetime.date.fromisoformat(stale_after) < today),
                 "needs_check": open_changes > 0 or conflicts > 0, "open_changes": open_changes,
                 "usage_count": int(item.get("usage_count") or 0) + sum(readers.values()), "usage_readers": readers,
                 "recorded_at": _kst(item.get("recorded_at"))},
        "created_by": actor_label(item.get("created_by"), names),
        "approver": approver_label(item, names), "key_fields": keys, "payload_values": payload_values,
        "links": link_groups(session, viewer, key, today=today),
        "external": ref_cards(session, viewer, external_chips(session, key, today), layer=item["layer"]),
        "missing_links": gaps, "link_rules": rules, "warnings": warnings,
        "copies": list(item.get("copies") or []),
        "history": history_rows(session, viewer, key, names),
        "effect": effect_state(session, item, today), "open_conflicts": conflicts,
    }
