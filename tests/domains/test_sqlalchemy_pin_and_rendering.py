"""SQLAlchemy stays on an exact 2.0.x pin, and JSON paths keep the SQL shape our indexes match.

- SQLAlchemy 2.1 was released 2026-09-24; a loose pin or ``pip install -U`` would jump to it
  (DISTINCT ON / JSON behaviour changes). Upgrades are deliberate, one exact version at a time
  (plan: docs/plans/2026-09-29-sqlalchemy-2-0-54-upgrade-plan.md).
- 2.0.42 renders *JSONB-typed* paths on PostgreSQL 14+ as ``col['k']``. FOMS JSON columns are
  ``JSON().with_variant(JSONB, 'postgresql')`` and must keep ``->`` / ``->>`` because partial
  and expression indexes (e.g. ``ix_external_order_link_dispatch_pending``) are written in
  that form and PostgreSQL only uses an index whose expression matches.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
_PIN = re.compile(r"^SQLAlchemy==2\.0\.\d+\s*$", re.I | re.M)
_ANY_SQLALCHEMY = re.compile(r"^SQLAlchemy\b.*$", re.I | re.M)


def test_requirements_pin_sqlalchemy_to_one_exact_2_0_release() -> None:
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    lines = _ANY_SQLALCHEMY.findall(text)
    assert len(lines) == 1, lines
    assert _PIN.match(lines[0]), f"SQLAlchemy must be pinned as ==2.0.N, got {lines[0]!r}"
    # negative controls
    assert not _PIN.match("SQLAlchemy>=2.0.54")
    assert not _PIN.match("SQLAlchemy==2.1.1")


def _pg17():
    dialect = postgresql.dialect()
    dialect.server_version_info = (17, 0)
    return dialect


def test_json_column_paths_render_as_arrow_operators_on_pg17() -> None:
    from models import Order

    sql = str(Order.structured_data["a"]["b"].as_string().compile(dialect=_pg17()))
    assert "->" in sql and "->>" in sql, sql
    assert "[" not in sql, sql


def test_designer_jsonb_variant_paths_render_as_arrow_operators_on_pg17() -> None:
    from foms.persistence.designer.models import DesignerAIRun

    sql = str(DesignerAIRun.input_json["a"].as_string().compile(dialect=_pg17()))
    assert "->>" in sql and "[" not in sql, sql
