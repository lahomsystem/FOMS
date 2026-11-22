"""넘긴 상담 배우기 — 되풀이 문턱의 '기다리는 말'(사장님 2026-11-23 '여러 번 나온 것만 바로 반영' · 설계서
``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 3절).

밤 배우기는 서로 다른 상담 :data:`MIN_CHATS` 곳 이상에서 나온 말만 지식에 바로 넣는다(새 지식 · 더함 — 넣는 갈래는
:mod:`.handoff_learning_route`). 한 상담에서만 들은 말은 지식에도 엇갈림 카드에도 넣지 않고 여기(:class:`models.CsAgentLearnHeld`)
모아 둔다.

- **모으기**(:func:`hold`): 가림 관문을 지난 일반화한 이름 · 글과 근거 상담 · 차례 번호, 올릴 때 합칠 근거 글(``case:`` ·
  ``staff:``)만. 놓을 자리 판정에 이미 만든 뜻 찾기 벡터가 있으면 그 줄의 벡터로 남긴다(근원 ``cs_learn_held`` — 돈 더 안 듦).
- **가까운 것 찾기**(:func:`near`): 같은 브랜드 · 기다리는 것 가운데 글자 비슷함(:func:`.case_memory.text_similarity`
  :data:`NEAR_SIMILARITY` 이상) 앞 :data:`MAX_NEAR` 개 + 벡터가 있으면 뜻 비슷함(:data:`NEAR_MEANING` 이상) 앞 :data:`MAX_NEAR`
  개. 놓을 자리 판정자에게 회사 지식과 따로 보인다(키 :data:`KEY_PREFIX` + 번호).
- **되풀이 더하기**(:func:`add_turns`): 같은 말이 다시 나오면 근거 상담 · 차례 · 근거 글을 합치고 마지막 본 때를 고친다.
- **끝내기**(:func:`finish`): 지식 · 카드로 올라가면 ``promoted``, 같음 · 이미 정함 · 규칙 아님이면 ``dropped``.
  :data:`EXPIRE_DAYS` 일 동안 다시 안 나온 말도 ``dropped``(:func:`expire`). 벡터 줄은 기다리는 동안만 둔다.

커밋은 부르는 쪽. 로그에는 수 · 코드만(글 · 상담 id 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import String, cast, select

from foms.persistence.brain.vectors import brain_embeddings
from foms.services.brain.embeddings import (
    SOURCE_HELD, drop_vectors, nearest_rows, safe_text, store_vector, table_ready, text_hash,
)
from foms.services.cs_agent.case_memory import text_similarity
from foms.services.cs_agent.channel_read import naive_utc
from models import CsAgentLearnHeld

logger = logging.getLogger(__name__)

__all__ = [
    "DROPPED", "EXPIRE_DAYS", "KEY_PREFIX", "MAX_NEAR", "MIN_CHATS", "PROMOTED", "STATES", "WAITING", "add_turns", "expire",
    "finish", "held_key", "held_row", "hold", "merged_evidence", "near",
]

WAITING, PROMOTED, DROPPED = "waiting", "promoted", "dropped"
#: 상태 셋 — 마이그레이션 ``csagent_08`` · models.py 검사 제약과 같은 글자(시험이 견준다).
STATES: tuple[str, ...] = (WAITING, PROMOTED, DROPPED)
#: 지식에 바로 넣는 서로 다른 상담 수 하한(사장님 11-23).
MIN_CHATS = 2
EXPIRE_DAYS = 60
MAX_NEAR, NEAR_SIMILARITY, NEAR_MEANING, SCAN = 3, 0.35, 0.5, 500
KEY_PREFIX = "held:"
_T = CsAgentLearnHeld


def held_key(row_id: int) -> str:
    """판정자에게 보이는 기다리는 말 키(``held:<번호>``) — 회사 지식 키와 겹치지 않는다."""
    return f"{KEY_PREFIX}{int(row_id)}"


def held_row(session: Any, key: Any) -> Optional[CsAgentLearnHeld]:
    """키 → 기다리는 줄(기다리는 것만 — 꼴이 틀리거나 이미 올림 · 버림이면 ``None``)."""
    number = key[len(KEY_PREFIX):] if isinstance(key, str) and key.startswith(KEY_PREFIX) else ""
    row = session.get(_T, int(number)) if number.isdigit() else None
    return row if row is not None and row.state == WAITING else None


def _case_order(item: str) -> tuple[int, str]:
    """근거 글 차례 — ``case:<차례>`` 는 번호 순."""
    tail = item[5:]
    return (int(tail) if tail.isdigit() else 0, item)


def merged_evidence(old: Iterable[Any], new: Iterable[Any]) -> list[str]:
    """근거 글 합치기 — ``case:`` 차례 번호 순, 그다음 ``staff:`` 따위 글자 순(같은 것은 한 번 — 제안 근거 꼴과 같다)."""
    items = list(dict.fromkeys(str(e) for e in [*old, *new] if isinstance(e, str) and e.strip()))
    cases = sorted((e for e in items if e.startswith("case:")), key=_case_order)
    return [*cases, *sorted(e for e in items if not e.startswith("case:"))]


def _keep_vector(session: Any, row: CsAgentLearnHeld, vector: Optional[list[float]], now: datetime.datetime) -> None:
    """놓을 자리 판정에 만든 벡터를 그 줄의 뜻 찾기 벡터로 남긴다(벡터 없음 · 표 없음 · 가림 검사에 걸리면 안 남김)."""
    body = f"{row.title}\n{row.text}"
    if vector is None or not safe_text(body) or not table_ready(session):
        return
    store_vector(session, SOURCE_HELD, str(row.id), None, vector, text_hash(body), now)


def hold(session: Any, *, brand: str, title: str, text: str, chats: Iterable[str], turns: Iterable[int],
         evidence: Sequence[str], now: datetime.datetime, vector: Optional[list[float]] = None) -> CsAgentLearnHeld:
    """한 상담에서만 들은 말을 기다리는 말로 모은다(모듈 설명). ``vector`` 는 놓을 자리 판정에 만든 그 글의 벡터(없으면 글자로만
    찾힌다). 커밋은 부르는 쪽."""
    at = naive_utc(now)
    row = _T(brand=brand, title=title, text=text, chat_ids=sorted({str(c) for c in chats}),
             turn_ids=sorted({int(t) for t in turns}), evidence=merged_evidence([], evidence), state=WAITING,
             first_seen=at, last_seen=at)
    session.add(row)
    session.flush()
    _keep_vector(session, row, vector, now)
    return row


def add_turns(row: CsAgentLearnHeld, *, chats: Iterable[str], turns: Iterable[int], evidence: Sequence[str],
              now: datetime.datetime) -> None:
    """같은 말이 또 나왔다 — 근거 상담 · 차례 · 근거 글을 합치고 마지막 본 때를 고친다(커밋은 부르는 쪽)."""
    row.chat_ids = sorted({*(str(c) for c in row.chat_ids or []), *(str(c) for c in chats)})
    row.turn_ids = sorted({*(int(t) for t in row.turn_ids or []), *(int(t) for t in turns)})
    row.evidence = merged_evidence(row.evidence or [], evidence)
    row.last_seen = naive_utc(now)


def finish(session: Any, row: CsAgentLearnHeld, state: str) -> None:
    """기다림을 끝낸다(``promoted`` · ``dropped``) — 그 줄의 벡터도 지운다(커밋은 부르는 쪽)."""
    if state not in (PROMOTED, DROPPED):
        raise ValueError("state")
    row.state = state
    drop_vectors(session, SOURCE_HELD, [str(row.id)])


def expire(session: Any, now: datetime.datetime) -> int:
    """:data:`EXPIRE_DAYS` 일 동안 다시 안 나온 기다리는 말을 버린다(한 번에 :data:`SCAN` 개 — 커밋은 부르는 쪽). 버린 수."""
    cutoff = naive_utc(now - datetime.timedelta(days=EXPIRE_DAYS))
    rows = list(session.execute(select(_T).where(_T.state == WAITING, _T.last_seen < cutoff)
                                .order_by(_T.last_seen).limit(SCAN)).scalars())
    for row in rows:
        row.state = DROPPED
    if rows:
        drop_vectors(session, SOURCE_HELD, [str(row.id) for row in rows])
        logger.info("[CS 넘김 학습] 기다리는 말 %d개를 %d일이 지나 버림", len(rows), EXPIRE_DAYS)
    return len(rows)


def _meaning_ids(session: Any, brand: str, vector: list[float]) -> list[int]:
    """뜻이 가까운 기다리는 말 번호(가까운 것부터 · :data:`NEAR_MEANING` 이상)."""
    on = brain_embeddings.c.source_key == cast(_T.id, String)
    ranked = nearest_rows(session, vector, source_kind=SOURCE_HELD, target=_T, on=on,
                          where=(_T.brand == brand, _T.state == WAITING), limit=MAX_NEAR)
    return [int(key) for key, score in ranked if score >= NEAR_MEANING and str(key).isdigit()]


def near(session: Any, *, brand: str, text: str, vector: Optional[list[float]] = None) -> list[dict[str, Any]]:
    """그 글과 가까운 기다리는 말(모듈 설명) — ``{"key", "title", "text"}`` 글자 쪽 먼저, 뜻 쪽이 더한 것 뒤."""
    rows = list(session.execute(select(_T).where(_T.brand == brand, _T.state == WAITING)
                                .order_by(_T.last_seen.desc(), _T.id.desc()).limit(SCAN)).scalars())
    by_id = {row.id: row for row in rows}
    scored = sorted(((text_similarity(text, row.text), row.id) for row in rows), reverse=True)
    picked = [row_id for score, row_id in scored if score >= NEAR_SIMILARITY][:MAX_NEAR]
    if vector is not None and rows and table_ready(session):
        for row_id in _meaning_ids(session, brand, vector):
            if row_id not in picked and (row_id in by_id or held_row(session, held_key(row_id)) is not None):
                picked.append(row_id)
                by_id.setdefault(row_id, session.get(_T, row_id))
    return [{"key": held_key(row_id), "title": by_id[row_id].title, "text": by_id[row_id].text} for row_id in picked]
