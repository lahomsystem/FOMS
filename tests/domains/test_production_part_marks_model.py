"""PRODPART-00: ``production_part_marks`` 표 · ``users.production_part`` 칸 · 파트 상수 시험(SQLite 레인).

설계 정본: ``docs/specs/2026-11-09-tablet-production-ui_SPEC.md`` §15.3 · §15.7(모델 · 마이그레이션).
PG 레인의 왕복 · 삭제 보존 시험은 ``tests/postgres/test_migration_chain.py``(head 기준 창이라 새 리비전이 저절로
들어간다) · ``tests/postgres/test_delete_retention.py``.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
from typing import Iterator

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from db import Base, db_session
from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.orders.delete_retention import _assert_fk_coverage, _referring_fks
import models
from foms.services.production import part_constants as pc
from models import Order, ProductionPartMark, User

ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "migrations" / "versions" / "prodpart_00_production_part_marks.py"


def _order_kwargs() -> dict:
    return dict(
        received_date="2026-11-13",
        customer_name="파트 시험",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="PRODUCTION",
    )


def _create_order() -> Order:
    order = Order(**_order_kwargs())
    db_session.add(order)
    db_session.commit()
    return order


def _mark(order_id: int, **fields) -> ProductionPartMark:
    values = dict(order_id=order_id, drawing_key="orders/1/drawing/a.png", part="cut", state="NEED")
    values.update(fields)
    return ProductionPartMark(**values)


# --------------------------------------------------------------------------- #
# 표 · 제약
# --------------------------------------------------------------------------- #
def test_insert_and_read_defaults(app):
    order = _create_order()
    db_session.add(_mark(order.id, sheet_id="sheet-1", picked_by_name="김재단"))
    db_session.commit()
    db_session.expire_all()

    row = db_session.query(ProductionPartMark).one()
    assert (row.order_id, row.drawing_key, row.part, row.state) == (order.id, "orders/1/drawing/a.png", "cut", "NEED")
    assert row.sheet_id == "sheet-1"
    assert row.picked_by_name == "김재단"
    assert row.updated_at is not None  # NOT NULL — 넣지 않아도 기본값이 찬다
    assert (row.done_by_user_id, row.done_by_name, row.done_at) == (None, None, None)


def test_one_row_per_drawing_and_part(app):
    order = _create_order()
    db_session.add(_mark(order.id, part="cut"))
    db_session.commit()
    db_session.add(_mark(order.id, part="cut", state="DONE"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_same_drawing_other_part_and_other_drawing_same_part_are_allowed(app):
    """대조군: UNIQUE 는 (주문, 장, 파트) 셋이 같을 때만 막는다 — 파트나 장이 다르면 들어간다."""
    order = _create_order()
    db_session.add_all([
        _mark(order.id, part="cut"),
        _mark(order.id, part="edge"),
        _mark(order.id, part="cut", drawing_key="orders/1/drawing/b.png"),
    ])
    db_session.commit()
    assert db_session.query(ProductionPartMark).count() == 3


@pytest.mark.parametrize("part", ["edge", "assemble", "inspect"])
def test_basic_is_cut_only(app, part):
    order = _create_order()
    db_session.add(_mark(order.id, part=part, state="BASIC"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_basic_on_cut_is_allowed(app):
    """대조군: 재단의 '기본'은 들어간다(위 거부가 BASIC 전체 거부가 아님을 보인다)."""
    order = _create_order()
    db_session.add(_mark(order.id, part="cut", state="BASIC"))
    db_session.commit()
    assert db_session.query(ProductionPartMark).one().state == "BASIC"


@pytest.mark.parametrize("fields", [{"part": "paint"}, {"part": "CUT"}, {"state": "done"}, {"state": "TAKEN"}])
def test_part_and_state_checks_reject_unknown_values(app, fields):
    order = _create_order()
    db_session.add(_mark(order.id, **fields))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("part", pc.PRODUCTION_PART_KEYS)
@pytest.mark.parametrize("state", ["NONE", "NEED", "DONE"])
def test_every_part_accepts_non_basic_states(app, part, state):
    order = _create_order()
    db_session.add(_mark(order.id, part=part, state=state))
    db_session.commit()
    assert db_session.query(ProductionPartMark).count() == 1


# --------------------------------------------------------------------------- #
# FK — 주문 CASCADE · 사용자 SET NULL(공용 SQLite 레인은 FK 를 안 켜므로 따로 켠 메모리 DB)
# --------------------------------------------------------------------------- #
@pytest.fixture
def fk_engine() -> Iterator[Engine]:
    """FK 를 켠 메모리 SQLite 에 같은 스키마를 만든다(ON DELETE DDL 이 실제로 도는지 보려고)."""
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _insert_order_and_user(conn) -> tuple[int, int]:
    order_id = conn.execute(Base.metadata.tables["orders"].insert().values(**_order_kwargs())).inserted_primary_key[0]
    user_id = conn.execute(Base.metadata.tables["users"].insert().values(
        username="cut-kim", password="x", name="김재단", role="STAFF", team="PRODUCTION", production_part="cut",
    )).inserted_primary_key[0]
    return order_id, user_id


def _insert_mark_by(conn, order_id: int, user_id: int) -> None:
    conn.execute(text(
        "INSERT INTO production_part_marks (order_id, drawing_key, part, state, "
        "picked_by_user_id, picked_by_name, done_by_user_id, done_by_name, updated_by_user_id, updated_at) "
        "VALUES (:o, 'k1', 'cut', 'DONE', :u, '김재단', :u, '김재단', :u, CURRENT_TIMESTAMP)"
    ), {"o": order_id, "u": user_id})


def test_deleting_order_removes_marks(fk_engine):
    with fk_engine.begin() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        order_id, user_id = _insert_order_and_user(conn)
        _insert_mark_by(conn, order_id, user_id)
    with fk_engine.begin() as conn:
        conn.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})
    with fk_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM production_part_marks")).scalar() == 0


def test_deleting_user_nulls_user_ids_but_keeps_name_snapshots(fk_engine):
    with fk_engine.begin() as conn:
        order_id, user_id = _insert_order_and_user(conn)
        _insert_mark_by(conn, order_id, user_id)
    with fk_engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    with fk_engine.connect() as conn:
        row = conn.execute(text(
            "SELECT picked_by_user_id, done_by_user_id, updated_by_user_id, picked_by_name, done_by_name, state "
            "FROM production_part_marks"
        )).one()
    assert tuple(row) == (None, None, None, "김재단", "김재단", "DONE")


def test_order_fk_is_cascade_so_delete_retention_accepts_it():
    """하드 삭제(삭제 보존)는 ``orders`` 행을 지운다 — 이 FK 가 CASCADE 여야 FK 검사가 통과하고 줄도 같이 사라진다."""
    assert ("production_part_marks", "order_id", "CASCADE") in _referring_fks()
    _assert_fk_coverage()  # 미처리 NOT NULL 참조자가 있으면 raise


def test_user_fks_are_set_null():
    table = ProductionPartMark.__table__
    user_fks = {fk.parent.name: (fk.ondelete or "").upper() for fk in table.foreign_keys if fk.column.table.name == "users"}
    assert user_fks == {"picked_by_user_id": "SET NULL", "done_by_user_id": "SET NULL", "updated_by_user_id": "SET NULL"}


# --------------------------------------------------------------------------- #
# users.production_part
# --------------------------------------------------------------------------- #
def test_user_production_part_check(app):
    db_session.add(User(username="part-bad", password="x", role="STAFF", team="PRODUCTION", production_part="paint"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("part", [None, *pc.PRODUCTION_PART_KEYS])
def test_user_production_part_accepts_null_and_four_keys(app, part):
    db_session.add(User(username=f"part-{part}", password="x", role="STAFF", team="PRODUCTION", production_part=part))
    db_session.commit()
    assert db_session.query(User).filter_by(username=f"part-{part}").one().production_part == part


def test_user_to_dict_has_production_part():
    assert User(username="u", production_part="edge").to_dict()["production_part"] == "edge"


# --------------------------------------------------------------------------- #
# 상수 · 계정 파트 판정
# --------------------------------------------------------------------------- #
def test_part_keys_match_production_step_defs():
    """파트 key = 주문 공정 칸 key(같은 순서) — 공정 칸 동기화(§15.5)가 key 하나로 잇는다."""
    assert pc.PRODUCTION_PART_DEFS == _PRODUCTION_STEP_DEFS
    assert pc.PRODUCTION_PART_KEYS == ("cut", "edge", "assemble", "inspect")


def _check_values(sql: str) -> tuple[str, ...]:
    return tuple(re.findall(r"'([^']+)'", sql))


def test_model_check_sql_matches_constants():
    """models 는 순환 때문에 상수 모듈을 못 부른다 — CHECK 글의 값이 상수와 같은지 여기서 고정한다."""
    assert _check_values(models.PRODUCTION_PART_CHECK_VALUES_SQL) == pc.PRODUCTION_PART_KEYS
    assert _check_values(models.PRODUCTION_PART_MARK_STATE_CHECK_VALUES_SQL) == pc.PART_MARK_STATES
    assert pc.BASIC_ALLOWED_PART == "cut"


def test_badge_classes_have_no_gray_slot():
    assert set(pc.PART_BADGE_CLASSES) == {"need", "taken", "done", "basic", "wait"}
    assert len(set(pc.PART_BADGE_CLASSES.values())) == 5


class _U:
    def __init__(self, team, part):
        self.team = team
        self.production_part = part


@pytest.mark.parametrize(
    ("team", "part", "expected"),
    [
        ("PRODUCTION", "cut", "cut"),
        (" production ", "inspect", "inspect"),
        ("PRODUCTION", None, None),
        ("PRODUCTION", "paint", None),
        ("CS", "cut", None),
        ("SALES", "edge", None),
        ("ACCOUNTING", "cut", None),
        (None, "cut", None),
    ],
)
def test_account_production_part_is_none_outside_production_team(team, part, expected):
    assert pc.account_production_part(_U(team, part)) == expected


def test_account_production_part_none_user():
    assert pc.account_production_part(None) is None


@pytest.mark.parametrize(("raw", "expected"), [("", None), (None, None), ("  ", None), ("cut", "cut"), (" Edge ", "edge")])
def test_normalize_production_part(raw, expected):
    assert pc.normalize_production_part(raw) == expected


@pytest.mark.parametrize("raw", ["paint", "재단", "cut;drop"])
def test_normalize_production_part_rejects_unknown(raw):
    with pytest.raises(ValueError):
        pc.normalize_production_part(raw)


def test_production_part_for_team_clears_outside_production():
    assert pc.production_part_for_team("PRODUCTION", "cut") == "cut"
    assert pc.production_part_for_team("CS", "cut") is None
    assert pc.production_part_for_team("", "cut") is None


def test_production_part_label():
    assert [pc.production_part_label(k) for k in pc.PRODUCTION_PART_KEYS] == ["재단", "엣지", "조립", "검수"]
    assert pc.production_part_label(None) is None
    assert pc.production_part_label("paint") is None


# --------------------------------------------------------------------------- #
# 마이그레이션
# --------------------------------------------------------------------------- #
def _load_migration():
    spec = importlib.util.spec_from_file_location("prodpart_00_unit", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_is_single_head_and_chains_from_previous_head():
    module = _load_migration()
    assert module.revision == "prodpart_00"
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert "prodpart_00" in {rev.revision for rev in script.walk_revisions("base", heads[0])}
    assert script.get_revision("prodpart_00").down_revision == module.down_revision == "chat_drop_01"


def test_migration_check_snapshots_equal_model_ddl():
    """마이그레이션의 CHECK · UNIQUE 이름 · 글이 models 와 글자 단위로 같다(create_all 레인 ↔ alembic 레인)."""
    module = _load_migration()
    table = ProductionPartMark.__table__
    model_checks = {c.name: str(c.sqltext) for c in table.constraints if c.name and c.name.startswith("ck_")}
    assert model_checks == {
        module.MARKS_PART_CHECK: module.MARKS_PART_CHECK_SQL,
        module.MARKS_STATE_CHECK: module.MARKS_STATE_CHECK_SQL,
        module.MARKS_BASIC_CHECK: module.MARKS_BASIC_CHECK_SQL,
    }
    uniques = {c.name: tuple(col.name for col in c.columns) for c in table.constraints if c.name and c.name.startswith("uq_")}
    assert uniques == {module.MARKS_UNIQUE: ("order_id", "drawing_key", "part")}
    user_checks = {c.name: str(c.sqltext) for c in User.__table__.constraints if c.name == module.USERS_CHECK}
    assert user_checks == {module.USERS_CHECK: module.USERS_CHECK_SQL}


def test_migration_columns_match_model_columns():
    """새 표 칸 이름 · NULL 여부가 models 와 같다(PG 왕복 지문이 보는 축의 SQLite 쪽 선검사)."""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    for column in ProductionPartMark.__table__.columns:
        assert f"'{column.name}'" in source, column.name
    assert "op.add_column('users', sa.Column('production_part', sa.String(length=16), nullable=True))" in source
    assert User.__table__.c.production_part.nullable is True
    assert User.__table__.c.production_part.type.length == 16
