"""brain 표 공통 도움 — 지금 줄 찾기 · 줄 ↔ 값 칸(날짜는 ``YYYY-MM-DD`` 글). 쓰기는 하지 않는다(쓰기는 :mod:`.apply`)."""

from __future__ import annotations

import copy
import datetime
from typing import Any, Mapping, Optional

from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from foms.persistence.brain.models import BrainLink, BrainObject

#: 항목 값 칸(제안 ``fields`` · 반영이 쓰는 칸). 정체 칸(키 · 브랜드 · 층 · 유형)은 바꾸지 않는다 — 바꾸려면 지우고 새로.
OBJECT_FIELDS: tuple[str, ...] = (
    "name", "text", "status", "confidence", "risk_grade", "valid_from", "valid_to", "checked_at", "evidence_kind",
    "evidence_ref", "visibility", "copies", "payload",
)
DATE_FIELDS: tuple[str, ...] = ("valid_from", "valid_to", "checked_at")
#: 링크 값 칸.
LINK_FIELDS: tuple[str, ...] = ("confidence", "valid_from", "valid_to", "evidence_kind", "evidence_ref", "payload")
_KST = datetime.timedelta(hours=9)  # 한국은 일광 절약 시간이 없다


def is_current(model: Any) -> ColumnElement[bool]:
    """지금 줄(대체되지 않은 판) 조건 — 부분 색인과 같은 글자."""
    return model.superseded_at.is_(None)


def in_force(model: Any, today: datetime.date) -> ColumnElement[bool]:
    """유효 기간 안 조건 — 끝 날(``valid_to``)이 없거나 오늘(한국 날짜) 이후. 끝 날은 그날까지 맞다(그날 포함).

    끝난 사실은 기본 읽기 · 이웃 · 모아 센 수에서 뺀다(7.7 · D105). 키로 바로 연 카드만 '기간 끝남'으로 흐리게 보인다."""
    return or_(model.valid_to.is_(None), model.valid_to >= today)


def is_ended(valid_to: Any, today: datetime.date) -> bool:
    """끝 날이 지났나(``date`` 또는 ``YYYY-MM-DD`` 글)."""
    if isinstance(valid_to, str):
        valid_to = datetime.date.fromisoformat(valid_to[:10])
    return isinstance(valid_to, datetime.date) and valid_to < today


def kst_day(now: datetime.datetime) -> datetime.date:
    """UTC naive 시각 → 한국 날짜(하루 판 · 낡음 날)."""
    return (now + _KST).date()


def current_object(session: Any, key: str, *, lock: bool = False) -> Optional[BrainObject]:
    """키의 지금 판 줄(없으면 ``None``). ``lock`` 이면 줄을 잠근다(PostgreSQL)."""
    query = select(BrainObject).where(BrainObject.item_key == key, is_current(BrainObject))
    if lock:
        query = query.with_for_update()
    return session.execute(query.execution_options(populate_existing=True)).scalar_one_or_none()


def object_version(session: Any, key: str, version: int) -> Optional[BrainObject]:
    """키의 그 판 줄(지난 판 포함)."""
    query = select(BrainObject).where(BrainObject.item_key == key, BrainObject.version == int(version))
    return session.execute(query).scalar_one_or_none()


def current_link(session: Any, kind: str, from_key: str, to_key: str, *, lock: bool = False) -> Optional[BrainLink]:
    """(종류, 시작, 끝) 링크의 지금 판 줄(없으면 ``None``)."""
    query = select(BrainLink).where(BrainLink.kind == kind, BrainLink.from_key == from_key,
                                    BrainLink.to_key == to_key, is_current(BrainLink))
    if lock:
        query = query.with_for_update()
    return session.execute(query.execution_options(populate_existing=True)).scalar_one_or_none()


def _jsonable(value: Any) -> Any:
    """날짜 → ``YYYY-MM-DD`` 글, JSON 은 깊은 사본."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()[:10]
    return copy.deepcopy(value)


def values_of(row: Any, fields: tuple[str, ...] = OBJECT_FIELDS) -> dict[str, Any]:
    """줄 → 값 칸 dict(제안 ``fields`` 와 같은 꼴 — 날짜는 글)."""
    return {name: _jsonable(getattr(row, name)) for name in fields}


def column_values(values: Mapping[str, Any]) -> dict[str, Any]:
    """값 칸 dict → 줄에 넣을 값(날짜 글 → ``date``). 꼴 검사를 지난 값만 넘긴다."""
    out = {name: copy.deepcopy(value) for name, value in values.items()}
    for name in DATE_FIELDS:
        if isinstance(out.get(name), str):
            out[name] = datetime.date.fromisoformat(out[name])
    return out
