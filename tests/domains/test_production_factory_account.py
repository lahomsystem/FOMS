"""계정 공장(3단계 ②, PRODFACTORY-01) — 값 한 곳 · 판정 함수 · 관리자 추가 · 수정 칸 · 감사 · 목록 글 · 마이그레이션(SQLite 레인).

설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §4-13 · §5 권한 표 · §6-2 · §8-6 · C9. PG 쪽(CHECK · 왕복)은
``tests/postgres/test_users_production_factory_pg.py``. 이름은 모두 지어낸 값이다.

되돌리면 실패: 2공장이 저장 안 됨 · 생산팀 밖에 공장이 남음 · 1공장을 1 로 적어 헛 감사가 남음 · 모르는 값을 조용히 1공장으로 ·
감사 글 꼴 · 목록 글에 2공장이 없음 · 관리자를 한 공장으로 · 파트 계정 · 반장이 남의 공장을 씀 · CHECK 글이 모델과 다름 · 머리 둘.
대조군: 1공장(비어 있음) 계정의 목록 글은 지금 그대로 · 공장을 안 건드린 저장은 감사 글이 없음.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

import models
from db import db_session
from foms.services.production.factory_constants import (
    account_production_factory,
    factory_label,
    normalize_factory,
    production_factory_for_team,
)
from foms.services.production.part_access import can_write_sheet, user_factory, writable_factories
from foms.services.production.part_mark_rules import subject_particle
from models import ProductionPartMark, SecurityLog, User
from tests.domains.test_admin_user_production_part import (  # noqa: F401 — _reset_rate_limits 는 자동 fixture
    _admin_client,
    _edit,
    _make_user,
    _reset_rate_limits,
    _user,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "prodfactory_01_users_production_factory.py"
_STRONG_PW = "Abcdef12"


def _ns(*, team="PRODUCTION", role="STAFF", factory=None, parts=None, lead=None) -> SimpleNamespace:
    return SimpleNamespace(team=team, role=role, production_factory=factory, production_parts=parts,
                           production_part=parts[0] if parts else None, production_lead=lead, is_active=True,
                           partner_org_id=None, id=9)


# --------------------------------------------------------------------------- #
# 값 한 곳 · 판정
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("raw", "expected"), [(None, None), ("", None), (" ", None), ("1", 1), (2, 2), (" 2 ", 2)])
def test_normalize_factory(raw, expected):
    assert normalize_factory(raw) == expected


@pytest.mark.parametrize("raw", ["3", 0, "두공장", True, "1.5"])
def test_normalize_factory_rejects_unknown(raw):
    with pytest.raises(ValueError):
        normalize_factory(raw)


def test_store_only_second_factory_for_production_and_read_null_as_first():
    assert production_factory_for_team("PRODUCTION", 2) == 2 and production_factory_for_team(" production ", 2) == 2
    assert production_factory_for_team("PRODUCTION", 1) is None  # 1공장 = 비움(NULL — 지금과 같음)
    assert production_factory_for_team("CS", 2) is None and production_factory_for_team("PRODUCTION", None) is None
    assert account_production_factory(_ns()) == 1 and account_production_factory(_ns(factory=2)) == 2
    assert account_production_factory(_ns(team="CS", factory=2)) is None and account_production_factory(None) is None
    assert (factory_label(1), factory_label(2), factory_label(None)) == ("1공장", "2공장", "1공장")


@pytest.mark.parametrize(("who", "factories"), [
    (dict(parts=["cut"]), (1,)),
    (dict(parts=["cut"], factory=2), (2,)),
    (dict(lead=True, factory=2), (2,)),  # 반장도 자기 공장 장만(C9)
    (dict(role="ADMIN", team="CS"), (1, 2)),  # 관리자만 두 공장
    (dict(role="ADMIN", factory=2), (1, 2)),
    (dict(), ()),  # 파트도 반장도 아님 = 보기만
    (dict(team="DRAWING", factory=2), ()),
])
def test_writable_factories_follow_the_permission_table(who, factories):
    person = _ns(**who)
    assert writable_factories(person) == factories
    assert [f for f in (1, 2) if can_write_sheet(person, f)] == list(factories)
    assert can_write_sheet(person, None) is (1 in factories)  # 공장이 비면 1공장
    assert user_factory(person) == (2 if who.get("factory") == 2 else 1)


# --------------------------------------------------------------------------- #
# 관리자 추가 · 수정
# --------------------------------------------------------------------------- #
def _factory(uid: int):
    return _user(uid).production_factory


def test_edit_saves_second_factory_only_for_production_and_clears_on_team_change(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_factory="2").status_code == 302
    assert _factory(uid) == 2
    assert _edit(admin, uid, production_factory="1").status_code == 302
    assert _factory(uid) is None  # 1공장은 비운다
    assert _edit(admin, uid, production_factory="2").status_code == 302
    assert _edit(admin, uid, team="SALES", production_factory="2").status_code == 302
    assert _factory(uid) is None
    bad = _edit(admin, uid, team="PRODUCTION", production_factory="3", name="바뀌면 안 됨")
    assert bad.status_code == 200 and "알 수 없는 공장이에요." in bad.get_data(as_text=True)
    assert _user(uid).name != "바뀌면 안 됨"


def test_add_user_saves_factory_only_for_production(app):
    admin = _admin_client(app)
    base = {"password": _STRONG_PW, "name": "새 공장", "role": "STAFF", "production_factory": "2"}
    assert admin.post("/admin/users/add", data={**base, "username": "pf_prod", "team": "PRODUCTION"}).status_code == 302
    assert admin.post("/admin/users/add", data={**base, "username": "pf_cs", "team": "CS"}).status_code == 302
    db_session.remove()
    got = {u.username: u.production_factory for u in db_session.query(User).filter(User.username.like("pf_%"))}
    assert got == {"pf_prod": 2, "pf_cs": None}


def test_audit_says_factory_and_untouched_save_writes_no_factory_line(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_factory="1").status_code == 302  # 대조군: 비어 있던 계정을 1공장으로 저장 = 바뀜 없음
    assert _edit(admin, uid, production_factory="2").status_code == 302
    assert _edit(admin, uid, production_factory="1").status_code == 302
    db_session.remove()
    rows = (db_session.query(SecurityLog).filter(SecurityLog.action == "USER_UPDATE", SecurityLog.target_id == uid)
            .order_by(SecurityLog.id).all())
    assert [r.message for r in rows] == [f"사용자 #{uid} 정보 수정", f"사용자 #{uid} 수정: 공장 1공장 → 2공장",
                                         f"사용자 #{uid} 수정: 공장 2공장 → 1공장"]
    assert rows[1].detail["changes"] == {"production_factory": {"from": 1, "to": 2}}


def test_factory_change_tells_admin_about_held_cards(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION", part="edge")
    from tests.support.production_part_claim_seed import make_order
    order = make_order(2)
    holder = _user(uid).name  # 세션을 비우므로 표시 줄을 넣기 전에 읽는다
    for key in order.keys:
        db_session.add(ProductionPartMark(order_id=order.id, drawing_key=key, part="edge", state="NEED", picked_by_user_id=uid,
                                          picked_by_name=holder, updated_by_user_id=uid))
    db_session.commit()
    resp = _edit(admin, uid, production_factory="2", production_parts=["edge"])
    assert resp.status_code == 302
    page = admin.get("/admin/users").get_data(as_text=True)
    who = subject_particle(_user(uid).name)  # 이름 + 이/가
    assert f"{who} 1공장에서 담당인 장이 2장 있어요. 그대로 두면 1공장 사람이 [담당 바꾸기]로 이어서 해요." in page
    assert _edit(admin, uid, production_factory="2", production_parts=["edge"]).status_code == 302  # 공장 그대로 = 안내 없음
    assert "담당인 장이" not in admin.get("/admin/users").get_data(as_text=True)


def test_edit_form_selects_saved_factory_and_list_says_second_factory_only(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    form = admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    select = form.split('name="production_factory">', 1)[1].split("</select>", 1)[0]
    assert '<option value="1" selected>1공장</option>' in select and '<option value="2">2공장</option>' in select
    assert "생산팀일 때만 쓰여요. 관리자는 두 공장을 모두 처리할 수 있어요." in form
    assert _edit(admin, uid, production_factory="2", production_parts=["cut", "edge"]).status_code == 302
    assert '<option value="2" selected>2공장</option>' in admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    add = admin.get("/admin/users/add").get_data(as_text=True)
    assert '<option value="1" selected>1공장</option>' in add
    _make_user(team="PRODUCTION", part="cut")  # 대조군: 1공장 계정은 지금 글 그대로
    listing = admin.get("/admin/users").get_data(as_text=True)
    assert "<td>생산팀 · 재단 · 엣지 · 2공장</td>" in listing and "<td>생산팀 · 재단</td>" in listing
    assert "1공장</td>" not in listing


def test_admin_templates_have_no_inline_style_for_factory_field():
    for name in ("add_user.html", "edit_user.html"):
        src = (ROOT / "templates/auth" / name).read_text(encoding="utf-8")
        block = src[src.index("data-production-factory-field"):][:900].split("</div>\n", 2)
        assert "style=" not in "".join(block[:2]) and 'class="form-select"' in block[0], name


# --------------------------------------------------------------------------- #
# 모델 · 마이그레이션 prodfactory_01
# --------------------------------------------------------------------------- #
def _migration():
    spec = importlib.util.spec_from_file_location("prodfactory_01_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_onto_lead_and_keeps_one_head():
    module = _migration()
    assert (module.revision, module.down_revision) == ("prodfactory_01", "prodlead_01")
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1


def test_model_column_and_check_on_both_dialects_match_the_migration():
    module = _migration()
    column = User.__table__.c.production_factory
    assert column.nullable is True and column.server_default is None and column.default is None and column.index is not True
    assert module.CHECK_SQL == models.PRODUCTION_FACTORY_CHECK_SQL
    checks = {c.name: str(c.sqltext) for c in User.__table__.constraints if c.name == module.CHECK_NAME}
    assert checks == {module.CHECK_NAME: module.CHECK_SQL}
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        ddl = str(CreateTable(User.__table__).compile(dialect=dialect))
        assert "production_factory SMALLINT" in ddl and module.CHECK_NAME in ddl, dialect.name


def test_migration_round_trip_on_sqlite_adds_check_and_keeps_other_columns():
    module = _migration()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, team VARCHAR(50), production_lead BOOLEAN)"))
        conn.execute(text("INSERT INTO users VALUES (1, 'PRODUCTION', 1), (2, 'CS', NULL)"))
        module.upgrade()
        assert dict(conn.execute(text("SELECT id, production_factory FROM users")).all()) == {1: None, 2: None}  # 채우기 없음
        conn.execute(text("UPDATE users SET production_factory = 2 WHERE id = 1"))
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE users SET production_factory = 3 WHERE id = 2"))
        module.downgrade()
        assert {c["name"] for c in inspect(conn).get_columns("users")} == {"id", "team", "production_lead"}
        assert dict(conn.execute(text("SELECT id, production_lead FROM users")).all()) == {1: 1, 2: None}  # 다른 칸 그대로
