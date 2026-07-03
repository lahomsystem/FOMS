"""Phase 3A: Web Push 구독 API + feature flag 테스트.

DB fixture 는 tests/conftest.py 의 `app`(in-memory sqlite) + `client` 를 사용한다.
feature flag(``FOMS_WEB_PUSH_ENABLED``)/VAPID 키는 monkeypatch 로 요청 시점에 토글한다.
"""
import pytest

from db import db_session
from models import NotificationPushSubscription, User

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}
FLAG_ENV = "FOMS_WEB_PUSH_ENABLED"
VAPID_ENV = "VAPID_PUBLIC_KEY"
EP = "https://fcm.googleapis.com/fcm/send/abc123"

SUBSCRIBE = "/erp/api/notifications/push/subscribe"
VAPID_URL = "/erp/api/notifications/push/vapid-public-key"
TEST_URL = "/erp/api/notifications/push/test"
MOBILE_STATE = "/erp/api/notifications/mobile-state"


def _mk_user(username, name, role="VIEWER", is_active=True):
    """사용자 생성 후 primary key(int) 반환. 요청 teardown 후 detach 를 피하기 위함."""
    user = User(
        username=username,
        password="x",
        name=name,
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user.id


def _login(client, user_id):
    """user_id 로 fresh 조회 후 세션에 로그인 상태를 심는다(detach 회피)."""
    user = db_session.get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _subscribe(client, endpoint=EP, p256dh="p", auth="a", **extra):
    body = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
    body.update(extra)
    return client.post(SUBSCRIBE, json=body, headers=WRITE_HEADERS)


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# ---------------------------------------------------------------------------
# feature flag off -> push API 전부 404
# ---------------------------------------------------------------------------

def test_flag_off_endpoints_return_404(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "0")
    u = _mk_user("po_off", "A")
    _login(client, u)

    assert client.get(VAPID_URL).status_code == 404
    assert _subscribe(client).status_code == 404
    assert client.post(TEST_URL, json={}, headers=WRITE_HEADERS).status_code == 404


# ---------------------------------------------------------------------------
# vapid-public-key
# ---------------------------------------------------------------------------

def test_vapid_not_configured_returns_503(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    monkeypatch.delenv(VAPID_ENV, raising=False)
    u = _mk_user("po_vapid_no", "A")
    _login(client, u)

    resp = client.get(VAPID_URL)
    assert resp.status_code == 503
    assert resp.get_json()["success"] is False


def test_vapid_configured_returns_key(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    monkeypatch.setenv(VAPID_ENV, "BPUBLICKEY")
    u = _mk_user("po_vapid_ok", "A")
    _login(client, u)

    resp = client.get(VAPID_URL)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["public_key"] == "BPUBLICKEY"


# ---------------------------------------------------------------------------
# subscribe upsert
# ---------------------------------------------------------------------------

def test_subscribe_new_then_upsert_same_owner(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_sub", "A")
    _login(client, u)

    r1 = _subscribe(client, p256dh="p1", auth="a1", platform="android")
    assert r1.status_code == 200
    rows = db.query(NotificationPushSubscription).filter_by(endpoint=EP).all()
    assert len(rows) == 1
    assert rows[0].user_id == u

    # 같은 owner 재등록 -> upsert(중복 row 없음, 값 갱신).
    r2 = _subscribe(client, p256dh="p2", auth="a2")
    assert r2.status_code == 200
    rows = db.query(NotificationPushSubscription).filter_by(endpoint=EP).all()
    assert len(rows) == 1
    assert rows[0].p256dh == "p2"
    # 응답에 endpoint 원문이 없어야 한다.
    assert EP not in r2.get_data(as_text=True)


def test_subscribe_reactivates_revoked_same_owner(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_react", "A")
    _login(client, u)

    _subscribe(client)
    client.delete(SUBSCRIBE, json={"endpoint": EP}, headers=WRITE_HEADERS)
    assert db.query(NotificationPushSubscription).filter_by(endpoint=EP).one().revoked_at is not None

    _subscribe(client)  # 재구독 -> revoked 해제
    assert db.query(NotificationPushSubscription).filter_by(endpoint=EP).one().revoked_at is None


def test_subscribe_other_owner_returns_403(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    a = _mk_user("po_own_a", "A")
    b = _mk_user("po_own_b", "B")

    _login(client, a)
    _subscribe(client, p256dh="p", auth="a")

    _login(client, b)
    r = _subscribe(client, p256dh="x", auth="y")
    assert r.status_code == 403
    # 원 소유자/값이 덮어써지지 않아야 한다.
    row = db.query(NotificationPushSubscription).filter_by(endpoint=EP).one()
    assert row.user_id == a
    assert row.p256dh == "p"


def test_subscribe_http_endpoint_returns_400(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_http", "A")
    _login(client, u)

    r = client.post(
        SUBSCRIBE,
        json={"endpoint": "http://insecure.example.com/x", "keys": {"p256dh": "p", "auth": "a"}},
        headers=WRITE_HEADERS,
    )
    assert r.status_code == 400


def test_subscribe_missing_write_header_returns_403(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_hdr", "A")
    _login(client, u)

    r = client.post(SUBSCRIBE, json={"endpoint": EP, "keys": {"p256dh": "p", "auth": "a"}})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# DELETE subscribe (soft-revoke)
# ---------------------------------------------------------------------------

def test_delete_self_soft_revokes(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_del", "A")
    _login(client, u)
    _subscribe(client)

    r = client.delete(SUBSCRIBE, json={"endpoint": EP}, headers=WRITE_HEADERS)
    assert r.status_code == 200
    row = db.query(NotificationPushSubscription).filter_by(endpoint=EP).one()
    assert row.revoked_at is not None  # 하드 삭제가 아니라 soft-delete


def test_delete_other_owner_returns_404(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    a = _mk_user("po_del_a", "A")
    b = _mk_user("po_del_b", "B")
    _login(client, a)
    _subscribe(client)

    _login(client, b)
    r = client.delete(SUBSCRIBE, json={"endpoint": EP}, headers=WRITE_HEADERS)
    assert r.status_code == 404
    # 원 구독은 여전히 활성.
    assert db.query(NotificationPushSubscription).filter_by(endpoint=EP).one().revoked_at is None


def test_delete_missing_endpoint_returns_404(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_del_missing", "A")
    _login(client, u)

    r = client.delete(
        SUBSCRIBE, json={"endpoint": "https://fcm.googleapis.com/none"}, headers=WRITE_HEADERS
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# test push
# ---------------------------------------------------------------------------

def test_push_test_self_returns_sender_not_deployed(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_test_self", "A")
    _login(client, u)
    _subscribe(client)

    r = client.post(TEST_URL, json={}, headers=WRITE_HEADERS)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["queued"] is False
    assert data["reason"] == "sender_not_deployed"


def test_push_test_no_subscription_returns_404(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_test_none", "A")
    _login(client, u)

    r = client.post(TEST_URL, json={}, headers=WRITE_HEADERS)
    assert r.status_code == 404


def test_push_test_other_user_non_admin_returns_403(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    a = _mk_user("po_test_v", "A", role="VIEWER")
    b = _mk_user("po_test_t", "B")
    _login(client, a)

    r = client.post(TEST_URL, json={"user_id": b}, headers=WRITE_HEADERS)
    assert r.status_code == 403


def test_push_test_admin_targets_other_user(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    admin = _mk_user("po_test_adm", "Adm", role="ADMIN")
    b = _mk_user("po_test_b", "B")

    _login(client, b)
    _subscribe(client)

    _login(client, admin)
    r = client.post(TEST_URL, json={"user_id": b}, headers=WRITE_HEADERS)
    assert r.status_code == 200
    assert r.get_json()["data"]["reason"] == "sender_not_deployed"


# ---------------------------------------------------------------------------
# mobile-state
# ---------------------------------------------------------------------------

def test_mobile_state_flag_off(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "0")
    u = _mk_user("po_ms_off", "A")
    _login(client, u)

    r = client.get(MOBILE_STATE)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["web_push_enabled"] is False
    assert data["subscription_active"] is False


def test_mobile_state_flag_on_with_active_subscription(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    monkeypatch.setenv(VAPID_ENV, "BKEY")
    u = _mk_user("po_ms_on", "A")
    _login(client, u)
    _subscribe(client)

    r = client.get(MOBILE_STATE)
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["web_push_enabled"] is True
    assert data["vapid_configured"] is True
    assert data["subscription_active"] is True


def test_mobile_state_subscription_active_false_after_revoke(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("po_ms_rev", "A")
    _login(client, u)
    _subscribe(client)
    client.delete(SUBSCRIBE, json={"endpoint": EP}, headers=WRITE_HEADERS)

    r = client.get(MOBILE_STATE)
    assert r.get_json()["data"]["subscription_active"] is False
