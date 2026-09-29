"""PostgreSQL 드라이버 정본 계약 — 드라이버 이름은 ``db_url_resolver`` 한 곳에서만 정한다.

드라이버를 적지 않은 ``postgresql://`` 는 SQLAlchemy 2.0 에선 psycopg2, 2.1 에선 psycopg(3) 로
열린다. psycopg2 를 빼거나 SQLAlchemy 를 올리는 순간 SIDEFX·cron·alembic 이 조용히 다른
드라이버로 붙지 않도록, 모든 엔진은 ``sqlalchemy_url()`` 을 거쳐 ``PG_SQLALCHEMY_DRIVER`` 를
명시한다(계획: docs/plans/2026-09-28-psycopg3-migration-plan.md 단계 1).

범위 밖: ``tests/``(레인 픽스처는 상수를 직접 쓴다). 단계 3 에서 psycopg2 를 뺐으므로 psycopg2 사용은
``tests/`` 를 포함한 저장소 전체에서 0 이어야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import foms.services.db_url_resolver as db_url_resolver

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = Path("foms/services/db_url_resolver.py")
_SCAN_DIRS = ("foms", "tools", "scripts", "migrations")
_EXCLUDED_PREFIXES: tuple[str, ...] = ()

_DRIVER_LITERAL = re.compile(r"postgresql\+psycopg")
_ENGINE_CALL = re.compile(r"\b(create_engine|engine_from_config)\(")
_CANONICAL_URL_CALL = re.compile(r"\bsqlalchemy_url\(")


def _in_scope_sources() -> list[tuple[Path, str]]:
    """Return (repo-relative path, text) for app·tool Python files under contract."""
    paths = [p for d in _SCAN_DIRS for p in (ROOT / d).rglob("*.py")]
    paths += list(ROOT.glob("*.py"))
    out: list[tuple[Path, str]] = []
    for path in sorted(set(paths)):
        rel = path.relative_to(ROOT)
        if rel.as_posix().startswith(_EXCLUDED_PREFIXES) or "__pycache__" in rel.parts:
            continue
        out.append((rel, path.read_text(encoding="utf-8")))
    return out


def _driver_literal_offenders(sources: list[tuple[Path, str]]) -> list[str]:
    return [rel.as_posix() for rel, text in sources if _DRIVER_LITERAL.search(text)]


def _engine_builder_offenders(sources: list[tuple[Path, str]]) -> list[str]:
    return [
        rel.as_posix()
        for rel, text in sources
        if _ENGINE_CALL.search(text) and not _CANONICAL_URL_CALL.search(text)
    ]


def test_scanners_catch_a_violation() -> None:
    """Negative control: the scanners must flag a bare driver literal and a bypassing engine."""
    bad = [(Path("tools/ops/bad.py"), 'engine = create_engine("postgresql+psycopg2://u@h/db")\n')]
    assert _driver_literal_offenders(bad) == ["tools/ops/bad.py"]
    assert _engine_builder_offenders(bad) == ["tools/ops/bad.py"]
    good = [(Path("tools/ops/good.py"), "engine = create_engine(sqlalchemy_url(url))\n")]
    assert _driver_literal_offenders(good) == []
    assert _engine_builder_offenders(good) == []


def test_scan_covers_the_known_engine_builders() -> None:
    """Guard against an empty scan: known builders must be inside the scanned set."""
    scanned = {rel.as_posix() for rel, _ in _in_scope_sources()}
    for expected in (
        "db.py",
        "wdcalculator_db.py",
        "migrations/env.py",
        "foms/services/sidefx_worker.py",
        "tools/cron/cleanup_order_drafts.py",
        "tools/ops/purge_audit_logs.py",
    ):
        assert expected in scanned


def test_no_hardcoded_postgres_driver_outside_resolver() -> None:
    assert _driver_literal_offenders(_in_scope_sources()) == []
    ini = (ROOT / "alembic.ini").read_text(encoding="utf-8")
    assert not _DRIVER_LITERAL.search(ini)


def test_every_engine_builder_goes_through_sqlalchemy_url() -> None:
    assert _engine_builder_offenders(_in_scope_sources()) == []


def test_dbapi_driver_is_imported_only_by_resolver_in_app_code() -> None:
    """App code (foms/ + root modules) opens raw connections only via postgres_dbapi_connect()."""
    offenders = [
        rel.as_posix()
        for rel, text in _in_scope_sources()
        if (rel.parts[0] == "foms" or len(rel.parts) == 1)
        and rel != RESOLVER
        and re.search(r"^\s*(import psycopg|from psycopg)", text, flags=re.M)
    ]
    assert offenders == []


def test_sqlstate_attribute_is_read_only_by_resolver() -> None:
    """psycopg2=``pgcode`` · psycopg=``sqlstate`` — callers use pg_error_code()."""
    offenders = [
        rel.as_posix()
        for rel, text in _in_scope_sources()
        if rel != RESOLVER and re.search(r"\bpgcode\b|\bsqlstate\b", text)
    ]
    assert offenders == []


def _engine_from_sidefx() -> object:
    from foms.services.sidefx_worker import make_engine_from_env

    return make_engine_from_env()


def _engine_from_cleanup_cron() -> object:
    from tools.cron.cleanup_order_drafts import _make_session

    session, engine = _make_session()
    session.close()
    return engine


def _engine_from_purge_audit_logs() -> object:
    from tools.ops.purge_audit_logs import _make_engine

    return _make_engine()


def _engine_from_purge_mutation_receipts() -> object:
    from tools.ops.purge_order_mutation_receipts import _make_engine

    return _make_engine()


def _engine_from_purge_sidefx_outbox() -> object:
    from tools.ops.purge_domain_side_effect_outbox import _make_engine

    return _make_engine()


@pytest.mark.parametrize(
    "build",
    [
        _engine_from_sidefx,
        _engine_from_cleanup_cron,
        _engine_from_purge_audit_logs,
        _engine_from_purge_mutation_receipts,
        _engine_from_purge_sidefx_outbox,
    ],
    ids=["sidefx", "cron-cleanup", "cron-purge-audit", "cron-purge-receipts", "sidefx-retention"],
)
def test_production_bare_url_builders_pin_the_canonical_driver(monkeypatch, build) -> None:
    """Railway gives ``postgres://`` with no driver; each production builder must pin ours.

    ``create_engine`` does not connect, so an unreachable port is fine.
    """
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@127.0.0.1:1/foms")
    engine = build()
    try:
        assert engine.url.drivername == f"postgresql+{db_url_resolver.PG_SQLALCHEMY_DRIVER}"
    finally:
        engine.dispose()


def test_psycogreen_is_gone_because_psycopg_cooperates_with_gevent_itself() -> None:
    """psycogreen only patched psycopg2; with psycopg (3) it is dead weight and misleading."""
    assert "psycogreen" not in (ROOT / "requirements.txt").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+psycogreen", app_source, flags=re.M)


def test_dbapi_connections_use_client_side_binding(monkeypatch) -> None:
    """Plan decision 1: ClientCursor keeps psycopg2's binding semantics for ~900 raw text() SQL."""
    import psycopg

    seen: dict = {}

    def fake_connect(**kwargs):
        seen.update(kwargs)
        return "connection"

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    assert db_url_resolver.postgres_dbapi_connect({"host": "h", "dbname": "d"}) == "connection"
    assert seen["cursor_factory"] is psycopg.ClientCursor
    assert seen["host"] == "h" and seen["dbname"] == "d"


def test_canonical_dialect_keeps_sql_compilation_cache_and_plain_binds() -> None:
    """The registered psycopg dialect subclass must (a) keep SQLAlchemy's compiled-SQL cache
    and (b) render no Python-type bind casts.

    SQLAlchemy reads ``supports_statement_cache`` from the class's own ``__dict__``; the
    2026-09-29 hotfix subclass (bind_typing NONE) omitted it, so web/worker/SIDEFX recompiled
    every statement (warning ``cprf``; local compile x300: 300ms vs 100ms with the cache).
    """
    import warnings

    from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select, exc

    class _NoFlag(db_url_resolver.PGDialect_psycopg_plain_binds.__mro__[1]):  # negative control
        pass

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", exc.SAWarning)
        assert _NoFlag()._supports_statement_cache is False

    engine = create_engine(db_url_resolver.sqlalchemy_url("postgres://u:p@127.0.0.1:1/foms"))
    try:
        dialect = engine.dialect
        assert isinstance(dialect, db_url_resolver.PGDialect_psycopg_plain_binds)
        with warnings.catch_warnings():
            warnings.simplefilter("error", exc.SAWarning)
            assert dialect._supports_statement_cache is True
        t = Table("probe", MetaData(), Column("id", Integer, primary_key=True))
        sql = str(select(t.c.id).where(t.c.id == "4445").compile(dialect=dialect))
        assert "::" not in sql
    finally:
        engine.dispose()


def test_migrations_leave_the_transaction_with_autocommit_block_not_a_sql_commit() -> None:
    """``execute(text("COMMIT"))`` then CONCURRENTLY DDL only worked because psycopg2 did not
    track transaction state; psycopg (3) sees the COMMIT and opens a new BEGIN, so the DDL fails.
    Migrations use ``op.get_context().autocommit_block()`` instead (driver independent)."""
    sql_commit = re.compile(r"execute\(\s*(sa\.)?text\(\s*['\"]\s*COMMIT\s*['\"]\s*\)\s*\)")
    assert sql_commit.search('conn.execute(sa.text("COMMIT"))')  # negative control
    offenders = [
        path.name
        for path in sorted((ROOT / "migrations" / "versions").glob("*.py"))
        if sql_commit.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


_PSYCOPG2_USE = re.compile(r"^\s*(import|from)\s+psycopg2\b|\bpsycopg2\.(connect|extras)", re.M)


def test_psycopg2_is_gone_from_code_tests_and_requirements() -> None:
    """Plan step 3: every direct psycopg2 user moved to psycopg; the package is not installed."""
    assert _PSYCOPG2_USE.search("import psycopg2\n")  # negative control
    assert _PSYCOPG2_USE.search("conn = psycopg2.connect(dsn)")
    paths = [p for d in (*_SCAN_DIRS, "tests") for p in (ROOT / d).rglob("*.py")] + list(ROOT.glob("*.py"))
    offenders = sorted(
        path.relative_to(ROOT).as_posix()
        for path in set(paths)
        if "__pycache__" not in path.parts
        and path.resolve() != Path(__file__).resolve()
        and _PSYCOPG2_USE.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == []
    assert "psycopg2" not in (ROOT / "requirements.txt").read_text(encoding="utf-8")


_TUPLE_IN_PLACEHOLDER = re.compile(r"\bIN\s+%(\(\w+\))?s\b", re.I)


def test_no_tuple_placeholder_after_in() -> None:
    """psycopg2 expanded a Python tuple into ``IN (a, b)``; psycopg sends it as one quoted
    literal, so ``IN %(x)s`` is a syntax error at runtime. Pass a list with ``= ANY(%(x)s)``
    or ``<> ALL(%(x)s)`` instead (found by the PG lane in plan step 3)."""
    assert _TUPLE_IN_PLACEHOLDER.search("WHERE s NOT IN %(closed)s")  # negative control
    assert _TUPLE_IN_PLACEHOLDER.search("WHERE id in %s")
    assert not _TUPLE_IN_PLACEHOLDER.search("WHERE s = ANY(%(closed)s)")
    offenders = [
        rel.as_posix() for rel, text in _in_scope_sources() if _TUPLE_IN_PLACEHOLDER.search(text)
    ]
    assert offenders == []
