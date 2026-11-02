"""DB-LEAK-01: 돌려놓지 않아 GC 가 치운 DB 연결의 **꺼낸 자리**를 로그에 남긴다.

운영 web 에 ``QueuePool Exception during reset or similar`` 가 하루 한 번꼴로 찍힌다
(2026-10-06 ~). 스택은 pool 의 weakref 콜백 → ``_finalize_fairy`` → rollback → psycopg
``wait_poll`` 안의 ``gevent.Timeout: 0.1 seconds`` — 어떤 코드가 연결을 꺼내고 닫지 않아
GC 가 대신 치우다 실패한 것이다. 동기 드라이버라 SQLAlchemy 는 GC 회수에 경고를 남기지
않으므로(비동기 방언만) 실패하지 않은 회수는 아예 안 보이고, 오류가 찍힌 요청은 GC 가
우연히 돈 자리일 뿐이다. 그래서 꺼낼 때 위치를 적어 두고, GC 회수일 때만 한 줄 남긴다.

동작은 바꾸지 않는다 — 기록만 한다. 끄기: ``FOMS_DB_LEAK_TRACE=0``.
설계: ``docs/plans/2026-11-02-db-connection-gc-leak-trace-spec.md``.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

from sqlalchemy import event

logger = logging.getLogger(__name__)

_INFO_KEY = "foms_leak_co"
_MAX_FRAMES = 6
_MAX_WALK = 150  # ORM 실행 경로가 SQLAlchemy 안에서만 수십 칸이다
#: 프로세스당 기록 상한 — 누수가 요청마다 나는 경우에도 로그를 덮지 않는다.
_MAX_REPORTS = 200

_reported = 0
_installed_engines: set[int] = set()

#: 저장소 뿌리(운영 ``/app``) — 이 아래 파일만 "앱 코드"로 본다(설치된 패키지 제외).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + os.sep
_SKIP_PARTS = (
    "site-packages",
    os.path.join("platform", "db_leak_trace.py"),
    os.path.join("common", "request_phase_profile.py"),  # raw_connection 계측 래퍼 — 자리만 차지한다
)
_POOL_BASE = os.path.join("sqlalchemy", "pool", "base.py")


def _app_frames() -> str:
    """현재 호출 스택에서 앱 코드 프레임만 안쪽부터 최대 ``_MAX_FRAMES`` 개 고른다."""
    out: list[str] = []
    frame = sys._getframe(2)
    walked = 0
    while frame is not None and walked < _MAX_WALK and len(out) < _MAX_FRAMES:
        filename = frame.f_code.co_filename
        if filename.startswith(_ROOT) and not any(p in filename for p in _SKIP_PARTS):
            short = filename[len(_ROOT):].replace(os.sep, "/")
            out.append(f"{short}:{frame.f_lineno}:{frame.f_code.co_name}")
        frame = frame.f_back
        walked += 1
    return " < ".join(out) or "-"


def _request_tag() -> tuple[str, str]:
    """꺼낸 순간의 (endpoint, request_id). 요청 밖이면 ``('-', '-')``."""
    try:
        from flask import g, has_request_context, request

        if has_request_context():
            return (request.endpoint or "-", getattr(g, "request_id", None) or "-")
    except Exception:  # noqa: BLE001
        pass  # failopen: intentional: 진단 전용 태그 — 못 읽으면 '-' 로 남기고 앱 동작에 끼어들지 않는다
    return ("-", "-")


def _is_gc_reclaim() -> bool:
    """reset 이 pool 의 weakref 콜백(``<lambda>``)에서 시작됐는지 본다.

    정상 반납은 ``_finalize_fairy`` 를 ``_checkin`` 이 부르고, GC 회수는
    ``_ConnectionRecord.checkout`` 안의 ``<lambda>`` 가 부른다(SQLAlchemy 2.0 pool/base.py).
    """
    frame = sys._getframe(2)
    for _ in range(8):
        if frame is None:
            return False
        code = frame.f_code
        if code.co_name == "_finalize_fairy":
            caller = frame.f_back
            return bool(
                caller is not None
                and caller.f_code.co_name == "<lambda>"
                and caller.f_code.co_filename.endswith(_POOL_BASE)
            )
        frame = frame.f_back
    return False


def _on_checkout(dbapi_connection: Any, connection_record: Any, connection_proxy: Any) -> None:
    try:
        endpoint, request_id = _request_tag()
        connection_record.info[_INFO_KEY] = (_app_frames(), endpoint, request_id, time.monotonic())
    except Exception:  # noqa: BLE001
        pass  # failopen: intentional: 기록 전용 리스너 — 실패해도 연결 꺼내기를 막지 않는다


def _on_reset(dbapi_connection: Any, connection_record: Any, reset_state: Any) -> None:
    global _reported
    try:
        if connection_record is None:
            return
        info = connection_record.info.pop(_INFO_KEY, None)
        if info is None or _reported >= _MAX_REPORTS or not _is_gc_reclaim():
            return
        _reported += 1
        frames, endpoint, request_id, t0 = info
        logger.warning(
            "[DB-LEAK] gc_reclaimed checkout_at=%s endpoint=%s req=%s held_s=%.1f",
            frames, endpoint, request_id, time.monotonic() - t0,
        )
    except Exception:  # noqa: BLE001
        pass  # failopen: intentional: 기록 전용 리스너 — 실패해도 연결 반납(rollback)을 막지 않는다


def install_db_leak_trace(engine: Any) -> bool:
    """engine 에 checkout/reset 리스너를 한 번 단다. 꺼져 있거나 이미 달았으면 ``False``."""
    if engine is None or os.getenv("FOMS_DB_LEAK_TRACE", "1").strip() == "0":
        return False
    if id(engine) in _installed_engines:
        return False
    event.listen(engine, "checkout", _on_checkout)
    event.listen(engine, "reset", _on_reset)
    _installed_engines.add(id(engine))
    return True
