"""제안함 '내 승인 대기'(설계서 7.5 화면 4 · 승인 흐름 · 사장님 D101 · D103) — 읽기만. 결정은 :mod:`.decide`.

**질의 단계에서 두 번 거른다**: ① 이 사람이 결정할 수 있는 제안만(:func:`.access.approver_layers` — 층 승인자 MANAGER 는 자기
층 · 사장님 몫 유형 빼고, ADMIN 은 모두) ② 보기 범위 안의 제안만(항목 동작은 지금 줄과 새 보기 범위 둘 다, 링크는 양 끝 — 4절 ·
12절, 모아 센 수 포함). 볼 수 없는 제안은 카드에도 수에도 0 이다.

- **항목당 카드 하나**: 같은 항목(링크는 같은 링크)에 열린 제안이 둘 이상이면 처음 것이 카드, 나머지는 같은 카드에 붙는다.
- **AI 제안**: **층마다**(사장님 D106 — 공통 · 상담 · 도면 · 생산) 이번 주 남은 자리(:data:`AI_WEEKLY_CAP` − 이번 주 그 층에서
  결정한 AI 제안 수)만큼, 그 항목이 **쓰인 횟수 순**으로 보인다(쓰인 횟수 = 판 줄 칸 + 따로 센 수 — :mod:`.usage`). 승인자는 자기
  층 묶음만, ADMIN 은 모든 층 묶음을 본다.
  만든 뒤 4주가 지난 AI 제안은 보이지 않고 :func:`.decide.expire_ai_proposals` 가 '기간 끝남'으로 닫는다.
- 카드: 한 줄 요약 재료 · 칸별 전 → 후 · 사람 까닭과 사진 먼저 · AI 일반화 다음 · 근거 서랍(근거 id 만 — 가린 글 자리) ·
  비슷한 사례 수와 날짜 · 함께 닿는 항목 · 관문 결과 · 기준 판 바뀜 경고 · 유형별 '승인의 뜻' · 등급 B 확인 값 · 휴대폰 가능.
  카드마다 따로 읽지 않는다(사례 · 이웃 · 링크 판 · 사람 이름은 묶음 질의 하나씩).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import and_, case, false, func, literal, not_, or_, select, true, union_all
from sqlalchemy.orm import aliased

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain.access import approval_problem, approver_layers
from foms.services.brain.card import actor_label, people_names
from foms.services.brain.constants import (
    AI_WEEKLY_CAP, CHANGE_APPLIED, CHANGE_OPEN, CHANGE_REJECTED, EXTERNAL_PREFIXES, GRADE_A, GRADE_B,
    HUMAN_EDIT_FIELDS, LAYERS, LINK_OPS, OBJECT_OPS, OP_CREATE, OP_UPDATE, OWNER_ONLY_TYPES, external_type,
)
from foms.services.brain.display import GATE_LABELS, approval_meaning, visibility_label
from foms.services.brain.external import ref_cards
from foms.services.brain.inbox_bins import bulk_ok_any_grade, card_bin, ref_label
from foms.services.brain.review_rules import AGENT_PREFIX, ai_cutoff, confirm_value, is_agent, phone_ok, week_start
from foms.services.brain.schemas import diff_rows, edit_prop, edit_props
from foms.services.brain.scope import Viewer, allowed_scopes
from foms.services.brain.store import LINK_FIELDS, OBJECT_FIELDS, current_object, is_current
from foms.services.brain.usage import usage_of, usage_total
from foms.services.datetime_kst import format_datetime_kst

MAX_CHANGES = 200
OCCURRED_AT = "occurred_at"  # 관찰 틀 원본 시각 칸(7.8 다음 13)
TOUCH_PER_CARD = 6
PHOTO_PREFIX = "photo:"


# ── 거르기 조건 ──────────────────────────────────────────────────────────
def agent_clause() -> Any:
    """에이전트 제안 조건."""
    return BrainChange.proposed_by.like(AGENT_PREFIX + "%")


def decidable_clause(viewer: Viewer) -> Any:
    """이 사람이 결정할 수 있는 제안(질의 조건 — :func:`.access.approval_problem` 과 같은 규칙)."""
    layers = approver_layers(viewer)
    if layers is None:
        return true()
    if not layers:
        return false()
    owner_end = select(BrainObject.id).where(BrainObject.item_key == BrainChange.link_to, is_current(BrainObject),
                                             BrainObject.item_type.in_(sorted(OWNER_ONLY_TYPES))).exists()
    return and_(BrainChange.layer.in_(layers), BrainChange.item_type.notin_(sorted(OWNER_ONLY_TYPES)), not_(owner_end))


def visible_clause(viewer: Viewer, cur: Any) -> Any:
    """보기 범위 안의 제안 — 항목 동작은 지금 줄 · 새 보기 범위 둘 다(만들기는 새 범위), 링크는 양 끝(바깥 정본은 늘 보임)."""
    scopes = allowed_scopes(viewer)
    if scopes is None:
        return true()
    if not scopes:
        return false()
    wanted = sorted(scopes)
    after = BrainChange.fields[("visibility", "after")].as_string()
    create = and_(BrainChange.op == OP_CREATE, after.in_(wanted), or_(cur.id.is_(None), cur.visibility.in_(wanted)))
    other = and_(BrainChange.op != OP_CREATE, cur.visibility.in_(wanted), or_(after.is_(None), after.in_(wanted)))
    seen = select(BrainObject.item_key).where(is_current(BrainObject), BrainObject.visibility.in_(wanted))
    outside = [BrainChange.link_to.like(prefix + "%") for prefix in EXTERNAL_PREFIXES]
    link = and_(BrainChange.op.in_(LINK_OPS), BrainChange.link_from.in_(seen), or_(*outside, BrainChange.link_to.in_(seen)))
    return or_(and_(BrainChange.op.in_(OBJECT_OPS), or_(create, other)), link)


def current_join(cur: Any) -> Any:
    """제안 → 그 항목(링크면 시작 항목)의 지금 줄."""
    return and_(cur.item_key == BrainChange.item_key, is_current(cur))


# ── AI 주 상한(층마다 — D106) ────────────────────────────────────────────
def _used_by_layer(session: Any, now: datetime.datetime) -> dict[str, int]:
    """이번 주 층마다 결정한 AI 제안 수."""
    rows = session.execute(select(BrainChange.layer, func.count()).where(
        agent_clause(), BrainChange.status.in_((CHANGE_APPLIED, CHANGE_REJECTED)),
        BrainChange.decided_at >= week_start(now)).group_by(BrainChange.layer)).all()
    return {layer: int(n) for layer, n in rows if layer}


def ai_week(session: Any, now: datetime.datetime, viewer: Optional[Viewer] = None) -> dict[str, Any]:
    """이번 주 AI 자리 — ``{"cap", "used", "left", "per_layer", "layers": {층: {"used", "left"}}}``.

    층마다 :data:`AI_WEEKLY_CAP` 자리다(D106). ``viewer`` 를 주면 그 사람이 결정하는 층만 더한다(층 승인자 MANAGER 는 자기 층
    하나 — 자리 20, ADMIN 은 모든 층), 안 주면 모든 층."""
    used = _used_by_layer(session, now)
    mine = approver_layers(viewer) if viewer is not None else None
    layers = tuple(LAYERS) if mine is None else tuple(layer for layer in LAYERS if layer in mine)
    per = {layer: {"used": used.get(layer, 0), "left": max(0, AI_WEEKLY_CAP - used.get(layer, 0))} for layer in layers}
    return {"cap": AI_WEEKLY_CAP * len(layers), "used": sum(v["used"] for v in per.values()),
            "left": sum(v["left"] for v in per.values()), "per_layer": AI_WEEKLY_CAP, "layers": per}


def shown_ai_ids(session: Any, now: datetime.datetime) -> list[int]:
    """제안함에 보일 AI 제안 id — 층마다 남은 자리만큼, 쓰인 횟수 많은 순(그다음 오래된 순). 4주 지난 것은 빼고."""
    week = ai_week(session, now)
    shown: list[int] = []
    cur = aliased(BrainObject)
    for layer, slot in week["layers"].items():
        if not slot["left"]:
            continue
        query = (select(BrainChange.id).outerjoin(cur, current_join(cur))
                 .where(BrainChange.status == CHANGE_OPEN, agent_clause(), BrainChange.layer == layer,
                        BrainChange.created_at >= ai_cutoff(now))
                 .order_by(usage_total(cur).desc(), BrainChange.created_at, BrainChange.id).limit(slot["left"]))
        shown.extend(int(i) for i in session.execute(query).scalars())
    return shown


def _in_box(session: Any, now: datetime.datetime) -> Any:
    """제안함에 드는 제안 — 사람 제안 전부 + 보일 AI 제안."""
    shown = shown_ai_ids(session, now)
    return or_(not_(agent_clause()), BrainChange.id.in_(shown) if shown else false())


def open_rows(session: Any, viewer: Viewer, now: datetime.datetime) -> list[tuple[BrainChange, Optional[BrainObject]]]:
    """이 사람의 열린 제안(+ 그 항목 지금 줄) — 결정 가능 · 보기 범위 · AI 자리로 거른 것, 오래된 순."""
    cur = aliased(BrainObject)
    rows = session.execute(
        select(BrainChange, cur).outerjoin(cur, current_join(cur))
        .where(BrainChange.status == CHANGE_OPEN, decidable_clause(viewer), visible_clause(viewer, cur),
               _in_box(session, now))
        .order_by(BrainChange.created_at, BrainChange.id).limit(MAX_CHANGES)).all()
    return [(change, row) for change, row in rows
            if approval_problem(viewer, op=change.op, layer=change.layer, types=[change.item_type]) is None]


def inbox_counts(session: Any, viewer: Viewer, now: datetime.datetime) -> dict[str, int]:
    """제안함 수(보기 범위 · 결정 가능으로 거른 것) — ``{"open", "cards", "ai_waiting"}``. 알림 수 API 가 쓴다."""
    cur = aliased(BrainObject)
    base = (select(BrainChange.id, BrainChange.item_key, BrainChange.link_kind, BrainChange.link_to, agent_clause().label("ai"))
            .outerjoin(cur, current_join(cur))
            .where(BrainChange.status == CHANGE_OPEN, decidable_clause(viewer), visible_clause(viewer, cur)))
    shown = set(shown_ai_ids(session, now))
    rows = [r for r in session.execute(base.where(or_(not_(agent_clause()), BrainChange.created_at >= ai_cutoff(now))))]
    boxed = [r for r in rows if not r.ai or r.id in shown]
    return {"open": len(boxed), "cards": len({(r.item_key, r.link_kind, r.link_to) for r in boxed}),
            "ai_waiting": len([r for r in rows if r.ai and r.id not in shown])}


# ── 카드 재료(묶음 질의) ─────────────────────────────────────────────────
def similar_cases(session: Any, viewer: Viewer, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    """항목 → 근거 관찰(사례 · 그림 읽기 · 사진 관찰 — ``evidence_of``) 수와 처음 · 마지막 날(볼 수 있는 것만).

    날은 **원본 시각**(관찰 틀 ``payload.occurred_at`` — 7.8 다음 13)이 있으면 그 날, 없으면 줄 쓴 때(``recorded_at``)의 한국
    날짜다(옮겨 쓴 관찰이 다 같은 날로 보이지 않게)."""
    wanted = sorted(set(keys))
    if not wanted:
        return {}
    obs = aliased(BrainObject)
    scopes = allowed_scopes(viewer)
    occurred = obs.payload[OCCURRED_AT].as_string()
    recorded = case((occurred.is_(None), obs.recorded_at))  # 원본 시각이 없는 줄만 줄 쓴 때로
    query = (select(BrainLink.to_key, func.count(), func.min(recorded), func.max(recorded), func.min(occurred),
                    func.max(occurred))
             .join(obs, and_(obs.item_key == BrainLink.from_key, is_current(obs)))
             .where(BrainLink.kind == "evidence_of", is_current(BrainLink), BrainLink.to_key.in_(wanted))
             .group_by(BrainLink.to_key))
    if scopes is not None:
        query = query.where(obs.visibility.in_(sorted(scopes)) if scopes else false())
    out = {}
    for key, n, first, last, first_seen, last_seen in session.execute(query):
        days = [d for d in (_day(_moment(first)), _day(_moment(last)), _seen_day(first_seen), _seen_day(last_seen)) if d]
        out[key] = {"count": int(n), "first": min(days) if days else None, "last": max(days) if days else None}
    return out


def _moment(value: Any) -> Optional[datetime.datetime]:
    """집계 값 → 시각(SQLite 는 글로 돌려준다)."""
    if isinstance(value, str):
        return datetime.datetime.fromisoformat(value)
    return value


def _seen_day(value: Any) -> Optional[str]:
    """원본 시각 글 → 한국 날짜 글(시간대가 없으면 적힌 날 그대로 · 못 읽으면 ``None``)."""
    try:
        moment = datetime.datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        return moment.date().isoformat()
    return _day(moment.astimezone(datetime.timezone.utc).replace(tzinfo=None))


def _touch_query(viewer: Viewer, keys: list[str], direction: str) -> Any:
    """한 방향 링크 + 끝 항목(볼 수 있는 지금 줄만)."""
    other = aliased(BrainObject)
    near, far = (BrainLink.from_key, BrainLink.to_key) if direction == "out" else (BrainLink.to_key, BrainLink.from_key)
    scopes = allowed_scopes(viewer)
    query = (select(near.label("near"), BrainLink.kind.label("kind"), literal(direction).label("direction"),
                    other.item_key.label("key"), other.name.label("name"), other.item_type.label("type"))
             .join(other, and_(other.item_key == far, is_current(other)))
             .where(near.in_(keys), is_current(BrainLink)))
    if scopes is not None:
        query = query.where(other.visibility.in_(sorted(scopes)) if scopes else false())
    return query


def touched_items(session: Any, viewer: Viewer, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    """항목 → 함께 닿는 항목(링크 양쪽 · 볼 수 있는 것) 수와 앞 :data:`TOUCH_PER_CARD` 개(한 질의 — 창 함수)."""
    wanted = sorted(set(keys))
    if not wanted:
        return {}
    both = union_all(_touch_query(viewer, wanted, "out"), _touch_query(viewer, wanted, "in")).subquery("both")
    rank = func.row_number().over(partition_by=both.c.near, order_by=(both.c.kind, both.c.name, both.c.key))
    size = func.count().over(partition_by=both.c.near)
    ranked = select(both, rank.label("rank"), size.label("size")).subquery("ranked")
    out: dict[str, dict[str, Any]] = {}
    for row in session.execute(select(ranked).where(ranked.c.rank <= TOUCH_PER_CARD)
                               .order_by(ranked.c.near, ranked.c.rank)):
        entry = out.setdefault(row.near, {"total": int(row.size), "items": []})
        entry["items"].append({"kind": row.kind, "direction": row.direction, "key": row.key, "name": row.name,
                               "type": row.type})
    return out


def link_versions(session: Any, changes: Iterable[BrainChange]) -> dict[tuple[str, str, str], int]:
    """링크 제안들의 지금 링크 판(한 질의)."""
    idents = {(c.link_kind, c.link_from, c.link_to) for c in changes if c.op in LINK_OPS}
    if not idents:
        return {}
    froms = sorted({f for _k, f, _t in idents})
    rows = session.execute(select(BrainLink.kind, BrainLink.from_key, BrainLink.to_key, BrainLink.version).where(
        BrainLink.from_key.in_(froms), is_current(BrainLink)))
    return {(k, f, t): int(v) for k, f, t, v in rows if (k, f, t) in idents}


# ── 카드 ─────────────────────────────────────────────────────────────────
def _day(value: Optional[datetime.datetime]) -> Optional[str]:
    """UTC naive 시각 → 한국 날짜 글."""
    return format_datetime_kst(value, "%Y-%m-%d") if value else None


def _diff(change: BrainChange) -> list[dict[str, Any]]:
    """칸별 전 → 후(정한 칸 차례 · 실음 칸은 유형 속성 틀 칸마다 펼침 — 7.7). 고쳐 넣기로 바뀐 칸은 처음 제안 값(``proposed``)도.
    줄마다 이름 · 단위 · 고쳐 넣을 수 있나 · 자료형 · 고른 값(화면 입력 칸을 틀에서 만든다)."""
    order = OBJECT_FIELDS if change.op in OBJECT_OPS else LINK_FIELDS
    fields = change.fields or {}
    ordered = {name: fields[name] for name in [n for n in order if n in fields] + sorted(n for n in fields
                                                                                       if n not in order)}
    editable_op = change.op in (OP_CREATE, OP_UPDATE)
    editable = set(HUMAN_EDIT_FIELDS) | {p.path for p in edit_props(change.item_type)}
    rows = []
    for row in diff_rows(change.item_type, ordered):
        prop = edit_prop(change.item_type, row["field"])
        row.update(editable=editable_op and row["field"] in editable,
                   datatype=prop.datatype if prop else ("date" if row["field"] in ("valid_from", "valid_to") else "text"),
                   choices=list(prop.choices) if prop else [])
        rows.append(row)
    return rows


def _base_changed(change: BrainChange, cur: Optional[BrainObject], links: dict[tuple[str, str, str], int]) -> dict:
    """기준 판 비교 — ``{"changed", "current"}``(만들기는 지금 줄이 생겼으면 바뀜)."""
    if change.op in LINK_OPS:
        current = links.get((change.link_kind, change.link_from, change.link_to))
    else:
        current = cur.version if cur is not None else None
    flagged = change.base_changed_at is not None
    stamp = format_datetime_kst(change.base_changed_at, "%Y-%m-%d %H:%M") if flagged else None
    if change.op == OP_CREATE:
        return {"changed": cur is not None or flagged, "current": current, "flagged_at": stamp}
    return {"changed": current != change.base_version or flagged, "current": current, "flagged_at": stamp}


CALC_REF, ABOUT_REF = "calc:", "about:"


def _sentence(change: BrainChange, cur: Optional[BrainObject]) -> str:
    """② 문장 카드의 'AI와 직원이 이렇게 알게 돼요' 글 — 제안의 새 글, 글을 안 바꾸면 지금 글(링크는 빈 글)."""
    after = ((change.fields or {}).get("text") or {}).get("after")
    if isinstance(after, str) and after.strip():
        return after.strip()
    return (cur.text or "").strip() if cur is not None and change.op not in LINK_OPS else ""


def _visible_to(change: BrainChange, cur: Optional[BrainObject]) -> Optional[str]:
    """볼 수 있는 사람(제안의 새 보기 범위, 없으면 지금 범위)."""
    value = ((change.fields or {}).get("visibility") or {}).get("after") or (cur.visibility if cur is not None else None)
    return visibility_label(value) if isinstance(value, str) else None


def price_cards(session: Any, viewer: Viewer, changes: Iterable[BrainChange]) -> dict[str, dict[str, Any]]:
    """제안 근거에 실린 계산기 자리 → 이름 · 지금 값(볼 수 있는 사람만 — :func:`.external.ref_cards`). 한 번에 읽는다."""
    refs = sorted({e for c in changes for e in (c.evidence or []) if isinstance(e, str) and e.startswith(CALC_REF)})
    if not refs:
        return {}
    chips = [{"ref": r, "kind": "value_from", "ext_type": external_type(r)} for r in refs]
    return {card["ref"]: card for card in ref_cards(session, viewer, chips)}


def about_items(session: Any, viewer: Viewer, changes: Iterable[BrainChange]) -> dict[str, dict[str, Any]]:
    """엇갈림 · 질문 제안 근거의 다루는 항목(``about:<키>``) → 이름 · 지금 글 · 판(볼 수 있는 것만 — ③ 질문 카드)."""
    keys = sorted({e[len(ABOUT_REF):] for c in changes for e in (c.evidence or [])
                   if isinstance(e, str) and e.startswith(ABOUT_REF)})
    scopes = allowed_scopes(viewer)
    out = {}
    for key in keys:
        row = current_object(session, key)
        if row is not None and (scopes is None or row.visibility in scopes):
            out[key] = {"key": key, "title": card_title_of(row), "text": row.text or "", "version": row.version}
    return out


def change_view(change: BrainChange, cur: Optional[BrainObject], names: dict[int, str],
                links: dict[tuple[str, str, str], int], admin: bool = False,
                prices: Optional[dict[str, dict[str, Any]]] = None,
                about: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """제안 하나의 화면 재료(글은 제안 · 항목에 있는 것만 — 가린 글 · 근거 id)."""
    field, value = confirm_value(change.op, change.fields, change.item_type)
    evidence = [str(e) for e in (change.evidence or [])]
    gates = change.gates or {}
    return {
        "id": change.id, "op": change.op, "grade": change.grade, "ai": is_agent(change.proposed_by),
        "action": change.action,
        "proposer": actor_label(change.proposed_by, names), "reason": change.reason or "",
        "photos": [e for e in evidence if e.startswith(PHOTO_PREFIX)],
        "evidence": [e for e in evidence if not e.startswith(PHOTO_PREFIX)],
        "fields": _diff(change), "base_version": change.base_version, "base": _base_changed(change, cur, links),
        "gates": [{"name": n, "value": gates[n]} for n in GATE_LABELS if n in gates],
        "meaning": approval_meaning(change.op, change.item_type,
                                    card_bin(change.op, change.item_type, change.fields, change.link_kind)),
        "confirm": ({"field": field, "value": value} if change.grade == GRADE_B and not (
            admin and bulk_ok_any_grade(change.op, change.item_type, change.fields, change.link_kind)) else None),
        "phone_ok": phone_ok(change.op, change.fields),
        "bulk_ok": change.grade == GRADE_A or (admin and bulk_ok_any_grade(change.op, change.item_type, change.fields,
                                                                            change.link_kind)),
        "rollback_of": change.rollback_of_version, "link": ({"kind": change.link_kind, "from": change.link_from,
                                                            "to": change.link_to, "to_label": ref_label(change.link_to)}
                                                           if change.op in LINK_OPS else None),
        "created_at": format_datetime_kst(change.created_at, "%Y-%m-%d %H:%M") if change.created_at else None,
        "sentence": _sentence(change, cur), "visible_to": _visible_to(change, cur),
        "prices": [{"label": p["label"], "value": p["value"], "hidden": p["value_hidden"], "exists": p["exists"]}
                   for p in ((prices or {}).get(e) for e in evidence) if p is not None],
        "about": [a for a in ((about or {}).get(e[len(ABOUT_REF):]) for e in evidence if e.startswith(ABOUT_REF))
                  if a is not None],
    }


def _group_key(change: BrainChange) -> tuple:
    """카드 묶음 — 항목 동작은 항목 키, 링크는 링크 정체."""
    if change.op in LINK_OPS:
        return ("link", change.link_kind, change.link_from, change.link_to)
    return ("item", change.item_key)


def card_title_of(row: BrainObject) -> str:
    """지금 항목의 한글 대표 이름(없으면 이름)."""
    label = (row.payload or {}).get("pref_label") if isinstance(row.payload, dict) else None
    return label.strip() if isinstance(label, str) and label.strip() else row.name


def card_title(change: BrainChange, cur: Optional[BrainObject], name: str) -> str:
    """카드 제목 — 한글 대표 이름(제안의 '후' → 지금 항목 순), 없으면 이름(설계서 7.9 — 영어 키 제목을 앞에 두지 않는다)."""
    after = ((change.fields or {}).get("payload") or {}).get("after")
    for payload in (after, cur.payload if cur is not None else None):
        label = payload.get("pref_label") if isinstance(payload, dict) else None
        if isinstance(label, str) and label.strip():
            return label.strip()
    return name


def _card(group: list[tuple[BrainChange, Optional[BrainObject]]], extra: dict[str, Any]) -> dict[str, Any]:
    """묶음 → 카드(처음 사람 제안, 없으면 처음 제안이 카드 · 나머지는 붙음)."""
    main_index = next((i for i, (c, _r) in enumerate(group) if not is_agent(c.proposed_by)), 0)
    change, cur = group[main_index]
    views = [change_view(c, r, extra["names"], extra["links"], extra["admin"], extra["prices"], extra["about"])
             for c, r in group]
    after_name = ((change.fields or {}).get("name") or {}).get("after")
    key = change.item_key or ""
    name = cur.name if cur is not None else (after_name or key)
    return {
        "id": change.id, "key": key, "name": name, "title": card_title(change, cur, name),
        "bin": card_bin(change.op, change.item_type, change.fields, change.link_kind),
        "type": change.item_type, "layer": change.layer, "brand": change.brand,
        "usage_count": (int(cur.usage_count or 0) + extra["usage"].get(key, 0)) if cur is not None else 0,
        "version": cur.version if cur is not None else None, "exists": cur is not None,
        "copies": len(cur.copies or []) if cur is not None else 0,
        "main": views[main_index], "attached": [v for i, v in enumerate(views) if i != main_index],
        "similar": extra["similar"].get(key, {"count": 0, "first": None, "last": None}),
        "touches": extra["touches"].get(key, {"total": 0, "items": []}),
    }


def _card_order(card: dict[str, Any]) -> tuple:
    """사람 제안 카드 먼저(오래된 순), 그다음 AI 카드(쓰인 횟수 순)."""
    ai = card["main"]["ai"]
    return (ai, -card["usage_count"] if ai else 0, card["main"]["created_at"] or "", card["id"])


def inbox(session: Any, viewer: Viewer, *, now: datetime.datetime) -> dict[str, Any]:
    """제안함 — ``{"cards", "counts", "ai"}``. 카드는 항목(링크)마다 하나."""
    rows = open_rows(session, viewer, now)
    groups: dict[tuple, list[tuple[BrainChange, Optional[BrainObject]]]] = {}
    for change, cur in rows:
        groups.setdefault(_group_key(change), []).append((change, cur))
    item_keys = [g[0][0].item_key for k, g in groups.items() if k[0] == "item"]
    people = {int(c.proposed_by[5:]) for c, _r in rows if (c.proposed_by or "").startswith("user:")
              and c.proposed_by[5:].isdigit()}
    extra = {"names": people_names(session, people), "links": link_versions(session, [c for c, _r in rows]),
             "similar": similar_cases(session, viewer, item_keys), "touches": touched_items(session, viewer, item_keys),
             "usage": usage_of(session, item_keys), "admin": viewer.is_admin,
             "prices": price_cards(session, viewer, [c for c, _r in rows]),
             "about": about_items(session, viewer, [c for c, _r in rows])}
    cards = sorted((_card(group, extra) for group in groups.values()), key=_card_order)
    return {"cards": cards, "counts": inbox_counts(session, viewer, now), "ai": ai_week(session, now, viewer)}
