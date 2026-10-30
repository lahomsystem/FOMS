"""사례 기억(L0) — 직원이 데스크에서 직접 보낸 답을 그 차례 줄에 붙이고, 다음 초안 재료로 같은 브랜드 비슷한 사례를 고른다.

설계서 17.2('1주차는 버튼 없이 학습부터' · '사례 기억' · '되먹임 막기' · '직원 정보') · 17.5(사례는 관찰 — 정체성과 분리) ·
17.6 L0, 플랜 C10-4(원장 S10-1 · S10-2 · R10-5 · R10-28). 표는 차례 줄 ``models.CsAgentTurn``(마이그레이션 ``csagent_03``) —
새 표가 없고 보관 기간도 줄과 같다. 채널톡은 GET 만(:func:`.drafting_read.read_lines` — 읽기 도우미 · 공유 양동이 그대로).

**1. 직원 직접 답 붙이기**(:func:`attach_staff_replies` — 초안을 쓰는 쪽이 부른다: 빠른 길이 돌면 빠른 길, 아니면 15분 바퀴.
순서 고정):

1. **DB 만으로 고르기** — 끝난 차례(:data:`REPLY_STATES` — 올림 · 저장만 · 건너뜀 · 직원 답함)인데 사례가 아직 없고
   (``outcome`` 비어 있음), 그 차례 손님 글 **뒤** · 다음 손님 글 **전**에 공개 직원 글이 있는 차례. 어느 차례 줄의 '보낸 글
   id'(``sent_message_id`` — 2주차 [보내기]로 우리가 보낸 글이 웹훅 · Open API 로 돌아온 것)와 같은 글은 직원 글로 세지 않는다
   (되먹임 막기 — R10-5). 다음 손님 글이 왔거나 마지막 직원 글 뒤 :data:`REPLY_SETTLE` 이 지나야 집는다(직원은 답을 여러
   말풍선으로 나눠 보낸다). '지난 초안'은 고르지 않는다 — 그 차례 직원 답은 갈아 끼운 새 차례 몫이다.
2. **상담마다 한 번 읽기** — 원문은 이 바퀴 메모리에만 둔다. 그 손님 글 뒤 · 다음 손님 글 전의 공개 직원 글(보낸 글 id 뺌)을
   모은다. 바퀴마다 읽기 수 · 시간 · 살펴볼 차례 수 상한(:data:`TICK_LIMITS` · :data:`PASS_LIMITS`)이 있다 — 채널톡 양동이를
   많이 쓰지 않게.
3. **복사 판정** — 가린 직원 답이 그 묶음 AI 초안(가린 초안 — 지우지 못한 앞 메모 포함) 가운데 하나와 :data:`COPY_SIMILARITY`
   이상 같으면 '복사'(학습 무게 0 — 다음 초안 재료에서 뺀다, AI 글이 사람 정답으로 학습되지 않게). 아니면 '직접 답' + 고친 정도.
4. **적기** — :func:`.turns.record_staff_reply`(사례가 비어 있을 때만 쓰는 조건부 쓰기). 직원 답이 가림 검사를 못 넘으면 글 칸을
   비우고 코드만(끝난 꼴 · 상담원 id) 남긴다. 같은 줄에 가린 손님 질문(그 차례 손님 글 — 가림 검사를 넘은 글만)도 적는다.

**2. 다음 초안 재료**(:func:`similar_cases` — 초안 차례가 두뇌를 부르기 전에): 같은 브랜드 · 끝난 꼴이 그대로 · 고침 · 직접 답
(복사 · 버림 · 시험용 떼어 둠 제외)인 사례 가운데 가린 손님 질문이 지금 손님 글과 비슷한 것 :data:`~.brain_cases.MAX_CASES`
개까지. PostgreSQL 은 pg_trgm(``%`` 로 GIN 색인을 타고 ``similarity`` 순), SQLite 시험 레인은 같은 셈의 파이썬 대체
(:func:`trigram_similarity`). 사례 글은 가림 검사를 다시 넘은 것만 · 허용 목록에는 넣지 않는다(다른 손님 금액 · 날짜를 새 초안에
옮기면 보내기 전 검사가 막는다).

직원 정보(R10-28): 보낸 직원 번호 · 상담원 id 는 ADMIN 만 본다(DB 칸뿐 — 보여 주는 화면 없음), 직원별 모아 보기 · 집계는
만들지 않는다(원장 Q20 — 근무 감시 고지 확인 전). 직원 이름 · 글 ·
손님 글은 로그 · 요약 · 예외에 싣지 않는다(상담 id · 차례 id · 코드 · 숫자만).
"""

from __future__ import annotations

import datetime
import difflib
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import and_, func, select, text

from foms.persistence.main.models import CsAgentChat, CsAgentMessage, CsAgentTurn
from foms.services.cs_agent.brain_cases import MAX_CASES
from foms.services.cs_agent.channel_read import ChannelRateLimited, ChannelReadError, OpenApiReader, naive_utc
from foms.services.cs_agent.drafting_read import FILE_NOTE, ChatLine, read_lines
from foms.services.cs_agent.masking import MaskLeak, leak_counts, mask
from foms.services.cs_agent.turns import (
    STATE_POSTED, STATE_SKIPPED, STATE_STAFF_REPLIED, STATE_STORED, TurnStateError, record_staff_reply,
)

logger = logging.getLogger(__name__)

__all__ = [
    "CASE_MIN_SIMILARITY", "COPY_SIMILARITY", "EDIT_REASONS", "LEARNING_OUTCOMES", "OUTCOMES", "PASS_LIMITS",
    "REPLY_SETTLE", "REPLY_STATES", "TICK_LIMITS", "AttachLimits", "AttachSummary", "attach_staff_replies",
    "current_question", "judge_reply", "similar_cases", "text_similarity", "trigram_similarity",
]

# ── 꼴 ───────────────────────────────────────────────────────────────────
OUTCOME_AS_IS, OUTCOME_EDITED, OUTCOME_DIRECT = "as_is", "edited", "direct"  # 그대로 · 고침 · 직접 답
OUTCOME_COPIED, OUTCOME_DISCARDED = "copied", "discarded"  # 복사(학습 무게 0) · 버림
#: 끝난 꼴 — 마이그레이션 ``csagent_03`` · 모델 검사 제약과 같은 순서 · 글자(시험이 맞춘다).
OUTCOMES: tuple[str, ...] = (OUTCOME_AS_IS, OUTCOME_EDITED, OUTCOME_DIRECT, OUTCOME_COPIED, OUTCOME_DISCARDED)
#: 고친 까닭(틀린 사실 · 약속 · 말투 · 빠짐 · 기타) — 2주차 [수정하기] 화면(C10-3)이 채운다.
EDIT_REASONS: tuple[str, ...] = ("wrong_fact", "promise", "tone", "missing", "other")
#: 다음 초안 재료가 되는 끝난 꼴 — 복사 · 버림은 빼고, 시험용 떼어 둔 줄도 뺀다.
LEARNING_OUTCOMES: tuple[str, ...] = (OUTCOME_AS_IS, OUTCOME_EDITED, OUTCOME_DIRECT)
#: 직원 답을 붙일 수 있는 끝난 차례(:func:`.turns.record_staff_reply` 가 받는 상태와 같다).
REPLY_STATES: tuple[str, ...] = (STATE_POSTED, STATE_STORED, STATE_SKIPPED, STATE_STAFF_REPLIED)

# ── 기준 숫자(시험이 고정한다) ───────────────────────────────────────────
#: 가린 직원 답 ↔ 가린 AI 초안 글자 비슷함(0~1)이 이 이상이면 '복사'. 끝 인사 · 문장 부호만 바꾼 복사를 잡고, 문장 하나를 고친
#: 답은 '직접 답'으로 남는 값(시험의 음성 대조군).
COPY_SIMILARITY = 0.9
#: 비슷한 사례로 보는 가장 낮은 trgm 비슷함 — 한국어 짧은 문의는 같은 뜻이어도 0.2~0.3 이라 pg_trgm 처음 값(0.3)보다 낮춘다.
CASE_MIN_SIMILARITY = 0.2
CASE_TEXT_LIMIT = 500  # 두뇌에 싣는 사례 글 하나의 글자 상한
QUERY_TEXT_LIMIT = 1000  # 비슷함을 재는 지금 손님 글의 글자 상한
CASE_POOL = 2000  # SQLite 레인이 비슷함을 재는 최근 사례 수
SIMILARITY_TEXT_LIMIT = 4000  # 글자 비슷함을 재는 글 길이 상한(셈 시간 상한)
#: 마지막 직원 글 뒤 이만큼 조용하면(또는 다음 손님 글이 오면) 직원 답이 끝난 것으로 본다.
REPLY_SETTLE = datetime.timedelta(seconds=120)
#: 이 안에 바뀐 차례만 본다(긴 연휴를 덮는 넓이 — 빠른 길 고르기 창과 같다).
ATTACH_WINDOW = datetime.timedelta(days=7)
_CHUNK = 500
HALT_READS, HALT_TIME, HALT_RATE_LIMITED, HALT_READ_FAILED = "read_cap", "time_budget", "rate_limited", "read_failed"
NO_ANCHOR, NO_REPLY_TEXT, DELETED_CHAT = "anchor_missing", "reply_missing", "chat_not_found"


@dataclass(frozen=True)
class AttachLimits:
    """한 바퀴 사례 붙이기 상한 — 상담 글 읽기 수 · 시간(초, 읽기 전에 본다) · DB 로 살펴볼 차례 수(새 차례부터).

    살펴볼 차례 수 상한은 새 차례부터 센다 — 창이 직원 답 없이 닫힌 옛 차례(사진만 보내 건너뛴 뒤 손님이 이어 쓴 차례 등 —
    직원 답은 뒤 차례 몫)가 창(:data:`ATTACH_WINDOW`) 동안 남아 있어도 새 차례를 밀어내지 않게.
    """

    max_reads: int
    seconds: float
    max_pending: int


TICK_LIMITS = AttachLimits(max_reads=2, seconds=5.0, max_pending=50)  # 빠른 길 5초 차례
PASS_LIMITS = AttachLimits(max_reads=20, seconds=30.0, max_pending=200)  # 15분 바퀴


@dataclass
class AttachSummary:
    """한 바퀴 결과 — 숫자 · 코드만(상담 id · 글 · 직원 정보 없음)."""

    pending: int = 0  # 사례가 없는 끝난 차례 가운데 그 뒤 직원 글이 온 것
    ready: int = 0  # 그중 직원 답이 끝난 것(다음 손님 글 · 조용 기다림)
    reads: int = 0
    direct: int = 0
    copied: int = 0
    no_text: int = 0  # 글 없이 코드만 남긴 사례(가림 검사 · 글을 못 찾음 · 지워진 상담)
    conflicts: int = 0  # 그사이 다른 쪽이 그 줄을 바꿈
    halted: Optional[str] = None

    def counts(self) -> dict[str, Any]:
        """JSON 한 덩어리."""
        return {key: getattr(self, key) for key in ("pending", "ready", "reads", "direct", "copied", "no_text",
                                                    "conflicts", "halted")}


# ── 비슷함 ───────────────────────────────────────────────────────────────
_WORD = re.compile(r"[^\W_]+")


def _trigrams(value: str) -> set[str]:
    """pg_trgm 과 같은 셈의 세 글자 묶음 — 소문자 · 글자 · 숫자 낱말마다 앞 빈칸 둘 · 뒤 빈칸 하나를 붙인다."""
    out: set[str] = set()
    for word in _WORD.findall(value.lower()):
        padded = f"  {word} "
        out.update(padded[i:i + 3] for i in range(len(padded) - 2))
    return out


def trigram_similarity(left: str, right: str) -> float:
    """pg_trgm ``similarity`` 의 파이썬 대체 — 겹친 세 글자 묶음 수 ÷ 합친 묶음 수(0~1). 묶음이 없으면 0."""
    a, b = _trigrams(left or ""), _trigrams(right or "")
    return len(a & b) / len(a | b) if a and b else 0.0


def text_similarity(left: str, right: str) -> float:
    """가린 글끼리 글자 비슷함(0~1) — 빈칸을 하나로 맞춘 뒤 이어진 같은 글자 비율(``difflib`` · 쓰레기 글자 거르기 끔)."""
    a = " ".join((left or "").split())[:SIMILARITY_TEXT_LIMIT]
    b = " ".join((right or "").split())[:SIMILARITY_TEXT_LIMIT]
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def judge_reply(masked_drafts: Iterable[str], masked_reply: str) -> tuple[str, Optional[Decimal]]:
    """(끝난 꼴, 고친 정도) — 가장 비슷한 AI 초안과 :data:`COPY_SIMILARITY` 이상이면 '복사', 아니면 '직접 답'.

    고친 정도 = 1 − 가장 비슷한 초안과의 글자 비슷함(소수 셋째 자리). 견줄 초안이나 직원 글이 없으면 ``(직접 답, None)``.
    """
    drafts = [draft for draft in masked_drafts if draft and draft.strip()]
    if not drafts or not masked_reply.strip():
        return OUTCOME_DIRECT, None
    best = max(text_similarity(draft, masked_reply) for draft in drafts)
    ratio = Decimal(str(round(1.0 - best, 3)))
    return (OUTCOME_COPIED if best >= COPY_SIMILARITY else OUTCOME_DIRECT), ratio


# ── 글 모으기(원문은 이 바퀴 메모리에만) ─────────────────────────────────
def _line_text(line: ChatLine) -> str:
    """글 하나의 재료 글 — 두뇌 재료와 같은 꼴(첨부는 왔다는 표시만)."""
    return "\n".join(part for part in (line.text.strip(), FILE_NOTE if line.meta.has_file else "") if part)


def _clean(text_value: str) -> Optional[str]:
    """가린 글 — 가림 검사가 0 이 아니거나 비었으면 ``None``."""
    masked = mask(text_value).strip()
    return masked if masked and not any(leak_counts(masked).values()) else None


def _masked_join(lines: Iterable[ChatLine]) -> Optional[str]:
    """글마다 가려 가림 검사를 넘은 글만 잇는다(줄바꿈). 이은 글도 한 번 더 본다 — 남은 것이 없으면 ``None``."""
    parts = [masked for line in lines if (masked := _clean(_line_text(line)))]
    joined = "\n".join(parts)
    return joined if joined and not any(leak_counts(joined).values()) else None


def current_question(lines: Sequence[ChatLine]) -> Optional[str]:
    """지금 손님 글 — 마지막 공개 직원 글 뒤 손님 글을 가려 이은 것(가림 검사를 넘은 글만, :data:`QUERY_TEXT_LIMIT` 자까지)."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    joined = _masked_join(line for line in lines[after + 1:] if line.meta.is_customer_signal)
    return joined[:QUERY_TEXT_LIMIT] if joined else None


@dataclass(frozen=True)
class _Found:
    """읽은 상담에서 찾은 한 차례의 짝 — 직원 답 원문은 메모리에만(repr 없음)."""

    asked_ids: tuple[str, ...]
    question: Optional[str]
    reply: str
    manager_id: Optional[str]
    missing: Optional[str]

    def __repr__(self) -> str:
        """글 없이 코드만."""
        return f"_Found(asked={len(self.asked_ids)}, missing={self.missing})"


def _find(lines: Sequence[ChatLine], anchor_id: str, sent: set[str]) -> _Found:
    """그 차례 손님 글들(앞 공개 직원 글 뒤 ~ 차례 글) · 그 뒤 다음 손님 글 전의 공개 직원 글(보낸 글 id 뺌)."""
    at = next((i for i, line in enumerate(lines) if line.meta.message_id == anchor_id), None)
    if at is None:
        return _Found((anchor_id,), None, "", None, NO_ANCHOR)
    start = max((i for i in range(at) if lines[i].meta.is_answer), default=-1) + 1
    asked = [line for line in lines[start:at + 1] if line.meta.is_customer_signal]
    replies: list[ChatLine] = []
    for line in lines[at + 1:]:
        if line.meta.is_customer_signal:
            break
        if line.meta.is_answer and line.meta.message_id not in sent:
            replies.append(line)
    reply = "\n".join(part for part in (_line_text(line) for line in replies) if part)
    manager = next((line.person_id for line in replies if line.person_id), None)
    ids = tuple(line.meta.message_id for line in asked) or (anchor_id,)
    return _Found(ids, _masked_join(asked), reply, manager, None if reply else NO_REPLY_TEXT)


# ── 1. 직원 직접 답 붙이기 ───────────────────────────────────────────────
@dataclass(frozen=True)
class _Pending:
    """직원 글이 온 사례 없는 끝난 차례 — 차례 id · 상담 · 브랜드 · 차례 손님 글 id · 그 글 시각(UTC naive)."""

    turn_id: int
    chat_id: str
    brand: str
    message_id: str
    message_at: datetime.datetime


def _pending(session: Any, now: datetime.datetime, limit: int) -> list[_Pending]:
    """사례가 없는 끝난 차례 가운데 그 손님 글 뒤 공개 직원 글이 온 상담의 것 — 상담 줄 요약으로 먼저 거르고 새 차례부터."""
    turn, user, chat = CsAgentTurn, CsAgentMessage, CsAgentChat
    stmt = (select(turn.id, turn.chat_id, turn.brand, turn.last_user_message_id, user.created_at)
            .join(user, and_(user.chat_id == turn.chat_id, user.message_id == turn.last_user_message_id))
            .join(chat, chat.chat_id == turn.chat_id)
            .where(turn.state.in_(REPLY_STATES), turn.outcome.is_(None),
                   turn.updated_at >= naive_utc(now) - ATTACH_WINDOW,
                   chat.last_answer_at.isnot(None), chat.last_answer_at > user.created_at)
            .order_by(user.created_at.desc(), turn.id.desc()).limit(int(limit)))
    return [_Pending(*row) for row in session.execute(stmt)]


def _chat_rows(session: Any, pending: Sequence[_Pending]) -> tuple[dict[str, list[Any]], dict[str, set[str]]]:
    """상담마다 (차례 손님 글 이후의 상태 표 글 줄 — 시간순, 우리가 보낸 글 id) — 한 번에 읽는다(글 원문 없음)."""
    chats = sorted({item.chat_id for item in pending})
    floor = min(item.message_at for item in pending)
    rows: dict[str, list[Any]] = {}
    sent: dict[str, set[str]] = {chat_id: set() for chat_id in chats}
    for start in range(0, len(chats), _CHUNK):
        part = chats[start:start + _CHUNK]
        stmt = (select(CsAgentMessage.chat_id, CsAgentMessage.message_id, CsAgentMessage.person_type,
                       CsAgentMessage.created_at, CsAgentMessage.is_private, CsAgentMessage.is_log,
                       CsAgentMessage.is_code_message)
                .where(CsAgentMessage.chat_id.in_(part), CsAgentMessage.created_at >= floor))
        for row in session.execute(stmt):
            rows.setdefault(row.chat_id, []).append(row)
        ids = select(CsAgentTurn.chat_id, CsAgentTurn.sent_message_id).where(
            CsAgentTurn.chat_id.in_(part), CsAgentTurn.sent_message_id.isnot(None))
        for chat_id, message_id in session.execute(ids):
            sent[chat_id].add(message_id)
    for found in rows.values():
        found.sort(key=lambda row: (row.created_at, row.message_id))
    return rows, sent


def _is_customer_row(row: Any) -> bool:
    """상태 표 줄이 손님 글(확인코드 글 · 기록 · 비공개 제외)인가 — :attr:`.channel_read.DerivedMessage.is_customer_signal`."""
    return row.person_type == "user" and not row.is_private and not row.is_log and not row.is_code_message


def _is_answer_row(row: Any) -> bool:
    """상태 표 줄이 공개 상담원 글인가 — :attr:`.channel_read.DerivedMessage.is_answer`."""
    return row.person_type == "manager" and not row.is_private and not row.is_log


def _reply_done(item: _Pending, rows: Sequence[Any], sent: set[str], now: datetime.datetime) -> bool:
    """차례 손님 글 뒤 · 다음 손님 글 전에 직원 글(보낸 글 id 뺌)이 있고, 다음 손님 글이 왔거나 마지막 직원 글 뒤 조용하면 참."""
    anchor = (item.message_at, item.message_id)
    staff: list[Any] = []
    for row in rows:
        if (row.created_at, row.message_id) <= anchor or row.message_id == item.message_id:
            continue
        if _is_customer_row(row):
            return bool(staff)  # 다음 손님 글이 직원 답 창을 닫는다
        if _is_answer_row(row) and row.message_id not in sent:
            staff.append(row)
    return bool(staff) and naive_utc(now) - staff[-1].created_at >= REPLY_SETTLE


def attach_staff_replies(session: Any, *, now: datetime.datetime, stop: Any, reader: Any = None,
                         limits: AttachLimits = PASS_LIMITS,
                         clock: Callable[[], float] = time.monotonic) -> AttachSummary:
    """직원이 데스크에서 직접 보낸 답을 그 차례 줄에 사례로 붙인다(모듈 설명 1 의 순서). 차례마다 커밋한다.

    Args:
        session: DB 세션.
        now: 지금(시간대 있는 값).
        stop: 멈춤 깃발(``check`` · ``reader_sleep`` — 읽기 전 · 쓰기 전마다 본다).
        reader: 채널톡 읽기 도우미(없으면 읽을 상담이 있을 때 기본 — 기다림이 깃발을 본다).
        limits: 읽기 수 · 시간 상한. clock: 시간 상한 시계(단조, 시험 주입).

    Returns:
        :class:`AttachSummary`.

    Raises:
        PassStopped: TERM 깃발(그때까지 쓴 차례는 커밋돼 있다).
        SQLAlchemyError: DB 오류 — 부르는 바퀴 · 러너가 기록한다.
    """
    summary = AttachSummary()
    stop.check()
    pending = _pending(session, now, limits.max_pending)
    summary.pending = len(pending)
    rows, sent = _chat_rows(session, pending) if pending else ({}, {})
    ready = [item for item in pending if _reply_done(item, rows.get(item.chat_id, ()), sent[item.chat_id], now)]
    session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡을 읽는 동안 열어 두지 않는다
    summary.ready = len(ready)
    if ready:
        _attach_ready(session, ready, sent, summary, now=now, stop=stop, limits=limits, clock=clock,
                      reader=reader or OpenApiReader(sleep=stop.reader_sleep))
    if summary.direct or summary.copied or summary.halted:
        logger.info("[CS 사례] 직원 답 붙이기 %s", summary.counts())
    return summary


def _attach_ready(session: Any, ready: Sequence[_Pending], sent: dict[str, set[str]], summary: AttachSummary, *,
                  now: datetime.datetime, stop: Any, limits: AttachLimits, clock: Callable[[], float],
                  reader: Any) -> None:
    """상담마다(새 차례 글부터) 한 번 읽고 그 상담의 집은 차례를 모두 적는다 — 읽기 수 · 시간 상한 · 한도면 멈춘다."""
    groups: dict[str, list[_Pending]] = {}
    for item in ready:
        groups.setdefault(item.chat_id, []).append(item)
    deadline = clock() + limits.seconds
    for chat_id, items in groups.items():
        if summary.reads >= limits.max_reads or clock() >= deadline:
            summary.halted = HALT_READS if summary.reads >= limits.max_reads else HALT_TIME
            return
        stop.check()  # 읽기 전
        summary.reads += 1
        try:
            lines: Optional[list[ChatLine]] = read_lines(reader, items[0].brand, chat_id)
        except ChannelRateLimited:
            summary.halted = HALT_RATE_LIMITED
            return
        except ChannelReadError as exc:
            if exc.status != 404:
                logger.warning("[CS 사례] 상담 글 읽기 실패 — 이번 바퀴 사례 붙이기를 멈춘다 chat=%s status=%s",
                               chat_id, exc.status)
                summary.halted = HALT_READ_FAILED
                return
            lines = None  # 지워진 상담 — 직원이 답한 것은 상태 표로 안다(글 없이 코드만)
        for item in items:
            stop.check()  # 쓰기 전
            _attach_one(session, item, lines, sent[chat_id], summary, now=now)


def _batch_drafts(session: Any, chat_id: str, asked_ids: Sequence[str]) -> list[str]:
    """그 묶음(차례 손님 글들) 차례들의 가린 AI 초안 — 지우지 못한 앞 메모를 복사해도 '복사'로 잡는다."""
    stmt = select(CsAgentTurn.masked_draft).where(CsAgentTurn.chat_id == chat_id,
                                                  CsAgentTurn.last_user_message_id.in_(list(asked_ids)),
                                                  CsAgentTurn.masked_draft.isnot(None))
    return [draft for draft in session.scalars(stmt) if draft]


def _attach_one(session: Any, item: _Pending, lines: Optional[Sequence[ChatLine]], sent: set[str],
                summary: AttachSummary, *, now: datetime.datetime) -> None:
    """한 차례 — 짝 찾기 → 복사 판정 → 조건부 쓰기(가림 검사에 걸리면 글 없이) → 커밋. 그사이 바뀐 줄은 손대지 않는다."""
    found = _find(lines, item.message_id, sent) if lines is not None else _Found((item.message_id,), None, "",
                                                                                 None, DELETED_CHAT)
    row = session.get(CsAgentTurn, item.turn_id, populate_existing=True)
    if row is None or row.outcome is not None:
        session.commit()
        return
    outcome, ratio = judge_reply(_batch_drafts(session, item.chat_id, found.asked_ids), mask(found.reply))
    case = {"masked_question": found.question, "outcome": outcome, "edit_ratio": ratio,
            "desk_manager_id": found.manager_id}
    missing = found.missing
    try:
        try:
            record_staff_reply(row, found.reply or None, case=case, now=now)
        except MaskLeak as exc:
            logger.warning("[CS 사례] 직원 답이 가림 검사를 못 넘어 글 없이 코드만 남긴다 chat=%s turn=%s counts=%s",
                           item.chat_id, item.turn_id, exc.counts)
            record_staff_reply(row, None, case=case, now=now)
            missing = "mask_leak"
    except TurnStateError:
        session.rollback()
        summary.conflicts += 1
        return
    session.commit()
    summary.no_text += int(missing is not None)
    setattr(summary, outcome, getattr(summary, outcome) + 1)
    logger.info("[CS 사례] 직원 답을 사례로 붙였다 chat=%s turn=%s outcome=%s missing=%s",
                item.chat_id, item.turn_id, outcome, missing)


# ── 2. 다음 초안 재료 ────────────────────────────────────────────────────
def _usable(brand: str) -> tuple[Any, ...]:
    """재료가 되는 사례 줄 — 같은 브랜드 · 그대로 · 고침 · 직접 답 · 떼어 두지 않음 · 질문과 사람 답이 있음."""
    turn = CsAgentTurn
    return (turn.brand == brand, turn.outcome.in_(LEARNING_OUTCOMES), turn.held_out.is_(False),
            turn.masked_question.isnot(None), turn.staff_reply_masked.isnot(None))


def _pg_statement(brand: str, query: str, limit: int) -> Any:
    """PostgreSQL 사례 질의 — ``%``(trgm 문턱 — GIN 색인을 탄다)로 거르고 ``similarity`` 높은 것 · 새 사례부터."""
    score = func.similarity(CsAgentTurn.masked_question, query)
    return (select(CsAgentTurn.masked_question, CsAgentTurn.staff_reply_masked)
            .where(*_usable(brand), CsAgentTurn.masked_question.bool_op("%")(query))
            .order_by(score.desc(), CsAgentTurn.id.desc()).limit(limit))


def _pg_cases(session: Any, brand: str, query: str, limit: int) -> list[tuple[str, str]]:
    """PostgreSQL — 이 트랜잭션만 trgm 문턱을 :data:`CASE_MIN_SIMILARITY` 로 두고 :func:`_pg_statement` 로 읽는다."""
    session.execute(text("SELECT set_config('pg_trgm.similarity_threshold', :value, true)"),
                    {"value": str(CASE_MIN_SIMILARITY)})
    found = session.execute(_pg_statement(brand, query, limit))
    return [(row.masked_question, row.staff_reply_masked) for row in found]


def _py_cases(session: Any, brand: str, query: str, limit: int) -> list[tuple[str, str]]:
    """SQLite 시험 레인 — 최근 :data:`CASE_POOL` 사례를 :func:`trigram_similarity` 로 재서 같은 문턱 · 같은 순서."""
    stmt = (select(CsAgentTurn.id, CsAgentTurn.masked_question, CsAgentTurn.staff_reply_masked)
            .where(*_usable(brand)).order_by(CsAgentTurn.id.desc()).limit(CASE_POOL))
    scored = [(trigram_similarity(row.masked_question, query), row.id, row) for row in session.execute(stmt)]
    scored = sorted((item for item in scored if item[0] >= CASE_MIN_SIMILARITY), key=lambda item: (-item[0], -item[1]))
    return [(row.masked_question, row.staff_reply_masked) for _, _, row in scored[:limit]]


def similar_cases(session: Any, brand: str, lines: Sequence[ChatLine], *,
                  limit: int = MAX_CASES) -> tuple[tuple[str, str], ...]:
    """다음 초안 재료 — 같은 브랜드 비슷한 지난 사례 (가린 질문, 사람이 보낸 가린 답), 비슷한 것부터 ``limit`` 개까지.

    지금 손님 글(:func:`current_question`)이 없으면 빈 튜플. 글마다 :data:`CASE_TEXT_LIMIT` 자로 자르고 가림 검사를 다시 넘은
    사례만 돌려준다(두뇌가 실을 때 한 번 더 본다). DB 를 읽기만 한다 — 커밋은 부르는 쪽(두뇌가 곧 커밋한다).
    """
    query = current_question(lines)
    if not query:
        return ()
    pick = _pg_cases if session.get_bind().dialect.name == "postgresql" else _py_cases
    out: list[tuple[str, str]] = []
    for question, answer in pick(session, brand, query, int(limit)):
        pair = (question[:CASE_TEXT_LIMIT].strip(), answer[:CASE_TEXT_LIMIT].strip())
        if all(part and not any(leak_counts(part).values()) for part in pair):
            out.append(pair)
    return tuple(out)
