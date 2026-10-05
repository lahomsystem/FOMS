"""rq worker 를 DB 하트비트와 함께 띄운다 (OPS-HEARTBEAT-01, 후속 F-6).

``start.sh`` 는 워커 컨테이너의 마지막 줄에서 ``exec rq worker`` 로 자기를 대체해 왔다
(지금은 ``tools/ops/worker_supervisor.py`` 가 이 러너를 띄우고 죽으면 다시 띄운다).
그 프로세스는 **자기 생존을 어디에도 남기지 않았다** — Redis 쪽 rq 하트비트는 rq 대시보드
전용이고, FOMS 의 감시 표(``side_effect_worker_heartbeats``)에는 아무 행도 없었다. 큐 소비가
멎어도(2026-02 워커 offline) 표만 봐서는 알 수 없었다.

이 러너가 하는 일은 하나다: :class:`rq.Worker` 의 ``heartbeat()` 를 감싸 같은 자리에서
``RQ_WORKER`` 행도 갱신한다. rq 가 자기 TTL 을 연장하는 그 지점이 곧 "루프가 돌고 있다" 는
뜻이라, 별도 스레드로 심장을 따로 뛰게 하는 것보다 정직하다(스레드는 rq 루프가 멎어도
계속 뛴다).

놀고 있는 워커의 ``heartbeat()`` 주기는 ``worker_ttl - 15`` = 405초(rq 기본)이고, 그 값을
하트비트 metadata 의 ``interval_seconds`` 로 신고한다. 판정 예산의 정본은
:func:`foms.services.sidefx_worker.effective_heartbeat_budget` 이며 운영값은
max(등록부 900, 405 x 3) = **1215초**다 — 등록부 900 은 신고가 없을 때의 바닥값이다.

재배포 공백 줄이기(2026-10-02, 성능 원장 P2-6)
-----------------------------------------------
- 큐를 듣기 시작하면(rq 의 ``*** Listening on``) ``FOMS_RQ_READY_FILE`` 경로에 표식 파일을 만든다.
  감독자는 그것을 보고 미뤄 둔 루프 5개를 켠다 — 그 전까지 rq 가 CPU 를 혼자 쓴다.
- 듣기 전에 잡 모듈을 부모에서 미리 연다. rq ``Worker`` 는 잡마다 ``fork`` 하고 자식이 잡 함수를
  import 하므로, 부모가 열어 둔 모듈은 자식이 공짜로 물려받는다. 썸네일 잡은 그동안 잡마다
  저장소 모듈을 열고 boto3 를 처음부터 데웠다(로컬 실측 약 0.25초, 로그의 R2 활성화 줄).
- 저장소 어댑터도 부모가 한 번 만들어 둔다(2026-10-05, 성능 원장 P3-7). 10-02 판은 세션만
  데우고 어댑터는 버려서 잡마다 약 5ms + 활성화 로그 2줄이 남았다(135잡 135줄). 클라우드
  어댑터일 때만 남기고, 자식은 시작할 때 물려받은 연결 풀을 비운다(:meth:`main_work_horse`).

사용::

    python tools/ops/run_rq_worker.py --url "$REDIS_URL" --queues default
"""
from __future__ import annotations

import argparse
import datetime
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from redis import Redis  # noqa: E402
from rq import Queue, Worker  # noqa: E402

from db import engine  # noqa: E402
from foms.services.datetime_kst import now_utc_naive  # noqa: E402
from foms.services.loop_heartbeat import emit_heartbeat, init_sentry_once  # noqa: E402
from foms.services.sidefx_worker import WORKER_KIND_RQ_WORKER  # noqa: E402

_LOGGER = logging.getLogger("run_rq_worker")

#: 이 프로세스의 heartbeat PK 값. 정본은 sidefx_worker 의 WORKER_KIND_SPECS 등록부다.
HEARTBEAT_WORKER_KIND = WORKER_KIND_RQ_WORKER

#: DB 하트비트 최소 간격(초). rq 는 잡 하나마다도 ``heartbeat()`` 를 부르므로, 바쁜 워커가
#: 잡마다 DB 를 때리지 않게 여기서 조인다. 놀 때의 주기(405초)보다 훨씬 짧아 무해하다.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60

#: 큐를 듣기 시작하면 표식 파일을 만들 경로를 담은 env. 감독자(``tools/ops/worker_supervisor.py``
#: 의 ``RQ_READY_FILE_ENV``)가 심는다. 없으면 표식을 만들지 않는다(단독 실행).
READY_FILE_ENV = "FOMS_RQ_READY_FILE"

#: "0" 이면 잡 모듈을 미리 열지 않는다(되돌리기 스위치). 기본은 연다.
PRELOAD_ENV = "FOMS_RQ_PRELOAD_JOBS"

#: 미리 열 잡 모듈. 큐에 넣는 잡 함수는 전부 여기 산다(``foms.services.jobs.queue`` 의
#: ``_TASK_PATH_PREFIX``·푸시의 ``_PUSH_TASK`` — 같은 이름임을 시험이 지킨다).
PRELOAD_MODULES = ("foms.services.jobs.tasks", "foms.services.storage")

#: 어댑터까지 부모에서 만들어 두는 저장소 모듈(자식은 :func:`drop_inherited_storage_connections`).
STORAGE_MODULE = "foms.services.storage"


def drop_inherited_storage_connections() -> bool:
    """자식이 물려받은 저장소 클라이언트의 연결 풀을 비운다 — 저장소를 연 적 없으면 아무것도 안 한다.

    부모가 저장소 모듈을 안 열었으면(미리 열기 꺼짐) ``sys.modules`` 에 없으므로 여기서 새로
    import 하지 않는다 — 비울 것이 없는데 모듈을 여는 비용만 생긴다.

    Returns:
        비웠으면 True. 저장소 미적재·클라이언트 없음·실패는 False(잡은 그대로 돈다).
    """
    module = sys.modules.get(STORAGE_MODULE)
    drop = getattr(module, "drop_inherited_connections", None)
    if not callable(drop):
        return False
    try:
        return bool(drop())
    except Exception as exc:  # noqa: BLE001 - 정리 실패가 잡을 막으면 안 된다
        _LOGGER.warning("물려받은 저장소 연결 정리 실패(무시): %s", exc)
        return False


def mark_ready(env: Mapping[str, str]) -> bool:
    """감독자에게 "큐를 듣고 있다" 고 알리는 표식 파일을 만든다. 실패해도 워커는 계속 돈다.

    Args:
        env: ``READY_FILE_ENV`` 를 찾을 env.

    Returns:
        표식을 만들었으면 True. 경로가 없거나 쓰기에 실패했으면 False(감독자는 기한이 지나면
        어차피 루프를 켠다).
    """
    path = (env.get(READY_FILE_ENV) or "").strip()
    if not path:
        return False
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
        return True
    except OSError as exc:
        _LOGGER.warning("rq 준비 표식을 못 만들었다(%s): %s", path, exc)
        return False


def preload_job_modules(env: Mapping[str, str]) -> list[str]:
    """잡 자식들이 물려받도록 부모에서 잡 모듈을 미리 연다.

    저장소는 모듈만이 아니라 어댑터까지 만든다(:func:`foms.services.storage.prime_shared_storage`).
    클라우드 어댑터면 전역 싱글톤으로 남아 자식의 ``get_storage()`` 가 새로 만들지 않고(로컬
    실측 약 5ms + 로그 2줄 → 0), 생성이 로컬 저장소로 폴백했으면 남기지 않는다 — 한 번의
    생성 실패가 그 뒤 모든 잡으로 번지면 안 된다. 그 경우에도 boto3 세션은 이미 데워졌다.

    미리 열기가 실패해도 워커는 뜬다 — 잡마다 여는 예전 방식으로 돌아갈 뿐이다.

    Args:
        env: ``PRELOAD_ENV`` 를 볼 env.

    Returns:
        미리 연 모듈 이름 목록(끈 경우 빈 목록).
    """
    if (env.get(PRELOAD_ENV) or "1").strip() == "0":
        return []
    done: list[str] = []
    for name in PRELOAD_MODULES:
        try:
            module = importlib.import_module(name)
            if name == STORAGE_MODULE:
                module.prime_shared_storage()  # 클라우드면 남기고 폴백이면 버린다(위 설명)
        except Exception as exc:  # noqa: BLE001 - 미리 열기 실패가 워커 기동을 막으면 안 된다
            _LOGGER.warning("잡 모듈 미리 열기 실패(%s) — 잡마다 여는 방식으로 계속: %s", name, exc)
            continue
        done.append(name)
    return done


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

    def bootstrap(self, *args, **kwargs):
        """rq 가 등록·구독을 마치고 ``*** Listening on`` 을 남긴 직후 감독자에게 알린다."""
        result = super().bootstrap(*args, **kwargs)
        mark_ready(os.environ)
        return result

    def main_work_horse(self, *args, **kwargs):
        """fork 직후 **자식** 진입점 — 물려받은 DB 연결을 버리고 시작한다.

        이 한 줄이 없으면 2026-09-08 운영 결함이 재현된다. 부모(워커 본체)가 하트비트를
        쓰면서 SQLAlchemy 풀에 살아 있는 DB 연결을 남기고, rq 는 잡마다 ``fork`` 한다.
        자식은 그 풀을 그대로 물려받아 **같은 TLS 소켓**에 쓰고, 60초 뒤 부모가 다음
        하트비트를 같은 소켓에 쓰는 순간 두 프로세스의 TLS 레코드가 섞인다:

            Postgres: SSL error: decryption failed or bad record mac
            Postgres: unexpected EOF on client connection with an open transaction
            worker  : (psycopg2.OperationalError) SSL SYSCALL error: EOF detected

        실측(운영 run 28·29): 정산 동기화가 두 번 다 **정확히 60초**(부모 하트비트 주기)에
        죽었다. 60초를 넘게 도는 잡은 전부 같은 방식으로 깨진다.

        ``dispose(close=False)`` 는 풀에서 참조만 버리고 소켓을 닫지 않는다 — 닫으면 그
        소켓의 진짜 주인인 **부모의 연결까지** 끊긴다.

        저장소(R2) 클라이언트도 부모가 만들어 물려준다(:func:`preload_job_modules`). 그 풀은
        보통 비어 있지만, 같은 모양의 공유가 생기지 않게 자식 쪽 풀을 비운다 — HTTP/TLS 소켓은
        닫아도 종료 신호를 보내지 않아 DB 와 달리 부모 연결을 끊지 않는다.
        """
        engine.dispose(close=False)
        drop_inherited_storage_connections()
        # 자식은 자기 시각으로 다시 센다(부모가 방금 썼다는 표식을 물려받으면 안 된다).
        self._last_db_heartbeat_at = None
        return super().main_work_horse(*args, **kwargs)


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
    # 이 프로세스에는 지금까지 Sentry 가 한 번도 붙지 않았다(실측: import 직후
    # ``sentry_sdk.get_client().is_active()`` = False). ``app.py`` 를 안 거치고 ``db`` 만
    # 열기 때문이다 — 그래서 하트비트 실패마다 부르는 emit_heartbeat 의 capture_exception()
    # 이 전량 no-op 이었다. init 하나로 그 구멍이 닫힌다: 잡 실패는 RQ 통합이, 미처리 예외는
    # SDK excepthook 이 스스로 잡으므로 여기에 try/except 를 새로 만들지 않는다.
    init_sentry_once(_LOGGER)
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
    preloaded = preload_job_modules(os.environ)
    print(f"[run-rq-worker] started (queues={','.join(queue_names)} "
          f"heartbeat_interval={worker.db_heartbeat_interval}s "
          f"preloaded={','.join(preloaded) or '-'})", flush=True)
    worker.work(logging_level=args.logging_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
