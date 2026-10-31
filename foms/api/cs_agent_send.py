"""AI 상담 초안 [보내기] · [수정하기] JSON API — 상담 직원(CS 팀) · ADMIN 만, 쓰기는 공용 CSRF · Origin 가드 뒤(플랜 C10-3).

- ``POST /api/cs-agent/turns/<id>/send`` ``{"token", "mode": "as_is" | "edited", "text"?, "edit_reason"?, "confirm"?,
  "shown_ms"?}`` — web 이 직접 손님께 보낸다(모델을 부르지 않는다, :func:`foms.services.cs_agent.send_flow.send_turn`).
- ``POST …/discard`` ``{"token"}`` — 버리기(끝난 꼴 '버림').
- ``POST …/rewrite`` ``{"token", "note"}`` — '고칠 말' 요청(빠른 길이 받아 새 초안 메모로).
- ``POST …/reconcile`` ``{"token"}`` — 결과 모름을 상담 글(requestId)로 맞추고 지금 상태.
- ``GET  …/status`` — 상태 코드만(다시 쓰기를 기다리는 화면이 본다).

미인증 401 · 권한 밖 403(JSON — 리다이렉트 없음). 쓰기 정책은 manifest 의 ``CS_AGENT_SEND``(게이트 =
:func:`~foms.services.cs_agent.send_auth.can_use_send_screen`)이고 CSRF 는 ``enforce_csrf_origin`` 이 핸들러 전에 본다 — 가드가
꺼진 자리에서도 핸들러가 권한을 다시 본다. 응답은 ``{"success", "data", "error"}`` 이고 글은 이 모듈 · 흐름 모듈이 정한 글만
싣는다(손님 글 · 보낼 글 · 예외 글 · 입력 값을 옮기지 않는다). 보내기 · 버리기 · 고칠 말의 감사 원장 한 줄(누가 · 어느 차례 ·
결과 코드, 글 없음)은 흐름 모듈이 남긴다. 결과 맞추기는 화면이 몇 초마다 부르는 확인이라 원장에 남기지 않는다(allowlist).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.send_auth import can_use_send_screen
from foms.services.cs_agent.send_flow import (
    FlowResult, SendRequest, discard_turn, reconcile_one, request_rewrite, send_turn, turn_status,
)
from foms.services.datetime_kst import now_kst

logger = logging.getLogger(__name__)

cs_agent_send_api_bp = Blueprint("cs_agent_send_api", __name__)

_PREFIX = "/api/cs-agent/turns/<int:turn_id>"


def _fail(status: int, error: str) -> tuple[Any, int]:
    """실패 응답(정한 글만)."""
    return _no_store(jsonify({"success": False, "data": None, "error": error})), status


def _no_store(response: Any) -> Any:
    """캐시하지 않는다(보내기 상태가 바로 바뀐다)."""
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _reply(result: FlowResult) -> tuple[Any, int]:
    """흐름 결과 → 응답(코드 · 화면 글 · 코드뿐인 재료)."""
    data = {"code": result.code, "message": result.message, **result.data}
    body = {"success": result.ok, "data": data, "error": None if result.ok else result.message}
    return _no_store(jsonify(body)), result.status


def _user() -> tuple[Optional[int], Optional[tuple[Any, int]]]:
    """권한 있는 사용자면 (id, None), 아니면 (None, 401 · 403 응답). id 는 커밋 전에 꺼내 둔다."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _fail(401, "로그인이 필요합니다.")
    if not can_use_send_screen(user):
        return None, _fail(403, "상담 직원 · 관리자만 쓸 수 있습니다.")
    return int(user.id), None


def _body() -> dict[str, Any]:
    """JSON 본문(객체가 아니면 빈 dict)."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _run(work: Any) -> tuple[Any, int]:
    """DB 오류는 정한 글로(입력 · 예외 글을 옮기지 않는다)."""
    session = get_db()
    try:
        return _reply(work(session))
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 보내기 API] DB 오류 endpoint=%s", request.endpoint)
        return _fail(500, "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.")


@cs_agent_send_api_bp.route(f"{_PREFIX}/send", methods=["POST"])
def cs_agent_send(turn_id: int) -> tuple[Any, int]:
    """[보내기] — 그대로 · 고친 글."""
    user_id, denied = _user()
    if denied:
        return denied
    body = _body()
    req = SendRequest(turn_id=turn_id, user_id=user_id, token=body.get("token"), mode=body.get("mode") or "as_is",
                      text=body.get("text"), edit_reason=body.get("edit_reason"), confirm=body.get("confirm") is True,
                      shown_ms=body.get("shown_ms"))
    return _run(lambda session: send_turn(session, req, secret_key=current_app.secret_key, now=now_kst()))


@cs_agent_send_api_bp.route(f"{_PREFIX}/discard", methods=["POST"])
def cs_agent_discard(turn_id: int) -> tuple[Any, int]:
    """[버리기] — 끝난 꼴 '버림'."""
    user_id, denied = _user()
    if denied:
        return denied
    token = _body().get("token")
    return _run(lambda session: discard_turn(session, turn_id=turn_id, user_id=user_id, token=token,
                                             secret_key=current_app.secret_key, now=now_kst()))


@cs_agent_send_api_bp.route(f"{_PREFIX}/rewrite", methods=["POST"])
def cs_agent_rewrite(turn_id: int) -> tuple[Any, int]:
    """'고칠 말' — AI 다시 쓰기 요청(빠른 길이 받는다)."""
    user_id, denied = _user()
    if denied:
        return denied
    body = _body()
    return _run(lambda session: request_rewrite(session, turn_id=turn_id, user_id=user_id, token=body.get("token"),
                                                note=body.get("note"), secret_key=current_app.secret_key,
                                                now=now_kst()))


@cs_agent_send_api_bp.route(f"{_PREFIX}/reconcile", methods=["POST"])
def cs_agent_reconcile(turn_id: int) -> tuple[Any, int]:
    """결과 모름 맞추기(보내기 화면 다시 열기)."""
    user_id, denied = _user()
    if denied:
        return denied
    token = _body().get("token")
    return _run(lambda session: reconcile_one(session, turn_id=turn_id, user_id=user_id, token=token,
                                              secret_key=current_app.secret_key, now=now_kst()))


@cs_agent_send_api_bp.route(f"{_PREFIX}/status", methods=["GET"])
def cs_agent_status(turn_id: int) -> tuple[Any, int]:
    """상태 코드만(읽기) — 다시 쓰기를 기다리는 화면이 메모가 바뀌었는지 본다."""
    _user_id, denied = _user()
    if denied:
        return denied
    session = get_db()
    row = session.get(CsAgentTurn, int(turn_id))
    data = turn_status(row) if row is not None else None
    session.rollback()
    if data is None:
        return _fail(404, "초안을 찾지 못했어요.")
    return _no_store(jsonify({"success": True, "data": data, "error": None})), 200
