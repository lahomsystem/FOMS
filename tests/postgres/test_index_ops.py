"""INDEX-OPS-01 PostgreSQL contract test (PGTEST-00 lane).

Proves the ``index_ops_00`` migration collapses the **exact-duplicate** unique
index on ``designer_sketchup_parse_jobs(idempotency_key)`` and nothing else:

* the standalone ``ux_sketchup_jobs_idempotency_key`` and the constraint-backed
  ``designer_sketchup_parse_jobs_idempotency_key_key`` are a true exact duplicate
  (same table, column, uniqueness, no predicate) — different name only;
* ``upgrade`` drops **only** the standalone index; the constraint index and every
  functional index (``ix_sketchup_jobs_*``, pkey) survive, uniqueness stays
  enforced;
* ``downgrade`` restores the standalone index (rollback DDL verified);
* an ``idempotency_key = $1`` lookup still plans an Index Scan on the surviving
  constraint index — 0 perf regression;
* SAFETY: when the UNIQUE constraint is absent (a catalog where ``ux_`` is the
  sole uniqueness index — possible in prod since the intake migration's CREATE
  TABLE omits the inline constraint), ``upgrade`` is a **no-op** and does not
  remove the load-bearing index. This is why local-catalog observation alone does
  not authorise the prod run.

``FOMS_TEST_DATABASE_URL`` unset → the whole lane skips (conftest). The dev DSN
comes from the environment; no password is committed here. The schema is applied
via ``Base.metadata.create_all`` (conftest), so the baseline has the constraint
index but not the migration-only ``ux_`` — each test synthesises the prod-like
duplicate and restores the baseline on teardown.
"""
from __future__ import annotations

import importlib.util
import pathlib
from typing import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

# --------------------------------------------------------------------------- #
# load the migration module by path (migrations/versions is not a package)
# --------------------------------------------------------------------------- #
_MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "index_ops_00_dedup_indexes.py"
)
_spec = importlib.util.spec_from_file_location("index_ops_00_dedup_indexes", _MIGRATION_PATH)
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)  # top-level import only — no DB side effects

TABLE = mig.TABLE                      # designer_sketchup_parse_jobs
DUP_INDEX = mig.DUP_INDEX              # ux_sketchup_jobs_idempotency_key (standalone)
CONSTRAINT_INDEX = "designer_sketchup_parse_jobs_idempotency_key_key"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _index_names(conn: Connection) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
    ).fetchall()
    return {r[0] for r in rows}


# Functional indexes the intake migration creates on the same table — different
# definitions, must never be flagged as duplicates nor dropped. create_all does
# not emit them (they are migration-only), so the fixture mirrors prod by adding
# them.
_FUNCTIONAL_DDL = {
    "ix_sketchup_jobs_status_created_at": "(status, created_at)",
    "ix_sketchup_jobs_claim": "(status, lease_expires_at, created_at)",
    "ix_sketchup_jobs_lease_owner": "(lease_owner)",
    "ix_sketchup_jobs_artifact_id": "(artifact_id)",
}


def _exact_duplicate_groups(conn: Connection) -> list[tuple[str, list[str]]]:
    """Canonical pg_index grouping over ALL indexes on the table.

    Indexes identical in every dimension (table, columns, opclass, options,
    collation, expression, predicate, uniqueness) but name form one group. A
    functional index with a different definition can never join the pair's group.
    """
    rows = conn.execute(text(
        """
        SELECT indrelid::regclass::text AS tbl,
               array_agg(indexrelid::regclass::text ORDER BY indexrelid::regclass::text) AS idxs
        FROM pg_index i
        WHERE i.indrelid = CAST(:t AS regclass)
        GROUP BY indrelid, indkey, indclass, indoption, indcollation,
                 COALESCE(indexprs::text, ''), COALESCE(indpred::text, ''), indisunique
        HAVING count(*) > 1
        """
    ), {"t": TABLE}).fetchall()
    return [(r[0], r[1]) for r in rows]


def _create_standalone_dup(conn: Connection) -> None:
    conn.execute(text(mig.CREATE_DUP_SQL))


def _drop_standalone_dup(conn: Connection) -> None:
    conn.execute(text(f"DROP INDEX IF EXISTS {DUP_INDEX}"))


def _drop_unique_constraint(conn: Connection) -> None:
    conn.execute(text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {CONSTRAINT_INDEX}"))


def _add_unique_constraint(conn: Connection) -> None:
    if not mig.unique_constraint_present(conn):
        conn.execute(text(
            f"ALTER TABLE {TABLE} ADD CONSTRAINT {CONSTRAINT_INDEX} "
            f"UNIQUE (idempotency_key)"
        ))


# --------------------------------------------------------------------------- #
# fixtures — autocommit conn (CONCURRENTLY DDL cannot run inside a transaction)
# --------------------------------------------------------------------------- #
@pytest.fixture
def dup_conn(pg_engine) -> Iterator[Connection]:
    """Autocommit connection normalised to the prod-like *duplicate* state.

    Baseline (create_all) has the constraint index but not ``ux_``. This fixture
    adds ``ux_`` so both exist (the exact duplicate). Teardown restores baseline:
    constraint present, ``ux_`` absent.
    """
    conn = pg_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        _add_unique_constraint(conn)      # defensive: baseline should already have it
        _create_standalone_dup(conn)      # synthesise the duplicate
        for name, cols in _FUNCTIONAL_DDL.items():   # mirror prod's functional indexes
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {TABLE} {cols}"))
        assert mig.unique_constraint_present(conn)
        assert DUP_INDEX in _index_names(conn)
        yield conn
    finally:
        for name in _FUNCTIONAL_DDL:
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
        _add_unique_constraint(conn)      # restore the canonical survivor if a test dropped it
        _drop_standalone_dup(conn)        # restore baseline (no standalone dup)
        conn.close()


# --------------------------------------------------------------------------- #
# 1. the pair really is an exact duplicate (candidate correctness)
# --------------------------------------------------------------------------- #
def test_pair_is_exact_duplicate(dup_conn):
    groups = _exact_duplicate_groups(dup_conn)
    assert len(groups) == 1, groups
    tbl, idxs = groups[0]
    assert tbl == TABLE
    assert set(idxs) == {DUP_INDEX, CONSTRAINT_INDEX}, idxs


# --------------------------------------------------------------------------- #
# 2. upgrade removes ONLY the standalone duplicate; everything else survives
# --------------------------------------------------------------------------- #
def test_upgrade_removes_only_standalone_duplicate(dup_conn):
    before = _index_names(dup_conn)
    assert {DUP_INDEX, CONSTRAINT_INDEX} <= before

    mig._apply_upgrade(dup_conn)

    after = _index_names(dup_conn)
    # exactly the standalone duplicate is gone
    assert before - after == {DUP_INDEX}, (before, after)
    # constraint index + every functional index preserved
    assert CONSTRAINT_INDEX in after
    assert set(_FUNCTIONAL_DDL) <= after, (set(_FUNCTIONAL_DDL) - after)
    assert f"{TABLE}_pkey" in after
    # uniqueness still enforced by the surviving constraint
    assert mig.unique_constraint_present(dup_conn)


# --------------------------------------------------------------------------- #
# 3. downgrade restores the standalone unique index (rollback DDL)
# --------------------------------------------------------------------------- #
def test_downgrade_restores_standalone_index(dup_conn):
    mig._apply_upgrade(dup_conn)
    assert DUP_INDEX not in _index_names(dup_conn)

    mig._apply_downgrade(dup_conn)

    assert DUP_INDEX in _index_names(dup_conn)
    # restored as a UNIQUE index
    is_unique = dup_conn.execute(text(
        "SELECT indisunique FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "WHERE c.relname = :n"
    ), {"n": DUP_INDEX}).scalar()
    assert is_unique is True


# --------------------------------------------------------------------------- #
# 4. surviving index still serves the equality lookup — 0 perf regression
# --------------------------------------------------------------------------- #
def test_lookup_still_index_scan_after_upgrade(dup_conn):
    mig._apply_upgrade(dup_conn)  # standalone dropped; only constraint index remains

    dup_conn.execute(text("SET enable_seqscan = off"))
    try:
        plan = "\n".join(
            r[0] for r in dup_conn.execute(text(
                f"EXPLAIN SELECT 1 FROM {TABLE} WHERE idempotency_key = :k"
            ), {"k": "probe"}).fetchall()
        )
    finally:
        dup_conn.execute(text("RESET enable_seqscan"))

    assert "Seq Scan" not in plan, plan
    assert "Index" in plan, plan
    assert CONSTRAINT_INDEX in plan, plan  # served by the surviving constraint index


# --------------------------------------------------------------------------- #
# 5. SAFETY — guard skips the drop when ux_ is the sole uniqueness index
# --------------------------------------------------------------------------- #
def test_upgrade_is_noop_without_constraint(dup_conn):
    # simulate a catalog where the table has only the standalone unique index
    _drop_unique_constraint(dup_conn)
    assert not mig.unique_constraint_present(dup_conn)
    assert DUP_INDEX in _index_names(dup_conn)

    mig._apply_upgrade(dup_conn)  # must NOT drop the load-bearing index

    assert DUP_INDEX in _index_names(dup_conn), "guard failed: dropped the sole unique index"
    # fixture teardown re-adds the constraint and drops ux_ to restore baseline
