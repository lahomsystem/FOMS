"""Database URL environment resolution helpers."""

import os
from urllib.parse import quote, unquote, urlparse

__all__ = ["prepare_database_url_env"]


def _normalize_postgres_scheme(url: str) -> str:
    """Normalize a legacy `postgres://` URL for SQLAlchemy compatibility."""
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


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

    Raw DATABASE_URL from some Windows/Railway CLI paths can trip libpq/psycopg2 UTF-8
    handling when credentials contain non-ASCII or odd quoting.
    """
    u = _normalize_postgres_scheme(url)
    if u.startswith("postgresql+psycopg2://"):
        u = "postgresql://" + u[len("postgresql+psycopg2://") :]
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
