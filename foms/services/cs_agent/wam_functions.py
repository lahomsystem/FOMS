"""채널톡 안 작은 창(WAM)이 부르는 앱 함수 — [보내기] · [수정하기]를 데스크 안에서(설계서 17.2.2 · 사장님 11-05).

함수 받는 곳(:mod:`foms.api.channel.channel_functions`)이 서명 · 채널(라홈) · 부른 상담원을 본 뒤 이 모듈의 :func:`handle` 만
부른다. 누른 사람은 서명된 ``context.caller`` 의 상담원 번호뿐이다 — ``params`` 에 실린 값으로 사람을 정하지 않는다.
``params`` 의 차례 번호 · 상담 id 는 작은 창이 받은 단추 값(브라우저에 보인다)이라 믿지 않는다: 차례가 그 상담의 것이어야 하고,
보내기 앞 확인 · 한 번만 · 최신인가 · 검사는 FOMS 화면 길과 같은 :func:`.send_flow.send_turn` 을 그대로 탄다.

- ``cs.draft.ping`` — 연결 확인(S1 시험 장치 — 글 · 손님 정보 없음).
- ``cs.draft.get`` ``{turn, chat}`` — [수정하기] 글 칸 재료(손님께 보낼 답 · 고친 까닭 칩 · 막힘 글). 접목 관리 칸이 켜졌으면
  근거 칩 ``evidence`` · 작은 창 줄 제안 ``action`` 도(:func:`.send_view.wam_graft` — 끄면 칸이 없다).
- ``cs.draft.send`` ``{turn, chat, mode?, text?, edit_reason?, edit_detail?, confirm?, shown_ms?, with_action?,
  drop_action?}`` — [보내기](그대로 · 고친 글). ``edit_detail`` 은 [수정하기]의 '왜 고쳤나요' 글(관리 칸 '자세한 이유' 켬일
  때만 가려서 적는다 — 사장님 11-11). ``with_action`` · ``drop_action`` 은 작은 창 줄 제안 번호([같이 넣기] · [빼기]) — 답이
  **보내진 뒤에만**(``sent``) 서명된 상담원에 이어진 FOMS 사용자 이름으로 승인 · 실행(:func:`.lifecycle.approve`, 실행기는
  services 표 ``SERVICE_RUNNERS``)하거나 거절(``other``)한다. 그 차례에서 상담 AI 가 만든 작은 창 줄 제안만 받는다. 이어진
  사용자가 없거나 권한이 없거나 실행이 막히면 답 보내기는 그대로 두고 결과의 ``action`` 한 줄로 알린다.
- ``cs.draft.discard`` ``{turn, chat}`` — [버리기].
- ``cs.handoff.get`` ``{turn, chat}`` — 넘김 메모 [배우기] 창 재료(상태 · 까닭 · AI 메모 힌트 · 본 마지막 손님 글).
- ``cs.handoff.send`` ``{turn, chat, text, confirm?, seen?, shown_ms?}`` — [배우기] 창 [보내기](:func:`.handoff_send.send_handoff`).
- ``cs.handoff.skip`` · ``cs.handoff.unskip`` ``{turn, chat}`` — [흘리기] · [배우기로 바꾸기].

응답 꼴은 채널톡 앱 함수 약속 그대로: 성공 ``{"result": ...}``, 예상한 실패 ``{"error": {"code", "type", "message"}}``.
흐름 결과(보냄 · 확인 필요 · 막힘 …)는 ``result`` 의 ``code`` · ``message`` 로 싣는다 — 작은 창이 그 글을 그대로 보인다. 로그에는
차례 번호 · 결과 코드만 남긴다(보낼 글 · 손님 글은 싣지 않는다).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.graft.models import ErpActionProposal
from foms.services.ai_staff.registry import proposer
from foms.services.channel_identity import get_user_by_manager_id
from foms.services.channel_send import CHAT_ID as _CHAT
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.edit_detail import MAX_DETAIL, switches as detail_switches
from foms.services.cs_agent.graft_settings import actions_on
from foms.services.cs_agent.graft_step import AGENT, SOURCE_KIND
from foms.services.cs_agent.handoff_send import handoff_view, send_handoff, skip_learning, unskip_learning
from foms.services.cs_agent.send_flow import FlowResult, SendRequest, discard_turn, send_turn
from foms.services.cs_agent.send_view import wam_graft, wam_view
from foms.services.cs_agent.settings import read_settings
from foms.services.erp_actions.lifecycle import ActionError, approve, reject
from foms.services.erp_actions.registry import ACTIONS, STATUS_EXECUTED
from foms.services.erp_actions.runners import SERVICE_RUNNERS
from models import User

logger = logging.getLogger(__name__)

__all__ = [
    "DISCARD", "FUNCTION_SCHEMAS", "GET", "HANDOFF_GET", "HANDOFF_SEND", "HANDOFF_SKIP", "HANDOFF_UNSKIP", "METHODS",
    "PING", "SEND", "handle",
]

PING, GET, SEND, DISCARD = "cs.draft.ping", "cs.draft.get", "cs.draft.send", "cs.draft.discard"
HANDOFF_GET, HANDOFF_SEND = "cs.handoff.get", "cs.handoff.send"
HANDOFF_SKIP, HANDOFF_UNSKIP = "cs.handoff.skip", "cs.handoff.unskip"
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
         "edit_detail": {"type": "string"}, "confirm": {"type": "string"}, "shown_ms": {"type": "integer"},
         "with_action": {"type": "integer"}, "drop_action": {"type": "integer"}}}},
    {"name": DISCARD, "description": "AI 초안 버리기",
     "inputSchema": {"type": "object", "properties": dict(_TURN_CHAT)}},
    {"name": HANDOFF_GET, "description": "넘김 메모 배우기 창 재료",
     "inputSchema": {"type": "object", "properties": dict(_TURN_CHAT)}},
    {"name": HANDOFF_SEND, "description": "넘김 메모 직원 답 손님께 보내기",
     "inputSchema": {"type": "object", "properties": {
         **_TURN_CHAT, "text": {"type": "string"}, "confirm": {"type": "string"}, "seen": {"type": "string"},
         "shown_ms": {"type": "integer"}}}},
    {"name": HANDOFF_SKIP, "description": "넘김 메모 상담 배우지 않기",
     "inputSchema": {"type": "object", "properties": dict(_TURN_CHAT)}},
    {"name": HANDOFF_UNSKIP, "description": "넘김 메모 상담 다시 배우기",
     "inputSchema": {"type": "object", "properties": dict(_TURN_CHAT)}},
)
METHODS = frozenset(schema["name"] for schema in FUNCTION_SCHEMAS)
_TURN_MAX = 2 ** 31 - 1
#: 흐름 결과 ``data`` 가운데 작은 창에 넘기는 칸(코드 · 숫자 · 확인표 · 검사 줄 — 글 · 상담 id 없음).
_RESULT_KEYS = ("problems", "warnings", "confirm", "outcome", "reason", "field", "send_state", "hint", "seen",
                "max_text", "note")
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
    detail = detail_switches(session, with_photos=False).detail  # '왜 고쳤나요' 칸(관리 칸 '자세한 이유')
    session.rollback()
    result = {"code": "ok", "ok": True, "blocked": view["blocked"], "draft": view["draft"],
              "fresh_note": view["fresh_note"], "checking": view["checking"],
              "edit_reasons": [list(item) for item in view["edit_reasons"]], "max_text": view["max_text"],
              "detail": bool(detail), "max_detail": MAX_DETAIL}
    if view["blocked"] is None:
        result.update(wam_graft(session, turn))  # 접목 근거 칩 · 작은 창 줄 제안(관리 칸 끔이면 칸 없음 — 지금과 같다)
    return result


def _send(session: Any, turn: int, chat: str, params: dict[str, Any], manager_id: str, *, secret_key: Any,
          now: datetime.datetime, reader: Any, sender: Optional[Callable[..., Any]]) -> dict[str, Any]:
    user_id = _user_id(manager_id)
    request = SendRequest(turn_id=turn, user_id=user_id, manager_id=manager_id, chat_id=chat,
                          mode=params.get("mode") or "as_is", text=params.get("text"),
                          edit_reason=params.get("edit_reason"), edit_detail=params.get("edit_detail"),
                          confirm=params.get("confirm"), shown_ms=params.get("shown_ms"))
    extra = {"sender": sender} if sender is not None else {}
    flow = send_turn(session, request, secret_key=secret_key, now=now, reader=reader, **extra)
    out = _flow(flow)
    action = _decide(session, turn, params, user_id, now) if flow.code == "sent" else None  # 보낸 뒤에만
    if action is not None:
        out["action"] = action
    return out


# ── 작은 창 줄 제안 [같이 넣기] · [빼기] — 답이 보내진 뒤에만 ─────────────────
_ACTION_MESSAGES = {
    "off": "할 일 제안이 꺼져 있어 넣지 않았어요.",
    "not_found": "할 일 제안을 찾지 못해 넣지 않았어요.",
    "no_user": "이 상담원에 이어진 FOMS 계정이 없어 할 일은 넣지 않았어요 — 승인 대기에서 처리해 주세요.",
    "ACTION_FORBIDDEN": "이 계정으로는 이 할 일을 넣을 수 없어요 — 승인 대기에서 처리해 주세요.",
    "rejected": "할 일 제안을 뺐어요.",
    "error": "할 일을 넣지 못했어요 — 승인 대기에서 확인해 주세요.",
}


def _act(code: str, *, ok: bool = False, message: Optional[str] = None) -> dict[str, Any]:
    """할 일 결과 한 줄 ``{"code", "ok", "message"}`` — 말은 코드가 정한 것만."""
    return {"code": code, "ok": ok, "message": message or _ACTION_MESSAGES.get(code) or _ACTION_MESSAGES["error"]}


def _number(value: Any) -> Optional[int]:
    """양의 정수(제안 번호)만 — 그 밖은 ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 < value <= _TURN_MAX else None


def _inline_row(session: Any, turn: int, proposal_id: int) -> Optional[ErpActionProposal]:
    """그 차례에서 상담 AI 가 만든 작은 창 줄 제안만(``params`` 의 번호를 믿지 않는다 — 아니면 ``None``)."""
    row = session.get(ErpActionProposal, proposal_id)
    spec = ACTIONS.get(row.action) if row is not None else None
    if spec is None or not spec.wam_inline or row.source_kind != SOURCE_KIND or row.source_ref != str(turn):
        return None
    return row if row.proposed_by == proposer(AGENT) else None


def _run(session: Any, row: ErpActionProposal, actor: Any, add: bool, now: datetime.datetime) -> dict[str, Any]:
    """[같이 넣기] = 승인 · 실행(스스로 커밋), [빼기] = 거절(까닭 ``other``) 후 커밋."""
    if add:
        done = approve(session, row.id, actor=actor, runners=SERVICE_RUNNERS, base_version=row.base_version,
                       now=naive_utc(now))
        return _act(done["status"], ok=done["status"] == STATUS_EXECUTED, message=done["message"])
    reject(session, row.id, actor=actor, code="other", now=naive_utc(now))
    session.commit()
    return _act("rejected", ok=True)


def _decide(session: Any, turn: int, params: dict[str, Any], user_id: Optional[int],
            now: datetime.datetime) -> Optional[dict[str, Any]]:
    """보낸 답의 작은 창 줄 제안 — 고른 것이 없으면 ``None``. 실패는 한 줄 결과로만(답 보내기를 되돌리지 않는다)."""
    add, drop = _number(params.get("with_action")), _number(params.get("drop_action"))
    if (add is None) == (drop is None):  # 고르지 않음 · 둘 다(어느 쪽인지 모름)
        return None
    try:
        return _decide_one(session, turn, add or drop, user_id, add is not None, now)
    except ActionError as exc:
        session.rollback()
        return _act(exc.code, message=_ACTION_MESSAGES.get(exc.code) or exc.message)
    except Exception as exc:  # noqa: BLE001 — 답은 이미 나갔다: 할 일 실패는 한 줄로만(로그엔 번호 · 코드만)
        session.rollback()
        logger.warning("[CS 작은 창] 할 일 실패 turn=%s proposal=%s code=%s", turn, add or drop, type(exc).__name__)
        return _act("error")


def _decide_one(session: Any, turn: int, proposal_id: int, user_id: Optional[int], add: bool,
                now: datetime.datetime) -> dict[str, Any]:
    """스위치 → 그 차례의 작은 창 줄 제안인가 → 이어진 FOMS 사용자 → 승인 · 실행 또는 거절(권한은 생명주기가 다시 본다)."""
    if not actions_on(read_settings(session, log=False)):
        session.rollback()
        return _act("off")
    row = _inline_row(session, turn, proposal_id)
    actor = session.get(User, user_id) if user_id is not None else None
    if row is None or actor is None:
        session.rollback()
        return _act("not_found" if row is None else "no_user")
    return _run(session, row, actor, add, now)


def _handoff(method: str, session: Any, turn: int, chat: str, params: dict[str, Any], manager_id: str, *,
             secret_key: Any, now: datetime.datetime, reader: Any, sender: Optional[Callable[..., Any]]) -> FlowResult:
    """넘김 메모 [배우기] · [흘리기] 함수(:mod:`.handoff_send`)."""
    if method == HANDOFF_GET:
        return handoff_view(session, turn, chat_hint=chat, manager_id=manager_id, reader=reader)
    if method == HANDOFF_SEND:
        request = SendRequest(turn_id=turn, user_id=_user_id(manager_id), manager_id=manager_id, chat_id=chat,
                              text=params.get("text"), confirm=params.get("confirm"), shown_ms=params.get("shown_ms"))
        extra = {"sender": sender} if sender is not None else {}
        return send_handoff(session, request, secret_key=secret_key, now=now, seen=params.get("seen"), reader=reader,
                            **extra)
    choose = skip_learning if method == HANDOFF_SKIP else unskip_learning
    return choose(session, turn_id=turn, chat_id=chat, manager_id=manager_id, user_id=_user_id(manager_id), now=now)


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
        if method.startswith("cs.handoff."):
            result = _flow(_handoff(method, session, turn, chat, params, str(manager_id), secret_key=secret_key,
                                    now=now, reader=reader, sender=sender))
        elif method == GET:
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
