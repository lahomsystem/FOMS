"""네이버 정산 동기화 실행 러너 (SETTLE-CHANNEL-01 §4).

**WORKER 서비스에서만 돈다.** 커머스API센터 애플리케이션의 호출 IP 한도는 3개고 Railway
static outbound IP 도 서비스당 3개다. 정확히 3=3이라 여유가 없어, 네이버로 나가는 HTTP 는
WORKER 한 곳에서만 나가야 한다. web 에서 실행하면 등록되지 않은 IP 라 차단된다.

주기 배선은 자동 발송처리 러너(``run_naver_auto_dispatch.py``)와 **같은 구조**다 — FOMS 에는
인앱 스케줄러가 없고 새 인프라 의존성(rq-scheduler·외부 cron)은 만들지 않는다. ``--loop`` 는
앱을 1회만 부팅하고 짧은 간격으로 깨어나, **하루 한 번 정해진 시각 창에 들어왔을 때만**
실행한다.

새벽에 도는 이유: 정산 조회는 하루당 2회(건별·수수료) x 45일이라 호출이 100회 안팎이고,
사람이 화면을 쓰는 시간대와 겹치면 "지금 동기화" 를 눌러도 쿼터를 나눠 쓰게 된다.

시각 창을 쓰는 이유: 워커가 재시작하거나 루프가 밀리면 정확히 그 분에 못 깨어날 수 있다.
창(기본 10분) 안이면 실행한다. 파티션 통째 교체라 **여러 번 돌아도 결과가 같다**(멱등).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_naver_settle_sync.py --once --dry-run --json
    python scripts/maintenance/run_naver_settle_sync.py --once --json
    python scripts/maintenance/run_naver_settle_sync.py --once --backfill-from 2026-06-04 --json
    python scripts/maintenance/run_naver_settle_sync.py --loop --at 05:30 --json
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Optional

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.datetime_kst import get_today_kst, now_kst  # noqa: E402
from foms.services.integrations.naver_commerce.client import (  # noqa: E402
    NaverCommerceClient,
)
from foms.services.integrations.naver_commerce.settle_sync import (  # noqa: E402
    run_settle_sync,
)

#: --loop 이 깨어나는 간격(초). 시각 창 판정만 하므로 짧아도 비용이 없다.
DEFAULT_TICK_SECONDS = 60

#: 시각 창 길이(분). 워커 재시작·루프 밀림으로 정각을 놓쳐도 이 안이면 실행한다.
DEFAULT_WINDOW_MINUTES = 10

#: 기본 실행 시각(KST) — 사람이 화면을 안 쓰는 시간대.
DEFAULT_AT = "05:30"


def _parse_args() -> argparse.Namespace:
    """CLI 인자를 읽는다(수동 점검 3종 + 배선 4종).

    Returns:
        파싱된 네임스페이스.
    """
    parser = argparse.ArgumentParser(
        description="Sync Naver settlement ledgers into FOMS on a daily schedule.")
    parser.add_argument("--once", action="store_true",
                        help="1회만 동기화(기본 동작 — 명시용 플래그).")
    parser.add_argument("--dry-run", action="store_true",
                        help="조회까지만 하고 DB 에 아무것도 쓰지 않는다(이력 행도 없다).")
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 요약 출력.")
    parser.add_argument("--loop", action="store_true",
                        help="장기 실행 루프: 앱 1회 부팅 후 시각 창을 지킨다(start.sh 배선용).")
    parser.add_argument("--at", default=os.environ.get("FOMS_NAVER_SETTLE_SYNC_AT", DEFAULT_AT),
                        help=f"--loop 실행 시각 HH:MM (KST, 기본 {DEFAULT_AT}).")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_MINUTES,
                        help=f"시각 창 길이(분, 기본 {DEFAULT_WINDOW_MINUTES}).")
    parser.add_argument("--tick", type=int, default=DEFAULT_TICK_SECONDS,
                        help=f"--loop 이 깨어나는 간격(초, 기본 {DEFAULT_TICK_SECONDS}).")
    parser.add_argument("--backfill-from", default=None,
                        help="소급 적재 시작일 YYYY-MM-DD (지정하면 확정 구간도 다시 읽는다).")
    return parser.parse_args()


def parse_at(value: str) -> tuple[int, int]:
    """``HH:MM`` 을 ``(시, 분)`` 으로 — 형식이 틀리면 :class:`ValueError`.

    Args:
        value: ``"05:30"`` 형태.

    Returns:
        ``(hour, minute)``.

    Raises:
        ValueError: 형식·범위 오류(조용히 기본값으로 떨어지지 않는다 — 그러면 사람이
            적어 둔 시각과 실제 실행 시각이 말없이 갈린다).
    """
    hour_text, _, minute_text = str(value or "").partition(":")
    hour, minute = int(hour_text), int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"시각 범위를 벗어났다: {value!r}")
    return (hour, minute)


def in_window(now: datetime, at: tuple[int, int], window_minutes: int) -> bool:
    """지금이 실행 창 안인가.

    Args:
        now: 현재 시각(KST).
        at: ``(시, 분)``.
        window_minutes: 창 길이(분).

    Returns:
        창 안이면 True.
    """
    target = now.replace(hour=at[0], minute=at[1], second=0, microsecond=0)
    return target <= now < target + timedelta(minutes=max(1, window_minutes))


def parse_backfill_from(value: Optional[str]) -> Optional[date]:
    """``--backfill-from`` 문자열을 날짜로(빈 값이면 None).

    Args:
        value: ``YYYY-MM-DD`` 또는 None.

    Returns:
        날짜 또는 None.

    Raises:
        ValueError: 형식 오류(조용히 무시하면 "백필했다"고 믿게 된다).
    """
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _sync_once(dry_run: bool, backfill_from: Optional[date]) -> dict:
    """단일 실행(호출측이 app_context 보유). 커밋은 서비스가 소유한다."""
    db = get_db()
    try:
        return run_settle_sync(
            db, NaverCommerceClient(), today=get_today_kst(),
            trigger="BACKFILL" if backfill_from else "SCHEDULE",
            backfill_from=backfill_from, dry_run=dry_run)
    except Exception:
        db.rollback()
        raise


def _print_result(result: dict, as_json: bool) -> None:
    """결과를 사람/기계 판독 형식으로 출력."""
    if as_json:
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        return
    stamp = datetime.now().strftime("%H:%M:%S")
    stats = result.get("stats") or {}
    scope = result.get("scope") or {}
    print(f"[{stamp}] naver settle sync: status={result.get('status')} "
          f"range={scope.get('from')}~{scope.get('to')} "
          f"calls={stats.get('calls')} rows={stats.get('rows')} "
          f"retro={len(stats.get('retro_changes') or [])} "
          f"dry_run={result.get('dry_run')} error={result.get('error')}", flush=True)


def _run_loop(args: argparse.Namespace) -> int:
    """앱 1회 부팅 후 tick 간격으로 깨어나 시각 창에서만 실행한다.

    실행 1회 실패가 루프를 죽이면 정산 동기화가 통째로 조용히 꺼진다 — 그래서 예외를
    삼키고 계속 돈다(사고는 로그로 남는다). 창 안에서 여러 번 깨어나도 파티션 통째 교체라
    결과가 같다.
    """
    at = parse_at(args.at)
    backfill_from = parse_backfill_from(args.backfill_from)
    tick = max(5, int(args.tick))
    print(f"[naver-settle-sync] started (at={args.at} window={args.window}m tick={tick}s)",
          flush=True)
    while True:
        try:
            if in_window(now_kst(), at, args.window):
                with app.app_context():
                    result = _sync_once(args.dry_run, backfill_from)
                _print_result(result, args.json)
        except Exception:
            print("[naver-settle-sync] run failed:", flush=True)
            traceback.print_exc()
        time.sleep(tick)


def run() -> int:
    """CLI 진입점.

    Returns:
        종료 코드. 0=성공, 1=실행은 됐으나 실패·중단(쿼터), 2=인자 오류.
    """
    args = _parse_args()
    try:
        backfill_from = parse_backfill_from(args.backfill_from)
    except ValueError as exc:
        print(f"[naver-settle-sync] --backfill-from 형식 오류: {exc}", flush=True)
        return 2
    if args.loop:
        return _run_loop(args)

    with app.app_context():
        result = _sync_once(args.dry_run, backfill_from)
    _print_result(result, args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(run())
