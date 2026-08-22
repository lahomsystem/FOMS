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
import os
import sys
import time
import traceback
from datetime import datetime

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.integrations.naver_commerce.ingest import run_sweep  # noqa: E402

#: --loop 최소 간격(초). 이보다 촘촘하면 rate limit 만 소모한다.
MIN_INTERVAL_SECONDS = 60


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


def _run_loop(interval: int, dry_run: bool, as_json: bool) -> int:
    """앱 1회 부팅 후 interval 간격 반복. 스윕 실패는 기록 후 계속(루프 생존)."""
    interval = max(MIN_INTERVAL_SECONDS, interval)
    print(f"[naver-sync-loop] started (interval={interval}s)", flush=True)
    while True:
        try:
            with app.app_context():
                result = _sweep_once(dry_run)
            _print_result(result, as_json)
        except Exception:
            # 스윕 1회 실패가 루프를 죽이면 수집이 통째로 꺼진다(조용한 중단이 최악).
            print("[naver-sync-loop] sweep failed:", flush=True)
            traceback.print_exc()
        time.sleep(interval)


def run() -> int:
    args = _parse_args()
    if args.loop:
        return _run_loop(args.interval, args.dry_run, args.json)

    with app.app_context():
        result = _sweep_once(args.dry_run)
    _print_result(result, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(run())
