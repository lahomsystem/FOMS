"""쓰인 횟수 — **판 행이 아니라 따로 센다**(설계서 7.7 · 사장님 D105 · 표 ``brain_usage``).

- :func:`count_reads` — 직원 챗봇(``chatbot``) · 상담 두뇌(``cs_brain``)가 근거로 쓴 항목 키마다 수 +1 · 마지막 쓰인 때. 판
  줄을 새로 만들지 않는다. 같은 (키, 읽은 쪽) 줄이 동시에 처음 만들어지면 저장점 안에서 다시 더한다(부르는 쪽 트랜잭션을 깨지
  않는다). 커밋은 부르는 쪽 몫이다.
- :func:`count_doc_reads` — 상담 두뇌 초안의 근거 id(지식 문서 항목 id)를 brain 항목 키로 바꿔 센다. 실패해도 초안 길을 깨지
  않는다(저장점 — 경고 로그에 코드만).
- :func:`usage_total` — 화면 정렬 · 표시용 식: 판 줄 칸(옮긴 옛 값) + 이 표의 합(상관 부분 질의 — N+1 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from foms.persistence.brain.models import BrainObject, BrainUsage
from foms.services.brain.constants import BRAND_COMMON, DOC_TYPES
from foms.services.brain.store import is_current

logger = logging.getLogger(__name__)

READER_CHATBOT, READER_CS = "chatbot", "cs_brain"
READERS: tuple[str, ...] = (READER_CHATBOT, READER_CS)
MAX_KEYS = 50


def _bump(session: Any, key: str, reader: str, now: datetime.datetime) -> None:
    """한 줄 +1 — 없으면 만든다(같은 때 만든 쪽이 있으면 다시 더한다)."""
    stmt = (update(BrainUsage).where(BrainUsage.item_key == key, BrainUsage.reader == reader)
            .values(count=BrainUsage.count + 1, last_used_at=now).execution_options(synchronize_session=False))
    if session.execute(stmt).rowcount:
        return
    try:
        with session.begin_nested():
            session.add(BrainUsage(item_key=key, reader=reader, count=1, last_used_at=now))
    except IntegrityError:
        session.execute(stmt)


def count_reads(session: Any, keys: Iterable[str], reader: str, *, now: datetime.datetime) -> int:
    """근거로 쓴 키마다 +1(겹친 키는 한 번). 센 키 수를 돌려준다. 판 줄은 건드리지 않는다."""
    if reader not in READERS:
        raise ValueError("reader")
    wanted = [k for k in dict.fromkeys(keys) if isinstance(k, str) and k][:MAX_KEYS]
    for key in wanted:
        _bump(session, key, reader, now)
    return len(wanted)


def doc_keys(session: Any, brand: str, doc_ids: Iterable[str]) -> list[str]:
    """지식 문서 항목 id → 지금 판 brain 키(그 브랜드 + 공통 · 지식 문서 유형). 없는 id 는 뺀다."""
    wanted = {i for i in doc_ids if isinstance(i, str) and i}
    if not wanted:
        return []
    rows = session.execute(select(BrainObject.item_key, BrainObject.payload).where(
        is_current(BrainObject), BrainObject.brand.in_((brand, BRAND_COMMON)),
        BrainObject.item_type.in_(DOC_TYPES))).all()
    return sorted(key for key, payload in rows if isinstance(payload, dict) and payload.get("doc_id") in wanted)


def count_doc_reads(session: Any, brand: str, doc_ids: Iterable[str], *, now: datetime.datetime) -> int:
    """상담 두뇌 초안 근거를 센다 — 실패해도 부르는 쪽 트랜잭션은 그대로(저장점). 센 키 수(실패면 0)."""
    ids = [i for i in doc_ids if isinstance(i, str)]
    if not ids:
        return 0
    try:
        with session.begin_nested():
            return count_reads(session, doc_keys(session, brand, ids), READER_CS, now=now)
    except SQLAlchemyError as exc:
        logger.warning("[회사 지식 쓰인 횟수] 상담 두뇌 근거를 세지 못했다 code=%s", type(exc).__name__)
        return 0


def usage_sum(model: Any = BrainObject) -> Any:
    """이 표의 합(그 항목 키 — 읽은 쪽 모두) 상관 부분 질의. ``model`` 은 항목 표 또는 그 별칭."""
    return (select(func.coalesce(func.sum(BrainUsage.count), 0)).where(BrainUsage.item_key == model.item_key)
            .correlate(model).scalar_subquery())


def usage_total(model: Any = BrainObject) -> Any:
    """화면 '쓰인 횟수' 식 — 판 줄 칸(옛 값) + 따로 센 합(줄이 없으면 0)."""
    return func.coalesce(model.usage_count, 0) + usage_sum(model)


def usage_of(session: Any, keys: Iterable[str]) -> dict[str, int]:
    """키마다 따로 센 합(없으면 0) — 읽은 쪽별이 아니라 합만."""
    wanted = sorted({k for k in keys if isinstance(k, str)})
    if not wanted:
        return {}
    rows = session.execute(select(BrainUsage.item_key, func.sum(BrainUsage.count))
                           .where(BrainUsage.item_key.in_(wanted)).group_by(BrainUsage.item_key)).all()
    found = {key: int(total or 0) for key, total in rows}
    return {key: found.get(key, 0) for key in wanted}


def usage_by_reader(session: Any, key: str) -> dict[str, int]:
    """한 항목의 읽은 쪽별 수(카드)."""
    rows = session.execute(select(BrainUsage.reader, BrainUsage.count).where(BrainUsage.item_key == key)).all()
    return {reader: int(count or 0) for reader, count in rows}
