"""연결 개수 규칙(설계서 7.7 · 사장님 D105 · 7.8 D115) — 최대는 반영 때 막고, 최소는 '빠진 링크'로 알린다. 품질 수.

규칙은 :func:`foms.services.brain.constants.cardinality`((시작 유형, 링크 종류, 실음 칸) → (최소, 최대)) 하나다 — 가격 규칙 →
정본 자리는 **근거 종류**(``payload.basis``)로 갈린다(계산기 꼭 1 · 회사 지식 0 · 두 값의 차이 꼭 2 · 설정 꼭 1, 근거 종류가
빈 옛 항목은 최소를 따지지 않음). 세는 것은 그 항목에서 **나가는** 지금 · 유효 기간 안(D105) 링크다.

- **최대**(:func:`check_link_limit`): 반영 동작이 링크 더하기 때 부른다. 데이터 규칙이라 보는 사람과 무관하게 모든 링크를 센다.
  같은 때 두 반영이 같은 항목에 더하지 못하게 시작 항목 줄을 잠근 뒤 센다(PostgreSQL).
- **최소**(:func:`missing_links` — 카드 · :func:`quality_counts` — 품질 수 API): 막지 않고 알린다. 보는 사람이 볼 수 없는 끝으로
  가는 링크는 세지 않는다(볼 수 없는 항목이 있다는 것조차 새지 않게 — 4절 '모아 센 수에도 범위'). 바깥 자리 끝은 늘 센다 —
  근거 종류가 받는 끝(계산기 · 설정)만 최소에 세고, 넘음은 모든 끝을 센다(근거 종류를 바꾼 뒤 남은 다른 끝도 넘음으로 보인다).
  수도 볼 수 있는 · 유효 기간 안 항목만 센다.
- **은퇴 항목을 가리키는 지금 링크**(7.8 다음 14 — :func:`retired_targets` 카드 · 품질 수 ``retired_links``): 막지 않고 경고.
- **값 목록 밖 줄**(:func:`off_list_counts` — 품질 수 ``off_list``): DB 검사 제약 대신 지금 줄의 유형 · 브랜드 · 상태 · 링크
  종류가 정한 목록(:func:`.constants.value_problems` 와 같은 목록) 안인지 센다(반영 동작 밖에서 쓴 줄을 잡는다).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import and_, false, func, not_, or_, select
from sqlalchemy.orm import aliased

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.constants import (
    BASIS_FIELD, BASIS_RULES, BRANDS, EXTERNAL_PREFIXES, LINK_KINDS, OBJECT_STATUSES,
    PRICE_RULE_TYPE, STATUS_RETIRED, TYPES, basis_rule, cardinality, cardinality_rules,
)
from foms.services.brain.errors import BrainLinkLimitError
from foms.services.brain.scope import Viewer, scope_clause
from foms.services.brain.store import in_force, is_current

_PREFIX_OF = {ext: prefix for prefix, ext in EXTERNAL_PREFIXES.items()}


def out_degree(session: Any, key: str, kind: str, today: datetime.date) -> int:
    """그 항목에서 나가는 지금 · 유효 기간 안 그 종류 링크 수(모든 끝)."""
    return int(session.execute(select(func.count()).select_from(BrainLink).where(
        BrainLink.from_key == key, BrainLink.kind == kind, is_current(BrainLink), in_force(BrainLink, today),
    )).scalar_one())


def check_link_limit(session: Any, source: BrainObject, kind: str, today: datetime.date) -> None:
    """링크 하나를 더해도 최대를 넘지 않나(반영 동작 — 링크 더하기). 가격 규칙은 그 항목의 근거 종류로 최대를 정한다.

    Raises:
        BrainLinkLimitError: 이미 최대만큼 이어져 있다(근거 종류 ``brain`` 은 최대 0).
    """
    _low, high = cardinality(source.item_type, kind, source.payload)
    if high is not None and out_degree(session, source.item_key, kind, today) >= high:
        raise BrainLinkLimitError(kind, high)


def _ends_clause(ends: Optional[Iterable[str]]) -> Any:
    """받는 끝 유형(바깥 자리)만 — ``None`` 이면 모든 끝."""
    if ends is None:
        return None
    prefixes = [_PREFIX_OF[e] for e in ends if e in _PREFIX_OF]
    return or_(*(BrainLink.to_key.like(p + "%") for p in prefixes)) if prefixes else false()


def _seen_links(viewer: Viewer, today: datetime.date, owner: Any, kind: str, ends: Optional[Iterable[str]] = None) -> Any:
    """``owner`` 항목에서 나가는, 보는 사람이 셀 수 있는 그 종류 링크 수(상관 부분 질의). ``ends`` 를 주면 그 바깥 끝만."""
    target = aliased(BrainObject)
    seen_target = select(target.item_key).where(target.item_key == BrainLink.to_key, is_current(target),
                                                *_owner_clauses(viewer, today, target)).exists()
    external = or_(*(BrainLink.to_key.like(prefix + "%") for prefix in EXTERNAL_PREFIXES))
    narrow = _ends_clause(ends)
    return (select(func.count()).select_from(BrainLink)
            .where(BrainLink.from_key == owner.item_key, BrainLink.kind == kind, is_current(BrainLink),
                   in_force(BrainLink, today), or_(external, seen_target) if narrow is None else narrow)
            .correlate(owner).scalar_subquery())


def _rule_ends(item_type: str, kind: str, basis: Optional[str]) -> Optional[tuple[str, ...]]:
    """최소에 세는 끝 — 가격 규칙 근거 종류 줄이면 그 근거 종류가 받는 끝, 그 밖은 모든 끝(``None``)."""
    if item_type == PRICE_RULE_TYPE and kind == "value_from" and basis is not None:
        return BASIS_RULES[basis][2] if basis else basis_rule(None)[2]
    return None


def missing_links(session: Any, viewer: Viewer, item: dict[str, Any], *,
                  today: datetime.date) -> list[dict[str, Any]]:
    """카드 '빠진 링크' — 최소에 못 미치는 종류 ``[{"kind", "min", "max", "have"}]``(최소 규칙이 없으면 빈 목록).

    ``item`` 은 ``key`` · ``type`` (+ 가격 규칙이면 ``payload`` — 근거 종류)."""
    kinds = sorted({k for t, k, _b, low, _h in cardinality_rules() if t == item["type"] and low > 0}
                   | ({"value_from"} if item["type"] == PRICE_RULE_TYPE else set()))
    owner = aliased(BrainObject)
    out = []
    for kind in kinds:
        low, high = cardinality(item["type"], kind, item.get("payload"))
        if low <= 0:
            continue
        ends = basis_rule(item.get("payload"))[2] if item["type"] == PRICE_RULE_TYPE and kind == "value_from" else None
        have = session.execute(select(_seen_links(viewer, today, owner, kind, ends)).where(
            owner.item_key == item["key"], is_current(owner))).scalar_one_or_none() or 0
        if have < low:
            out.append({"kind": kind, "min": low, "max": high, "have": int(have)})
    return out


def _basis_clause(owner: Any, basis: Optional[str]) -> list[Any]:
    """가격 규칙 근거 종류 줄 거르기(빈 근거 = 정한 값이 아닌 모든 것)."""
    if basis is None:
        return []
    value = owner.payload[BASIS_FIELD].as_string()
    if basis:
        return [value == basis]
    return [or_(value.is_(None), value.notin_(sorted(BASIS_RULES)))]


def quality_counts(session: Any, viewer: Viewer, *, today: datetime.date) -> dict[str, Any]:
    """품질 수(7.5 화면 11 의 앞 조각) — 규칙마다 볼 수 있는 항목 수 · 최소 미달 수 · 최대 넘음 수 + 은퇴 항목을 가리키는 지금
    링크 수 + 값 목록 밖 줄 수.

    Returns:
        ``{"rules": [{"type", "kind", "basis", "min", "max", "items", "missing", "over"}], "missing_total", "over_total",
        "retired_links", "off_list"}`` — ``basis`` 는 가격 규칙 근거 종류(빈 근거는 ``""``, 그 밖 규칙은 ``None``).
    """
    rows = []
    for item_type, kind, basis, low, high in cardinality_rules():
        owner = aliased(BrainObject)
        visible = [owner.item_type == item_type, is_current(owner), *_owner_clauses(viewer, today, owner),
                   *_basis_clause(owner, basis)]
        items = int(session.execute(select(func.count()).select_from(owner).where(*visible)).scalar_one())
        need = _seen_links(viewer, today, owner, kind, _rule_ends(item_type, kind, basis))
        every = _seen_links(viewer, today, owner, kind)
        missing = int(session.execute(select(func.count()).select_from(owner).where(*visible, need < low))
                      .scalar_one()) if low > 0 and items else 0
        over = int(session.execute(select(func.count()).select_from(owner).where(*visible, every > high))
                   .scalar_one()) if high is not None and items else 0
        rows.append({"type": item_type, "kind": kind, "basis": basis, "min": low, "max": high, "items": items,
                     "missing": missing, "over": over})
    return {"rules": rows, "missing_total": sum(r["missing"] for r in rows), "over_total": sum(r["over"] for r in rows),
            "retired_links": retired_link_count(session, viewer, today=today), "off_list": off_list_counts(session)}


def _retired_join(viewer: Viewer, today: datetime.date) -> tuple[Any, Any, Any]:
    """지금 · 유효 기간 안 링크 + 볼 수 있는 시작 항목 + 볼 수 있는 은퇴한 끝 항목(별칭 둘 · 조건)."""
    source, target = aliased(BrainObject), aliased(BrainObject)
    where = and_(is_current(BrainLink), in_force(BrainLink, today),
                 source.item_key == BrainLink.from_key, is_current(source), *_owner_clauses(viewer, today, source),
                 target.item_key == BrainLink.to_key, is_current(target), scope_clause(viewer, target.visibility),
                 target.status == STATUS_RETIRED)
    return source, target, where


def retired_link_count(session: Any, viewer: Viewer, *, today: datetime.date) -> int:
    """은퇴 항목을 가리키는 지금 링크 수(양 끝을 볼 수 있는 것만 — 7.8 다음 14 경고)."""
    _source, _target, where = _retired_join(viewer, today)
    return int(session.execute(select(func.count()).select_from(BrainLink).where(where)).scalar_one())


def retired_targets(session: Any, viewer: Viewer, key: str, *, today: datetime.date) -> list[dict[str, Any]]:
    """카드 경고 — 이 항목에서 나가는, 은퇴 항목을 가리키는 지금 링크 ``[{"kind", "key", "name"}]``(볼 수 있는 끝만)."""
    source, target, where = _retired_join(viewer, today)
    rows = session.execute(select(BrainLink.kind, target.item_key, target.name).where(
        where, BrainLink.from_key == key).order_by(BrainLink.kind, target.item_key).limit(30)).all()
    return [{"kind": kind, "key": to_key, "name": name} for kind, to_key, name in rows]


def off_list_counts(session: Any) -> dict[str, int]:
    """값 목록 밖 지금 줄 수 — 유형 · 브랜드 · 상태(항목) · 링크 종류(링크). DB 검사 제약 대신 코드 목록으로 센다(7.8 다음 14)."""
    def count(model: Any, *clauses: Any) -> int:
        return int(session.execute(select(func.count()).select_from(model).where(is_current(model), *clauses))
                   .scalar_one())

    return {"item_type": count(BrainObject, not_(BrainObject.item_type.in_(TYPES))),
            "brand": count(BrainObject, not_(BrainObject.brand.in_(BRANDS))),
            "status": count(BrainObject, not_(BrainObject.status.in_(OBJECT_STATUSES))),
            "kind": count(BrainLink, not_(BrainLink.kind.in_(LINK_KINDS)))}


def _owner_clauses(viewer: Viewer, today: datetime.date, owner: Any) -> list[Any]:
    """별칭 항목 표에 같은 보기 범위 · 유효 기간 조건(:func:`.read.visible_clauses` 와 같은 뜻)."""
    return [scope_clause(viewer, owner.visibility), in_force(owner, today)]


def item_rules(item_type: Optional[str], payload: Any = None) -> list[dict[str, Any]]:
    """그 유형의 연결 개수 규칙(화면 안내용) — 가격 규칙은 그 항목 근거 종류의 규칙 하나."""
    kinds = [k for t, k, basis, _l, _h in cardinality_rules() if t == item_type and basis in (None, "")]
    return [{"kind": kind, "min": low, "max": high}
            for kind in kinds for low, high in (cardinality(item_type, kind, payload),)]
