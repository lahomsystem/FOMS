"""Guardrails: tests must never drop or reset PostgreSQL."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

POSTGRES_DIALECTS = frozenset({"postgresql", "postgres"})
VISUAL_SQLITE_DIR = Path(__file__).resolve().parent / "visual"


def is_postgresql_url(db_url: str) -> bool:
    """
    Return True when the URL targets PostgreSQL.

    Args:
        db_url: SQLAlchemy database URL (DATABASE_URL).

    Returns:
        True for postgresql/postgres drivers; False for empty or other backends.
    """
    if not db_url or not db_url.strip():
        return False
    try:
        dialect = make_url(db_url).drivername.split("+", 1)[0].lower()
    except Exception:
        return False
    return dialect in POSTGRES_DIALECTS


def assert_not_postgresql(db_url: str, *, context: str) -> None:
    """
    Fail the test session when DATABASE_URL points at PostgreSQL.

    Args:
        db_url: Active DATABASE_URL value.
        context: Human-readable caller label for the error message.
    """
    if is_postgresql_url(db_url):
        pytest.fail(
            f"{context}: PostgreSQL DATABASE_URL is blocked. "
            "Tests must not connect to, drop, truncate, or reset PostgreSQL. "
            "Unset DATABASE_URL or use sqlite (e.g. sqlite:///:memory: or "
            "sqlite:///tests/visual/visual_local.sqlite for visual tests)."
        )


def resolve_sqlite_file_path(db_url: str) -> Path | None:
    """
    Return absolute path for a file-backed SQLite URL.

    Args:
        db_url: SQLAlchemy database URL.

    Returns:
        Absolute path, or None for :memory: and non-sqlite backends.
    """
    url = make_url(db_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    db_path = Path(url.database)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    return db_path.resolve()


def assert_visual_test_database(db_url: str) -> None:
    """
    Restrict visual regression tests to throwaway SQLite under tests/visual/.

    Args:
        db_url: DATABASE_URL before app import in visual fixtures.
    """
    assert_not_postgresql(db_url, context="Visual regression tests")
    if ":memory:" in db_url:
        pytest.fail(
            "Visual tests require file-backed SQLite. "
            "Set DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite"
        )
    db_path = resolve_sqlite_file_path(db_url)
    if db_path is None:
        pytest.fail(
            "Visual tests require file-backed SQLite under tests/visual/. "
            f"Got DATABASE_URL={db_url!r}"
        )
    try:
        db_path.relative_to(VISUAL_SQLITE_DIR.resolve())
    except ValueError:
        pytest.fail(
            "Visual tests may only reset SQLite files under tests/visual/. "
            f"Resolved path: {db_path}"
        )


def assert_safe_for_schema_reset(db_url: str, *, context: str) -> None:
    """
    Block metadata drop/create against PostgreSQL (defense in depth).

    Args:
        db_url: Active DATABASE_URL value.
        context: Human-readable caller label.
    """
    assert_not_postgresql(db_url, context=context)
