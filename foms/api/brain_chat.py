"""회사 지식 물어보기(직원 챗봇) JSON API(설계서 10절 · D88 · D99 · 12절) — 접두 ``/api/brain/chat``.

- ``GET /state`` — 스위치 · 단계 · 내가 물을 수 있나 · 오늘 남은 질문 수 · (ADMIN) 설정 표 · 빈 지식 목록.
- ``POST /ask`` ``{"question"}`` — 답하는 길 한 곳(:func:`foms.services.brain.chat_answer.ask` — 가림 → 사람 상한 → 보기 범위 안
  찾기 → 두뇌 → 코드 확인 → 기록). **챗봇은 지식을 쓰지 않는다** — 고칠 말은 사람이 항목 카드의 이름 있는 액션 ``propose_edit`` 로.
- ``POST /questions/<id>/feedback`` ``{"feedback": "helpful" | "not_helpful" | "wrong", "note"}`` — 내 질문에만.
- ``POST /settings`` ``{"changes", "version"}`` — ADMIN 만(정책 ``ADMIN_OPS``).
- ``GET /tools`` — 에이전트 도구로 내놓은 것(읽기 셋)과 챗봇이 권하는 사람 액션(ADMIN · 층 승인자).
- ``GET /history`` — **내가 물은 것만**(오늘 · 지난 7일, 가린 글 앞부분 · 모름 · 주문 읽기 — 설계서 2026-11-14-foms-graft 3.7).
  접목판 스위치(``brain_ui`` 또는 ``erp_read``)가 켜진 사람만 — 꺼진 사람에게는 없는 주소와 같은 답(지금 그대로).

여는 사람은 :func:`foms.services.brain.chat_access.page_viewer`(ADMIN · 단계 안 내부 직원) — 그 밖(바깥 역할 · 꺼진 계정 · 단계
밖)은 **404**, 로그인 안 함 401. PARTNER 세션은 협력사 문지기가 먼저 막는다(없는 주소와 같은 답). 쓰기는 공용 CSRF · Origin 가드
뒤(정책 manifest ``BRAIN_ASK`` — 로그인 내부 직원, 실제 단계 판정은 여기서 다시). 응답 ``{"success", "data", "error"}`` · 정한 말만.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.brain.access import screen_viewer
from foms.services.brain.actions import ACTIONS, AGENT_EXPOSED_WRITES
from foms.services.brain.chat_access import ask_viewer, page_viewer
from foms.services.brain.chat_answer import STATUS, ChatError, ask
from foms.services.brain.chat_gaps import latest_gaps
from foms.services.brain.chat_log import ChatFeedbackError, asked_today, my_history, record_feedback
from foms.services.brain.chat_settings import (
    ChatSettingsError, daily_cap, read_chat_settings, save_chat_settings, settings_view,
)
from foms.services.brain.chat_tools import AGENT_TOOLS, CHAT_OFFERED_ACTIONS, READ_TOOL_SPECS
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import enabled as graft_enabled

logger = logging.getLogger(__name__)

brain_chat_api_bp = Blueprint("brain_chat_api", __name__, url_prefix="/api/brain/chat")

NOT_FOUND = "찾을 수 없습니다."
#: 오류 코드 → 화면 말.
MESSAGES: dict[str, str] = {
    "forbidden": NOT_FOUND,
    "off": "물어보기가 꺼져 있어요 — 설정에서 켜 주세요.",
    "shape": "질문은 1 ~ 500자 글로 적어 주세요.",
    "mask": "이름 · 전화 · 주소 같은 개인정보는 빼고 다시 물어봐 주세요(가림 검사에 걸려 보내지 않았어요).",
    "person_cap": "오늘 물을 수 있는 수를 다 썼어요 — 내일 다시 물어봐 주세요.",
    "money_cap": "오늘 물어보기 돈 상한에 닿았어요 — 내일 다시 물어봐 주세요.",
    "not_ready": "물어보기 준비가 안 됐어요(하루 돈 상한 · 열쇠 설정) — 관리자에게 알려 주세요.",
    "unavailable": "지금 답을 받지 못했어요 — 잠시 뒤 다시 물어봐 주세요.",
    "feedback_shape": "고르기 값이 맞지 않아요.",
    "feedback_mask": "고칠 말에 이름 · 전화 같은 개인정보가 있어요 — 빼고 다시 적어 주세요.",
    "settings_invalid": "설정 값이 맞지 않아요 — 칸을 확인해 주세요.",
    "settings_conflict": "다른 사람이 먼저 저장했어요 — 새로 불러온 뒤 다시 해 주세요.",
    "settings_no_change": "바뀐 칸이 없어요.",
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


def _opened(db: Any) -> tuple[Any, Any, Optional[tuple[Any, int]]]:
    """(설정, Viewer, 거절 응답) — 로그인 안 함 401 · 열 수 없는 사람 404."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, None, _reply(401, None, "로그인이 필요합니다.")
    cfg = read_chat_settings(db)
    viewer = page_viewer(user, cfg)
    if viewer is None:
        return cfg, None, _reply(404, None, NOT_FOUND)
    return cfg, viewer, None


@brain_chat_api_bp.route("/state", methods=["GET"])
def brain_chat_state() -> tuple[Any, int]:
    """화면 첫 값 — 물을 수 있나 · 남은 수(ADMIN 은 설정 · 빈 지식 목록까지)."""
    db = get_db()
    try:
        cfg, viewer, denied = _opened(db)
        if denied:
            return denied
        can_ask = ask_viewer(g.current_user, cfg) is not None
        used = asked_today(db, viewer.user_id, now_utc_naive())
        data = {"enabled": cfg.enabled, "stage": cfg.stage, "can_ask": can_ask, "is_admin": viewer.is_admin,
                "left_today": max(0, int(cfg.get("per_person_daily")) - used),
                "card_links": screen_viewer(g.current_user) is not None}
        if viewer.is_admin:
            data.update(cap_ready=daily_cap(cfg) is not None, settings=settings_view(cfg), gaps=latest_gaps(db))
        return _reply(200, data, None)
    finally:
        db.rollback()


@brain_chat_api_bp.route("/ask", methods=["POST"])
def brain_chat_ask() -> tuple[Any, int]:
    """물어보기 한 번."""
    db = get_db()
    cfg, viewer, denied = _opened(db)
    if denied:
        db.rollback()
        return denied
    if viewer.is_admin and not cfg.enabled:
        db.rollback()
        return _reply(409, {"code": "off"}, MESSAGES["off"])
    try:
        data = ask(db, g.current_user, _body().get("question"))
        db.commit()
    except ChatError as exc:
        db.rollback()
        return _reply(STATUS.get(exc.code, 503), {"code": exc.code}, MESSAGES.get(exc.code, MESSAGES["unavailable"]))
    except SQLAlchemyError:
        db.rollback()
        logger.warning("[회사 지식 물어보기] DB 오류")
        return _reply(500, None, MESSAGES["db"])
    return _reply(200, data, None)


@brain_chat_api_bp.route("/questions/<int:question_id>/feedback", methods=["POST"])
def brain_chat_feedback(question_id: int) -> tuple[Any, int]:
    """내 질문에 피드백 — 틀림이면 근거 항목에 신고가 붙는다(둘 이상이면 승인자에게)."""
    db = get_db()
    cfg, viewer, denied = _opened(db)
    if denied:
        db.rollback()
        return denied
    body = _body()
    try:
        data = record_feedback(db, question_id=question_id, asker_id=viewer.user_id, feedback=body.get("feedback"),
                               note=body.get("note"), now_utc=now_utc_naive())
        db.commit()
    except ChatFeedbackError as exc:
        db.rollback()
        if exc.code == "not_found":
            return _reply(404, None, NOT_FOUND)
        return _reply(400, {"code": exc.code}, MESSAGES["feedback_" + ("mask" if exc.code == "mask" else "shape")])
    except SQLAlchemyError:
        db.rollback()
        return _reply(500, None, MESSAGES["db"])
    return _reply(200, data, None)


@brain_chat_api_bp.route("/settings", methods=["POST"])
def brain_chat_settings_save() -> tuple[Any, int]:
    """설정 저장 — ADMIN 만(그 밖 404)."""
    db = get_db()
    _cfg, viewer, denied = _opened(db)
    if denied or not viewer.is_admin:
        db.rollback()
        return denied or _reply(404, None, NOT_FOUND)
    body = _body()
    try:
        cfg = save_chat_settings(db, actor_id=viewer.user_id, changes=body.get("changes"), version=body.get("version"))
        db.commit()
    except ChatSettingsError as exc:
        db.rollback()
        status = 409 if exc.code == "conflict" else 400
        return _reply(status, {"code": exc.code, "fields": list(exc.fields)}, MESSAGES["settings_" + exc.code])
    except SQLAlchemyError:
        db.rollback()
        return _reply(500, None, MESSAGES["db"])
    return _reply(200, {"settings": settings_view(cfg), "cap_ready": daily_cap(cfg) is not None}, None)


@brain_chat_api_bp.route("/history", methods=["GET"])
def brain_chat_history() -> tuple[Any, int]:
    """내가 물은 것(오늘 · 지난 7일) — 로그인 사용자 번호로만 고른다. 스위치가 꺼진 사람에게는 없는 주소와 같은 답(지금과 같다)."""
    user = getattr(g, "current_user", None)
    if user is not None and not (graft_enabled("brain_ui", user) or graft_enabled("erp_read", user)):
        abort(404)
    db = get_db()
    try:
        _cfg, viewer, denied = _opened(db)
        if denied:
            return denied
        return _reply(200, my_history(db, asker_id=viewer.user_id, now_utc=now_utc_naive()), None)
    finally:
        db.rollback()


@brain_chat_api_bp.route("/tools", methods=["GET"])
def brain_chat_tools() -> tuple[Any, int]:
    """에이전트 도구 목록 — 읽기 셋만(쓰기 액션은 아직 하나도 도구로 내놓지 않는다) · 챗봇이 권하는 사람 액션."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _reply(401, None, "로그인이 필요합니다.")
    if screen_viewer(user) is None:
        return _reply(404, None, NOT_FOUND)
    return _reply(200, {"agent_tools": [t for t in READ_TOOL_SPECS if t["name"] in AGENT_TOOLS],
                        "agent_write_actions": list(AGENT_EXPOSED_WRITES),
                        "chat_offers": [{"name": n, "label": ACTIONS[n].label} for n in CHAT_OFFERED_ACTIONS]}, None)
