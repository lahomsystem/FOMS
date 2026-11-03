"""협력사 단가표 판 PostgreSQL 레인(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §3.1 · §8).

SQLite 메인 레인은 FK 를 강제하지 않는다. 여기서는 진짜 PostgreSQL 에서 ① 협력사마다 ACTIVE 판 하나(부분 유일 색인 —
RETIRED 는 대조군) ② 없는 협력사 판은 FK 로 막힘 ③ 마이그레이션 ``pricelist_00`` 이 models 와 같은 표 · 색인을 만들고
upgrade → downgrade → upgrade 가 되는지 ④ 새 판 저장(옛 판 RETIRED · 새 판 ACTIVE)이 실제 색인과 부딪히지 않는지를 본다.
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
from models import PartnerOrg, PartnerPriceList

ROOT = Path(__file__).resolve().parents[2]
_SHEET = {"schema": 1, "brand": "t", "seq": 1, "retired": [], "categories": [
    {"id": "c0", "side": "left", "title": "기본 제품 가격", "headers": ["제품명", "자당 단가"], "types": ["text", "price"],
     "layout": {}, "rows": [{"cells": ["슬라이딩", 100000], "items": [
         {"key": "r1", "name_col": 0, "price_col": 1, "role": "product", "unit": "자", "kind": "ja", "cond": {},
          "partner_label": "", "pick_names": ["슬라이딩"], "for_products": [], "pickable": True}]}]}]}


def _migration():
    path = ROOT / "migrations" / "versions" / "pricelist_00_partner_price_lists.py"
    spec = importlib.util.spec_from_file_location("pricelist_00_unit", path)
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


def _shape(conn):
    cols = conn.execute(text(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'partner_price_lists' ORDER BY column_name")).all()
    idx = dict(conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'partner_price_lists'")).all())
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
    assert (mig.revision, mig.down_revision) == ("pricelist_00", "brain_02")
    with Operations.context(MigrationContext.configure(conn)):
        mig.downgrade()
        assert _shape(conn) == ([], {})
        mig.upgrade()
        assert _shape(conn) == models_shape
        mig.downgrade()
        mig.upgrade()
    assert _shape(conn) == models_shape
