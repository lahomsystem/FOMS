"""INDEX-OPS-01: exact-duplicate index cleanup (idempotency_key)

Revision ID: index_ops_00
Revises: task_backfill_00
Create Date: 2026-07-25

§5.2 INDEX-OPS-01. ``designer_sketchup_parse_jobs.idempotency_key`` carries **two**
identical UNIQUE btree indexes on the same single column, no predicate:

* ``designer_sketchup_parse_jobs_idempotency_key_key`` — the constraint-backed
  index emitted by the ORM (``models`` declares ``idempotency_key ... unique=True``;
  ``Base.metadata.create_all`` materialises the UNIQUE **constraint**). This is the
  canonical survivor: it is tied to the model and cannot be removed with
  ``DROP INDEX`` (only ``ALTER TABLE ... DROP CONSTRAINT`` would).
* ``ux_sketchup_jobs_idempotency_key`` — a redundant *standalone* unique index the
  ``designer_sketchup_intake`` migration additionally created via
  ``CREATE UNIQUE INDEX``. Same (table, column, uniqueness, no partial predicate),
  different name → an **exact duplicate**. Not constraint-backed, so droppable.

This migration removes only that redundant standalone index. Uniqueness is
unaffected — the constraint index enforces the same guarantee. Functional indexes
(``ix_sketchup_jobs_status_created_at`` / ``_claim`` / ``_lease_owner`` /
``_artifact_id`` / pkey) have different definitions and are **not** touched.

SAFETY / prod precondition (do NOT skip):
    The ``designer_sketchup_intake`` migration's ``CREATE TABLE`` does not declare
    the UNIQUE constraint inline — it creates ``ux_...`` separately. So a database
    whose table was materialised purely by that migration (not by ``create_all``)
    could hold *only* ``ux_...`` and NOT the constraint index. Blindly dropping
    ``ux_...`` there would remove the SOLE uniqueness index → correctness
    regression. ``upgrade()`` therefore self-guards: it drops ``ux_...`` only when
    the UNIQUE **constraint** on ``idempotency_key`` is present (true duplicate).
    Otherwise it is a no-op. Confirm on the target catalog before deploy:
        SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        WHERE t.relname='designer_sketchup_parse_jobs' AND c.contype='u';
    plus an EXPLAIN of an ``idempotency_key = $1`` lookup (must still be an Index
    Scan on the surviving constraint index — 0 perf regression). Local-catalog
    observation alone does not authorise the prod run.

CONCURRENTLY: DROP/CREATE INDEX CONCURRENTLY cannot run inside a transaction
block, so each statement runs after an explicit COMMIT (``_run_concurrently``,
mirroring ``phase_c_indexes``). Multi-replica ``alembic upgrade head`` is
serialised by the **session-level** advisory lock in ``migrations/env.py`` — the
xact-level lock trap (released by the internal COMMIT, leaving CONCURRENTLY builds
to race into INVALID indexes) is documented there and avoided by design.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'index_ops_00'
down_revision: Union[str, None] = 'task_backfill_00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = 'designer_sketchup_parse_jobs'
COLUMN = 'idempotency_key'
DUP_INDEX = 'ux_sketchup_jobs_idempotency_key'

# Exact-duplicate cleanup DDL (single source of truth; imported by the test).
DROP_DUP_SQL = f'DROP INDEX CONCURRENTLY IF EXISTS {DUP_INDEX}'
CREATE_DUP_SQL = (
    f'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {DUP_INDEX} '
    f'ON {TABLE} ({COLUMN})'
)

# The canonical survivor: a UNIQUE constraint on exactly (idempotency_key).
_CONSTRAINT_GUARD_SQL = text(
    """
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = :table
      AND c.contype = 'u'
      AND (SELECT array_agg(a.attname::text ORDER BY k.ord)
             FROM unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
             JOIN pg_attribute a
               ON a.attrelid = c.conrelid AND a.attnum = k.attnum) = ARRAY[:column]::text[]
    LIMIT 1
    """
)


def unique_constraint_present(conn) -> bool:
    """True when a UNIQUE constraint on exactly ``(idempotency_key)`` exists.

    Args:
        conn: live SQLAlchemy connection bound to the target database.

    Returns:
        Whether the canonical constraint-backed uniqueness index is present, i.e.
        whether dropping the redundant standalone index is safe (the constraint
        keeps enforcing uniqueness).
    """
    return conn.execute(
        _CONSTRAINT_GUARD_SQL, {'table': TABLE, 'column': COLUMN}
    ).first() is not None


def _run_concurrently(conn, sql: str) -> None:
    """Run CONCURRENTLY DDL outside the migration transaction (COMMIT first)."""
    conn.execute(text('COMMIT'))
    conn.execute(text(sql))


def _apply_upgrade(conn) -> None:
    """Guarded dedup on ``conn`` (shared by ``upgrade`` and the PG-lane test)."""
    if unique_constraint_present(conn):
        _run_concurrently(conn, DROP_DUP_SQL)
    else:
        # ux_ is the sole uniqueness index here — removing it would drop the
        # guarantee. No true duplicate to collapse; leave the catalog untouched.
        print(
            f'[INDEX-OPS-01] Skip: no UNIQUE constraint on {TABLE}({COLUMN}); '
            f'{DUP_INDEX} is load-bearing, not a duplicate.'
        )


def _apply_downgrade(conn) -> None:
    """Recreate the standalone unique index on ``conn`` (rollback of the dedup)."""
    _run_concurrently(conn, CREATE_DUP_SQL)


def upgrade() -> None:
    """Drop the redundant standalone unique index, but only when the constraint survives."""
    _apply_upgrade(op.get_bind())


def downgrade() -> None:
    """Recreate the standalone unique index (rollback of the dedup)."""
    _apply_downgrade(op.get_bind())
