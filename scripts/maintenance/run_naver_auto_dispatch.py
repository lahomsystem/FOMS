"""네이버 발송처리 자동 실행 러너 (NAVER-AUTODISPATCH-01).

**WORKER 서비스에서만 돈다.** 네이버로 나가는 HTTP 는 호출 IP 한도(3=3) 때문에 워커 한
곳에서만 나가야 하고, 이 러너가 넣는 job 도 그 워커가 소비한다.

주기 배선은 수집 스윕·알림 escalation 과 **같은 구조**다 — FOMS 에는 인앱 스케줄러가 없고
새 인프라 의존성(rq-scheduler·외부 cron)은 만들지 않는다. ``--loop`` 는 앱을 1회만 부팅하고
짧은 간격으로 깨어나, **하루 한 번 정해진 시각 창에 들어왔을 때만** 실행한다.

시각 창을 쓰는 이유: 워커가 재시작하거나 루프가 밀리면 정확히 그 분에 못 깨어날 수 있다.
창(기본 10분) 안이면 실행하고, 하루 1회 계약은 서비스가 DB 상태로 지킨다 — 러너가 두 번
불러도 두 번 나가지 않는다.

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_naver_auto_dispatch.py --once --json
    python scripts/maintenance/run_naver_auto_dispatch.py --once --force --json
    python scripts/maintenance/run_naver_auto_dispatch.py --loop --at 16:50 --json
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import get_db  # noqa: E402
from foms.services.datetime_kst import now_kst  # noqa: E402
from foms.services.integrations.naver_commerce.auto_dispatch import (  # noqa: E402
    run_auto_dispatch,
)

#: --loop 이 깨어나는 간격(초). 시각 창 판정만 하므로 짧아도 비용이 없다.
DEFAULT_TICK_SECONDS = 60

#: 시각 창 길이(분). 워커 재시작·루프 밀림으로 정각을 놓쳐도 이 안이면 실행한다.
DEFAULT_WINDOW_MINUTES = 10

#: 기본 실행 시각(KST). 사용자 결정 2026-09-02.
DEFAULT_AT = "16:50"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dispatch today's measured Naver orders on a daily schedule.")
    parser.add_argument("--once", action="store_true",
                        help="1회만 판정·실행(기본 동작 — 명시용 플래그).")
    parser.add_argument("--force", action="store_true",
                        help="영업일·하루1회 규칙을 건너뛴다(기능 스위치는 못 넘는다).")
    parser.add_argument("--json", action="store_true", help="기계 판독용 JSON 요약 출력.")
    parser.add_argument("--loop", action="store_true",
                        help="장기 실행 루프: 앱 1회 부팅 후 시각 창을 지킨다(start.sh 배선용).")
    parser.add_argument("--at", default=os.environ.get("FOMS_NAVER_AUTO_DISPATCH_AT", DEFAULT_AT),
                        help=f"--loop 실행 시각 HH:MM (KST, 기본 {DEFAULT_AT}).")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_MINUTES,
                        help=f"시각 창 길이(분, 기본 {DEFAULT_WINDOW_MINUTES}).")
    parser.add_argument("--tick", type=int, default=DEFAULT_TICK_SECONDS,
                        help=f"--loop 이 깨어나는 간격(초, 기본 {DEFAULT_TICK_SECONDS}).")
    return parser.parse_args()


def parse_at(value: str) -> tuple[int, int]:
    """``HH:MM`` 을 ``(시, 분)`` 으로 — 형식이 틀리면 :class:`ValueError`.

    Args:
        value: ``"16:50"`` 형태.

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


def _dispatch_once(force: bool) -> dict:
    """단일 실행(호출측이 app_context 보유). 커밋은 서비스가 소유한다."""
    db = get_db()
    try:
        return run_auto_dispatch(db, force=force)
    except Exception:
        db.rollback()
        raise


def _print_result(result: dict, as_json: bool) -> None:
    """결과를 사람/기계 판독 형식으로 출력."""
    if as_json:
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] naver auto-dispatch: outcome={result.get('outcome')} "
          f"date={result.get('date')} queued={result.get('queued')} "
          f"blocked={result.get('blocked')} total={result.get('total')}", flush=True)


def _run_loop(args: argparse.Namespace) -> int:
    """앱 1회 부팅 후 tick 간격으로 깨어나 시각 창에서만 실행한다.

    실행 1회 실패가 루프를 죽이면 자동 발송이 통째로 조용히 꺼진다 — 그래서 예외를 삼키고
    계속 돈다(사고는 로그로 남는다). 하루 1회 계약은 서비스가 DB 로 지키므로 창 안에서
    여러 번 깨어나도 두 번 나가지 않는다.
    """
    at = parse_at(args.at)
    tick = max(5, int(args.tick))
    print(f"[naver-auto-dispatch] started (at={args.at} window={args.window}m tick={tick}s)",
          flush=True)
    while True:
        try:
            if in_window(now_kst(), at, args.window):
                with app.app_context():
                    result = _dispatch_once(args.force)
                # 창 안에서 매 tick 마다 "already_ran" 을 찍으면 로그가 그걸로 덮인다.
                if result.get("outcome") != "already_ran":
                    _print_result(result, args.json)
        except Exception:
            print("[naver-auto-dispatch] run failed:", flush=True)
            traceback.print_exc()
        time.sleep(tick)


def run() -> int:
    args = _parse_args()
    if args.loop:
        return _run_loop(args)

    with app.app_context():
        result = _dispatch_once(args.force)
    _print_result(result, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(run())
