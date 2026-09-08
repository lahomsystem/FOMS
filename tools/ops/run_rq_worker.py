"""rq worker 를 DB 하트비트와 함께 띄운다 (OPS-HEARTBEAT-01, 후속 F-6).

``start.sh`` 는 워커 컨테이너의 마지막 줄에서 ``exec rq worker`` 로 자기를 대체해 왔다.
그 프로세스는 **자기 생존을 어디에도 남기지 않았다** — Redis 쪽 rq 하트비트는 rq 대시보드
전용이고, FOMS 의 감시 표(``side_effect_worker_heartbeats``)에는 아무 행도 없었다. 큐 소비가
멎어도(2026-02 워커 offline) 표만 봐서는 알 수 없었다.

이 러너가 하는 일은 하나다: :class:`rq.Worker` 의 ``heartbeat()` 를 감싸 같은 자리에서
``RQ_WORKER`` 행도 갱신한다. rq 가 자기 TTL 을 연장하는 그 지점이 곧 "루프가 돌고 있다" 는
뜻이라, 별도 스레드로 심장을 따로 뛰게 하는 것보다 정직하다(스레드는 rq 루프가 멎어도
계속 뛴다).

놀고 있는 워커의 ``heartbeat()`` 주기는 ``worker_ttl - 15`` = 405초(rq 기본)라, 판정 예산은
등록부에서 900초로 잡혀 있다(:data:`foms.services.sidefx_worker.WORKER_KIND_SPECS`).

사용::

    python tools/ops/run_rq_worker.py --url "$REDIS_URL" --queues default
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redis import Redis  # noqa: E402
from rq import Queue, Worker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.loop_heartbeat import emit_heartbeat  # noqa: E402
from foms.services.sidefx_worker import WORKER_KIND_RQ_WORKER  # noqa: E402

_LOGGER = logging.getLogger("run_rq_worker")

#: 이 프로세스의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_RQ_WORKER

#: DB 하트비트 최소 간격(초). rq 는 잡 하나마다도 ``heartbeat()`` 를 부르므로, 바쁜 워커가
#: 잡마다 DB 를 때리지 않게 여기서 조인다. 놀 때의 주기(405초)보다 훨씬 짧아 무해하다.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60


class HeartbeatWorkerMixin:
    """rq 하트비트 자리에서 FOMS 감시 표도 갱신하는 mixin.

    rq 와 무관하게 단독으로 시험할 수 있도록 mixin 으로 뗐다 — Redis 없이도
    :meth:`maybe_emit_db_heartbeat` 만 불러 조임 규칙을 검사할 수 있다.
    """

    #: 하위 클래스/인스턴스가 덮어쓰는 최소 간격(초).
    db_heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS

    #: 마지막으로 DB 에 쓴 시각(UTC naive). 아직 안 썼으면 None.
    _last_db_heartbeat_at: Optional[datetime.datetime] = None

    def db_heartbeat_metadata(self) -> dict:
        """하트비트에 실을 집계값(운영 감시용 수치만).

        Returns:
            ``{"queues", "successful", "failed", "state"}``. 잡 인자·고객 정보는 넣지 않는다.
        """
        state = getattr(self, "_state", "") or ""
        return {
            # 판정부가 예산을 잡는 근거. rq 는 놀 때 이 주기로만 heartbeat 를 부른다.
            "interval_seconds": int(getattr(self, "dequeue_timeout", 0) or 0),
            "queues": ",".join(getattr(self, "queue_names", lambda: [])()),
            "successful": int(getattr(self, "successful_job_count", 0) or 0),
            "failed": int(getattr(self, "failed_job_count", 0) or 0),
            "state": str(getattr(state, "value", state)),
        }

    def maybe_emit_db_heartbeat(self, now: Optional[datetime.datetime] = None) -> bool:
        """조임 간격이 지났으면 DB 하트비트를 남긴다.

        Args:
            now: 현재 시각(UTC naive). 생략하면 지금.

        Returns:
            이번 호출에서 실제로 기록했으면 True, 조임에 걸려 건너뛰었으면 False.
            기록 시도가 실패한 경우도 True 가 아니다 — 다음 호출에서 다시 시도한다.
        """
        now = now or now_utc_naive()
        last = self._last_db_heartbeat_at
        if last is not None and (now - last).total_seconds() < self.db_heartbeat_interval:
            return False
        ok = emit_heartbeat(engine, HEARTBEAT_WORKER_KIND,
                            metadata=self.db_heartbeat_metadata(), logger=_LOGGER)
        if ok:
            self._last_db_heartbeat_at = now
        return ok

    def heartbeat(self, *args, **kwargs):  # noqa: D102 - rq 의 시그니처를 그대로 잇는다
        result = super().heartbeat(*args, **kwargs)
        # 관측 배선이 워커를 죽이면 안 된다 — emit_heartbeat 이 이미 예외를 흡수한다.
        self.maybe_emit_db_heartbeat()
        return result


class HeartbeatWorker(HeartbeatWorkerMixin, Worker):
    """``rq worker`` 본체 + FOMS 감시 표 하트비트."""


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run an rq worker that reports a FOMS heartbeat.")
    p.add_argument("--url", default=os.environ.get("REDIS_URL"),
                   help="Redis 접속 URL (기본 $REDIS_URL).")
    p.add_argument("--queues", default="default",
                   help="소비할 큐 이름 쉼표 목록(기본 default).")
    p.add_argument("--heartbeat-interval", type=int,
                   default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
                   help=f"DB 하트비트 최소 간격(초, 기본 {DEFAULT_HEARTBEAT_INTERVAL_SECONDS}).")
    p.add_argument("--logging-level", default="INFO", help="rq 로깅 수준(기본 INFO).")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """워커를 띄운다.

    Returns:
        종료 코드. 인자 오류(URL 부재)는 2 — 조용히 큐 없이 도는 것보다 죽는 게 낫다.
    """
    args = _parse_args(argv)
    if not (args.url or "").strip():
        print("[run-rq-worker] REDIS_URL 이 없다", flush=True)
        return 2

    queue_names = [q.strip() for q in args.queues.split(",") if q.strip()]
    if not queue_names:
        print("[run-rq-worker] 소비할 큐가 없다", flush=True)
        return 2

    connection = Redis.from_url(args.url)
    queues = [Queue(name, connection=connection) for name in queue_names]
    worker = HeartbeatWorker(queues, connection=connection)
    worker.db_heartbeat_interval = max(1, int(args.heartbeat_interval))
    print(f"[run-rq-worker] started (queues={','.join(queue_names)} "
          f"heartbeat_interval={worker.db_heartbeat_interval}s)", flush=True)
    worker.work(logging_level=args.logging_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
