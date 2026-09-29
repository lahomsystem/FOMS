"""PG lane: every engine binds parameters client-side, like psycopg2 did.

psycopg (3) binds server-side by default. Then one parameter used as two types —
``VALUES (:d, CAST(:d AS JSONB))`` — fails with ``AmbiguousParameter`` (seen in
``test_access_log_detail_pg.py`` on the first switch). ``db_url_resolver`` sets
``ClientCursor`` on every psycopg connection, including engines built from a URL
(SIDEFX, cron, alembic, ops tools) — plan decision 1,
docs/plans/2026-09-28-psycopg3-migration-plan.md.
"""

from __future__ import annotations

import psycopg
import pytest
from sqlalchemy import create_engine, text

from foms.services.db_url_resolver import (
    postgresql_connect_kwargs_from_url,
    sqlalchemy_url,
)

_ONE_PARAM_TWO_TYPES = "SELECT CAST(%(d)s AS TEXT), CAST(%(d)s AS JSONB)"


@pytest.fixture(scope="module")
def lane_dsn(pg_admin_url) -> str:
    return pg_admin_url.render_as_string(hide_password=False)


def test_server_side_binding_rejects_one_param_used_as_two_types(lane_dsn) -> None:
    """Negative control: psycopg's default cursor really does fail on this SQL."""
    with psycopg.connect(**postgresql_connect_kwargs_from_url(lane_dsn)) as raw:
        with pytest.raises(psycopg.errors.AmbiguousParameter):
            raw.execute(_ONE_PARAM_TWO_TYPES.replace("CAST(%(d)s AS TEXT)", "%(d)s"), {"d": "{}"})


def test_url_built_engine_uses_client_side_binding(lane_dsn) -> None:
    engine = create_engine(sqlalchemy_url(lane_dsn))
    try:
        with engine.connect() as conn:
            assert conn.connection.dbapi_connection.cursor_factory is psycopg.ClientCursor
            row = conn.execute(
                text("SELECT :d, CAST(:d AS JSONB)"), {"d": '{"a": 1}'}
            ).one()
            assert row[0] == '{"a": 1}'
    finally:
        engine.dispose()


def test_string_value_compared_to_integer_column_binds_like_psycopg2(lane_dsn) -> None:
    """``filter_by(id="4445")`` must work: request JSON sends ids as strings.

    SQLAlchemy's psycopg dialect renders bind casts from the *Python value* type
    (``id = '4445'::VARCHAR`` → ``integer = character varying``), which psycopg2 never did.
    2026-09-29 production: every AS visit-date save on /api/update_order_field was 500.
    """
    from sqlalchemy import Column, Integer, MetaData, Table, select

    t = Table("bind_cast_probe", MetaData(), Column("id", Integer, primary_key=True))
    engine = create_engine(sqlalchemy_url(lane_dsn))
    try:
        with engine.begin() as conn:
            t.create(conn)
            conn.execute(t.insert(), [{"id": 4445}])
            got = conn.execute(select(t.c.id).where(t.c.id == "4445")).scalar_one()
            assert got == 4445
            t.drop(conn)
        # A dialect subclass that forgets this runs with SQL compilation caching off.
        assert engine.dialect.supports_statement_cache is True
        assert engine.dialect.bind_typing.name == "NONE"
    finally:
        engine.dispose()
