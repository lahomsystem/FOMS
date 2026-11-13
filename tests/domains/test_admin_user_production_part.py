"""PRODPART-00(P15-2): 관리자 사용자 추가 · 수정 화면의 '생산 파트' 칸 시험(SQLite 레인).

설계 정본: ``docs/specs/2026-11-09-tablet-production-ui_SPEC.md`` §15.3(계정 파트 칸 — 생산팀이 아니면 저장 때
비움 · 세션은 안 끊음 · 감사 스냅샷) · §15.7(관리자 화면). 앱 teardown 이 세션을 닫으므로 요청 뒤에는 정수 id 로
다시 읽는다.
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.security.session_guard import pin_session
from foms.web.auth.routes import _AUDITED_USER_FIELDS, _user_audit_snapshot
from models import SecurityLog, User

_STRONG_PW = "Abcdef12"
_seq = 0


@pytest.fixture(autouse=True)
def _reset_rate_limits(app):
    """사용자 추가 등 한도 버킷이 프로세스 수명 동안 쌓인다 — 시험마다 비운다."""
    for limiter in app.extensions.get("limiter", set()):
        limiter.reset()
    yield


def _make_user(*, role: str = "STAFF", team: str | None = "PRODUCTION", part: str | None = None) -> int:
    global _seq
    _seq += 1
    user = User(
        username=f"ppart_{_seq}", password=generate_password_hash(_STRONG_PW), role=role, team=team,
        name=f"파트{_seq}", is_active=True, production_part=part,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _user(uid: int) -> User:
    db_session.remove()
    return db_session.get(User, uid)


def _login(client, uid: int) -> None:
    """로그인 라우트와 같은 세션 값을 심는다(pin_session 포함 — 세션 끊기 판정이 실제로 돈다)."""
    user = _user(uid)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
        pin_session(sess, user)


def _admin_client(app):
    admin = app.test_client()
    _login(admin, _make_user(role="ADMIN", team="CS"))
    return admin


def _edit(client, uid: int, **fields):
    target = _user(uid)
    data = {"username": target.username, "name": target.name, "role": target.role, "team": target.team or "",
            "is_active": "on"}
    data.update(fields)
    return client.post(f"/admin/users/edit/{uid}", data=data, follow_redirects=False)


# --------------------------------------------------------------------------- #
# 저장
# --------------------------------------------------------------------------- #
def test_admin_saves_part_for_production_user(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    resp = _edit(admin, uid, production_part="cut")
    assert resp.status_code == 302, resp.get_data(as_text=True)[:400]
    assert _user(uid).production_part == "cut"

    resp = _edit(admin, uid, production_part="")
    assert resp.status_code == 302
    assert _user(uid).production_part is None  # '없음' 을 고르면 비운다


def test_non_production_team_gets_null_even_when_part_sent(app):
    admin = _admin_client(app)
    uid = _make_user(team="CS")
    resp = _edit(admin, uid, production_part="assemble")
    assert resp.status_code == 302
    assert _user(uid).production_part is None


def test_moving_out_of_production_team_clears_part(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION", part="edge")
    resp = _edit(admin, uid, team="SALES", production_part="edge")
    assert resp.status_code == 302
    saved = _user(uid)
    assert (saved.team, saved.production_part) == ("SALES", None)


@pytest.mark.parametrize("bad", ["paint", "재단", "CUT;DROP"])
def test_unknown_part_is_rejected_and_nothing_saved(app, bad):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION", part="cut")
    resp = _edit(admin, uid, production_part=bad, name="바뀌면 안 됨")
    assert resp.status_code == 200  # 저장하지 않고 화면을 다시 그린다
    assert "알 수 없는 생산 파트" in resp.get_data(as_text=True)
    saved = _user(uid)
    assert saved.production_part == "cut"
    assert saved.name != "바뀌면 안 됨"


def test_add_user_saves_part_only_for_production(app):
    admin = _admin_client(app)
    base = {"password": _STRONG_PW, "name": "새 재단", "role": "STAFF", "production_part": "cut"}
    resp = admin.post("/admin/users/add", data={**base, "username": "new_cut", "team": "PRODUCTION"})
    assert resp.status_code == 302, resp.get_data(as_text=True)[:400]
    resp = admin.post("/admin/users/add", data={**base, "username": "new_cs", "team": "CS"})
    assert resp.status_code == 302
    db_session.remove()
    parts = {u.username: u.production_part for u in db_session.query(User).filter(User.username.in_(["new_cut", "new_cs"]))}
    assert parts == {"new_cut": "cut", "new_cs": None}


def test_add_user_rejects_unknown_part(app):
    admin = _admin_client(app)
    resp = admin.post("/admin/users/add", data={
        "username": "new_bad", "password": _STRONG_PW, "name": "잘못", "role": "STAFF", "team": "PRODUCTION",
        "production_part": "paint",
    })
    assert resp.status_code == 200
    assert "알 수 없는 생산 파트" in resp.get_data(as_text=True)
    db_session.remove()
    assert db_session.query(User).filter_by(username="new_bad").count() == 0


# --------------------------------------------------------------------------- #
# 세션 · 감사
# --------------------------------------------------------------------------- #
def test_part_change_keeps_target_session_but_team_change_kills_it(app, client):
    uid = _make_user(team="PRODUCTION")
    _login(client, uid)
    admin = _admin_client(app)

    assert _edit(admin, uid, production_part="inspect").status_code == 302
    assert client.get("/profile").status_code == 200  # 파트만 바뀌면 그대로 로그인

    assert _edit(admin, uid, team="CS", production_part="").status_code == 302
    assert client.get("/profile").status_code != 200  # 대조군: 팀이 바뀌면 끊긴다


def test_audit_snapshot_and_log_include_part(app):
    assert "production_part" in _AUDITED_USER_FIELDS
    uid = _make_user(team="PRODUCTION")
    assert _user_audit_snapshot(_user(uid))["production_part"] is None

    admin = _admin_client(app)
    assert _edit(admin, uid, production_part="assemble").status_code == 302
    db_session.remove()
    messages = [row.message for row in db_session.query(SecurityLog).order_by(SecurityLog.id)]
    edits = [m for m in messages if f"사용자 #{uid} 수정:" in m]
    assert edits == [f"사용자 #{uid} 수정: production_part 미지정→assemble"], messages
    row = db_session.query(SecurityLog).filter(SecurityLog.action == "USER_UPDATE", SecurityLog.target_id == uid).one()
    assert row.detail["changes"] == {"production_part": {"from": None, "to": "assemble"}}


# --------------------------------------------------------------------------- #
# 화면
# --------------------------------------------------------------------------- #
def test_edit_and_add_forms_render_part_select(app):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION", part="edge")
    html = admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    assert 'name="production_part"' in html
    assert '<option value="edge" selected>엣지' in html
    for label in ("없음", "재단", "엣지", "조립", "검수"):
        assert label in html
    assert "생산팀일 때만 쓰여요" in html

    add_html = admin.get("/admin/users/add").get_data(as_text=True)
    assert 'name="production_part"' in add_html
    assert '<option value="inspect">검수</option>' in add_html


def test_user_list_appends_part_to_team_text(app):
    admin = _admin_client(app)
    _make_user(team="PRODUCTION", part="cut")
    _make_user(team="CS", part="assemble")  # 대조군: 팀을 다른 데서 바꿔 값이 남아도 생산팀이 아니면 안 붙는다
    _make_user(team="PRODUCTION", part=None)  # 대조군: 파트 없는 생산팀은 팀 글 그대로
    html = admin.get("/admin/users").get_data(as_text=True)
    assert "<td>생산팀 · 재단</td>" in html
    assert "· 조립" not in html
    assert "<td>생산팀</td>" in html


# --------------------------------------------------------------------------- #
# 문 — 관리자가 아니면 막힌다(기존 문 그대로)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", ["MANAGER", "STAFF", "VIEWER"])
def test_non_admin_cannot_set_part(app, client, role):
    actor = _make_user(role=role, team="PRODUCTION")
    _login(client, actor)
    uid = _make_user(team="PRODUCTION")
    resp = _edit(client, uid, production_part="cut")
    assert resp.status_code == 302
    assert "/admin/users" not in resp.headers["Location"]  # 관리 화면이 아니라 자기 첫 화면으로 돌려보냄
    assert _user(uid).production_part is None
    assert client.get(f"/admin/users/edit/{uid}").status_code == 302
    assert client.post("/admin/users/add", data={
        "username": f"sneak_{role}", "password": _STRONG_PW, "name": "몰래", "role": "STAFF", "team": "PRODUCTION",
        "production_part": "cut",
    }).status_code == 302
    db_session.remove()
    assert db_session.query(User).filter_by(username=f"sneak_{role}").count() == 0


def test_admin_control_reaches_edit_form(app):
    """대조군: 같은 요청을 관리자가 하면 화면이 열린다(위 막힘이 시험 준비 탓이 아님)."""
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert admin.get(f"/admin/users/edit/{uid}").status_code == 200
