"""AUDIT-LOG T5: 관리자 행위 구조화 + 접근거부 DB 기록 계약 테스트 (SQLite 도메인 레인).

스펙: ``docs/specs/2026-08-05-system-audit-logging-design.md`` §3-3·§4 T5·§7,
플랜: ``docs/plans/2026-08-05-system-audit-logging-plan.md`` T5.

검증 대상:

1. 관리자 사용자 수정 — role/team/is_active/username 을 **field 별 from→to** 로 기록.
2. 관리자의 비밀번호 재설정 — **별도 행**, 비밀번호 원문·해시 어떤 형태로도 미기록.
3. ``/register`` 최초 관리자 부트스트랩 — 기록 1건.
4. API 403(주문 정책) — 독립 커밋으로 ``security_logs`` 행 생성 + 60초 dedupe(연타 1건,
   창 만료 후 ``(억제 N회)`` 반영).
5. CSRF/Origin 차단 — 동일.
6. 본 세션 트랜잭션 rollback 주입 후에도 감사 행 잔존.
7. 감사 engine 미가용 주입 시 요청 응답 정상 + fail-open 경고 로그.
8. dedupe 캐시 상한 GC.

**SQLite 레인의 한계(명시)**: ``audit_writer`` 는 SQLite 에서 메인 engine 을 재사용하므로
"별도 커넥션·별도 트랜잭션"은 이 레인에서 증명되지 않는다(pysqlite 는 커넥션 단위
트랜잭션 — 같은 커넥션을 공유한다). 진짜 독립 커밋은 ``tests/postgres/
test_audit_writer_pg.py`` 가 실 PostgreSQL 전용 engine 으로 증명한다. 여기서는
"rollback 을 주입해도 감사 행이 남는다"는 관측 계약만 고정한다.
"""

from __future__ import annotations

import logging

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, SecurityLog, User
from foms.services import audit_writer
from foms.services.request_write_guard import enforce_csrf_origin

_STRONG_PW = "Abcdef12"
_RESET_PW = "Zxcvbn99"


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _audit_isolation():
    """dedupe 캐시는 프로세스 전역이다 — 테스트마다 비워 격리한다."""
    audit_writer.reset_dedupe_cache()
    yield
    audit_writer.reset_dedupe_cache()


@pytest.fixture(autouse=True)
def _reset_rate_limits(app):
    """/register 는 rate limit 이 걸려 있다(메모리 버킷이 프로세스 수명 동안 누적)."""
    for limiter in app.extensions.get("limiter", set()):
        limiter.reset()
    yield


@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 주문 정책 가드를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


@pytest.fixture
def guard_on(app):
    """이 테스트 동안만 공용 CSRF/Origin write guard 를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("WRITE_GUARD_ENABLED", sentinel)
    app.config["WRITE_GUARD_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    else:
        app.config["WRITE_GUARD_ENABLED"] = prev


@pytest.fixture
def fake_clock(monkeypatch):
    """dedupe 창을 제어하는 가짜 단조 시계(초 단위 수동 전진)."""

    class _Clock:
        def __init__(self) -> None:
            self.value = 1000.0

        def advance(self, seconds: float) -> None:
            self.value += seconds

    clock = _Clock()
    monkeypatch.setattr(audit_writer, "_monotonic", lambda: clock.value)
    return clock


def _make_user(username, *, role="STAFF", team=None, is_active=True, raw_password=_STRONG_PW):
    """User 를 만들고 정수 id 를 반환한다(요청 teardown 후 detach 대비)."""
    user = User(
        username=username,
        password=generate_password_hash(raw_password),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=is_active,
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


def _make_order(status="RECEIVED"):
    order = Order(
        received_date="2026-08-05",
        customer_name="감사 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _messages():
    """현재 security_logs 의 모든 message 를 id 순으로."""
    db_session.expire_all()
    rows = db_session.query(SecurityLog).order_by(SecurityLog.id).all()
    return [row.message for row in rows]


def _matching(fragment):
    return [m for m in _messages() if fragment in m]


# --------------------------------------------------------------------------
# 1. 관리자 사용자 수정 — field 별 from→to
# --------------------------------------------------------------------------
def test_edit_user_records_field_level_from_to(client, app):
    """role/team/is_active/username 변경이 ``field from→to`` 로 한 줄에 남는다."""
    admin_id = _make_user("audit-admin", role="ADMIN")
    target_id = _make_user("audit-target", role="STAFF", team="CS")
    _login(client, admin_id)

    resp = client.post(f"/admin/users/edit/{target_id}", data={
        "username": "audit-target-2",
        "name": "이름변경",
        "role": "ADMIN",
        "team": "SALES",
        "is_active": "on",
    }, follow_redirects=False)
    assert resp.status_code == 302, resp.get_data(as_text=True)[:400]

    edits = _matching(f"사용자 #{target_id} 수정:")
    assert len(edits) == 1, _messages()
    message = edits[0]
    assert "role STAFF→ADMIN" in message
    assert "team CS→SALES" in message
    assert "username audit-target→audit-target-2" in message
    # 실제 DB 도 바뀌었는지(감사만 남고 반영 안 되는 오탐 차단)
    db_session.expire_all()
    saved = db_session.get(User, target_id)
    assert saved.role == "ADMIN"
    assert saved.team == "SALES"


def test_edit_user_deactivation_records_is_active_transition(client, app):
    """비활성 전환은 ``is_active True→False`` 로 남는다."""
    admin_id = _make_user("audit-admin2", role="ADMIN")
    target_id = _make_user("audit-target2", role="STAFF", team="CS")
    _login(client, admin_id)

    client.post(f"/admin/users/edit/{target_id}", data={
        "username": "audit-target2",
        "name": "audit-target2-name",
        "role": "STAFF",
        "team": "CS",
        # is_active 미전송 = 비활성
    })

    edits = _matching(f"사용자 #{target_id} 수정:")
    assert len(edits) == 1, _messages()
    assert "is_active True→False" in edits[0]


def test_edit_user_without_tracked_change_keeps_single_line(client, app):
    """감사 대상 필드가 그대로면 기존 한 줄(``정보 수정``)을 유지한다."""
    admin_id = _make_user("audit-admin3", role="ADMIN")
    target_id = _make_user("audit-target3", role="STAFF", team="CS")
    _login(client, admin_id)

    client.post(f"/admin/users/edit/{target_id}", data={
        "username": "audit-target3",
        "name": "이름만 변경",
        "role": "STAFF",
        "team": "CS",
        "is_active": "on",
    })

    assert _matching(f"사용자 #{target_id} 정보 수정") == [f"사용자 #{target_id} 정보 수정"]
    assert _matching(f"사용자 #{target_id} 수정:") == []


# --------------------------------------------------------------------------
# 2. 관리자 비밀번호 재설정 — 별도 행 + 값 미기록
# --------------------------------------------------------------------------
def test_admin_password_reset_is_separate_row_without_secret(client, app):
    """타인 비번 재설정은 별도 행이며 원문·해시 어떤 형태로도 기록되지 않는다."""
    admin_id = _make_user("pw-admin", role="ADMIN")
    target_id = _make_user("pw-target", role="STAFF", team="CS")
    _login(client, admin_id)

    resp = client.post(f"/admin/users/edit/{target_id}", data={
        "username": "pw-target",
        "name": "pw-target-name",
        "role": "STAFF",
        "team": "CS",
        "is_active": "on",
        "new_password": _RESET_PW,
    })
    assert resp.status_code == 302

    reset_rows = _matching("비밀번호 재설정(관리자 #")
    assert reset_rows == [f"사용자 #{target_id} 비밀번호 재설정(관리자 #{admin_id})"]

    # 비밀번호가 실제로 바뀌었는데도(no-op 아님)…
    db_session.expire_all()
    saved_hash = db_session.get(User, target_id).password
    assert saved_hash

    # …어떤 감사 행에도 원문/해시/해시 조각이 없다(부정 단언).
    for message in _messages():
        assert _RESET_PW not in message
        assert saved_hash not in message
        assert "pbkdf2" not in message and "scrypt" not in message


# --------------------------------------------------------------------------
# 3. /register 부트스트랩 기록
# --------------------------------------------------------------------------
def test_register_bootstrap_records_one_row(client, app):
    """사용자 0명 상태의 최초 관리자 부트스트랩 가입이 1건 기록된다."""
    assert db_session.query(User).count() == 0

    resp = client.post("/register", data={
        "username": "first-admin",
        "name": "최초관리자",
        "team": "",
        "password": _STRONG_PW,
        "confirm_password": _STRONG_PW,
    })
    assert resp.status_code == 302

    created = db_session.query(User).filter_by(username="first-admin").first()
    assert created is not None and created.role == "ADMIN"

    rows = _matching("최초 관리자 부트스트랩 가입")
    assert rows == [f"최초 관리자 부트스트랩 가입: first-admin (ID: {created.id})"]


# --------------------------------------------------------------------------
# 4. API 403 → 독립 모드 SecurityLog + dedupe
# --------------------------------------------------------------------------
def test_api_403_writes_security_log_row(client, app, policy_on):
    """VIEWER 의 finance mutation 403 이 security_logs 행을 남긴다(handler 미실행 경로)."""
    viewer_id = _make_user("deny-viewer", role="VIEWER")
    _login(client, viewer_id)
    oid = _make_order("COMPLETED")

    resp = client.post(f"/api/orders/{oid}/settlement/issue", json={"issued": True})
    assert resp.status_code == 403
    assert resp.headers.get("X-Auth-Policy") == "denied"

    rows = _matching("권한 거부(주문 정책)")
    assert len(rows) == 1, _messages()
    assert f"/api/orders/{oid}/settlement/issue" in rows[0]
    db_session.expire_all()
    logged = db_session.query(SecurityLog).filter(
        SecurityLog.message.like("권한 거부(주문 정책)%")).one()
    assert logged.user_id == viewer_id


def test_api_403_dedupes_within_window_and_reports_suppressed(
        client, app, policy_on, fake_clock):
    """같은 (user, endpoint, action) 연타는 60초 창에 1건, 창 만료 후 억제 카운트 보고."""
    viewer_id = _make_user("deny-burst", role="VIEWER")
    _login(client, viewer_id)
    oid = _make_order("COMPLETED")
    path = f"/api/orders/{oid}/settlement/issue"

    for _ in range(3):
        assert client.post(path, json={"issued": True}).status_code == 403

    rows = _matching("권한 거부(주문 정책)")
    assert len(rows) == 1, rows
    assert "억제" not in rows[0]

    # 창 안(59초)에서는 여전히 억제된다.
    fake_clock.advance(59)
    assert client.post(path, json={"issued": True}).status_code == 403
    assert len(_matching("권한 거부(주문 정책)")) == 1

    # 창 만료 후 첫 요청이 누적분(3회)을 함께 보고한다.
    fake_clock.advance(2)
    assert client.post(path, json={"issued": True}).status_code == 403
    rows = _matching("권한 거부(주문 정책)")
    assert len(rows) == 2, rows
    assert rows[1].endswith("(억제 3회)"), rows[1]


def test_dedupe_key_separates_subject_and_endpoint(client, app, policy_on):
    """dedupe 는 (주체, endpoint, action) 별로 독립이다 — 다른 사용자는 따로 기록된다."""
    oid = _make_order("COMPLETED")
    for name in ("deny-a", "deny-b"):
        uid = _make_user(name, role="VIEWER")
        _login(client, uid)
        assert client.post(
            f"/api/orders/{oid}/settlement/issue", json={"issued": True}).status_code == 403

    assert len(_matching("권한 거부(주문 정책)")) == 2, _messages()


# --------------------------------------------------------------------------
# 5. CSRF/Origin 차단 경로
# --------------------------------------------------------------------------
def test_csrf_block_writes_security_log_row(client, app, guard_on):
    """CSRF 토큰 없는 mutation 차단이 security_logs 행을 남긴다."""
    uid = _make_user("csrf-user", role="STAFF", team="CS")
    _login(client, uid)
    oid = _make_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert resp.status_code == 403
    assert resp.headers.get("X-Write-Guard") == "blocked"

    rows = _matching("요청 차단(write-guard)")
    assert len(rows) == 1, _messages()
    assert "reason=invalid_csrf_token" in rows[0]

    # 연타는 60초 창에서 억제된다(같은 user·endpoint·reason).
    client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert len(_matching("요청 차단(write-guard)")) == 1


# --------------------------------------------------------------------------
# 6. rollback 주입 후에도 감사 행 잔존
# --------------------------------------------------------------------------
def test_denied_audit_row_survives_session_rollback(client, app, guard_on):
    """요청 도중 본 세션을 rollback 시켜도 차단 감사 행은 남는다.

    ``enforce_csrf_origin`` 은 before_request 단계라 본 트랜잭션 commit 이 없다. 세션에
    pending 변경을 만들어 두고 차단을 유발한 뒤 rollback 을 주입한다.
    """
    uid = _make_user("rollback-user", role="STAFF", team="CS")
    oid = _make_order()

    with app.test_request_context(
        f"/api/orders/{oid}/call-log", method="POST", json={"result": "connected"}
    ):
        from flask import session as flask_session

        flask_session["user_id"] = uid
        # 본 세션에 pending 변경을 만든다(요청 트랜잭션 진행 중 상태 재현).
        pending = db_session.get(User, uid)
        pending.name = "롤백될 이름"
        db_session.flush()

        response = enforce_csrf_origin()
        assert response is not None and response.status_code == 403

        db_session.rollback()  # ← rollback 주입

    rows = _matching("요청 차단(write-guard)")
    assert len(rows) == 1, _messages()


def test_detached_write_is_not_undone_by_rollback(app):
    """``write_security_log_detached`` 자체가 본 세션 rollback 에 지워지지 않는다."""
    assert audit_writer.write_security_log_detached("독립 커밋 검증", user_id=None) is True
    db_session.rollback()
    assert _matching("독립 커밋 검증") == ["독립 커밋 검증"]


# --------------------------------------------------------------------------
# 7. 감사 engine 미가용 → fail-open
# --------------------------------------------------------------------------
def test_audit_engine_unavailable_fails_open(client, app, policy_on, monkeypatch, caplog):
    """감사 engine 이 죽어도 요청 응답은 정상이고 경고 로그만 남는다(행 0)."""
    from sqlalchemy.exc import SQLAlchemyError

    class _DeadEngine:
        def begin(self):
            raise SQLAlchemyError("audit engine unavailable (injected)")

    monkeypatch.setattr(audit_writer, "get_audit_engine", lambda: _DeadEngine())

    viewer_id = _make_user("failopen-viewer", role="VIEWER")
    _login(client, viewer_id)
    oid = _make_order("COMPLETED")

    with caplog.at_level(logging.WARNING, logger="foms.services.audit_writer"):
        resp = client.post(f"/api/orders/{oid}/settlement/issue", json={"issued": True})

    # 요청은 정상 처리(정책 거부 403 그대로 — 500 아님)
    assert resp.status_code == 403
    assert resp.headers.get("X-Auth-Policy") == "denied"
    assert resp.get_json()["success"] is False

    assert _matching("권한 거부(주문 정책)") == []
    assert any("독립 기록 실패" in record.getMessage() for record in caplog.records), [
        r.getMessage() for r in caplog.records]


def test_write_returns_false_on_engine_failure(app, monkeypatch):
    """writer 는 실패를 전파하지 않고 False 를 반환한다."""
    from sqlalchemy.exc import SQLAlchemyError

    def _boom():
        raise SQLAlchemyError("injected")

    monkeypatch.setattr(audit_writer, "get_audit_engine", _boom)
    assert audit_writer.write_security_log_detached("실패해야 함") is False
    assert _matching("실패해야 함") == []


# --------------------------------------------------------------------------
# 8. dedupe 캐시 상한 GC
# --------------------------------------------------------------------------
def test_dedupe_cache_respects_limit_and_gcs_oldest(app, monkeypatch):
    """키가 상한을 넘으면 오래된 키부터 버려 캐시가 무한 성장하지 않는다."""
    monkeypatch.setattr(audit_writer, "DEDUPE_CACHE_LIMIT", 4)
    audit_writer.reset_dedupe_cache()

    for index in range(25):
        audit_writer.record_access_denied(
            f"GC 검증 {index}", user_id=None, ip="10.0.0.1",
            endpoint=f"ep{index}", action="policy:TEST")

    assert audit_writer.dedupe_cache_size() == 4
    assert len(_matching("GC 검증")) == 25


def test_dedupe_gc_evicts_oldest_so_recycled_key_writes_again(app, monkeypatch, fake_clock):
    """GC 로 밀려난 키는 창 안이어도 다시 기록된다(상한의 대가 — 명시 계약)."""
    monkeypatch.setattr(audit_writer, "DEDUPE_CACHE_LIMIT", 2)
    audit_writer.reset_dedupe_cache()

    def _hit(endpoint):
        return audit_writer.record_access_denied(
            f"GC 축출 {endpoint}", user_id=7, endpoint=endpoint, action="policy:TEST")

    assert _hit("ep-a") is True
    assert _hit("ep-a") is False          # 창 안 → 억제
    assert _hit("ep-b") is True
    assert _hit("ep-c") is True           # 상한 2 초과 → 가장 오래된 ep-a 축출
    assert audit_writer.dedupe_cache_size() == 2
    assert _hit("ep-a") is True           # 축출됐으므로 창 안이어도 새로 기록
