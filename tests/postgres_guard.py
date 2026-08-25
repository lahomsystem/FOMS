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


def assert_engine_not_postgresql(engine: object, *, context: str) -> None:
    """
    Block schema operations when the **live engine** targets PostgreSQL.

    환경변수 문자열만 보는 :func:`assert_not_postgresql` 로는 못 막는 구멍이 있다.
    ``db.py`` 는 ``DATABASE_URL`` 이 없으면 로컬 Postgres 하드코딩 fallback 으로 붙는다.
    어떤 파일이 ``tests/conftest.py`` 보다 **먼저** ``db`` 를 import 하면 엔진은 그 시점에
    Postgres 로 묶이고, 그 뒤 conftest 가 ``setdefault`` 로 env 에 sqlite 를 넣는 순간
    문자열 가드는 "sqlite 니까 안전"으로 통과한다 — 그리고 티어다운 ``drop_all`` 이
    로컬 dev DB 를 드롭한다. 2026-08-23 실제로 그렇게 테이블 86개가 날아갔다
    (스키마는 재생성했으나 행 데이터는 복구 불가).

    그래서 판정 대상은 env 문자열이 아니라 **엔진이 실제로 붙은 곳**이다.

    Args:
        engine: SQLAlchemy Engine (``url.drivername`` 을 읽는다).
        context: Human-readable caller label.
    """
    drivername = getattr(getattr(engine, "url", None), "drivername", "") or ""
    dialect = drivername.split("+", 1)[0].lower()
    if dialect in POSTGRES_DIALECTS:
        pytest.fail(
            f"{context}: live engine is bound to PostgreSQL "
            f"({getattr(engine, 'url', '?')!r}). Schema drop/create is blocked. "
            "This usually means a module imported `db` before tests/conftest.py set "
            "DATABASE_URL — check import order in the file you just added."
        )


def assert_safe_for_schema_reset(db_url: str, *, context: str,
                                 engine: object | None = None) -> None:
    """
    Block metadata drop/create against PostgreSQL (defense in depth).

    Args:
        db_url: Active DATABASE_URL value.
        context: Human-readable caller label.
        engine: 살아 있는 엔진. 주면 문자열이 아니라 **실제 접속 대상**으로도 판정한다
            (import 순서가 어긋나면 문자열만으로는 못 막는다 —
            :func:`assert_engine_not_postgresql` 참고).
    """
    assert_not_postgresql(db_url, context=context)
    if engine is not None:
        assert_engine_not_postgresql(engine, context=context)
