"""PostgreSQL 드라이버 정본 계약 — 드라이버 이름은 ``db_url_resolver`` 한 곳에서만 정한다.

드라이버를 적지 않은 ``postgresql://`` 는 SQLAlchemy 2.0 에선 psycopg2, 2.1 에선 psycopg(3) 로
열린다. psycopg2 를 빼거나 SQLAlchemy 를 올리는 순간 SIDEFX·cron·alembic 이 조용히 다른
드라이버로 붙지 않도록, 모든 엔진은 ``sqlalchemy_url()`` 을 거쳐 ``PG_SQLALCHEMY_DRIVER`` 를
명시한다(계획: docs/plans/2026-09-28-psycopg3-migration-plan.md 단계 1).

범위 밖: ``tests/``(레인 픽스처는 상수를 직접 쓴다), ``scripts/migrations/``(일회성 이관
스크립트 — 계획 §8-2 결정 대기).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import foms.services.db_url_resolver as db_url_resolver

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = Path("foms/services/db_url_resolver.py")
_SCAN_DIRS = ("foms", "tools", "scripts", "migrations")
_EXCLUDED_PREFIXES = ("scripts/migrations/",)

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
