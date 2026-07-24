"""Purge terminal ``domain_side_effect_outbox`` rows (SIDEFX-RETENTION-01).

SIDEFX-00 이 만든 ``domain_side_effect_outbox`` 의 **terminal 행**만 retention 기간을
넘겼을 때 배치 삭제하는 ops CLI 다. 두 status class 만 대상으로 한다:

* ``DONE``  — ``completed_at`` 이 ``now - done_retention`` 보다 과거(기본 30일).
* ``DEAD``  — ``dead_at`` 이 ``now - dead_retention`` 보다 과거(기본 180일).

**절대 건드리지 않는 것**: ``PENDING``/``PROCESSING`` 행(아무리 오래돼도 삭제 0 — status
술어가 구조적으로 제외)과 source business row(outbox 행만 삭제, source FK 대상은 무접근).
retention_days 가 0 이상이면 cutoff(``now - retention``)가 항상 ``now`` 이전이므로 술어는
아직 살아 있는 terminal 행을 배제할 수 없게 만들지 않는다(정밀 status+timestamp 조건).

경계·재사용 규칙(REV-CLEANUP-01 ``purge_order_mutation_receipts`` 규약 이식):

* SIDEFX-00 스키마·부분 인덱스(``ix_dseo_done_retention``/``ix_dseo_dead_retention``)를
  **재사용만** 한다(스키마 변경/마이그레이션 없음). 삭제의 ``ORDER BY <ts>, id`` 가 그
  인덱스를 탄다.
* Flask app 을 import 하지 않는다 — 전체 app 초기화(gevent patch, DB auto-init/migrate)는
  Railway heartbeat timeout 원인이므로 ``DATABASE_URL`` 로 직접 엔진을 만든다(worker/
  purge tool 공통 규율).
* 동시 실행은 PostgreSQL **session-level advisory lock** 으로 직렬화한다(키는 outbox
  전용). 락을 못 잡으면(다른 purge 진행 중) 아무것도 지우지 않고 benign skip 한다.
* 기본은 **dry-run**(``--apply`` 없으면 삭제 0, 대상 수만 보고). ``--apply`` 만 실제 삭제.
* **broad date delete 금지**: 삭제는 ``id IN (SELECT id ... WHERE status+timestamp)`` 의
  ID 멤버십 삭제이지 ``DELETE ... WHERE <ts> < cutoff`` 광역 삭제가 아니다.
* **resume/crash-safe**: 배치마다 commit 하므로 중단 후 재실행하면 남은 행부터 이어서
  지운다(committed 배치는 사라진 채 유지). 재실행 자체가 resume 다.

공용 worker(``tools/ops/run_domain_side_effect_outbox.py`` 의 RETENTION loop, 86400s 주기)가
이미 :func:`foms.services.sidefx_worker.run_retention_once` 로 daily 자동 purge 를 수행한다.
이 CLI 는 그 자동 경로와 별개의 **수동/ops 진단·강제 실행** 진입점이다(별도 scheduler 신설 아님).

exit code: 0 성공(dry-run·apply·lock-skip 포함), 1 오류.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

_LOGGER = logging.getLogger("purge_domain_side_effect_outbox")

DEFAULT_DONE_RETENTION_DAYS = 30
DEFAULT_DEAD_RETENTION_DAYS = 180
DEFAULT_BATCH_SIZE = 1000
# session-level advisory lock 키(문자열 → hashtext). outbox 전용 키 — 같은 문자열은 같은
# 락을 가리켜 두 purge 프로세스가 서로를 배제한다(REV-CLEANUP-01 관용을 outbox 로 분리).
ADVISORY_LOCK_KEY = "foms:purge_domain_side_effect_outbox"

# terminal status → retention timestamp 컬럼. 삭제 SQL 의 식별자는 이 화이트리스트에서만
# 나오므로 f-string 보간에 주입 표면이 없다(값은 바인드 파라미터).
_RETENTION_TS_COLUMN = {"DONE": "completed_at", "DEAD": "dead_at"}


@dataclass(frozen=True)
class PurgeResult:
    """purge 실행 결과.

    Attributes:
        scanned_done: cutoff 이전 ``completed_at`` 을 가진 DONE(=삭제 대상) 수.
        scanned_dead: cutoff 이전 ``dead_at`` 을 가진 DEAD(=삭제 대상) 수.
        deleted_done: 실제 삭제된 DONE 수(dry-run 은 0).
        deleted_dead: 실제 삭제된 DEAD 수(dry-run 은 0).
        batches: 실행한 삭제 배치 수(DONE·DEAD 합).
        locked: advisory lock 을 못 잡아 skip 했으면 True(그 경우 모든 카운트 0).
        applied: ``--apply`` 로 실제 삭제를 수행했으면 True.
    """

    scanned_done: int
    scanned_dead: int
    deleted_done: int
    deleted_dead: int
    batches: int
    locked: bool
    applied: bool

    @property
    def scanned(self) -> int:
        """삭제 대상 총합(DONE + DEAD)."""
        return self.scanned_done + self.scanned_dead

    @property
    def deleted(self) -> int:
        """실제 삭제 총합(DONE + DEAD; dry-run 은 0)."""
        return self.deleted_done + self.deleted_dead


def _now_utc_naive() -> datetime:
    """naive(UTC) 현재 시각. ``completed_at``/``dead_at`` 이 naive-UTC 로 저장되므로 동일 규약."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _count(connection: Connection, status: str, cutoff: datetime) -> int:
    """``status`` terminal 행 중 retention timestamp 가 cutoff 이전인 수를 센다."""
    ts = _RETENTION_TS_COLUMN[status]  # KeyError = 프로그래밍 오류(화이트리스트 강제)
    return connection.execute(
        text(
            f"SELECT COUNT(*) FROM domain_side_effect_outbox "
            f"WHERE status = :status AND {ts} IS NOT NULL AND {ts} < :cutoff"
        ),
        {"status": status, "cutoff": cutoff},
    ).scalar() or 0


def _purge_class(
    connection: Connection,
    status: str,
    cutoff: datetime,
    batch_size: int,
    log: logging.Logger,
) -> tuple[int, int]:
    """한 status class 의 retention 초과 행을 ID 멤버십으로 배치 삭제한다.

    ``(<ts>, id)`` 부분 인덱스를 타는 keyset 삭제. 가장 오래된 것부터 배치로 지우고
    배치마다 commit → 재실행이 남은 것부터 이어받는 resume 그 자체.

    Returns:
        ``(deleted, batches)``.
    """
    ts = _RETENTION_TS_COLUMN[status]
    delete_batch = text(
        f"DELETE FROM domain_side_effect_outbox WHERE id IN ("
        f" SELECT id FROM domain_side_effect_outbox"
        f" WHERE status = :status AND {ts} IS NOT NULL AND {ts} < :cutoff"
        f" ORDER BY {ts}, id"
        f" LIMIT :lim)"
    )
    deleted = 0
    batches = 0
    while True:
        n = connection.execute(
            delete_batch, {"status": status, "cutoff": cutoff, "lim": batch_size}
        ).rowcount or 0
        connection.commit()
        if n == 0:
            break
        deleted += n
        batches += 1
        log.info(
            "[purge_domain_side_effect_outbox] status=%s batch=%d deleted=%d total=%d",
            status, batches, n, deleted,
        )
        if n < batch_size:
            break
    return deleted, batches


def run(
    connection: Connection,
    *,
    done_retention_days: int = DEFAULT_DONE_RETENTION_DAYS,
    dead_retention_days: int = DEFAULT_DEAD_RETENTION_DAYS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    apply: bool = False,
    now: Optional[datetime] = None,
    logger: Optional[logging.Logger] = None,
) -> PurgeResult:
    """retention 초과 terminal 행을 세고(그리고 ``apply`` 면) 배치 삭제한다.

    Args:
        connection: SQLAlchemy Connection(commit-as-you-go 모드). 배치마다
            ``connection.commit()`` 하므로 같은 물리 연결이 유지되어 session-level
            advisory lock 이 전체 실행 동안 살아 있는다.
        done_retention_days: DONE 은 ``completed_at`` 이 ``now - N일`` 보다 과거일 때만
            삭제(0 이상, 기본 30).
        dead_retention_days: DEAD 는 ``dead_at`` 이 ``now - N일`` 보다 과거일 때만 삭제
            (0 이상, 기본 180).
        batch_size: 한 배치에서 삭제할 최대 행 수(≥1, 기본 1000).
        apply: True 면 실제 삭제, False(기본)면 dry-run(삭제 0·대상 수만).
        now: 테스트용 시각 주입(기본 ``_now_utc_naive()``).
        logger: 진행 로그용(기본 모듈 로거).

    Returns:
        PurgeResult(scanned_done/scanned_dead/deleted_done/deleted_dead/batches/
        locked/applied).

    Raises:
        ValueError: retention_days<0 또는 batch_size<1.
    """
    if done_retention_days < 0:
        raise ValueError("done_retention_days must be >= 0")
    if dead_retention_days < 0:
        raise ValueError("dead_retention_days must be >= 0")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    log = logger or _LOGGER
    base = now or _now_utc_naive()
    done_cutoff = base - timedelta(days=done_retention_days)
    dead_cutoff = base - timedelta(days=dead_retention_days)

    got = connection.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:k))"),
        {"k": ADVISORY_LOCK_KEY},
    ).scalar()
    if not got:
        log.warning(
            "[purge_domain_side_effect_outbox] advisory lock busy; "
            "another purge is running — skipping (no rows touched)"
        )
        return PurgeResult(
            scanned_done=0, scanned_dead=0, deleted_done=0, deleted_dead=0,
            batches=0, locked=True, applied=False,
        )

    try:
        scanned_done = _count(connection, "DONE", done_cutoff)
        scanned_dead = _count(connection, "DEAD", dead_cutoff)

        deleted_done = deleted_dead = 0
        batches = 0
        if apply:
            if scanned_done:
                deleted_done, b = _purge_class(
                    connection, "DONE", done_cutoff, batch_size, log)
                batches += b
            if scanned_dead:
                deleted_dead, b = _purge_class(
                    connection, "DEAD", dead_cutoff, batch_size, log)
                batches += b

        return PurgeResult(
            scanned_done=scanned_done, scanned_dead=scanned_dead,
            deleted_done=deleted_done, deleted_dead=deleted_dead,
            batches=batches, locked=False, applied=apply,
        )
    finally:
        connection.execute(
            text("SELECT pg_advisory_unlock(hashtext(:k))"),
            {"k": ADVISORY_LOCK_KEY},
        )
        connection.commit()


def _make_engine() -> Engine:
    """``DATABASE_URL``(없으면 ``FOMS_TEST_DATABASE_URL``)로 bare 엔진 생성(Flask app 미import)."""
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL") or os.environ.get("FOMS_TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or FOMS_TEST_DATABASE_URL) is not set")
    if url.startswith("postgres://"):  # Railway 표기 → SQLAlchemy 표기
        url = "postgresql://" + url[len("postgres://"):]
    engine_kwargs: dict = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
    return create_engine(url, **engine_kwargs)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI flags. dry-run(기본) vs --apply, per-class retention, batch."""
    parser = argparse.ArgumentParser(
        description=(
            "Purge terminal domain_side_effect_outbox rows (SIDEFX-RETENTION-01). "
            "Default is dry-run; pass --apply to delete. "
            "PENDING/PROCESSING are never touched."
        )
    )
    parser.add_argument(
        "--done-retention-days", type=int, default=DEFAULT_DONE_RETENTION_DAYS,
        help=f"Delete DONE rows whose completed_at is older than now-N days "
             f"(default {DEFAULT_DONE_RETENTION_DAYS}).",
    )
    parser.add_argument(
        "--dead-retention-days", type=int, default=DEFAULT_DEAD_RETENTION_DAYS,
        help=f"Delete DEAD rows whose dead_at is older than now-N days "
             f"(default {DEFAULT_DEAD_RETENTION_DAYS}).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Rows deleted per batch/commit (default {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete. Without this flag, only counts (dry-run).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Explicit dry-run alias (default behaviour; no deletes).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entrypoint. Exit 0 성공, 1 오류."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args(argv)
    if args.dry_run and args.apply:
        _LOGGER.error(
            "[purge_domain_side_effect_outbox] --dry-run and --apply are mutually exclusive"
        )
        return 1

    mode = "apply" if args.apply else "dry-run"
    started = time.monotonic()
    try:
        engine = _make_engine()
        try:
            with engine.connect() as conn:
                result = run(
                    conn,
                    done_retention_days=args.done_retention_days,
                    dead_retention_days=args.dead_retention_days,
                    batch_size=args.batch_size,
                    apply=args.apply,
                )
        finally:
            engine.dispose()
        elapsed = time.monotonic() - started
        if result.locked:
            _LOGGER.info(
                "[purge_domain_side_effect_outbox] mode=%s SKIPPED (advisory lock busy) "
                "elapsed=%.1fs", mode, elapsed,
            )
            return 0
        _LOGGER.info(
            "[purge_domain_side_effect_outbox] mode=%s done_retention_days=%d "
            "dead_retention_days=%d batch_size=%d scanned_done=%d scanned_dead=%d "
            "deleted_done=%d deleted_dead=%d batches=%d elapsed=%.1fs",
            mode, args.done_retention_days, args.dead_retention_days, args.batch_size,
            result.scanned_done, result.scanned_dead,
            result.deleted_done, result.deleted_dead, result.batches, elapsed,
        )
        return 0
    except Exception:
        _LOGGER.exception("[purge_domain_side_effect_outbox] failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
