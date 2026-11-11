"""넘김 메모 [배우기] · [흘리기] — AI 가 초안을 안 쓰고 넘긴 차례에 직원이 직접 쓴 답을 보내고 배우게 · 배우지 않게(사장님 11-11).

넘김 메모(:mod:`.handoff_memo`)에 단추 둘이 붙는다(관리 화면 '[배우기] · [흘리기] 단추' — 처음 끔, 채널톡 안 작은 창 길만).
작은 창 앱 함수(:mod:`.wam_functions` 의 ``cs.handoff.*``)가 이 모듈만 부른다. 누른 사람은 서명된 채널톡 상담원뿐이다.

- **[배우기] → [보내기]** (:func:`send_handoff`) — 초안 [보내기](:mod:`.send_flow`)와 같은 0~5 순서 · 같은 보내기 감싸개
  (:func:`.send.send_reply` — 봇 이름 공개 글 · requestId = 차례 id) · 같은 '고친 글' 검사(확실한 위험은 막고 나머지는 '확인 후
  보내기'). 다른 점 셋:
  1. 차례는 넘김 메모 차례(건너뜀 — :func:`.send_record.open_handoff_turn`)만 연다. 초안 길(``cs.draft.*``)은 지금처럼 올림
     차례만 연다 — 두 길은 서로의 차례를 열지 못한다.
  2. '최신인가'가 다르다: 그 손님 글 뒤에 공개 답(직원 · 우리 봇)이 있으면 막는다(손님께 두 번 가지 않게). 손님이 그사이 더
     썼으면 막지 않고 알린다 — 창을 열 때 본 마지막 손님 글(``seen``)과 지금이 다르면 '새 글'과 새 ``seen`` 을 돌려주고, 직원이
     읽어 본 뒤 한 번 더 누르면 보낸다(사장님 11-11 '한 번 더 누르면 보내기'). 넘김 메모는 같은 미답 묶음의 첫 차례에만 붙어
     (:func:`.handoff_memo._repeated`) 지금 규칙이면 손님이 이어 쓰는 상담에서 [배우기]가 늘 막힌다.
  3. 보낸 글은 '직접 답'(AI 초안 없음 — :func:`.send_record.sent_case` ``direct``)으로 적는다. 그날 밤 넘김 학습
     (:mod:`.handoff_learning`)이 이 차례를 늘 사람 몫인 까닭(주문 조회 · 불만 · 환불 …)이어도 읽는다(직원이 배우라고 골랐다).
- **[흘리기]** (:func:`skip_learning`) — 끝난 꼴 '버림'. 학습 · 비슷한 사례 고르기 · 사진 학습 · 지식 백필이 모두 이 값을 뺀다.
  손님께는 아무것도 안 간다. **[배우기로 바꾸기]** (:func:`unskip_learning`)는 보냈던 차례면 '직접 답', 아니면 비움(보통 규칙)으로.
- 같은 상담의 다른 차례(뒤에 온 초안 메모)가 보내는 중이면 '확인 중'(:func:`.send_record.chat_busy` — 상담 줄 잠금).

결과는 :class:`HandoffResult` — 코드 · HTTP 상태 · 숫자와 코드뿐인 ``data``. 보낼 글 · 손님 글은 싣지 않는다(로그도).
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from sqlalchemy import case, or_, update

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.case_memory import OUTCOME_DIRECT, OUTCOME_DISCARDED
from foms.services.cs_agent.channel_read import ChannelReadError, OpenApiReader, naive_utc
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.drafting_read import (
    MEMO_NOTE_HEAD, ChatLine, customer_texts, memo_snippets, read_lines, read_medium,
)
from foms.services.cs_agent.handoff_learning import used_ids
from foms.services.cs_agent.handoff_memo import PHOTO_READ_TEXT, REASON_LABEL, reason_text
from foms.services.cs_agent.handoff_memo_settings import handoff_buttons_on
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.ontology import with_ontology
from foms.services.cs_agent.quote_record import allowed_from
from foms.services.cs_agent.send import send_reply
from foms.services.cs_agent.send_auth import confirm_matches, confirm_stamp
from foms.services.cs_agent.send_flow import (
    HARD_CODES, MAX_TEXT, MESSAGES, MODE_EDITED, FlowResult, SendRequest, _audited, _back, _gate, _problems, _record,
    _shown_ms, _validate, switch_on,
)
from foms.services.cs_agent.send_record import (
    HANDOFF_CODES, NOT_TAUGHT_REASONS, SEND_FAILED, SEND_SENDING, SEND_SENT, SEND_UNKNOWN_STATE, chat_busy,
    revert_sending, sent_case, start_sending, still_sending,
)
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import STATE_SKIPPED

logger = logging.getLogger(__name__)

__all__ = ["HANDOFF_MESSAGES", "HandoffResult", "handoff_view", "send_handoff", "skip_learning", "unskip_learning"]

#: 결과 코드 → 작은 창 글(해요체 — 글 · 손님 정보 없음). 없는 코드는 초안 [보내기] 글(:data:`.send_flow.MESSAGES`).
HANDOFF_MESSAGES: dict[str, str] = {
    "write": "손님께 보낼 답을 직접 써 주세요. 보내면 오늘 밤 AI가 이 답을 배워요.",
    "sent": "손님께 보냈어요. 오늘 밤 이 답을 배워요.",
    "learn_sent": "이미 이 창으로 보냈어요. 배우지 않게 하려면 [흘리기]를 눌러 주세요.",
    "skipped": "흘렸어요. 이 상담은 배우지 않고, 비슷한 사례로도 안 써요.",
    "skipped_learned": "흘렸어요. 다만 이 상담은 이미 지난밤에 배웠어요 — 회사 지식 받은 함의 안은 거절해 주세요.",
    "is_skipped": "흘리기로 돼 있어요. 배우려면 [배우기로 바꾸기]를 눌러 주세요.",
    "unskipped_open": "배우기로 바꿨어요. 답을 써서 보내 주세요.",
    "unskipped_sent": "배우기로 바꿨어요. 보낸 답을 오늘 밤 배워요.",
    "unskipped_desk": "배우기로 바꿨어요. 데스크에서 보낸 답은 보통 규칙대로 배워요.",
    "not_skipped": "흘린 상담이 아니에요.",
    "answered": "이미 직원 답이 나간 상담이에요. 이 창으로는 보내지 않았어요.",
    "new_message": "그사이 손님이 새 글을 썼어요. 데스크에서 읽어 보고, 답이 맞으면 [보내기]를 한 번 더 눌러 주세요.",
    "already": "이미 처리된 상담이에요(보냄 · 처리 중).",
    "not_open": "이 메모로는 더 할 수 없어요. 새 메모의 단추를 써 주세요.",
    "not_found": "상담을 찾지 못했어요.",
    "buttons_off": "지금은 [배우기] · [흘리기]가 꺼져 있어요(관리 화면).",
}
#: 창을 열 때 손님이 메모 뒤에 더 썼으면 보이는 알림(막지 않는다).
MORE_NOTE = "메모 뒤에 손님이 글을 더 썼어요. 데스크에서 읽어 보고 써 주세요."


@dataclass(frozen=True)
class HandoffResult(FlowResult):
    """넘김 메모 결과 — 화면 글만 :data:`HANDOFF_MESSAGES` 를 먼저 본다."""

    @property
    def message(self) -> str:
        """화면 글."""
        return HANDOFF_MESSAGES.get(self.code) or MESSAGES.get(self.code, MESSAGES["bad_request"])


def _r(code: str, status: int, **data: Any) -> HandoffResult:
    return HandoffResult(code, status, data)


def _as_handoff(result: FlowResult) -> HandoffResult:
    return result if isinstance(result, HandoffResult) else HandoffResult(result.code, result.status, dict(result.data))


def _is_handoff_turn(row: Any) -> bool:
    """넘김 메모가 붙은 건너뜀 차례인가('AI 냐' 한 줄 메모 차례는 아니다)."""
    return (row.state == STATE_SKIPPED and row.error_code in HANDOFF_CODES and bool(row.memo_message_id)
            and row.handoff_reason not in NOT_TAUGHT_REASONS)


def _buttons_on(session: Any) -> bool:
    return handoff_buttons_on(read_settings(session, log=False))


# ── 상담 글 읽기 판정 ────────────────────────────────────────────────────
def _customers(lines: list[ChatLine]) -> list[ChatLine]:
    return [line for line in lines if line.meta.is_customer_signal]


def _answered(lines: list[ChatLine], claimed_id: Any) -> Optional[bool]:
    """그 손님 글 뒤에 공개 답(직원 · 우리 봇)이 있는가 — 그 손님 글을 못 찾으면 ``None``."""
    anchor = next((line for line in _customers(lines) if line.meta.message_id == claimed_id), None)
    if anchor is None:
        return None
    return any(line.meta.is_answer and line.key > anchor.key for line in lines)


def _latest(lines: list[ChatLine]) -> Optional[str]:
    """지금 마지막 손님 글 id."""
    customers = _customers(lines)
    return customers[-1].meta.message_id if customers else None


def _memo(lines: list[ChatLine], memo_id: Any) -> Optional[ChatLine]:
    """그 차례의 넘김 메모 줄(비공개 — 없으면 ``None``)."""
    return next((line for line in lines if line.meta.message_id == memo_id and line.meta.is_private), None)


def _hint(lines: list[ChatLine], memo_id: Any) -> str:
    """넘김 메모의 직원 참고 칸(이미 가린 글 — 없으면 빈 글)."""
    memo = _memo(lines, memo_id)
    if memo is None or MEMO_NOTE_HEAD not in memo.text:
        return ""
    return memo.text.split(MEMO_NOTE_HEAD, 1)[1].strip()


def _reason(row: Any, lines: list[ChatLine]) -> str:
    """창의 까닭 — 메모와 같은 말. 사진을 읽었는지는 메모를 올린 차례만 알아서, 메모가 '사진은 읽었지만'이면 그 말을 쓴다."""
    memo = _memo(lines, row.memo_message_id)
    read = memo is not None and REASON_LABEL + PHOTO_READ_TEXT in memo.text.splitlines()
    return reason_text(row.error_code, handoff_reason=row.handoff_reason, check_codes=row.check_codes or (),
                       photos_read=read)


# ── 창 재료(cs.handoff.get) ──────────────────────────────────────────────
def _state(row: Any, answered: Optional[bool]) -> str:
    """창 상태 — checking · learn_sent · answered · is_skipped · write."""
    if row.send_state in (SEND_SENDING, SEND_UNKNOWN_STATE):
        return "checking"
    if row.send_state == SEND_SENT:
        return "learn_sent"
    if answered:
        return "answered"
    if row.outcome == OUTCOME_DISCARDED:
        return "is_skipped"
    return "answered" if row.outcome is not None else "write"


def handoff_view(session: Any, turn_id: int, *, chat_hint: Any, manager_id: Any, reader: Any = None) -> HandoffResult:
    """[배우기] 창 재료 — 상태 · 까닭 · 힌트(가린 직원 참고) · 본 마지막 손님 글 id · 글자 상한. DB 는 읽기만 한다."""
    if not manager_id:
        return _r("token", 403, reason="no_manager")
    row = session.get(CsAgentTurn, int(turn_id), populate_existing=True)
    session.rollback()
    if row is None or not isinstance(chat_hint, str) or chat_hint != row.chat_id:
        return _r("not_found", 404)
    if not _is_handoff_turn(row):
        return _r("not_open", 409)
    _row, denied = _gate(session, row.id, None, "", None, need_switch=False, manager_id=str(manager_id),
                         chat_id=chat_hint)
    session.rollback()
    if denied is not None:
        return _as_handoff(denied)
    try:
        lines = read_lines(reader if reader is not None else OpenApiReader(), row.brand, row.chat_id)
    except ChannelReadError as exc:
        logger.warning("[CS 배우기] 상담 글 읽기 실패 turn=%s status=%s", row.id, exc.status)
        return _r("read_failed", 503)
    reason = _reason(row, lines)
    answered = _answered(lines, row.last_user_message_id)
    state = _state(row, answered)
    if state == "write":
        state = "buttons_off" if not _buttons_on(session) else "write" if switch_on(session) else "switch_off"
    session.rollback()
    seen = _latest(lines)
    more = state == "write" and seen is not None and seen != row.last_user_message_id
    return _r(state, 200, reason=reason, hint=_hint(lines, row.memo_message_id), seen=seen, max_text=MAX_TEXT,
              note=MORE_NOTE if more else None)


# ── [보내기](cs.handoff.send) ────────────────────────────────────────────
def _closed(row: Any) -> Optional[HandoffResult]:
    """더 보낼 수 없는 차례면 그 결과."""
    if not _is_handoff_turn(row):
        return _r("not_open", 409)
    if row.send_state in (SEND_SENDING, SEND_UNKNOWN_STATE):
        return _r("checking", 202)
    if row.send_state == SEND_SENT:
        return _r("learn_sent", 409)
    if row.outcome == OUTCOME_DISCARDED:
        return _r("is_skipped", 409)
    return _r("answered", 409) if row.outcome is not None else None


def send_handoff(session: Any, request: SendRequest, *, secret_key: Any, now: datetime.datetime, seen: Any = None,
                 reader: Any = None, sender: Callable[..., Any] = send_reply) -> HandoffResult:
    """[배우기] 창 [보내기] 한 번 + 감사 원장 한 줄(``CS_AGENT_SEND`` · ``kind=handoff``). 커밋한다. 작은 창 길만(``manager_id``)."""
    result = _send(session, request, secret_key=secret_key, now=now, seen=seen, reader=reader, sender=sender)
    return _as_handoff(_audited(session, "CS_AGENT_SEND", request.turn_id, request.user_id, result,
                                manager_id=request.manager_id, kind="handoff"))


def _send(session: Any, request: SendRequest, *, secret_key: Any, now: datetime.datetime, seen: Any, reader: Any,
          sender: Callable[..., Any]) -> FlowResult:
    if request.manager_id is None:
        return _r("token", 403, reason="no_manager")
    request = replace(request, mode=MODE_EDITED, edit_reason=None)
    row, denied = _gate(session, request.turn_id, request.user_id, "", secret_key, manager_id=request.manager_id,
                        chat_id=request.chat_id)
    closed = denied or _closed(row) or _validate(request)
    if closed is None and not _buttons_on(session):
        closed = _r("buttons_off", 409)
    if closed is None and chat_busy(session, row):
        closed = _r("checking", 202)
    if closed is not None:
        session.rollback()
        return closed
    previous = row.send_state
    if not start_sending(session, row, user_id=request.user_id, manager_id=request.manager_id,
                         click_ms=_shown_ms(request.shown_ms), now=now, handoff=True):
        session.rollback()
        return _r("already", 409)
    session.commit()  # ① '보내는 중'을 채널톡을 부르기 전에 커밋한다(상담 줄 잠금도 여기서 풀린다)
    logger.info("[CS 배우기] 보내는 중 turn=%s", row.id)
    called: list[bool] = []
    try:
        return _started(session, row, request, previous=previous, now=now, seen=seen, called=called,
                        secret_key=secret_key, reader=reader if reader is not None else OpenApiReader(), sender=sender)
    except Exception:
        session.rollback()
        if not called:
            revert_sending(session, row.id, back_to=previous if previous == SEND_FAILED else None, error="error",
                           now=now)
            session.commit()
        logger.error("[CS 배우기] 보내는 중 예상 밖 오류 turn=%s called=%s", row.id, bool(called))
        raise


def _started(session: Any, row: Any, request: SendRequest, *, previous: Optional[str], now: datetime.datetime,
             seen: Any, reader: Any, sender: Callable[..., Any], called: list[bool], secret_key: Any) -> FlowResult:
    """② 최신인가(답 나감은 막고 손님 새 글은 한 번 더) → ③ 검사 → ④ 보내기 → ⑤ 결과."""
    try:
        lines = read_lines(reader, row.brand, row.chat_id)
        medium = read_medium(reader, row.brand, row.chat_id)
    except ChannelReadError as exc:
        logger.warning("[CS 배우기] 상담 글 읽기 실패 turn=%s status=%s", row.id, exc.status)
        return _back(session, row, previous, "read_failed", now, _r("read_failed", 503))
    answered = _answered(lines, row.last_user_message_id)
    if answered is None:
        return _back(session, row, previous, "not_visible", now, _r("read_failed", 503, reason="not_visible"))
    if answered:
        return _back(session, row, previous, "answered", now, _r("answered", 409))
    latest = _latest(lines)
    if latest != (seen if isinstance(seen, str) and seen else row.last_user_message_id):
        return _back(session, row, previous, "stale", now, _r("new_message", 409, seen=latest))
    text = (request.text or "").strip()
    knowledge = with_ontology(session, load_approved(session, row.brand))
    quote_allowed = allowed_from(row.quote_lines)
    session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡을 부르는 동안 열어 두지 않는다
    check = check_draft(text, brand=row.brand, medium=medium, private_snippets=memo_snippets(lines),
                        allowed_numbers=(*knowledge.spoken_texts(), *quote_allowed), same_values=knowledge.same_values(),
                        customer_texts=customer_texts(lines))
    hard = [p for p in check.problems if p.code in HARD_CODES]
    soft = [p for p in check.problems if p not in hard]
    if hard:
        return _back(session, row, previous, "check_failed", now, _r("blocked", 422, problems=_problems(hard)))
    stamp = {"turn_id": row.id, "user_id": request.who, "text": text, "codes": [p.code for p in soft]}
    if soft and not confirm_matches(secret_key, request.confirm, **stamp):
        return _back(session, row, previous, "needs_confirm", now, _r(
            "needs_confirm", 409, warnings=_problems(soft), confirm=confirm_stamp(secret_key, **stamp)))
    if not (switch_on(session) and _buttons_on(session)):  # ④ 바로 앞 — 그사이 꺼졌으면 보내지 않는다
        return _back(session, row, previous, "switch_off", now, _r("switch_off", 409))
    if not still_sending(session, row.id):
        session.commit()
        return _r("checking", 202)
    session.commit()
    called.append(True)
    sent = sender(row.chat_id, text, brand=row.brand, turn_id=row.id)
    case_fields = sent_case(lines, ai_draft=None, sent_text=text, edited=False, edit_reason=None, direct=True)
    return _record(session, row, sent, case_fields, text=text, now=now, warned=[p.code for p in soft])


# ── [흘리기] · [배우기로 바꾸기] ─────────────────────────────────────────
def _open_for_choice(session: Any, turn_id: int, *, chat_id: Any, manager_id: Any,
                     user_id: Optional[int]) -> tuple[Optional[Any], Optional[HandoffResult]]:
    if not manager_id:
        return None, _r("token", 403, reason="no_manager")
    row, denied = _gate(session, turn_id, user_id, "", None, need_switch=False, manager_id=str(manager_id),
                        chat_id=chat_id)
    if denied is not None:
        return None, _as_handoff(denied)
    if not _is_handoff_turn(row):
        return None, _r("not_open", 409)
    if row.send_state in (SEND_SENDING, SEND_UNKNOWN_STATE):
        return None, _r("checking", 202)
    return row, None


def _choice_where(row: Any) -> tuple[Any, ...]:
    turns = CsAgentTurn.__table__
    return (turns.c.id == row.id, turns.c.state == STATE_SKIPPED, turns.c.error_code.in_(HANDOFF_CODES),
            or_(turns.c.send_state.is_(None), turns.c.send_state.notin_((SEND_SENDING, SEND_UNKNOWN_STATE))))


def skip_learning(session: Any, *, turn_id: int, chat_id: Any, manager_id: Any, user_id: Optional[int] = None,
                  now: datetime.datetime) -> HandoffResult:
    """[흘리기] — 끝난 꼴 '버림'(학습 · 비슷한 사례에서 빠진다). 손님께는 아무것도 가지 않는다. 커밋한다."""
    row, denied = _open_for_choice(session, turn_id, chat_id=chat_id, manager_id=manager_id, user_id=user_id)
    if denied is not None:
        session.rollback()
        return denied
    turns = CsAgentTurn.__table__
    done = session.execute(update(turns).where(*_choice_where(row), or_(turns.c.outcome.is_(None),
                                                                        turns.c.outcome != OUTCOME_DISCARDED))
                           .values(outcome=OUTCOME_DISCARDED, updated_at=naive_utc(now))).rowcount == 1
    session.commit()
    learned = row.id in used_ids(session)
    session.rollback()
    result = _r("skipped_learned" if learned else "skipped", 200, changed=done)
    logger.info("[CS 배우기] 흘림 turn=%s changed=%s learned=%s", row.id, done, learned)
    return _as_handoff(_audited(session, "CS_AGENT_HANDOFF_SKIP", row.id, user_id, result, manager_id=str(manager_id)))


def unskip_learning(session: Any, *, turn_id: int, chat_id: Any, manager_id: Any, user_id: Optional[int] = None,
                    now: datetime.datetime) -> HandoffResult:
    """[배우기로 바꾸기] — 흘린 차례를 보냈으면 '직접 답', 아니면 비움(보통 규칙 — 사례 기억이 다시 본다). 커밋한다."""
    row, denied = _open_for_choice(session, turn_id, chat_id=chat_id, manager_id=manager_id, user_id=user_id)
    if denied is not None:
        session.rollback()
        return denied
    turns = CsAgentTurn.__table__
    done = session.execute(update(turns).where(*_choice_where(row), turns.c.outcome == OUTCOME_DISCARDED)
                           .values(outcome=case((turns.c.send_state == SEND_SENT, OUTCOME_DIRECT), else_=None),
                                   updated_at=naive_utc(now))).rowcount == 1
    session.commit()
    if not done:
        return _as_handoff(_audited(session, "CS_AGENT_HANDOFF_UNSKIP", row.id, user_id, _r("not_skipped", 409),
                                    manager_id=str(manager_id)))
    code = ("unskipped_sent" if row.send_state == SEND_SENT
            else "unskipped_desk" if row.staff_reply_masked else "unskipped_open")
    logger.info("[CS 배우기] 배우기로 바꿈 turn=%s code=%s", row.id, code)
    return _as_handoff(_audited(session, "CS_AGENT_HANDOFF_UNSKIP", row.id, user_id, _r(code, 200),
                                manager_id=str(manager_id)))
