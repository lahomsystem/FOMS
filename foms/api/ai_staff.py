"""AI 직원 JSON API(설계서 2026-11-14-foms-graft 3.10, 판 ⑪ — 머리 ``/api/ai-staff``).

읽기: ``GET /api/ai-staff`` 목록 · ``GET /api/ai-staff/<열쇠>`` 자세히(읽는 것 · 도구 · 할 일 · 수준 · 2주 승인율 · 최근 실패 ·
시간 · (ADMIN 만) 비용 · 실행 기록 하나). 쓰기: ``POST /api/ai-staff/levels`` 수준 표 고치기(ADMIN 만 — 공용 CSRF · Origin 가드 뒤 ·
길 목록 ``ADMIN_OPS``, 처리기 안에서 ADMIN 을 다시 본다 — 가드가 꺼진 시험 맥락에서도 뚫리지 않는다).

- 여는 사람: :func:`foms.services.ai_staff.views.staff_viewer`(새 화면 스위치 켬 + 회사 지식 화면을 여는 ADMIN · MANAGER) —
  아니면 404, 로그인 안 함 401. 수준 고치기는 ADMIN 이 아니면 404(없는 길과 같다).
- 답은 ``{"success", "data", "error"}`` · ``Cache-Control: private, no-store``(사람마다 다르다 — 비용 칸 · 고치기 칸).
- 오류 글은 코드가 정한 말만(받은 값을 싣지 않는다).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.ai_staff.levels import LevelError, save_levels
from foms.services.ai_staff.views import staff_detail, staff_list, staff_viewer
from foms.services.datetime_kst import now_utc_naive

logger = logging.getLogger(__name__)

ai_staff_api_bp = Blueprint("ai_staff_api", __name__, url_prefix="/api/ai-staff")

__all__ = ["ai_staff_api_bp"]

_NOT_FOUND = "찾을 수 없습니다."
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."


def _reply(status: int, data: Any, error: Optional[str]) -> tuple[Any, int]:
    """답 — 사람마다 보이는 것이 달라 캐시하지 않는다."""
    response = jsonify({"success": error is None, "data": data, "error": error})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _viewer() -> tuple[Any, Any, Optional[tuple[Any, int]]]:
    """로그인 안 함 401 · 열 수 없는 사람 404 · 열 수 있으면 (사용자, Viewer, None)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, None, _reply(401, None, "로그인이 필요합니다.")
    viewer = staff_viewer(user)
    if viewer is None:
        return None, None, _reply(404, None, _NOT_FOUND)
    return user, viewer, None


@ai_staff_api_bp.route("", methods=["GET"])
def ai_staff_list() -> tuple[Any, int]:
    """왼쪽 목록 — 직원 다섯 · 수준 꼬리표."""
    _user, viewer, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        data = staff_list(db, viewer)
    finally:
        db.rollback()  # 읽기만
    return _reply(200, data, None)


@ai_staff_api_bp.route("/<string:key>", methods=["GET"])
def ai_staff_detail(key: str) -> tuple[Any, int]:
    """직원 하나 자세히(모르는 열쇠는 404)."""
    _user, viewer, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    try:
        data = staff_detail(db, viewer, key, now_utc_naive())
    finally:
        db.rollback()  # 읽기만
    return _reply(200, data, None) if data is not None else _reply(404, None, _NOT_FOUND)


@ai_staff_api_bp.route("/levels", methods=["POST"])
def ai_staff_levels() -> tuple[Any, int]:
    """수준 표 고치기 — 본문 ``{"levels": {"<직원>": {"<할 일>": 0 ~ 2}}}``(ADMIN 만)."""
    user, viewer, denied = _viewer()
    if denied:
        return denied
    if not viewer.is_admin:
        return _reply(404, None, _NOT_FOUND)
    payload = request.get_json(silent=True)
    db = get_db()
    try:
        data = save_levels(db, user, payload if isinstance(payload, dict) else {})
        db.commit()
    except LevelError as exc:
        db.rollback()
        if exc.code == "LEVEL_FORBIDDEN":
            return _reply(404, None, _NOT_FOUND)
        return _reply(400, {"code": exc.code, "fields": list(exc.fields)}, exc.message)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[AI-STAFF] 수준 저장 DB 오류")
        return _reply(500, None, _SAVE_FAILED)
    return _reply(200, data, None)
