"""단계 2 '물건 찾아 따라가기' — 손님 글에서 제품 라인 · 옵션을 이름표로 찾고, 그 물건에 걸린 규칙을 따라간다(DB 읽기만).

설계서 2026-11-12 온톨로지 5절 · 5.0(사장님 D196 — 처음 끔). 관리 칸 '물건 찾아 따라가기'(:data:`.onto_settings.ONTO_GRAPH_FIELD`)
가 켜진 차례만 :mod:`.drafting_pass` 가 부른다. 묶음 글은 :mod:`.onto_block`.

- **찾기**: 지금 판 · 반영(active) · 유효 기간 안 · 보기 범위 '모두' · 라홈과 공통인 제품 라인 · 옵션의 이름 · 대표 이름 · 다른 이름을
  손님 원문(띄어쓰기 · 대소문자 무시 — :func:`foms.services.brain.labels.norm`)에서 찾는다. **긴 이름표 먼저, 겹치면 긴 쪽만**
  (예: '외부3단서랍'이 맞으면 그 안의 '서랍' 은 다른 항목으로 치지 않는다). 물건 상한 :data:`MAX_ITEMS`. 원문은 이 바퀴
  메모리에서만 쓰고 남기지 않는다(두뇌는 묶음만 받는다 — 묶음엔 맞은 이름표 대신 대표 이름).
- **옵션은 제품에 매여 있지 않다**(4.1 — 계산기 제품마다 붙은 옵션 0) — 제품 → 옵션 따라가기는 없다. 물건마다 들어오는
  ``applies_to`` 링크의 규칙(정책 · 가격 규칙 · 규격 — 같은 판 · 반영 · 기간 · 범위 조건)만, 물건당 :data:`MAX_RULES`(쓰인 횟수 순).
- 주문이 확인된 차례(5.6)는 그 주문 품목 이름도 찾기 재료다(손님이 제품 이름을 안 써도 그 제품 규칙이 걸린다).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from sqlalchemy import select

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.constants import BRAND_COMMON, SCOPE_ALL, STATUS_ACTIVE
from foms.services.brain.labels import MIN_LABEL, aliases_of, norm, pref_of
from foms.services.brain.store import in_force, is_current

__all__ = ["ITEM_TYPES", "MAX_ITEMS", "MAX_RULES", "OntoHit", "RULE_TYPES", "find_items", "hits_for", "matches",
           "visible"]

ITEM_TYPES: tuple[str, ...] = ("product_line", "option")
RULE_TYPES: tuple[str, ...] = ("policy", "price_rule", "spec")
MAX_ITEMS, MAX_RULES = 8, 6


@dataclass(frozen=True)
class OntoRule:
    """물건에 걸린 규칙 하나 — 지식 문서 id(있으면) · 유형 · 대표 이름."""

    key: str
    doc_id: str
    item_type: str
    name: str


@dataclass(frozen=True)
class OntoHit:
    """찾은 물건 하나 — 키 · 유형 · 대표 이름 · 실음 칸(속성) · 걸린 규칙 · 뜻으로 찾았나(:mod:`.onto_meaning`)."""

    key: str
    item_type: str
    name: str
    payload: dict
    rules: tuple[OntoRule, ...] = ()
    by_meaning: bool = False


def visible(model: Any, brand: str, day: datetime.date) -> tuple[Any, ...]:
    """상담 에이전트가 보는 줄 — 지금 판 · 반영 · 보기 범위 모두 · 그 브랜드와 공통 · 유효 기간 안."""
    return (is_current(model), model.status == STATUS_ACTIVE, model.visibility == SCOPE_ALL,
            model.brand.in_((brand, BRAND_COMMON)), in_force(model, day))


def _labels(name: str, payload: Any) -> list[str]:
    """그 물건을 부르는 이름표(이름 · 대표 이름 · 다른 이름 — 숨은 이름 포함, 두 글자 이상)."""
    return [label for label in dict.fromkeys([name, pref_of(name, payload), *aliases_of(payload)])
            if len(norm(label)) >= MIN_LABEL]


def _ascii_alnum(ch: str) -> bool:
    """영문 · 숫자 한 글자인가(빈 글은 아님)."""
    return bool(ch) and ch.isascii() and ch.isalnum()


def _cut_inside(body: str, start: int, end: int) -> bool:
    """이름표 끝이 영문 · 숫자인데 바로 옆도 영문 · 숫자면 더 긴 낱말 안이다('타입1' 은 '타입10' 안에서 맞지 않는다)."""
    return ((_ascii_alnum(body[start]) and start > 0 and _ascii_alnum(body[start - 1]))
            or (_ascii_alnum(body[end - 1]) and _ascii_alnum(body[end:end + 1])))


def matches(rows: Iterable[tuple[str, str, Any]], texts: Sequence[str]) -> list[str]:
    """(키, 이름, 실음 칸) 줄 · 원문 → 맞은 키(긴 이름표 먼저 · 겹치면 긴 쪽 · 영문 · 숫자 경계 · 처음 맞은 순 · 상한
    :data:`MAX_ITEMS`)."""
    body = norm(" ".join(texts))
    found: list[tuple[int, int, int, str]] = []  # (-길이, 시작, 끝, 키)
    for key, name, payload in rows:
        for label in _labels(name, payload):
            needle, start = norm(label), body.find(norm(label))
            while start >= 0:
                if not _cut_inside(body, start, start + len(needle)):
                    found.append((-len(needle), start, start + len(needle), key))
                start = body.find(needle, start + 1)
    taken: list[tuple[int, int]] = []
    picked: dict[str, int] = {}
    for _neg, start, end, key in sorted(found):
        if any(start < b and a < end for a, b in taken):
            continue
        taken.append((start, end))
        picked.setdefault(key, start)
    return sorted(picked, key=picked.get)[:MAX_ITEMS]


def _rules(session: Any, keys: Sequence[str], brand: str, day: datetime.date) -> dict[str, list[OntoRule]]:
    """물건 키마다 들어오는 ``applies_to`` 규칙(쓰인 횟수 많은 순 · 물건당 :data:`MAX_RULES`)."""
    rows = session.execute(
        select(BrainLink.to_key, BrainObject.item_key, BrainObject.item_type, BrainObject.name, BrainObject.payload)
        .join(BrainObject, BrainObject.item_key == BrainLink.from_key)
        .where(is_current(BrainLink), BrainLink.kind == "applies_to", BrainLink.to_key.in_(list(keys)),
               BrainObject.item_type.in_(RULE_TYPES), *visible(BrainObject, brand, day))
        .order_by(BrainObject.usage_count.desc(), BrainObject.item_key)).all()
    out: dict[str, list[OntoRule]] = {key: [] for key in keys}
    for to_key, key, item_type, name, payload in rows:
        doc_id = str((payload or {}).get("doc_id") or "") if isinstance(payload, dict) else ""
        if len(out[to_key]) < MAX_RULES:
            out[to_key].append(OntoRule(key, doc_id, item_type, name))
    return out


def find_items(session: Any, texts: Sequence[str], *, brand: str, day: datetime.date,
               extra: Iterable[str] = ()) -> list[OntoHit]:
    """손님 원문(+ 확인된 주문 품목 이름) → 찾은 물건과 걸린 규칙. 없으면 빈 목록."""
    words = [*texts, *extra]
    if not any(word.strip() for word in words):
        return []
    rows = session.execute(select(BrainObject.item_key, BrainObject.name, BrainObject.payload, BrainObject.item_type)
                           .where(BrainObject.item_type.in_(ITEM_TYPES), *visible(BrainObject, brand, day))).all()
    keys = matches([(key, name, payload) for key, name, payload, _t in rows], words)
    return _hits(session, rows, keys, brand, day) if keys else []


def hits_for(session: Any, keys: Sequence[str], *, brand: str, day: datetime.date,
             by_meaning: bool = False) -> list[OntoHit]:
    """정한 키들 → 물건과 걸린 규칙(볼 수 있는 제품 라인 · 옵션만 · 키 순서 그대로)."""
    if not keys:
        return []
    rows = session.execute(select(BrainObject.item_key, BrainObject.name, BrainObject.payload, BrainObject.item_type)
                           .where(BrainObject.item_key.in_(list(keys)), BrainObject.item_type.in_(ITEM_TYPES),
                                  *visible(BrainObject, brand, day))).all()
    found = {row[0] for row in rows}
    return _hits(session, rows, [key for key in keys if key in found], brand, day, by_meaning=by_meaning)


def _hits(session: Any, rows: Sequence[Any], keys: Sequence[str], brand: str, day: datetime.date, *,
          by_meaning: bool = False) -> list[OntoHit]:
    """(키, 이름, 실음 칸, 유형) 줄 · 고른 키 → :class:`OntoHit` 목록."""
    kinds = {key: item_type for key, _name, _payload, item_type in rows}
    by_key = {key: (name, payload) for key, name, payload, _t in rows}
    rules = _rules(session, keys, brand, day)
    return [OntoHit(key, kinds[key], pref_of(by_key[key][0], by_key[key][1]),
                    dict(by_key[key][1] or {}) if isinstance(by_key[key][1], dict) else {}, tuple(rules[key]),
                    by_meaning=by_meaning)
            for key in keys]

