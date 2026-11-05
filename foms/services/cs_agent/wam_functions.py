"""채널톡 안 작은 창(WAM)이 부르는 앱 함수 — [보내기] · [수정하기]를 데스크 안에서(설계서 17.2.2 · 사장님 11-05).

함수 받는 곳(:mod:`foms.api.channel.channel_functions`)이 서명 · 채널(라홈) · 부른 상담원을 본 뒤 이 모듈의 :func:`handle` 만
부른다. 누른 사람은 서명된 ``context.caller`` 의 상담원 번호뿐이다 — ``params`` 에 실린 값으로 사람을 정하지 않는다.
``params`` 의 차례 번호 · 상담 id 는 작은 창이 받은 단추 값(브라우저에 보인다)이라 믿지 않는다: 차례가 그 상담의 것이어야 하고,
보내기 앞 확인 · 한 번만 · 최신인가 · 검사는 FOMS 화면 길과 같은 :func:`.send_flow.send_turn` 을 그대로 탄다.

- ``cs.draft.ping`` — 연결 확인(S1 시험 장치 — 글 · 손님 정보 없음).
- ``cs.draft.get`` ``{turn, chat}`` — [수정하기] 글 칸 재료(손님께 보낼 답 · 고친 까닭 칩 · 막힘 글).
- ``cs.draft.send`` ``{turn, chat, mode?, text?, edit_reason?, confirm?, shown_ms?}`` — [보내기](그대로 · 고친 글).
- ``cs.draft.discard`` ``{turn, chat}`` — [버리기].

응답 꼴은 채널톡 앱 함수 약속 그대로: 성공 ``{"result": ...}``, 예상한 실패 ``{"error": {"code", "type", "message"}}``.
흐름 결과(보냄 · 확인 필요 · 막힘 …)는 ``result`` 의 ``code`` · ``message`` 로 싣는다 — 작은 창이 그 글을 그대로 보인다. 로그에는
차례 번호 · 결과 코드만 남긴다(보낼 글 · 손님 글은 싣지 않는다).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError

from foms.services.channel_identity import get_user_by_manager_id
from foms.services.channel_send import CHAT_ID as _CHAT
from foms.services.cs_agent.send_flow import FlowResult, SendRequest, discard_turn, send_turn
from foms.services.cs_agent.send_view import wam_view

logger = logging.getLogger(__name__)

__all__ = ["DISCARD", "FUNCTION_SCHEMAS", "GET", "METHODS", "PING", "SEND", "handle"]

PING, GET, SEND, DISCARD = "cs.draft.ping", "cs.draft.get", "cs.draft.send", "cs.draft.discard"
_TURN_CHAT = {"turn": {"type": "integer"}, "chat": {"type": "string"}}
#: 채널톡이 함수 목록을 물을 때(``extension.core.function.getFunctions``) 답하는 꼴(이름 · 입력 틀).
FUNCTION_SCHEMAS: tuple[dict[str, Any], ...] = (
    {"name": PING, "description": "AI 초안 작은 창 연결 확인",
     "inputSchema": {"type": "object", "properties": {"turn": {"type": "integer"}}}},
    {"name": GET, "description": "AI 초안 고치기 재료",
     "inputSchema": {"type": "object", "properties": dict(_TURN_CHAT)}},
    {"name": SEND, "description": "AI 초안 손님께 보내기",
     "inputSchema": {"type": "object", "properties": {
         **_TURN_CHAT, "mode": {"type": "string"}, "text": {"type": "string"}, "edit_reason": {"type": "string"},
         "confirm": {"type": "string"}, "shown_ms": {"type": "integer"}}}},
    {"name": DISCARD, "description": "AI 초안 버리기",
     "inputSchema": {"type": "object", "properties": dict(_TURN_CHAT)}},
)
METHODS = frozenset(schema["name"] for schema in FUNCTION_SCHEMAS)
_TURN_MAX = 2 ** 31 - 1
#: 흐름 결과 ``data`` 가운데 작은 창에 넘기는 칸(코드 · 숫자 · 확인표 · 검사 줄 — 글 · 상담 id 없음).
_RESULT_KEYS = ("problems", "warnings", "confirm", "outcome", "reason", "field", "send_state")
_DB_ERROR = {"code": "db_error", "ok": False, "message": "저장하지 못했어요. 잠시 뒤 다시 눌러 주세요."}


def _error(code: int, kind: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "type": kind, "message": message}}


def _turn(params: Any) -> Optional[int]:
    """``params.turn`` — 양의 정수만(그 밖은 ``None``)."""
    value = params.get("turn") if isinstance(params, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if 0 < number <= _TURN_MAX else None


def _chat(params: Any) -> Optional[str]:
    """``params.chat`` — 작은 창이 받은 상담 id(꼴이 맞을 때만)."""
    value = params.get("chat") if isinstance(params, dict) else None
    return value if isinstance(value, str) and _CHAT.fullmatch(value) else None


def _flow(result: FlowResult) -> dict[str, Any]:
    """흐름 결과 → 작은 창 결과(코드 · 화면 글 · 정한 칸만)."""
    out: dict[str, Any] = {"code": result.code, "ok": result.ok, "message": result.message}
    out.update({key: result.data[key] for key in _RESULT_KEYS if key in result.data})
    return out


def _user_id(manager_id: str) -> Optional[int]:
    """채널톡 상담원의 FOMS 짝(활성 계정만 — 없으면 ``None``, 보내기는 상담원 번호로만 적는다)."""
    user = get_user_by_manager_id(manager_id)
    return int(user.id) if user is not None else None


def _get(session: Any, turn: int, chat: str, reader: Any) -> dict[str, Any]:
    """[수정하기] 재료 — 보낼 답 · 막힘 글 · 새 글 알림 · 고친 까닭 칩 · 글자 상한."""
    view = wam_view(session, turn, chat_hint=chat, reader=reader)
    if view is None:
        return {"code": "not_found", "ok": False, "message": "초안을 찾지 못했어요."}
    return {"code": "ok", "ok": True, "blocked": view["blocked"], "draft": view["draft"],
            "fresh_note": view["fresh_note"], "checking": view["checking"],
            "edit_reasons": [list(item) for item in view["edit_reasons"]], "max_text": view["max_text"]}


def _send(session: Any, turn: int, chat: str, params: dict[str, Any], manager_id: str, *, secret_key: Any,
          now: datetime.datetime, reader: Any, sender: Optional[Callable[..., Any]]) -> dict[str, Any]:
    request = SendRequest(turn_id=turn, user_id=_user_id(manager_id), manager_id=manager_id, chat_id=chat,
                          mode=params.get("mode") or "as_is", text=params.get("text"),
                          edit_reason=params.get("edit_reason"), confirm=params.get("confirm"),
                          shown_ms=params.get("shown_ms"))
    extra = {"sender": sender} if sender is not None else {}
    return _flow(send_turn(session, request, secret_key=secret_key, now=now, reader=reader, **extra))


def handle(method: str, params: Any, manager_id: Optional[str], *, session: Any = None, secret_key: Any = None,
           now: Optional[datetime.datetime] = None, reader: Any = None,
           sender: Optional[Callable[..., Any]] = None) -> dict[str, Any]:
    """서명을 지난 함수 한 번 — 상담원이 부른 것만 받는다(봇 · 손님 · 빈 caller 는 권한 없음).

    Args:
        method · params: 채널톡이 실어 온 함수 이름 · 입력(믿지 않는다).
        manager_id: 서명된 caller 의 상담원 번호(상담원이 아니면 ``None``).
        session · secret_key · now: DB 세션 · 앱 비밀 키(확인표) · 지금 — ping 밖의 함수에 쓴다.
        reader · sender: 채널톡 읽기 · 보내기 도우미(시험은 가짜 — 없으면 기본).
    """
    if not manager_id:
        return _error(4, "unauthorized", "상담원만 쓸 수 있어요.")
    if method == PING:
        return {"result": {"ok": True, "turn": _turn(params)}}
    if method not in METHODS:
        return _error(-32601, "methodNotFound", "없는 함수예요.")
    turn, chat = _turn(params), _chat(params)
    if turn is None or chat is None or session is None or now is None:
        return _error(-32602, "invalidParams", "초안 차례를 알 수 없어요.")
    try:
        if method == GET:
            result = _get(session, turn, chat, reader)
        elif method == SEND:
            result = _send(session, turn, chat, params, str(manager_id), secret_key=secret_key, now=now,
                           reader=reader, sender=sender)
        else:
            result = _flow(discard_turn(session, turn_id=turn, user_id=_user_id(str(manager_id)), token="",
                                        secret_key=secret_key, now=now, manager_id=str(manager_id), chat_id=chat))
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 작은 창] DB 오류 method=%s turn=%s", method, turn)
        return {"result": dict(_DB_ERROR)}
    logger.info("[CS 작은 창] %s turn=%s code=%s", method, turn, result.get("code"))
    return {"result": result}
