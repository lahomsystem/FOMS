"""Database URL environment resolution helpers.

This module is also the single source of the PostgreSQL DBAPI driver. A bare
``postgresql://`` URL means psycopg2 in SQLAlchemy 2.0 but psycopg (3) in 2.1, so every
engine in the repo goes through :func:`sqlalchemy_url` and every raw DBAPI connection
through :func:`postgres_dbapi_connect` (plan: docs/plans/2026-09-28-psycopg3-migration-plan.md).
"""

import os
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from sqlalchemy import event
from sqlalchemy.engine import Engine

__all__ = [
    "prepare_database_url_env",
    "postgresql_connect_kwargs_from_url",
    "sqlalchemy_url",
    "postgres_dbapi_connect",
    "pg_error_code",
    "PG_SQLALCHEMY_DRIVER",
]

#: psycopg (3). Rollback to psycopg2 = set "psycopg2" here and restore the psycopg2 branch of
#: postgres_dbapi_connect (psycopg2-binary stays installed until plan step 3).
PG_SQLALCHEMY_DRIVER = "psycopg"

_ALLOWED_PG_QUERY_KEYS = frozenset(
    {
        "sslmode",
        "sslrootcert",
        "sslcert",
        "sslkey",
        "channel_binding",
        "connect_timeout",
        "application_name",
        "options",
        "keepalives",
        "keepalives_idle",
        "keepalives_interval",
        "keepalives_count",
    }
)


def _normalize_postgres_scheme(url: str) -> str:
    """Normalize a legacy `postgres://` URL for SQLAlchemy compatibility."""
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def _strip_postgres_driver(url: str) -> str:
    """Turn ``postgres://`` / ``postgresql+<driver>://`` into plain ``postgresql://``."""
    u = _normalize_postgres_scheme(url)
    if u.startswith("postgresql+"):
        _, sep, rest = u.partition("://")
        if sep:
            return "postgresql://" + rest
    return u


def sqlalchemy_url(url: str) -> str:
    """Return ``url`` with the canonical PostgreSQL driver; other URLs (sqlite, empty) unchanged."""
    if not url:
        return url
    u = _strip_postgres_driver(url)
    if not u.startswith("postgresql://"):
        return url
    return f"postgresql+{PG_SQLALCHEMY_DRIVER}://" + u[len("postgresql://"):]


def postgres_dbapi_connect(connect_kwargs: dict[str, Any]) -> Any:
    """Open a raw DBAPI connection with the canonical driver (SQLAlchemy ``creator``, admin tools).

    ``ClientCursor`` keeps psycopg2's client-side parameter binding: the app has ~900 raw
    ``text()`` statements and most tests run on SQLite, so server-side binding differences
    (``:x IS NULL``, parameters in ``SET``, multi-statement strings) would not be caught.
    Client-side cursors also never create prepared statements. psycopg is imported here —
    after app.py's gevent patch — because it picks its wait function at import time.
    """
    import psycopg

    return psycopg.connect(**connect_kwargs, cursor_factory=psycopg.ClientCursor)


@event.listens_for(Engine, "connect")
def _psycopg_client_side_binding(dbapi_connection: Any, _connection_record: Any) -> None:
    """Give every psycopg connection a ``ClientCursor`` — URL-built engines included.

    ``creator`` engines already get it from :func:`postgres_dbapi_connect`, but engines made
    from :func:`sqlalchemy_url` (SIDEFX, cron, alembic, ops tools, the PG test lane) connect
    through SQLAlchemy's own dialect, which would default to server-side binding.
    """
    module = type(dbapi_connection).__module__
    if not module.startswith("psycopg"):
        return
    import psycopg

    if isinstance(dbapi_connection, psycopg.Connection):
        dbapi_connection.cursor_factory = psycopg.ClientCursor


def pg_error_code(error: BaseException) -> str | None:
    """Return the PostgreSQL SQLSTATE of a (SQLAlchemy-wrapped) DBAPI error, if any.

    psycopg exposes it as ``sqlstate``; psycopg2 as ``pgcode`` (no ``sqlstate``).
    """
    orig = getattr(error, "orig", None) or error
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _should_prefer_public_url(host: str | None) -> bool:
    """Prefer Railway public DB URLs from Windows when the host is internal-only."""
    return bool(
        os.name == "nt"
        and host
        and host.endswith(".railway.internal")
    )


def _pg_core_ready(
    host: str | None,
    port: str | None,
    user: str | None,
    database: str | None,
) -> bool:
    """True when PG* vars are enough to build a URL (password may be empty; do not use falsy password in all())."""
    if not host or not port or not database:
        return False
    if user is None:
        return False
    return str(port).isdigit()


def _reencode_postgres_url_credentials(url: str) -> str:
    """
    Re-build postgres URL userinfo with percent-encoding.

    Raw DATABASE_URL from some Windows/Railway CLI paths can trip libpq UTF-8
    handling when credentials contain non-ASCII or odd quoting.
    """
    u = _strip_postgres_driver(url)
    if not u.startswith("postgresql://"):
        return url
    parsed = urlparse(u)
    if not parsed.hostname:
        return url
    username = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password is not None else ""
    userinfo = f"{quote(username, safe='')}:{quote(password, safe='')}"
    host = parsed.hostname
    port_s = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or "/"
    dbname = path[1:] if path.startswith("/") else path
    path_out = f"/{quote(dbname, safe='')}" if dbname else "/"
    out = f"postgresql://{userinfo}@{host}{port_s}{path_out}"
    if parsed.query:
        out += f"?{parsed.query}"
    if parsed.fragment:
        out += f"#{parsed.fragment}"
    return out


def prepare_database_url_env() -> str | None:
    """Resolve and normalize `DATABASE_URL` from Railway/Postgres environment variables."""
    host = os.environ.get("PGHOST")
    port = os.environ.get("PGPORT")
    user = os.environ.get("PGUSER")
    password = os.environ.get("PGPASSWORD")
    database = os.environ.get("PGDATABASE")

    if _should_prefer_public_url(host):
        for key in ("DATABASE_PUBLIC_URL", "RAILWAY_PUBLIC_DATABASE_URL"):
            candidate = os.environ.get(key)
            if candidate:
                normalized = _reencode_postgres_url_credentials(
                    _normalize_postgres_scheme(candidate)
                )
                os.environ["DATABASE_URL"] = normalized
                return normalized

    if _pg_core_ready(host, port, user, database):
        pwd = "" if password is None else password
        resolved = (
            "postgresql://"
            f"{quote(user, safe='')}:{quote(pwd, safe='')}"
            f"@{host}:{port}/{quote(database, safe='')}"
        )
        os.environ["DATABASE_URL"] = resolved
        return resolved

    existing = os.environ.get("DATABASE_URL")
    if existing:
        normalized = _normalize_postgres_scheme(existing)
        if os.name == "nt":
            normalized = _reencode_postgres_url_credentials(normalized)
        os.environ["DATABASE_URL"] = normalized
        return normalized

    for key in ("DATABASE_PUBLIC_URL", "RAILWAY_PUBLIC_DATABASE_URL"):
        candidate = os.environ.get(key)
        if candidate:
            normalized = _reencode_postgres_url_credentials(
                _normalize_postgres_scheme(candidate)
            )
            os.environ["DATABASE_URL"] = normalized
            return normalized

    return None


def postgresql_connect_kwargs_from_url(url: str) -> dict[str, Any]:
    """
    Parse a postgresql(+driver) URL into DBAPI ``connect()`` keyword arguments.

    Avoids passing a single libpq connection URI through Windows paths where
    non-ASCII credentials can trigger UnicodeDecodeError inside libpq.
    """
    if not url or not str(url).strip():
        raise ValueError("empty database URL")
    u = _strip_postgres_driver(str(url).strip())
    if not u.startswith("postgresql://"):
        raise ValueError("not a PostgreSQL URL")
    parsed = urlparse(u)
    kw: dict[str, Any] = {}
    if parsed.hostname:
        kw["host"] = parsed.hostname
    if parsed.port is not None:
        kw["port"] = int(parsed.port)
    path = parsed.path or ""
    if path.startswith("/"):
        path = path[1:]
    if path:
        kw["dbname"] = unquote(path)
    if parsed.username:
        kw["user"] = unquote(parsed.username)
    if parsed.password is not None:
        kw["password"] = unquote(parsed.password)
    if parsed.query:
        q = parse_qs(parsed.query, keep_blank_values=True)
        for key, vals in q.items():
            if key not in _ALLOWED_PG_QUERY_KEYS or not vals:
                continue
            val = vals[0]
            if key == "connect_timeout":
                kw[key] = int(val)
            else:
                kw[key] = val
    return kw
