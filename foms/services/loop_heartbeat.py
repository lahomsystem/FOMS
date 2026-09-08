"""무감독 백그라운드 루프의 생존 신호 공통 배선 (OPS-HEARTBEAT-01).

``start.sh`` 는 워커 컨테이너에서 백그라운드 루프 여러 개를 ``&`` 로 띄우고 셸은
``exec rq worker`` 로 자기를 대체한다. wait/trap/supervisor 가 0 이라 루프가 죽어도 아무도
모른다 — 2026-02 워커 offline, 2026-08-31 SIDEFX 미배포를 **두 번 다 사용자가 화면에서
먼저 발견**했다.

각 루프는 tick 마다 :func:`emit_heartbeat` 로 ``side_effect_worker_heartbeats`` 에 자기
``worker_kind`` 행을 남기고, 판정은 :mod:`foms.services.sidefx_worker` 의 등록부
(``WORKER_KIND_SPECS``)를 읽는 readiness checker 가 한다.

이 모듈이 지키는 두 가지 규율:

* **하트비트 실패가 본 작업을 막지 않는다** — 관측 배선 때문에 자동 발송·수집이 멈추는 것이
  더 나쁜 실패다.
* **그렇다고 삼키지도 않는다** — 경고 로그 + Sentry 이벤트로 남긴다. 조용히 사라지면
  배선이 없는 것과 같다.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.engine import Engine

_FALLBACK_LOGGER = logging.getLogger("loop_heartbeat")


def capture_exception(message: Optional[str] = None) -> None:
    """지금 처리 중인 예외를 Sentry 로 올린다(``except`` 블록 안에서만 부른다).

    잡아서 로그로만 찍은 예외는 SDK 가 스스로 보지 못한다 — 그래서 명시로 올린다.

    Args:
        message: 예외 대신 올릴 메시지. 생략하면 현재 예외를 올린다.

    Returns:
        None. ``SENTRY_DSN`` 이 없으면 클라이언트가 없어 no-op 이고, ``sentry-sdk``
        미설치 환경에서는 조용히 지나간다(관측 배선이 본 작업을 막으면 안 된다).
    """
    try:
        import sentry_sdk
    except ImportError:
        return
    if message is None:
        sentry_sdk.capture_exception()
    else:
        sentry_sdk.capture_message(message)


def emit_heartbeat(
    engine: Engine,
    worker_kind: str,
    *,
    metadata: Optional[dict[str, Any]] = None,
    oldest_lag_seconds: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """이번 tick 의 생존 신호를 남긴다. 실패해도 예외를 올리지 않는다.

    **일을 안 한 tick 에서도 부른다.** 시각 창 밖이라 건너뛰면 하루 대부분 하트비트가 낡아
    보여 감시가 무의미해진다 — "루프가 죽었다" 와 "지금은 일할 시각이 아니다" 를 가르는 것이
    이 배선의 목적이다.

    Args:
        engine: 하트비트를 쓸 DB 엔진.
        worker_kind: ``side_effect_worker_heartbeats`` PK. 등록부
            (:data:`foms.services.sidefx_worker.WORKER_KIND_SPECS`)에 있어야 누가 읽는다.
        metadata: 이번 tick 요약(집계 수치만). **고객 정보(이름·전화·주소)는 넣지 않는다** —
            이 표는 운영 감시용이다.
        oldest_lag_seconds: scan 계열 kind 의 마지막 스캔 이후 경과(초).
        logger: 경고를 남길 로거. 생략하면 이 모듈 로거.

    Returns:
        기록에 성공했으면 True, 실패했으면 False(경고 로그 + Sentry 이벤트를 남긴 뒤).
    """
    from foms.services.sidefx_worker import upsert_heartbeat

    log = logger or _FALLBACK_LOGGER
    try:
        upsert_heartbeat(engine, worker_kind, metadata=metadata,
                         oldest_lag_seconds=oldest_lag_seconds)
        return True
    except Exception:
        log.warning("heartbeat upsert failed worker_kind=%s", worker_kind, exc_info=True)
        capture_exception()
        return False
