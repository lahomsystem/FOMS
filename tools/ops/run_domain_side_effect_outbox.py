"""domain side-effect outbox worker (SIDEFX-WORKER-01).

SIDEFX-00 outbox 를 소비하는 delivery/expiry/retention worker 다. 세 loop 를 한
프로세스에서 돌린다:

* delivery: ``--interval`` 초마다 PENDING 을 claim → 도메인 handler dispatch → DONE/재시도/DEAD.
* expiry scan: ``--expiry-scan-interval`` 초마다 만료 lease 회수(죽은 worker 회복).
* retention scan: ``--retention-scan-interval`` 초마다 terminal 행 purge(DONE 30d/DEAD 180d).

10 초마다 세 worker_kind heartbeat 를 upsert 하고, SIGTERM/SIGINT 에 graceful shutdown 한다.

**실 provider I/O 는 도메인 handler 몫**(하류 CHANNEL-WRITER-01·URGENT-CALL-01·NOTIFICATION).
이 프로세스는 mechanics 만 수행한다 — handler registry 가 비어 있으면(이 packet 만 배포된
상태) dispatch 가 NoHandler 로 재시도/DEAD 되므로 handler 배포 전에는 delivery 를 켜지 않는다.

현재 등록된 delivery handler(=delivery 를 켜도 DEAD 로 떨어지지 않는 effect_type):

* ``STORAGE_DELETE`` — :func:`foms.services.storage_delete_handler.handle_storage_delete`
  (WIZ-DELETE-01, 공용·source_domain 분기).
* ``GEOCODE`` — :func:`foms.services.geocode_delivery_handler.handle_geocode`
  (DATA-MEASUREMENT-01 소비단. 주소 변경 tx 가 예약한 행을 소비해 Order 좌표를 채운다).
* ``ALIMTALK_SEND`` — :func:`foms.services.alimtalk_delivery_handler.handle_alimtalk_send`
  (실측 예약 알림톡 자동 발송. 수동 발송은 요청 스레드 동기).

그 밖의 effect_type(NOTIFICATION·CACHE_INVALIDATE 등)은 아직 handler 가 없다 — 그 종류의
행이 쌓이는 도메인을 켜기 전에 handler 를 먼저 배포해야 한다.

배포: ``railway-domain-sidefx.toml`` 별도 service, start command
``python tools/ops/run_domain_side_effect_outbox.py --loop --interval 5
--expiry-scan-interval 300 --retention-scan-interval 86400``.

exit code: 0 정상 종료(--once 완료 또는 graceful shutdown), 1 부팅/치명 오류.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import logging
import os
import signal
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.sidefx_worker import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    HEARTBEAT_INTERVAL_SECONDS,
    WORKER_KIND_DELIVERY,
    WORKER_KIND_EXPIRY_SCAN,
    WORKER_KIND_RETENTION,
    make_engine_from_env,
    oldest_pending_lag_seconds,
    register_expiry_scan_provider,
    register_handler,
    run_delivery_once,
    run_expiry_scan_once,
    run_retention_once,
    upsert_heartbeat,
)
from foms.services.alimtalk_delivery_handler import handle_alimtalk_send  # noqa: E402
from foms.services.geocode_delivery_handler import handle_geocode
from foms.services.record_only_effects import (
    CHANNEL_PUSH_RECORDED_EFFECT_TYPE,
    handle_record_only,
)  # noqa: E402
from foms.services.storage_delete_handler import handle_storage_delete  # noqa: E402
from foms.services.upload_cleanup import run_upload_expiry_scan_once  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

_LOGGER = logging.getLogger("run_domain_side_effect_outbox")


def _owner_hash() -> str:
    """이 worker 인스턴스의 안정적 식별 해시(hostname:pid:uuid → sha256)."""
    raw = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Domain side-effect outbox worker (SIDEFX-WORKER-01)."
    )
    p.add_argument("--loop", action="store_true",
                   help="장기 실행 루프. 미지정 시 delivery+expiry+retention 한 번만 돌고 종료(--once 동치).")
    p.add_argument("--once", action="store_true",
                   help="단발 실행(--loop 없이도 기본이 단발이나, 명시용).")
    p.add_argument("--interval", type=int, default=5,
                   help="delivery poll 간격(초, 기본 5, 최소 1).")
    p.add_argument("--expiry-scan-interval", type=int, default=300,
                   help="만료 lease 회수 scan 간격(초, 기본 300).")
    p.add_argument("--retention-scan-interval", type=int, default=86400,
                   help="retention purge scan 간격(초, 기본 86400).")
    p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS,
                   help=f"claim lease 유효기간(초, 기본 {DEFAULT_LEASE_SECONDS}).")
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
                   help=f"이 횟수만큼 실패하면 DEAD(기본 {DEFAULT_MAX_ATTEMPTS}).")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                   help=f"delivery/reclaim 배치 크기(기본 {DEFAULT_BATCH_SIZE}).")
    p.add_argument("--retention-limit", type=int, default=1000,
                   help="retention 배치당 삭제 상한(기본 1000).")
    return p.parse_args(argv)


class _Clock:
    """마지막 성공 scan 시각을 기록해 heartbeat lag 를 산출한다."""

    def __init__(self, now: datetime.datetime) -> None:
        self.last_expiry_scan_at = now
        self.last_retention_scan_at = now

    def scan_lag(self, last: datetime.datetime, now: datetime.datetime) -> int:
        return max(0, int((now - last).total_seconds()))


def _emit_heartbeats(engine: Engine, clock: _Clock) -> None:
    """세 worker_kind heartbeat 를 upsert 한다(delivery=pending lag, scan=마지막 scan 이후 lag)."""
    now = now_utc_naive()
    session_local = sessionmaker(bind=engine)
    s = session_local()
    try:
        pending_lag = oldest_pending_lag_seconds(s, now=now)
    finally:
        s.close()
    upsert_heartbeat(engine, WORKER_KIND_DELIVERY, oldest_lag_seconds=pending_lag, now=now)
    upsert_heartbeat(engine, WORKER_KIND_EXPIRY_SCAN,
                     oldest_lag_seconds=clock.scan_lag(clock.last_expiry_scan_at, now), now=now)
    upsert_heartbeat(engine, WORKER_KIND_RETENTION,
                     oldest_lag_seconds=clock.scan_lag(clock.last_retention_scan_at, now), now=now)


def _run_cycle(engine: Engine, args: argparse.Namespace, owner: str) -> dict:
    """delivery + expiry + retention 한 번씩 실행하고 결과를 반환(--once 용)."""
    delivery = run_delivery_once(
        engine, owner_hash=owner, lease_token_fn=lambda: str(uuid.uuid4()),
        lease_seconds=args.lease_seconds, max_attempts=args.max_attempts,
        batch_size=args.batch_size,
    )
    reclaim = run_expiry_scan_once(
        engine, max_attempts=args.max_attempts, batch_size=args.batch_size)
    retention = run_retention_once(engine, limit=args.retention_limit)
    _emit_heartbeats(engine, _Clock(now_utc_naive()))
    return {"delivery": delivery, "reclaim": reclaim, "retention": retention}


def _run_loop(engine: Engine, args: argparse.Namespace, owner: str,
              stop: threading.Event) -> int:
    """delivery 를 interval 마다, scan 은 각자 주기로, heartbeat 는 10 초마다 반복한다."""
    interval = max(1, args.interval)
    now = now_utc_naive()
    clock = _Clock(now)
    next_delivery = next_expiry = next_retention = next_heartbeat = time.monotonic()
    _LOGGER.info("[sidefx-worker] started owner=%s interval=%ds expiry=%ds retention=%ds",
                 owner[:12], interval, args.expiry_scan_interval, args.retention_scan_interval)
    while not stop.is_set():
        mono = time.monotonic()
        if mono >= next_delivery:
            _safe(lambda: run_delivery_once(
                engine, owner_hash=owner, lease_token_fn=lambda: str(uuid.uuid4()),
                lease_seconds=args.lease_seconds, max_attempts=args.max_attempts,
                batch_size=args.batch_size), "delivery")
            next_delivery = mono + interval
        if mono >= next_expiry:
            if _safe(lambda: run_expiry_scan_once(
                    engine, max_attempts=args.max_attempts, batch_size=args.batch_size),
                    "expiry-scan"):
                clock.last_expiry_scan_at = now_utc_naive()
            next_expiry = mono + max(1, args.expiry_scan_interval)
        if mono >= next_retention:
            if _safe(lambda: run_retention_once(engine, limit=args.retention_limit),
                     "retention-scan"):
                clock.last_retention_scan_at = now_utc_naive()
            next_retention = mono + max(1, args.retention_scan_interval)
        if mono >= next_heartbeat:
            _safe(lambda: _emit_heartbeats(engine, clock), "heartbeat")
            next_heartbeat = mono + HEARTBEAT_INTERVAL_SECONDS
        stop.wait(min(interval, HEARTBEAT_INTERVAL_SECONDS))
    _LOGGER.info("[sidefx-worker] graceful shutdown")
    return 0


def _safe(fn, label: str) -> bool:
    """loop step 을 실행하고 예외를 삼키지 않고 로그로 남긴 뒤 계속한다(한 step 실패가 worker 를 죽이지 않게)."""
    try:
        fn()
        return True
    except Exception:  # noqa: BLE001 — 로그로 기록(삼키지 않음), 다음 주기에 재시도
        _LOGGER.exception("[sidefx-worker] %s step failed", label)
        return False


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    owner = _owner_hash()
    # WIZ-DELETE-01(task #44): STORAGE_DELETE delivery handler 를 등록한다(공용·source_domain
    # 분기). 이게 없으면 STORAGE_DELETE 행이 NoHandler → 재시도 → DEAD 로 쌓인다. replace=True
    # 로 재시작·재-import 시 중복 등록을 idempotent 하게 처리한다.
    register_handler("STORAGE_DELETE", handle_storage_delete, replace=True)
    # DATA-MEASUREMENT-01: 주소 변경이 예약한 GEOCODE 행을 소비한다. 이게 없으면 운영에 쌓인
    # GEOCODE PENDING 이 NoHandler 로 10회 재시도 후 전부 DEAD 가 된다(readiness fail-closed).
    register_handler("GEOCODE", handle_geocode, replace=True)
    # 실측 알림톡 자동 발송. 이게 없으면 ALIMTALK_SEND 행이 NoHandler → DEAD.
    register_handler("ALIMTALK_SEND", handle_alimtalk_send, replace=True)
    # SIDEFX-RECORDONLY-01: 배달할 일이 없는 기록 전용 effect. 등록하지 않으면 NoHandler 로
    # 10회 재시도 후 DEAD 로 쌓여 **진짜 실패를 덮는다**(운영 실측 1,188행, 2026-09-02).
    register_handler(CHANNEL_PUSH_RECORDED_EFFECT_TYPE, handle_record_only, replace=True)
    # UPLOAD-02: 만료 ticket/draft cleanup 을 300s expiry scan 에 배선(별도 scheduler 없음).
    # replace=True 로 재시작·재-import 시 중복 등록을 idempotent 하게 처리한다.
    register_expiry_scan_provider("upload_expiry", run_upload_expiry_scan_once, replace=True)
    try:
        engine = make_engine_from_env()
    except Exception:
        _LOGGER.exception("[sidefx-worker] engine init failed")
        return 1
    try:
        if not args.loop:
            result = _run_cycle(engine, args, owner)
            _LOGGER.info("[sidefx-worker] once: %s", result)
            return 0
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        return _run_loop(engine, args, owner, stop)
    except Exception:
        _LOGGER.exception("[sidefx-worker] fatal")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
