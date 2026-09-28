"""Tests for database URL resolution helpers."""

import foms.services.db_url_resolver as db_url_resolver


def _clear_database_env(monkeypatch) -> None:
    for key in (
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "DATABASE_URL",
        "DATABASE_PUBLIC_URL",
        "RAILWAY_PUBLIC_DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_prepare_database_url_env_normalizes_existing_database_url(monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost/sample")

    resolved = db_url_resolver.prepare_database_url_env()

    assert resolved == "postgresql://user:pass@localhost/sample"
    assert resolved == db_url_resolver.os.environ["DATABASE_URL"]


def test_prepare_database_url_env_builds_url_from_pg_components(monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "sa les")
    monkeypatch.setenv("PGPASSWORD", "p@ss word")
    monkeypatch.setenv("PGDATABASE", "erp/test")

    resolved = db_url_resolver.prepare_database_url_env()

    assert resolved == "postgresql://sa%20les:p%40ss%20word@localhost:5432/erp%2Ftest"
    assert resolved == db_url_resolver.os.environ["DATABASE_URL"]


def test_prepare_database_url_env_builds_url_when_password_empty_string(monkeypatch) -> None:
    """Empty PGPASSWORD must not skip the PG* URL builder (truthy password check was a footgun)."""
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "u")
    monkeypatch.setenv("PGPASSWORD", "")
    monkeypatch.setenv("PGDATABASE", "d")

    resolved = db_url_resolver.prepare_database_url_env()

    assert resolved == "postgresql://u:@localhost:5432/d"
    assert resolved == db_url_resolver.os.environ["DATABASE_URL"]


def test_prepare_database_url_env_builds_url_when_password_env_missing(monkeypatch) -> None:
    """Missing PGPASSWORD key still builds URL with empty password when other PG* vars exist."""
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("PGHOST", "localhost")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "u")
    monkeypatch.setenv("PGDATABASE", "d")

    resolved = db_url_resolver.prepare_database_url_env()

    assert resolved == "postgresql://u:@localhost:5432/d"


def test_prepare_database_url_env_prefers_public_url_when_requested(monkeypatch) -> None:
    _clear_database_env(monkeypatch)
    monkeypatch.setenv("PGHOST", "private.railway.internal")
    monkeypatch.setenv("DATABASE_PUBLIC_URL", "postgres://public:pass@remote/publicdb")
    monkeypatch.setattr(db_url_resolver, "_should_prefer_public_url", lambda host: True)

    resolved = db_url_resolver.prepare_database_url_env()

    assert resolved == "postgresql://public:pass@remote/publicdb"
    assert resolved == db_url_resolver.os.environ["DATABASE_URL"]


def test_postgresql_connect_kwargs_from_url_decodes_userinfo_and_query() -> None:
    kw = db_url_resolver.postgresql_connect_kwargs_from_url(
        "postgresql+psycopg2://u:p%40x@h.example:5432/my%2Fdb?sslmode=require&connect_timeout=8"
    )
    assert kw["host"] == "h.example"
    assert kw["port"] == 5432
    assert kw["dbname"] == "my/db"
    assert kw["user"] == "u"
    assert kw["password"] == "p@x"
    assert kw["sslmode"] == "require"
    assert kw["connect_timeout"] == 8


def test_prepare_database_url_env_returns_none_when_no_candidates_exist(monkeypatch) -> None:
    _clear_database_env(monkeypatch)

    resolved = db_url_resolver.prepare_database_url_env()

    assert resolved is None
    assert "DATABASE_URL" not in db_url_resolver.os.environ


def test_sqlalchemy_url_pins_canonical_driver_for_every_postgres_spelling() -> None:
    expected = f"postgresql+{db_url_resolver.PG_SQLALCHEMY_DRIVER}://u:p@h:5432/db?sslmode=require"
    for raw in (
        "postgres://u:p@h:5432/db?sslmode=require",
        "postgresql://u:p@h:5432/db?sslmode=require",
        "postgresql+psycopg2://u:p@h:5432/db?sslmode=require",
        "postgresql+psycopg://u:p@h:5432/db?sslmode=require",
    ):
        assert db_url_resolver.sqlalchemy_url(raw) == expected


def test_sqlalchemy_url_leaves_non_postgres_urls_alone() -> None:
    for raw in ("", "sqlite://", "sqlite:///tmp/x.sqlite", "mysql://u@h/db"):
        assert db_url_resolver.sqlalchemy_url(raw) == raw


def test_connect_kwargs_accept_any_driver_suffix() -> None:
    kw = db_url_resolver.postgresql_connect_kwargs_from_url("postgresql+psycopg://u:p@h/db")
    assert kw == {"host": "h", "dbname": "db", "user": "u", "password": "p"}


def test_pg_error_code_reads_psycopg_sqlstate_and_psycopg2_pgcode() -> None:
    from types import SimpleNamespace

    assert db_url_resolver.pg_error_code(SimpleNamespace(orig=SimpleNamespace(sqlstate="55P03"))) == "55P03"
    assert db_url_resolver.pg_error_code(SimpleNamespace(orig=SimpleNamespace(pgcode="55P03"))) == "55P03"
    assert db_url_resolver.pg_error_code(SimpleNamespace(pgcode="23505")) == "23505"
    assert db_url_resolver.pg_error_code(ValueError("not a DB error")) is None
