"""[보내기] 기록 — 차례 줄의 보내기 상태 조건부 쓰기 · 보낸 글을 상태 표에 '답'으로 · 결과 모름 맞추기(requestId).

플랜 C10-3 · 설계서 17.2('누를 때 서버가 확인하는 것' 1 · 5 · 되먹임 막기) · 원장 R10-10 · R10-5. 표는 ``models.CsAgentTurn``
(``csagent_04`` 칸). 차례 ``state`` 는 그대로 ``posted`` 이고 보내기는 ``send_state`` 칸만 바꾼다.

- **조건부 쓰기(한 문장 · 바뀐 줄 1 이어야)**: '보내는 중'(:func:`start_sending`)은 메모 올림 · 끝난 꼴 없음 · 아직 안 보냈거나
  못 보낸 줄 · 화면이 본 그 메모일 때만 — 두 번 누름 · 두 사람 동시엔 하나만 바뀐다. 뒤 쓰기는 모두 ``send_state`` 를 조건으로
  건다(그사이 빠른 길이 차례를 '지난 초안'으로 바꿔도 보낸 사실은 적는다).
- **보냄(:func:`finish_sent`)**: 보낸 글 id · 보낸 때 · 끝난 꼴(그대로 · 고침) · 고친 정도 · 까닭 · 가린 보낸 글 · 가린 손님 질문 ·
  첫 미답 손님 글 시각. 이어서 상태 표에 그 글을 공개 직원 글(답)로 적는다(:func:`record_answer` — 웹훅이 먼저 봇 글로 넣었으면
  답으로 고친다). 그래서 상담이 '답 필요'에서 빠지고, 다음 손님 글의 초안 재료에 [직원] 글로 들어가며, 사례 기억은 보낸 글 id 로
  '직접 답'에서 뺀다(C10-4 거름).
- **결과 모름(:func:`mark_unknown`)**: 다시 보내지 않는다. 사례 칸을 미리 적어 두고, :func:`reconcile_turn` 이 그 상담 글을 읽어
  requestId 로 찾으면 보냄으로, :data:`NOT_DELIVERED_AFTER` 가 지나도 없으면 못 보냄(다시 누를 수 있음)으로 바꾼다. '보내는 중'
  으로 :data:`STUCK_AFTER` 넘게 남은 줄(보내던 web 이 죽음)도 같이 맞춘다(채널톡은 requestId 겹침을 거르지 않는다 — 우리 상태가
  유일한 막기다).
- 글은 로그 · 예외 · 요약에 싣지 않는다(차례 id · 상담 id · 코드 · 숫자만). 커밋은 부르는 쪽.
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy import and_, or_, select, update

from foms.persistence.main.models import CsAgentMessage, CsAgentTurn
from foms.services.cs_agent.case_material import current_question
from foms.services.cs_agent.case_memory import OUTCOME_AS_IS, OUTCOME_EDITED, text_similarity
from foms.services.cs_agent.channel_read import (
    ChannelReadError, DerivedMessage, OpenApiReader, channel_for_brand, derive_message, naive_utc,
)
from foms.services.cs_agent.drafting_read import ChatLine, memo_draft, read_lines
from foms.services.cs_agent.masking import MaskLeak, mask
from foms.services.cs_agent.send import request_id_for
from foms.services.cs_agent.state_store import SOURCE_OPENAPI, _bump_chat_summary, store_messages
from foms.services.cs_agent.turns import STATE_POSTED
from foms.services.cs_agent.turns_fields import masked_or_none

logger = logging.getLogger(__name__)

__all__ = [
    "NOT_DELIVERED_AFTER", "REWRITE_WORKING", "SEND_FAILED", "SEND_SENDING", "SEND_SENT", "SEND_STATES",
    "SEND_UNKNOWN_STATE", "STUCK_AFTER", "SentCase", "finish_sent", "mark_send_failed", "mark_unknown", "open_turn",
    "reconcile_sends", "reconcile_turn", "record_answer", "revert_sending", "sent_case", "start_sending",
    "still_sending", "waiting_since",
]

SEND_SENDING, SEND_SENT, SEND_UNKNOWN_STATE, SEND_FAILED = "sending", "sent", "unknown", "failed"
#: 보내기 상태 — 마이그레이션 ``csagent_04`` · 모델 검사 제약과 같은 순서 · 글자(시험이 맞춘다).
SEND_STATES: tuple[str, ...] = (SEND_SENDING, SEND_SENT, SEND_UNKNOWN_STATE, SEND_FAILED)
#: '고칠 말' 처리 중 — 이 동안은 보내기를 막는다(검수 R15-5, 상태 이름은 :mod:`.rewrite` 와 같다).
REWRITE_WORKING = "working"
#: '보내는 중'이 이만큼 넘게 남으면 보내던 web 이 죽은 것으로 보고 상담 글로 맞춘다(보내기 한 번은 읽기 + 쓰기 각 10초 안).
STUCK_AFTER = datetime.timedelta(seconds=60)
#: 결과를 모르는 보내기가 이만큼 지나도 상담 글에 없으면 못 보냄 — 다시 누를 수 있다.
NOT_DELIVERED_AFTER = datetime.timedelta(minutes=5)
NOT_DELIVERED = "not_delivered"
_TURNS = CsAgentTurn.__table__
_MSGS = CsAgentMessage.__table__
_CASE_FIELDS = ("outcome", "edit_ratio", "edit_reason", "staff_reply_masked", "masked_question", "waiting_since")


class SentCase(dict):
    """보낸 글의 사례 칸(끝난 꼴 · 고친 정도 · 까닭 · 가린 보낸 글 · 가린 질문 · 첫 미답 손님 글 시각) — 글 원문은 없다."""

    def __repr__(self) -> str:
        """글 없이 끝난 꼴만."""
        return f"SentCase(outcome={self.get('outcome')})"


def waiting_since(lines: Sequence[ChatLine]) -> Optional[datetime.datetime]:
    """첫 미답 손님 글 시각(UTC naive) — 마지막 공개 직원 글 뒤 첫 손님 글('발송' 지표의 시작)."""
    after = max((i for i, line in enumerate(lines) if line.meta.is_answer), default=-1)
    first = next((line for line in lines[after + 1:] if line.meta.is_customer_signal), None)
    return naive_utc(first.meta.created_at) if first is not None else None


def sent_case(lines: Sequence[ChatLine], *, ai_draft: Optional[str], sent_text: str, edited: bool,
              edit_reason: Optional[str]) -> SentCase:
    """보낸 글의 사례 칸 — 고친 정도 = 1 − (가린 AI 초안 ↔ 가린 보낸 글) 글자 비슷함. 가림 검사에 걸린 글은 칸을 비운다."""
    masked_sent = mask(sent_text)
    ratio: Optional[Decimal] = Decimal("0.000")
    if edited:
        ratio = (Decimal(str(round(1.0 - text_similarity(mask(ai_draft), masked_sent), 3)))
                 if ai_draft else None)
    try:
        reply = masked_or_none(sent_text)
    except MaskLeak as exc:
        logger.warning("[CS 보내기] 보낸 글이 가림 검사를 못 넘어 사례 글을 비운다 counts=%s", exc.counts)
        reply = None
    return SentCase(outcome=OUTCOME_EDITED if edited else OUTCOME_AS_IS, edit_ratio=ratio,
                    edit_reason=edit_reason if edited else None, staff_reply_masked=reply,
                    masked_question=current_question(lines), waiting_since=waiting_since(lines))


# ── 조건부 쓰기(한 문장 — 바뀐 줄 1) ─────────────────────────────────────
def _one(session: Any, stmt: Any) -> bool:
    """UPDATE 한 문장 — 바뀐 줄이 하나면 참."""
    return session.execute(stmt).rowcount == 1


def open_turn(turn_id: int, memo_id: Optional[str] = None) -> tuple[Any, ...]:
    """아직 열린 메모 차례 조건(조건부 쓰기 한 곳 — 보내기 · 버리기 · 고칠 말 · 다시 쓰기가 같이 쓴다, 검수 R15 단순화).

    메모 올림 · 끝난 꼴 없음 · 안 보냈거나 못 보낸 줄. ``memo_id`` 를 주면 화면이 본 그 메모일 때만.
    """
    where = (_TURNS.c.id == turn_id, _TURNS.c.state == STATE_POSTED, _TURNS.c.outcome.is_(None),
             or_(_TURNS.c.send_state.is_(None), _TURNS.c.send_state == SEND_FAILED))
    return where if memo_id is None else (*where, _TURNS.c.memo_message_id == memo_id)


def start_sending(session: Any, row: Any, *, user_id: int, click_ms: Optional[int], now: datetime.datetime) -> bool:
    """'보내는 중' — 열린 차례 · 화면이 본 그 메모 · '고칠 말' 처리 중 아님일 때만(두 번 누름 · 동시엔 하나만)."""
    at = naive_utc(now)
    stmt = (update(_TURNS)
            .where(*open_turn(row.id, row.memo_message_id),
                   or_(_TURNS.c.rewrite_state.is_(None), _TURNS.c.rewrite_state != REWRITE_WORKING))
            .values(send_state=SEND_SENDING, send_started_at=at, sent_by_user_id=int(user_id), click_ms=click_ms,
                    send_error=None, updated_at=at))
    return _one(session, stmt)


def revert_sending(session: Any, turn_id: int, *, back_to: Optional[str], error: str, now: datetime.datetime) -> bool:
    """보내지 않고 되돌린다(새 글 · 검사 · 확인 필요 · 읽기 실패) — 누른 직원 · 밀리초는 지운다(보낸 사람이 아니다)."""
    stmt = (update(_TURNS).where(_TURNS.c.id == turn_id, _TURNS.c.send_state == SEND_SENDING)
            .values(send_state=back_to, send_error=error, sent_by_user_id=None, click_ms=None,
                    send_started_at=None if back_to is None else _TURNS.c.send_started_at, updated_at=naive_utc(now)))
    return _one(session, stmt)


def still_sending(session: Any, turn_id: int) -> bool:
    """채널톡을 부르기 바로 전 — 아직 '보내는 중'인가(그사이 맞추기 · 다른 쪽이 바꿨으면 부르지 않는다, 검수 R15-4)."""
    return session.scalar(select(_TURNS.c.send_state).where(_TURNS.c.id == turn_id)) == SEND_SENDING


def finish_sent(session: Any, turn_id: int, *, message_id: Optional[str], sent_at: datetime.datetime,
                case: Optional[SentCase], now: datetime.datetime) -> bool:
    """보냄 — '보내는 중' · '결과 모름' 줄만. ``case`` 가 없으면(맞추기가 미리 적은 칸을 쓴다) 사례 칸은 그대로 둔다."""
    values: dict[str, Any] = {"send_state": SEND_SENT, "sent_message_id": message_id, "sent_at": naive_utc(sent_at),
                              "send_error": None, "updated_at": naive_utc(now), **(case or {})}
    stmt = (update(_TURNS).where(_TURNS.c.id == turn_id, _TURNS.c.send_state.in_((SEND_SENDING, SEND_UNKNOWN_STATE)))
            .values(values))
    return _one(session, stmt)


def mark_unknown(session: Any, turn_id: int, *, case: SentCase, now: datetime.datetime) -> bool:
    """결과 모름 — 다시 보내지 않는다. 사례 칸을 미리 적어 두면 맞추기는 상태만 바꾼다."""
    stmt = (update(_TURNS).where(_TURNS.c.id == turn_id, _TURNS.c.send_state == SEND_SENDING)
            .values(send_state=SEND_UNKNOWN_STATE, send_error="send_unknown", updated_at=naive_utc(now), **case))
    return _one(session, stmt)


def mark_send_failed(session: Any, turn_id: int, *, error: str, now: datetime.datetime,
                     states: Sequence[str] = (SEND_SENDING,)) -> bool:
    """못 보냄(확실히 — 다시 누를 수 있다) — 사례 칸 · 누른 직원을 비운다."""
    values: dict[str, Any] = {"send_state": SEND_FAILED, "send_error": error, "sent_by_user_id": None,
                              "click_ms": None, "updated_at": naive_utc(now)}
    values.update({name: None for name in _CASE_FIELDS})
    stmt = update(_TURNS).where(_TURNS.c.id == turn_id, _TURNS.c.send_state.in_(tuple(states))).values(values)
    return _one(session, stmt)


# ── 상태 표에 '답' 한 줄 ─────────────────────────────────────────────────
def _answer_message(brand: str, chat_id: str, message_id: str, sent_at: datetime.datetime, text: str,
                    turn_id: int) -> DerivedMessage:
    """보낸 글의 파생 칸 — 웹훅이 받을 글과 같은 꼴(봇 공개 글 + 우리 requestId)로 :func:`derive_message` 를 돌린다. 그래서
    직원 답(manager)으로 읽히고 약속(연락 · 전화 약속과 기한)도 데스크 직접 답과 같이 잰다(검수 R15-2). 글은 메모리에서만."""
    entity = {"chatType": "userChat", "chatId": chat_id, "channelId": channel_for_brand(brand), "id": message_id,
              "personType": "bot", "requestId": request_id_for(turn_id), "plainText": text,
              "createdAt": int(sent_at.astimezone(datetime.timezone.utc).timestamp() * 1000)}
    message, _reason = derive_message(entity, expected_brand=brand)
    return message if message is not None else DerivedMessage(
        chat_id=chat_id, message_id=message_id, channel_id=channel_for_brand(brand), brand=brand, person_type="manager",
        created_at=sent_at.astimezone(datetime.timezone.utc))


def record_answer(session: Any, *, brand: str, chat_id: str, message_id: str, sent_at: datetime.datetime, text: str,
                  turn_id: int, now: datetime.datetime) -> None:
    """보낸 글을 상태 표에 공개 직원 글(답) · 약속 칸과 함께 넣는다. 이미 들어와 있으면(웹훅이 먼저 봇 글로) 답으로 고치고
    비어 있던 약속 칸만 채운 뒤 상담 줄을 올린다."""
    message = _answer_message(brand, chat_id, message_id, sent_at, text, turn_id)
    if store_messages(session, [message], source=SOURCE_OPENAPI, now=naive_utc(now)).inserted:
        return
    due = message.promise_due_at
    fixed = session.execute(update(_MSGS).where(_MSGS.c.chat_id == chat_id, _MSGS.c.message_id == message_id,
                                                _MSGS.c.is_private.is_(False),
                                                or_(_MSGS.c.person_type != "manager", _MSGS.c.promise_kind.is_(None)))
                            .values(person_type="manager", promise_kind=message.promise_kind,
                                    promise_due_at=naive_utc(due) if due else None,
                                    promise_rule=message.promise_rule)).rowcount
    if fixed:
        _bump_chat_summary(session, message, naive_utc(now))


# ── 결과 모름 맞추기(requestId) ──────────────────────────────────────────
def _pending(session: Any, now: datetime.datetime, limit: int) -> list[Any]:
    """맞출 줄 — 결과 모름 · 오래 남은 '보내는 중', 오래된 것부터."""
    at = naive_utc(now)
    stmt = (select(CsAgentTurn)
            .where(or_(CsAgentTurn.send_state == SEND_UNKNOWN_STATE,
                       and_(CsAgentTurn.send_state == SEND_SENDING, CsAgentTurn.send_started_at < at - STUCK_AFTER)))
            .order_by(CsAgentTurn.send_started_at, CsAgentTurn.id).limit(int(limit))
            .execution_options(populate_existing=True))
    return list(session.scalars(stmt))


def reconcile_turn(session: Any, row: Any, *, now: datetime.datetime, reader: Any) -> str:
    """한 줄 맞추기 — 상담 글에서 requestId 로 우리 글을 찾으면 보냄, 오래 없으면 못 보냄, 아니면 그대로. 커밋한다.

    Returns:
        ``sent`` · ``failed`` · ``waiting``(아직 모름) · ``read_failed`` · ``skipped``(맞출 줄이 아님).
    """
    at = naive_utc(now)
    if row.send_state not in (SEND_UNKNOWN_STATE, SEND_SENDING):
        return "skipped"
    if row.send_state == SEND_SENDING and (row.send_started_at is None or row.send_started_at >= at - STUCK_AFTER):
        return "waiting"  # 보내는 중인 web 이 아직 일하고 있다
    try:
        lines = read_lines(reader, row.brand, row.chat_id)
    except ChannelReadError as exc:
        session.rollback()
        logger.warning("[CS 보내기] 결과 맞추기 읽기 실패 turn=%s status=%s", row.id, exc.status)
        return "read_failed"
    wanted = request_id_for(row.id)
    at_found = next((i for i, line in enumerate(lines) if line.request_id == wanted and not line.meta.is_private), None)
    if at_found is not None:
        found, case = lines[at_found], None
        if row.send_state == SEND_SENDING:  # 보내던 web 이 죽었다 — 사례 칸을 우리 글 **앞** 상담 글로 채운다(R16-5)
            memo = next((line for line in lines if line.meta.message_id == row.memo_message_id), None)
            ai = memo_draft(memo.text) if memo is not None else None
            case = sent_case(lines[:at_found], ai_draft=ai, sent_text=found.text,
                             edited=ai is None or ai != found.text.strip(), edit_reason=None)
        if finish_sent(session, row.id, message_id=found.meta.message_id, sent_at=found.meta.created_at, case=case,
                       now=now):
            record_answer(session, brand=row.brand, chat_id=row.chat_id, message_id=found.meta.message_id,
                          sent_at=found.meta.created_at, text=found.text, turn_id=row.id, now=now)
        session.commit()
        logger.info("[CS 보내기] 결과를 맞췄다 — 보냄 turn=%s message=%s", row.id, found.meta.message_id)
        return "sent"
    started = row.send_started_at
    if started is not None and started < at - NOT_DELIVERED_AFTER:
        mark_send_failed(session, row.id, error=NOT_DELIVERED, now=now, states=(SEND_UNKNOWN_STATE, SEND_SENDING))
        session.commit()
        logger.warning("[CS 보내기] 결과를 맞췄다 — 상담에 없음(못 보냄, 다시 누를 수 있다) turn=%s", row.id)
        return "failed"
    session.commit()
    return "waiting"


def reconcile_sends(session: Any, *, now: datetime.datetime, reader: Any, stop: Any = None,
                    limit: int = 3) -> dict[str, int]:
    """바퀴 정리 — 맞출 줄을 :data:`limit` 개까지 맞춘다(상담마다 읽기 한 번). 숫자만 돌려준다."""
    rows = _pending(session, now, limit)
    session.commit()
    counts: dict[str, int] = {}
    if rows and reader is None:
        reader = OpenApiReader(sleep=stop.reader_sleep) if stop is not None else OpenApiReader()  # 맞출 줄이 있을 때만
    for row in rows:
        if stop is not None:
            stop.check()  # 읽기 · 쓰기 전
        verdict = reconcile_turn(session, row, now=now, reader=reader)
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts
