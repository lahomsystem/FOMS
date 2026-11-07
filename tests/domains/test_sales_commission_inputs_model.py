"""FCOMM-01: ``sales_commission_inputs`` 표(회계팀 입력 — 시공비 · 지정 요율) 모델 시험(SQLite 레인).

설계 정본: ``docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md`` §4.2.
PG 레인의 왕복 · 삭제 보존 시험은 ``tests/postgres/test_migration_chain.py`` · ``test_delete_retention.py``.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import Base, db_session
from foms.services.orders.delete_retention import _assert_fk_coverage, _referring_fks
from models import Order, SalesCommissionInput, User

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _order_kwargs() -> dict:
    return dict(
        received_date="2026-11-06",
        customer_name="수수료 시험",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
    )


def _create_order() -> Order:
    order = Order(**_order_kwargs())
    db_session.add(order)
    db_session.commit()
    return order


def _create_user() -> User:
    user = User(username="fcomm-acct", password="x", role="STAFF", name="회계", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def test_insert_and_read_defaults(app):
    order = _create_order()
    user = _create_user()
    db_session.add(SalesCommissionInput(
        order_id=order.id, install_cost=350000, rate_override_bp=1500, note="현장 추가", updated_by_user_id=user.id,
    ))
    db_session.commit()
    db_session.expire_all()

    row = db_session.get(SalesCommissionInput, order.id)
    assert row is not None
    assert (row.install_cost, row.rate_override_bp, row.note) == (350000, 1500, "현장 추가")
    assert row.version == 1
    assert row.updated_by_user_id == user.id
    assert row.updated_at is not None


def test_all_value_columns_may_be_empty(app):
    order = _create_order()
    db_session.add(SalesCommissionInput(order_id=order.id))
    db_session.commit()
    row = db_session.get(SalesCommissionInput, order.id)
    assert (row.install_cost, row.rate_override_bp, row.note, row.updated_by_user_id) == (None, None, None, None)
    assert row.version == 1


def test_one_row_per_order(app):
    order = _create_order()
    db_session.add(SalesCommissionInput(order_id=order.id, install_cost=1))
    db_session.commit()
    db_session.add(SalesCommissionInput(order_id=order.id, install_cost=2))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize(
    "fields",
    [
        {"install_cost": -1},
        {"rate_override_bp": -1},
        {"rate_override_bp": 10001},
    ],
)
def test_check_constraints_reject_out_of_range(app, fields):
    order = _create_order()
    db_session.add(SalesCommissionInput(order_id=order.id, **fields))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("bp", [0, 10000])
def test_rate_bp_bounds_are_inclusive(app, bp):
    order = _create_order()
    db_session.add(SalesCommissionInput(order_id=order.id, install_cost=0, rate_override_bp=bp))
    db_session.commit()
    assert db_session.get(SalesCommissionInput, order.id).rate_override_bp == bp


def test_order_fk_is_cascade_so_delete_retention_accepts_it():
    """하드 삭제(삭제 보존 적용)는 ``orders`` 행을 지운다 — 이 FK 가 CASCADE 여야 FK 검사가 통과하고 줄도 같이 사라진다."""
    assert ("sales_commission_inputs", "order_id", "CASCADE") in _referring_fks()
    _assert_fk_coverage()  # 미처리 NOT NULL 참조자가 있으면 raise


def test_deleting_order_removes_input_row_when_fk_enforced():
    """공용 SQLite 레인은 FK 를 강제하지 않는다(PRAGMA foreign_keys 꺼짐) — 그래서 따로 FK 를 켠 메모리 DB 에
    같은 스키마를 만들어 주문 삭제가 입력 줄을 같이 지우는지(ON DELETE CASCADE DDL) 본다."""
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(bind=engine)
        with engine.begin() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
            order_id = conn.execute(
                Base.metadata.tables["orders"].insert().values(**_order_kwargs())
            ).inserted_primary_key[0]
            conn.execute(text(
                "INSERT INTO sales_commission_inputs (order_id, install_cost) VALUES (:id, 1000)"
            ), {"id": order_id})
        with Session(engine) as session, session.begin():
            session.execute(text("DELETE FROM orders WHERE id = :id"), {"id": order_id})
        with engine.connect() as conn:
            left = conn.execute(text("SELECT COUNT(*) FROM sales_commission_inputs")).scalar()
        assert left == 0
    finally:
        engine.dispose()


def test_migration_is_single_head_and_matches_model_ddl_names():
    path = ROOT / "migrations" / "versions" / "fcomm_00_sales_commission_inputs.py"
    spec = importlib.util.spec_from_file_location("fcomm_00_unit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "fcomm_00"

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    assert "fcomm_00" in {rev.revision for rev in script.walk_revisions("base", heads[0])}
    assert script.get_revision("fcomm_00").down_revision == module.down_revision

    source = path.read_text(encoding="utf-8")
    table = SalesCommissionInput.__table__
    names = {c.name for c in table.constraints if c.name and c.name.startswith("ck_")}
    assert names == {"ck_sales_commission_inputs_install_cost", "ck_sales_commission_inputs_rate_bp"}
    for name in names:
        assert name in source
