"""상태 표 — 수신 기록 뒤돌아 읽기 · 파생 칸 저장 · 표만으로 상태 계산 · 수신 누락 경보 · 한 상담 보정.

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C1-2 · 설계서 4절 2 · 15.2.

- **뽑기(커서 없음, 원장 R4-1 · R4-16)**: 수신 기록 표를 PK 로 뒤돌아 최근 :data:`INBOUND_LOOKBACK_ROWS` 줄만
  본다. web 이 gevent 2 프로세스라 id 를 먼저 받고 늦게 커밋한 줄이 있어 'id > 커서'는 줄을 건너뛴다. 글 표는
  (상담, 메시지 id) 고유 · 있으면 무시라서 다시 읽어도 겹치지 않는다. 15분 루프와 실시간 길(C6-1)이 같이 쓴다.
- **최소 보관**: 원본은 ``entity`` 칸만 읽어 :func:`~foms.services.cs_agent.channel_read.derive_message` 로
  파생 칸만 넣는다 — 수신 원본을 나중에 지워도(플랜 C5-1) 감시가 돈다.
- **늦게 온 옛 글**: 상담 줄의 마지막 손님 글 · 마지막 공개 직원 글은 더 새 시각일 때만, 채널톡 상태는 더 새
  ``updatedAt`` 일 때만 바뀐다(R1-7).
- **수신 누락 경보**: '채널톡엔 글이 있는데 수신 기록엔 없음'인 글 id 를 돌려준다(알림 배선은 C1-3 ``report``).
- **감시 루프용(C1-3)**: 열린 상담 상태를 상담 줄 · 글 묶음 질의로 한 번에(:func:`compute_open_states`), 한 상담
  보정은 읽기(:meth:`OpenApiReader.read_messages`)와 쓰기(:func:`apply_api_messages`)로 나눠 그 사이에 TERM 을 본다.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Mapping, Optional, Sequence

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.main.models import ChannelInboundEventLog, CsAgentChat, CsAgentMessage
from foms.services.cs_agent.channel_read import (
    MESSAGE_PAGE_LIMIT,
    ChatSnapshot,
    DerivedMessage,
    OpenApiReader,
    aware_utc,
    channel_for_brand,
    derive_message,
    naive_utc,
)
from foms.services.cs_agent.state import KST, BusinessDayFn, ChatMessage, ChatState, compute_chat_state
from foms.services.datetime_kst import now_utc_naive

logger = logging.getLogger(__name__)

__all__ = [
    "ACTIVE_WINDOW",
    "INBOUND_LOOKBACK_ROWS",
    "IngestResult",
    "ReconcileResult",
    "StoreResult",
    "apply_api_messages",
    "apply_chat_snapshots",
    "compute_open_states",
    "compute_state_from_table",
    "effective_chat_state",
    "find_missing_inbound",
    "ingest_inbound",
    "load_chat_messages",
    "reconcile_chat",
    "store_messages",
]

UTC = datetime.timezone.utc

SOURCE_WEBHOOK = "webhook"
SOURCE_OPENAPI = "openapi"

# ── 상태 표 저장 ─────────────────────────────────────────────────────────
_CHATS = CsAgentChat.__table__
_MSGS = CsAgentMessage.__table__
_LOG = ChannelInboundEventLog
_INSERT_BUILDERS: dict[str, Callable[[Any], Any]] = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}
#: 한 번에 넣는 줄 수(바인드 변수 상한 아래로).
_INSERT_CHUNK = 200


@dataclass
class StoreResult:
    """:func:`store_messages` 결과 — 새로 넣은 글 · 이미 있던 글 · 수신 줄 id 를 처음 적은 글 수."""

    inserted: int = 0
    duplicates: int = 0
    marked_inbound: int = 0


def _insert_ignore(session: Any, table: Any, rows: list[dict[str, Any]], keys: Sequence[str],
                   returning: Sequence[Any] = ()) -> list[Any]:
    """있으면 무시하고 넣기(ON CONFLICT DO NOTHING). ``returning`` 을 주면 새로 들어간 줄만 돌려준다.

    줄은 키 순서로 넣는다 — 두 루프가 겹쳐 돌아도 잠금 순서가 같아 서로 막히지 않는다.

    Raises:
        RuntimeError: PostgreSQL · SQLite 가 아닌 DB.
    """
    dialect = session.get_bind().dialect.name
    builder = _INSERT_BUILDERS.get(dialect)
    if builder is None:
        raise RuntimeError(f"있으면 무시하고 넣기를 모르는 DB: {dialect}")
    ordered = sorted(rows, key=lambda row: tuple(str(row[key]) for key in keys))
    inserted: list[Any] = []
    for start in range(0, len(ordered), _INSERT_CHUNK):
        stmt = builder(table).values(ordered[start:start + _INSERT_CHUNK])
        stmt = stmt.on_conflict_do_nothing(index_elements=list(keys))
        if returning:
            inserted.extend(session.execute(stmt.returning(*returning)).all())
        else:
            session.execute(stmt)
    return inserted


def _message_row(message: DerivedMessage, source: str, inbound_log_id: Optional[int],
                 now: datetime.datetime) -> dict[str, Any]:
    """파생 칸 → 상태 표 한 줄."""
    due = message.promise_due_at
    return {
        "chat_id": message.chat_id, "message_id": message.message_id, "brand": message.brand,
        "person_type": message.person_type, "created_at": naive_utc(message.created_at),
        "is_private": message.is_private, "is_log": message.is_log, "has_file": message.has_file,
        "is_closing": message.is_closing, "is_code_message": message.is_code_message,
        "promise_kind": message.promise_kind, "promise_due_at": naive_utc(due) if due else None,
        "promise_rule": message.promise_rule, "source": source, "inbound_log_id": inbound_log_id,
        "ingested_at": now,
    }


def _bump_chat_summary(session: Any, message: DerivedMessage, now: datetime.datetime) -> None:
    """상담 줄의 마지막 손님 글 · 마지막 공개 직원 글을 고친다 — 더 새 시각일 때만(원장 R1-7).

    한 문장(UPDATE … WHERE 더 새로움)이라 두 루프가 겹쳐도 옛 글이 새 값을 덮지 못한다.
    """
    if message.is_customer_signal:
        at_col, id_col = _CHATS.c.last_user_at, _CHATS.c.last_user_message_id
    elif message.is_answer:
        at_col, id_col = _CHATS.c.last_answer_at, _CHATS.c.last_answer_message_id
    else:
        return
    at = naive_utc(message.created_at)
    newer = or_(at_col.is_(None), at_col < at, and_(at_col == at, id_col < message.message_id))
    session.execute(update(_CHATS).where(_CHATS.c.chat_id == message.chat_id, newer)
                    .values({at_col: at, id_col: message.message_id, _CHATS.c.updated_at: now}))


def _mark_inbound(session: Any, pairs: Sequence[tuple[tuple[str, str], int]]) -> int:
    """Open API 로 먼저 넣은 글이 수신 기록에서 처음 보이면 수신 줄 id 만 적는다(누락 경보 · 다시 읽기 거름)."""
    marked = 0
    for (chat_id, message_id), log_id in pairs:
        result = session.execute(
            update(_MSGS).where(_MSGS.c.chat_id == chat_id, _MSGS.c.message_id == message_id,
                                _MSGS.c.inbound_log_id.is_(None))
            .values(inbound_log_id=log_id))
        marked += int(result.rowcount or 0)
    return marked


def store_messages(session: Any, messages: Sequence[DerivedMessage], *, source: str,
                   inbound_ids: Optional[Mapping[tuple[str, str], int]] = None,
                   now: Optional[datetime.datetime] = None) -> StoreResult:
    """파생 칸을 상태 표에 넣는다 — (상담, 메시지 id) 가 이미 있으면 무시한다. 커밋은 부르는 쪽 몫.

    새로 들어간 글만 상담 줄의 마지막 손님 글 · 마지막 공개 직원 글을 고친다(그것도 더 새 시각일 때만).
    이미 있던 글이 수신 기록에서 처음 보이면 수신 줄 id 만 적는다.

    Args:
        session: DB 세션.
        messages: :func:`derive_message` 결과.
        source: 처음 넣는 길(``webhook`` · ``openapi``).
        inbound_ids: ``{(상담, 메시지 id): 수신 기록 줄 id}`` — 웹훅 길만.
        now: 넣는 시각(UTC naive, 시험 주입).

    Returns:
        :class:`StoreResult`.
    """
    if source not in (SOURCE_WEBHOOK, SOURCE_OPENAPI):
        raise ValueError(f"모르는 길: {source!r}")
    first_seen: dict[tuple[str, str], DerivedMessage] = {}
    for message in messages:
        first_seen.setdefault((message.chat_id, message.message_id), message)
    unique = list(first_seen.values())
    if not unique:
        return StoreResult()
    now = now or now_utc_naive()
    inbound_ids = inbound_ids or {}
    chats = {m.chat_id: {"chat_id": m.chat_id, "brand": m.brand, "channel_id": m.channel_id,
                         "created_at": now, "updated_at": now} for m in unique}
    _insert_ignore(session, _CHATS, list(chats.values()), ("chat_id",))
    rows = [_message_row(m, source, inbound_ids.get((m.chat_id, m.message_id)), now) for m in unique]
    new_keys = {(row.chat_id, row.message_id) for row in _insert_ignore(
        session, _MSGS, rows, ("chat_id", "message_id"), returning=(_MSGS.c.chat_id, _MSGS.c.message_id))}
    for message in sorted((m for m in unique if (m.chat_id, m.message_id) in new_keys),
                          key=lambda m: (m.created_at, m.message_id)):
        _bump_chat_summary(session, message, now)
    old = [((m.chat_id, m.message_id), inbound_ids[(m.chat_id, m.message_id)]) for m in unique
           if (m.chat_id, m.message_id) not in new_keys and (m.chat_id, m.message_id) in inbound_ids]
    return StoreResult(inserted=len(new_keys), duplicates=len(unique) - len(new_keys),
                       marked_inbound=_mark_inbound(session, old))


# ── 수신 기록 뒤돌아 읽기 ────────────────────────────────────────────────
#: 한 번에 뒤돌아 보는 수신 기록 줄 수(R4-1 — 커서를 두지 않는다). 늦은 커밋(gevent 2 프로세스 · 초 단위)보다
#: 훨씬 넓고 재배포로 루프가 몇 분 멈춰도 메운다. 더 오래 멈춰 창을 넘친 줄은 15분 Open API 보정이 정본으로
#: 메우고, 그때 :func:`find_missing_inbound` 가 그 상담의 수신 기록을 한 번 더 읽는다. 비용은 PK 색인 훑기와
#: '이미 넣은 줄' 거르기뿐이라(원본 JSONB 는 새 줄만 연다) 몇 초마다 돌아도 작다. 거른 줄(그룹 채팅 · 모르는
#: 채널 · 같은 글의 두 번째 수신 줄)은 상태 표에 흔적이 없어 창 안에 있는 동안 다시 연다 — 5초마다 도는 빠른 길은
#: 연 줄 id(:attr:`IngestResult.examined_ids`)로 거른 줄을 기억해 ``skip_ids`` 로 넘긴다(원장 R10-4).
INBOUND_LOOKBACK_ROWS = 500


@dataclass
class IngestResult:
    """수신 기록 읽기 결과. ``examined`` 는 이번에 원본을 연 줄 수(이미 넣은 줄은 열지 않는다)."""

    examined: int = 0
    inserted: int = 0
    duplicates: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    examined_ids: list[int] = field(default_factory=list)  # 원본을 연 수신 줄 id(빠른 길이 거른 줄을 기억한다)


def _ingest_rows(session: Any, stmt: Any, now: datetime.datetime) -> IngestResult:
    """수신 줄(id · 원본)을 파생 칸으로 바꿔 넣고 커밋한다. 같은 글의 두 번째 수신 줄은 첫 줄 id 로 둔다."""
    result = IngestResult()
    derived: list[DerivedMessage] = []
    inbound_ids: dict[tuple[str, str], int] = {}
    try:
        for row in session.execute(stmt):
            result.examined += 1
            result.examined_ids.append(int(row.id))
            payload = row.raw_payload if isinstance(row.raw_payload, Mapping) else {}
            message, reason = derive_message(payload.get("entity"))
            if message is None:
                result.skipped[reason] = result.skipped.get(reason, 0) + 1
                continue
            key = (message.chat_id, message.message_id)
            if key not in inbound_ids:
                inbound_ids[key] = int(row.id)
                derived.append(message)
        stored = store_messages(session, derived, source=SOURCE_WEBHOOK, inbound_ids=inbound_ids, now=now)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    result.inserted, result.duplicates = stored.inserted, stored.duplicates
    return result


def ingest_inbound(session: Any, *, lookback: int = INBOUND_LOOKBACK_ROWS,
                   now: Optional[datetime.datetime] = None, skip_ids: Collection[int] = ()) -> IngestResult:
    """수신 기록 최근 ``lookback`` 줄을 PK 로 뒤돌아 읽어 상태 표에 넣고 커밋한다(커서 없음).

    상태 표에 수신 줄 id 가 이미 적힌 줄은 원본을 다시 열지 않는다. 늦게 커밋된 낮은 id 줄도 다음 바퀴의
    창 안에 있으면 들어간다. 확인코드 글 · 상담원 글 · 봇 글도 넣는다(답 판정은 상태 계산이 한다).

    Args:
        session: DB 세션(이 함수가 커밋한다).
        lookback: 뒤돌아 볼 줄 수.
        now: 넣는 시각(UTC naive, 시험 주입).
        skip_ids: 원본을 다시 열지 않을 수신 줄 id(빠른 길이 기억한 거른 줄 — 15분 바퀴는 넘기지 않는다).

    Returns:
        :class:`IngestResult`.
    """
    if lookback <= 0:
        raise ValueError("lookback 은 1 이상")
    ids = list(session.scalars(select(_LOG.id).order_by(_LOG.id.desc()).limit(lookback)))
    seen: set[int] = set()
    if ids:
        seen = set(session.scalars(select(_MSGS.c.inbound_log_id).where(_MSGS.c.inbound_log_id >= min(ids))))
    todo = sorted(i for i in set(ids) - seen if i not in skip_ids)
    if not todo:
        session.commit()  # 읽기 트랜잭션을 닫는다(루프가 'idle in transaction' 으로 남지 않게)
        return IngestResult()
    stmt = select(_LOG.id, _LOG.raw_payload).where(_LOG.id.in_(todo)).order_by(_LOG.id)
    result = _ingest_rows(session, stmt, now or now_utc_naive())
    if result.inserted:
        logger.info("[CS 상담] 수신 기록에서 글 %d건 넣음(원본 연 줄 %d, 거름 %s)",
                    result.inserted, result.examined, result.skipped or "-")
    return result


# ── 상태 표 → 상태 계산 ──────────────────────────────────────────────────
def _derived_from_row(row: Any) -> DerivedMessage:
    """상태 표 한 줄 → 파생 칸."""
    due = row.promise_due_at
    return DerivedMessage(
        chat_id=row.chat_id, message_id=row.message_id, channel_id=channel_for_brand(row.brand),
        brand=row.brand, person_type=row.person_type, created_at=row.created_at.replace(tzinfo=UTC),
        is_private=bool(row.is_private), is_log=bool(row.is_log), has_file=bool(row.has_file),
        is_closing=row.is_closing, is_code_message=bool(row.is_code_message),
        promise_kind=row.promise_kind, promise_due_at=due.replace(tzinfo=UTC) if due else None,
        promise_rule=row.promise_rule)


def load_chat_messages(session: Any, chat_id: str) -> list[ChatMessage]:
    """상태 표에 있는 상담 글 전부(원문 없음) — :func:`compute_chat_state` 입력."""
    rows = session.execute(select(_MSGS).where(_MSGS.c.chat_id == chat_id)).all()
    return [_derived_from_row(row).to_chat_message() for row in rows]


def effective_chat_state(chat_state: Optional[str], state_at: Optional[datetime.datetime],
                         last_user_at: Optional[datetime.datetime]) -> str:
    """상태 계산에 넘길 채널톡 상태. 모르면 열림, 닫힘으로 읽은 뒤 손님 글이 또 왔으면 다시 열린 것으로 본다."""
    state = chat_state or "opened"
    if state == "closed" and last_user_at is not None and (state_at is None or last_user_at > state_at):
        return "opened"
    return state


def compute_state_from_table(session: Any, chat_id: str, *, now: datetime.datetime,
                             is_business_day: Optional[BusinessDayFn] = None) -> Optional[ChatState]:
    """상태 표만으로 상담 상태를 낸다(수신 원본 · 원문 없이). 상담 줄이 없으면 ``None``."""
    chat = session.execute(select(_CHATS).where(_CHATS.c.chat_id == chat_id)).first()
    if chat is None:
        return None
    return compute_chat_state(
        chat_id, chat.brand, load_chat_messages(session, chat_id), now=now,
        chat_state=effective_chat_state(chat.chat_state, chat.state_at, chat.last_user_at),
        is_business_day=is_business_day)


#: 이만큼 조용한 상담은 감시에서 뺀다 — 카카오 상담은 손님 마지막 글 30일 뒤 저절로 닫힌다(설계서 2.6).
ACTIVE_WINDOW = datetime.timedelta(days=30)
#: 글을 상담 묶음으로 읽을 때 한 번에 넣는 상담 id 수(바인드 변수 상한 아래로).
_IN_CHUNK = 500


def compute_open_states(session: Any, *, now: datetime.datetime, brands: Sequence[str],
                        active_window: datetime.timedelta = ACTIVE_WINDOW,
                        is_business_day: Optional[BusinessDayFn] = None,
                        chat_ids: Optional[Sequence[str]] = None) -> list[ChatState]:
    """열린 상담 상태를 한 번에 낸다 — 상담 줄 한 질의 + 글 묶음 질의(상담마다 따로 읽지 않는다, N+1 없음).

    마지막 손님 글이나 마지막 공개 직원 글이 ``active_window`` 안인 상담만 본다. 닫힘으로 읽은 뒤 손님이 또 쓴
    상담은 열린 것으로 본다(:func:`effective_chat_state`).

    Args:
        session: DB 세션(읽기만).
        now: 지금(시간대 있는 값).
        brands: 볼 브랜드.
        active_window: 이보다 오래 조용한 상담은 뺀다.
        is_business_day: 운영일 판정(시험 주입).
        chat_ids: 이 상담만 본다(빠른 길이 고른 상담 — 주면 ``active_window`` 대신 이 목록, 500개까지).

    Returns:
        열린 상담의 :class:`ChatState` — 순서 없음(보고 순서는 ``state.sort_by_priority``).
    """
    since = naive_utc(now) - active_window
    scope = (or_(_CHATS.c.last_user_at >= since, _CHATS.c.last_answer_at >= since) if chat_ids is None
             else _CHATS.c.chat_id.in_(list(chat_ids)[:_IN_CHUNK]))
    rows = session.execute(select(_CHATS).where(_CHATS.c.brand.in_(list(brands)), scope)).all()
    chats = {row.chat_id: (row, effective_chat_state(row.chat_state, row.state_at, row.last_user_at))
             for row in rows}
    chats = {chat_id: pair for chat_id, pair in chats.items() if pair[1] != "closed"}
    messages: dict[str, list[ChatMessage]] = {chat_id: [] for chat_id in chats}
    ids = sorted(chats)
    for start in range(0, len(ids), _IN_CHUNK):
        for row in session.execute(select(_MSGS).where(_MSGS.c.chat_id.in_(ids[start:start + _IN_CHUNK]))):
            messages[row.chat_id].append(_derived_from_row(row).to_chat_message())
    return [compute_chat_state(chat_id, row.brand, messages[chat_id], now=now, chat_state=chat_state,
                               is_business_day=is_business_day)
            for chat_id, (row, chat_state) in chats.items()]


def apply_chat_snapshots(session: Any, snapshots: Sequence[ChatSnapshot], *,
                         now: Optional[datetime.datetime] = None) -> int:
    """Open API 상담 목록을 상담 줄에 반영하고 커밋한다 — 더 새로운 ``updatedAt`` 일 때만 상태를 바꾼다.

    Returns:
        상태가 바뀐 상담 수.
    """
    now = now or now_utc_naive()
    chats = {s.chat_id: {"chat_id": s.chat_id, "brand": s.brand, "channel_id": s.channel_id,
                         "created_at": now, "updated_at": now} for s in snapshots}
    changed = 0
    try:
        if chats:
            _insert_ignore(session, _CHATS, list(chats.values()), ("chat_id",))
        for snap in snapshots:
            if snap.state is None:
                continue
            values: dict[Any, Any] = {_CHATS.c.chat_state: snap.state, _CHATS.c.updated_at: now}
            newer: Any = _CHATS.c.chat_state.is_(None)
            if snap.updated_at is not None:
                at = naive_utc(snap.updated_at)
                values[_CHATS.c.state_at] = at
                newer = or_(_CHATS.c.state_at.is_(None), _CHATS.c.state_at < at)
            result = session.execute(update(_CHATS).where(_CHATS.c.chat_id == snap.chat_id, newer)
                                     .values(values))
            changed += int(result.rowcount or 0)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    return changed


# ── 수신 누락 경보 · 한 상담 보정 ────────────────────────────────────────
#: 웹훅이 아직 오는 중일 수 있는 시간 — 이보다 최근 글은 누락으로 세지 않는다.
INBOUND_GRACE = datetime.timedelta(minutes=5)
#: 운영 웹훅을 FOMS 운영 주소로 옮긴 날 — 그 전 글은 수신 기록에 없는 게 맞다(설계서 2.4). 스테이징에는
#: 웹훅이 없으니 스테이징 루프는 이 경보를 켜지 않는다(C1-3).
INBOUND_WATCH_START = datetime.datetime(2026, 10, 21, tzinfo=KST)


def _webhook_expected(message: DerivedMessage) -> bool:
    """웹훅으로 꼭 와야 하는 글 — 손님 글 · 공개 직원 글. 내부 메모 · 봇 · 기록은 오는지 아직 모른다(원장 Q1)."""
    return message.person_type in ("user", "manager") and not message.is_private and not message.is_log


def _inbound_seen(session: Any, chat_id: str) -> set[str]:
    """수신 기록에서 본 적 있는(수신 줄 id 가 적힌) 그 상담 글 id."""
    stmt = select(_MSGS.c.message_id).where(_MSGS.c.chat_id == chat_id, _MSGS.c.inbound_log_id.isnot(None))
    return set(session.scalars(stmt))


def find_missing_inbound(session: Any, chat_id: str, api_messages: Sequence[DerivedMessage], *,
                         now: datetime.datetime, grace: datetime.timedelta = INBOUND_GRACE,
                         watch_from: datetime.datetime = INBOUND_WATCH_START) -> list[str]:
    """채널톡(Open API)엔 있는데 수신 기록엔 없는 글 id — 웹훅이 빠졌다는 경보 재료(R1-1).

    상태 표에 수신 줄 id 가 없으면, 뒤돌아 읽기 창을 넘겨 못 넣은 줄일 수 있으니 그 상담의 수신 기록을
    한 번 더 읽어 넣은 뒤(커밋) 다시 본다. 알림은 보내지 않는다(C1-3 몫).

    Args:
        session: DB 세션.
        chat_id: 상담 id.
        api_messages: :meth:`OpenApiReader.read_messages` 결과.
        now: 지금(시간대 있는 값).
        grace: 이보다 최근 글은 세지 않는다.
        watch_from: 이보다 옛 글은 세지 않는다.

    Returns:
        빠진 글 id(정렬).
    """
    upper, lower = aware_utc(now) - grace, aware_utc(watch_from)
    candidates = {m.message_id for m in api_messages
                  if m.chat_id == chat_id and _webhook_expected(m) and lower <= m.created_at <= upper}
    missing = candidates - _inbound_seen(session, chat_id)
    if missing:
        seen_logs = select(_MSGS.c.inbound_log_id).where(_MSGS.c.chat_id == chat_id,
                                                         _MSGS.c.inbound_log_id.isnot(None))
        stmt = (select(_LOG.id, _LOG.raw_payload)
                .where(_LOG.source_chat_id == chat_id, _LOG.id.not_in(seen_logs)).order_by(_LOG.id))
        _ingest_rows(session, stmt, now_utc_naive())
        missing -= _inbound_seen(session, chat_id)
    return sorted(missing)


@dataclass(frozen=True)
class ReconcileResult:
    """한 상담 보정 결과 — Open API 로 새로 넣은 글 수 · 수신 기록에 없던 글 id."""

    inserted: int
    missing_inbound: list[str]


def reconcile_chat(session: Any, reader: OpenApiReader, brand: str, chat_id: str, *,
                   now: datetime.datetime, limit: int = MESSAGE_PAGE_LIMIT) -> ReconcileResult:
    """Open API(정본)로 상담 최근 글을 읽어 상태 표를 맞추고 커밋한다 — 15분 보정 · 밀린 상담 채우기의 한 상담 몫.

    웹훅이 빠뜨린 글도 여기서 상태 표에 들어가 '답 필요'가 맞게 나오고, 빠진 글 id 는 경보 재료로 돌려준다.
    읽기와 쓰기 사이에 멈춤 깃발을 두려면 :meth:`OpenApiReader.read_messages` 뒤 :func:`apply_api_messages` 를 부른다.
    """
    return apply_api_messages(session, chat_id, reader.read_messages(brand, chat_id, limit=limit), now=now)


def apply_api_messages(session: Any, chat_id: str, messages: Sequence[DerivedMessage], *,
                       now: datetime.datetime, detect_missing: bool = True) -> ReconcileResult:
    """Open API 로 이미 읽은 한 상담 글을 상태 표에 맞추고 커밋한다(쓰기 몫만 — 감시 루프는 그 앞에서 TERM 을 본다).

    Args:
        session: DB 세션(이 함수가 커밋한다).
        chat_id: 상담 id.
        messages: :meth:`OpenApiReader.read_messages` 결과.
        now: 지금(시간대 있는 값) — 수신 누락 판정의 기준.
        detect_missing: 수신 누락을 찾을지 — 웹훅이 오지 않는 환경(스테이징)은 모든 글이 '누락'이라 끈다.

    Returns:
        :class:`ReconcileResult`.
    """
    missing = find_missing_inbound(session, chat_id, messages, now=now) if detect_missing else []
    try:
        stored = store_messages(session, messages, source=SOURCE_OPENAPI)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    if missing:
        logger.warning("[CS 상담] 수신 기록에 없는 채널톡 글 %d건 chat=%s", len(missing), chat_id)
    return ReconcileResult(stored.inserted, missing)
