"""AI 직원 JSON API(설계서 2026-11-14-foms-graft 3.10, 판 ⑪ — 머리 ``/api/ai-staff``).

읽기: ``GET /api/ai-staff`` 목록 · ``GET /api/ai-staff/<열쇠>`` 자세히(읽는 것 · 도구 · 할 일 · 수준 · 2주 승인율 · 최근 실패 ·
시간 · (ADMIN 만) 비용 · 실행 기록 하나). 쓰기: ``POST /api/ai-staff/levels`` 수준 표 고치기(ADMIN 만 — 공용 CSRF · Origin 가드 뒤 ·
길 목록 ``ADMIN_OPS``, 처리기 안에서 ADMIN 을 다시 본다 — 가드가 꺼진 시험 맥락에서도 뚫리지 않는다).

- 여는 사람: :func:`foms.services.ai_staff.views.staff_viewer`(새 화면 스위치 켬 + 회사 지식 화면을 여는 ADMIN · MANAGER) —
  아니면 404, 로그인 안 함 401. 수준 고치기는 ADMIN 이 아니면 404(없는 길과 같다).
- 답은 ``{"success", "data", "error"}`` · ``Cache-Control: private, no-store``(사람마다 다르다 — 비용 칸 · 고치기 칸).
- 오류 글은 코드가 정한 말만(받은 값을 싣지 않는다).

상담 AI 평가 묶음(설계서 3.15 · D209 — T16): ``GET /api/ai-staff/cs`` 답에 ``evals`` 칸(⑪ 'AI 시험' — 줄 셋 · 틀린 차례 · 마지막
시험 · (ADMIN 만) 쓴 돈 · 설정). 쓰기 둘 — ``POST /api/ai-staff/evals/run``(ADMIN 만 · 돈 상한 0 이나 묶음 0 이면 409 · 도는 중이면
409 · 큐가 없으면 503 — web 에서 대신 돌리지 않는다) · ``POST /api/ai-staff/evals/settings``(ADMIN 만). 둘 다 공용 CSRF · Origin 가드
뒤 · 길 목록 ``ADMIN_OPS`` · 처리기 안에서 ADMIN 을 다시 본다(아니면 404). 감사 줄은 :mod:`foms.services.ai_staff.evals` 가 남긴다.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.ai_staff.evals import FAILED, EvalError, begin_run, enqueue_run, save_eval_settings, update_run
from foms.services.ai_staff.evals_view import eval_view
from foms.services.ai_staff.levels import LevelError, save_levels
from foms.services.ai_staff.views import staff_detail, staff_list, staff_viewer
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import enabled

logger = logging.getLogger(__name__)

ai_staff_api_bp = Blueprint("ai_staff_api", __name__, url_prefix="/api/ai-staff")

__all__ = ["ai_staff_api_bp"]

_NOT_FOUND = "찾을 수 없습니다."
_SAVE_FAILED = "저장하지 못했어요. 잠시 뒤 다시 해 주세요."
_QUEUE_DOWN = "지금은 시험을 돌릴 수 없어요. 잠시 뒤 다시 해 주세요."
#: 평가 거절 코드 → 답 상태(꼴 틀림 400 · 설정 0 · 도는 중 409). ADMIN 아님은 404 로 따로 간다.
_EVAL_STATUS = {"EVAL_SHAPE": 400, "EVAL_NO_CAP": 409, "EVAL_NO_SIZE": 409, "EVAL_BUSY": 409}


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
    """직원 하나 자세히(모르는 열쇠는 404). 상담 AI 답에는 'AI 시험' 칸 값(``evals``)을 더한다."""
    user, viewer, denied = _viewer()
    if denied:
        return denied
    db = get_db()
    now = now_utc_naive()
    try:
        data = staff_detail(db, viewer, key, now)
        if data is not None and data["key"] == "cs":
            data["evals"] = eval_view(db, viewer, now=now, erp=enabled("erp_read", user))
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


def _admin_only() -> tuple[Any, Optional[tuple[Any, int]]]:
    """평가 쓰기 길 — 로그인 안 함 401 · 화면을 못 여는 사람 · ADMIN 아님 404 · 아니면 (사용자, None)."""
    user, viewer, denied = _viewer()
    if denied:
        return None, denied
    if not viewer.is_admin:
        return None, _reply(404, None, _NOT_FOUND)
    return user, None


def _eval_refused(exc: EvalError) -> tuple[Any, int]:
    """평가 거절 → 답(ADMIN 아님 404 · 꼴 틀림 400 · 설정 0 · 도는 중 409 — 글은 코드가 정한 말)."""
    if exc.code not in _EVAL_STATUS:
        return _reply(404, None, _NOT_FOUND)
    return _reply(_EVAL_STATUS[exc.code], {"code": exc.code, "fields": list(exc.fields)}, exc.message)


@ai_staff_api_bp.route("/evals/run", methods=["POST"])
def ai_staff_evals_run() -> tuple[Any, int]:
    """[시험 다시 돌리기](ADMIN 만) — '줄 섬' 한 줄을 적고 WORKER 줄에 넣는다. 202 ``{"run": 번호}``."""
    user, denied = _admin_only()
    if denied:
        return denied
    db = get_db()
    try:
        run = begin_run(db, user, now_utc_naive())
        db.commit()
    except EvalError as exc:
        db.rollback()
        return _eval_refused(exc)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[AI-STAFF] 시험 돌리기 DB 오류")
        return _reply(500, None, _SAVE_FAILED)
    if enqueue_run(run["id"]):
        return _reply(202, {"run": run["id"]}, None)
    _release_queued(db, run["id"])
    return _reply(503, {"code": "EVAL_QUEUE"}, _QUEUE_DOWN)


def _release_queued(db: Any, run_id: int) -> None:
    """큐 넣기 실패 뒤 — 남은 '줄 섬'을 '실패'로 풀어 단추를 막지 않게 한다. DB 가 못 받으면 되돌리고 로그만 남긴다
    (그 줄은 :data:`foms.services.ai_staff.evals.STALE_AFTER` 뒤 저절로 풀린다)."""
    try:
        update_run(db, run_id, now_utc_naive(), status=FAILED, code="queue_unavailable")
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[AI-STAFF] 시험 줄 풀기 DB 오류 run=%s", run_id)


@ai_staff_api_bp.route("/evals/settings", methods=["POST"])
def ai_staff_evals_settings() -> tuple[Any, int]:
    """평가 설정 저장(ADMIN 만) — 본문 ``{"cap_usd"?, "past_size"?, "risk_size"?, "past_target_pct"?}``(적은 칸만)."""
    user, denied = _admin_only()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    db = get_db()
    try:
        data = save_eval_settings(db, user, payload if isinstance(payload, dict) else {})
        db.commit()
    except EvalError as exc:
        db.rollback()
        return _eval_refused(exc)
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[AI-STAFF] 시험 설정 저장 DB 오류")
        return _reply(500, None, _SAVE_FAILED)
    return _reply(200, data, None)
