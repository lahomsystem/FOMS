"""Purge expired ``order_mutation_receipts`` rows (REV-CLEANUP-01).

REV-00 이 만든 ``order_mutation_receipts`` (idempotency + read-after-write receipt)
중 replay window(``expires_at`` = 커밋+24시간)가 retention 기간을 넘겨 만료된 행을
배치 삭제한다. child ``order_mutation_read_resources`` 는 FK ``ON DELETE CASCADE`` 로
함께 사라진다.

**절대 건드리지 않는 것**: active receipt(아직 24시간 replay window 안, 즉
``expires_at >= now``)와 그 read-resource, 그리고 cache family generation rows.
retention_days 가 0 이상이면 cutoff(``now - retention``)가 항상 ``now`` 이전이므로
``expires_at < cutoff`` 술어는 active/replay receipt 를 구조적으로 제외한다.

경계·재사용 규칙:

* REV-00 스키마·``(expires_at, id)`` purge 인덱스를 **재사용만** 한다(스키마 변경/
  마이그레이션 없음). purge 술어의 ``ORDER BY expires_at, id`` 가 그 인덱스를 탄다.
* Flask app 을 import 하지 않는다 — 전체 app 초기화(gevent patch, DB auto-init,
  auto-migrate)는 Railway heartbeat timeout 원인이 되므로 ``DATABASE_URL`` 로 직접
  엔진을 만든다(``tools/cron/cleanup_order_drafts.py`` 와 동일 규율).
* 동시 실행은 PostgreSQL **session-level advisory lock** 으로 직렬화한다. 락을 못
  잡으면(다른 purge 진행 중) 아무것도 지우지 않고 benign skip 한다.
* 기본은 **dry-run**(``--apply`` 없으면 삭제 0, 대상 수만 보고). ``--apply`` 만
  실제 삭제한다.
* **resume/crash-safe**: 배치마다 commit 하므로 중단 후 재실행하면 남은 만료 행부터
  이어서 지운다(committed 배치는 사라진 채 유지). 재실행 자체가 resume 다.

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

_LOGGER = logging.getLogger("purge_order_mutation_receipts")

DEFAULT_RETENTION_DAYS = 7
DEFAULT_BATCH_SIZE = 1000
# session-level advisory lock 키(문자열 → hashtext). 같은 문자열은 같은 락을 가리켜
# 두 purge 프로세스가 서로를 배제한다. backfill 의 hashtext advisory 관용을 재사용.
ADVISORY_LOCK_KEY = "foms:purge_order_mutation_receipts"


@dataclass(frozen=True)
class PurgeResult:
    """purge 실행 결과.

    Attributes:
        scanned: cutoff 이전 ``expires_at`` 를 가진(=삭제 대상) receipt 수. dry-run 은
            이 값만 보고한다.
        deleted: 실제 삭제된 receipt 수(dry-run 은 0). child cascade 는 별도 계수하지
            않는다(FK 가 보장).
        batches: 실행한 삭제 배치 수.
        locked: advisory lock 을 못 잡아 skip 했으면 True(그 경우 scanned/deleted=0).
        applied: ``--apply`` 로 실제 삭제를 수행했으면 True.
    """

    scanned: int
    deleted: int
    batches: int
    locked: bool
    applied: bool


def _now_utc_naive() -> datetime:
    """naive(UTC) 현재 시각. ``expires_at`` 이 naive-UTC 로 저장되므로 동일 규약."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run(
    connection: Connection,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    apply: bool = False,
    now: Optional[datetime] = None,
    logger: Optional[logging.Logger] = None,
) -> PurgeResult:
    """만료 receipt 를 세고(그리고 ``apply`` 면) 배치 삭제한다.

    Args:
        connection: SQLAlchemy Connection(commit-as-you-go 모드). 배치마다
            ``connection.commit()`` 하므로 같은 물리 연결이 유지되어 session-level
            advisory lock 이 전체 실행 동안 살아 있는다.
        retention_days: ``expires_at`` 가 ``now - retention_days`` 보다 과거인 receipt
            만 삭제 대상. 0 이상이어야 하며 기본 7. active/replay(``expires_at >= now``)
            는 구조적으로 제외된다.
        batch_size: 한 배치에서 삭제할 최대 receipt 수(≥1, 기본 1000).
        apply: True 면 실제 삭제, False(기본)면 dry-run(삭제 0·대상 수만).
        now: 테스트용 시각 주입(기본 ``_now_utc_naive()``).
        logger: 진행 로그용(기본 모듈 로거).

    Returns:
        PurgeResult(scanned/deleted/batches/locked/applied).

    Raises:
        ValueError: retention_days<0 또는 batch_size<1.
    """
    if retention_days < 0:
        raise ValueError("retention_days must be >= 0")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    log = logger or _LOGGER
    cutoff = (now or _now_utc_naive()) - timedelta(days=retention_days)

    got = connection.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:k))"),
        {"k": ADVISORY_LOCK_KEY},
    ).scalar()
    if not got:
        log.warning(
            "[purge_order_mutation_receipts] advisory lock busy; "
            "another purge is running — skipping (no rows touched)"
        )
        return PurgeResult(scanned=0, deleted=0, batches=0, locked=True, applied=False)

    try:
        scanned = connection.execute(
            text(
                "SELECT COUNT(*) FROM order_mutation_receipts "
                "WHERE expires_at < :cutoff"
            ),
            {"cutoff": cutoff},
        ).scalar() or 0

        deleted = 0
        batches = 0
        if apply and scanned:
            # (expires_at, id) 인덱스를 타는 keyset 삭제. 가장 오래 만료된 것부터 배치로
            # 지우고 배치마다 commit → 재실행이 남은 것부터 이어받는 resume 그 자체.
            delete_batch = text(
                "DELETE FROM order_mutation_receipts WHERE id IN ("
                " SELECT id FROM order_mutation_receipts"
                " WHERE expires_at < :cutoff"
                " ORDER BY expires_at, id"
                " LIMIT :lim)"
            )
            while True:
                n = connection.execute(
                    delete_batch, {"cutoff": cutoff, "lim": batch_size}
                ).rowcount or 0
                connection.commit()
                if n == 0:
                    break
                deleted += n
                batches += 1
                log.info(
                    "[purge_order_mutation_receipts] batch=%d deleted=%d total=%d",
                    batches, n, deleted,
                )
                if n < batch_size:
                    break

        return PurgeResult(
            scanned=scanned, deleted=deleted, batches=batches,
            locked=False, applied=apply,
        )
    finally:
        connection.execute(
            text("SELECT pg_advisory_unlock(hashtext(:k))"),
            {"k": ADVISORY_LOCK_KEY},
        )
        connection.commit()


def _make_engine() -> Engine:
    """``DATABASE_URL`` 로 bare SQLAlchemy 엔진 생성(Flask app 미import)."""
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    if url.startswith("postgres://"):  # Railway 표기 → SQLAlchemy 표기
        url = "postgresql://" + url[len("postgres://"):]
    engine_kwargs: dict = {"pool_pre_ping": True}
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
    return create_engine(url, **engine_kwargs)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI flags. dry-run(기본) vs --apply, retention, batch."""
    parser = argparse.ArgumentParser(
        description=(
            "Purge expired order_mutation_receipts (REV-CLEANUP-01). "
            "Default is dry-run; pass --apply to delete."
        )
    )
    parser.add_argument(
        "--retention-days", type=int, default=DEFAULT_RETENTION_DAYS,
        help=f"Delete receipts whose expires_at is older than now-N days "
             f"(default {DEFAULT_RETENTION_DAYS}).",
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
            "[purge_order_mutation_receipts] --dry-run and --apply are mutually exclusive"
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
                    retention_days=args.retention_days,
                    batch_size=args.batch_size,
                    apply=args.apply,
                )
        finally:
            engine.dispose()
        elapsed = time.monotonic() - started
        if result.locked:
            _LOGGER.info(
                "[purge_order_mutation_receipts] mode=%s SKIPPED (advisory lock busy) "
                "elapsed=%.1fs", mode, elapsed,
            )
            return 0
        _LOGGER.info(
            "[purge_order_mutation_receipts] mode=%s retention_days=%d batch_size=%d "
            "scanned=%d deleted=%d batches=%d elapsed=%.1fs",
            mode, args.retention_days, args.batch_size,
            result.scanned, result.deleted, result.batches, elapsed,
        )
        return 0
    except Exception:
        _LOGGER.exception("[purge_order_mutation_receipts] failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
