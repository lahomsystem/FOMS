"""INACTIVE-SESSION-01: 비활성화(퇴사 처리)된 계정의 기존 세션은 모든 경로에서 바로 끊긴다.

스펙 docs/specs/2026-10-19-inactive-user-session-gate_SPEC.md.

예전에는 활성 여부를 ``login_required`` 장식만 봤다. 그래서 장식 없이 핸들러 안에서
``g.current_user`` 만 보는 경로(ops 조회 2종), 쓰기 정책 가드(``evaluate_policy``),
실시간 연결(Socket.IO connect)은 비활성 계정의 세션을 그대로 받아 줬다. 이제
``_set_current_user`` 가 요청 시작 한 곳에서 세션을 비우고, 정책 엔진과 실시간 연결은
같은 규칙을 따로 한 번 더 둔다.

각 경로마다 활성 사용자 대조군을 같이 둔다 — 거부만 보면 "언제나 거부" 하는 회귀도 통과한다.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from itsdangerous import URLSafeSerializer
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.orders.order_mutation_policy import (
    POLICY_REGISTRY,
    evaluate_policy,
    user_can,
)
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from models import Order, User

BADGE_URL = "/erp/api/notifications/badge"  # @login_required 장식 경로
DRIFT_URL = "/api/foms/ops/drift-audit"  # 핸들러 안에서 g.current_user 만 본다(ADMIN)
HEARTBEAT_URL = "/api/foms/ops/worker-heartbeats"  # 같은 방식(ADMIN)
IN_HANDLER_URLS = [DRIFT_URL, HEARTBEAT_URL]


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
def _config_toggle(app, key):
    """config ``key`` 를 이 테스트 동안만 True 로 두고 원복하는 제너레이터."""
    sentinel = object()
    prev = app.config.get(key, sentinel)
    app.config[key] = True
    yield
    if prev is sentinel:
        app.config.pop(key, None)
    else:
        app.config[key] = prev


@pytest.fixture
def policy_on(app):
    """정책 가드(AUTH-01)를 이 테스트 동안만 켠다."""
    yield from _config_toggle(app, "AUTH_POLICY_ENABLED")


@pytest.fixture
def guard_on(app):
    """공용 write guard(WRITE-GUARD-01)를 이 테스트 동안만 켠다."""
    yield from _config_toggle(app, "WRITE_GUARD_ENABLED")


def _make_user(username, *, role="STAFF", team="CS"):
    """활성 사용자 1명을 만들고 id 를 돌려준다."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, uid, *, username="u", role="STAFF"):
    """세션을 심는다(permanent + last-seen 창 안 → 활성 요청은 세션을 쓰지 않는다)."""
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
        sess.permanent = True
        sess["last_seen_touch_ts"] = time.time()


def _deactivate(uid):
    """관리자 퇴사 처리와 같은 결과 — 행은 남고 ``is_active`` 만 False."""
    user = db_session.get(User, uid)
    user.is_active = False
    db_session.commit()


def _session_user_id(client):
    with client.session_transaction() as sess:
        return sess.get("user_id")


def _create_order():
    order = Order(
        received_date="2026-10-19",
        customer_name="비활성 세션 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _calls_of(oid):
    db_session.remove()
    order = db_session.query(Order).filter_by(id=oid).first()
    return (order.structured_data or {}).get("calls")


def _issue_csrf(client, app):
    """세션에 CSRF seed 를 심고 서버가 인정할 서명 토큰을 돌려준다(test_write_guard 준용)."""
    seed = os.urandom(16).hex()
    with client.session_transaction() as sess:
        sess[_CSRF_SESSION_KEY] = seed
    return URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)


def _stale():
    return datetime(2026, 1, 1, 9, 0, 0)


def _stored_last_login(uid):
    """요청 세션과 무관하게 DB 에 실제로 남은 값을 읽는다."""
    with engine.connect() as conn:
        return conn.execute(
            User.__table__.select().where(User.__table__.c.id == uid)
        ).mappings().one()["last_login"]


# --------------------------------------------------------------------------
# 1. 장식 경로(@login_required)
# --------------------------------------------------------------------------
def test_decorated_route_active_user_ok(client, app):
    """대조군: 활성 사용자는 장식 경로를 그대로 쓴다."""
    uid = _make_user("isg-deco-active")
    _login(client, uid)

    resp = client.get(BADGE_URL)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True
    assert _session_user_id(client) == uid


def test_decorated_route_requires_login_after_deactivation(client, app):
    """비활성화 뒤 같은 세션 → 로그인으로 보내고 세션을 비운다."""
    uid = _make_user("isg-deco-inactive")
    _login(client, uid)
    _deactivate(uid)

    resp = client.get(BADGE_URL)

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    assert _session_user_id(client) is None


# --------------------------------------------------------------------------
# 2. 핸들러 안에서 g.current_user 만 보는 경로(장식 없음)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("url", IN_HANDLER_URLS)
def test_in_handler_route_active_admin_ok(client, app, url):
    """대조군: 활성 ADMIN 은 200."""
    uid = _make_user(f"isg-admin-active-{url.rsplit('/', 1)[-1]}", role="ADMIN", team=None)
    _login(client, uid, role="ADMIN")

    resp = client.get(url)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True


@pytest.mark.parametrize("url", IN_HANDLER_URLS)
def test_in_handler_route_401_after_deactivation(client, app, url):
    """비활성 ADMIN 의 남은 세션 → 401(예전에는 장식이 없어 200 으로 운영 통계를 받았다)."""
    uid = _make_user(f"isg-admin-inactive-{url.rsplit('/', 1)[-1]}", role="ADMIN", team=None)
    _login(client, uid, role="ADMIN")
    _deactivate(uid)

    resp = client.get(url)

    assert resp.status_code == 401, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False
    assert _session_user_id(client) is None


def test_unknown_user_id_session_is_cleared(client, app):
    """행이 없는 user_id 세션도 같은 규칙 — 401 이고 세션이 비워진다."""
    _login(client, 999_999, role="ADMIN")

    resp = client.get(DRIFT_URL)

    assert resp.status_code == 401
    assert _session_user_id(client) is None


# --------------------------------------------------------------------------
# 3. 정책 가드를 거치는 쓰기 경로
# --------------------------------------------------------------------------
def test_policy_guarded_write_active_user_passes(client, app, policy_on):
    """대조군: 정책 가드를 켜도 활성 CS 직원의 통화 기록은 저장된다."""
    uid = _make_user("isg-write-active")
    _login(client, uid)
    oid = _create_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") is None
    assert _calls_of(oid)[0]["result"] == "connected"


def test_policy_guarded_write_401_after_deactivation(client, app, policy_on):
    """비활성화 뒤 쓰기 → 정책 가드가 핸들러 전에 401(AUTH_REQUIRED). DB 변화 0."""
    uid = _make_user("isg-write-inactive")
    _login(client, uid)
    oid = _create_order()
    _deactivate(uid)

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})

    assert resp.status_code == 401, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") == "denied"
    assert resp.get_json()["code"] == "AUTH_REQUIRED"
    assert _calls_of(oid) is None


def test_both_guards_active_user_write_passes(client, app, policy_on, guard_on):
    """대조군: 운영과 같이 두 가드를 다 켜도 활성 사용자는 유효 토큰으로 저장한다."""
    uid = _make_user("isg-both-active")
    _login(client, uid)
    oid = _create_order()
    token = _issue_csrf(client, app)

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected"},
        headers={"X-CSRF-Token": token},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _calls_of(oid)[0]["result"] == "connected"


def test_both_guards_inactive_write_blocked_before_handler(client, app, policy_on, guard_on):
    """두 가드를 다 켜면 write guard 가 정책 가드보다 먼저 돈다.

    세션이 비워져 활성 때 받은 토큰도 더는 맞지 않으므로 write guard 의 403 으로 막힌다.
    상태 코드는 401 이 아니지만 핸들러 전 차단(DB 변화 0)이고, 다음 화면 이동은 로그인으로 간다.
    """
    uid = _make_user("isg-both-inactive")
    _login(client, uid)
    oid = _create_order()
    token = _issue_csrf(client, app)
    _deactivate(uid)

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected"},
        headers={"X-CSRF-Token": token},
    )

    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.headers.get("X-Write-Guard") == "blocked"
    assert _calls_of(oid) is None
    assert _session_user_id(client) is None


# --------------------------------------------------------------------------
# 4. 정책 엔진 직접 호출
# --------------------------------------------------------------------------
def test_evaluate_policy_treats_inactive_user_as_unauthenticated(app):
    """엔진을 직접 부르는 경로도 비활성 계정을 미인증(None)과 같은 답으로 받는다."""
    policy = POLICY_REGISTRY["ERP_EDIT"]
    active = SimpleNamespace(id=1, role="ADMIN", team=None, is_active=True)
    inactive = SimpleNamespace(id=1, role="ADMIN", team=None, is_active=False)

    assert evaluate_policy(policy, active).allowed  # 대조군
    decision = evaluate_policy(policy, inactive)
    anonymous = evaluate_policy(policy, None)
    assert (decision.allowed, decision.status, decision.code) == (False, 401, "AUTH_REQUIRED")
    assert (decision.allowed, decision.status, decision.code, decision.reason) == (
        anonymous.allowed, anonymous.status, anonymous.code, anonymous.reason,
    )
    assert user_can("ERP_EDIT", active) is True
    assert user_can("ERP_EDIT", inactive) is False


def test_evaluate_policy_anonymous_policy_same_for_inactive_and_none(app):
    """익명 허용 정책(가입 화면 등)은 미인증과 같이 비활성 계정에도 열린다 — 규칙이 하나다."""
    policy = POLICY_REGISTRY["ACCOUNT_ANON"]
    inactive = SimpleNamespace(id=1, role="STAFF", team="CS", is_active=False)

    assert evaluate_policy(policy, None).allowed is True
    assert evaluate_policy(policy, inactive).allowed is True


# --------------------------------------------------------------------------
# 5. 실시간 연결(Socket.IO connect — before_request 를 거치지 않는다)
# --------------------------------------------------------------------------
def _ws_client(app, uid):
    from app import socketio

    http = app.test_client()
    with http.session_transaction() as sess:
        sess["user_id"] = uid
    return socketio.test_client(app, flask_test_client=http)


def test_socketio_accepts_active_user(app):
    """대조군: 활성 사용자는 연결된다."""
    uid = _make_user("isg-ws-active")

    ws = _ws_client(app, uid)
    try:
        assert ws.is_connected() is True
    finally:
        if ws.is_connected():
            ws.disconnect()


def test_socketio_refuses_inactive_user(app):
    """비활성 사용자의 남은 세션은 연결을 거부한다."""
    uid = _make_user("isg-ws-inactive")
    _deactivate(uid)

    ws = _ws_client(app, uid)

    assert ws.is_connected() is False


def test_socketio_refuses_unknown_user_id(app):
    """행이 없는 user_id 세션은 연결을 거부한다(예전에는 user_id 존재만 봤다)."""
    ws = _ws_client(app, 999_999)

    assert ws.is_connected() is False


# --------------------------------------------------------------------------
# 6. 마지막 활동 시각(_touch_last_seen)
# --------------------------------------------------------------------------
def test_active_request_touches_last_login(client, app, monkeypatch):
    """대조군: 활성 사용자의 요청은 last_login 을 따라 올린다(터치 창 0)."""
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "0")
    uid = _make_user("isg-seen-active")
    db_session.get(User, uid).last_login = _stale()
    db_session.commit()
    _login(client, uid)

    client.get(BADGE_URL)

    assert _stored_last_login(uid) > _stale()


def test_inactive_request_does_not_touch_last_login(client, app, monkeypatch):
    """비활성 사용자의 요청은 last_login 을 바꾸지 않는다(퇴사자가 "최근 활동" 으로 보이지 않게)."""
    monkeypatch.setenv("FOMS_LAST_SEEN_TOUCH_SECONDS", "0")
    uid = _make_user("isg-seen-inactive")
    db_session.get(User, uid).last_login = _stale()
    db_session.commit()
    _login(client, uid)
    _deactivate(uid)

    client.get(BADGE_URL)
    client.get(DRIFT_URL)

    assert _stored_last_login(uid) == _stale()


# --------------------------------------------------------------------------
# 7. SESSION-COOKIE-01 — 세션을 쓰는 것은 비활성일 때뿐
# --------------------------------------------------------------------------
def _set_cookie_headers(app, resp):
    name = app.config["SESSION_COOKIE_NAME"]
    return [h for h in resp.headers.getlist("Set-Cookie") if h.startswith(f"{name}=")]


def test_active_poll_still_writes_no_cookie(client, app):
    """대조군: 활성 사용자의 폴링 응답은 여전히 Set-Cookie 를 쓰지 않는다(2026-09-09 사고)."""
    uid = _make_user("isg-cookie-active")
    _login(client, uid)

    first = client.get(BADGE_URL)
    second = client.get(BADGE_URL)

    assert first.status_code == 200 and second.status_code == 200
    assert _set_cookie_headers(app, first) == []
    assert _set_cookie_headers(app, second) == []


def test_inactive_request_clears_session_cookie(client, app):
    """비활성 사용자의 요청은 세션 쿠키를 지우는 Set-Cookie 를 보낸다."""
    uid = _make_user("isg-cookie-inactive")
    _login(client, uid)
    _deactivate(uid)

    resp = client.get(BADGE_URL)

    headers = _set_cookie_headers(app, resp)
    assert len(headers) == 1, resp.headers
    assert _session_user_id(client) is None
