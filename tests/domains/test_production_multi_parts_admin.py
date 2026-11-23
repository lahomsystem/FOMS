"""여러 파트(P2) — 관리자 사용자 화면 체크칸 · 두 칸 같이 쓰기 · 감사 글 · 목록 글 · 마이그레이션 ``prodparts_01``(SQLite 레인).

설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` §6-1 · §8-6 · §15. PG 쪽(CHECK · 채우기 · 되돌리기)은
``tests/postgres/test_users_production_parts_pg.py``. 이름은 모두 지어낸 값이다.

되돌리면 실패: 두 번째 파트 버림 · 옛 칸에 첫 파트를 안 씀(되돌린 옛 코드가 엉뚱한 파트를 읽음) · 정의 순서 아님 · 체크칸을 다 끄면 옛
값이 남음 · 생산팀 밖에 파트가 남음 · 감사 글이 옛 칸 · 목록 글에 첫 파트만 · 채우기 빠짐 · 되돌리기가 첫 파트를 안 살림.
대조군: 옛 고르기 칸(production_part)으로 보낸 저장도 같은 두 칸 · 파트 없는 생산팀 목록 글은 '생산팀' 그대로.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

import models
from db import db_session
from models import SecurityLog, User
from tests.domains.test_admin_user_production_part import (  # noqa: F401 — _reset_rate_limits 는 자동 fixture
    _admin_client,
    _edit,
    _make_user,
    _reset_rate_limits,
    _user,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "prodparts_01_users_production_parts.py"
_STRONG_PW = "Abcdef12"


def _parts(uid: int) -> tuple:
    saved = _user(uid)
    return saved.production_parts, saved.production_part


# --------------------------------------------------------------------------- #
# 저장 — 체크칸 여럿 → 새 칸(목록) + 옛 칸(첫 파트)
# --------------------------------------------------------------------------- #
def test_edit_saves_two_parts_in_order_and_first_part_in_old_column(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    resp = _edit(admin, uid, production_parts=["edge", "cut"])
    assert resp.status_code == 302, resp.get_data(as_text=True)[:400]
    assert _parts(uid) == (["cut", "edge"], "cut")
    assert _edit(admin, uid, production_parts=["inspect", "assemble", "edge"]).status_code == 302
    assert _parts(uid) == (["edge", "assemble", "inspect"], "edge")
    assert _edit(admin, uid).status_code == 302  # 체크칸을 모두 끄면 두 칸 다 비운다(파트 없는 생산팀 = 대신)
    assert _parts(uid) == (None, None)


def test_edit_clears_parts_outside_production_and_rejects_unknown(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION", part="cut")
    resp = _edit(admin, uid, production_parts=["cut", "paint"], name="바뀌면 안 됨")
    assert resp.status_code == 200 and "알 수 없는 생산 파트" in resp.get_data(as_text=True)
    assert _parts(uid) == (None, "cut") and _user(uid).name != "바뀌면 안 됨"  # 아무것도 안 바뀜
    assert _edit(admin, uid, team="SALES", production_parts=["cut", "edge"]).status_code == 302
    assert _parts(uid) == (None, None)


def test_old_select_field_still_saves_both_columns(app):
    """배포 전에 열어 둔 화면(고르기 한 칸 production_part)에서 저장해도 두 칸이 맞는다 — 파트 둘이던 사람도 그 하나로."""
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_parts=["cut", "edge"]).status_code == 302
    assert _edit(admin, uid, production_part="edge").status_code == 302
    assert _parts(uid) == (["edge"], "edge")
    assert _edit(admin, uid, production_part="").status_code == 302
    assert _parts(uid) == (None, None)


def test_add_user_saves_parts_only_for_production(app):
    admin = _admin_client(app)
    base = {"password": _STRONG_PW, "name": "새 두파트", "role": "STAFF", "production_parts": ["inspect", "cut"]}
    assert admin.post("/admin/users/add", data={**base, "username": "mp_new_prod", "team": "PRODUCTION"}).status_code == 302
    assert admin.post("/admin/users/add", data={**base, "username": "mp_new_cs", "team": "CS"}).status_code == 302
    db_session.remove()
    got = {u.username: (u.production_parts, u.production_part)
           for u in db_session.query(User).filter(User.username.in_(["mp_new_prod", "mp_new_cs"]))}
    assert got == {"mp_new_prod": (["cut", "inspect"], "cut"), "mp_new_cs": (None, None)}


def test_part_change_keeps_target_session(app, client):
    from tests.domains.test_admin_user_production_part import _login
    uid = _make_user(team="PRODUCTION", part="cut")
    _login(client, uid)
    assert _edit(_admin_client(app), uid, production_parts=["cut", "edge"]).status_code == 302
    assert client.get("/profile").status_code == 200  # 파트만 바뀌면 그대로 로그인(세션 안 끊음)


# --------------------------------------------------------------------------- #
# 감사 · 화면 글
# --------------------------------------------------------------------------- #
def test_audit_says_part_names_before_and_after(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION", part="cut")  # 옛 칸만 있는 행 — 감사 '전'은 적힌 파트(재단)
    assert _edit(admin, uid, production_parts=["cut", "edge"]).status_code == 302
    assert _edit(admin, uid).status_code == 302
    db_session.remove()
    edits = [r.message for r in db_session.query(SecurityLog).order_by(SecurityLog.id) if f"사용자 #{uid} 수정:" in r.message]
    assert edits == [f"사용자 #{uid} 수정: 생산 파트 재단 → 재단 · 엣지", f"사용자 #{uid} 수정: 생산 파트 재단 · 엣지 → 미지정"]
    rows = (db_session.query(SecurityLog).filter(SecurityLog.action == "USER_UPDATE", SecurityLog.target_id == uid)
            .order_by(SecurityLog.id).all())
    assert [r.detail["changes"] for r in rows] == [{"production_parts": {"from": ["cut"], "to": ["cut", "edge"]}},
                                                   {"production_parts": {"from": ["cut", "edge"], "to": None}}]


def test_edit_form_checks_saved_parts_and_list_shows_all_parts(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_parts=["cut", "edge"]).status_code == 302
    html = admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    checked = [k for k in ("cut", "edge", "assemble", "inspect") if f'value="{k}" checked>' in html]
    assert checked == ["cut", "edge"] and '<legend class="form-label fs-6 mb-2">생산 파트 (선택)</legend>' in html
    _make_user(team="PRODUCTION")  # 대조군: 파트 없는 생산팀은 '생산팀' 그대로(지금 글)
    listing = admin.get("/admin/users").get_data(as_text=True)
    assert "<td>생산팀 · 재단 · 엣지</td>" in listing and "<td>생산팀</td>" in listing


def test_admin_templates_have_no_inline_style_for_new_fields():
    for name in ("add_user.html", "edit_user.html"):
        src = (ROOT / "templates/auth" / name).read_text(encoding="utf-8")
        block = src[src.index("<fieldset"):src.index("</fieldset>")]
        assert "style=" not in block and block.count('name="production_parts"') == 1, name


# --------------------------------------------------------------------------- #
# 모델 · 마이그레이션 prodparts_01
# --------------------------------------------------------------------------- #
def _migration():
    spec = importlib.util.spec_from_file_location("prodparts_01_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_onto_handover_and_keeps_one_head():
    module = _migration()
    assert (module.revision, module.down_revision) == ("prodparts_01", "prodpart_01_handover")
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["prodparts_01"]


def test_model_column_and_pg_only_check_match_the_migration():
    module = _migration()
    column = User.__table__.c.production_parts
    assert column.nullable is True and column.server_default is None and column.index is not True
    assert module.CHECK_SQL == models.PRODUCTION_PARTS_CHECK_SQL
    checks = {c.name: str(c.sqltext) for c in User.__table__.constraints if c.name == module.CHECK_NAME}
    assert checks == {module.CHECK_NAME: module.CHECK_SQL}
    pg = str(CreateTable(User.__table__).compile(dialect=postgresql.dialect()))
    lite = str(CreateTable(User.__table__).compile(dialect=sqlite.dialect()))
    assert "production_parts JSONB" in pg and module.CHECK_NAME in pg
    assert "production_parts JSON" in lite and module.CHECK_NAME not in lite  # SQLite 는 앱 검사(normalize_production_parts)


def test_migration_fills_from_old_column_and_downgrade_keeps_old_column_on_sqlite():
    """downgrade 는 옛 칸을 건드리지 않는다 — 두 칸이 같은 행은 이미 첫 파트, 어긋난 행(코드만 되돌린 동안 옛 화면이 옛 칸을 고침)은
    옛 칸이 나중 값이라 그대로 남아야 한다(옛 칸을 새 칸 첫 값으로 덮으면 뺏은 파트 권한이 돌아온다)."""
    module = _migration()
    assert not hasattr(module, "_RESTORE_SQL")
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, team VARCHAR(50), production_part VARCHAR(16))"))
        conn.execute(text("INSERT INTO users VALUES (1, 'PRODUCTION', 'edge'), (2, 'PRODUCTION', NULL), (3, 'CS', 'cut'),"
                          " (4, 'PRODUCTION', 'cut')"))
        module.upgrade()
        got = dict(conn.execute(text("SELECT id, production_parts FROM users")).all())
        assert got == {1: '["edge"]', 2: None, 3: '["cut"]', 4: '["cut"]'}  # 옛 칸이 있는 행만(팀은 읽는 쪽이 본다)
        conn.execute(text("UPDATE users SET production_parts = json_array('cut','assemble'), production_part = 'cut' WHERE id = 1"))
        conn.execute(text("UPDATE users SET production_parts = json_array('cut','edge'), production_part = 'inspect' WHERE id = 4"))
        module.downgrade()
        assert dict(conn.execute(text("SELECT id, production_part FROM users")).all()) == {1: "cut", 2: None, 3: "cut", 4: "inspect"}
        assert {c["name"] for c in inspect(conn).get_columns("users")} == {"id", "team", "production_part"}
