"""링크 제약(설계서 7.8 다음 1 · 2 · 14) — 허용 짝 표(:data:`.constants.ALLOWED_LINKS`) 위에서 **항목 값 · 이미 있는 링크**를
보는 검사. 제안 때(:func:`.proposals.propose_link`)와 반영 때(:func:`.apply.apply_change`) 같은 함수(:func:`check_link_rules`)를
부른다 — 링크 **더하기**만 본다(빼기는 막지 않는다: 잘못 이어진 링크는 끊을 수 있어야 한다).

1. 가격 규칙 근거 종류별 끝(사장님 D115) — ``calc`` 는 계산기만 · ``setting`` 은 설정만 · ``derived`` 는 둘 다 · ``brain`` 은
   정본 자리 링크 없음(빈 근거 종류는 예전처럼 둘 다). 개수 최대는 :func:`.quality.check_link_limit` 가 반영 때 센다.
2. 같은 두 항목 사이에 ``requires`` + ``excludes`` 를 함께 두지 않는다(어느 방향이든 — 서로 맞서는 조건).
3. ``supersedes`` · ``broader`` 고리 막기(자기 자신 포함) — 지금 · 유효 기간 안 링크를 따라간다(:data:`MAX_WALK` 까지).
4. ``supersedes`` 를 반영하면 앞 항목의 유효 끝을 찍는다(:func:`superseded_end` — 새 결정의 유효 시작 전날, 시작 날이 없으면
   반영 날 한국 날짜). 앞 항목 새 판은 :mod:`.apply` 가 쓴다.

막을 때는 :class:`.errors.BrainLinkRuleError`(규칙 이름 · 키만 — 항목 글 없음).
"""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select

from foms.persistence.brain.models import BrainLink
from foms.services.brain.constants import (
    ACYCLIC_KINDS, OPPOSED_KINDS, PRICE_RULE_TYPE, basis_of, basis_rule,
)
from foms.services.brain.errors import BrainLinkRuleError
from foms.services.brain.store import in_force, is_current

#: 고리 찾기에서 따라가는 항목 수 상한(넘으면 고리 없음으로 보지 않고 막는다 — 확인 못 한 고리를 넣지 않게).
MAX_WALK = 2000


def end_problem(source_type: Optional[str], payload: Any, kind: str, to_type: Optional[str]) -> Optional[str]:
    """시작 항목 값으로 본 끝 유형 문제(가격 규칙 근거 종류 — D115). 없으면 ``None``."""
    if source_type != PRICE_RULE_TYPE or kind != "value_from":
        return None
    _low, _high, ends = basis_rule(payload)
    if to_type in ends:
        return None
    return f"근거 종류 {basis_of(payload) or '빈 값'} 인 가격 규칙은 이 정본 자리({to_type})를 가리키지 않는다"


def opposed_exists(session: Any, kind: str, from_key: str, to_key: str, today: datetime.date) -> bool:
    """같은 두 항목 사이(어느 방향이든)에 맞서는 종류(필요 ↔ 제외)의 지금 · 유효 기간 안 링크가 있나."""
    other = OPPOSED_KINDS.get(kind)
    if other is None:
        return False
    pair = or_(and_(BrainLink.from_key == from_key, BrainLink.to_key == to_key),
               and_(BrainLink.from_key == to_key, BrainLink.to_key == from_key))
    return bool(session.execute(select(func.count()).select_from(BrainLink).where(
        BrainLink.kind == other, pair, is_current(BrainLink), in_force(BrainLink, today))).scalar_one())


def reaches(session: Any, kind: str, start: str, goal: str, today: datetime.date) -> bool:
    """``start`` 에서 그 종류 지금 · 유효 기간 안 링크를 따라가 ``goal`` 에 닿나(너비 우선 — 단계마다 한 질의).
    :data:`MAX_WALK` 를 넘으면 닿은 것으로 본다(확인 못 한 고리를 넣지 않게)."""
    seen, frontier = {start}, [start]
    while frontier:
        rows = session.execute(select(BrainLink.to_key).where(
            BrainLink.kind == kind, BrainLink.from_key.in_(frontier), is_current(BrainLink),
            in_force(BrainLink, today))).scalars().all()
        frontier = []
        for key in rows:
            if key == goal:
                return True
            if key not in seen:
                seen.add(key)
                frontier.append(key)
        if len(seen) > MAX_WALK:
            return True
    return False


def creates_cycle(session: Any, kind: str, from_key: str, to_key: str, today: datetime.date) -> bool:
    """이 링크를 더하면 고리가 생기나(고리 막는 종류만 — 자기 자신을 가리키는 것 포함)."""
    if kind not in ACYCLIC_KINDS:
        return False
    return from_key == to_key or reaches(session, kind, to_key, from_key, today)


def check_link_rules(session: Any, source: Any, kind: str, to_key: str, to_type: Optional[str],
                     today: datetime.date) -> None:
    """링크 더하기 제약(모듈 설명 1 ~ 3). ``source`` 는 시작 항목 지금 줄.

    Raises:
        BrainLinkRuleError: 근거 종류와 맞지 않는 끝 · 맞서는 짝 · 고리.
    """
    problem = end_problem(source.item_type, source.payload, kind, to_type)
    if problem:
        raise BrainLinkRuleError("basis_end", problem)
    if opposed_exists(session, kind, source.item_key, to_key, today):
        raise BrainLinkRuleError("opposed", f"같은 두 항목 사이에 {OPPOSED_KINDS[kind]} 링크가 있다 — {kind} 를 함께 두지 않는다")
    if creates_cycle(session, kind, source.item_key, to_key, today):
        raise BrainLinkRuleError("cycle", f"{kind} 링크가 고리를 만든다")


def superseded_end(decision_valid_from: Optional[datetime.date], today: datetime.date) -> datetime.date:
    """대체된 앞 항목의 유효 끝 — 새 결정의 유효 시작 전날, 시작 날이 없으면 반영 날(그날까지 맞다)."""
    if decision_valid_from is not None:
        return decision_valid_from - datetime.timedelta(days=1)
    return today
