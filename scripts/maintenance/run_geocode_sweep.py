"""GEO-SWEEP-01 — 좌표 없는 주문을 주기적으로 RQ 지오코딩 큐에 넣는 스윕.

왜 필요한가 (2026-08-31 운영 진단)
    2026-07-27 이후 주문 생성·주소 수정의 지오코딩 예약이 RQ 큐에서 SIDEFX outbox
    (``enqueue_order_address_geocode``)로 옮겨졌는데, **SIDEFX 워커는 운영에 배포된 적이
    없다**(``side_effect_worker_heartbeats`` 0행, ``domain_side_effect_outbox`` 전 행
    PENDING). 그래서 신규 주문은 좌표 없이 만들어지고, 사용자가 지도를 열 때
    ``foms/api/measurement/map.py`` 가 한 건씩 RQ 로 넘겨 그제서야 변환된다.
    RQ 워커(``rq worker default``)는 살아 있으므로, 이 스윕이 미리 채워 두면 지도가
    처음부터 다 보인다. outbox 계보는 그대로 두고 **그 위에 얹는 안전망**이다.

무엇을 집는가
    술어 SSOT 는 :mod:`foms.services.geocode_candidates` (백필 CLI
    ``tools/ops/backfill_geocode_missing.py`` 와 공용). 이 스윕의 대상은

    * ``geocode_status IS NULL`` — 한 번도 시도 안 한 건.
    * ``geocode_status='pending'`` 이면서 마지막 시도가 :data:`PENDING_RETRY_SECONDS`
      보다 오래된 건(시각 불명=NULL 포함) — 주소 수정 경로가 ``pending`` 만 찍고 죽은
      outbox 에 예약해 영구 고착된 계열의 유일한 구제책.
    * ``geocode_status='failed'`` 이면서 마지막 시도가 :data:`FAILED_RETRY_SECONDS`
      보다 오래된 건 — 사유 불명 실패(레거시 포함)를 하루 1회 다시 시도한다.
      ``--include-failed`` 를 주면 나이 제한 없이 전부 집는다(운영자 수동 실행용).
    * ``geocode_status='address_error'`` 는 **어떤 경우에도 제외**. 카카오가 "그런 주소
      없음"이라고 답한 건이라 반복 호출은 쿼터만 태운다(GEO-FAILKIND-01).

사용 예 (PowerShell 5.x / bash 동일)::

    python scripts/maintenance/run_geocode_sweep.py --once
    python scripts/maintenance/run_geocode_sweep.py --once --json --batch 20
    python scripts/maintenance/run_geocode_sweep.py --loop --interval 60 --json

exit code: 0=정상(정상 종료·시그널 종료 포함), 1=치명(큐 사용 불가 등).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import signal
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.geocode_candidates import build_missing_geocode_query  # noqa: E402
from foms.services import geocode_retry  # noqa: E402
from foms.services.geocode_helpers import extract_address_from_order  # noqa: E402
from models import Order  # noqa: E402

# 한 라운드에서 큐에 넣을 최대 건수. 카카오 쿼터·워커 적체를 함께 고려한 보수적 기본값.
DEFAULT_BATCH = 50

# --loop 기본 간격(초)과 하한. 하한을 두는 이유: 간격을 1초로 주면 워커가 소진하기도
# 전에 같은 후보를 다시 훑어 DB 쿼리만 태운다.
DEFAULT_INTERVAL_SECONDS = 60
MIN_INTERVAL_SECONDS = 15

# ``pending`` 재시도 임계값(초).
#
# 운영 실측상 지오코딩은 건당 약 2.9초이고 RQ 워커는 동시성 1(완전 직렬)이다.
# 배치 50건이면 소진에 약 145초가 걸리는데 스윕 간격은 60초다. 스윕이 "예약했음"을
# 표시하지 않으면 두 번째 라운드가 돌 때 첫 라운드 주문들은 아직 ``lat IS NULL`` 이라
# **같은 주문이 매 라운드 다시 큐에 들어가** 큐가 중복 잡으로 부풀고 진짜 신규 건이
# 뒤로 밀린다. 그래서 enqueue 직전에 ``geocode_status='pending'`` + ``geocoded_at`` 를
# 찍고(=시도 표식), 그보다 최근에 찍힌 건은 이번 라운드에서 건너뛴다.
# 600초 = 최악 소진 시간(50건 x 2.9초 ~= 145초)의 약 4배 여유. 워커가 밀려도 중복
# enqueue 없이 조용히 기다렸다가, 정말 처리되지 않은 건만 다시 집는다.
PENDING_RETRY_SECONDS = int(geocode_retry.PENDING_RETRY_INTERVAL.total_seconds())

# ``failed`` 재시도 임계값(초) — 정본은 :mod:`foms.services.geocode_retry`.
#
# 2026-09-01 조사: 일시 오류가 전부 ``failed`` 로 굳는데 스윕·범용 지도 어느 쪽도 그 건을
# 다시 시도하지 않아, 주소가 멀쩡한 11건이 사람 손을 탈 때까지 좌표 없이 남았다. 이제
# 진짜 주소 오류는 ``address_error`` 로 갈라지므로 남은 ``failed`` 는 하루 1회 재시도한다.
FAILED_RETRY_SECONDS = int(geocode_retry.FAILED_RETRY_INTERVAL.total_seconds())

_LOG_PREFIX = "[geocode-sweep]"

# SIGTERM/SIGINT 수신 플래그. 루프는 라운드 경계에서만 빠져나간다(작업 중단 없음).
_shutdown = threading.Event()

_Session = sessionmaker(bind=engine)


def _attempt_stamp() -> datetime.datetime:
    """``Order.geocoded_at`` 에 기록할 "마지막 지오코딩 시도" 시각.

    좌표 반영 SSOT(:func:`foms.services.geocode_helpers.apply_geocode_to_order`)가
    ``now_utc_naive()`` 로 같은 컬럼을 쓴다. 스윕이 다른 시계(로컬 ``datetime.now()``)로
    쓰면 dev(KST)에서 9시간 어긋나 나이 판정이 뒤집히므로 같은 함수를 쓴다.

    Returns:
        naive UTC datetime.
    """
    return now_utc_naive()


def _log(message: str) -> None:
    """스윕 표준 로그 1줄 출력(컨테이너 로그 수집용으로 즉시 flush).

    Args:
        message: 접두어 뒤에 붙일 본문.
    """
    print(f"{_LOG_PREFIX} {message}", flush=True)


def _log_error(message: str) -> None:
    """스윕 에러 로그 1줄 출력(stderr).

    Args:
        message: 접두어 뒤에 붙일 본문.
    """
    print(f"{_LOG_PREFIX} {message}", file=sys.stderr, flush=True)


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """CLI 인자 파싱.

    Args:
        argv: 인자 목록(None 이면 ``sys.argv[1:]``). 테스트 주입용.

    Returns:
        파싱된 :class:`argparse.Namespace`.
    """
    parser = argparse.ArgumentParser(
        description="좌표 없는 주문을 RQ 지오코딩 큐에 넣는 스윕",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true',
                      help="1회만 스윕하고 종료(기본 동작).")
    mode.add_argument('--loop', action='store_true',
                      help="--interval 간격으로 반복 (worker 컨테이너 배선용, start.sh 참조).")
    parser.add_argument('--interval', type=int, default=DEFAULT_INTERVAL_SECONDS,
                        help=f"--loop 스윕 간격(초, 기본 {DEFAULT_INTERVAL_SECONDS}, "
                             f"최소 {MIN_INTERVAL_SECONDS}).")
    parser.add_argument('--batch', type=int, default=DEFAULT_BATCH,
                        help=f"1회 라운드 최대 건수 (기본 {DEFAULT_BATCH}).")
    parser.add_argument('--include-failed', action='store_true',
                        help="geocode_status='failed' 건을 나이 제한 없이 전부 포함"
                             f" (기본은 {FAILED_RETRY_SECONDS}초 백오프). "
                             "address_error 는 이 옵션으로도 포함되지 않는다.")
    parser.add_argument('--json', action='store_true',
                        help="라운드마다 구조화 로그(JSON) 1줄 출력.")
    return parser.parse_args(argv)


def install_signal_handlers() -> None:
    """SIGTERM/SIGINT 를 받으면 현재 라운드를 마치고 정상 종료하도록 배선한다.

    메인 스레드가 아니거나(테스트 등) 플랫폼이 해당 시그널을 지원하지 않으면 조용히
    건너뛴다 — 시그널 배선 실패로 스윕 자체가 죽으면 안 된다.
    """
    def _handle(signum: int, _frame: Any) -> None:
        """시그널 핸들러: 종료 플래그만 세운다(라운드 중단 없음)."""
        _log(f"signal {signum} received; finishing current round then exiting")
        _shutdown.set()

    for sig_name in ('SIGTERM', 'SIGINT'):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _handle)
        except (ValueError, OSError, RuntimeError) as exc:
            _log(f"signal {sig_name} handler not installed: {exc}")


def sweep_once(
    session: Any,
    *,
    batch: int = DEFAULT_BATCH,
    include_failed: bool = False,
    pending_retry_seconds: int = PENDING_RETRY_SECONDS,
    failed_retry_seconds: int = FAILED_RETRY_SECONDS,
    now: Optional[datetime.datetime] = None,
) -> dict[str, int]:
    """스윕 1라운드: 후보를 골라 시도 표식을 커밋한 뒤 RQ 에 enqueue 한다.

    순서가 중요하다. ``geocode_status='pending'`` + ``geocoded_at`` 를 **커밋한 뒤에**
    enqueue 한다. 반대로 하면 워커가 먼저 끝내고 ``success`` 를 쓴 위에 스윕이 ``pending``
    을 덮어써서 상태가 거꾸로 간다.

    Args:
        session: SQLAlchemy 세션(호출자 소유 — 이 함수는 close 하지 않는다).
        batch: 이번 라운드에서 다룰 최대 건수.
        include_failed: True 면 ``failed`` 를 나이 제한 없이 전부 포함(수동 실행용).
        pending_retry_seconds: ``pending`` 을 다시 집기까지의 최소 경과 시간(초).
        failed_retry_seconds: ``failed`` 를 다시 집기까지의 최소 경과 시간(초).
        now: 기준 시각(테스트 주입용). None 이면 :func:`_attempt_stamp`.

    Returns:
        ``{'scanned', 'queued', 'skipped', 'failed'}`` 집계 dict.

    Raises:
        SQLAlchemyError: 시도 표식 커밋에 실패한 경우(롤백 후 재전파).
    """
    stamp = now or _attempt_stamp()
    cutoff = stamp - datetime.timedelta(seconds=max(0, int(pending_retry_seconds)))
    failed_cutoff = stamp - datetime.timedelta(seconds=max(0, int(failed_retry_seconds)))

    query = build_missing_geocode_query(
        session,
        include_failed=include_failed,
        pending_retry_before=cutoff,
        failed_retry_before=failed_cutoff,
    )
    rows = query.order_by(Order.id.desc()).limit(max(1, int(batch))).all()

    targets: list[Order] = []
    seen: set[int] = set()
    skipped = 0
    for order in rows:
        order_id = int(order.id)
        if order_id in seen:
            # 같은 라운드에서 같은 주문을 두 번 넣지 않는다.
            skipped += 1
            continue
        seen.add(order_id)
        # DB 술어는 ``Order.address`` 컬럼만 본다. ERP 주문의 정본 주소는
        # structured_data.site 이므로 실제 변환 가능한 주소인지 한 번 더 확인한다.
        address = (extract_address_from_order(order) or '').strip()
        if not address or address == '-':
            skipped += 1
            continue
        targets.append(order)

    result = {'scanned': len(rows), 'queued': 0, 'skipped': skipped, 'failed': 0}
    if not targets:
        return result

    for order in targets:
        order.geocode_status = 'pending'
        order.geocoded_at = stamp
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise

    from foms.services.jobs.queue import enqueue_geocode_order_address

    for order in targets:
        if enqueue_geocode_order_address(order.id):
            result['queued'] += 1
        else:
            result['failed'] += 1
    return result


def print_result(result: dict[str, int], as_json: bool) -> None:
    """라운드 집계를 사람/기계 판독 형식으로 1줄 출력한다.

    Args:
        result: :func:`sweep_once` 반환 dict.
        as_json: True 면 구조화 로그(JSON) 1줄.
    """
    if as_json:
        payload = {
            'event': 'geocode_sweep',
            'ts': _attempt_stamp().isoformat(timespec='seconds'),
            **result,
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return
    _log(
        f"scanned={result['scanned']} queued={result['queued']} "
        f"skipped={result['skipped']} failed={result['failed']}"
    )


def preflight_queue() -> bool:
    """RQ 큐를 쓸 수 있는지 먼저 확인한다(못 쓰면 에러 로그).

    ``REDIS_URL`` 이 없으면 ``enqueue_geocode_order_address`` 가 조용히 False 를
    반환한다. 그 상태로 루프를 돌면 "스윕은 도는데 좌표는 안 채워지는" 무음 실패가 되므로
    시작 전에 끊는다.

    Returns:
        큐를 쓸 수 있으면 True.
    """
    from foms.services.jobs.queue import get_rq_queue

    if get_rq_queue() is not None:
        return True
    if not os.environ.get('REDIS_URL'):
        _log_error(
            "FATAL: REDIS_URL 이 없어 지오코딩 큐에 넣을 수 없습니다. "
            "worker 컨테이너 환경변수를 확인하세요."
        )
    else:
        _log_error(
            "FATAL: REDIS_URL 은 있으나 RQ 큐 연결에 실패했습니다. "
            "Redis 도달 가능 여부를 확인하세요."
        )
    return False


def _run_round(**kwargs: Any) -> dict[str, int]:
    """세션을 새로 열어 :func:`sweep_once` 를 1회 실행하고 반드시 닫는다.

    라운드마다 세션을 새로 만드는 이유: 루프가 장시간 돌 때 커넥션을 붙잡은 채
    idle 로 남기지 않기 위해서다.

    Args:
        **kwargs: :func:`sweep_once` 로 그대로 넘길 키워드 인자.

    Returns:
        :func:`sweep_once` 집계 dict.
    """
    session = _Session()
    try:
        return sweep_once(session, **kwargs)
    finally:
        session.close()


def _run_loop(*, interval: int, batch: int, include_failed: bool, as_json: bool) -> int:
    """--loop 모드: 라운드 실패는 기록하고 계속 돈다.

    라운드 1회 실패가 루프를 죽이면 좌표 스윕이 통째로 꺼진다(다음 배포까지 무음).

    Args:
        interval: 라운드 간격(초). :data:`MIN_INTERVAL_SECONDS` 하한 적용.
        batch: 1회 라운드 최대 건수.
        include_failed: ``failed`` 건 포함 여부.
        as_json: 구조화 로그 출력 여부.

    Returns:
        프로세스 exit code (정상 종료 0).
    """
    interval = max(MIN_INTERVAL_SECONDS, int(interval))
    _log(
        f"started (interval={interval}s batch={batch} "
        f"include_failed={include_failed} pending_retry={PENDING_RETRY_SECONDS}s "
        f"failed_retry={FAILED_RETRY_SECONDS}s)"
    )
    while not _shutdown.is_set():
        try:
            result = _run_round(batch=batch, include_failed=include_failed)
            print_result(result, as_json)
            if result['failed']:
                _log_error(f"enqueue 실패 {result['failed']}건 (Redis 상태 확인 필요)")
        except (SQLAlchemyError, OSError, ValueError, RuntimeError):
            _log_error("round failed:")
            traceback.print_exc()
        _shutdown.wait(interval)
    _log("stopped")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 진입점.

    Args:
        argv: 인자 목록(None 이면 ``sys.argv[1:]``). 테스트 주입용.

    Returns:
        프로세스 exit code. 0=정상, 1=치명(큐 사용 불가·1회 실행 중 enqueue 실패).
    """
    args = _parse_args(argv)
    if not preflight_queue():
        return 1

    install_signal_handlers()
    if args.loop:
        return _run_loop(
            interval=args.interval,
            batch=args.batch,
            include_failed=args.include_failed,
            as_json=args.json,
        )

    result = _run_round(batch=args.batch, include_failed=args.include_failed)
    print_result(result, args.json)
    if result['failed']:
        _log_error(f"enqueue 실패 {result['failed']}건")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
