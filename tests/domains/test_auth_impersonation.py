"""AUTH-IMPERSONATION-01: switch-user/back 감사·write guard·권한 계약 테스트.

관리자 사용자 전환(switch-user)/복귀(switch-back) route 를 정본화한다:

* **POST + 기존 write guard**: 두 route 는 POST 전용(GET 405)이며 WRITE-GUARD-01 공용
  before_request 가드(``request_write_guard.py``)의 소비자다 — CSRF/Origin 미충족 mutation 은
  핸들러 실행 전 403(``X-Write-Guard: blocked``)으로 차단된다. 이 파일은 가드를 소유하지 않고
  ``guard_on`` 픽스처로 명시 활성화만 한다(test_write_guard.py 관례 준용).
* **감사**: 전환은 original actor(진짜 관리자)와 target 을, 복귀는 back 이벤트와 전환 계정을
  각각 SecurityLog 에 기록해 추적 가능하다.
* **권한**: ADMIN 세션만 switch-user 를 수행하고, 그 외는 302 리다이렉트가 아니라 **403** 으로
  차단한다(공유 ``role_required`` 데코레이터는 delete 등에서 그대로 302 를 유지 — 대조 확인).

앱 teardown 이 세션을 close 하므로 요청 후에는 정수 id 로 재조회해 검증한다.
"""

import os

import pytest
from itsdangerous import URLSafeSerializer
from werkzeug.security import generate_password_hash

from db import db_session
from models import SecurityLog, User
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def guard_on(app):
    """이 테스트 동안만 공용 write guard 를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("WRITE_GUARD_ENABLED", sentinel)
    app.config["WRITE_GUARD_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    else:
        app.config["WRITE_GUARD_ENABLED"] = prev


def _make_user(*, username, role, team="CS", name=None):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=name or f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, uid, *, username, role):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role


def _issue_csrf(client, app):
    """클라이언트 세션에 CSRF seed 를 심고 서버가 인정할 서명 토큰을 반환한다."""
    seed = os.urandom(16).hex()
    with client.session_transaction() as sess:
        sess[_CSRF_SESSION_KEY] = seed
    return URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)


def _security_logs():
    """teardown 세션 close 후에도 안전하게 SecurityLog 전체를 재조회한다."""
    db_session.remove()
    return db_session.query(SecurityLog).all()


def _is_write_guard_block(resp):
    return resp.status_code == 403 and resp.headers.get("X-Write-Guard") == "blocked"


# --------------------------------------------------------------------------
# POST + write guard
# --------------------------------------------------------------------------
def test_switch_user_get_returns_405(client):
    """switch-user 는 POST 전용 — GET 은 405."""
    assert client.get("/switch-user/1").status_code == 405


def test_switch_back_get_returns_405(client):
    """switch-back 은 POST 전용 — GET 은 405."""
    assert client.get("/switch-back").status_code == 405


def test_switch_user_without_csrf_blocked_no_switch(client, app, guard_on):
    """가드 활성 시 CSRF 없는 switch-user POST → 403(write-guard) + 전환 발생 0."""
    admin_id = _make_user(username="root-admin", role="ADMIN")
    target_id = _make_user(username="staff-a", role="STAFF")
    _login(client, admin_id, username="root-admin", role="ADMIN")

    resp = client.post(f"/switch-user/{target_id}")

    assert _is_write_guard_block(resp), (resp.status_code, resp.headers.get("X-Write-Guard"))
    with client.session_transaction() as sess:
        assert sess["user_id"] == admin_id  # 핸들러 실행 전 차단 → 세션 미변경
        assert "impersonating_from" not in sess


# --------------------------------------------------------------------------
# 감사: original actor / target / back
# --------------------------------------------------------------------------
def test_admin_switch_records_actor_and_target_audit(client, app):
    """전환 성공 → 세션 impersonation + SecurityLog 가 original actor+target 기록."""
    admin_id = _make_user(username="root-admin2", role="ADMIN")
    target_id = _make_user(username="staff-b", role="STAFF", name="스태프비")
    _login(client, admin_id, username="root-admin2", role="ADMIN")

    resp = client.post(f"/switch-user/{target_id}")

    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_id"] == target_id
        assert sess["impersonating_from"] == admin_id

    logs = _security_logs()
    switch_rows = [
        log for log in logs
        if log.user_id == admin_id and str(target_id) in log.message
    ]
    assert switch_rows, "전환 감사(original actor=admin, target 포함)가 SecurityLog 에 없음"


def test_switch_back_records_back_audit(client, app):
    """복귀 성공 → 세션 원복 + SecurityLog 가 back 이벤트(원 관리자+전환 계정) 기록."""
    admin_id = _make_user(username="root-admin3", role="ADMIN", name="루트관리자")
    target_id = _make_user(username="staff-c", role="STAFF")
    # 전환된 상태를 직접 구성(관리자 세션 + impersonating_from)
    with client.session_transaction() as sess:
        sess["user_id"] = target_id
        sess["username"] = "staff-c"
        sess["role"] = "STAFF"
        sess["impersonating_from"] = admin_id

    resp = client.post("/switch-back")

    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_id"] == admin_id
        assert "impersonating_from" not in sess

    logs = _security_logs()
    back_rows = [
        log for log in logs
        if log.user_id == admin_id and str(target_id) in log.message
    ]
    assert back_rows, "복귀 감사(원 관리자 귀속 + 전환 계정 참조)가 SecurityLog 에 없음"


# --------------------------------------------------------------------------
# 권한: ADMIN 만 switch, 그 외 403
# --------------------------------------------------------------------------
def test_non_admin_switch_user_forbidden_403(client, app):
    """비-ADMIN 세션의 switch-user → 403(리다이렉트 아님), 전환 발생 0."""
    staff_id = _make_user(username="staff-d", role="STAFF")
    target_id = _make_user(username="staff-e", role="STAFF")
    _login(client, staff_id, username="staff-d", role="STAFF")

    resp = client.post(f"/switch-user/{target_id}")

    assert resp.status_code == 403, resp.status_code
    with client.session_transaction() as sess:
        assert sess["user_id"] == staff_id
        assert "impersonating_from" not in sess


# --------------------------------------------------------------------------
# delete 무변경 대조: 공유 role_required 는 delete 에서 여전히 302
# --------------------------------------------------------------------------
def test_delete_route_unchanged_non_admin_still_redirects(client, app):
    """대조: delete route 의 비-ADMIN 접근은 공유 role_required 로 여전히 302(403 아님).

    switch-user 만 403 으로 정본화했고 delete 로직/권한 데코레이터는 손대지 않았음을 증명.
    """
    staff_id = _make_user(username="staff-f", role="STAFF")
    victim_id = _make_user(username="staff-g", role="STAFF")
    _login(client, staff_id, username="staff-f", role="STAFF")

    resp = client.post(f"/admin/users/delete/{victim_id}")

    assert resp.status_code == 302, resp.status_code  # role_required 리다이렉트(무변경)
    assert resp.headers.get("X-Write-Guard") is None
    # 대상 유저는 삭제되지 않았다
    db_session.remove()
    assert db_session.query(User).filter_by(id=victim_id).first() is not None


def test_delete_get_returns_405(client):
    """대조: delete 는 POST 전용 유지 — GET 405(무변경)."""
    assert client.get("/admin/users/delete/1").status_code == 405


# --------------------------------------------------------------------------
# CSRF seed 가 전환 경계를 넘어 유효한지(2026-09-11 switch-back 403 회귀)
# --------------------------------------------------------------------------
def _render_token(app, *, user_id, impersonating_from=None):
    """페이지 렌더 시점의 ``{{ csrf_token() }}`` 값을 그대로 재현한다."""
    from flask import session as flask_session

    from foms.services.request_write_guard import generate_csrf_token

    with app.test_request_context():
        flask_session["user_id"] = user_id
        if impersonating_from is not None:
            flask_session["impersonating_from"] = impersonating_from
        return generate_csrf_token()


def test_switch_back_token_from_impersonated_page_is_accepted(client, app, guard_on):
    """전환 상태에서 렌더된 페이지의 토큰으로 복귀 POST → 가드 통과(403 아님)."""
    admin_id = _make_user(username="root-admin-csrf1", role="ADMIN")
    target_id = _make_user(username="staff-csrf1", role="STAFF")
    with client.session_transaction() as sess:
        sess["user_id"] = target_id
        sess["username"] = "staff-csrf1"
        sess["role"] = "STAFF"
        sess["impersonating_from"] = admin_id

    token = _render_token(app, user_id=target_id, impersonating_from=admin_id)
    resp = client.post("/switch-back", data={"csrf_token": token})

    assert not _is_write_guard_block(resp), resp.get_json()
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["user_id"] == admin_id


def test_stale_tab_token_survives_switch_back(client, app, guard_on):
    """다른 탭이 이미 복귀시킨 뒤 남은 탭이 복귀를 눌러도 403 이 아니다.

    전환 중 렌더된 토큰의 seed 는 전환 계정이 아니라 **원 관리자**에 묶이므로, 복귀로
    ``session['user_id']`` 가 바뀌어도 같은 로그인 주체의 토큰은 유효하다. 사용자에게는
    검증 실패 JSON 대신 '전환된 상태가 아닙니다' 안내가 간다.
    """
    admin_id = _make_user(username="root-admin-csrf2", role="ADMIN")
    target_id = _make_user(username="staff-csrf2", role="STAFF")
    with client.session_transaction() as sess:
        sess["user_id"] = target_id
        sess["username"] = "staff-csrf2"
        sess["role"] = "STAFF"
        sess["impersonating_from"] = admin_id

    stale_token = _render_token(app, user_id=target_id, impersonating_from=admin_id)
    # 다른 탭이 먼저 복귀
    assert client.post("/switch-back", data={"csrf_token": stale_token}).status_code == 302
    # 남은 탭(같은 토큰)이 뒤늦게 복귀 시도
    resp = client.post("/switch-back", data={"csrf_token": stale_token})

    assert not _is_write_guard_block(resp), resp.get_json()
    assert resp.status_code == 302


def test_legacy_impersonated_seed_token_still_accepted(client, app, guard_on):
    """배포 전 렌더된 구 토큰(전환 계정 seed)도 전환 중에는 계속 통과한다."""
    admin_id = _make_user(username="root-admin-csrf3", role="ADMIN")
    target_id = _make_user(username="staff-csrf3", role="STAFF")
    with client.session_transaction() as sess:
        sess["user_id"] = target_id
        sess["username"] = "staff-csrf3"
        sess["role"] = "STAFF"
        sess["impersonating_from"] = admin_id

    legacy_token = _render_token(app, user_id=target_id)  # impersonating_from 없이 파생
    resp = client.post("/switch-back", data={"csrf_token": legacy_token})

    assert not _is_write_guard_block(resp), resp.get_json()
    assert resp.status_code == 302
