"""문장으로 고치기 저장(설계서 2026-11-18 3절 · 11절) — 마이그레이션 ``brain_03`` ↔ ORM · 머리 하나 · 빈 SQLite 왕복 · 상태 목록.

합성 값만.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, create_engine, inspect
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError

from db import Base, db_session
from foms.persistence.brain import models as brain_models
from foms.persistence.brain.models import BrainChange, BrainChangeRequest
from foms.services.brain import change_request_store as store

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "brain_03_change_requests.py"


def _load():
    spec = importlib.util.spec_from_file_location("brain_03_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_brain_03_chains_onto_graft_00_and_keeps_one_head():
    module = _load()
    assert (module.revision, module.down_revision) == ("brain_03", "graft_00")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1 and "brain_03" in {rev.revision for rev in script.walk_revisions("base", heads[0])}


def test_brain_03_matches_the_models():
    module = _load()
    table = Base.metadata.tables[module.TABLE]
    assert [col.name for col in table.columns] == ["id", *(n for n, *_ in module.COLUMNS)]
    assert not table.foreign_keys  # 사람 번호 칸에 FK 없음
    for name, type_, nullable, default in module.COLUMNS:
        column = table.c[name]
        assert column.nullable is nullable and type(column.type) is type(type_), name
        assert getattr(column.type, "length", None) == getattr(type_, "length", None), name
        assert (column.server_default is not None) == (default is not None), name
    checks = {k.name: str(k.sqltext) for k in table.constraints if isinstance(k, CheckConstraint)}
    assert checks == {module.CHECK_NAME: module.in_check("status", module.REQUEST_STATUSES)}
    indexes = {i.name: tuple(c.name for c in i.columns) for i in table.indexes}
    assert indexes == dict(module.INDEXES)
    changes = Base.metadata.tables[module.CHANGE_TABLE]
    name, type_, nullable = module.CHANGE_COLUMN
    assert changes.c[name].nullable is nullable and type(changes.c[name].type) is type(type_)
    assert {i.name: tuple(c.name for c in i.columns) for i in changes.indexes}[module.CHANGE_INDEX[0]] == \
        module.CHANGE_INDEX[1]


def test_status_names_are_one_list():
    module = _load()
    assert brain_models.REQUEST_STATUSES == module.REQUEST_STATUSES == tuple(store.STATUS_LABELS)


def test_brain_03_upgrade_then_downgrade_runs_on_an_empty_sqlite():
    """마이그레이션 파일을 빈 SQLite 에서 실제로 돌린다(brain_changes 는 칸 둘만 둔 합성 표)."""
    module = _load()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        conn.execute(sql_text("CREATE TABLE brain_changes (id INTEGER PRIMARY KEY, op VARCHAR(16))"))
        module.upgrade()
        assert "brain_change_requests" in set(inspect(conn).get_table_names())
        assert "request_id" in {c["name"] for c in inspect(conn).get_columns("brain_changes")}
        insert = sql_text("INSERT INTO brain_change_requests (created_by, layer_scope, masked_text, status) "
                          "VALUES (1, 'all', '합성 문장', :status)")
        conn.execute(insert, {"status": "ready"})
        with pytest.raises(IntegrityError):
            conn.execute(insert, {"status": "nope"})
        module.downgrade()
        assert "brain_change_requests" not in set(inspect(conn).get_table_names())
        assert "request_id" not in {c["name"] for c in inspect(conn).get_columns("brain_changes")}


def test_orm_defaults_and_empty_request_id(app):
    row = BrainChangeRequest(created_by=1, layer_scope="all", masked_text="합성 문장", status="analyzing")
    db_session.add(row)
    db_session.flush()
    assert isinstance(row.created_at, datetime.datetime) and row.bundle is None and row.decided_at is None
    change = BrainChange(op="update", item_key="common/x", grade="A", status="open", proposed_by="user:1")
    db_session.add(change)
    db_session.flush()
    assert change.request_id is None  # 지금 줄은 빈 값 그대로
    db_session.rollback()
