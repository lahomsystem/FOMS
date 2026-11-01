"""'고칠 말' 다시 쓰기 — [수정하기] 화면의 요청을 빠른 길이 받아 새 초안 메모로 바꾼다(모델을 부르는 곳은 빠른 길 하나).

플랜 C10-3 · 설계서 17.2('[수정하기] → 고치는 칸 + 고칠 말로 AI 가 다시 쓰기 — 빠른 길이 받음') · 17.1(R10-9: 보내기는 web,
모델을 부르는 일만 빠른 길). :func:`run_rewrites` 는 빠른 길 차례(:mod:`.realtime`)가 초안 뒤에 부른다. 요청 하나(순서 고정):

1. 요청 줄(``rewrite_state='requested'``)을 '하는 중'으로 조건부 쓰기 → 커밋(두 컨테이너가 겹쳐도 하나만).
2. 스위치(비상 정지 아님 · 초안 메모 · 빠른 길 · [보내기] 버튼) — 꺼졌으면 '못 함'.
3. 상담 글 다시 읽기 — 선점한 손님 글이 아직 마지막이고 직원 답이 없을 때만(아니면 '못 함').
4. 지금 메모의 '손님께 보낼 답'(앞 초안)과 가린 고칠 말을 두뇌 재료에 싣는다(가림은 두뇌가 한다 — 앞 초안도 다시 가린다).
   두뇌 → 초안과 같은 보내기 전 검사(걸리면 '못 함').
5. 새 메모(링크 버튼 포함)를 올리고 다시 읽어 비공개 확인 → 차례 줄의 메모 id · 가린 초안을 새것으로(그사이 보냄 · 버림이면 쓰지
   않는다). 공개로 보이면 초안 스위치를 끄고 · 확인 못 함이면 '저장만'으로 + 관리자 알림(초안 메모와 같은 막는 장치).

'하는 중'으로 :data:`WORKING_EXPIRES` 넘게 남은 줄(죽은 실행 단위)은 차례 시작에 '못 함'(``rewrite_expired``)으로 되돌린다 —
그 동안은 [보내기]가 막히므로 영원히 남지 않게(검수 R15-5). 예상 밖 예외는 그 줄을 '못 함'으로 되돌린 뒤 올린다.
다시 쓴 수(하는 중으로 집을 때 센다)는 차례마다 :data:`.send_flow.MAX_REWRITES` 까지(요청 쪽이 막는다). 글은 로그 · 요약에 싣지 않는다(차례 id · 코드만).
"""

from __future__ import annotations

import datetime
import logging
from types import SimpleNamespace
from typing import Any, Callable

from sqlalchemy import select, update

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.brain import BrainNotReady, BrainUnavailable, DraftRequest, SpendCapReached
from foms.services.cs_agent.brain_prompt import PURPOSE_DRAFT
from foms.services.cs_agent.channel_read import ChannelReadError, OpenApiReader, naive_utc
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.drafting_pass import HUMAN_ONLY_MARK
from foms.services.cs_agent.drafting_post import _alert
from foms.services.cs_agent.drafting_read import (
    conversation, freshness, memo_draft, memo_snippets, memo_text, read_lines, read_medium,
)
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.memo import MEMO_BRAND, REASON_NOT_PRIVATE
from foms.services.cs_agent.quote_record import allowed_from, lines_from
from foms.services.cs_agent.send import memo_buttons
from foms.services.cs_agent.send_record import REWRITE_WORKING, open_turn
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import (
    DRAFT_MEMO, DRAFT_OFF, DRAFT_STORE, draft_mode, read_switch, set_draft_mode,
)
from foms.services.cs_agent.turns_fields import ID_PATTERN, masked_or_none

logger = logging.getLogger(__name__)

__all__ = ["REWRITE_DONE", "REWRITE_FAILED", "REWRITE_REQUESTED", "REWRITE_STATES", "REWRITE_WORKING",
           "WORKING_EXPIRES", "run_rewrites"]

REWRITE_REQUESTED, REWRITE_DONE, REWRITE_FAILED = "requested", "done", "failed"  # 하는 중은 send_record 와 같은 이름
#: '하는 중' 만료 — 두뇌 시간 상한(60초까지) + 읽기 · 메모 여유. 넘으면 죽은 실행 단위로 보고 되돌린다.
WORKING_EXPIRES = datetime.timedelta(minutes=3)
#: 다시 쓰기 상태 — 마이그레이션 ``csagent_04`` · 모델 검사 제약과 같은 순서 · 글자(시험이 맞춘다).
REWRITE_STATES: tuple[str, ...] = (REWRITE_REQUESTED, REWRITE_WORKING, REWRITE_DONE, REWRITE_FAILED)
_TURNS = CsAgentTurn.__table__


def _claim(session: Any, turn_id: int, now: datetime.datetime) -> bool:
    """요청 → 하는 중(조건부 한 문장). 다시 쓴 수는 여기서 센다 — 못 함으로 끝나도 두뇌 한 번은 쓴 것이다(상한이 돈을 묶는다)."""
    stmt = (update(_TURNS).where(*open_turn(turn_id), _TURNS.c.rewrite_state == REWRITE_REQUESTED)
            .values(rewrite_state=REWRITE_WORKING, rewrite_count=_TURNS.c.rewrite_count + 1, updated_at=naive_utc(now)))
    return session.execute(stmt).rowcount == 1


def _give_up(session: Any, turn_id: int, code: str, now: datetime.datetime) -> str:
    """못 함 — 하는 중 줄만, 까닭은 보내기 막힘 칸에 코드로(화면이 '직접 고쳐 보내 주세요'를 보인다)."""
    session.rollback()
    session.execute(update(_TURNS).where(_TURNS.c.id == turn_id, _TURNS.c.rewrite_state == REWRITE_WORKING)
                    .values(rewrite_state=REWRITE_FAILED, send_error=f"rewrite_{code}"[:48],
                            updated_at=naive_utc(now)))
    session.commit()
    logger.warning("[CS 다시 쓰기] 못 함 turn=%s code=%s", turn_id, code)
    return code


def _switch_ready(session: Any) -> bool:
    """비상 정지 아님 · 초안 메모 · 빠른 길 · [보내기] 버튼 켬(DB 에서 새로)."""
    cfg = read_settings(session, log=False)
    return (read_switch(session) and draft_mode(session) == DRAFT_MEMO and bool(cfg.get("realtime_enabled"))
            and bool(cfg.get("send_buttons_enabled")))


def run_rewrites(session: Any, *, now: datetime.datetime, stop: Any, reader: Any, brain: Callable[..., Any],
                 poster: Callable[..., Any], daytime: bool = True, limit: int = 1) -> dict[str, int]:
    """'고칠 말' 요청을 :data:`limit` 개까지 처리한다(모듈 설명의 순서). 숫자 · 코드만 돌려준다. 커밋한다."""
    expired = session.execute(update(_TURNS).where(_TURNS.c.rewrite_state == REWRITE_WORKING,
                                                   _TURNS.c.updated_at < naive_utc(now) - WORKING_EXPIRES)
                              .values(rewrite_state=REWRITE_FAILED, send_error="rewrite_expired",
                                      updated_at=naive_utc(now))).rowcount
    session.commit()
    if expired:
        logger.warning("[CS 다시 쓰기] 오래 남은 '하는 중' %d건을 되돌렸다(다시 요청할 수 있다)", expired)
    stmt = (select(CsAgentTurn.id).where(CsAgentTurn.rewrite_state == REWRITE_REQUESTED)
            .order_by(CsAgentTurn.rewrite_requested_at, CsAgentTurn.id).limit(int(limit)))
    ids = list(session.scalars(stmt))
    session.commit()
    counts: dict[str, int] = {"expired": expired} if expired else {}
    if ids and reader is None:
        reader = OpenApiReader(sleep=stop.reader_sleep)  # 요청이 있을 때만 만든다(5초마다 도는 차례)
    for turn_id in ids:
        stop.check()  # 쓰기 · 두뇌 전
        if not _claim(session, turn_id, now):
            session.rollback()
            continue
        session.commit()
        try:
            verdict = _one(session, turn_id, now=now, stop=stop, reader=reader, brain=brain, poster=poster,
                           daytime=daytime)
        except Exception:
            _give_up(session, turn_id, "error", now)  # 그 줄을 '하는 중'에 두지 않는다 — 예외는 그대로 올린다
            raise
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _one(session: Any, turn_id: int, *, now: datetime.datetime, stop: Any, reader: Any, brain: Callable[..., Any],
         poster: Callable[..., Any], daytime: bool) -> str:
    """요청 하나 — 스위치 → 읽기 → 두뇌 → 검사 → 새 메모 → 줄 바꾸기."""
    row = session.get(CsAgentTurn, turn_id, populate_existing=True)
    chat_id, note, memo_id = row.chat_id, row.rewrite_note_masked, row.memo_message_id
    quote_lines, quote_allowed = lines_from(row.quote_lines), allowed_from(row.quote_lines)  # 그 차례 계산기 값(R17-1)
    if not _switch_ready(session) or row.brand != MEMO_BRAND or not note:
        return _give_up(session, turn_id, "switched_off", now)
    knowledge = load_approved(session, row.brand)
    session.commit()
    try:
        lines = read_lines(reader, MEMO_BRAND, chat_id)
        medium = read_medium(reader, MEMO_BRAND, chat_id)
    except ChannelReadError:
        return _give_up(session, turn_id, "read_failed", now)
    stale = freshness(lines, row.last_user_message_id)
    memo = next((line for line in lines if line.meta.message_id == memo_id and line.meta.is_private), None)
    previous = memo_draft(memo.text) if memo is not None else None
    if stale or previous is None:
        return _give_up(session, turn_id, stale or "memo_missing", now)
    try:
        request = DraftRequest(brand=MEMO_BRAND, chat_id=chat_id, medium=medium, purpose=PURPOSE_DRAFT, daytime=daytime,
                               messages=conversation(lines), customer_names=(), staff_names=(), knowledge=knowledge,
                               realtime=True, rewrite=(previous, note), calculator_lines=quote_lines)
    except ValueError:
        return _give_up(session, turn_id, "bad_request", now)
    stop.check()  # 두뇌 전
    try:
        result = brain(request, session=session, now=now)
    except (BrainNotReady, SpendCapReached, BrainUnavailable, MaskLeak) as exc:
        return _give_up(session, turn_id, getattr(exc, "code", None) or type(exc).__name__.lower(), now)
    if result.refused or result.handoff or not result.draft.strip():
        return _give_up(session, turn_id, "handoff", now)
    allowed = (*(item.text for item in knowledge.items if HUMAN_ONLY_MARK not in item.text), *quote_allowed)
    human_only = {item.item_id for item in knowledge.items if HUMAN_ONLY_MARK in item.text}
    check = check_draft(result.draft, brand=MEMO_BRAND, medium=medium, allowed_numbers=allowed,
                        private_snippets=(*memo_snippets(lines), result.staff_note),
                        human_only_amounts=bool(human_only.intersection(result.evidence_ids)))
    if not check.ok:
        return _give_up(session, turn_id, "check_failed", now)
    return _post(session, turn_id, chat_id, result, now=now, reader=reader, poster=poster)


def _post(session: Any, turn_id: int, chat_id: str, result: Any, *, now: datetime.datetime, reader: Any,
          poster: Callable[..., Any]) -> str:
    """새 메모를 올리고(버튼 포함) 줄을 새 메모로 바꾼다. 공개 · 확인 못 함이면 초안 메모와 같은 막는 장치."""
    if not _switch_ready(session):  # 두뇌를 부르는 동안 꺼졌으면 올리지 않는다
        return _give_up(session, turn_id, "switched_off", now)
    session.commit()
    sent = poster(chat_id, memo_text(result.draft, result.staff_note), brand=MEMO_BRAND, reader=reader,
                  buttons=memo_buttons(turn_id, chat_id))
    if not sent.posted:
        return _give_up(session, turn_id, "memo_unknown" if sent.outcome_unknown else "memo_failed", now)
    message_id = sent.message_id if isinstance(sent.message_id, str) and ID_PATTERN.fullmatch(sent.message_id) else None
    values: dict[str, Any] = {"rewrite_state": REWRITE_DONE, "send_error": None, "updated_at": naive_utc(now)}
    if message_id is not None:
        values["memo_message_id"] = message_id
    try:
        values["masked_draft"] = masked_or_none(result.draft)
    except MaskLeak:
        values["masked_draft"] = None  # 가림이 놓친 꼴 — 가린 사본을 두지 않는다(메모는 이미 올렸다)
    done = session.execute(update(_TURNS).where(*open_turn(turn_id), _TURNS.c.rewrite_state == REWRITE_WORKING)
                           .values(values)).rowcount == 1
    guard = None if sent.verified else (DRAFT_OFF if sent.reason == REASON_NOT_PRIVATE else DRAFT_STORE)
    if guard is not None:
        set_draft_mode(session, guard, reason=sent.reason or "not_verified", now=now)
    session.commit()
    if guard is not None:
        logger.error("[CS 다시 쓰기] 새 메모의 비공개를 확인 못 했다 — 초안 스위치를 %s 로 turn=%s", guard, turn_id)
        _alert(SimpleNamespace(session=session, now=now), chat_id, message_id, guard, sent.reason)
    if not done:  # 그사이 보냄 · 버림 — 새 메모는 데스크에 남지만 차례는 그대로다
        logger.warning("[CS 다시 쓰기] 새 메모를 올렸지만 그사이 차례가 끝났다 turn=%s message=%s", turn_id, message_id)
        return "closed"
    logger.info("[CS 다시 쓰기] 새 초안 메모 turn=%s message=%s", turn_id, message_id)
    return REWRITE_DONE

