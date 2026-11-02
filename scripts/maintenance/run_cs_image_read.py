"""AI 상담팀원 그림 미리 읽기 러너 — WORKER 감독자 자식 ``cs_image_read``(설계서 17.11 (b)).

한 차례는 :func:`foms.services.cs_agent.image_preread.run_preread_tick` 이다(스위치 · 따로 잠금 · 볼 상담 · 미리 읽을지 ·
읽기). 이 러너는 앱을 한 번 부팅하고 :data:`TICK_SECONDS` 마다 차례를 돌린다. 감독자는 env ``FOMS_CS_IMAGE_READ_ENABLED=1``
일 때만 띄운다(처음 끔 — 끈 동안 WORKER 메모리가 늘지 않는다). 실제 일은 관리 화면 '그림 읽기'(처음 끔)가 켜야 한다.

- **TERM/INT**: 멈춤 깃발만 세운다. 차례는 두뇌 전마다 깃발을 보고, 러너는 깃발 뒤엔 하트비트를 포함해 아무것도 쓰지 않고
  끝난다(원장 R4-4).
- **관측(OPS-HEARTBEAT-01)**: ``CS_IMAGE_READ`` 하트비트를 :data:`HEARTBEAT_SECONDS` 마다 — 그 사이 차례 수 · 읽은 묶음 ·
  실패 수와 마지막 결과 코드뿐(상담 id · 손님 정보 없음).
- **Sentry**: 이 프로세스의 오류 이벤트에서 스택 지역 변수를 뺀다 — 그림 바이트 · 상담 글이 따라가지 않게(D89 · R5-2).

사용 예 (PowerShell 5.x)::

    python scripts/maintenance/run_cs_image_read.py --once --json
    python scripts/maintenance/run_cs_image_read.py --loop --json
"""
import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
)

from app import app  # noqa: E402
from db import db_session, engine  # noqa: E402
from foms.services.cs_agent.image_preread import TICK_SECONDS, PrereadMemory, run_preread_tick  # noqa: E402
from foms.services.cs_agent.loop import StopFlag  # noqa: E402
from foms.services.cs_agent.runner_support import (  # noqa: E402
    error_summary,
    install_sentry_privacy,
    install_signal_handlers,
)
from foms.services.loop_heartbeat import (  # noqa: E402
    capture_exception,
    emit_heartbeat,
    init_sentry_once,
    safe_metadata,
)
from foms.services.sidefx_worker import WORKER_KIND_CS_IMAGE_READ  # noqa: E402

_LOGGER = logging.getLogger("cs_image_read")

#: 이 루프의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_CS_IMAGE_READ
HEARTBEAT_SECONDS = 30
_COUNTED = ("read", "failed")


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """CLI 인자."""
    parser = argparse.ArgumentParser(description="AI CS agent image pre-read path — 2 second ticks, separate lock.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="한 차례만 돌고 끝낸다(기본 동작).")
    mode.add_argument("--loop", action="store_true", help="장기 실행 루프(감독자 배선용).")
    parser.add_argument("--json", action="store_true", help="일이 있었던 차례마다 JSON 요약 한 줄.")
    return parser.parse_args(argv)


def _tick(stop: StopFlag, memory: PrereadMemory) -> Optional[dict]:
    """차례 하나(앱 컨텍스트 안) — 실패는 기록하고 삼킨다(한 번 실패가 루프를 죽이면 미리 읽기가 조용히 꺼진다)."""
    try:
        with app.app_context():
            try:
                return run_preread_tick(db_session, memory=memory, stop=stop).summary()
            except Exception:
                db_session.rollback()
                raise
            finally:
                db_session.remove()
    except Exception as exc:
        print(f"[cs-image-read] tick failed: {error_summary(exc)}", flush=True)  # 예외 글 없음(R14-8)
        capture_exception()
        return None


def _heartbeat_metadata(totals: Optional[dict], interval: int = HEARTBEAT_SECONDS) -> dict:
    """하트비트에 실을 합계 — 정해진 칸만(상담 id · 손님 정보 없음)."""
    source = totals or {}
    return {"interval_seconds": int(interval or 0), "outcome": str(source.get("outcome") or "tick_failed"),
            "ticks": int(source.get("ticks") or 0), "read": int(source.get("read") or 0),
            "failed": int(source.get("failed") or 0)}


def _add(totals: dict, summary: Optional[dict]) -> None:
    """차례 요약을 하트비트 합계에 더한다(숫자만)."""
    summary = summary or {}
    totals["ticks"] = int(totals.get("ticks") or 0) + 1
    totals["outcome"] = str(summary.get("outcome") or "tick_failed")
    for key in _COUNTED:
        totals[key] = int(totals.get(key) or 0) + int(summary.get(key) or 0)


def _run_loop(as_json: bool, stop: StopFlag) -> int:
    """앱 1회 부팅 후 차례를 돈다. TERM 깃발이 서면 하트비트도 쓰지 않고 0 으로 끝낸다."""
    memory, totals, last_beat = PrereadMemory(), {}, None
    print(f"[cs-image-read] started (tick={TICK_SECONDS}s heartbeat={HEARTBEAT_SECONDS}s)", flush=True)
    while not stop.is_set():
        started = time.monotonic()
        summary = _tick(stop, memory)
        if stop.is_set():
            break
        _add(totals, summary)
        if as_json and summary and summary.get("chats"):
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        if last_beat is None or time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
            metadata = safe_metadata(lambda: _heartbeat_metadata(totals), _heartbeat_metadata(None),
                                     logger=_LOGGER, label="cs-image-read")
            emit_heartbeat(engine, HEARTBEAT_WORKER_KIND, metadata=metadata, logger=_LOGGER)
            totals, last_beat = {}, time.monotonic()
        stop.sleep(max(0.5, TICK_SECONDS - (time.monotonic() - started)))
    print("[cs-image-read] stopped (TERM)", flush=True)
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
    summary = _tick(stop, PrereadMemory())
    print(json.dumps(summary or {"outcome": "tick_failed"}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
