"""PostgreSQL test-lane fixtures (PGTEST-00).

Opt-in real-PostgreSQL lane for the downstream concurrency / lock / SKIP LOCKED
packets. It is dormant unless ``FOMS_TEST_DATABASE_URL`` (or the ``PG*`` env
family) points at a *local* PostgreSQL admin database. When active it creates a
throwaway ``foms_test_<worker>_<uuid>`` database per pytest session, applies the
full app schema, and drops it on teardown.

Schema is applied with ``Base.metadata.create_all`` — not Alembic. Running
``alembic upgrade head`` against an empty database fails on the very first
migration (``aef164da4c43`` does ``add_column('orders')`` with no create-table
ancestor: the schema was historically bootstrapped via ``create_all`` + stamp,
so the migration chain is not runnable from scratch).

Safety: no credentials are hard-coded (the DSN comes from the environment), the
lane refuses any non-local host, and it refuses to CREATE/DROP any database
whose name is not prefixed ``foms_test_``. A stray Railway/production DSN
therefore fails immediately instead of touching a real database.
"""
from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import Session, sessionmaker

TEST_DB_PREFIX = "foms_test_"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class PgLaneSafetyError(RuntimeError):
    """Raised when the PG lane would touch a non-local host or non-test database."""


def assert_local_admin_url(raw_url: str) -> URL:
    """Parse an admin DSN and fail unless it targets a local PostgreSQL host.

    Args:
        raw_url: SQLAlchemy/psycopg2 DSN taken from the environment.

    Returns:
        The parsed SQLAlchemy URL when the host is localhost/127.0.0.1/::1.

    Raises:
        PgLaneSafetyError: host is missing or is not a recognised local host.
    """
    url = make_url(raw_url)
    host = (url.host or "").strip().strip("[]").lower()
    if host not in LOCAL_HOSTS:
        raise PgLaneSafetyError(
            f"PostgreSQL test lane refuses non-local host {host!r}. "
            f"FOMS_TEST_DATABASE_URL host must be one of {sorted(LOCAL_HOSTS)} "
            "(guards against public/Railway databases)."
        )
    return url


def assert_test_db_name(name: str) -> str:
    """Fail unless a database name is a throwaway ``foms_test_`` database.

    Args:
        name: database name about to be CREATEd or DROPped.

    Returns:
        The validated name.

    Raises:
        PgLaneSafetyError: name does not start with ``foms_test_``.
    """
    if not name or not name.startswith(TEST_DB_PREFIX):
        raise PgLaneSafetyError(
            f"PostgreSQL test lane refuses to CREATE/DROP database {name!r}; "
            f"only {TEST_DB_PREFIX!r}-prefixed throwaway databases are allowed."
        )
    return name


def _admin_dsn_from_env() -> str | None:
    """Resolve the admin DSN from FOMS_TEST_DATABASE_URL or the PG* env family.

    Returns:
        A DSN string, or None when no PostgreSQL env is configured (lane skips).
    """
    dsn = os.environ.get("FOMS_TEST_DATABASE_URL", "").strip()
    if dsn:
        return dsn
    host = os.environ.get("PGHOST", "").strip()
    if not host:
        return None
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "")
    port = os.environ.get("PGPORT", "5432")
    dbname = os.environ.get("PGDATABASE", "postgres")
    auth = user if not password else f"{user}:{password}"
    return f"postgresql://{auth}@{host}:{port}/{dbname}"


def _raw_connect(url: URL, dbname: str):
    """Open an autocommit-capable psycopg2 connection for CREATE/DROP DATABASE.

    Args:
        url: validated local admin URL (host/port/credentials source).
        dbname: database to connect to (e.g. the ``postgres`` maintenance DB).

    Returns:
        A live psycopg2 connection (caller owns closing it).
    """
    import psycopg2

    return psycopg2.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        dbname=dbname,
        client_encoding="UTF8",
    )


@pytest.fixture(scope="session")
def pg_admin_url() -> URL:
    """Session admin URL, or skip when the PG lane is not configured.

    Returns:
        Validated local admin URL.

    Raises:
        PgLaneSafetyError: configured DSN targets a non-local host.
    """
    dsn = _admin_dsn_from_env()
    if not dsn:
        pytest.skip("FOMS_TEST_DATABASE_URL not set; PostgreSQL lane is opt-in")
    return assert_local_admin_url(dsn)


@pytest.fixture(scope="session")
def pg_test_database(pg_admin_url: URL) -> Iterator[URL]:
    """Create a throwaway ``foms_test_*`` database, apply schema, drop on teardown.

    xdist-safe: the database name embeds ``PYTEST_XDIST_WORKER`` so parallel
    workers never share a database.

    Yields:
        A ``postgresql+psycopg2`` URL for the per-session test database.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    db_name = assert_test_db_name(f"{TEST_DB_PREFIX}{worker}_{uuid.uuid4().hex[:12]}")
    admin_dbname = pg_admin_url.database or "postgres"

    conn = _raw_connect(pg_admin_url, admin_dbname)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()

    test_url = pg_admin_url.set(drivername="postgresql+psycopg2", database=db_name)

    engine = create_engine(test_url, connect_args={"client_encoding": "utf8"})
    try:
        # Import app so every model module is registered on Base.metadata before
        # create_all (cached no-op when the root conftest already imported it).
        import app  # noqa: F401
        from db import Base

        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()

    try:
        yield test_url
    finally:
        assert_test_db_name(db_name)  # defense in depth before DROP
        conn = _raw_connect(pg_admin_url, admin_dbname)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (db_name,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        finally:
            conn.close()


@pytest.fixture(scope="session")
def pg_engine(pg_test_database: URL):
    """Session-scoped engine on the test database.

    Concurrency tests that need multiple committing transactions should use this
    engine directly (open several connections). Disposed before the database is
    dropped.

    Yields:
        A SQLAlchemy Engine bound to the throwaway test database.
    """
    engine = create_engine(
        pg_test_database,
        connect_args={"client_encoding": "utf8"},
        pool_pre_ping=True,
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def pg_session(pg_engine) -> Iterator[Session]:
    """Per-test ORM session wrapped in a transaction that always rolls back.

    Suitable for single-connection tests. Multi-session concurrency tests should
    use ``pg_engine`` directly, since a rolled-back transaction cannot model
    cross-session SKIP LOCKED / FOR UPDATE contention.

    Yields:
        A SQLAlchemy Session; its transaction is rolled back on teardown.
    """
    connection = pg_engine.connect()
    trans = connection.begin()
    session_local = sessionmaker(bind=connection)
    session = session_local()
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()
