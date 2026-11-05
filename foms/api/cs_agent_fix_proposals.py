"""AI 상담팀원 주간 고침 안 승인 JSON API(설계서 17.6.1 (e) · 사장님 결정 D94) — ADMIN 만, 쓰기는 공용 CSRF · Origin 가드 뒤.

- ``GET  /api/admin/cs-agent/fix-proposals`` — 제안 목록(새 것부터, 가린 글 · 관문 · 근거 차례 id · 결정).
- ``POST /api/admin/cs-agent/fix-proposals/<id>/decide`` ``{"decision": "approve" | "reject", "note"?}`` — 사장님 결정.
  승인이면 회사 지식에 반영하고 지식 문서는 표에서 다시 쓴다(:func:`.weekly_fix_store.decide`), 거절이면 한 줄 까닭.

결정한 사람은 **로그인한 사용자에서만** 받는다 — 본문의 ``approved_by`` · ``user_id`` 같은 칸은 읽지 않는다(R10-18). 자동 반영
길은 없다 — 이 승인 동작이 고침 안을 넣는 유일한 길이다. 미인증 401 · ADMIN 아님 403(JSON). 쓰기 정책은 manifest 의
``ADMIN_OPS``. 응답은 ``{"success", "data", "error"}`` 이고 오류 글은 이 모듈이 정한 글만 싣는다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.cs_agent.weekly_fix_store import decide, list_proposals
from foms.services.datetime_kst import now_kst

logger = logging.getLogger(__name__)

cs_agent_fix_api_bp = Blueprint("cs_agent_fix_api", __name__)

_PREFIX = "/api/admin/cs-agent/fix-proposals"
_MESSAGES = {
    "approved": "승인했어요 — 회사 지식에 넣었고, AI 상담 기준 답도 새 판으로 바뀌었어요.",
    "rejected": "거절했어요 — 같은 안은 다시 올리지 않아요.",
    "already": "이미 결정한 안이에요.",
    "not_found": "안을 찾지 못했어요.",
    "apply_failed": ("넣지 못했어요(그사이 바뀜 · 회사 지식에 그 기준 답이 없음 · 지식 문서가 회사 지식과 다름) — "
                     "새로 불러온 뒤 다시 눌러 주세요."),
    "common_item": "두 브랜드가 같이 쓰는 기준 답이라 여기서 바꾸지 않아요 — 회사 지식 화면에서 고칠 말 제안으로 올려 주세요.",
    "bad_request": "decision 은 approve 또는 reject 입니다.",
    "forbidden": "관리자만 쓸 수 있습니다.",
}


def _reply(status: int, data: Any, error: Optional[str]) -> tuple[Any, int]:
    """응답 — 캐시하지 않는다."""
    response = jsonify({"success": error is None, "data": data, "error": error})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _admin() -> tuple[Any, Optional[tuple[Any, int]]]:
    """켜진 ADMIN 이면 (사용자, None), 아니면 (None, 401 · 403 응답)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _reply(401, None, "로그인이 필요합니다.")
    if getattr(user, "role", None) != "ADMIN" or not getattr(user, "is_active", True):
        return None, _reply(403, None, _MESSAGES["forbidden"])
    return user, None


@cs_agent_fix_api_bp.route(_PREFIX, methods=["GET"])
def cs_agent_fix_proposals() -> tuple[Any, int]:
    """제안 목록(읽기)."""
    _user, denied = _admin()
    if denied:
        return denied
    session = get_db()
    items = list_proposals(session)
    session.rollback()
    return _reply(200, {"proposals": items}, None)


@cs_agent_fix_api_bp.route(f"{_PREFIX}/<proposal_id>/decide", methods=["POST"])
def cs_agent_fix_decide(proposal_id: str) -> tuple[Any, int]:
    """사장님 결정 — 승인 · 거절(결정한 사람 = 로그인 사용자)."""
    user, denied = _admin()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    body = payload if isinstance(payload, dict) else {}
    session = get_db()
    try:
        result = decide(session, proposal_id, decision=body.get("decision"), user=user, note=body.get("note"),
                        now=now_kst())
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 주간 고침 API] DB 오류 proposal=%s", proposal_id)
        return _reply(500, None, "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.")
    message = _MESSAGES.get(result.code, _MESSAGES["bad_request"])
    data = {"code": result.code, "message": message, "version": result.version}
    return _reply(result.status, data, None if result.status < 300 else message)
