"""Database URL environment resolution helpers."""

import os
from urllib.parse import quote

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
                normalized = _normalize_postgres_scheme(candidate)
                os.environ["DATABASE_URL"] = normalized
                return normalized

    if all([host, port, user, password, database]):
        resolved = (
            "postgresql://"
            f"{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{quote(database, safe='')}"
        )
        os.environ["DATABASE_URL"] = resolved
        return resolved

    existing = os.environ.get("DATABASE_URL")
    if existing:
        normalized = _normalize_postgres_scheme(existing)
        os.environ["DATABASE_URL"] = normalized
        return normalized

    for key in ("DATABASE_PUBLIC_URL", "RAILWAY_PUBLIC_DATABASE_URL"):
        candidate = os.environ.get(key)
        if candidate:
            normalized = _normalize_postgres_scheme(candidate)
            os.environ["DATABASE_URL"] = normalized
            return normalized

    return None
