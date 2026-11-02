"""[수정하기] '왜 고쳤나요(자세히)' · 사진 JSON API — 상담 직원(CS 팀) · ADMIN 만, 쓰기는 공용 CSRF · Origin 가드 뒤(설계서 17.6.1).

- ``POST   /api/cs-agent/turns/<id>/edit-detail`` ``{"detail": 글}`` — 끝난 꼴 '고침'인 줄만(아니면 409). 덮어쓴다(빈 글은 지움).
- ``POST   /api/cs-agent/turns/<id>/edit-photos`` multipart(``photo`` 한 장 + ``no_personal`` ``1``/``0``) → ``{"seq": n}``.
- ``DELETE /api/cs-agent/turns/<id>/edit-photos/<seq>`` — 저장소에서 바로 지우고 줄은 ``purged_at``.

권한 · 스위치 · 검사는 :mod:`foms.services.cs_agent.edit_detail` 이 본다(보낸 직원 24시간 · ADMIN — D94). 미인증 401 · 권한 밖
403(JSON — 리다이렉트 없음). 쓰기 정책은 manifest 의 ``CS_AGENT_SEND``(게이트 = :func:`~.send_auth.can_use_send_screen`)이고
CSRF 는 ``enforce_csrf_origin`` 이 핸들러 전에 본다 — 가드가 꺼진 자리에서도 핸들러가 권한을 다시 본다. 사진 multipart 는
``foms/platform/request_limits.py`` 의 manifest 에 있다(없으면 기본 1MiB 상한에 걸려 휴대폰 사진이 모두 413). 응답은
``{"success", "data", "error"}`` 이고 **URL · 저장소 key · 글을 싣지 않는다** — 원본 보기는 권한을 보는 화면 라우트
(``/cs-agent/turns/<id>/photos/<seq>``)만이다. 감사 원장 한 줄은 서비스 모듈이 남긴다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.cs_agent.edit_detail import DetailResult, add_photo, delete_photo, save_detail
from foms.services.cs_agent.edit_photos import MAX_BYTES
from foms.services.cs_agent.send_auth import can_use_send_screen
from foms.services.datetime_kst import now_kst

logger = logging.getLogger(__name__)

cs_agent_edit_api_bp = Blueprint("cs_agent_edit_api", __name__)

_PREFIX = "/api/cs-agent/turns/<int:turn_id>"
_TRUE = frozenset({"1", "true", "on", "yes"})


def _fail(status: int, error: str) -> tuple[Any, int]:
    """실패 응답(정한 글만)."""
    return _no_store(jsonify({"success": False, "data": None, "error": error})), status


def _no_store(response: Any) -> Any:
    """캐시하지 않는다."""
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _reply(result: DetailResult) -> tuple[Any, int]:
    """서비스 결과 → 응답(코드 · 화면 글 · 숫자뿐인 재료)."""
    data = {"code": result.code, "message": result.message, **result.data}
    body = {"success": result.ok, "data": data, "error": None if result.ok else result.message}
    return _no_store(jsonify(body)), result.status


def _user() -> tuple[Optional[Any], Optional[tuple[Any, int]]]:
    """권한 있는 사용자면 (사용자, None), 아니면 (None, 401 · 403 응답)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _fail(401, "로그인이 필요합니다.")
    if not can_use_send_screen(user):
        return None, _fail(403, "상담 직원 · 관리자만 쓸 수 있습니다.")
    return user, None


def _run(work: Any) -> tuple[Any, int]:
    """DB 오류는 정한 글로(입력 · 예외 글을 옮기지 않는다)."""
    session = get_db()
    try:
        return _reply(work(session))
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 고친 까닭 API] DB 오류 endpoint=%s", request.endpoint)
        return _fail(500, "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요(보낸 글은 그대로예요).")


@cs_agent_edit_api_bp.route(f"{_PREFIX}/edit-detail", methods=["POST"])
def cs_agent_edit_detail(turn_id: int) -> tuple[Any, int]:
    """자세한 이유 저장(덮어씀)."""
    user, denied = _user()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return _run(lambda session: save_detail(session, turn_id=turn_id, user=user, detail=detail, now=now_kst()))


@cs_agent_edit_api_bp.route(f"{_PREFIX}/edit-photos", methods=["POST"])
def cs_agent_edit_photo_add(turn_id: int) -> tuple[Any, int]:
    """사진 한 장 올리기(multipart ``photo`` + ``no_personal``)."""
    user, denied = _user()
    if denied:
        return denied
    upload = request.files.get("photo")
    if upload is None:
        return _fail(400, "사진을 골라 주세요.")
    data = upload.stream.read(MAX_BYTES + 1)  # 상한 + 1 바이트까지만 읽는다 — 넘으면 서비스가 크기로 거절
    no_personal = (request.form.get("no_personal") or "").strip().lower() in _TRUE
    return _run(lambda session: add_photo(session, turn_id=turn_id, user=user, data=data, no_personal=no_personal,
                                          now=now_kst()))


@cs_agent_edit_api_bp.route(f"{_PREFIX}/edit-photos/<int:seq>", methods=["DELETE"])
def cs_agent_edit_photo_delete(turn_id: int, seq: int) -> tuple[Any, int]:
    """사진 지우기(저장소에서 바로)."""
    user, denied = _user()
    if denied:
        return denied
    return _run(lambda session: delete_photo(session, turn_id=turn_id, seq=seq, user=user, now=now_kst()))
