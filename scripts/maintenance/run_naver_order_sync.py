"""네이버 스마트스토어 주문 수집 실행 (NAVER-INGEST-01 §3.1).

**이 스크립트는 WORKER 서비스에서만 돈다.** 커머스API센터 애플리케이션의 호출 IP 한도는 3개고
Railway static outbound IP 도 서비스당 3개다. 정확히 3=3이라 여유가 없어, 네이버로 나가는
HTTP 는 WORKER 한 곳에서만 나가야 한다. web 에서 실행하면 등록되지 않은 IP 라 차단된다.

주기 실행 배선은 알림 escalation 스윕과 같은 구조다(FOMS 는 in-process 스케줄러가 없고 새
인프라 의존성 추가는 금지). ``--loop`` 는 앱을 1회만 부팅하고 interval 간격으로 스윕을
반복하며, 스윕 1회 실패가 루프를 죽이지 않는다. 다중 replica 여도 멱등이라 안전하다
(중복은 ``UNIQUE (channel, external_id)`` 가 막는다).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_naver_order_sync.py --once --dry-run --json
    python scripts/maintenance/run_naver_order_sync.py --once
    python scripts/maintenance/run_naver_order_sync.py --loop --interval 300 --json
"""
import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Optional

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import engine, get_db  # noqa: E402
from foms.services.integrations.naver_commerce.ingest import run_sweep  # noqa: E402
from foms.services.loop_heartbeat import (  # noqa: E402
    capture_exception,
    emit_heartbeat,
    init_sentry_once,
)
from foms.services.sidefx_worker import WORKER_KIND_NAVER_ORDER_SYNC  # noqa: E402

_LOGGER = logging.getLogger("naver_order_sync")

#: 이 루프의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_NAVER_ORDER_SYNC

#: --loop 최소 간격(초). 이보다 촘촘하면 rate limit 만 소모한다.
MIN_INTERVAL_SECONDS = 60

#: 잠을 쪼개는 단위(초). **일하는 주기와 살아 있다고 말하는 주기를 분리**한다.
#: 스윕은 그대로 interval 마다 1회만 돌고(네이버 HTTP 호출 증가 0), 자는 동안에는
#: 이 간격으로 DB 하트비트만 남긴다. 신고 간격이 좁아지면 판정부
#: (:func:`foms.services.sidefx_worker.effective_heartbeat_budget`)가 예산을
#: ``max(등록부 900, 60 x 3)`` = 900초로 잡아, 자는 도중 죽은 루프가 감시 주기 60초
#: (``tools/ops/run_domain_side_effect_outbox.py``)를 더해 최대 16분 안에 잡힌다
#: (예전에는 신고 1800 -> 예산 5400 이라 90분+ 침묵했다).
HEARTBEAT_TICK_SECONDS = 60


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Naver SmartStore orders into FOMS.")
    parser.add_argument("--once", action="store_true",
                        help="1회만 수집(기본 동작 — 명시용 플래그).")
    parser.add_argument("--dry-run", action="store_true",
                        help="조회까지만 하고 주문·링크·워터마크를 만들지 않는다.")
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 요약 출력.")
    parser.add_argument("--loop", action="store_true",
                        help="장기 실행 루프: 앱 1회 부팅 후 interval 간격 반복 (start.sh 배선용).")
    parser.add_argument("--interval", type=int, default=300,
                        help=f"--loop 간격(초, 기본 300, 최소 {MIN_INTERVAL_SECONDS}).")
    return parser.parse_args()


def _sweep_once(dry_run: bool) -> dict:
    """단일 수집 실행(호출측이 app_context 보유). 커밋은 run_sweep 이 소유한다."""
    db = get_db()
    try:
        return run_sweep(db, dry_run=dry_run)
    except Exception:
        db.rollback()
        raise


def _print_result(result: dict, as_json: bool) -> None:
    """수집 결과를 사람/기계 판독 형식으로 출력."""
    if as_json:
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    ts = datetime.now().strftime("%H:%M:%S")
    window = result.get("window") or {}
    print(
        f"[{ts}] naver sync: changed={result.get('changed')} "
        f"candidates={result.get('candidates')} created={result.get('created')} "
        f"skipped={result.get('skipped')} pending={result.get('pending_review')} "
        f"dry_run={result.get('dry_run')} window={window.get('from')}~{window.get('to')}",
        flush=True,
    )


def _heartbeat_metadata(result, interval: int = 0,
                        outcome: Optional[str] = None) -> dict:
    """하트비트에 실을 집계값. 주문 식별자·고객 정보는 싣지 않는다(운영 감시용).

    ``interval_seconds`` 는 판정부가 예산을 잡는 근거다 — 이 루프의 간격은 env
    (``FOMS_NAVER_SYNC_INTERVAL_SECONDS``)로 바뀐다(스테이징 실측 1800초).

    ``outcome`` 을 넘기면 스윕 결과 대신 그 값을 쓴다 — 스윕 **전에** 남기는 하트비트를
    ``sweep_failed`` 로 거짓 기록하지 않기 위해서다.
    """
    payload = result or {}
    return {
        "interval_seconds": int(interval or 0),
        "outcome": outcome or ("ok" if result is not None else "sweep_failed"),
        "changed": int(payload.get("changed") or 0),
        "candidates": int(payload.get("candidates") or 0),
        "created": int(payload.get("created") or 0),
        "pending_review": int(payload.get("pending_review") or 0),
    }


def _beat(result: Optional[dict], declared_interval: int,
          outcome: Optional[str] = None) -> None:
    """하트비트 1건을 남긴다.

    ``declared_interval`` 은 스윕 주기가 아니라 **다음 하트비트까지 벌어질 수 있는 최대
    공백**(초)이다. 판정부가 ``max(등록부 기본값, 신고 x 3)`` 으로 예산을 잡으므로 이
    값이 곧 정지 감지 지연을 정한다.

    Args:
        result: 마지막 스윕 결과. 스윕이 터졌으면 ``None``(metadata 의 ``outcome`` 이
            ``sweep_failed`` 가 된다).
        declared_interval: 이 하트비트가 신고할 최대 공백(초).
        outcome: metadata 의 ``outcome`` 을 이 값으로 고정한다(스윕 전 하트비트용).

    Returns:
        None. 기록 실패는 :func:`emit_heartbeat` 가 경고 로그 + Sentry 로 남기고 삼킨다
        (관측 배선이 수집을 멈추면 더 나쁜 실패다).
    """
    emit_heartbeat(engine, HEARTBEAT_WORKER_KIND,
                   metadata=_heartbeat_metadata(result, declared_interval, outcome),
                   logger=_LOGGER)


def _sleep_with_heartbeats(interval: int, result: Optional[dict],
                           tick: int = HEARTBEAT_TICK_SECONDS) -> None:
    """다음 스윕까지의 잠을 ``tick`` 초로 쪼개고 조각마다 하트비트를 남긴다.

    별도 스레드를 쓰지 않는다 — 스레드는 루프 본체가 멎어도 계속 뛰어 "살아 있다" 고
    거짓말한다(``tools/ops/run_rq_worker.py`` 가 같은 이유로 스레드를 배제했다).
    스윕 호출 횟수는 그대로라 네이버 HTTP 호출은 한 번도 늘지 않는다 — 늘어나는 것은
    분당 하트비트 upsert 1회뿐이다.

    신고값 규칙이 이 함수의 핵심이다.

    * 마지막 조각이 아니면 ``tick``(60)을 신고한다 -> 예산 900초. 자는 도중 죽으면
      감시 주기 60초를 더해 최대 16분 안에 잡힌다.
    * 마지막 조각 뒤에는 곧바로 스윕이 시작되므로 ``interval``(운영 1800)을 신고해 예산을
      스윕 허용치로 되넓힌다. ``resolve_window``(naver_commerce/watermark.py)에는 구간
      상한이 없어, 며칠 멎어 있다 살아난 첫 스윕은 24시간씩 쪼개 여러 번 도느라 길어질
      수 있다. 거기서 예산을 좁게 두면 2026-09-08 헛알림을 그대로 되풀이한다.

    Args:
        interval: 스윕 주기(초). 잠의 총합이자 마지막 조각의 신고값이다.
        result: 마지막 스윕 결과(하트비트 metadata 용).
        tick: 잠 한 조각의 길이(초).

    Returns:
        None.
    """
    remaining = interval
    while remaining > 0:
        nap = min(tick, remaining)
        # 모듈 속성으로 부른다 — 계약 테스트가 이 자리에서 루프를 끊는다.
        time.sleep(nap)
        remaining -= nap
        _beat(result, interval if remaining <= 0 else tick)


def _run_loop(interval: int, dry_run: bool, as_json: bool) -> int:
    """앱 1회 부팅 후 interval 간격 반복. 스윕 실패는 기록 후 계속(루프 생존)."""
    interval = max(MIN_INTERVAL_SECONDS, interval)
    print(f"[naver-sync-loop] started (interval={interval}s)", flush=True)
    while True:
        result = None
        # 스윕 **전에** 넓은 예산을 신고한다. 이 한 줄이 첫 스윕(재배포 직후, 밀린 구간을
        # 따라잡느라 길다 — resolve_window 에 구간 상한이 없다)과 매 사이클 스윕을 함께
        # 덮는다. 여기가 없으면 표에 남은 마지막 신고가 tick(60)이라 예산이 900 뿐이고,
        # 멀쩡히 따라잡는 루프에 2026-09-08 과 같은 헛알림이 난다.
        _beat(None, interval, outcome="sweeping")
        try:
            with app.app_context():
                result = _sweep_once(dry_run)
            _print_result(result, as_json)
        except Exception:
            # 스윕 1회 실패가 루프를 죽이면 수집이 통째로 꺼진다(조용한 중단이 최악).
            print("[naver-sync-loop] sweep failed:", flush=True)
            traceback.print_exc()
            capture_exception()
        # 스윕이 터진 tick 도 하트비트를 남긴다 — "죽었다" 와 "이번 스윕만 실패" 를 가른다.
        # 신고값은 tick 이다: 이 하트비트 다음에 오는 것은 스윕이 아니라 60초 낮잠이라,
        # 여기서 interval 을 신고하면 자는 동안 예산이 90분으로 되넓어진다(넓은 예산이
        # 필요한 자리는 스윕 **앞**이고, 그것은 위에서 이미 신고했다).
        _beat(result, HEARTBEAT_TICK_SECONDS)
        _sleep_with_heartbeats(interval, result)


def run() -> int:
    """CLI 진입점.

    Sentry 는 진입점에서 공용 게이트로 붙인다. 이 파일은 상단에서 ``app`` 을 import 하므로
    사실상 이미 붙어 있고(``app_factory`` 가 ``init_sentry`` 를 부른다), 게이트는 그때
    다시 init 하지 않는다 — 앞 클라이언트를 갈아치우면 전송 대기 이벤트가 유실된다.
    그럼에도 명시로 부르는 이유는 배선을 한 벌로 두기 위해서다(러너마다 다른 방식으로
    붙이면 어디가 비었는지 아무도 모른다).

    Returns:
        프로세스 종료 코드(``--loop`` 는 정상 경로에서 돌아오지 않는다).
    """
    init_sentry_once(_LOGGER)
    args = _parse_args()
    if args.loop:
        return _run_loop(args.interval, args.dry_run, args.json)

    with app.app_context():
        result = _sweep_once(args.dry_run)
    _print_result(result, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(run())
