"""[보내기] · [수정하기] — web 이 직접 손님께 보낸다(모델을 부르지 않는다) · 버리기 · '고칠 말' 요청 · 결과 맞추기.

플랜 C10-3 · 설계서 17.2('누를 때 서버가 확인하는 것' 1~5 · 되먹임 막기 · 직원 정보) · 17.2.1(링크 길) · 원장 R10-9 ~ R10-11 ·
R10-16 · D68 · D69. 화면(``foms/web/cs_agent_send.py``)과 JSON API(``foms/api/cs_agent_send.py``)가 이 모듈만 부른다.

:func:`send_turn` 순서(고정):

0. **앞 확인(쓰기 없음)** — 서명 표(그 차례 · 그 직원 · 지금 메모 · 30분) 또는 서명된 채널톡 상담원(작은 창 길 — 앱 함수 받는
   곳이 서명 · 라홈 채널 · 상담원 caller 를 이미 봤다, 설계서 17.2.2 — 이때는 작은 창이 받은 상담 id 가 차례와 같아야 한다) ·
   라홈만(하우드는 쓰기 허락 전) · 운영 밖은 시험 상담 허용 목록만 · 스위치(관리 화면 '[보내기] · [수정하기] 버튼' 켬 · 비상
   정지 아님) · 차례(메모 올림 · 끝난 꼴 없음 · 아직 안 보냄).
1. **한 번만** — '보내는 중'을 조건부 쓰기로 먼저 커밋한다(:func:`.send_record.start_sending` — 두 번 누름 · 두 사람 동시엔 하나).
2. **최신인가** — 채널톡 Open API 로 그 상담 최근 글을 읽어 선점한 손님 글이 아직 마지막이고 그 뒤 공개 직원 답이 없을 때만
   (DB 상태 표는 늦다 — R10-11). 아니면 되돌리고 '새 글이 있어요'.
3. **검사** — 보낼 글: 그대로 = 그 메모를 다시 읽은 '손님께 보낼 답'(:func:`.drafting_read.memo_draft` — DB 에는 가린 사본만),
   고침 = 화면 입력. 그대로면 :func:`.checks.check_draft` 전체(걸리면 막음). 고친 글은 확실한 위험(:data:`HARD_CODES` — 다른
   브랜드 · 계좌 · 가림 표시 · 내부 메모 글 · 내부 말 · AI 표시 · 사람인 척)과 **AI 초안에 이미 있던 문제 코드**(검수 R15-3 — 한
   글자 고쳐 전체 검사를 피하지 못하게)만 막고, 나머지(맞춤 금액 · 날짜 · 약속 …)는 '확인 후 보내기' 경고 — 그 글 · 그 경고에
   묶인 확인표(:func:`.send_auth.confirm_stamp`)를 들고 한 번 더 눌러야 보낸다(R10-16 · R15-1).
4. **보내기** — 보내기 감싸개(:func:`.send.send_reply` — 봇 이름 공개 글 · requestId = 차례 id). 바로 앞에서 스위치와 '보내는 중'을
   한 번 더 본다(그사이 맞추기 · 다른 쪽이 바꿨으면 부르지 않는다 — R15-4). '고칠 말' 처리 중엔 보내지 않는다(R15-5).
5. **결과** — 보냄: 보낸 글 id · 끝난 꼴(그대로 · 고침) · 고친 정도 · 까닭(안 고르면 비움) · 보낸 직원 · 보낸 때 + 상태 표 '답'(약속 칸 포함). 모름:
   다시 보내지 않고 '확인 중'(requestId 로 맞춘다 — :func:`reconcile_one` · 빠른 길 바퀴). 거절: '못 보냄'(다시 누를 수 있다). 결과를
   못 적었으면(그사이 줄이 바뀜) '보냈어요'라 하지 않고 '확인 중'.

결과는 :class:`FlowResult`(코드 · HTTP 상태 · 숫자와 코드뿐인 ``data``) — 손님 글 · 보낼 글은 싣지 않는다. 로그도 차례 id · 코드만.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import or_, update
from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.case_memory import EDIT_REASONS, OUTCOME_DISCARDED
from foms.services.cs_agent.channel_read import ChannelReadError, OpenApiReader, naive_utc
from foms.services.cs_agent.checks import REASONS, check_draft
from foms.services.cs_agent.drafting_read import freshness, memo_draft, memo_snippets, read_lines, read_medium
from foms.services.cs_agent.knowledge import load_approved
from foms.services.cs_agent.masking import MaskLeak
from foms.services.cs_agent.memo import memo_allowed
from foms.services.cs_agent.quote_record import allowed_from
from foms.services.cs_agent.send import SEND_BRAND, send_reply
from foms.services.cs_agent.send_auth import SendTokenError, check_send_token, confirm_matches, confirm_stamp
from foms.services.cs_agent.send_record import (
    REWRITE_WORKING, SEND_FAILED, SEND_SENDING, SEND_SENT, SEND_UNKNOWN_STATE, chat_busy, finish_sent, mark_send_failed,
    mark_unknown, open_turn, reconcile_turn, record_answer, revert_sending, sent_case, start_sending, still_sending,
)
from foms.services.cs_agent.settings import read_settings
from foms.services.cs_agent.turns import DRAFT_MEMO, STATE_POSTED, draft_mode, read_switch
from foms.services.cs_agent.turns_fields import masked_or_none
from models import SecurityLog

logger = logging.getLogger(__name__)

__all__ = [
    "HARD_CODES", "MAX_NOTE", "MAX_REWRITES", "MAX_TEXT", "MESSAGES", "MODE_AS_IS", "MODE_EDITED", "FlowResult",
    "SendRequest", "discard_turn", "edit_reason_or_none", "reconcile_one", "request_rewrite", "send_turn", "switch_on",
    "turn_status",
]

MODE_AS_IS, MODE_EDITED = "as_is", "edited"
#: 고친 글 · '고칠 말' 길이 상한(글자).
MAX_TEXT, MAX_NOTE = 1000, 300
#: 한 차례에 '고칠 말'로 다시 쓰는 상한(두뇌 돈 · 데스크 메모 수).
MAX_REWRITES = 3
#: 화면이 보인 때부터 누를 때까지 밀리초로 받는 상한(넘으면 비운다 — 하루).
MAX_SHOWN_MS = 24 * 60 * 60 * 1000
#: 사람이 고친 글에서도 막는 확실한 위험(R10-16) — 나머지 검사 코드는 '확인 후 보내기' 경고다.
HARD_CODES = frozenset({"empty", "other_brand", "account_number", "mask_marker", "private_memo_leak", "internal_words",
                        "ai_mention", "human_claim"})
#: 결과 코드 → 화면 글(글 · 손님 정보 없음).
MESSAGES: dict[str, str] = {
    "sent": "손님께 보냈어요.",
    "checking": "보냈는지 확인하고 있어요 — 다시 누르지 말고 잠시 기다려 주세요.",
    "new_message": "그사이 새 글이 있어요 — 데스크에서 새 글을 보고 다시 판단해 주세요(보내지 않았어요).",
    "needs_confirm": "확인이 필요한 곳이 있어요 — 내용이 맞으면 '확인 후 보내기'를 한 번 더 눌러 주세요.",
    "blocked": "보낼 수 없는 내용이 있어요 — 고친 뒤 다시 눌러 주세요(보내지 않았어요).",
    "already": "이미 처리된 초안이에요(보냄 · 버림 · 처리 중).",
    "not_open": "더는 보낼 수 없는 초안이에요(지난 초안 · 직원 답함).",
    "switch_off": "지금은 보내기가 꺼져 있어요(관리 화면 스위치 · 비상 정지).",
    "not_allowed": "이 상담은 보내기가 허락되지 않았어요(하우드 · 시험 상담 밖).",
    "rewriting": "AI 가 고칠 말로 다시 쓰는 중이에요 — 잠시 뒤 새 초안으로 바뀝니다(그때 보내 주세요).",
    "token": "화면이 오래됐어요 — 새로 열어 주세요.",
    "failed": "채널톡이 받지 않았어요 — 잠시 뒤 다시 눌러 주세요.",
    "read_failed": "채널톡 글을 읽지 못했어요 — 잠시 뒤 다시 눌러 주세요(보내지 않았어요).",
    "memo_missing": "채널톡에서 이 초안 메모를 찾지 못했어요 — 수정하기로 글을 넣어 보내 주세요.",
    "bad_request": "입력을 확인해 주세요.",
    "not_found": "초안을 찾지 못했어요.",
    "discarded": "초안을 버렸어요.",
    "rewrite_requested": "고칠 말을 받았어요 — AI 가 다시 쓰면 이 화면이 새 초안으로 바뀝니다.",
    "rewrite_off": "지금은 AI 다시 쓰기를 못 해요(빠른 길 · 내부 메모 스위치 확인).",
}


@dataclass(frozen=True)
class FlowResult:
    """결과 — 코드 · HTTP 상태 · 화면 재료(코드 · 숫자만)."""

    code: str
    status: int
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """성공 꼴(보냄 · 확인 중 · 버림 · 다시 쓰기 받음)인가."""
        return self.status < 300

    @property
    def message(self) -> str:
        """화면 글."""
        return MESSAGES.get(self.code, MESSAGES["bad_request"])


@dataclass(frozen=True)
class SendRequest:
    """[보내기] 요청 — 고친 글은 repr 에 싣지 않는다.

    FOMS 화면 길은 ``user_id`` + ``token``(서명 표). 채널톡 작은 창 길은 ``manager_id``(서명된 caller — 앱 함수 받는 곳만 채운다)
    + ``chat_id``(작은 창이 받은 상담 id)이고 ``user_id`` 는 FOMS 짝이 있을 때만이다. ``manager_id`` 가 비면 늘 표를 본다.
    """

    turn_id: int
    user_id: Optional[int]
    token: str = field(default="", repr=False)
    mode: str = MODE_AS_IS
    text: Optional[str] = field(default=None, repr=False)
    edit_reason: Optional[str] = None
    confirm: Any = None  # '확인 후 보내기' 확인표(needs_confirm 응답의 confirm — 참 · 거짓 칸이 아니다, R15-1)
    shown_ms: Optional[int] = None
    manager_id: Optional[str] = None
    chat_id: Optional[str] = None

    @property
    def who(self) -> Any:
        """확인표가 묶는 사람 — FOMS 직원 번호, 작은 창 길이면 채널톡 상담원 번호."""
        return self.user_id if self.manager_id is None else f"m:{self.manager_id}"


def _fail(code: str, status: int, **data: Any) -> FlowResult:
    return FlowResult(code, status, data)


def _audited(session: Any, action: str, turn_id: int, user_id: Optional[int], result: FlowResult, *,
             manager_id: Optional[str] = None, kind: Optional[str] = None) -> FlowResult:
    """감사 원장 한 줄(누가 · 어느 차례 · 결과 코드 — 글 없음)을 남기고 결과를 그대로 돌려준다. 못 남겨도 결과는 그대로다.
    작은 창 길은 채널톡 상담원 번호를 같이 적는다(FOMS 짝이 없으면 직원 번호는 비운다). ``kind`` 는 길 표지(넘김 메모
    [배우기] — ``handoff``)."""
    detail: dict[str, Any] = {"code": result.code, "status": result.status}
    if kind is not None:
        detail["kind"] = kind
    if manager_id is not None:
        detail.update(via="wam", channel_manager=str(manager_id))
    try:
        session.add(SecurityLog(user_id=None if user_id is None else int(user_id), action=action,
                                target_type="cs_agent_turn", target_id=int(turn_id),
                                message=f"{action} turn={int(turn_id)} code={result.code}", detail=detail))
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 보내기] 감사 원장을 못 남겼다 action=%s turn=%s", action, turn_id)
    return result


def switch_on(session: Any) -> bool:
    """보내기 스위치 — 관리 화면 버튼 칸 켬 · 비상 정지 아님(DB 에서 새로 읽는다)."""
    return bool(read_settings(session, log=False).get("send_buttons_enabled")) and read_switch(session)


def turn_status(row: Any) -> dict[str, Any]:
    """화면 · 상태 API 재료 — 상태 코드 · 메모 id 만(글 · 상담 id 없음)."""
    return {"state": row.state, "send_state": row.send_state, "outcome": row.outcome, "send_error": row.send_error,
            "rewrite_state": row.rewrite_state, "rewrite_count": int(row.rewrite_count or 0),
            "memo_id": row.memo_message_id}


def _gate(session: Any, turn_id: int, user_id: Optional[int], token: Any, secret_key: Any, *,
          need_switch: bool = True, manager_id: Optional[str] = None,
          chat_id: Optional[str] = None) -> tuple[Optional[Any], Optional[FlowResult]]:
    """앞 확인(쓰기 없음) — 차례 · 표(또는 서명된 상담원 + 같은 상담) · 라홈 · 허용 목록 · 스위치. ``(줄, None)`` 또는
    ``(None, 결과)``."""
    row = session.get(CsAgentTurn, int(turn_id), populate_existing=True)
    if row is None:
        return None, _fail("not_found", 404)
    if manager_id is None:
        if user_id is None:
            return None, _fail("token", 403, reason="no_user")
        try:
            check_send_token(secret_key, token, turn_id=row.id, user_id=user_id, memo_id=row.memo_message_id)
        except SendTokenError as exc:
            return None, _fail("token", 403, reason=exc.code)
    elif not isinstance(chat_id, str) or chat_id != row.chat_id:  # 작은 창이 연 상담의 차례가 아니면 없는 차례로
        return None, _fail("not_found", 404)
    if row.brand != SEND_BRAND or not memo_allowed(row.chat_id):
        return None, _fail("not_allowed", 403)
    if need_switch and not switch_on(session):
        return None, _fail("switch_off", 409)
    return row, None


def _closed(row: Any) -> Optional[FlowResult]:
    """더 할 일이 없는 차례면 그 결과 — 보내는 중 · 모름은 '확인 중', 보냄 · 버림은 '이미', 지난 초안 등은 '못 보냄'."""
    if row.send_state in (SEND_SENDING, SEND_UNKNOWN_STATE):
        return _fail("checking", 202, **turn_status(row))
    if row.send_state == SEND_SENT or row.outcome is not None:
        return _fail("already", 409, **turn_status(row))
    if row.state != STATE_POSTED or not row.memo_message_id:
        return _fail("not_open", 409, **turn_status(row))
    if row.rewrite_state == REWRITE_WORKING:
        return _fail("rewriting", 409, **turn_status(row))
    return None


def _shown_ms(value: Any) -> Optional[int]:
    """누름 밀리초 — 0 이상 정수만(아니면 비움)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_SHOWN_MS else None


def edit_reason_or_none(value: Any) -> Any:
    """고친 까닭 — 안 고름(``None`` · 빈 글)은 ``None``, 나머지는 그대로(꼴은 :func:`_validate` 가 본다)."""
    return None if value is None or value == "" else value


def _validate(request: SendRequest) -> Optional[FlowResult]:
    """요청 꼴 — 고친 글은 1~:data:`MAX_TEXT` 자. 고친 까닭은 고르지 않아도 된다(``None`` 으로 둔다 — 운영에서 까닭을 안
    골라 [보내기]가 안 됐다, 2026-11 C10-7). 고른 까닭은 :data:`.case_memory.EDIT_REASONS` 가운데 하나여야 한다."""
    if request.mode not in (MODE_AS_IS, MODE_EDITED):
        return _fail("bad_request", 400, field="mode")
    if request.mode == MODE_EDITED:
        text = request.text if isinstance(request.text, str) else ""
        if not text.strip() or len(text) > MAX_TEXT:
            return _fail("bad_request", 400, field="text")
        reason = edit_reason_or_none(request.edit_reason)
        if reason is not None and reason not in EDIT_REASONS:
            return _fail("bad_request", 400, field="edit_reason")
    return None


def _problems(items: Any) -> list[dict[str, Any]]:
    """검사 결과 → 화면 줄(코드 · 짧은 이유 · 수)."""
    return [{"code": p.code, "reason": REASONS.get(p.code, p.code), "count": p.count} for p in items]


def send_turn(session: Any, request: SendRequest, *, secret_key: Any, now: datetime.datetime, reader: Any = None,
              sender: Callable[..., Any] = send_reply) -> FlowResult:
    """[보내기] 한 번 + 감사 원장 한 줄(:func:`_send_turn`)."""
    result = _send_turn(session, request, secret_key=secret_key, now=now, reader=reader, sender=sender)
    return _audited(session, "CS_AGENT_SEND", request.turn_id, request.user_id, result, manager_id=request.manager_id)


def _send_turn(session: Any, request: SendRequest, *, secret_key: Any, now: datetime.datetime, reader: Any,
               sender: Callable[..., Any]) -> FlowResult:
    """[보내기] 한 번(모듈 설명의 순서). 커밋한다.

    Args:
        session: DB 세션.
        request: :class:`SendRequest`(신뢰하지 않는다 — 꼴을 본다).
        secret_key: 앱 비밀 키(서명 표).
        now: 지금(시간대 있는 값).
        reader: 채널톡 Open API 읽기 도우미(시험은 가짜 — 없으면 기본).
        sender: 보내기 감싸개(시험은 가짜).

    Returns:
        :class:`FlowResult`.
    """
    row, denied = _gate(session, request.turn_id, request.user_id, request.token, secret_key,
                        manager_id=request.manager_id, chat_id=request.chat_id)
    if denied is not None:
        session.rollback()
        return denied
    closed = _closed(row) or _validate(request)
    if closed is not None:
        session.rollback()
        return closed
    if chat_busy(session, row):  # 같은 상담의 다른 차례(넘김 메모 [배우기])가 보내는 중 — 손님께 두 번 가지 않게
        session.rollback()
        return _fail("checking", 202)
    previous = row.send_state
    if not start_sending(session, row, user_id=request.user_id, manager_id=request.manager_id,
                         click_ms=_shown_ms(request.shown_ms), now=now):
        session.rollback()
        return _fail("already", 409)
    session.commit()  # ① '보내는 중'을 채널톡을 부르기 전에 커밋한다 — 두 번 누름 · 두 사람 동시엔 하나만 여기를 지난다
    logger.info("[CS 보내기] 보내는 중 turn=%s mode=%s", row.id, request.mode)
    called: list[bool] = []
    try:
        return _send_started(session, row, request, previous=previous, now=now, called=called, secret_key=secret_key,
                             reader=reader if reader is not None else OpenApiReader(), sender=sender)
    except Exception:
        session.rollback()
        if not called:  # 채널톡을 부르기 전이면 되돌린다 — 부른 뒤면 결과를 모르니 맞추기(requestId)에 맡긴다
            revert_sending(session, row.id, back_to=previous if previous == SEND_FAILED else None, error="error",
                           now=now)
            session.commit()
        logger.error("[CS 보내기] 보내는 중 예상 밖 오류 turn=%s called=%s", row.id, bool(called))
        raise


def _back(session: Any, row: Any, previous: Optional[str], code: str, now: datetime.datetime,
          result: FlowResult) -> FlowResult:
    """보내지 않고 되돌린다(앞 상태로) — 결과를 그대로 돌려준다."""
    revert_sending(session, row.id, back_to=previous if previous == SEND_FAILED else None, error=code, now=now)
    session.commit()
    logger.info("[CS 보내기] 보내지 않고 되돌림 turn=%s code=%s", row.id, code)
    return result


def _send_started(session: Any, row: Any, request: SendRequest, *, previous: Optional[str], now: datetime.datetime,
                  reader: Any, sender: Callable[..., Any], called: list[bool], secret_key: Any) -> FlowResult:
    """② 최신인가 → ③ 검사 → ④ 보내기 → ⑤ 결과('보내는 중'을 커밋한 뒤)."""
    try:
        lines = read_lines(reader, row.brand, row.chat_id)
        medium = read_medium(reader, row.brand, row.chat_id)
    except ChannelReadError as exc:
        logger.warning("[CS 보내기] 상담 글 읽기 실패 turn=%s status=%s", row.id, exc.status)
        return _back(session, row, previous, "read_failed", now, _fail("read_failed", 503))
    stale = freshness(lines, row.last_user_message_id)
    if stale:
        return _back(session, row, previous, stale, now, _fail("new_message", 409, reason=stale))
    memo = next((line for line in lines if line.meta.message_id == row.memo_message_id and line.meta.is_private), None)
    ai_draft = memo_draft(memo.text) if memo is not None else None
    edited = request.mode == MODE_EDITED
    if not edited and ai_draft is None:
        return _back(session, row, previous, "memo_missing", now, _fail("memo_missing", 409))
    text = (request.text or "").strip() if edited else ai_draft
    edited = edited and text != (ai_draft or "").strip()
    knowledge = load_approved(session, row.brand)
    quote_allowed = allowed_from(row.quote_lines)  # 그 차례 계산기 값 — '계산됨 · 확인됨'일 때만(C10-6 · R17-1)
    session.commit()  # 읽기 트랜잭션을 닫는다 — 채널톡을 부르는 동안 열어 두지 않는다
    args = {"brand": row.brand, "medium": medium, "private_snippets": memo_snippets(lines),
            "allowed_numbers": (*knowledge.spoken_texts(), *quote_allowed)}
    check = check_draft(text, **args)
    kept = set(check_draft(ai_draft, **args).codes) if edited and ai_draft else set()  # AI 초안의 문제는 고쳐도 막는다
    hard = [p for p in check.problems if not edited or p.code in HARD_CODES or p.code in kept]
    soft = [p for p in check.problems if p not in hard]
    if hard:
        return _back(session, row, previous, "check_failed", now, _fail("blocked", 422, problems=_problems(hard)))
    stamp = {"turn_id": row.id, "user_id": request.who, "text": text, "codes": [p.code for p in soft]}
    if soft and not confirm_matches(secret_key, request.confirm, **stamp):
        return _back(session, row, previous, "needs_confirm", now, _fail(
            "needs_confirm", 409, warnings=_problems(soft), confirm=confirm_stamp(secret_key, **stamp)))
    if not switch_on(session):  # ④ 바로 앞 — 그사이 꺼졌으면(비상 정지 · 버튼 끔) 보내지 않는다
        return _back(session, row, previous, "switch_off", now, _fail("switch_off", 409))
    if not still_sending(session, row.id):  # 그사이 맞추기 · 다른 쪽이 줄을 바꿨다 — 부르지 않는다(R15-4)
        session.commit()
        return _fail("checking", 202)
    session.commit()
    called.append(True)
    sent = sender(row.chat_id, text, brand=row.brand, turn_id=row.id)
    case = sent_case(lines, ai_draft=ai_draft, sent_text=text, edited=edited,
                     edit_reason=edit_reason_or_none(request.edit_reason) if edited else None)
    return _record(session, row, sent, case, text=text, now=now, warned=[p.code for p in soft])


def _record(session: Any, row: Any, sent: Any, case: Any, *, text: str, now: datetime.datetime,
            warned: list[str]) -> FlowResult:
    """⑤ 결과 적기 — 보냄 · 모름(다시 안 보냄) · 못 보냄. 적기가 0 줄이면(그사이 줄이 바뀜) '확인 중'으로 답한다(R15-4)."""
    if sent.posted and sent.message_id:
        at = sent.created_at or now
        written = finish_sent(session, row.id, message_id=sent.message_id, sent_at=at, case=case, now=now)
        session.commit()  # 보낸 사실을 먼저 굳힌다 — 상태 표 '답'은 그다음(못 적어도 웹훅 · 보정이 채운다)
        if not written:
            logger.warning("[CS 보내기] 보냈지만 줄이 그사이 바뀌어 결과를 못 적었다 — 맞추기에 맡긴다 turn=%s", row.id)
            return _fail("checking", 202, message_id=sent.message_id)
        try:
            record_answer(session, brand=row.brand, chat_id=row.chat_id, message_id=sent.message_id, sent_at=at,
                          text=text, turn_id=row.id, now=now)
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.warning("[CS 보내기] 보낸 글을 상태 표 '답'으로 못 적었다(웹훅 · 보정이 채운다) turn=%s", row.id)
        logger.info("[CS 보내기] 보냄 turn=%s message=%s outcome=%s warned=%s", row.id, sent.message_id,
                    case.get("outcome"), ",".join(warned) or "-")
        return _fail("sent", 200, outcome=case.get("outcome"), message_id=sent.message_id)
    if sent.posted or sent.outcome_unknown:
        mark_unknown(session, row.id, case=case, now=now)
        session.commit()
        logger.warning("[CS 보내기] 결과 모름 — 다시 보내지 않고 requestId 로 맞춘다 turn=%s", row.id)
        return _fail("checking", 202, send_state=SEND_UNKNOWN_STATE)
    written = mark_send_failed(session, row.id, error=sent.reason or "send_failed", now=now)
    session.commit()
    return _fail("failed", 502, reason=sent.reason) if written else _fail("checking", 202)


# ── 버리기 · 고칠 말 · 결과 맞추기 ───────────────────────────────────────
def discard_turn(session: Any, *, turn_id: int, user_id: Optional[int], token: Any, secret_key: Any,
                 now: datetime.datetime, manager_id: Optional[str] = None, chat_id: Optional[str] = None) -> FlowResult:
    """버리기 — 끝난 꼴 '버림'(학습 무게 0). 손님께는 아무것도 가지 않는다. 커밋한다. 작은 창 길은 ``manager_id`` · ``chat_id``
    (:class:`SendRequest` 와 같다)."""
    row, denied = _gate(session, turn_id, user_id, token, secret_key, need_switch=False, manager_id=manager_id,
                        chat_id=chat_id)
    closed = denied or _closed(row)
    if closed is not None:
        session.rollback()
        return closed
    turns = CsAgentTurn.__table__
    done = session.execute(update(turns).where(*open_turn(row.id, row.memo_message_id))
                           .values(outcome=OUTCOME_DISCARDED, updated_at=naive_utc(now))).rowcount == 1
    session.commit()
    logger.info("[CS 보내기] 버림 turn=%s done=%s", turn_id, done)
    return _audited(session, "CS_AGENT_DISCARD", turn_id, user_id,
                    _fail("discarded", 200) if done else _fail("already", 409), manager_id=manager_id)


def request_rewrite(session: Any, *, turn_id: int, user_id: int, token: Any, note: Any, secret_key: Any,
                    now: datetime.datetime) -> FlowResult:
    """'고칠 말' 요청 — 가린 말을 차례 줄에 두면 빠른 길(모델을 부르는 유일한 곳)이 받아 새 초안 메모로 바꾼다. 커밋한다."""
    row, denied = _gate(session, turn_id, user_id, token, secret_key)
    closed = denied or _closed(row)
    if closed is not None:
        session.rollback()
        return closed
    if not isinstance(note, str) or not note.strip() or len(note) > MAX_NOTE:
        session.rollback()
        return _fail("bad_request", 400, field="note")
    cfg = read_settings(session, log=False)
    if not cfg.get("realtime_enabled") or draft_mode(session) != DRAFT_MEMO:
        session.rollback()
        return _fail("rewrite_off", 409)
    if int(row.rewrite_count or 0) >= MAX_REWRITES or row.rewrite_state in ("requested", "working"):
        session.rollback()
        return _fail("already", 409, **turn_status(row))
    try:
        masked = masked_or_none(note)
    except MaskLeak:
        session.rollback()
        return _fail("bad_request", 400, field="note_private")
    turns = CsAgentTurn.__table__
    done = session.execute(update(turns).where(*open_turn(row.id, row.memo_message_id),
                                               turns.c.rewrite_count < MAX_REWRITES,
                                               or_(turns.c.rewrite_state.is_(None),
                                                   turns.c.rewrite_state.in_(("done", "failed"))))
                           .values(rewrite_state="requested", rewrite_note_masked=masked,
                                   rewrite_requested_at=naive_utc(now), updated_at=naive_utc(now))).rowcount == 1
    session.commit()
    logger.info("[CS 보내기] 고칠 말 요청 turn=%s done=%s", turn_id, done)
    return _audited(session, "CS_AGENT_REWRITE", turn_id, user_id,
                    _fail("rewrite_requested", 202) if done else _fail("already", 409))


def reconcile_one(session: Any, *, turn_id: int, user_id: int, token: Any, secret_key: Any, now: datetime.datetime,
                  reader: Any = None) -> FlowResult:
    """보내기 화면 다시 열기 — 결과 모름 · 오래 남은 '보내는 중'을 상담 글(requestId)로 맞추고 지금 상태를 돌려준다."""
    row, denied = _gate(session, turn_id, user_id, token, secret_key, need_switch=False)
    if denied is not None:
        session.rollback()
        return denied
    verdict = reconcile_turn(session, row, now=now, reader=reader if reader is not None else OpenApiReader())
    row = session.get(CsAgentTurn, int(turn_id), populate_existing=True)
    session.commit()
    code = {"sent": "sent", "failed": "failed"}.get(verdict, "checking" if row.send_state in (
        SEND_SENDING, SEND_UNKNOWN_STATE) else "already" if row.send_state == SEND_SENT else
        "failed" if row.send_state == SEND_FAILED else "not_open")
    return _fail(code, 200, verdict=verdict, **turn_status(row))
