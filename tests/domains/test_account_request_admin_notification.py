"""NOTIF-ROLE-01: 계정 요청 관리자 알림이 사건 1건 = Notification 1건인지 검증.

회귀 배경: 가입 신청·비밀번호 재설정 요청 알림이 활성 ADMIN 수만큼 별개 Notification
row 로 복제돼 왔다(관리자 5명 = 알림 5건). 알림 SSOT 는 공유 Notification 1건 +
수신자별 ``notification_user_states`` 이므로 ``target_type='ROLE'`` +
``target_role='ADMIN'`` 경로로 되돌린다.

계약:
1. 계정 이벤트 1건 -> Notification row **1건**(관리자 수와 무관).
2. 그 row 는 ``target_type='ROLE'``, ``target_role='ADMIN'``, ``target_user_id`` 없음.
3. 활성 ADMIN 이 0명이면 아무도 못 받을 알림 row 를 만들지 않는다(고아 알림 방지).

수신자 state 수는 ``recipients.resolve_recipients_for_notification`` 의 ROLE 해석
계약이라 이 파일에서 단언하지 않는다(해당 담당 테스트 몫).
"""
from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Notification, User
from foms.services.security.account_requests import (
    APPROVAL_ACTIVE,
    NOTIF_ACCOUNT_RESET_REQUEST,
    NOTIF_ACCOUNT_SIGNUP,
    notify_admins_account_event,
    submit_password_reset_request,
)

_STRONG_PW = "Abcdef12"


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


def _mk_user(username, *, role="STAFF", is_active=True):
    """테스트용 User 를 만들고 flush 후 인스턴스를 돌려준다."""
    user = User(
        username=username,
        password=generate_password_hash(_STRONG_PW),
        role=role,
        name=f"{username}-name",
        is_active=is_active,
        approval_status=APPROVAL_ACTIVE,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _notifs(notification_type):
    return (
        db_session.query(Notification)
        .filter_by(notification_type=notification_type)
        .all()
    )


def _assert_role_admin_contract(notif):
    """ROLE 타깃 계약(대상 지정 3필드)을 단언한다."""
    assert notif.target_type == "ROLE"
    assert notif.target_role == "ADMIN"
    assert notif.target_user_id is None


def test_account_event_creates_single_role_notification(db):
    """활성 ADMIN 이 3명이어도 계정 이벤트 알림 row 는 1건이다."""
    for idx in range(3):
        _mk_user(f"nrole_adm{idx}", role="ADMIN")
    _mk_user("nrole_staff", role="STAFF")

    notify_admins_account_event(
        db,
        notification_type=NOTIF_ACCOUNT_SIGNUP,
        title="새 가입 신청",
        message="본문",
    )

    rows = _notifs(NOTIF_ACCOUNT_SIGNUP)
    assert len(rows) == 1  # 과거엔 관리자 수(3)만큼 복제됐다
    _assert_role_admin_contract(rows[0])
    assert rows[0].title == "새 가입 신청"


def test_signup_request_notifies_admins_with_one_row(client, app):
    """/register 가입 신청 1건 -> ROLE 알림 1건(관리자 2명)."""
    for idx in range(2):
        _mk_user(f"nrole_sig_adm{idx}", role="ADMIN")
    db_session.commit()

    resp = client.post("/register", data={
        "username": "nrole_newbie",
        "name": "신청자",
        "team": "CS",
        "password": _STRONG_PW,
        "confirm_password": _STRONG_PW,
    }, follow_redirects=False)
    assert resp.status_code == 302

    rows = _notifs(NOTIF_ACCOUNT_SIGNUP)
    assert len(rows) == 1
    _assert_role_admin_contract(rows[0])


def test_password_reset_request_notifies_admins_with_one_row(db):
    """비밀번호 재설정 요청도 같은 ROLE 계약을 따른다."""
    for idx in range(3):
        _mk_user(f"nrole_rst_adm{idx}", role="ADMIN")
    _mk_user("nrole_target", role="STAFF")

    _row, created = submit_password_reset_request(db, "nrole_target")

    assert created is True
    rows = _notifs(NOTIF_ACCOUNT_RESET_REQUEST)
    assert len(rows) == 1
    _assert_role_admin_contract(rows[0])


def test_no_active_admin_creates_no_notification(db):
    """활성 ADMIN 0명(비활성 ADMIN·타 role 만) -> 알림 row 0건, 반환 0."""
    _mk_user("nrole_dead_adm", role="ADMIN", is_active=False)
    _mk_user("nrole_lonely_staff", role="STAFF")

    created_states = notify_admins_account_event(
        db,
        notification_type=NOTIF_ACCOUNT_SIGNUP,
        title="새 가입 신청",
        message="본문",
    )

    assert created_states == 0
    assert db_session.query(Notification).count() == 0


def test_reset_request_without_active_admin_still_records_row(db):
    """관리자가 없어도 재설정 요청 row 자체는 남는다(알림만 생략)."""
    from models import PasswordResetRequest

    _mk_user("nrole_noadm_target", role="STAFF")

    _row, created = submit_password_reset_request(db, "nrole_noadm_target")

    assert created is True
    assert db_session.query(PasswordResetRequest).count() == 1
    assert db_session.query(Notification).count() == 0
