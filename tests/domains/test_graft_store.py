"""접목판 표 셋(설계서 2026-11-14-foms-graft 3.4) — ORM ↔ 마이그레이션 ``graft_00`` 칸 · 꼴 · 색인 · 검사 일치 · 머리 하나 ·
열린 제안 겹침 막기(부분 유일 색인) · 상태 검사 · 마이그레이션이 실제로 올라가고 내려감.

합성 값만 쓴다(손님 글 · 직원 이름 · 금액 없음). 바깥 호출 없음.
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
from sqlalchemy import CheckConstraint, create_engine, func, inspect, select
from sqlalchemy import text as sql_text
from sqlalchemy.exc import IntegrityError

from db import Base, db_session
from foms.persistence.graft import models as graft_models
from foms.persistence.graft.models import AiAgentRun, BrainUsageEvent, ErpActionProposal
from foms.services.erp_actions import registry

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "graft_00_action_proposals_usage_runs.py"
NOW = datetime.datetime(2026, 11, 14, 1, 0)
TABLES = ("erp_action_proposals", "brain_usage_events", "ai_agent_runs")


def _load():
    spec = importlib.util.spec_from_file_location("graft_00_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _where(index, dialect):
    where = index.dialect_options[dialect]["where"]
    return str(where) if where is not None else None


# ── 마이그레이션 ↔ ORM ────────────────────────────────────────────────────
def test_graft_00_chains_onto_prodpart_00_and_keeps_one_head():
    module = _load()
    assert (module.revision, module.down_revision) == ("graft_00", "prodpart_00")
    source = MIGRATION.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()  # 뒤에 새 마이그레이션이 붙어도 graft_00 은 사슬 안에 있어야 한다
    assert len(heads) == 1 and "graft_00" in {rev.revision for rev in script.walk_revisions("base", heads[0])}
    assert script.get_revision("graft_00").down_revision == "prodpart_00"


def test_graft_00_columns_match_the_models():
    module = _load()
    assert tuple(module.COLUMNS) == TABLES
    for name, columns in module.COLUMNS.items():
        table = Base.metadata.tables[name]
        assert [col.name for col in table.columns] == ["id", *(n for n, *_ in columns)], name
        assert not table.foreign_keys, name  # 주문 · 사람 번호 칸에 FK 없음(감사 원장)
        for col_name, type_, nullable, default in columns:
            column = table.c[col_name]
            assert column.nullable is nullable, (name, col_name)
            assert type(column.type) is type(type_), (name, col_name)
            assert getattr(column.type, "length", None) == getattr(type_, "length", None), (name, col_name)
            assert (column.server_default is not None) == (default is not None), (name, col_name)


def test_graft_00_checks_and_indexes_match_the_models():
    module = _load()
    for name in TABLES:
        table = Base.metadata.tables[name]
        checks = {k.name: str(k.sqltext) for k in table.constraints if isinstance(k, CheckConstraint)}
        assert checks == {n: module.in_check(col, vals) for n, col, vals in module.CHECKS[name]}, name
        indexes = {i.name: i for i in table.indexes}
        assert set(indexes) == {n for n, *_ in module.INDEXES[name]}, name
        for index_name, cols, unique, where_sql in module.INDEXES[name]:
            index = indexes[index_name]
            assert tuple(col.name for col in index.columns) == cols and index.unique is unique, index_name
            assert _where(index, "postgresql") == where_sql == _where(index, "sqlite"), index_name


def test_status_names_are_one_list_in_model_migration_and_registry():
    module = _load()
    assert graft_models.PROPOSAL_STATUSES == module.PROPOSAL_STATUSES == registry.STATUSES
    assert graft_models.OPEN_SQL == module.OPEN_SQL == f"status = '{registry.STATUS_OPEN}'"


def test_models_module_puts_the_three_tables_on_base():
    import models

    assert (models.ErpActionProposal, models.BrainUsageEvent, models.AiAgentRun) == (
        ErpActionProposal, BrainUsageEvent, AiAgentRun)
    assert set(TABLES) <= set(Base.metadata.tables)


def test_graft_00_upgrade_then_downgrade_runs_and_its_partial_index_blocks_a_second_open_row():
    """마이그레이션 파일을 빈 SQLite 에서 실제로 돌린다(PostgreSQL 왕복은 tests/postgres/test_migration_chain.py)."""
    module = _load()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        module.upgrade()
        names = set(inspect(conn).get_table_names())
        assert set(TABLES) <= names
        insert = sql_text("INSERT INTO erp_action_proposals (action, proposed_by, level, status, dedupe_key, created_at) "
                          "VALUES ('schedule_construction', 'agent:schedule', 2, :status, 'k', '2026-11-14 01:00:00')")
        conn.execute(insert, {"status": "rejected"})
        conn.execute(insert, {"status": "open"})  # 대조군: 닫힌 줄과 같은 열쇠의 열린 줄은 된다
        with pytest.raises(IntegrityError):
            conn.execute(insert, {"status": "open"})
        module.downgrade()
        assert not set(TABLES) & set(inspect(conn).get_table_names())


# ── ORM 동작(SQLite 레인) ────────────────────────────────────────────────
def _proposal(status="open", key="schedule_construction:7:abc"):
    return ErpActionProposal(action="schedule_construction", proposed_by="agent:schedule", order_id=7, level=2,
                             status=status, dedupe_key=key, params={"date": "2026-11-20", "time": "오전"})


def test_open_dedupe_key_is_unique_only_while_open(app):
    db_session.add_all([_proposal(status="rejected"), _proposal(status="executed"), _proposal()])
    db_session.commit()  # 대조군: 닫힌 줄 둘 + 열린 줄 하나는 같은 열쇠여도 된다
    db_session.add(_proposal())
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
    db_session.add(_proposal(key="schedule_construction:8:abc"))  # 다른 열쇠는 된다
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(ErpActionProposal).where(
        ErpActionProposal.status == "open")) == 2


def test_status_outside_the_list_is_refused(app):
    db_session.add(_proposal(status="approved"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_defaults_fill_times_and_counts(app):
    db_session.add_all([_proposal(),
                        BrainUsageEvent(item_key="erp:order/7", reader="erp_action", ref_kind="proposal", ref_id="1"),
                        AiAgentRun(agent="schedule", steps=[{"tool": "erp.visit.list", "what": "방문", "ms": 3}])])
    db_session.commit()
    proposal = db_session.scalars(select(ErpActionProposal)).one()
    use = db_session.scalars(select(BrainUsageEvent)).one()
    run = db_session.scalars(select(AiAgentRun)).one()
    assert proposal.created_at is not None and use.used_at is not None and run.started_at is not None
    assert run.proposals == 0 and proposal.params == {"date": "2026-11-20", "time": "오전"}
    assert proposal.decided_by is None and proposal.result is None
