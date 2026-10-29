"""AI 상담팀원 감시 루프 러너 — WORKER 감독자 자식 ``cs_loop``(플랜 C1-3, 설계서 3.2).

한 바퀴는 :func:`foms.services.cs_agent.loop.run_pass` 다(바로 끄기 · 대표 잠금 · 수신 기록 · 채널톡 보정 · 상태 · 경보 ·
아침 보고). 이 러너는 앱을 한 번 부팅하고 ``--interval``(기본 900초)마다 바퀴를 돌리고, 아침 보고 시각(KST 8시)이
그 사이에 오면 그 시각에 맞춰 깬다. 대표가 아니어서 건너뛴 바퀴는 60초 뒤 다시 본다(재배포 겹침은 몇 초~25초).

- **TERM/INT**: 멈춤 깃발만 세운다. 바퀴는 일을 집기 전 · 쓰기 전마다 깃발을 보고 멈추고, 러너는 깃발 뒤엔 하트비트를
  포함해 아무것도 쓰지 않고 끝난다(원장 R4-4). 자는 동안에도 1초 안에 깨어 끝난다 — 감독자 정지 유예(25초) 안이다.
- **관측(OPS-HEARTBEAT-01)**: 바퀴마다 ``CS_LOOP`` 하트비트를 남긴다 — 끈 바퀴 · 대표 아닌 바퀴도 남긴다("죽었다" 와
  "지금은 꺼 두었다" 를 가른다). metadata 는 집계 수와 마지막 정상 바퀴 시각뿐(상담 id · 손님 정보 없음).
- **수신 누락 경보**: 채널톡 웹훅이 오는 운영에서만 켠다 — 환경 판정은 저장소에 이미 있는
  ``foms.platform.sentry_setup.resolve_environment``(``FOMS_ENV`` → Railway 프로젝트 이름)를 그대로 쓴다.
- **Sentry**: 이 프로세스의 오류 이벤트에서 스택 지역 변수를 뺀다 — 수신 기록 원본(손님 글)이 따라가지 않게(원장 R5-2).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_cs_loop.py --once --json
    python scripts/maintenance/run_cs_loop.py --loop --interval 900 --json
    python scripts/maintenance/run_cs_loop.py --switch off
    python scripts/maintenance/run_cs_loop.py --switch on
"""
import argparse
import datetime
import json
import logging
import os
import signal
import sys
import traceback
from typing import Any, Optional

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app import app  # noqa: E402
from db import db_session, engine  # noqa: E402
from foms.platform.sentry_setup import resolve_environment  # noqa: E402
from foms.services.cs_agent.brain_spend import HEARTBEAT_CAP_KEY, heartbeat_cap_value  # noqa: E402
from foms.services.cs_agent.loop import (  # noqa: E402
    DEFAULT_INTERVAL_SECONDS,
    OUTCOME_NOT_LEADER,
    OUTCOME_OK,
    LoopConfig,
    StopFlag,
    run_pass,
    set_switch,
    watch_missing_inbound_for,
)
from foms.services.cs_agent.report import (  # noqa: E402
    HEARTBEAT_LAST_SUCCESS_KEY,
    read_last_success,
    seconds_until_report,
)
from foms.services.datetime_kst import now_kst  # noqa: E402
from foms.services.loop_heartbeat import (  # noqa: E402
    capture_exception,
    emit_heartbeat,
    init_sentry_once,
    safe_metadata,
)
from foms.services.sidefx_worker import WORKER_KIND_CS_LOOP  # noqa: E402

_LOGGER = logging.getLogger("cs_loop")

#: 이 루프의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_CS_LOOP

MIN_INTERVAL_SECONDS = 60
#: 대표가 아니어서 건너뛴 바퀴를 다시 볼 때까지(초) — 15분을 다 기다리지 않는다.
NOT_LEADER_RETRY_SECONDS = 60
#: 아침 보고 시각 바로 뒤에 깨도록 더하는 여유(초).
REPORT_WAKE_MARGIN_SECONDS = 5


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(
        description="AI CS agent watch loop — read-only Channel Talk, in-app morning report and alerts.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="한 바퀴만 돌고 끝낸다(기본 동작).")
    mode.add_argument("--loop", action="store_true", help="장기 실행 루프(감독자 배선용).")
    mode.add_argument("--switch", choices=("on", "off"),
                      help="바로 끄기 값(SystemSetting)을 쓰고 끝낸다 — off 면 다음 바퀴부터 일 0.")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
                        help=f"--loop 바퀴 간격(초, 기본 {DEFAULT_INTERVAL_SECONDS}, 최소 {MIN_INTERVAL_SECONDS}).")
    parser.add_argument("--json", action="store_true", help="바퀴마다 JSON 요약 한 줄.")
    return parser.parse_args(argv)


def loop_config() -> LoopConfig:
    """실행 환경에서 바퀴 설정을 정한다 — 수신 누락 경보는 웹훅이 오는 운영에서만 켠다."""
    return LoopConfig(watch_missing_inbound=watch_missing_inbound_for(resolve_environment()))


def drop_frame_locals(event: Any, _hint: Any = None) -> Any:
    """Sentry 이벤트에서 스택 프레임 지역 변수(``vars``)를 뺀다 — 수신 기록 원본(손님 글 · 번호)을 든 지역 변수가
    오류와 함께 Sentry 로 가지 않게(sentry-sdk 는 지역 변수를 기본으로 싣는다, 원장 R5-2). 꼴이 달라도 던지지 않는다."""
    if not isinstance(event, dict):
        return event
    for section in ("exception", "threads"):
        values = event.get(section, {}).get("values") if isinstance(event.get(section), dict) else None
        for entry in values if isinstance(values, list) else ():
            trace = entry.get("stacktrace") if isinstance(entry, dict) else None
            frames = trace.get("frames") if isinstance(trace, dict) else None
            for frame in frames if isinstance(frames, list) else ():
                if isinstance(frame, dict):
                    frame.pop("vars", None)
    return event


def install_sentry_privacy() -> None:
    """이 프로세스의 Sentry 이벤트 모두에 :func:`drop_frame_locals` 를 건다(sentry-sdk 가 없으면 지나간다)."""
    try:
        from sentry_sdk.scope import add_global_event_processor
    except ImportError:
        return
    add_global_event_processor(drop_frame_locals)


def install_signal_handlers(stop: StopFlag) -> None:
    """TERM/INT 에 멈춤 깃발만 세운다. 처리기를 못 달면 경고만 남긴다(바퀴는 그래도 돈다)."""
    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, stop.set)
        except (ValueError, OSError, RuntimeError) as exc:
            _LOGGER.warning("signal %s handler not installed: %s", name, exc)


def _pass_once(stop: StopFlag, config: LoopConfig) -> dict:
    """한 바퀴(호출측이 app_context 보유) — JSON 요약을 돌려준다. 실패하면 롤백하고 예외를 올린다."""
    try:
        return run_pass(db_session, config=config, stop=stop).summary()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.remove()


def _heartbeat_metadata(result: Optional[dict], interval: int = 0,
                        last_success: Optional[str] = None) -> dict:
    """하트비트에 실을 집계값. 상담 id · 손님 정보(글 · 이름 · 번호)는 싣지 않는다.

    이 프로세스(WORKER)의 env 하루 상한도 싣는다 — 관리 화면(web)은 env 를 읽지 않고 이 값을 천장으로 보인다.
    """
    summary = result or {}
    return {
        "interval_seconds": int(interval or 0),
        "outcome": str(summary.get("outcome") or "pass_failed"),
        "ingested": int(summary.get("ingested") or 0),
        "reconciled": int(summary.get("reconciled") or 0),
        "needs_reply": int(summary.get("needs_reply") or 0),
        "alerts": int(summary.get("alerts") or 0),
        "report_sent": bool(summary.get("report_sent")),
        HEARTBEAT_LAST_SUCCESS_KEY: last_success,
        HEARTBEAT_CAP_KEY: heartbeat_cap_value(),
    }


def _initial_last_success() -> Optional[str]:
    """재시작 전 컨테이너가 하트비트에 남긴 마지막 정상 바퀴 시각(UTC ISO). 못 읽으면 ``None``(경고)."""
    try:
        with app.app_context():
            stamp = read_last_success(db_session)
    except SQLAlchemyError:
        _LOGGER.warning("[cs-loop] last success read failed", exc_info=True)
        return None
    finally:
        db_session.remove()
    return stamp.replace(tzinfo=None).isoformat(timespec="seconds") if stamp else None


def next_sleep_seconds(interval: int, outcome: Optional[str], now: datetime.datetime,
                       started: Optional[datetime.datetime] = None) -> float:
    """다음 바퀴까지 잘 초 — 간격, 대표가 아니었으면 짧게, 아침 보고 시각이 먼저 오면 그 시각까지.

    보고 시각은 바퀴를 **시작한** 때(``started``)로 잰다 — 7시 59분에 시작해 8시를 넘겨 끝난 바퀴는 보고를 내지
    않았으니 곧 다음 바퀴를 돈다(끝난 때로 재면 다음 날 8시를 가리켜 보고가 한 간격 밀린다, 원장 R5-4).
    """
    base = min(interval, NOT_LEADER_RETRY_SECONDS) if outcome == OUTCOME_NOT_LEADER else interval
    started = started or now
    until = seconds_until_report(started) - (now - started).total_seconds()
    return max(1.0, min(float(base), until + REPORT_WAKE_MARGIN_SECONDS))


def _tick(stop: StopFlag, config: LoopConfig, as_json: bool) -> Optional[dict]:
    """바퀴 하나 — 실패는 기록하고 삼킨다(한 번 실패가 루프를 죽이면 감시가 조용히 꺼진다)."""
    try:
        with app.app_context():
            summary = _pass_once(stop, config)
    except Exception:
        print("[cs-loop] pass failed:", flush=True)
        traceback.print_exc()
        capture_exception()
        return None
    if as_json or summary.get("alerts") or summary.get("report_sent"):
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def _run_loop(interval: int, as_json: bool, stop: StopFlag) -> int:
    """앱 1회 부팅 후 바퀴를 돈다. TERM 깃발이 서면 하트비트도 쓰지 않고 0 으로 끝낸다."""
    interval = max(MIN_INTERVAL_SECONDS, int(interval))
    config = loop_config()
    last_success = _initial_last_success()
    print(f"[cs-loop] started (interval={interval}s missing_inbound_watch={config.watch_missing_inbound})",
          flush=True)
    while not stop.is_set():
        started = now_kst()
        summary = _tick(stop, config, as_json)
        if stop.is_set():
            break  # TERM 뒤엔 쓰기를 시작하지 않는다(R4-4) — 하트비트도
        if summary and summary.get("outcome") == OUTCOME_OK:
            last_success = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).isoformat(
                timespec="seconds")
        metadata = safe_metadata(
            lambda: _heartbeat_metadata(summary, interval, last_success),
            _heartbeat_metadata(None, interval, last_success), logger=_LOGGER, label="cs-loop")
        emit_heartbeat(engine, HEARTBEAT_WORKER_KIND, metadata=metadata, logger=_LOGGER)
        stop.sleep(next_sleep_seconds(interval, (summary or {}).get("outcome"), now_kst(), started))
    print("[cs-loop] stopped (TERM)", flush=True)
    return 0


def _write_switch(value: str) -> dict[str, Any]:
    """바로 끄기 값을 쓴다(관리자 스크립트 한 줄)."""
    with app.app_context():
        try:
            return set_switch(db_session, on=value == "on")
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.remove()


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점 — 이 프로세스의 Sentry 를 먼저 붙이고 바로 끄기 · 1회 · 루프로 간다.

    Returns:
        프로세스 exit code(0=정상).
    """
    init_sentry_once(_LOGGER)
    install_sentry_privacy()
    args = _parse_args(argv)
    if args.switch:
        print(json.dumps({"switch": _write_switch(args.switch)}, ensure_ascii=False), flush=True)
        return 0
    stop = StopFlag()
    install_signal_handlers(stop)
    if args.loop:
        return _run_loop(args.interval, args.json, stop)
    with app.app_context():
        summary = _pass_once(stop, loop_config())
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
