"""ACCOUNT-SELF-01: 셀프 가입 승인·비밀번호 재설정 요청 큐 계약 테스트 (SQLite 도메인 레인).

스펙: docs/specs/2026-08-06-account-self-service-design.md

* 셀프 가입: 사용자 존재 시 /register 는 PENDING·VIEWER 신청을 만들고 관리자에게 알림.
  PENDING 은 비밀번호가 맞아도 로그인 불가, 승인(role·team 지정) 후 로그인 가능,
  거절은 row 삭제(재신청 허용). 부트스트랩(사용자 0명)은 기존 ADMIN·ACTIVE 즉시 생성 유지.
* 재설정 요청: username 실존 여부와 무관하게 항상 동일 성공 응답(계정 열거 방지),
  미매칭도 user_id NULL 로 기록, 매칭 사용자 PENDING 중복은 새 row 생략,
  관리자 처리(done/dismiss)로 큐 마감.

이 파일은 항상 도는 SQLite ``client``/``db_session`` 레인이다. PG 전용(server_default
backfill)은 마이그레이션 레인이 검증한다.
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Notification, PasswordResetRequest, User
from foms.services.security.account_requests import (
    APPROVAL_ACTIVE,
    APPROVAL_PENDING,
    NOTIF_ACCOUNT_RESET_REQUEST,
    NOTIF_ACCOUNT_SIGNUP,
    RESET_DISMISSED,
    RESET_DONE,
    RESET_PENDING,
)

_STRONG_PW = "Abcdef12"
_WEAK_PW = "abc"


@pytest.fixture(autouse=True)
def _reset_rate_limits(app):
    """register/재설정 요청 rate limit(FOMS_ACCOUNT_REQUEST_RATE_LIMIT) 버킷 초기화.

    limiter 의 memory storage 가 프로세스 수명 동안 유지되어 테스트 간 5/hour 버킷이
    누적된다 — 각 테스트 전에 비워 격리한다(rate limit 자체는 아래 전용 테스트가 검증).
    """
    for limiter in app.extensions.get("limiter", set()):
        limiter.reset()
    yield


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _make_user(username, *, role="STAFF", team=None, is_active=True,
               approval_status=APPROVAL_ACTIVE, raw_password=_STRONG_PW):
    """User 를 만들고 **정수 id** 를 반환한다.

    앱 요청 teardown 이 scoped session 을 remove 하므로 ORM 인스턴스를 요청 이후까지
    들고 있으면 DetachedInstanceError 가 난다 — 항상 id 로 재조회한다.
    """
    user = User(
        username=username,
        password=generate_password_hash(raw_password),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=is_active,
        approval_status=approval_status,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id):
    fresh = db_session.get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = fresh.id
        sess["username"] = fresh.username
        sess["role"] = fresh.role


def _signup(client, username, *, name="신청자", team="", password=_STRONG_PW):
    return client.post("/register", data={
        "username": username,
        "name": name,
        "team": team,
        "password": password,
        "confirm_password": password,
    }, follow_redirects=False)


# --------------------------------------------------------------------------
# 셀프 가입 신청
# --------------------------------------------------------------------------
def test_signup_creates_pending_viewer_and_notifies_admins(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    resp = _signup(client, "newbie", team="CS")
    assert resp.status_code == 302

    created = db_session.query(User).filter_by(username="newbie").first()
    assert created is not None
    assert created.role == "VIEWER"
    assert created.team == "CS"
    assert created.approval_status == APPROVAL_PENDING
    assert created.is_active is True
    # 새 계정은 항상 strong 기록
    assert created.password_policy_version == 1

    notifs = db_session.query(Notification).filter_by(
        notification_type=NOTIF_ACCOUNT_SIGNUP).all()
    assert len(notifs) == 1
    assert notifs[0].target_user_id == admin_id
    assert notifs[0].target_type == "USER"


def test_signup_rejects_weak_password_and_duplicate(client, app):
    _make_user("adm", role="ADMIN")
    resp = _signup(client, "weakling", password=_WEAK_PW)
    assert resp.status_code == 200  # 폼 재렌더
    assert db_session.query(User).filter_by(username="weakling").first() is None

    _signup(client, "taken")
    resp2 = _signup(client, "taken")
    assert resp2.status_code == 200
    assert db_session.query(User).filter_by(username="taken").count() == 1


def test_bootstrap_first_user_is_active_admin(client, app):
    """사용자 0명일 때 /register 는 기존 부트스트랩 동작(즉시 ADMIN·ACTIVE) 유지."""
    assert db_session.query(User).count() == 0
    resp = _signup(client, "firstadmin", name="최초관리자")
    assert resp.status_code == 302

    created = db_session.query(User).filter_by(username="firstadmin").first()
    assert created.role == "ADMIN"
    assert created.approval_status == APPROVAL_ACTIVE
    # 부트스트랩은 알림 생성 없음
    assert db_session.query(Notification).count() == 0


# --------------------------------------------------------------------------
# PENDING 로그인 게이트
# --------------------------------------------------------------------------
def test_pending_user_cannot_login_until_approved(client, app):
    _make_user("adm", role="ADMIN")
    _signup(client, "waiting")

    resp = client.post("/login", data={
        "username": "waiting", "password": _STRONG_PW,
    }, follow_redirects=False)
    assert resp.status_code == 200  # 로그인 폼 재렌더(세션 미생성)
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_wrong_password_on_pending_does_not_reveal_status(client, app):
    """비밀번호 오답이면 승인 대기 여부를 노출하지 않는다(일반 불일치 메시지)."""
    _make_user("adm", role="ADMIN")
    _signup(client, "waiting2")
    resp = client.post("/login", data={
        "username": "waiting2", "password": "Wrongpw99",
    })
    body = resp.get_data(as_text=True)
    assert "승인 대기" not in body


# --------------------------------------------------------------------------
# 승인 / 거절
# --------------------------------------------------------------------------
def test_admin_approve_assigns_role_team_and_enables_login(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    _signup(client, "joiner", team="CS")
    pending_id = db_session.query(User).filter_by(username="joiner").first().id

    _login(client, admin_id)
    resp = client.post(f"/admin/users/approve/{pending_id}", data={
        "role": "STAFF", "team": "SALES",
    }, follow_redirects=False)
    assert resp.status_code == 302

    approved = db_session.get(User, pending_id)
    assert approved.approval_status == APPROVAL_ACTIVE
    assert approved.role == "STAFF"
    assert approved.team == "SALES"

    # 승인 후 로그인 성공
    client.get("/logout")
    with client.session_transaction() as sess:
        sess.clear()
    login_resp = client.post("/login", data={
        "username": "joiner", "password": _STRONG_PW,
    }, follow_redirects=False)
    assert login_resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id") == pending_id


def test_admin_reject_deletes_pending_row(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    _signup(client, "rejected")
    pending_id = db_session.query(User).filter_by(username="rejected").first().id

    _login(client, admin_id)
    resp = client.post(f"/admin/users/reject/{pending_id}", follow_redirects=False)
    assert resp.status_code == 302
    assert db_session.get(User, pending_id) is None


def test_approve_rejects_non_pending_and_invalid_role(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    active_id = _make_user("already", role="STAFF")
    # 가입 신청은 로그인 전에 접수(로그인 상태의 /register 는 홈으로 redirect)
    _signup(client, "badrole")
    pid = db_session.query(User).filter_by(username="badrole").first().id

    _login(client, admin_id)
    client.post(f"/admin/users/approve/{active_id}", data={"role": "MANAGER"})
    assert db_session.get(User, active_id).role == "STAFF"  # 비대상 무변경

    client.post(f"/admin/users/approve/{pid}", data={"role": "SUPERROOT"})
    assert db_session.get(User, pid).approval_status == APPROVAL_PENDING


def test_approve_requires_admin_role(client, app):
    _make_user("adm", role="ADMIN")
    staff_id = _make_user("plainstaff", role="STAFF")
    _signup(client, "target")
    pid = db_session.query(User).filter_by(username="target").first().id

    _login(client, staff_id)
    client.post(f"/admin/users/approve/{pid}", data={"role": "ADMIN"})
    assert db_session.get(User, pid).approval_status == APPROVAL_PENDING


# --------------------------------------------------------------------------
# 비밀번호 재설정 요청 큐
# --------------------------------------------------------------------------
def test_reset_request_same_response_for_unknown_and_known(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    known_id = _make_user("knownuser", role="STAFF")

    r1 = client.post("/password-reset/request", data={"username": "knownuser"},
                     follow_redirects=False)
    r2 = client.post("/password-reset/request", data={"username": "ghostuser"},
                     follow_redirects=False)
    # 열거 방지: 둘 다 동일하게 로그인으로 redirect
    assert r1.status_code == r2.status_code == 302
    assert r1.headers["Location"] == r2.headers["Location"]

    rows = db_session.query(PasswordResetRequest).order_by(
        PasswordResetRequest.id).all()
    assert len(rows) == 2
    assert rows[0].user_id == known_id
    assert rows[1].user_id is None
    assert rows[1].username_submitted == "ghostuser"
    assert all(r.status == RESET_PENDING for r in rows)

    notifs = db_session.query(Notification).filter_by(
        notification_type=NOTIF_ACCOUNT_RESET_REQUEST).all()
    assert len(notifs) == 2
    assert all(n.target_user_id == admin_id for n in notifs)


def test_reset_request_dedups_pending_for_same_user(client, app):
    _make_user("adm", role="ADMIN")
    _make_user("dupuser", role="STAFF")
    client.post("/password-reset/request", data={"username": "dupuser"})
    client.post("/password-reset/request", data={"username": "dupuser"})
    assert db_session.query(PasswordResetRequest).count() == 1


def test_admin_handles_reset_request_done_and_dismiss(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    _make_user("resetme", role="STAFF")
    client.post("/password-reset/request", data={"username": "resetme"})
    client.post("/password-reset/request", data={"username": "nobody-x"})
    row_done, row_dismiss = db_session.query(PasswordResetRequest).order_by(
        PasswordResetRequest.id).all()
    done_id, dismiss_id = row_done.id, row_dismiss.id

    _login(client, admin_id)
    client.post(f"/admin/password-reset/{done_id}/handle", data={"action": "done"})
    client.post(f"/admin/password-reset/{dismiss_id}/handle", data={"action": "dismiss"})

    done_row = db_session.get(PasswordResetRequest, done_id)
    dismiss_row = db_session.get(PasswordResetRequest, dismiss_id)
    assert done_row.status == RESET_DONE
    assert dismiss_row.status == RESET_DISMISSED
    assert done_row.handled_by_user_id == admin_id
    assert done_row.handled_at is not None

    # 이미 처리된 요청 재처리는 no-op
    client.post(f"/admin/password-reset/{done_id}/handle", data={"action": "dismiss"})
    assert db_session.get(PasswordResetRequest, done_id).status == RESET_DONE


def test_register_post_rate_limited(client, app):
    """가입 POST 는 FOMS_ACCOUNT_REQUEST_RATE_LIMIT(기본 5/hour)로 제한된다."""
    _make_user("adm", role="ADMIN")
    for i in range(5):
        _signup(client, f"bulk{i}")
    resp = _signup(client, "bulk-over")
    assert resp.status_code == 429
    assert db_session.query(User).filter_by(username="bulk-over").first() is None
    # GET(폼)은 제한하지 않는다
    assert client.get("/register").status_code == 200


def test_user_list_shows_pending_and_reset_sections(client, app):
    admin_id = _make_user("adm", role="ADMIN")
    _signup(client, "queueduser", name="대기자")
    client.post("/password-reset/request", data={"username": "adm"})

    _login(client, admin_id)
    resp = client.get("/admin/users")
    body = resp.get_data(as_text=True)
    assert "가입 승인 대기" in body
    assert "queueduser" in body
    assert "비밀번호 재설정 요청" in body
