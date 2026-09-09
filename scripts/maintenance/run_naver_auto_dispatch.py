"""네이버 발송처리 자동 실행 러너 (NAVER-AUTODISPATCH-01).

**WORKER 서비스에서만 돈다.** 네이버로 나가는 HTTP 는 호출 IP 한도(3=3) 때문에 워커 한
곳에서만 나가야 하고, 이 러너가 넣는 job 도 그 워커가 소비한다.

주기 배선은 수집 스윕·알림 escalation 과 **같은 구조**다 — FOMS 에는 인앱 스케줄러가 없고
새 인프라 의존성(rq-scheduler·외부 cron)은 만들지 않는다. ``--loop`` 는 앱을 1회만 부팅하고
짧은 간격으로 깨어나, **하루 한 번 정해진 시각 창에 들어왔을 때만** 실행한다.

시각 창을 쓰는 이유: 워커가 재시작하거나 루프가 밀리면 정확히 그 분에 못 깨어날 수 있다.
창(기본 10분) 안이면 실행하고, 하루 1회 계약은 서비스가 DB 상태로 지킨다 — 러너가 두 번
불러도 두 번 나가지 않는다.

관측(OPS-HEARTBEAT-01): tick 마다 ``side_effect_worker_heartbeats`` 의
``NAVER_AUTO_DISPATCH`` 행을 갱신한다. **창 밖이라 아무것도 안 한 tick 도 갱신한다** —
그래야 "루프가 죽었다" 와 "지금은 일할 시각이 아니다" 가 갈린다. Sentry 는 진입점에서
공용 게이트 :func:`foms.services.loop_heartbeat.init_sentry_once` 로 붙인다 — 이미 붙어
있으면(상단 ``from app import app`` 경로) 다시 init 하지 않는다(앞 클라이언트를 갈아치우면
그 전송 스레드에 남아 있던 이벤트가 유실된다).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_naver_auto_dispatch.py --once --json
    python scripts/maintenance/run_naver_auto_dispatch.py --once --force --json
    python scripts/maintenance/run_naver_auto_dispatch.py --loop --at 16:50 --json
"""
import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

# ``app`` import 는 ``app.py`` -> ``build_app`` -> ``init_sentry`` 를 이미 태운다
# (foms/platform/app_factory.py). 그래서 이 러너는 Sentry 를 다시 초기화하지 않는다 —
# ``sentry_sdk.init`` 을 두 번 부르면 클라이언트가 갈리고 앞 클라이언트의 전송 스레드가
# 남는다. 이 프로세스에 없던 것은 init 이 아니라 **잡은 예외를 올려 보내는 배선**이라,
# 그 자리를 :func:`_capture_to_sentry` 로 채운다.
from app import app  # noqa: E402
from db import engine, get_db  # noqa: E402
from foms.services.datetime_kst import now_kst  # noqa: E402
from foms.services.integrations.naver_commerce.auto_dispatch import (  # noqa: E402
    run_auto_dispatch,
)
from foms.services.loop_heartbeat import capture_exception, init_sentry_once  # noqa: E402
from foms.services.sidefx_worker import (  # noqa: E402
    WORKER_KIND_NAVER_AUTO_DISPATCH,
    upsert_heartbeat,
)

_LOGGER = logging.getLogger("naver_auto_dispatch")

#: --loop 이 깨어나는 간격(초). 시각 창 판정만 하므로 짧아도 비용이 없다.
DEFAULT_TICK_SECONDS = 60

#: 시각 창 길이(분). 워커 재시작·루프 밀림으로 정각을 놓쳐도 이 안이면 실행한다.
DEFAULT_WINDOW_MINUTES = 10

#: 기본 실행 시각(KST). 사용자 결정 2026-09-02.
DEFAULT_AT = "16:50"

#: 이 루프의 heartbeat PK 값(``side_effect_worker_heartbeats.worker_kind``).
#: 정본은 :data:`foms.services.sidefx_worker.WORKER_KIND_SPECS` 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_NAVER_AUTO_DISPATCH


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


def _heartbeat_metadata(*, in_window_now: bool, result: Optional[dict],
                        tick: int = 0) -> dict:
    """하트비트에 실을 집계값을 만든다.

    Args:
        in_window_now: 이번 tick 이 실행 창 안이었는가.
        result: 실행했으면 :func:`run_auto_dispatch` 결과, 아니면 ``None``.

    Returns:
        ``{"in_window", "outcome", "queued", "blocked", "total"}``. **고객 정보(이름·전화·
        주소)는 절대 넣지 않는다** — 이 표는 운영 감시용이고 집계 수치면 충분하다.
    """
    payload = result or {}
    return {
        # 판정부가 예산을 잡는 근거(:meth:`ReadinessThresholds.heartbeat_age_limit`).
        # 간격이 env 로 열려도 감시가 따라온다.
        "interval_seconds": int(tick or 0),
        "in_window": bool(in_window_now),
        "outcome": payload.get("outcome") or None,
        "queued": int(payload.get("queued") or 0),
        "blocked": int(payload.get("blocked") or 0),
        "total": int(payload.get("total") or 0),
    }


def _emit_heartbeat(*, in_window_now: bool, result: Optional[dict],
                    tick: int = 0) -> None:
    """이번 tick 의 생존 신호를 ``side_effect_worker_heartbeats`` 에 남긴다.

    **일을 안 한 tick 에서도 갱신한다.** 창 밖 tick 이 건너뛰면 하루 23시간 50분 동안
    하트비트가 낡아 보여 감시가 무의미해진다 — "루프가 죽었다" 와 "지금은 일할 시각이
    아니다" 를 가르는 것이 이 배선의 목적이다(2026-02 워커 offline, 2026-08-31 SIDEFX
    미배포를 둘 다 사람이 화면에서 먼저 발견했다).

    하트비트 실패는 **본 작업을 막지 않는다**: 되돌릴 수 없는 자동 발송이 관측 배선 때문에
    멈추는 것이 더 나쁜 실패다. 대신 삼키지도 않는다 — 경고 로그 + Sentry 이벤트로 남긴다.

    Args:
        in_window_now: 이번 tick 이 실행 창 안이었는가.
        result: 실행했으면 :func:`run_auto_dispatch` 결과, 아니면 ``None``.

    Returns:
        None.
    """
    try:
        upsert_heartbeat(
            engine, HEARTBEAT_WORKER_KIND,
            metadata=_heartbeat_metadata(in_window_now=in_window_now, result=result,
                                         tick=tick),
        )
    except Exception:
        _LOGGER.warning("heartbeat upsert failed worker_kind=%s",
                        HEARTBEAT_WORKER_KIND, exc_info=True)
        capture_exception()


def _run_tick(args: argparse.Namespace, at: tuple[int, int]) -> None:
    """루프 1회분 — 창 안이면 발송하고, 창 밖이어도 하트비트를 남긴다.

    Args:
        args: CLI 인자(``force``·``window``·``json`` 을 읽는다).
        at: ``(시, 분)`` 실행 시각.

    Returns:
        None. 발송 실패는 로그·Sentry 로 남기고 삼킨다 — 1회 실패가 루프를 죽이면 자동
        발송이 통째로 조용히 꺼진다. 실패한 tick 도 하트비트는 남긴다(루프는 살아 있다).
    """
    in_window_now = False
    result: Optional[dict] = None
    try:
        in_window_now = in_window(now_kst(), at, args.window)
        if in_window_now:
            with app.app_context():
                result = _dispatch_once(args.force)
            # 창 안에서 매 tick 마다 "already_ran" 을 찍으면 로그가 그걸로 덮인다.
            if result.get("outcome") != "already_ran":
                _print_result(result, args.json)
    except Exception:
        print("[naver-auto-dispatch] run failed:", flush=True)
        traceback.print_exc()
        capture_exception()
    _emit_heartbeat(in_window_now=in_window_now, result=result,
                    tick=max(5, int(getattr(args, "tick", 0) or 0)))


def _run_loop(args: argparse.Namespace) -> int:
    """앱 1회 부팅 후 tick 간격으로 깨어나 시각 창에서만 실행한다.

    실행 1회 실패가 루프를 죽이면 자동 발송이 통째로 조용히 꺼진다 — 그래서 예외를 삼키고
    계속 돈다(사고는 로그로 남는다). 하루 1회 계약은 서비스가 DB 로 지키므로 창 안에서
    여러 번 깨어나도 두 번 나가지 않는다.

    :func:`_run_tick` 이 이미 자기 실패를 삼키지만 여기서 한 겹 더 막는다. 이 루프의 계약은
    "무슨 일이 있어도 죽지 않는다" 이고, 그 계약을 tick 구현에 떠맡기면 tick 을 고칠 때
    조용히 깨진다. ``time.sleep`` 은 이 방어 밖에 둔다 — 인터럽트로 루프를 끝낼 수 있어야 한다.
    """
    at = parse_at(args.at)
    tick = max(5, int(args.tick))
    print(f"[naver-auto-dispatch] started (at={args.at} window={args.window}m tick={tick}s)",
          flush=True)
    while True:
        try:
            _run_tick(args, at)
        except Exception:
            print("[naver-auto-dispatch] tick failed:", flush=True)
            traceback.print_exc()
            capture_exception()
        time.sleep(tick)


def run() -> int:
    """CLI 진입점 — 이 프로세스의 Sentry 를 먼저 붙이고 1회 실행 또는 루프로 간다.

    Returns:
        프로세스 exit code(0=정상).
    """
    init_sentry_once(_LOGGER)
    args = _parse_args()
    if args.loop:
        return _run_loop(args)

    with app.app_context():
        result = _dispatch_once(args.force)
    _print_result(result, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(run())
