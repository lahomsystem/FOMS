"""열린 엇갈림 — 항목에 대한 엇갈림이 열린 동안 그 항목은 **'확인 필요'**(설계서 3.1 규칙 4 · 전사 지식 온톨로지 점검 '지금 8').

'열린 엇갈림' = 반영(``active``) · 지금 판 · 유효 기간 안 ``conflict`` 항목이 그 항목을 가리킨다 — ``about`` 링크(지금 · 유효 기간
안)로, 또는 챗봇 틀림 신고로 만든 엇갈림의 실음 칸 ``target``(링크를 잇기 전 — :mod:`.chat_reports`). 엇갈림을 은퇴시키면 닫힌다.

'확인 필요'는 열린 제안(:mod:`.browse` 의 상관 부분 질의) **또는** 열린 엇갈림이다 — 화면 표시 · 지식 표 거르기 · 카드 ·
챗봇 후보가 같은 판정을 쓴다.
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from foms.persistence.brain.models import BrainLink, BrainObject
from foms.services.brain.constants import STATUS_ACTIVE
from foms.services.brain.store import in_force, is_current
from foms.services.datetime_kst import get_today_kst

CONFLICT = "conflict"


def _about(conflict: Any, key_column: Any, today: datetime.date) -> ColumnElement[bool]:
    """엇갈림 줄이 그 키에 대한 것인가 — ``about`` 링크 또는 실음 칸 ``target``."""
    link = exists(select(BrainLink.id).where(BrainLink.kind == "about", BrainLink.from_key == conflict.item_key,
                                             BrainLink.to_key == key_column, is_current(BrainLink),
                                             in_force(BrainLink, today)))
    return or_(link, conflict.payload["target"].as_string() == key_column)


def open_conflict_clause(model: Any = BrainObject, today: Optional[datetime.date] = None) -> ColumnElement[bool]:
    """그 항목(``model`` — 항목 표 또는 별칭)에 열린 엇갈림이 있다(상관 부분 질의)."""
    day = today or get_today_kst()
    conflict = aliased(BrainObject)
    return exists(select(conflict.id).where(conflict.item_type == CONFLICT, is_current(conflict),
                                            conflict.status == STATUS_ACTIVE, in_force(conflict, day),
                                            _about(conflict, model.item_key, day)).correlate(model))


def open_conflict_counts(session: Any, keys: Iterable[str], today: Optional[datetime.date] = None) -> dict[str, int]:
    """키 → 열린 엇갈림 수(없으면 빠짐)."""
    wanted = sorted({k for k in keys if isinstance(k, str)})
    if not wanted:
        return {}
    day = today or get_today_kst()
    target = aliased(BrainObject)
    conflict = aliased(BrainObject)
    rows = session.execute(select(target.item_key, func.count(conflict.id))
                           .join(conflict, and_(conflict.item_type == CONFLICT, is_current(conflict),
                                                conflict.status == STATUS_ACTIVE, in_force(conflict, day),
                                                _about(conflict, target.item_key, day)))
                           .where(target.item_key.in_(wanted), is_current(target))
                           .group_by(target.item_key)).all()
    return {key: int(n) for key, n in rows if n}
