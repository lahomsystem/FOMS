"""반장 따로 지정(PRODLEAD-01) — 관리자 추가 · 수정 · 가입 승인의 '반장' 칸 · 감사 글 · 목록 글 · 마이그레이션 채우기(SQLite 레인).

설계서 ``docs/specs/2026-11-23-production-self-claim-and-factory2_SPEC.md`` 맨 위 '승인 때 고친 것' 5(사장님 2026-11-24 "반장을 따로
지정하기"). 권한 규칙(대신 · 보기만 · 공정 칸 잠금)은 ``test_production_multi_parts.py`` · ``test_production_part_steps_sync.py``,
PG 채우기 · 왕복은 ``tests/postgres/test_users_production_lead_pg.py``. 이름은 모두 지어낸 값이다.

되돌리면 실패: 반장 체크가 저장 안 됨 · 생산팀 밖에 반장이 남음 · 팀을 바꿔도 반장이 남음 · 승인이 파트 · 반장을 버림 · 감사 글이 빠지거나
'True→None' 꼴 · 목록 글에 반장이 없음 · 옛 안내 글("하나도 안 고르면 … 대신") 남음 · 채우기 조건이 VIEWER · 다른 팀 · 파트 있는 계정까지.
대조군: 반장이 아닌 생산팀 목록 글은 '생산팀' 그대로 · 반장 칸을 안 건드린 저장은 감사 글이 없음.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

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
MIGRATION = ROOT / "migrations" / "versions" / "prodlead_01_users_production_lead.py"
_STRONG_PW = "Abcdef12"
_NOTE = "반장은 모든 파트 도면을 대신 처리하고 공정을 직접 체크할 수 있어요."


def _lead(uid: int):
    return _user(uid).production_lead


# --------------------------------------------------------------------------- #
# 저장 — 추가 · 수정 · 승인
# --------------------------------------------------------------------------- #
def test_edit_saves_lead_only_for_production_and_team_change_clears_it(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_lead="on").status_code == 302
    assert _lead(uid) is True
    assert _edit(admin, uid, production_lead="on", production_parts=["cut", "edge"]).status_code == 302
    assert (_lead(uid), _user(uid).production_parts) == (True, ["cut", "edge"])  # 반장이 파트도 가질 수 있다
    assert _edit(admin, uid).status_code == 302  # 체크를 끄면 비운다(NULL = 반장 아님)
    assert _lead(uid) is None
    assert _edit(admin, uid, production_lead="on").status_code == 302
    assert _edit(admin, uid, team="CS", production_lead="on").status_code == 302  # 다른 팀으로 바꾸면 같이 비움
    assert _lead(uid) is None


def test_add_user_saves_lead_only_for_production(app):
    admin = _admin_client(app)
    base = {"password": _STRONG_PW, "name": "새 반장", "role": "STAFF", "production_lead": "on"}
    assert admin.post("/admin/users/add", data={**base, "username": "pl_new_prod", "team": "PRODUCTION"}).status_code == 302
    assert admin.post("/admin/users/add", data={**base, "username": "pl_new_cs", "team": "CS"}).status_code == 302
    plain = {**base, "username": "pl_new_plain", "team": "PRODUCTION"}
    plain.pop("production_lead")
    assert admin.post("/admin/users/add", data=plain).status_code == 302  # 새 계정의 기본은 반장 아님
    db_session.remove()
    got = {u.username: u.production_lead for u in db_session.query(User).filter(User.username.like("pl_new_%"))}
    assert got == {"pl_new_prod": True, "pl_new_cs": None, "pl_new_plain": None}


def _pending(name: str) -> int:
    user = User(username=f"pl_pend_{name}", password="x", name=name, role="VIEWER", team="PRODUCTION", is_active=True,
                approval_status="PENDING")
    db_session.add(user)
    db_session.commit()
    return user.id


def test_approve_saves_parts_and_lead_for_production_and_clears_other_teams(app):
    admin = _admin_client(app)
    prod, cs = _pending("생산신청"), _pending("상담신청")
    resp = admin.post(f"/admin/users/approve/{prod}", data={"role": "STAFF", "team": "PRODUCTION",
                                                           "production_parts": ["edge", "cut"], "production_lead": "on"})
    assert resp.status_code == 302
    saved = _user(prod)
    assert (saved.approval_status, saved.production_parts, saved.production_part, saved.production_lead) == (
        "ACTIVE", ["cut", "edge"], "cut", True)
    assert admin.post(f"/admin/users/approve/{cs}", data={"role": "STAFF", "team": "CS", "production_parts": ["cut"],
                                                         "production_lead": "on"}).status_code == 302
    saved = _user(cs)
    assert (saved.approval_status, saved.production_parts, saved.production_part, saved.production_lead) == (
        "ACTIVE", None, None, None)
    bad = _pending("엉뚱")
    assert admin.post(f"/admin/users/approve/{bad}", data={"role": "STAFF", "team": "PRODUCTION",
                                                          "production_parts": ["paint"]}).status_code == 302
    assert _user(bad).approval_status == "PENDING"  # 모르는 파트 = 승인 안 함(되묻기)
    db_session.remove()
    approve = [r.message for r in db_session.query(SecurityLog).filter(SecurityLog.action == "USER_APPROVE")]
    assert any("생산 파트 미지정 → 재단 · 엣지" in m and "반장 해제 → 지정" in m for m in approve), approve


# --------------------------------------------------------------------------- #
# 감사 · 화면 글
# --------------------------------------------------------------------------- #
def test_audit_says_lead_set_and_cleared(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_lead="on").status_code == 302
    assert _edit(admin, uid, name="이름만").status_code == 302  # 반장은 그대로 끔 — 아래에서 '해제'
    assert _edit(admin, uid, production_lead="on").status_code == 302
    assert _edit(admin, uid, production_lead="on", name="또 이름만").status_code == 302  # 대조군: 반장 그대로면 반장 글 없음
    db_session.remove()
    rows = (db_session.query(SecurityLog).filter(SecurityLog.action == "USER_UPDATE", SecurityLog.target_id == uid)
            .order_by(SecurityLog.id).all())
    assert [r.message for r in rows] == [f"사용자 #{uid} 수정: 반장 해제 → 지정", f"사용자 #{uid} 수정: 반장 지정 → 해제",
                                         f"사용자 #{uid} 수정: 반장 해제 → 지정", f"사용자 #{uid} 정보 수정"]
    assert rows[0].detail["changes"] == {"production_lead": {"from": False, "to": True}}


def test_forms_show_lead_checkbox_and_short_parts_note_and_list_says_lead(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_lead="on", production_parts=["cut", "edge"]).status_code == 302
    edit = admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    assert 'name="production_lead" checked>' in edit and _NOTE in edit
    add = admin.get("/admin/users/add").get_data(as_text=True)
    assert 'name="production_lead">' in add and _NOTE in add
    for html in (edit, add):  # P2 안내의 뒤 절은 틀린 말이 됐다(파트 없음 ≠ 대신)
        assert "<div class=\"form-text\" data-production-parts-note>여럿 골라도 돼요.</div>" in html
        assert "하나도 안 고르면" not in html
    lead_only = _make_user(team="PRODUCTION")
    assert _edit(admin, lead_only, production_lead="on").status_code == 302
    _make_user(team="PRODUCTION")  # 대조군: 파트도 반장도 없는 생산팀 = '생산팀' 그대로
    _pending("목록신청")
    listing = admin.get("/admin/users").get_data(as_text=True)
    assert "<td>생산팀 · 반장 · 재단 · 엣지</td>" in listing and "<td>생산팀 · 반장</td>" in listing
    assert "<td>생산팀</td>" in listing
    approve = listing.split("data-approve-production-fields", 1)[1].split("</span>", 1)[0]
    assert approve.count('name="production_parts"') == 4 and 'name="production_lead"' in approve and "반장" in approve


def test_admin_templates_have_no_inline_style_for_lead_fields():
    for name in ("add_user.html", "edit_user.html", "user_list.html"):
        src = (ROOT / "templates/auth" / name).read_text(encoding="utf-8")
        marker = "data-approve-production-fields" if name == "user_list.html" else "data-production-lead-field"
        block = src[src.index(marker):][:900]
        assert "style=" not in block and 'name="production_lead"' in block, name


# --------------------------------------------------------------------------- #
# 모델 · 마이그레이션 prodlead_01(SQLite)
# --------------------------------------------------------------------------- #
def _migration():
    spec = importlib.util.spec_from_file_location("prodlead_01_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chains_onto_prodparts_and_model_column_matches():
    module = _migration()
    assert (module.revision, module.down_revision) == ("prodlead_01", "prodparts_01")
    column = User.__table__.c.production_lead
    assert column.nullable is True and column.server_default is None and column.default is None and column.index is not True


def test_migration_fills_only_production_staff_and_managers_without_parts_on_sqlite():
    module = _migration()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, role VARCHAR, team VARCHAR(50), is_active BOOLEAN, "
                          "production_part VARCHAR(16), production_parts JSON)"))
        conn.execute(text(
            "INSERT INTO users VALUES "
            "(1, 'STAFF', 'PRODUCTION', 1, NULL, NULL),"      # 파트 없는 생산 STAFF → 반장
            "(2, 'MANAGER', ' production ', 0, NULL, '[]')," # 꺼진 계정 · 빈 목록 · 빈칸 섞인 팀 글도 → 반장
            "(3, 'VIEWER', 'PRODUCTION', 1, NULL, NULL),"     # 조회 전용 → 그대로
            "(4, 'STAFF', 'CS', 1, NULL, NULL),"              # 다른 팀 → 그대로
            "(5, 'STAFF', 'PRODUCTION', 1, 'cut', '[\"cut\"]')," # 파트 있는 계정 → 그대로
            "(6, 'ADMIN', 'PRODUCTION', 1, NULL, NULL),"      # 관리자는 칸과 상관없이 늘 된다 → 그대로
            "(7, 'STAFF', 'PRODUCTION', 1, NULL, '[\"edge\"]')")) # 새 칸만 남은 행(옛 칸 NULL) — 앱은 파트 없음으로 본다 → 반장
        module.upgrade()
        got = dict(conn.execute(text("SELECT id, production_lead FROM users")).all())
        assert got == {1: 1, 2: 1, 3: None, 4: None, 5: None, 6: None, 7: 1}
        conn.execute(text(f"UPDATE users SET production_lead = 1 WHERE {module.FILL_WHERE}"))  # 다시 돌려도 같다
        assert dict(conn.execute(text("SELECT id, production_lead FROM users")).all()) == got
        module.downgrade()
        assert {c["name"] for c in inspect(conn).get_columns("users")} == {
            "id", "role", "team", "is_active", "production_part", "production_parts"}  # 다른 칸은 그대로
        assert dict(conn.execute(text("SELECT id, production_part FROM users")).all())[5] == "cut"


def test_fill_where_matches_the_app_meaning_of_no_parts():
    """운영에 올리기 전 셀 읽기 전용 집계는 이 글을 그대로 쓴다(두 방언 같은 글). '파트 없음' = 옛 칸 NULL — 앱 판정
    ``stored_production_parts`` 와 같다(새 칸에 목록이 남아 있어도 옛 칸이 비면 파트 없음)."""
    assert _migration().FILL_WHERE == (
        "upper(trim(team)) = 'PRODUCTION' AND upper(trim(role)) IN ('STAFF', 'MANAGER') AND production_part IS NULL")
    from types import SimpleNamespace

    from foms.services.production.part_constants import stored_production_parts
    for parts in (None, [], ["edge"], ["cut", "edge"]):
        assert stored_production_parts(SimpleNamespace(production_part=None, production_parts=parts)) == ()
