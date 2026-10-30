"""빠른 길 — 15분 바퀴와 따로 도는 5초 차례: 수신 기록 → 모아 받기 → 초안(선점 · 두뇌 · 검사 · 놓기) · 갈아 끼움 · 직원 답함.

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C10-1 · 설계서 17.2 · 17.3(원장 R10-1 · R10-2 · R10-4 · R10-31 · D65).
WORKER 감독자 자식 ``cs_realtime``(``scripts/maintenance/run_cs_realtime.py``)이 :data:`TICK_SECONDS` 마다 :func:`run_tick`
을 부른다. 차례 하나(순서 고정):

0. **켜짐** — 관리 화면 빠른 길 스위치(``realtime_enabled``, 처음 끔) **그리고** 초안 스위치 ``store`` · ``memo`` **그리고**
   비상 정지 아님. 하나라도 아니면 스위치만 읽고 일 0(``idle``). 켜져 있으면 15분 바퀴는 초안을 쓰지 않는다(:mod:`.loop`).
1. **따로 잠금** — :data:`REALTIME_LOCK_KEY`(15분 바퀴 대표 잠금과 다른 키). 못 잡으면 그 차례만 건너뛰고 다음 차례(5초)에
   다시 잡아 본다 — 15분 바퀴가 보정 · 아침 보고로 잠금을 몇 분 쥐어도 빠른 길은 막히지 않는다(R10-1).
2. **수신 기록 뒤돌아 읽기(C6-1 그대로)** — 커서 없음 · PK 로 최근 줄 · (상담, 메시지 id) 고유 · 확인코드 글 거름 · 시작
   신호는 손님 글만(:func:`.state_store.ingest_inbound`). 원본을 열었는데 상태 표에 흔적이 남지 않은 줄(거른 줄 · 같은 글의
   두 번째 수신 줄) id 를 :class:`TickMemory` 에 기억해 다음 차례부터 열지 않는다(크기 상한 — R10-4).
3. **죽은 선점 정리** — 만료(:data:`CLAIM_TTL`)가 지난 ``claimed`` 줄을 ``failed`` 로(시도 상한 안에서 다시 집힌다, R10-2).
   직원이 공개 답을 한 상담의 다시 집을 실패 줄은 ``staff_replied`` 로 닫는다.
4. **모아 받기** — 라홈 · 답 필요 · 맺음 글뿐 아님 · 마지막 손님 글 뒤 공개 직원 글 없음 · 묵은 상담 기준 안. 마지막 손님 글 뒤
   조용 기다림(``quiet_wait_s``, 처음 15초 — D65)이 찼거나, 첫 미답 손님 글부터 최대 기다림(``max_wait_s``)이 지났고 그 사이
   이 상담 초안이 한 번도 없었으면 집는다(R4-S1). 같은 상담의 앞 차례(올림 · 저장만)는 손님 새 글을 처음 본 차례에
   '지난 초안'(``superseded``)으로 바꾼다 — 앞 메모 지우기는 부르는 쪽이 넘기는 ``memo_remover``(기본 ``None`` = 지우지
   않음, C10-2 시험 뒤에 정한다)만 한다.
5. **초안** — :func:`.drafting.run_drafting` 의 선점 · 두뇌 · 검사 · 직전 다시 읽기 · 놓기를 그대로 쓴다. 바뀐 곳은 :class:`_RealtimePass`
   하나다: 선점 주인 ``realtime:…`` · 만료 90초 · 두뇌 시간 상한은 실시간 길(``realtime_timeout_s``) · 그사이 손님이 더 쓰면
   '지난 초안', 직원이 공개 답을 하면 '직원 답함'(초안 안 올림) · 손님이 'AI 냐 사람이냐' 물으면 두뇌 없이 초안 없음
   (:mod:`.ask_human` — 메모 스위치면 비공개 한 줄 메모, 저장만이면 기록만).

TERM: 일을 집기 전 · 쓰기 전 · 두뇌 전마다 깃발(:class:`.loop.StopFlag`)을 본다 — 깃발 뒤엔 새 두뇌를 부르지 않는다.
모델을 부르는 곳은 이 길(과 빠른 길이 꺼졌을 때의 15분 바퀴)뿐이다. 웹훅 입구 · RQ · share_consult 는 고치지 않는다.
글(손님 글 · 초안)은 로그 · 예외 · 요약에 싣지 않는다 — 상담 id · 코드 · 숫자만.
"""

from __future__ import annotations

import datetime
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import and_, or_, select

from foms.persistence.main.models import CsAgentChat, CsAgentMessage, CsAgentTurn
from foms.services.common.business_calendar import is_business_day as calendar_is_business_day
from foms.services.cs_agent.ask_human import ASK_HUMAN_MEMO, ASKED_IF_AI, any_asks_if_human
from foms.services.cs_agent.brain import check_ready, draft_reply
from foms.services.cs_agent.channel_read import OpenApiReader, naive_utc
from foms.services.cs_agent.drafting import BRAND, _candidates, _Pass, _reclaimable, run_drafting
from foms.services.cs_agent.drafting_post import memo_on, post_note
from foms.services.cs_agent.drafting_read import SKIP_HUMAN_REPLIED, SKIP_STALE, ChatLine
from foms.services.cs_agent.drafting_summary import DraftSummary
from foms.services.cs_agent.loop import PassStopped, StopFlag, leader_lock
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.memo import memo_allowed, post_private_memo
from foms.services.cs_agent.settings import PanelSettings, read_settings
from foms.services.cs_agent.state import KST, BusinessDayFn
from foms.services.cs_agent.state_store import INBOUND_LOOKBACK_ROWS, compute_open_states, ingest_inbound
from foms.services.cs_agent.turns import (
    DRAFT_MEMO, DRAFT_STORE, MAX_ATTEMPTS, STATE_CLAIMED, STATE_FAILED, STATE_POSTED, STATE_POSTING, STATE_STORED,
    TurnStateError, draft_mode, expired_claims, mark_failed, mark_staff_replied, mark_superseded, read_switch,
    record_handoff,
)
from foms.services.datetime_kst import now_kst

logger = logging.getLogger(__name__)

__all__ = [
    "CLAIM_TTL", "REALTIME_LOCK_KEY", "TICK_SECONDS", "TickMemory", "TickResult", "run_tick",
]

UTC = datetime.timezone.utc
#: 빠른 길 대표 잠금 — 15분 바퀴(``loop.LEADER_LOCK_KEY``)와 다른 키다(R10-1).
REALTIME_LOCK_KEY = "foms:cs_agent_realtime"
TICK_SECONDS = 5.0
#: 선점 만료 — 시간 상한(처음 45초, 패널 20~60) + 읽기 · 검사 · 메모 여유(R10-2). 지나면 죽은 선점이다.
CLAIM_TTL = datetime.timedelta(seconds=90)
#: 한 차례에서 새로 집기를 그만두는 시간(선점 전에 본다) — 남은 상담은 다음 차례가 잇는다.
TICK_BUDGET_SECONDS = 60.0
#: 마지막 손님 글이 이 안인 미답 상담만 본다(묵은 상담 기준은 따로 운영일로 거른다 — 긴 연휴를 덮는 넓이).
CANDIDATE_WINDOW = datetime.timedelta(days=7)
MAX_CANDIDATES = 500
#: '다시 볼 필요 없음' 판정은 마지막 손님 글이 이만큼 지난 뒤에만 기억한다(늦게 커밋된 앞 글이 들어올 틈).
DECIDE_AFTER = datetime.timedelta(seconds=60)
#: 프로세스 메모리 상한 — 거른 줄 · 판정 각각(뒤돌아 읽기 창 500줄의 네 배). 넘으면 오래된 것부터 버린다.
MEMORY_LIMIT = 4 * INBOUND_LOOKBACK_ROWS
FAIL_CLAIM_EXPIRED = "claim_expired"
OUTCOME_OK, OUTCOME_IDLE, OUTCOME_NOT_LEADER, OUTCOME_STOPPED = "ok", "idle", "not_leader", "stopped"
_FINAL = frozenset({STATE_POSTED, STATE_STORED})  # 갈아 끼울 수 있는 끝난 차례(올림 · 저장만)


# ── 프로세스 메모리 ──────────────────────────────────────────────────────
class _Bounded(OrderedDict):
    """크기 상한이 있는 집합(넣은 순서 — 넘치면 가장 먼저 넣은 것부터 버린다)."""

    def __init__(self, limit: int) -> None:
        """상한을 정한다."""
        super().__init__()
        self.limit = int(limit)

    def add(self, key: Any) -> None:
        """하나 넣는다(있으면 맨 뒤로)."""
        self[key] = None
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


class TickMemory:
    """차례 사이에 남기는 프로세스 메모리 — 거른 수신 줄 id · '다시 볼 필요 없는' (상담, 손님 글) 판정. 둘 다 크기 상한.

    판정은 관리 화면 설정 판(version)이 바뀌면 지운다(묵은 상담 기준 같은 값이 바뀌면 다시 본다). 재시작하면 비어서 시작한다 —
    그때는 한 번씩 더 열 뿐이다.
    """

    def __init__(self, limit: int = MEMORY_LIMIT) -> None:
        """빈 메모리."""
        self.filtered = _Bounded(limit)
        self.decided = _Bounded(limit)
        self.settings_version: Optional[int] = None

    def forget_decisions_if_changed(self, version: int) -> None:
        """설정 판이 바뀌었으면 판정을 지운다."""
        if self.settings_version != version:
            self.decided.clear()
            self.settings_version = version


# ── 결과 ─────────────────────────────────────────────────────────────────
@dataclass
class TickResult:
    """한 차례 결과 — 숫자 · 코드만(상담 id · 글 없음)."""

    outcome: str
    ingested: int = 0
    examined: int = 0  # 원본을 연 수신 줄
    filtered: int = 0  # 새로 기억한 거른 줄
    expired: int = 0  # 만료가 지나 실패로 돌린 선점
    staff_replied: int = 0  # 직원 답이 와 닫은 실패 줄
    superseded: int = 0  # 손님이 더 써서 '지난 초안'으로 바꾼 끝난 차례
    pending: int = 0  # 조용 기다림 · 최대 기다림 전이라 아직 안 집은 상담
    picked: int = 0
    too_old: int = 0
    drafting: Optional[DraftSummary] = None

    def summary(self) -> dict[str, Any]:
        """JSON 한 덩어리 — 초안을 돈 차례만 ``drafting`` 칸이 붙는다."""
        out = {key: getattr(self, key) for key in ("outcome", "ingested", "examined", "filtered", "expired",
                                                   "staff_replied", "superseded", "pending", "picked", "too_old")}
        if self.drafting is not None:
            out["drafting"] = self.drafting.counts()
        return out


# ── 차례 하나 ────────────────────────────────────────────────────────────
def run_tick(session: Any, *, memory: TickMemory, stop: Optional[StopFlag] = None, reader: Optional[Any] = None,
             now: Optional[datetime.datetime] = None, clock: Callable[[], float] = time.monotonic,
             is_business_day: Optional[BusinessDayFn] = None, brain: Callable[..., Any] = draft_reply,
             poster: Callable[..., Any] = post_private_memo, ready: Callable[..., Any] = check_ready,
             memo_remover: Optional[Callable[[str, str], Any]] = None,
             lock_key: str = REALTIME_LOCK_KEY) -> TickResult:
    """빠른 길 한 차례(모듈 설명의 순서). 꺼진 차례 · 대표가 아닌 차례 · 멈춘 차례는 일 0.

    Args:
        session: DB 세션(이 함수 · 두뇌가 커밋한다).
        memory: 차례 사이에 남기는 프로세스 메모리(러너가 하나 만들어 계속 넘긴다).
        stop: TERM 깃발(없으면 내린 깃발).
        reader: 채널톡 읽기 도우미(없으면 집을 상담이 있을 때 기본 — 기다림이 깃발을 본다).
        now: 지금(시간대 있는 값, 시험 주입). clock: 시간 상한 시계(단조, 시험 주입).
        is_business_day: 운영일 판정(시험 주입). brain · poster · ready: 두뇌 · 메모 감싸개 · 두뇌 준비 확인(시험은 가짜).
        memo_remover: 갈아 끼운 차례의 앞 메모를 지우는 함수 ``(상담 id, 메모 id)`` — 기본 ``None`` 은 지우지 않는다(C10-2).
        lock_key: 대표 잠금 키(시험이 15분 바퀴 키를 넘겨 음성 대조한다).

    Returns:
        :class:`TickResult`.

    Raises:
        SQLAlchemyError: DB 오류 — 러너가 기록하고 다음 차례로 간다.
    """
    stop = stop or StopFlag()
    now = (now or now_kst()).astimezone(KST)
    if stop.is_set():
        return TickResult(OUTCOME_STOPPED)
    cfg = read_settings(session, log=False)
    mode, running = draft_mode(session), read_switch(session)
    session.commit()  # 읽기 트랜잭션을 닫는다
    if not (cfg.get("realtime_enabled") and running and mode in (DRAFT_STORE, DRAFT_MEMO)):
        return TickResult(OUTCOME_IDLE)
    with leader_lock(session.get_bind(), lock_key) as leader:
        if not leader:
            return TickResult(OUTCOME_NOT_LEADER)
        result = TickResult(OUTCOME_OK)
        try:
            cal = is_business_day or calendar_is_business_day
            picks = _prepare(session, result, memory=memory, cfg=cfg, now=now, stop=stop, cal=cal,
                             memo_remover=memo_remover)
            if picks:
                result.drafting = DraftSummary()
                run_drafting(session, states=(), reader=reader or OpenApiReader(sleep=stop.reader_sleep), now=now,
                             stop=stop, mode=mode, is_business_day=cal, brain=brain, poster=poster, clock=clock,
                             budget_seconds=TICK_BUDGET_SECONDS, ready=ready, summary=result.drafting, picks=picks,
                             pass_type=_RealtimePass)
        except PassStopped:
            session.rollback()
            result.outcome = OUTCOME_STOPPED
        return result


def _prepare(session: Any, result: TickResult, *, memory: TickMemory, cfg: PanelSettings, now: datetime.datetime,
             stop: StopFlag, cal: BusinessDayFn, memo_remover: Optional[Callable[[str, str], Any]]) -> list[tuple[str, str]]:
    """수신 기록 → 죽은 선점 · 직원 답 정리 → 모아 받기. 집을 (상담, 손님 글 id) 목록(우선순위 순)을 돌려준다."""
    stop.check()
    _ingest(session, result, memory, now)
    _expire_claims(session, result, now, stop)
    _close_answered(session, result, now, stop)
    memory.forget_decisions_if_changed(cfg.version)
    return _pick(session, result, memory=memory, cfg=cfg, now=now, stop=stop, cal=cal, memo_remover=memo_remover)


# ── 2 · 3: 수신 기록 · 정리 ──────────────────────────────────────────────
def _ingest(session: Any, result: TickResult, memory: TickMemory, now: datetime.datetime) -> None:
    """수신 기록을 넣고, 원본을 열었는데 상태 표에 수신 줄 id 가 안 남은 줄(거른 줄)을 기억한다(R10-4)."""
    ingested = ingest_inbound(session, lookback=INBOUND_LOOKBACK_ROWS, now=naive_utc(now), skip_ids=memory.filtered)
    result.ingested, result.examined = ingested.inserted, ingested.examined
    if not ingested.examined_ids:
        return
    stmt = select(CsAgentMessage.inbound_log_id).where(CsAgentMessage.inbound_log_id.in_(ingested.examined_ids))
    recorded = set(session.scalars(stmt))
    session.commit()
    for log_id in ingested.examined_ids:
        if log_id not in recorded:
            memory.filtered.add(log_id)
            result.filtered += 1


def _expire_claims(session: Any, result: TickResult, now: datetime.datetime, stop: StopFlag) -> None:
    """만료가 지난 선점 → 실패(시도 상한 안에서 다시 집힌다). 살아 있던 주인은 조건부 쓰기가 0 줄이라 올리지 않는다."""
    rows = expired_claims(session, now)
    session.commit()
    for row in rows:
        stop.check()  # 쓰기 전
        _write_one(session, lambda: mark_failed(row, error_code=FAIL_CLAIM_EXPIRED, now=now), result, "expired")
    if result.expired:
        logger.warning("[CS 빠른 길] 만료가 지난 선점 %d건을 실패로 돌렸다(다시 집음)", result.expired)


def _close_answered(session: Any, result: TickResult, now: datetime.datetime, stop: StopFlag) -> None:
    """직원이 공개 답을 한 상담의 아직 안 끝난(다시 집을) 실패 줄 → '직원 답함'(초안 안 올림)."""
    stmt = (select(CsAgentTurn)
            .join(CsAgentChat, CsAgentChat.chat_id == CsAgentTurn.chat_id)
            .join(CsAgentMessage, and_(CsAgentMessage.chat_id == CsAgentTurn.chat_id,
                                       CsAgentMessage.message_id == CsAgentTurn.last_user_message_id))
            .where(CsAgentTurn.state == STATE_FAILED, CsAgentTurn.attempts < MAX_ATTEMPTS,
                   CsAgentTurn.updated_at >= naive_utc(now) - CANDIDATE_WINDOW,
                   CsAgentChat.last_answer_at.isnot(None), CsAgentChat.last_answer_at > CsAgentMessage.created_at)
            .limit(100).execution_options(populate_existing=True))
    rows = list(session.scalars(stmt))
    session.commit()
    for row in rows:
        stop.check()  # 쓰기 전
        _write_one(session, lambda: mark_staff_replied(row, now=now), result, "staff_replied")


def _write_one(session: Any, write: Callable[[], Any], result: TickResult, counter: str) -> bool:
    """줄 하나 쓰고 커밋 — 그사이 다른 쪽이 그 줄을 바꿨으면(조건부 쓰기 0 줄) 손대지 않고 넘어간다."""
    try:
        write()
    except TurnStateError:
        session.rollback()
        return False
    session.commit()
    setattr(result, counter, getattr(result, counter) + 1)
    return True


# ── 4: 모아 받기 ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _TurnRow:
    """상담의 차례 줄 하나(고르기 재료) — 상태 · 손님 글 시각만."""

    id: int
    message_id: str
    state: str
    attempts: int
    error_code: Optional[str]
    memo_message_id: Optional[str]
    message_at: Optional[datetime.datetime]  # 그 차례를 연 손님 글 시각(UTC naive)


def _unanswered_chats(session: Any, now: datetime.datetime) -> list[Any]:
    """라홈 · 마지막 손님 글이 창 안 · 그 뒤 공개 직원 글 없음인 상담 줄(마지막 손님 글이 오래된 것부터)."""
    stmt = (select(CsAgentChat.chat_id, CsAgentChat.last_user_message_id, CsAgentChat.last_user_at,
                   CsAgentChat.last_answer_at)
            .where(CsAgentChat.brand == BRAND, CsAgentChat.last_user_message_id.isnot(None),
                   CsAgentChat.last_user_at >= naive_utc(now) - CANDIDATE_WINDOW,
                   or_(CsAgentChat.last_answer_at.is_(None), CsAgentChat.last_answer_at < CsAgentChat.last_user_at))
            .order_by(CsAgentChat.last_user_at, CsAgentChat.chat_id).limit(MAX_CANDIDATES))
    return list(session.execute(stmt))


def _turns_of(session: Any, chat_ids: Sequence[str]) -> dict[str, list[_TurnRow]]:
    """상담마다 차례 줄(그 차례를 연 손님 글 시각과 함께) — 한 질의."""
    stmt = (select(CsAgentTurn.chat_id, CsAgentTurn.id, CsAgentTurn.last_user_message_id, CsAgentTurn.state,
                   CsAgentTurn.attempts, CsAgentTurn.error_code, CsAgentTurn.memo_message_id, CsAgentMessage.created_at)
            .outerjoin(CsAgentMessage, and_(CsAgentMessage.chat_id == CsAgentTurn.chat_id,
                                            CsAgentMessage.message_id == CsAgentTurn.last_user_message_id))
            .where(CsAgentTurn.chat_id.in_(list(chat_ids))))
    out: dict[str, list[_TurnRow]] = {}
    for row in session.execute(stmt):
        out.setdefault(row.chat_id, []).append(_TurnRow(row.id, row.last_user_message_id, row.state,
                                                        int(row.attempts or 0), row.error_code, row.memo_message_id,
                                                        row.created_at))
    return out


def _pick(session: Any, result: TickResult, *, memory: TickMemory, cfg: PanelSettings, now: datetime.datetime,
          stop: StopFlag, cal: BusinessDayFn, memo_remover: Optional[Callable[[str, str], Any]]) -> list[tuple[str, str]]:
    """모아 받기 — 새로 볼 상담만 고르고(판정 기억), 앞 차례를 갈아 끼운 뒤, 조용 · 최대 기다림이 찬 상담만 돌려준다."""
    chats = {row.chat_id: row for row in _unanswered_chats(session, now)
             if (row.chat_id, row.last_user_message_id) not in memory.decided}
    if not chats:
        session.commit()
        return []
    turns = _turns_of(session, list(chats))
    session.commit()
    _supersede(session, result, chats, turns, now=now, stop=stop, memo_remover=memo_remover)
    open_ids = [chat_id for chat_id, row in chats.items() if _still_open(row, turns.get(chat_id, ()), memory, now)]
    states = compute_open_states(session, now=now, brands=(BRAND,), is_business_day=cal,
                                 chat_ids=open_ids) if open_ids else []
    picked, result.too_old = _candidates(session, states, now=now, is_business_day=cal,
                                         max_wait_days=cfg.get("max_wait_business_days"))
    session.commit()
    chosen = {chat_id for chat_id, _ in picked}
    for chat_id in open_ids:  # 답 필요가 아님 · 맺음 글뿐 · 닫힘 · 너무 묵음 — 손님이 새로 쓰기 전엔 그대로다
        if chat_id not in chosen:
            _decide(memory, chats[chat_id], now)
    waiting = {state.chat_id: state.waiting_since for state in states}
    out = [pair for pair in picked if _ready(chats[pair[0]], waiting.get(pair[0]), turns.get(pair[0], ()), cfg, now)]
    result.pending, result.picked = len(picked) - len(out), len(out)
    return out


def _decide(memory: TickMemory, row: Any, now: datetime.datetime) -> None:
    """(상담, 손님 글)을 '다시 볼 필요 없음'으로 기억한다 — 마지막 손님 글이 :data:`DECIDE_AFTER` 지난 뒤에만."""
    if naive_utc(now) - row.last_user_at >= DECIDE_AFTER:
        memory.decided.add((row.chat_id, row.last_user_message_id))


def _still_open(row: Any, turns: Iterable[_TurnRow], memory: TickMemory, now: datetime.datetime) -> bool:
    """이 손님 글의 차례가 없거나 다시 집을 수 있는 실패 줄이면 참. 끝난 차례면 판정을 기억한다(손님 글 하나에 초안 하나)."""
    current = next((turn for turn in turns if turn.message_id == row.last_user_message_id), None)
    if current is None or _reclaimable(current):
        return True
    if current.state not in (STATE_CLAIMED, STATE_POSTING):  # 일하는 중 · 올리는 중은 다음 차례에 다시 본다
        _decide(memory, row, now)
    return False


def _ready(row: Any, waiting_since: Optional[datetime.datetime], turns: Iterable[_TurnRow], cfg: PanelSettings,
           now: datetime.datetime) -> bool:
    """모아 받기 — 마지막 손님 글 뒤 조용 기다림이 찼거나, 첫 미답 글부터 최대 기다림이 지났고 이 묶음 초안이 아직 없음."""
    at = naive_utc(now)
    if (at - row.last_user_at).total_seconds() >= int(cfg.get("quiet_wait_s")):
        return True
    if waiting_since is None:
        return False
    first = naive_utc(waiting_since)
    drafted = any(turn.message_at is not None and turn.message_at >= first for turn in turns)
    return not drafted and (at - first).total_seconds() >= int(cfg.get("max_wait_s"))


def _supersede(session: Any, result: TickResult, chats: dict[str, Any], turns: dict[str, list[_TurnRow]], *,
               now: datetime.datetime, stop: StopFlag, memo_remover: Optional[Callable[[str, str], Any]]) -> None:
    """손님이 새로 쓴 상담의 앞 차례(같은 미답 묶음의 올림 · 저장만)를 '지난 초안'으로 — 직원 답 앞 차례는 그대로 둔다."""
    for chat_id, chat in chats.items():
        for turn in turns.get(chat_id, ()):
            if turn.message_id == chat.last_user_message_id or turn.state not in _FINAL:
                continue
            if chat.last_answer_at is not None and (turn.message_at is None or turn.message_at <= chat.last_answer_at):
                continue
            stop.check()  # 쓰기 전
            row = session.get(CsAgentTurn, turn.id, populate_existing=True)
            if row is None or not _write_one(session, lambda: mark_superseded(row, now=now), result, "superseded"):
                continue
            logger.info("[CS 빠른 길] 손님이 더 써서 앞 차례를 지난 초안으로 chat=%s turn=%s", chat_id, turn.id)
            if memo_remover is not None and turn.memo_message_id:  # 차례는 이미 '지난 초안'으로 커밋했다
                memo_remover(chat_id, turn.memo_message_id)


# ── 5: 초안 차례 꼴(빠른 길만 다른 곳) ───────────────────────────────────
class _RealtimePass(_Pass):
    """빠른 길의 차례 꼴 — 선점 주인 · 만료 · 실시간 시간 상한 · 갈아 끼움 · 직원 답함 · 'AI 냐' 물음(나머지는 15분 바퀴 그대로)."""

    realtime, owner_kind, claim_ttl = True, "realtime", CLAIM_TTL

    def skip(self, row: CsAgentTurn, code: str, *, codes: Sequence[Any] = (), masked: Optional[str] = None,
             halt: Optional[str] = None) -> Optional[str]:
        """그사이 손님이 더 썼으면 '지난 초안', 직원이 공개 답을 했으면 '직원 답함'으로 닫는다. 나머지는 건너뜀 그대로."""
        if code not in (SKIP_STALE, SKIP_HUMAN_REPLIED):
            return super().skip(row, code, codes=codes, masked=masked, halt=halt)
        self.stop.check()  # 쓰기 전
        chat_id = row.chat_id
        try:
            self._close(row, code, masked, codes)
        except MaskLeak:
            self._close(row, code, None, ())
        self.session.commit()
        counter = "superseded" if code == SKIP_STALE else "staff_replied"
        setattr(self.summary, counter, getattr(self.summary, counter) + 1)
        logger.info("[CS 빠른 길] 차례를 닫음 chat=%s state=%s", chat_id, counter)
        return halt

    def _close(self, row: CsAgentTurn, code: str, masked: Optional[str], codes: Sequence[Any]) -> None:
        """닫는 쓰기 한 번 — 만든 초안이 있으면 가린 사본을 같이 남긴다."""
        if code == SKIP_STALE:
            mark_superseded(row, masked_draft=masked, check_codes=codes, now=self.now)
        else:
            mark_staff_replied(row, masked_draft=masked, now=self.now)

    def asks_human(self, lines: Sequence[ChatLine]) -> bool:
        """마지막 공개 직원 글 뒤 손님 글 가운데 'AI 냐 사람이냐' 물음이 있나(:mod:`.ask_human`)."""
        after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
        return any_asks_if_human(line.text for line in lines[after + 1:] if line.meta.is_customer_signal)

    def hand_to_human(self, row: CsAgentTurn, chat_id: str) -> Optional[str]:
        """두뇌 없이 사람에게 — 넘김 까닭을 적고, 메모 스위치면 비공개 한 줄 메모, 저장만이면 기록만(건너뜀). 멈출 까닭."""
        self.stop.check()  # 쓰기 전
        record_handoff(row, reason=ASKED_IF_AI)
        self.summary.asked_human += 1
        logger.info("[CS 빠른 길] 손님이 'AI 냐 사람이냐' 물어 두뇌 없이 사람에게 chat=%s", chat_id)
        if memo_on(self) and memo_allowed(chat_id):
            return post_note(self, row, chat_id, text=ASK_HUMAN_MEMO)
        return super().skip(row, ASKED_IF_AI)

