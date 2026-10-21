"""'상담 먼저' 알림톡 카톡 실패 → 링크 문자 자동 발송 스윕 실행.

코어 로직은 ``foms.api.share_sms_fallback.run_consult_sms_sweep`` 이다. FOMS 에는 in-process 주기 스케줄러가
없어 WORKER 감독자(``tools/ops/worker_supervisor.py``)가 ``--loop`` 로 띄운다. 여러 replica 가
동시에 돌아도 한 발송에 문자는 한 번만 나간다(이벤트 행 잠금).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_share_consult_fallback.py --json
    python scripts/maintenance/run_share_consult_fallback.py --loop --interval 60 --json

설계서: ``docs/specs/2026-10-21-consult-sms-fallback-design.md``.
"""
import argparse
import json
import logging
import os
import sys
import time
import traceback

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import db_session, engine  # noqa: E402
from foms.api.share_sms_fallback import run_consult_sms_sweep  # noqa: E402
from foms.services.loop_heartbeat import (  # noqa: E402
    capture_exception,
    emit_heartbeat,
    init_sentry_once,
    safe_metadata,
)
from foms.services.sidefx_worker import WORKER_KIND_SHARE_CONSULT_SMS  # noqa: E402

_LOGGER = logging.getLogger("share_consult_fallback")

#: 이 루프의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_SHARE_CONSULT_SMS


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send link SMS when a consult-first alimtalk failed.")
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 요약 출력.")
    parser.add_argument("--loop", action="store_true",
                        help="장기 실행 루프 모드: 앱을 1회만 부팅하고 interval 간격으로 스윕을 반복.")
    parser.add_argument("--interval", type=int, default=60,
                        help="--loop 모드 스윕 간격(초, 기본 60, 최소 15).")
    return parser.parse_args()


def _sweep_once() -> dict:
    """스윕 1회(호출측이 app_context 보유). 실패하면 롤백하고 예외를 올린다."""
    try:
        return run_consult_sms_sweep(db_session)
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.remove()


def _heartbeat_metadata(result, interval: int = 0) -> dict:
    """하트비트에 실을 집계값. 고객 정보(번호·이름·주문)는 싣지 않는다."""
    counts = result or {}
    return {
        "interval_seconds": int(interval or 0),
        "outcome": "ok" if result is not None else "sweep_failed",
        "delivered": int(counts.get("delivered") or 0),
        "pending": int(counts.get("pending") or 0),
        "sms_sent": int(counts.get("sms_sent") or 0),
        "sms_failed": int(counts.get("sms_failed") or 0),
    }


def _run_loop(interval: int, as_json: bool) -> int:
    """앱 1회 부팅 후 interval 간격으로 스윕 반복. 스윕 실패는 기록 후 계속."""
    interval = max(15, interval)
    print(f"[consult-sms-loop] started (interval={interval}s)", flush=True)
    while True:
        result = None
        try:
            with app.app_context():
                result = _sweep_once()
            if as_json or result:
                print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception:
            print("[consult-sms-loop] sweep failed:", flush=True)
            traceback.print_exc()
            capture_exception()
        metadata = safe_metadata(
            lambda: _heartbeat_metadata(result, interval),
            {"interval_seconds": interval, "outcome": "ok" if result is not None else "sweep_failed",
             "delivered": 0, "pending": 0, "sms_sent": 0, "sms_failed": 0},
            logger=_LOGGER, label="consult-sms",
        )
        emit_heartbeat(engine, HEARTBEAT_WORKER_KIND, metadata=metadata, logger=_LOGGER)
        time.sleep(interval)


def run() -> int:
    """CLI 진입점. 정상 종료 0."""
    init_sentry_once(_LOGGER)
    args = _parse_args()
    if args.loop:
        return _run_loop(args.interval, args.json)
    with app.app_context():
        result = _sweep_once()
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
