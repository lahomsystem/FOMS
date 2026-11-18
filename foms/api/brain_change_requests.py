"""문장으로 고치기 JSON API(설계서 2026-11-18-brain-sentence-change 11절 표) — 접두 ``/api/brain/change-requests``.

| 길 | 무엇 |
|---|---|
| ``POST /api/brain/change-requests`` ``{text}`` | 분석 시작 → 묶음 화면 값(``id`` · ``status`` 포함) |
| ``GET /api/brain/change-requests/<id>`` | 묶음 화면 값 |
| ``POST …/<id>/answer`` ``{text}`` | 되물음에 답(같은 묶음 다시 분석) |
| ``POST …/<id>/apply`` ``{skip: [줄 번호]}`` | 이대로 고치기 |
| ``POST …/<id>/discard`` | 버리기 |
| ``POST …/<id>/revert`` | 이 묶음 되돌리기 |
| ``GET /api/brain/change-requests?page=`` | 목록 |

여는 사람은 :func:`foms.services.brain.change_request_store.can_use`(스위치 ``brain_change_request`` · 관리자 또는 층 승인자) — 그 밖과
스위치 끔은 **404**(있는지도 알리지 않는다), 로그인 안 함 401. 볼 수 없는 묶음도 없는 묶음과 같은 404. **넣은 사람은 로그인
사용자에서만** 받는다(본문의 사람 칸은 읽지 않는다). 쓰기는 공용 CSRF · Origin 가드 뒤. 응답 ``{"success", "data", "error"}`` ·
오류 글은 정한 말만(문장 · 답 글은 싣지 않는다).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.brain.change_request import answer, discard, start, view
from foms.services.brain.change_request_apply import apply, revert
from foms.services.brain.change_request_store import STATUS, ChangeRequestError, can_use, list_page

logger = logging.getLogger(__name__)

brain_change_api_bp = Blueprint("brain_change_api", __name__, url_prefix="/api/brain/change-requests")

NOT_FOUND = "찾을 수 없습니다."
#: 오류 코드 → 화면 말.
MESSAGES: dict[str, str] = {
    "forbidden": NOT_FOUND,
    "shape": "바뀐 내용은 1 ~ 800자 글로 적어 주세요.",
    "mask": "이름 · 전화 · 주소 같은 개인정보는 빼고 다시 적어 주세요(가림 검사에 걸려 보내지 않았어요).",
    "off": "문장으로 고치기가 꺼져 있어요(하루 돈 상한이 비었어요) — 관리자에게 알려 주세요.",
    "state": "지금 상태에서는 할 수 없어요 — 새로 불러온 뒤 다시 해 주세요.",
    "empty": "고칠 줄이 없어요 — 뺀 줄을 다시 골라 주세요.",
    "db": "저장하지 못했어요. 잠시 뒤 다시 해 주세요.",
}


def _reply(status: int, data: Any, error: Optional[str]) -> tuple[Any, int]:
    """응답 — 사람마다 다르니 캐시하지 않는다."""
    response = jsonify({"success": error is None, "data": data, "error": error})
    response.headers["Cache-Control"] = "private, no-store"
    return response, status


def _body() -> dict[str, Any]:
    """JSON 본문(객체 아니면 빈 dict)."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _run(work: Callable[[Any, Any], Any], *, write: bool) -> tuple[Any, int]:
    """로그인 401 · 쓸 수 없는 사람 404 → 일 → (쓰기면) 커밋. 서비스 오류 · DB 오류면 되돌린다. 읽기 길(묶음 · 목록)도 10분 넘게
    멈춘 분석을 닫으며 커밋한다(그 밖 쓰기 없음)."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _reply(401, None, "로그인이 필요합니다.")
    if can_use(user) is None:
        return _reply(404, None, NOT_FOUND)
    db = get_db()
    try:
        data = work(db, user)
        if write:
            db.commit()
    except ChangeRequestError as exc:
        db.rollback()
        return _reply(STATUS.get(exc.code, 409), {"code": exc.code}, MESSAGES.get(exc.code, MESSAGES["state"]))
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[문장으로 고치기] DB 오류 endpoint=%s", request.endpoint)
        return _reply(500, None, MESSAGES["db"])
    finally:
        if not write:
            db.rollback()
    return _reply(200, data, None)


@brain_change_api_bp.route("", methods=["POST"])
def brain_change_start() -> tuple[Any, int]:
    """분석 시작(가림 → 묶음 줄 → 분석) — 끝난 묶음 화면 값."""
    text = _body().get("text")
    return _run(lambda db, user: start(db, user, text), write=True)


@brain_change_api_bp.route("", methods=["GET"])
def brain_change_list() -> tuple[Any, int]:
    """목록(관리자 모두 · 그 밖 내가 넣은 것)."""
    page = request.args.get("page", type=int) or 1
    return _run(lambda db, user: list_page(db, user, page), write=True)  # 멈춘 분석 닫기를 저장한다


@brain_change_api_bp.route("/<int:request_id>", methods=["GET"])
def brain_change_view(request_id: int) -> tuple[Any, int]:
    """묶음 화면 값."""
    return _run(lambda db, user: view(db, user, request_id), write=True)  # 멈춘 분석 닫기를 저장한다


@brain_change_api_bp.route("/<int:request_id>/answer", methods=["POST"])
def brain_change_answer(request_id: int) -> tuple[Any, int]:
    """되물음에 답 — 같은 묶음 다시 분석."""
    text = _body().get("text")
    return _run(lambda db, user: answer(db, user, request_id, text), write=True)


@brain_change_api_bp.route("/<int:request_id>/apply", methods=["POST"])
def brain_change_apply(request_id: int) -> tuple[Any, int]:
    """이대로 고치기(``skip`` = 뺄 줄 번호들)."""
    skip = _body().get("skip")
    return _run(lambda db, user: apply(db, user, request_id, skip=skip), write=True)


@brain_change_api_bp.route("/<int:request_id>/discard", methods=["POST"])
def brain_change_discard(request_id: int) -> tuple[Any, int]:
    """버리기(반영 전만)."""
    return _run(lambda db, user: discard(db, user, request_id), write=True)


@brain_change_api_bp.route("/<int:request_id>/revert", methods=["POST"])
def brain_change_revert(request_id: int) -> tuple[Any, int]:
    """이 묶음 되돌리기(이 묶음이 반영한 것만)."""
    return _run(lambda db, user: revert(db, user, request_id), write=True)
