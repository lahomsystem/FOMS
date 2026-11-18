"""빈 재료 채우기 3판 E '공정 단계 · 제약 · 상황도 따라가기' — :mod:`.onto_find` 의 찾기를 넓힌다(DB 읽기만).

설계서 2026-11-13 온톨로지 빈 재료 채우기 3절 E · 사장님 D205(새 관리 칸 처음 끔 — :data:`.onto_settings.ONTO_FOLLOW_FIELD`).
'물건 찾아 따라가기'가 켜지고 이 칸도 켜진 차례만 :mod:`.drafting_pass` 가 :func:`follow_items` 를 부른다. **끄면 이 모듈은 불리지
않는다** — 두뇌 재료는 글자까지 지금 그대로(시험이 강제).

- **찾기**: 제품 라인 · 옵션에 더해 공정 단계 · 상황도 같은 이름표 맞춤(:func:`.onto_find.matches` — 긴 이름표 먼저 · 겹치면
  긴 쪽 · 물건 상한 :data:`.onto_find.MAX_ITEMS` 는 넷을 합쳐서)으로 찾는다. 보기 조건(지금 판 · 반영 · 보기 범위 모두 · 그
  브랜드와 공통 · 유효 기간 안)은 :func:`.onto_find.visible` 그대로 — 은퇴 · 승인 안 된 · 좁은 범위 항목은 찾지도 잇지도 않는다.
- **공정 단계**: 그 단계로 오는 ``at_step`` 지식(정책 · 사실 · 제작 조건 · 기준 답 · 상황 — 허용 짝 그대로).
- **제품 · 옵션**: 들어오는 ``applies_to`` 규칙(지금 길)에 더해, 그 물건에서 나가는 ``requires``(꼭 같이)와 어느 방향이든
  ``excludes``(같이 못 함 — 방향 없는 뜻, 2판과 같음)의 다른 쪽 대표 이름.
- **상황**: 그 상황에서 나가는 ``applies_to`` 제품 · 옵션 · ``at_step`` 공정 단계, 그 상황으로 오는 ``answers`` 기준 답(지식 id).
- **상한**(앞 설계 5.0 그대로): 물건 8 · 물건당 줄 :data:`.onto_find.MAX_RULES`(걸린 규칙 · 꼭 같이 · 같이 못 함 · 상황 줄을 합쳐
  쓰인 횟수 많은 순) · 묶음 2,000자(:mod:`.onto_block`). 금액 · 키는 싣지 않는다 — 줄은 지식 id 와 대표 이름뿐.
- **제약 넘김**(앞 설계 5절 4): 이름표로 찾은 제품 · 옵션 둘이 ``excludes`` 로 이어져 있으면(손님이 고른 조합) :func:`clashes` 가
  참이고, 부르는 쪽이 두뇌 답을 **막지 않고** 넘김 까닭 :data:`HANDOFF_CONSTRAINT`('제작 조건을 확인해야 해요')로 바꾼다
  (:func:`constraint_handoff`). 상담 AI 가 '안 돼요'라고 단정하지 않는다 — 틀린 '같이 못 함'이 승인돼 있어도 사람이 본다(7절 위험 표).
  이 까닭은 두뇌가 고르는 값(:data:`.brain_prompt.HANDOFF_REASONS` — 출력 스키마 enum)이 아니라 코드만 쓰는 값이다(거절
  ``refused`` 와 같은 자리) — 스키마에 넣으면 칸을 꺼도 두뇌에 가는 요청이 바뀐다.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Iterable, Sequence

from sqlalchemy import select

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.constants import ALLOWED_LINKS
from foms.services.brain.labels import pref_of
from foms.services.brain.store import is_current
from foms.services.cs_agent.brain_prompt import HANDOFF_UNSURE
from foms.services.cs_agent.onto_find import (
    ITEM_TYPES, MAX_RULES, OntoHit, OntoRule, doc_id_of, hits_from, matches, visible,
)

__all__ = ["FOLLOW_TYPES", "HANDOFF_CONSTRAINT", "ROLE_EXCLUDES", "ROLE_REQUIRES", "ROLE_TO", "STEP_SOURCES",
           "clashes", "constraint_handoff", "follow_items"]

STEP, SITUATION = "process_step", "situation"
FOLLOW_TYPES: tuple[str, ...] = (STEP, SITUATION)
#: 공정 단계로 오는 ``at_step`` 의 시작 유형(허용 짝 그대로 — 정책 · 사실 · 제작 조건 · 기준 답 · 상황).
STEP_SOURCES: tuple[str, ...] = tuple(sorted(ALLOWED_LINKS["at_step"][0]))
ROLE_REQUIRES, ROLE_EXCLUDES, ROLE_TO = "requires", "excludes", "to"
#: 코드만 쓰는 넘김 까닭(두뇌 출력 enum 밖) — 메모 말은 :data:`.handoff_memo.HANDOFF_TEXTS`.
HANDOFF_CONSTRAINT = "constraint"
#: 제약 넘김이 덮어쓰는 두뇌 넘김 까닭 — 모름 · 그 밖만(불만 · 할인 · 일정 같은 뚜렷한 까닭은 그대로 둔다).
_VAGUE_REASONS: frozenset[str] = frozenset({HANDOFF_UNSURE, "other"})


def _linked(session: Any, kind: str, ends: Sequence[str], *, near: Any, far: Any, types: Iterable[str], brand: str,
            day: datetime.date, role: str = "") -> list[tuple[str, OntoRule]]:
    """``near`` 끝이 ``ends`` 안인 지금 링크의 다른 쪽(``far``) 항목 — (가까운 끝, 줄) 목록, 쓰인 횟수 많은 순. ``role`` 이 있으면
    (꼭 같이 · 같이 못 함 · 상황이 걸린 곳) 대표 이름 · 지식 id 없음, 없으면(걸린 지식) 지금 길처럼 이름 · 지식 id.

    다른 쪽도 보기 조건(:func:`.onto_find.visible`)을 지나야 한다 — 은퇴 · 좁은 범위 · 다른 브랜드 끝은 잇지 않는다."""
    if not ends:
        return []
    rows = session.execute(
        select(near, BrainObject.item_key, BrainObject.item_type, BrainObject.name, BrainObject.payload,
               BrainObject.usage_count)
        .join(BrainObject, BrainObject.item_key == far)
        .where(is_current(BrainLink), BrainLink.kind == kind, near.in_(list(ends)),
               BrainObject.item_type.in_(list(types)), *visible(BrainObject, brand, day))
        .order_by(BrainObject.usage_count.desc(), BrainObject.item_key)).all()
    return [(end, OntoRule(key, "" if role else doc_id_of(payload), item_type, pref_of(name, payload) if role else name,
                           int(usage or 0), role))
            for end, key, item_type, name, payload, usage in rows]


def _ties(session: Any, keys: Sequence[str], brand: str, day: datetime.date) -> tuple[dict, dict]:
    """제품 · 옵션 키마다 (꼭 같이 · 같이 못 함 줄, 같이 못 함 다른 쪽 키 전부 — 상한 없음)."""
    ends = (*ITEM_TYPES, "spec", "build_rule")
    lines: dict[str, list[OntoRule]] = {key: [] for key in keys}
    banned: dict[str, set[str]] = {key: set() for key in keys}
    common = {"types": ends, "brand": brand, "day": day}
    for end, rule in _linked(session, "requires", keys, near=BrainLink.from_key, far=BrainLink.to_key,
                             role=ROLE_REQUIRES, **common):
        lines[end].append(rule)
    out_ex = _linked(session, "excludes", keys, near=BrainLink.from_key, far=BrainLink.to_key, role=ROLE_EXCLUDES,
                     **common)
    in_ex = _linked(session, "excludes", keys, near=BrainLink.to_key, far=BrainLink.from_key, role=ROLE_EXCLUDES,
                    **common)
    for end, rule in sorted((*out_ex, *in_ex), key=lambda pair: (-pair[1].usage, pair[1].key)):
        if rule.key not in banned[end]:  # 양쪽으로 둘 다 이어져 있어도 한 줄
            banned[end].add(rule.key)
            lines[end].append(rule)
    return lines, banned


def _top(rules: Iterable[OntoRule]) -> tuple[OntoRule, ...]:
    """줄을 쓰인 횟수 많은 순으로 상한 :data:`.onto_find.MAX_RULES` 까지(같으면 들어온 차례)."""
    ordered = sorted(enumerate(rules), key=lambda pair: (-pair[1].usage, pair[0]))
    return tuple(rule for _i, rule in ordered[:MAX_RULES])


def follow_items(session: Any, texts: Sequence[str], *, brand: str, day: datetime.date,
                 extra: Iterable[str] = ()) -> list[OntoHit]:
    """손님 원문(+ 확인된 주문 품목 이름) → 찾은 제품 · 옵션 · 공정 단계 · 상황과 그 줄(모듈 설명). 없으면 빈 목록."""
    words = [*texts, *extra]
    if not any(word.strip() for word in words):
        return []
    rows = session.execute(select(BrainObject.item_key, BrainObject.name, BrainObject.payload, BrainObject.item_type)
                           .where(BrainObject.item_type.in_((*ITEM_TYPES, *FOLLOW_TYPES)),
                                  *visible(BrainObject, brand, day))).all()
    keys = matches([(key, name, payload) for key, name, payload, _t in rows], words)
    if not keys:
        return []
    kinds = {key: item_type for key, _n, _p, item_type in rows}
    by_key = {key: (name, payload) for key, name, payload, _t in rows}
    things = [key for key in keys if kinds[key] in ITEM_TYPES]
    steps = [key for key in keys if kinds[key] == STEP]
    places = [key for key in keys if kinds[key] == SITUATION]
    base = {hit.key: hit for hit in hits_from(session, rows, things, brand, day)}
    ties, banned = _ties(session, things, brand, day)
    extra_rules: dict[str, list[OntoRule]] = {key: [] for key in (*steps, *places)}
    common = {"brand": brand, "day": day}
    for end, rule in _linked(session, "at_step", steps, near=BrainLink.to_key, far=BrainLink.from_key,
                             types=STEP_SOURCES, **common):
        extra_rules[end].append(rule)
    for kind, types in (("applies_to", ITEM_TYPES), ("at_step", (STEP,))):
        for end, rule in _linked(session, kind, places, near=BrainLink.from_key, far=BrainLink.to_key, types=types,
                                 role=ROLE_TO, **common):
            extra_rules[end].append(rule)
    for end, rule in _linked(session, "answers", places, near=BrainLink.to_key, far=BrainLink.from_key,
                             types=("template",), **common):
        extra_rules[end].append(rule)
    out: list[OntoHit] = []
    for key in keys:
        if key in base:
            hit = base[key]
            lines = _top((*hit.rules, *ties[key]))
            out.append(dataclasses.replace(hit, rules=lines, clash_keys=frozenset(banned[key])))
        else:
            name, payload = by_key[key]
            lines = _top(extra_rules[key])
            out.append(OntoHit(key, kinds[key], pref_of(name, payload), {}, lines))
    return out


def clashes(hits: Sequence[Any]) -> bool:
    """이름표로 찾은 제품 · 옵션 둘이 '같이 못 함'으로 이어져 있나(뜻으로 찾은 물건은 손님이 고른 것이 아니라 뺀다)."""
    chosen = {hit.key for hit in hits if hit.item_type in ITEM_TYPES and not getattr(hit, "by_meaning", False)}
    return any(chosen & set(getattr(hit, "clash_keys", ())) for hit in hits if hit.key in chosen)


def constraint_handoff(result: Any) -> Any:
    """같이 못 함 조합 차례의 두뇌 답 → 넘김 까닭 :data:`HANDOFF_CONSTRAINT`(초안은 놓지 않는다 — 넘김 길). 거절 · 뚜렷한
    까닭의 넘김은 그대로."""
    if result.refused or (result.handoff and result.handoff_reason not in _VAGUE_REASONS):
        return result
    return dataclasses.replace(result, handoff=True, handoff_reason=HANDOFF_CONSTRAINT)
