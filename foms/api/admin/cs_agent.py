"""AI 상담팀원 관리 패널 JSON API(설계서 16.1 · 16.6 단계 1) — ADMIN 만, 쓰기는 공용 CSRF · Origin 가드 뒤.

- ``GET  /api/admin/cs-agent/state`` — 스위치 · 두뇌 설정 · 하루 상한 · 기록 한 덩어리(:func:`.panel.panel_state`).
- ``POST /api/admin/cs-agent/switch/loop`` ``{"on": bool}`` — 비상 정지(감시 루프 켬 · 멈춤).
- ``POST /api/admin/cs-agent/switch/draft`` ``{"mode": "off" | "store" | "memo"}`` — 초안 스위치.
- ``POST /api/admin/cs-agent/settings`` ``{"values": {...}, "expected_version": int}`` — 두뇌 · 돈 설정(버전 대조 — 다른
  사람이 먼저 저장했으면 409). 다음 단계 칸(고르기 · 의도 고르기 · 실시간 길 — 잠김)을 바꾸는 저장은 400 이다.

미인증 401 · ADMIN 아님 403(JSON — 리다이렉트 없음, ``/api/foms/ops/*`` 와 같은 규약). 쓰기 정책은 manifest 의
``ADMIN_OPS`` 이고 CSRF 는 ``enforce_csrf_origin`` 이 핸들러 전에 본다. 응답은 ``{"success", "data", "error"}`` 이고 오류 글은
이 모듈이 정한 글만 싣는다(예외 글 · 입력 값을 옮기지 않는다). 값은 다음 차례부터 적용된다(재배포 없음).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.cs_agent.panel import change_draft_mode, change_loop, panel_state
from foms.services.cs_agent.settings import (
    SettingsConflictError, SettingsInvalidError, SettingsLockedError, SettingsNoChangeError, save_settings,
)
from foms.services.cs_agent.turns import DRAFT_MODES
from foms.services.datetime_kst import now_kst

logger = logging.getLogger(__name__)

cs_agent_admin_api_bp = Blueprint("cs_agent_admin_api", __name__)

_PREFIX = "/api/admin/cs-agent"


def _fail(status: int, error: str, data: Optional[dict[str, Any]] = None) -> tuple[Any, int]:
    """실패 응답(정한 글만)."""
    return jsonify({"success": False, "data": data, "error": error}), status


def _ok(data: dict[str, Any]) -> tuple[Any, int]:
    """성공 응답 — 캐시하지 않는다(스위치 · 돈 값이 바로 바뀐다)."""
    response = jsonify({"success": True, "data": data, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200


def _admin() -> tuple[Optional[int], Optional[tuple[Any, int]]]:
    """켜진 ADMIN 이면 (사용자 id, None), 아니면 (None, 401 · 403 응답). id 는 커밋 전에 꺼내 둔다."""
    user = getattr(g, "current_user", None)
    if user is None:
        return None, _fail(401, "로그인이 필요합니다.")
    if getattr(user, "role", None) != "ADMIN":
        return None, _fail(403, "관리자만 쓸 수 있습니다.")
    return int(user.id), None


def _body() -> dict[str, Any]:
    """JSON 본문(객체가 아니면 빈 dict)."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _state(session: Any) -> dict[str, Any]:
    """새로 읽은 화면 한 덩어리 — 읽기 트랜잭션은 닫는다."""
    state = panel_state(session, now=now_kst())
    session.rollback()
    return state


@cs_agent_admin_api_bp.route(f"{_PREFIX}/state", methods=["GET"])
def cs_agent_state() -> tuple[Any, int]:
    """관리 화면 한 덩어리(읽기만)."""
    _actor, denied = _admin()
    if denied:
        return denied
    return _ok(_state(get_db()))


@cs_agent_admin_api_bp.route(f"{_PREFIX}/switch/loop", methods=["POST"])
def cs_agent_switch_loop() -> tuple[Any, int]:
    """비상 정지 — ``{"on": false}`` 면 다음 바퀴부터 감시 루프 일 0, ``{"on": true}`` 면 다시 돈다."""
    actor_id, denied = _admin()
    if denied:
        return denied
    on = _body().get("on")
    if not isinstance(on, bool):
        return _fail(400, "on 은 true · false 가운데 하나입니다.")
    session = get_db()
    try:
        changed = change_loop(session, on=on, actor_user_id=actor_id, now=now_kst())
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 관리] 비상 정지 값을 쓰지 못했다 user=%s on=%s", actor_id, on)
        return _fail(500, "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.")
    return _ok({"changed": changed, "state": _state(session)})


@cs_agent_admin_api_bp.route(f"{_PREFIX}/switch/draft", methods=["POST"])
def cs_agent_switch_draft() -> tuple[Any, int]:
    """초안 스위치 — ``{"mode": "off" | "store" | "memo"}``."""
    actor_id, denied = _admin()
    if denied:
        return denied
    mode = _body().get("mode")
    if not isinstance(mode, str) or mode not in DRAFT_MODES:
        return _fail(400, "mode 는 off · store · memo 가운데 하나입니다.")
    session = get_db()
    try:
        changed = change_draft_mode(session, mode=mode, actor_user_id=actor_id, now=now_kst())
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 관리] 초안 스위치 값을 쓰지 못했다 user=%s mode=%s", actor_id, mode)
        return _fail(500, "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.")
    return _ok({"changed": changed, "state": _state(session)})


@cs_agent_admin_api_bp.route(f"{_PREFIX}/settings", methods=["POST"])
def cs_agent_save_settings() -> tuple[Any, int]:
    """두뇌 · 돈 설정 저장 — 칸 하나라도 틀리면 통째로 거절(400 · 칸 이름), 다음 단계 칸(잠김)을 바꾸면 400, 버전이 다르면 409."""
    actor_id, denied = _admin()
    if denied:
        return denied
    body = _body()
    expected = body.get("expected_version")
    if isinstance(expected, bool) or not isinstance(expected, int):
        return _fail(400, "expected_version(읽은 버전, 정수)이 필요합니다.")
    session = get_db()
    try:
        result = save_settings(session, body.get("values"), expected_version=expected, actor_user_id=actor_id)
        session.commit()
    except SettingsLockedError as exc:
        session.rollback()
        return _fail(400, "다음 단계 칸은 아직 바꿀 수 없습니다: " + ", ".join(exc.fields),
                     {"fields": list(exc.fields), "locked": True})
    except SettingsInvalidError as exc:
        session.rollback()
        return _fail(400, "고를 수 없는 값이 있습니다: " + ", ".join(exc.fields), {"fields": list(exc.fields)})
    except SettingsConflictError as exc:
        session.rollback()
        return _fail(409, "다른 사람이 먼저 저장했습니다. 새로 불러온 뒤 다시 저장해 주세요.",
                     {"current_version": exc.current_version})
    except SettingsNoChangeError:
        session.rollback()
        return _fail(400, "바뀐 칸이 없습니다.", {"fields": []})
    except SQLAlchemyError:
        session.rollback()
        logger.warning("[CS 관리] 설정을 쓰지 못했다 user=%s expected_version=%s", actor_id, expected)
        return _fail(500, "저장하지 못했습니다. 잠시 뒤 다시 눌러 주세요.")
    return _ok({"version": result.version, "changed": list(result.changed), "state": _state(session)})
