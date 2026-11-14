"""쓰인 곳 기록 — 한 번 쓰일 때마다 한 줄(설계서 2026-11-14-foms-graft 3.4 · 3.8 · 표 ``brain_usage_events``).

합 표 ``brain_usage``(:mod:`.usage` — 키 · 읽은 쪽마다 수 · 마지막 때)는 그대로 둔다. 이 표는 '지난 2주 수 · 최근 줄' · '이 차례 ·
제안이 쓴 키'를 답하려고 날짜 있는 줄을 쌓는다. 키는 지식 키와 ERP 물건 키(``erp:order/<번호>``)를 같이 쓴다.

- :func:`record_uses` — 근거로 쓴 키마다 한 줄(겹친 키는 한 번 · :data:`MAX_KEYS` 개까지). **커밋은 부르는 쪽 몫**이다.
- :func:`uses_window` · :func:`recent_uses` · :func:`refs_of` — 읽기만(색인 ``(item_key, used_at)`` · ``(ref_kind, ref_id)`` 를 탄다).
- 읽은 쪽(:data:`READERS`)은 상담 초안 · ERP 할 일 제안 · 물어보기. 글은 담지 않는다(키 · 번호 · 때만).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import func, select

from foms.persistence.graft.models import BrainUsageEvent
from foms.services.datetime_kst import now_utc_naive

__all__ = [
    "MAX_DAYS", "MAX_KEYS", "MAX_RECENT", "READER_CHATBOT", "READER_CS_DRAFT", "READER_ERP_ACTION", "READERS", "Use",
    "recent_uses", "record_uses", "refs_of", "uses_window",
]

READER_CS_DRAFT, READER_ERP_ACTION, READER_CHATBOT = "cs_draft", "erp_action", "chatbot"
READERS: tuple[str, ...] = (READER_CS_DRAFT, READER_ERP_ACTION, READER_CHATBOT)
MAX_KEYS = 50
MAX_DAYS = 365
MAX_RECENT = 50
_KEY_LIMIT, _KIND_LIMIT, _REF_LIMIT = 120, 16, 64


@dataclass(frozen=True)
class Use:
    """쓰인 곳 한 줄 — 읽은 쪽 · 무엇 때문에(종류 · 번호) · 언제(UTC naive)."""

    reader: str
    ref_kind: str
    ref_id: str
    used_at: datetime.datetime


def _ref(ref_kind: Any, ref_id: Any) -> tuple[str, str]:
    """(종류, 번호) 글 — 비거나 상한을 넘으면 :class:`ValueError`."""
    kind, ref = str(ref_kind or "").strip(), str(ref_id if ref_id is not None else "").strip()
    if not kind or len(kind) > _KIND_LIMIT:
        raise ValueError("ref_kind")
    if not ref or len(ref) > _REF_LIMIT:
        raise ValueError("ref_id")
    return kind, ref


def record_uses(session: Any, keys: Iterable[Any], reader: str, ref_kind: Any, ref_id: Any,
                now: datetime.datetime) -> int:
    """근거로 쓴 키마다 한 줄을 더한다(겹친 키는 한 번 · 빈 키 · 긴 키는 뺀다 · :data:`MAX_KEYS` 개까지). 커밋은 부르는 쪽.

    Args:
        session: DB 세션.
        keys: 지식 키 · ERP 물건 키 목록.
        reader: :data:`READERS` 가운데 하나.
        ref_kind: 무엇 때문에 — ``cs_turn`` · ``proposal`` · ``question`` 같은 짧은 이름(16자까지).
        ref_id: 그 번호(64자까지 — 정수도 글로 남긴다).
        now: 쓰인 때(UTC naive).

    Returns:
        더한 줄 수.

    Raises:
        ValueError: 모르는 읽은 쪽 · 빈 · 긴 ``ref_kind`` · ``ref_id``.
    """
    if reader not in READERS:
        raise ValueError("reader")
    kind, ref = _ref(ref_kind, ref_id)
    wanted = [key for key in dict.fromkeys(keys) if isinstance(key, str) and key and len(key) <= _KEY_LIMIT]
    rows = [BrainUsageEvent(item_key=key, reader=reader, ref_kind=kind, ref_id=ref, used_at=now)
            for key in wanted[:MAX_KEYS]]
    session.add_all(rows)
    return len(rows)


def uses_window(session: Any, key: str, days: int, *, now: Optional[datetime.datetime] = None) -> dict[str, int]:
    """그 키가 지난 ``days`` 일 동안 쓰인 수 — 읽은 쪽마다(쓰이지 않은 쪽은 0).

    Args:
        session: DB 세션.
        key: 지식 키 · ERP 물건 키.
        days: 1 ~ :data:`MAX_DAYS`.
        now: 기준 때(UTC naive — 없으면 지금).

    Returns:
        읽은 쪽 → 수(:data:`READERS` 모두).
    """
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_DAYS:
        raise ValueError("days")
    since = (now or now_utc_naive()) - datetime.timedelta(days=days)
    rows = session.execute(
        select(BrainUsageEvent.reader, func.count()).where(BrainUsageEvent.item_key == key,
                                                           BrainUsageEvent.used_at >= since)
        .group_by(BrainUsageEvent.reader)).all()
    found = {reader: int(count) for reader, count in rows}
    return {reader: found.get(reader, 0) for reader in READERS}


def recent_uses(session: Any, key: str, limit: int) -> list[Use]:
    """그 키가 쓰인 최근 줄(새것 먼저 · :data:`MAX_RECENT` 개까지)."""
    size = max(0, min(int(limit), MAX_RECENT))
    if size == 0:
        return []
    rows = session.execute(
        select(BrainUsageEvent.reader, BrainUsageEvent.ref_kind, BrainUsageEvent.ref_id, BrainUsageEvent.used_at)
        .where(BrainUsageEvent.item_key == key)
        .order_by(BrainUsageEvent.used_at.desc(), BrainUsageEvent.id.desc()).limit(size)).all()
    return [Use(reader=reader, ref_kind=kind, ref_id=ref, used_at=used_at) for reader, kind, ref, used_at in rows]


def refs_of(session: Any, ref_kind: Any, ref_id: Any) -> list[str]:
    """그 차례 · 제안 · 질문이 쓴 키(처음 쓴 차례대로 · 겹침 없이)."""
    kind, ref = _ref(ref_kind, ref_id)
    rows = session.execute(
        select(BrainUsageEvent.item_key).where(BrainUsageEvent.ref_kind == kind, BrainUsageEvent.ref_id == ref)
        .order_by(BrainUsageEvent.used_at, BrainUsageEvent.id)).scalars().all()
    return list(dict.fromkeys(rows))
