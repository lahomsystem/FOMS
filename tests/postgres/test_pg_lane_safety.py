"""Safety-guard proof for the PostgreSQL lane (PGTEST-00).

Pure unit tests — no database connection — so they run in every CI job (even
without PostgreSQL configured) and prove the lane refuses non-local hosts and
non-``foms_test_`` databases *before* any CREATE/DROP is attempted.
"""
from __future__ import annotations

import pytest

from tests.postgres.conftest import (
    PgLaneSafetyError,
    assert_local_admin_url,
    assert_test_db_name,
)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://postgres:pw@db.railway.app:5432/railway",
        "postgresql://u:p@containers-us-west-1.railway.app:5432/postgres",
        "postgresql://u:p@10.0.0.5:5432/postgres",
        "postgresql://u:p@example.com:5432/postgres",
    ],
)
def test_non_local_host_rejected(dsn: str) -> None:
    """A non-local admin DSN fails immediately (no connection attempted)."""
    with pytest.raises(PgLaneSafetyError):
        assert_local_admin_url(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://postgres:placeholder-pw@127.0.0.1:5432/postgres",
        "postgresql://postgres@localhost:5432/postgres",
        "postgresql://postgres@[::1]:5432/postgres",
    ],
)
def test_local_host_accepted(dsn: str) -> None:
    """Loopback hosts are accepted."""
    url = assert_local_admin_url(dsn)
    assert (url.host or "").strip("[]").lower() in {"localhost", "127.0.0.1", "::1"}


@pytest.mark.parametrize(
    "name",
    ["furniture_orders", "postgres", "production", "foms_prod", "template1", ""],
)
def test_non_test_db_name_rejected(name: str) -> None:
    """Only foms_test_* databases may be CREATEd/DROPped."""
    with pytest.raises(PgLaneSafetyError):
        assert_test_db_name(name)


def test_test_db_name_accepted() -> None:
    """A throwaway name passes the guard."""
    assert assert_test_db_name("foms_test_main_abc123") == "foms_test_main_abc123"
