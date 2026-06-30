"""Delete expired OrderDraft rows (P0-00C).

Default is dry-run. Pass --execute to delete rows where expires_at < now().

Flask app은 import하지 않는다. 전체 app 초기화(gevent patch, DB auto-init,
auto-migrate 등)는 Railway Heartbeat timeout의 원인이 되므로 DATABASE_URL로
직접 SQLAlchemy 엔진을 생성해 작업한다.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timedelta

logger = logging.getLogger("cleanup_order_drafts")

# 미승격 ERP draft 주문(status='DRAFT')을 소프트 삭제하기까지의 경과 시간(시간).
ERP_DRAFT_STALE_HOURS = int(os.environ.get("ERP_DRAFT_STALE_HOURS", "48"))


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags for dry-run vs execute."""
    parser = argparse.ArgumentParser(
        description="Cleanup expired OrderDraft rows (default: dry-run)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run alias (default behavior; no deletes).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Delete expired drafts. Without this flag, only counts.",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    """Configure root logging for cron stdout."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _make_session():
    """Create a bare SQLAlchemy session from DATABASE_URL (no Flask app)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Railway Postgres URL은 postgres:// → postgresql:// 변환 필요
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    engine_kwargs: dict = {"pool_pre_ping": True}
    # connect_timeout는 psycopg2 전용; pytest sqlite:// 에서는 TypeError 발생
    if "sqlite" not in url:
        engine_kwargs["connect_args"] = {"connect_timeout": 10}
    engine = create_engine(url, **engine_kwargs)
    Session = sessionmaker(bind=engine)
    return Session(), engine


def run(*, execute: bool = False, session=None) -> tuple[int, int]:
    """Count and optionally delete expired OrderDraft rows.

    Args:
        execute: When True, delete rows with expires_at < now().
        session: Optional SQLAlchemy session (pytest uses Flask ``db_session``).

    Returns:
        Tuple of (scanned_count, deleted_count).
    """
    from sqlalchemy import text

    owns_session = session is None
    engine = None
    if owns_session:
        session, engine = _make_session()
    now = datetime.utcnow()
    try:
        scanned_row = session.execute(
            text("SELECT COUNT(*) FROM order_drafts WHERE expires_at < :now"),
            {"now": now},
        ).fetchone()
        scanned = scanned_row[0] if scanned_row else 0

        deleted = 0
        if execute and scanned > 0:
            result = session.execute(
                text("DELETE FROM order_drafts WHERE expires_at < :now"),
                {"now": now},
            )
            deleted = result.rowcount
            session.commit()
        return scanned, deleted
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
            if engine is not None:
                engine.dispose()


def run_erp_draft_orders(
    *, execute: bool = False, session=None, stale_hours: int = ERP_DRAFT_STALE_HOURS
) -> tuple[int, int]:
    """Count and optionally soft-delete stale, never-promoted ERP draft orders.

    add_order 자동저장/draft 생성은 ``orders`` 테이블에 ``status='DRAFT'`` 행을
    남긴다. 명시 저장(승격) 시 status가 RECEIVED/MEASURE 등으로 바뀌므로
    여전히 ``status='DRAFT'`` 인 행은 끝까지 제출되지 않은 버려진 draft다.
    이를 일정 시간 경과 후 소프트 삭제(``status='DELETED'`` + ``deleted_at``)해
    ``orders`` 테이블 무한 증식을 막는다(가역적, R2 첨부 고아 없음).

    Args:
        execute: True면 임계 초과 draft를 소프트 삭제.
        session: 선택적 SQLAlchemy 세션(pytest는 Flask ``db_session``).
        stale_hours: 마지막 갱신 후 이 시간(시간)을 넘긴 draft만 대상.

    Returns:
        (scanned_count, soft_deleted_count) 튜플.
    """
    from sqlalchemy import text

    owns_session = session is None
    engine = None
    if owns_session:
        session, engine = _make_session()
    now = datetime.now()
    threshold = now - timedelta(hours=stale_hours)
    # status='DRAFT' = 미승격 ERP draft 유일 식별자(JSON 술어 불필요 → 크로스 DB 안전).
    where = (
        "status = 'DRAFT' AND deleted_at IS NULL "
        "AND COALESCE(structured_updated_at, created_at) < :threshold"
    )
    try:
        scanned_row = session.execute(
            text(f"SELECT COUNT(*) FROM orders WHERE {where}"),
            {"threshold": threshold},
        ).fetchone()
        scanned = scanned_row[0] if scanned_row else 0

        deleted = 0
        if execute and scanned > 0:
            result = session.execute(
                text(
                    f"UPDATE orders SET status='DELETED', original_status='DRAFT', "
                    f"deleted_at=:now_iso WHERE {where}"
                ),
                {"threshold": threshold, "now_iso": now.isoformat()},
            )
            deleted = result.rowcount
            session.commit()
        return scanned, deleted
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
            if engine is not None:
                engine.dispose()


def main() -> int:
    """CLI entrypoint. Exit 0 on success, 1 on error."""
    _setup_logging()
    args = _parse_args()
    if args.dry_run and args.execute:
        logger.error("[cleanup_order_drafts] --dry-run and --execute are mutually exclusive")
        return 1

    execute = args.execute
    mode = "execute" if execute else "dry-run"
    started = time.monotonic()
    try:
        # 두 청소를 한 세션/엔진으로 수행(Railway cron 단일 명령).
        session, engine = _make_session()
        try:
            scanned, deleted = run(execute=execute, session=session)
            erp_scanned, erp_deleted = run_erp_draft_orders(execute=execute, session=session)
        finally:
            session.close()
            engine.dispose()
        elapsed = time.monotonic() - started
        logger.info(
            "[cleanup_order_drafts] mode=%s scanned=%d deleted=%d "
            "erp_draft_scanned=%d erp_draft_deleted=%d elapsed=%.1fs",
            mode,
            scanned,
            deleted,
            erp_scanned,
            erp_deleted,
            elapsed,
        )
        return 0
    except Exception:
        logger.exception("[cleanup_order_drafts] failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
