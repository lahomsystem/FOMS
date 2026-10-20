"""세션 끊기 — 로그아웃·비밀번호·역할 변경·대리 로그인 (SPEC 2026-10-20-session-revoke).

쿠키를 복사해 둔 두 번째 클라이언트로 "옛 쿠키" 를 흉내 낸다. 앱 teardown 이 세션을 닫으므로
요청 뒤에는 정수 id 로 다시 읽는다.
"""

import re
import subprocess
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.security.session_guard import pin_session
from foms.services.security.password_policy import set_strong_password
from models import SecurityLog, User

ROOT = Path(__file__).resolve().parents[2]
_STRONG = "Zx9!session-revoke"
_seq = 0


def _make_user(role="STAFF", team="CS"):
    global _seq
    _seq += 1
    user = User(username=f"rev_{_seq}", password=generate_password_hash("pw"), role=role,
                team=team, name=f"rev-{_seq}", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _user(uid):
    db_session.remove()
    return db_session.get(User, uid)


def _login(client, uid):
    """로그인 라우트와 같은 세션 값을 심는다(pin_session 포함)."""
    user = _user(uid)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
        pin_session(sess, user)


def _clone(app, client):
    """같은 세션 쿠키를 든 두 번째 클라이언트(복사된 쿠키)."""
    name = app.config.get("SESSION_COOKIE_NAME") or "session"
    cookie = client.get_cookie(name)
    other = app.test_client()
    other.set_cookie(name, cookie.value)
    return other


def _logged_in(client):
    resp = client.get("/profile")
    return resp.status_code == 200


def test_logout_revokes_copied_cookie_but_not_other_devices(app, client):
    uid = _make_user()
    _login(client, uid)
    copied = _clone(app, client)
    other_device = app.test_client()
    _login(other_device, uid)
    assert _logged_in(copied) and _logged_in(other_device)

    client.post("/logout")

    assert not _logged_in(copied)
    assert _logged_in(other_device)


def test_password_reset_kills_all_sessions(app, client):
    uid = _make_user()
    _login(client, uid)
    assert _logged_in(client)

    user = _user(uid)
    set_strong_password(user, _STRONG)
    db_session.commit()

    assert not _logged_in(client)


def test_own_password_change_keeps_current_session(app, client):
    uid = _make_user()
    _login(client, uid)
    other_device = app.test_client()
    _login(other_device, uid)

    resp = client.post("/profile", data={"name": "새이름", "current_password": "pw",
                                         "new_password": _STRONG, "confirm_password": _STRONG})
    assert resp.status_code == 302

    assert _logged_in(client)
    assert not _logged_in(other_device)


def test_role_change_by_admin_kills_sessions(app, client):
    uid = _make_user(role="ADMIN", team="CS")
    _login(client, uid)
    admin_id = _make_user(role="ADMIN", team="CS")
    admin = app.test_client()
    _login(admin, admin_id)

    target = _user(uid)
    resp = admin.post(f"/admin/users/edit/{uid}", data={
        "name": target.name, "role": "STAFF", "team": "CS", "is_active": "on"})
    assert resp.status_code in (200, 302)
    assert _user(uid).role == "STAFF"

    assert not _logged_in(client)
    assert _logged_in(admin)


def test_legacy_session_without_version_still_valid(app, client):
    """배포 전 로그인한 세션(sv·sid 없음)은 그대로 통과하고, 쿠키를 다시 쓰지 않는다."""
    uid = _make_user()
    user = _user(uid)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    assert _logged_in(client)
    with client.session_transaction() as sess:
        assert "sid" not in sess


def test_legacy_session_logout_kills_copies(app, client):
    """표지 없는 옛 세션의 로그아웃은 그 계정 세션을 모두 끊는다(골라 끊을 수 없어서)."""
    uid = _make_user()
    user = _user(uid)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    copied = _clone(app, client)
    assert _logged_in(copied)

    client.post("/logout")

    assert not _logged_in(copied)


def _switch(admin_client, target_id):
    return admin_client.post(f"/switch-user/{target_id}")


def test_impersonation_dies_when_admin_deactivated(app, client):
    admin_id = _make_user(role="ADMIN")
    target_id = _make_user()
    _login(client, admin_id)
    assert _switch(client, target_id).status_code == 302
    assert _logged_in(client)

    admin = _user(admin_id)
    admin.is_active = False
    db_session.commit()

    assert not _logged_in(client)


def test_impersonation_dies_when_admin_password_changes(app, client):
    admin_id = _make_user(role="ADMIN")
    target_id = _make_user()
    _login(client, admin_id)
    _switch(client, target_id)

    admin = _user(admin_id)
    set_strong_password(admin, _STRONG)
    db_session.commit()

    assert not _logged_in(client)


def test_impersonation_switch_back_keeps_admin_session(app, client):
    admin_id = _make_user(role="ADMIN")
    target_id = _make_user()
    _login(client, admin_id)
    _switch(client, target_id)

    assert client.post("/switch-back").status_code == 302
    assert _logged_in(client)
    with client.session_transaction() as sess:
        assert sess["user_id"] == admin_id
        assert "impersonator_sv" not in sess


def test_audit_during_impersonation_names_admin(app):
    from flask import session

    from foms.web.auth import log_access

    admin_id = _make_user(role="ADMIN")
    target_id = _make_user()
    with app.test_request_context("/"):
        session["user_id"] = target_id
        session["impersonating_from"] = admin_id
        log_access("전환 중 행위", target_id, action="TEST_IMPERSONATED")
        log_access("관리자 본인 행위", admin_id, action="TEST_ADMIN_SELF")

    db_session.remove()
    rows = {r.action: r for r in db_session.query(SecurityLog)
            .filter(SecurityLog.action.in_(["TEST_IMPERSONATED", "TEST_ADMIN_SELF"]))}
    assert (rows["TEST_IMPERSONATED"].detail or {}).get("impersonated_by") == admin_id
    assert "impersonated_by" not in (rows["TEST_ADMIN_SELF"].detail or {})


def test_no_session_role_reads_in_app_code():
    """역할 판정은 DB 사용자 역할로 — 쿠키 안 session['role'] 읽기 0."""
    out = subprocess.run(["git", "grep", "-nE", r"session(\.get\(|\[)['\"]role['\"]", "--", "foms"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    reads = [ln for ln in out.splitlines() if not re.search(r"session\[['\"]role['\"]\]\s*=", ln)]
    assert not reads, reads
