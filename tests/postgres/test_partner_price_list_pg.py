"""협력사 단가표 판 PostgreSQL 레인(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.1 · §8).

SQLite 메인 레인은 FK 를 강제하지 않는다. 여기서는 진짜 PostgreSQL 에서 ① 협력사마다 ACTIVE 판 하나(부분 유일 색인 —
RETIRED 는 대조군) ② 없는 협력사 판은 FK 로 막힘 ③ 마이그레이션 ``pricelist_00`` 이 models 와 같은 표 · 색인을 만들고
upgrade → downgrade → upgrade 가 되는지 ④ 새 판 저장(옛 판 RETIRED · 새 판 ACTIVE)이 실제 색인과 부딪히지 않는지
⑤ 품목 옵션 표(``itemopt_00``)가 품목 · 단계마다 한 줄이고 주문을 지우면 같이 지워지는지(CASCADE) ⑥ 명세서 표(``pstmt_00``)가
주문마다 초안 하나 · 문서번호 하나이고 주문을 지우면 명세서 · 문의가 같이 지워지는지를 본다.
``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다(레인 규칙은 ``tests/postgres/conftest.py``). 단가 · 이름은 가짜다.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from foms.services.partners.price_list import save_price_list
from models import Order, OrderItemOption, PartnerOrg, PartnerPriceList, PartnerStatement, PartnerStatementQuestion

ROOT = Path(__file__).resolve().parents[2]
_SHEET = {"schema": 1, "brand": "t", "seq": 1, "retired": [], "categories": [
    {"id": "c0", "side": "left", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가"], "types": ["text", "price"],
     "layout": {}, "rows": [{"cells": ["슬라이딩", 100000], "items": [
         {"key": "r1", "name_col": 0, "price_col": 1, "role": "product", "unit": "자", "kind": "ja", "cond": {},
          "partner_label": "", "pick_names": ["슬라이딩"], "for_products": [], "pickable": True}]}]}]}


def _migration(name="pricelist_00_partner_price_lists"):
    path = ROOT / "migrations" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"{name}_unit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _org(pg_session, name="라운즈-pg") -> PartnerOrg:
    org = PartnerOrg(name=name)
    pg_session.add(org)
    pg_session.flush()
    return org


def _row(org_id, version, status):
    return PartnerPriceList(partner_org_id=org_id, version=version, label=f"{version}판", status=status,
                            effective_from=dt.date(2026, 11, version), sheet=_SHEET)


def _shape(conn, table="partner_price_lists"):
    cols = conn.execute(text(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name = :t ORDER BY column_name"), {"t": table}).all()
    idx = dict(conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :t"), {"t": table}).all())
    return cols, idx


def test_one_active_version_per_org(pg_session):
    org = _org(pg_session)
    other = _org(pg_session, "다른-pg")
    pg_session.add_all([_row(org.id, 1, "RETIRED"), _row(org.id, 2, "ACTIVE"), _row(other.id, 1, "ACTIVE")])
    pg_session.flush()  # 대조군: 지난 판 + 지금 판 하나 · 다른 협력사의 지금 판
    savepoint = pg_session.begin_nested()
    pg_session.add(_row(org.id, 3, "ACTIVE"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    savepoint.rollback()
    _cols, idx = _shape(pg_session.connection())
    assert "WHERE ((status)::text = 'ACTIVE'::text)" in idx["uq_partner_price_lists_active"]


def test_foreign_key_to_partner_orgs_is_enforced(pg_session):
    savepoint = pg_session.begin_nested()
    pg_session.add(_row(987654, 1, "ACTIVE"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    savepoint.rollback()


def test_save_new_version_retires_old_under_real_index(pg_session):
    org = _org(pg_session)
    first = save_price_list(pg_session, org.id, _SHEET, label="11월판", effective_from="2026-11-01", base_id=None, user_id=None)
    second = save_price_list(pg_session, org.id, _SHEET, label="12월판", effective_from="2026-12-01",
                             base_id=first.id, user_id=None)
    pg_session.flush()
    statuses = dict(pg_session.execute(text(
        "SELECT version, status FROM partner_price_lists WHERE partner_org_id = :o"), {"o": org.id}).all())
    assert statuses == {1: "RETIRED", 2: "ACTIVE"} and second.version == 2


def test_migration_matches_models_and_round_trips(pg_session):
    conn = pg_session.connection()
    models_shape = _shape(conn)
    mig = _migration()
    # 이 판을 가리키는 뒤 판들(alembic 은 뒤 판부터 내린다 — 명세서 표도 단가표 판을 FK 로 가리킨다)
    children = [_migration("itemopt_00_order_item_options"), _migration("pstmt_00_partner_statements")]
    assert (mig.revision, mig.down_revision) == ("pricelist_00", "brain_02")
    with Operations.context(MigrationContext.configure(conn)):
        for child in reversed(children):
            child.downgrade()
        mig.downgrade()
        assert _shape(conn) == ([], {})
        mig.upgrade()
        assert _shape(conn) == models_shape
        mig.downgrade()
        mig.upgrade()
        for child in children:
            child.upgrade()
    assert _shape(conn) == models_shape


def _order(pg_session) -> Order:
    order = Order(received_date="2026-11-03", customer_name="가짜 고객", phone="010-0000-0000", address="가짜 주소",
                  product="슬라이딩", status="DRAWING", is_erp_order=True)
    pg_session.add(order)
    pg_session.flush()
    return order


def test_item_options_one_row_per_item_stage_and_cascade(pg_session):
    order = _order(pg_session)
    uid = "11111111-2222-3333-4444-555555555555"
    pg_session.add_all([OrderItemOption(order_id=order.id, item_uid=uid, stage="PARTNER", state="none"),
                        OrderItemOption(order_id=order.id, item_uid=uid, stage="CURRENT", state="chosen",
                                        lines=[{"key": "r1", "name": "x", "qty": "1", "memo": ""}])])
    pg_session.flush()  # 대조군: 같은 품목의 다른 단계
    savepoint = pg_session.begin_nested()
    pg_session.add(OrderItemOption(order_id=order.id, item_uid=uid, stage="CURRENT", state="none"))
    with pytest.raises(IntegrityError):
        pg_session.flush()
    savepoint.rollback()
    savepoint = pg_session.begin_nested()
    pg_session.add(OrderItemOption(order_id=order.id, item_uid=uid, stage="CONFIRMED", state="maybe"))
    with pytest.raises(IntegrityError):
        pg_session.flush()  # state 검사 제약
    savepoint.rollback()
    pg_session.execute(text("DELETE FROM orders WHERE id = :i"), {"i": order.id})
    left = pg_session.execute(text("SELECT count(*) FROM order_item_options WHERE order_id = :i"), {"i": order.id}).scalar()
    assert left == 0


def test_item_options_migration_matches_models_and_round_trips(pg_session):
    conn = pg_session.connection()
    models_shape = _shape(conn, "order_item_options")
    mig = _migration("itemopt_00_order_item_options")
    assert (mig.revision, mig.down_revision) == ("itemopt_00", "pricelist_00")
    with Operations.context(MigrationContext.configure(conn)):
        mig.downgrade()
        assert _shape(conn, "order_item_options") == ([], {})
        mig.upgrade()
        assert _shape(conn, "order_item_options") == models_shape
        mig.downgrade()
        mig.upgrade()
    assert _shape(conn, "order_item_options") == models_shape


def _stmt(order, status="DRAFT", doc_no=None):
    return PartnerStatement(partner_org_id=order.partner_org_id, order_id=order.id, status=status, doc_no=doc_no)


def test_statements_one_draft_per_order_unique_doc_no_and_cascade(pg_session):
    org = _org(pg_session)
    order = _order(pg_session)
    order.partner_org_id = org.id
    pg_session.add_all([_stmt(order), _stmt(order, "ISSUED", "HD-20261110-01"), _stmt(order, "VOID", "HD-20261110-02")])
    pg_session.flush()  # 대조군: 초안 하나 + 발행 · 취소본은 여럿
    savepoint = pg_session.begin_nested()
    pg_session.add(_stmt(order))
    with pytest.raises(IntegrityError):
        pg_session.flush()  # 주문마다 초안은 하나
    savepoint.rollback()
    savepoint = pg_session.begin_nested()
    pg_session.add(_stmt(order, "ISSUED", "HD-20261110-01"))
    with pytest.raises(IntegrityError):
        pg_session.flush()  # 문서번호는 하나
    savepoint.rollback()
    issued = pg_session.query(PartnerStatement).filter_by(doc_no="HD-20261110-01").one()
    pg_session.add(PartnerStatementQuestion(statement_id=issued.id, line_ref="1-2", text="이 금액 맞나요?"))
    pg_session.flush()
    pg_session.execute(text("DELETE FROM orders WHERE id = :i"), {"i": order.id})
    left = pg_session.execute(text("SELECT (SELECT count(*) FROM partner_statements WHERE order_id = :i) + "
                                   "(SELECT count(*) FROM partner_statement_questions)"), {"i": order.id}).scalar()
    assert left == 0


def test_statements_migration_matches_models_and_round_trips(pg_session):
    conn = pg_session.connection()
    shapes = {t: _shape(conn, t) for t in ("partner_statements", "partner_statement_questions")}
    mig = _migration("pstmt_00_partner_statements")
    assert (mig.revision, mig.down_revision) == ("pstmt_00", "itemopt_00")
    with Operations.context(MigrationContext.configure(conn)):
        mig.downgrade()
        assert all(_shape(conn, t) == ([], {}) for t in shapes)
        mig.upgrade()
        assert {t: _shape(conn, t) for t in shapes} == shapes
        mig.downgrade()
        mig.upgrade()
    assert {t: _shape(conn, t) for t in shapes} == shapes
