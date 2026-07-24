"""Infrastructure smoke tests for the PostgreSQL lane (PGTEST-00).

These prove the lane itself works — a throwaway test database is created, the
schema is applied, and the PostgreSQL primitives the downstream concurrency
packets rely on (SELECT 1, advisory lock, FOR UPDATE) behave. They are NOT
application mutation tests. They skip when the lane is not configured
(FOMS_TEST_DATABASE_URL unset), keeping the lane opt-in.
"""
from __future__ import annotations

from sqlalchemy import text


def test_test_database_is_throwaway(pg_engine) -> None:
    """The lane runs against a generated foms_test_* database, not a real one."""
    with pg_engine.connect() as conn:
        dbname = conn.execute(text("SELECT current_database()")).scalar()
    assert dbname.startswith("foms_test_"), dbname


def test_select_one(pg_engine) -> None:
    """Basic connectivity: a trivial query returns."""
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1


def test_schema_applied(pg_engine) -> None:
    """create_all populated the app schema (orders table present)."""
    with pg_engine.connect() as conn:
        exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'orders')"
            )
        ).scalar()
    assert exists is True


def test_advisory_lock_acquire_release(pg_engine) -> None:
    """Session advisory lock (used by the migration/concurrency paths) round-trips."""
    lock_id = 918273645
    with pg_engine.connect() as conn:
        got = conn.execute(
            text("SELECT pg_try_advisory_lock(:i)"), {"i": lock_id}
        ).scalar()
        assert got is True
        released = conn.execute(
            text("SELECT pg_advisory_unlock(:i)"), {"i": lock_id}
        ).scalar()
        assert released is True


def test_select_for_update_one_row(pg_engine) -> None:
    """Row-level FOR UPDATE locking works inside a transaction."""
    with pg_engine.begin() as conn:
        conn.execute(
            text("CREATE TEMP TABLE _pg_lane_smoke (id int primary key) ON COMMIT DROP")
        )
        conn.execute(text("INSERT INTO _pg_lane_smoke (id) VALUES (1)"))
        locked = conn.execute(
            text("SELECT id FROM _pg_lane_smoke WHERE id = 1 FOR UPDATE")
        ).scalar()
        assert locked == 1
