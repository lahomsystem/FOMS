"""AI 상담팀원 빠른 길 러너 — WORKER 감독자 자식 ``cs_realtime``(플랜 C10-1, 설계서 17.3).

한 차례는 :func:`foms.services.cs_agent.realtime.run_tick` 이다(스위치 · 따로 잠금 · 수신 기록 · 모아 받기 · 초안). 이 러너는 앱을
한 번 부팅하고 :data:`TICK_SECONDS` 마다 차례를 돌린다. 대표가 아니어도 다음 차례(5초)에 다시 잡아 본다 — 15분 바퀴 러너처럼
60초를 기다리지 않는다(원장 R10-2). 15분 바퀴(``run_cs_loop.py``)와 같은 env(``FOMS_CS_LOOP_ENABLED=1``)일 때 감독자가 띄운다.

- **TERM/INT**: 멈춤 깃발만 세운다. 차례는 일을 집기 전 · 쓰기 전 · 두뇌 전마다 깃발을 보고 멈추고, 러너는 깃발 뒤엔 하트비트를
  포함해 아무것도 쓰지 않고 끝난다(원장 R4-4). 자는 동안에도 1초 안에 깨어 끝난다.
- **관측(OPS-HEARTBEAT-01)**: ``CS_REALTIME`` 하트비트를 :data:`HEARTBEAT_SECONDS` 마다 남긴다(차례마다 쓰면 DB 쓰기가 분당 12번)
  — 그 사이 차례 수 · 넣은 글 · 집은 상담 · 두뇌 수의 합과 마지막 차례 결과 코드뿐(상담 id · 손님 정보 없음). 꺼 둔 차례도
  남긴다("죽었다" 와 "지금은 꺼 두었다" 를 가른다).
- **Sentry**: 이 프로세스의 오류 이벤트에서 스택 지역 변수를 뺀다 — 상담 글 원문이 따라가지 않게(원장 R5-2).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_cs_realtime.py --once --json
    python scripts/maintenance/run_cs_realtime.py --loop --json
"""
import argparse
import json
import logging
import os
import sys
import time
import traceback
from typing import Optional

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import db_session, engine  # noqa: E402
from foms.services.cs_agent.loop import StopFlag  # noqa: E402
from foms.services.cs_agent.realtime import TICK_SECONDS, TickMemory, run_tick  # noqa: E402
from foms.services.cs_agent.runner_support import (  # noqa: E402
    install_sentry_privacy,
    install_signal_handlers,
)
from foms.services.loop_heartbeat import (  # noqa: E402
    capture_exception,
    emit_heartbeat,
    init_sentry_once,
    safe_metadata,
)
from foms.services.sidefx_worker import WORKER_KIND_CS_REALTIME  # noqa: E402

_LOGGER = logging.getLogger("cs_realtime")

#: 이 루프의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_CS_REALTIME
#: 하트비트 간격(초) — metadata 의 ``interval_seconds`` 로 신고한다(등록부 예산은 그 3배와 300 가운데 큰 쪽).
HEARTBEAT_SECONDS = 30
#: 하트비트에 합해 싣는 차례 숫자(상담 id · 글 없음).
_COUNTED = ("ingested", "picked")


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(
        description="AI CS agent realtime path — 5 second ticks, separate lock, drafts after the quiet wait.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="한 차례만 돌고 끝낸다(기본 동작).")
    mode.add_argument("--loop", action="store_true", help="장기 실행 루프(감독자 배선용).")
    parser.add_argument("--json", action="store_true", help="일이 있었던 차례마다 JSON 요약 한 줄.")
    return parser.parse_args(argv)


def _tick(stop: StopFlag, memory: TickMemory) -> Optional[dict]:
    """차례 하나(앱 컨텍스트 안) — 실패는 기록하고 삼킨다(한 번 실패가 루프를 죽이면 빠른 길이 조용히 꺼진다)."""
    try:
        with app.app_context():
            try:
                return run_tick(db_session, memory=memory, stop=stop).summary()
            except Exception:
                db_session.rollback()
                raise
            finally:
                db_session.remove()
    except Exception:
        print("[cs-realtime] tick failed:", flush=True)
        traceback.print_exc()
        capture_exception()
        return None


def _add(totals: dict, summary: Optional[dict]) -> None:
    """차례 요약을 하트비트 합계에 더한다(숫자만)."""
    summary = summary or {}
    totals["ticks"] = int(totals.get("ticks") or 0) + 1
    totals["outcome"] = str(summary.get("outcome") or "tick_failed")
    for key in _COUNTED:
        totals[key] = int(totals.get(key) or 0) + int(summary.get(key) or 0)
    drafting = summary.get("drafting") if isinstance(summary.get("drafting"), dict) else {}
    totals["brain_calls"] = int(totals.get("brain_calls") or 0) + int(drafting.get("brain_calls") or 0)


def _heartbeat_metadata(totals: Optional[dict], interval: int = HEARTBEAT_SECONDS) -> dict:
    """하트비트에 실을 합계. 상담 id · 손님 정보(글 · 이름 · 번호)는 싣지 않는다 — 정해진 칸만 꺼낸다."""
    source = totals or {}
    return {
        "interval_seconds": int(interval or 0),
        "outcome": str(source.get("outcome") or "tick_failed"),
        "ticks": int(source.get("ticks") or 0),
        "ingested": int(source.get("ingested") or 0),
        "picked": int(source.get("picked") or 0),
        "brain_calls": int(source.get("brain_calls") or 0),
    }


def _worth_printing(summary: Optional[dict]) -> bool:
    """일이 있었던 차례인가(꺼 둔 차례 · 빈 차례는 줄을 찍지 않는다 — 5초마다 로그가 쌓인다)."""
    if not summary:
        return False
    return bool(summary.get("ingested") or summary.get("picked") or summary.get("superseded")
                or summary.get("staff_replied") or summary.get("expired"))


def _run_loop(as_json: bool, stop: StopFlag) -> int:
    """앱 1회 부팅 후 차례를 돈다. TERM 깃발이 서면 하트비트도 쓰지 않고 0 으로 끝낸다."""
    memory = TickMemory()
    totals: dict = {}
    last_beat: Optional[float] = None
    print(f"[cs-realtime] started (tick={TICK_SECONDS}s heartbeat={HEARTBEAT_SECONDS}s)", flush=True)
    while not stop.is_set():
        started = time.monotonic()
        summary = _tick(stop, memory)
        if stop.is_set():
            break  # TERM 뒤엔 쓰기를 시작하지 않는다(R4-4) — 하트비트도
        _add(totals, summary)
        if as_json and _worth_printing(summary):
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        if last_beat is None or time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
            metadata = safe_metadata(lambda: _heartbeat_metadata(totals), _heartbeat_metadata(None),
                                     logger=_LOGGER, label="cs-realtime")
            emit_heartbeat(engine, HEARTBEAT_WORKER_KIND, metadata=metadata, logger=_LOGGER)
            totals, last_beat = {}, time.monotonic()
        stop.sleep(max(0.5, TICK_SECONDS - (time.monotonic() - started)))
    print("[cs-realtime] stopped (TERM)", flush=True)
    return 0


def run(argv: Optional[list] = None) -> int:
    """CLI 진입점 — 이 프로세스의 Sentry 를 먼저 붙이고 1회 · 루프로 간다.

    Returns:
        프로세스 exit code(0=정상).
    """
    init_sentry_once(_LOGGER)
    install_sentry_privacy()
    args = _parse_args(argv)
    stop = StopFlag()
    install_signal_handlers(stop.set, _LOGGER)
    if args.loop:
        return _run_loop(args.json, stop)
    summary = _tick(stop, TickMemory())
    print(json.dumps(summary or {"outcome": "tick_failed"}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
