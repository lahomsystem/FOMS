"""AI 상담팀원 — PC 반복(학습 폴더 스크립트)이 내부 메모를 올리기 전에 서버 비상 정지를 묻는 읽기 길(읽기 전용 JSON).

``GET /api/cs-agent/pc-switch`` — 머리값 ``X-FOMS-CS-PC-TOKEN`` 하나로만 연다(로그인 세션 · CSRF 없음 — 기계 요청).

- 서버 열쇠는 env :data:`TOKEN_ENV` 다. 없거나 비었거나 :data:`MIN_TOKEN_LENGTH` 자보다 짧으면 길이 꺼져 있다(**503** —
  짧은 열쇠는 설정 미비로 본다, 서버 로그에 묶어 남긴다). 열쇠가 없거나 틀리면 **401**(상수 시간 비교 —
  ``hmac.compare_digest``, 열쇠 글은 로그에 싣지 않는다).
- 경고 로그는 :data:`WARN_WINDOW_SECONDS` 마다 한 줄로 묶는다 — 창의 첫 번만 남기고 그사이 센 수를 다음 줄의
  ``suppressed`` 에 싣는다(프로세스마다 센다). 틀린 열쇠를 쏟아부어도 로그가 넘치지 않는다.
- 속도 제한은 IP 로만 센다(기본 분당 30 — :func:`foms.services.rate_limit.init_limiter` 가 이 길에 건다). 공용 한도는
  세션 쿠키로 묶음을 고르는데, 로그인이 없는 이 길은 쿠키를 갈아 끼우면 묶음이 끝없이 바뀐다. 넘으면 429.
- 맞으면 ``{"success": true, "data": {"stop": <감시 루프 비상 정지면 true>}, "error": null}`` 만 준다 — 다른 스위치 값 ·
  설정 · 손님 글은 주지 않는다. 스위치를 못 읽으면(DB 오류) ``stop=true`` — 닫힌 쪽이다(PC 는 메모를 올리지 않는다).
- 쓰지 않는 GET 이라 쓰기 가드 · 정책 manifest(쓰기 길만 싣는다)와 감사 목록(쓰기 길만)에 올리지 않는다 — 같은 꼴의 토큰
  읽기 길 ``GET /api/drawing-agent/digest`` 와 같다. 협력사 세션은 공용 문지기(partner_gate)가 먼저 막는다.
- 응답은 캐시하지 않는다(``Cache-Control: no-store``).
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.services.cs_agent.turns import read_switch

logger = logging.getLogger(__name__)

cs_agent_pc_bp = Blueprint("cs_agent_pc", __name__, url_prefix="/api/cs-agent")

#: PC 반복과 나눠 가진 열쇠(값은 web env 에만 — 저장소에 두지 않는다).
TOKEN_ENV = "FOMS_CS_PC_SWITCH_TOKEN"
SWITCH_HEADER = "X-FOMS-CS-PC-TOKEN"
#: 서버 열쇠의 가장 짧은 길이(글자) — 이보다 짧으면 맞혀 보기에 약해 설정 미비로 보고 길을 닫는다.
MIN_TOKEN_LENGTH = 32
#: 같은 경고를 한 줄로 묶는 창(초).
WARN_WINDOW_SECONDS = 60.0
_CLOSED = "PC 스위치 길이 꺼져 있습니다."


class LogBundle:
    """같은 경고를 창마다 한 줄로 묶는다 — 창의 첫 번은 바로 남기고, 창 안의 나머지는 세었다가 다음 줄에 싣는다."""

    def __init__(self, window_s: float = WARN_WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        """창 길이와 시계(시험은 가짜 시계)."""
        self.window_s, self.clock = window_s, clock
        self._lock = threading.Lock()
        self._last: dict[str, float] = {}
        self._held: dict[str, int] = {}

    def due(self, key: str) -> Optional[int]:
        """지금 한 줄을 남길 차례면 그사이 묶은 수(0 이상), 아니면 ``None``(세기만 한다)."""
        now = self.clock()
        with self._lock:
            last = self._last.get(key)
            if last is not None and now - last < self.window_s:
                self._held[key] = self._held.get(key, 0) + 1
                return None
            self._last[key] = now
            return self._held.pop(key, 0)


_WARNINGS = LogBundle()


def _warn(key: str, message: str, *args: Any) -> None:
    """묶어서 경고 — 창의 첫 번만 남기고 그사이 묶은 수(``suppressed``)를 붙인다."""
    held = _WARNINGS.due(key)
    if held is not None:
        logger.warning(message + " suppressed=%d", *args, held)


def _reply(payload: dict[str, Any], status: int = 200) -> Any:
    """JSON 응답 — 캐시하지 않는다."""
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _token_ok(given: str, expected: str) -> bool:
    """열쇠 비교(상수 시간 — 글자를 바이트로 바꿔 견준다. 글자가 아스키가 아니어도 오류 없이 틀림)."""
    return hmac.compare_digest(given.strip().encode("utf-8"), expected.encode("utf-8"))


def _stopped() -> bool:
    """감시 루프 비상 정지인가 — 줄을 못 읽으면 정지로 본다(닫힌 쪽). 읽기 트랜잭션은 닫는다."""
    session = get_db()
    try:
        running = read_switch(session)
        session.rollback()  # 읽기만 했다 — 트랜잭션을 닫는다
        return not running
    except SQLAlchemyError:
        logger.warning("[CS PC] 비상 정지 값을 못 읽어 정지로 알린다")
        _discard(session)
        return True


def _discard(session: Any) -> None:
    """읽다 실패한 트랜잭션을 버린다 — 버리기마저 실패하면 남기고 넘어간다(답은 이미 정지다)."""
    try:
        session.rollback()
    except SQLAlchemyError:
        logger.warning("[CS PC] 읽기 실패 뒤 되돌리기도 실패했다 — 요청 끝에서 세션을 닫는다")


@cs_agent_pc_bp.route("/pc-switch", methods=["GET"])
def cs_agent_pc_switch() -> Any:
    """PC 반복용 비상 정지 읽기 — 503(열쇠 env 없음 · 짧음) · 401(열쇠 틀림) · 429(IP 한도) · 200 ``{"stop": bool}``."""
    expected = (os.environ.get(TOKEN_ENV) or "").strip()
    if len(expected) < MIN_TOKEN_LENGTH:
        if expected:  # 열쇠는 넣었는데 짧다 — 설정 미비(길이 · 글은 싣지 않는다)
            _warn("short", "CS_PC_SWITCH_KEY_SHORT min=%d", MIN_TOKEN_LENGTH)
        return _reply({"success": False, "data": None, "error": _CLOSED}, 503)
    if not _token_ok(request.headers.get(SWITCH_HEADER) or "", expected):
        _warn("denied", "CS_PC_SWITCH_DENIED ip=%s", request.remote_addr)
        return _reply({"success": False, "data": None, "error": "열쇠가 맞지 않습니다."}, 401)
    return _reply({"success": True, "data": {"stop": _stopped()}, "error": None})
