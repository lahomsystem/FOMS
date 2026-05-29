"""Unit tests for PostgreSQL test guardrails."""

from __future__ import annotations

import pytest

from tests.postgres_guard import (
    assert_not_postgresql,
    assert_visual_test_database,
    is_postgresql_url,
    resolve_sqlite_file_path,
)


class TestIsPostgresqlUrl:
    """is_postgresql_url dialect detection."""

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://user:pass@localhost/foms",
            "postgresql+psycopg2://user:pass@host/db",
            "postgres://user:pass@localhost/db",
        ],
    )
    def test_postgres_urls(self, url: str) -> None:
        assert is_postgresql_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "sqlite:///:memory:",
            "sqlite:///tests/visual/visual_local.sqlite",
        ],
    )
    def test_non_postgres_urls(self, url: str) -> None:
        assert is_postgresql_url(url) is False


class TestAssertNotPostgresql:
    """assert_not_postgresql fails fast on PostgreSQL."""

    def test_blocks_postgres(self) -> None:
        with pytest.raises(pytest.fail.Exception):
            assert_not_postgresql(
                "postgresql://user:pass@localhost/foms",
                context="unit test",
            )

    def test_allows_sqlite(self) -> None:
        assert_not_postgresql("sqlite:///:memory:", context="unit test")


class TestAssertVisualTestDatabase:
    """Visual tests only allow throwaway SQLite under tests/visual/."""

    def test_blocks_postgres(self) -> None:
        with pytest.raises(pytest.fail.Exception):
            assert_visual_test_database("postgresql://localhost/foms")

    def test_blocks_memory(self) -> None:
        with pytest.raises(pytest.fail.Exception):
            assert_visual_test_database("sqlite:///:memory:")

    def test_blocks_sqlite_outside_visual_dir(self) -> None:
        with pytest.raises(pytest.fail.Exception):
            assert_visual_test_database("sqlite:///tmp/other.sqlite")

    def test_allows_visual_sqlite(self) -> None:
        assert_visual_test_database("sqlite:///tests/visual/visual_local.sqlite")


class TestResolveSqliteFilePath:
    """resolve_sqlite_file_path returns absolute paths for file SQLite."""

    def test_memory_returns_none(self) -> None:
        assert resolve_sqlite_file_path("sqlite:///:memory:") is None

    def test_file_returns_path(self) -> None:
        path = resolve_sqlite_file_path("sqlite:///tests/visual/visual_local.sqlite")
        assert path is not None
        assert path.name == "visual_local.sqlite"
