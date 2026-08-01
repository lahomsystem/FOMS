"""ACTOR-STATE-01: 알림 mark/archive/ack + push subscription actor-owner 정본 계약.

이 파일은 §5.2 ACTOR-STATE-01 행(exact actor owner allowlist / child receipt·version /
rate·audit / VIEWER own-resource positive·cross-user deny / chat·Order·business mutation
허용 금지 = scope 봉쇄)을 **하나의 회귀 계약**으로 고정한다.

surface 자체는 선행 packet 이 구현했다(Phase 0B owner-scoped state, Phase 3A push owner
check, AUTH-01 ancillary allowlist+manifest 분류, realtime rate limit). 이 테스트는 그
불변식이 앞으로도 유지되는지 검증하며, 보호(owner 재검사·ancillary allowlist·audit
event·rate wiring)를 제거하면 red 가 된다.

두 축을 분리한다.
* **route owner 재검사**(가드 OFF 기본): (notification_id, session_user) 소유 row 만
  상태 변경, 타인 것은 route 에서 차단(404 anti-enumeration; push 는 403/404).
* **정책 게이트 ON**(:data:`policy_on`): AUTH-01 hard deny 가 켜져도 VIEWER 는 자기
  notification/push ancillary 를 통과하고(own-resource positive), 그 뒤 route owner
  재검사가 cross-user 를 막는다(P1-24 회귀 방지).

DB fixture 는 tests/conftest.py 의 in-memory ``app``/``client`` 를 쓴다. request handler 가
commit/remove 하므로 setup row 는 **commit** 해 teardown(비-commit 404/403 경로 포함)에서도
살아남게 하고, 모든 식별자는 요청 전에 정수 지역변수로 캡처한다(detach 회피).
"""
import datetime

import pytest

from db import db_session
from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationPushSubscription,
    NotificationRecipientSource,
    NotificationUserState,
    Order,
    User,
)
from foms.services.orders.order_mutation_policy import (
    ANCILLARY_ALLOWLIST,
    POLICY_REGISTRY,
    load_policy_manifest,
)

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}

#: manifest 가 이 endpoint 들을 이 policy_id 로 분류해야 한다(actor-owned ancillary 계약).
_EXPECTED_POLICY = {
    "notifications.api_notification_mark_read": "MARK_OWN_NOTIFICATION_READ",
    "notifications.api_notifications_mark_all_read": "MARK_OWN_NOTIFICATION_READ",
    "notifications.api_notification_archive": "ARCHIVE_OWN_NOTIFICATION",
    "notifications.api_notifications_archive_all": "ARCHIVE_OWN_NOTIFICATION",
    "notifications.api_notification_ack": "ACK_OWN_NOTIFICATION",
    "notifications_push.subscribe": "CREATE_OWN_PUSH_SUBSCRIPTION",
}


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def db(app):
    """db_session 을 yield 하고 teardown 에서 롤백한다."""
    yield db_session
    db_session.rollback()


@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 AUTH-01 정책 가드를 강제 활성화하고 원복한다(cross-test 오염 방지)."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _mk_user(username, name="U", role="VIEWER", team=None, is_active=True):
    user = User(
        username=username, password="x", name=name, team=team,
        role=role, is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _mk_notification(**kwargs):
    defaults = dict(notification_type="ANNOUNCEMENT", target_type="ORDER", title="t")
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db_session.add(notif)
    db_session.commit()
    return notif


def _mk_state(notif_id, user_id, source=NotificationRecipientSource.TARGET_TEAM, **kwargs):
    state = NotificationUserState(
        notification_id=notif_id, user_id=user_id, recipient_source=source, **kwargs,
    )
    db_session.add(state)
    db_session.commit()
    return state


def _mk_push_sub(user_id, endpoint, revoked_at=None):
    sub = NotificationPushSubscription(user_id=user_id, endpoint=endpoint, revoked_at=revoked_at)
    db_session.add(sub)
    db_session.commit()
    return sub


def _mk_order(manager_name="담당자", **kwargs):
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name=kwargs.get("customer_name", "고객"),
        phone="010-0000-0000", address="Seoul", product="가구",
        status=kwargs.get("status", "ERPORDER"),
        manager_name=manager_name, is_erp_order=True,
        structured_data={"workflow": {"stage": "ERPORDER"}},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _login(client, user_id, username, role):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role


def _get_state(pk):
    db_session.expire_all()
    return db_session.get(NotificationUserState, pk)


def _events(notif_id, event_type):
    return (
        db_session.query(NotificationEvent)
        .filter(
            NotificationEvent.notification_id == notif_id,
            NotificationEvent.event_type == event_type,
        )
        .all()
    )


def _gate_passed(resp):
    """AUTH-01 정책 게이트를 통과했는가(막지 않았으면 business 응답이 무엇이든 True)."""
    return resp.headers.get("X-Auth-Policy") is None


# ===========================================================================
# 1. exact actor owner allowlist — 소유 actor 만 mark/archive/ack, cross-user deny
# ===========================================================================
def test_owner_mark_archive_ack_succeed(client, db):
    """소유 actor 는 자기 알림을 read/archive/ack 200 처리한다(본인 row)."""
    owner = _mk_user("as_owner", role="STAFF", team="CS")
    oid = owner.id
    read_n = _mk_notification(target_type="TEAM", target_team="CS").id
    arc_n = _mk_notification(target_type="TEAM", target_team="CS").id
    ack_n = _mk_notification(target_type="TEAM", target_team="CS", is_urgent=True).id
    read_s = _mk_state(read_n, oid).id
    arc_s = _mk_state(arc_n, oid).id
    ack_s = _mk_state(ack_n, oid).id

    _login(client, oid, "as_owner", "STAFF")
    assert client.post(f"/erp/api/notifications/{read_n}/read", headers=WRITE_HEADERS).status_code == 200
    assert client.post(f"/erp/api/notifications/{arc_n}/archive", headers=WRITE_HEADERS).status_code == 200
    assert client.post(f"/erp/api/notifications/{ack_n}/ack", headers=WRITE_HEADERS).status_code == 200

    assert _get_state(read_s).read_at is not None
    assert _get_state(arc_s).archived_at is not None
    assert _get_state(ack_s).ack_at is not None


@pytest.mark.parametrize("action", ["read", "archive", "ack"])
def test_cross_user_mutation_denied_and_no_state_change(client, db, action):
    """타 actor 의 알림 상태 변경은 route owner 재검사로 차단(404), 대상 row 무변경."""
    a = _mk_user(f"as_x_a_{action}", role="STAFF", team="CS")
    b = _mk_user(f"as_x_b_{action}", role="STAFF", team="SALES")
    aid, bid = a.id, b.id
    notif_id = _mk_notification(target_type="USER", target_user_id=aid, is_urgent=True).id
    a_state_id = _mk_state(notif_id, aid, source=NotificationRecipientSource.TARGET_USER).id

    _login(client, bid, f"as_x_b_{action}", "STAFF")  # b 는 a 의 알림에 접근
    resp = client.post(f"/erp/api/notifications/{notif_id}/{action}", headers=WRITE_HEADERS)
    # 404 = anti-enumeration owner deny (본인 row 없음). 존재/미존재를 구분하지 않는다.
    assert resp.status_code == 404

    st = _get_state(a_state_id)
    assert st.read_at is None and st.archived_at is None and st.ack_at is None
    # audit event 도 생기지 않는다(handler 미실행).
    assert _events(notif_id, NotificationEventType.READ) == []
    assert _events(notif_id, NotificationEventType.ARCHIVE) == []
    assert _events(notif_id, NotificationEventType.ACK) == []


def test_bulk_read_all_only_touches_own_states(client, db):
    """read-all 은 현재 actor 의 미읽음 row 만 갱신하고 타인 row 는 건드리지 않는다."""
    a = _mk_user("as_bulk_a", role="STAFF", team="CS")
    b = _mk_user("as_bulk_b", role="STAFF", team="CS")
    aid, bid = a.id, b.id
    n1 = _mk_notification(target_type="TEAM", target_team="CS").id
    n2 = _mk_notification(target_type="TEAM", target_team="CS").id
    sa1, sa2, sb1 = _mk_state(n1, aid).id, _mk_state(n2, aid).id, _mk_state(n1, bid).id

    _login(client, aid, "as_bulk_a", "STAFF")
    resp = client.post("/erp/api/notifications/read-all", headers=WRITE_HEADERS)
    assert resp.status_code == 200 and resp.get_json()["count"] == 2
    assert _get_state(sa1).read_at is not None and _get_state(sa2).read_at is not None
    assert _get_state(sb1).read_at is None  # 타인 row 불변


# ===========================================================================
# 2. VIEWER own-resource positive + cross-user deny (정책 게이트 ON — P1-24)
# ===========================================================================
def test_viewer_marks_own_notification_under_policy_gate(client, db, policy_on):
    """정책 ON 이어도 VIEWER 는 자기 알림 read/archive/ack 를 통과·성공한다(hard deny 예외)."""
    viewer = _mk_user("as_viewer_own", role="VIEWER", team="CS")
    vid = viewer.id
    read_n = _mk_notification(target_type="TEAM", target_team="CS").id
    arc_n = _mk_notification(target_type="TEAM", target_team="CS").id
    ack_n = _mk_notification(target_type="TEAM", target_team="CS", is_urgent=True).id
    read_s, arc_s, ack_s = _mk_state(read_n, vid).id, _mk_state(arc_n, vid).id, _mk_state(ack_n, vid).id

    _login(client, vid, "as_viewer_own", "VIEWER")
    r1 = client.post(f"/erp/api/notifications/{read_n}/read", headers=WRITE_HEADERS)
    r2 = client.post(f"/erp/api/notifications/{arc_n}/archive", headers=WRITE_HEADERS)
    r3 = client.post(f"/erp/api/notifications/{ack_n}/ack", headers=WRITE_HEADERS)
    for r in (r1, r2, r3):
        assert _gate_passed(r), (r.status_code, r.headers.get("X-Auth-Policy"))
        assert r.status_code == 200

    assert _get_state(read_s).read_at is not None
    assert _get_state(arc_s).archived_at is not None
    assert _get_state(ack_s).ack_at is not None


def test_viewer_cross_user_denied_by_route_owner_recheck(client, db, policy_on):
    """VIEWER 가 ancillary 게이트를 통과해도 타인 알림은 route owner 재검사로 404."""
    viewer = _mk_user("as_viewer_cross", role="VIEWER", team="CS")
    other = _mk_user("as_viewer_cross_o", role="STAFF", team="CS")
    vid, otherid = viewer.id, other.id
    notif_id = _mk_notification(target_type="USER", target_user_id=otherid).id
    other_state_id = _mk_state(notif_id, otherid, source=NotificationRecipientSource.TARGET_USER).id

    _login(client, vid, "as_viewer_cross", "VIEWER")
    resp = client.post(f"/erp/api/notifications/{notif_id}/read", headers=WRITE_HEADERS)
    # 게이트는 ancillary 라 통과시키지만(정책은 owner 무판정), route 가 owner 로 막는다.
    assert _gate_passed(resp)
    assert resp.status_code == 404
    assert _get_state(other_state_id).read_at is None


# ===========================================================================
# 3. child receipt/version — audit event 기록 + 멱등(중복 없음)
# ===========================================================================
def test_state_change_records_receipt_and_is_idempotent(client, db):
    """read/archive/ack 는 각각 audit event 1건을 남기고, 재호출은 no-op(멱등)."""
    owner = _mk_user("as_receipt", role="STAFF", team="CS")
    oid = owner.id
    notif_id = _mk_notification(target_type="TEAM", target_team="CS", is_urgent=True).id
    state_id = _mk_state(notif_id, oid).id

    _login(client, oid, "as_receipt", "STAFF")
    for action, evt in (
        ("read", NotificationEventType.READ),
        ("archive", NotificationEventType.ARCHIVE),
        ("ack", NotificationEventType.ACK),
    ):
        r1 = client.post(f"/erp/api/notifications/{notif_id}/{action}", headers=WRITE_HEADERS)
        r2 = client.post(f"/erp/api/notifications/{notif_id}/{action}", headers=WRITE_HEADERS)
        assert r1.status_code == 200 and r2.status_code == 200
        # transition 시점 1건만 — 재호출은 event 를 추가하지 않는다(멱등 receipt).
        evs = _events(notif_id, evt)
        assert len(evs) == 1, (action, len(evs))
        assert evs[0].user_state_id == state_id
        assert evs[0].actor_user_id == oid
        assert evs[0].recipient_user_id == oid


def test_ack_is_independent_of_read(client, db):
    """ack 은 read 와 독립 채널 — read 후에도 ack_at 은 별도로 채워진다."""
    owner = _mk_user("as_ack_indep", role="STAFF", team="CS")
    oid = owner.id
    notif_id = _mk_notification(target_type="TEAM", target_team="CS", is_urgent=True).id
    state_id = _mk_state(notif_id, oid).id

    _login(client, oid, "as_ack_indep", "STAFF")
    client.post(f"/erp/api/notifications/{notif_id}/read", headers=WRITE_HEADERS)
    st = _get_state(state_id)
    assert st.read_at is not None and st.ack_at is None
    prev_read = st.read_at

    client.post(f"/erp/api/notifications/{notif_id}/ack", headers=WRITE_HEADERS)
    st = _get_state(state_id)
    assert st.ack_at is not None and st.read_at == prev_read


# ===========================================================================
# 4. rate limit + audit wiring
# ===========================================================================
def test_state_routes_are_rate_limited(app):
    """mark/archive/ack write endpoint 는 realtime bootstrap 에서 rate limit 로 래핑된다."""
    import foms.api.notifications as notif_mod

    # 모듈-레벨 view 는 login+write-guard 데코 형태이고, realtime bootstrap 이
    # limiter.limit(...) 로 한 겹 더 감싸 app.view_functions 를 교체한다.
    for endpoint, raw_attr in (
        ("notifications.api_notification_mark_read", "api_notification_mark_read"),
        ("notifications.api_notifications_mark_all_read", "api_notifications_mark_all_read"),
        ("notifications.api_notification_archive", "api_notification_archive"),
        ("notifications.api_notifications_archive_all", "api_notifications_archive_all"),
        ("notifications.api_notification_ack", "api_notification_ack"),
    ):
        wired = app.view_functions.get(endpoint)
        assert wired is not None, endpoint
        assert wired is not getattr(notif_mod, raw_attr), f"{endpoint} 미래핑(rate limit 누락)"


def test_write_guard_missing_header_403(client, db):
    """audit 의 전제인 write-guard: 헤더 누락은 handler 전 403."""
    owner = _mk_user("as_wg1", role="STAFF", team="CS")
    oid = owner.id
    notif_id = _mk_notification(target_type="TEAM", target_team="CS").id
    _mk_state(notif_id, oid)
    _login(client, oid, "as_wg1", "STAFF")
    assert client.post(f"/erp/api/notifications/{notif_id}/read").status_code == 403


def test_write_guard_cross_origin_403(client, db):
    """write-guard: cross-origin Origin 헤더는 handler 전 403."""
    owner = _mk_user("as_wg2", role="STAFF", team="CS")
    oid = owner.id
    notif_id = _mk_notification(target_type="TEAM", target_team="CS").id
    _mk_state(notif_id, oid)
    _login(client, oid, "as_wg2", "STAFF")
    cross = dict(WRITE_HEADERS, Origin="http://evil.example.com")
    assert client.post(f"/erp/api/notifications/{notif_id}/read", headers=cross).status_code == 403


# ===========================================================================
# 5. push subscription — 본인 구독만 등록/해제
# ===========================================================================
def test_push_subscribe_other_owner_endpoint_forbidden(client, db, monkeypatch):
    """타 owner 가 이미 등록한 endpoint 를 재등록하면 403(endpoint owner 재검사)."""
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    a = _mk_user("as_push_a", role="STAFF", team="CS")
    b = _mk_user("as_push_b", role="STAFF", team="CS")
    aid, bid = a.id, b.id
    ep = "https://push.example.com/ep/shared-owner"
    _mk_push_sub(aid, ep)

    _login(client, bid, "as_push_b", "STAFF")
    resp = client.post(
        "/erp/api/notifications/push/subscribe",
        json={"endpoint": ep, "keys": {"p256dh": "k", "auth": "s"}},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "endpoint_owned_by_another_user"


def test_push_unsubscribe_other_owner_endpoint_not_found(client, db, monkeypatch):
    """타 owner 의 endpoint 해제 시도는 404(본인 소유만 revoke)."""
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    a = _mk_user("as_unsub_a", role="STAFF", team="CS")
    b = _mk_user("as_unsub_b", role="STAFF", team="CS")
    aid, bid = a.id, b.id
    ep = "https://push.example.com/ep/unsub-owner"
    sub_id = _mk_push_sub(aid, ep).id

    _login(client, bid, "as_unsub_b", "STAFF")
    resp = client.delete(
        "/erp/api/notifications/push/subscribe",
        json={"endpoint": ep},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 404
    db_session.expire_all()
    assert db_session.get(NotificationPushSubscription, sub_id).revoked_at is None  # 불변


def test_push_subscribe_own_endpoint_succeeds(client, db, monkeypatch):
    """VIEWER 도 자기 endpoint 는 등록 가능(own-resource positive)."""
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    viewer = _mk_user("as_push_own", role="VIEWER", team="CS")
    vid = viewer.id
    _login(client, vid, "as_push_own", "VIEWER")
    resp = client.post(
        "/erp/api/notifications/push/subscribe",
        json={"endpoint": "https://push.example.com/ep/own", "keys": {"p256dh": "k", "auth": "s"}},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200 and resp.get_json()["data"]["active"] is True


# ===========================================================================
# 6. scope 봉쇄 — chat/Order/business mutation 로 새지 않는다
# ===========================================================================
def test_state_change_does_not_mutate_order(client, db):
    """알림 상태 변경은 연결된 Order 를 건드리지 않는다(business mutation 격리)."""
    owner = _mk_user("as_scope_order", role="STAFF", team="CS")
    oid = owner.id
    order = _mk_order()
    order_id = order.id
    before = dict(order.structured_data or {})
    notif_id = _mk_notification(target_type="USER", target_user_id=oid, order_id=order_id).id
    _mk_state(notif_id, oid, source=NotificationRecipientSource.TARGET_USER)

    _login(client, oid, "as_scope_order", "STAFF")
    assert client.post(f"/erp/api/notifications/{notif_id}/read", headers=WRITE_HEADERS).status_code == 200

    db_session.expire_all()
    after = db_session.get(Order, order_id)
    assert dict(after.structured_data or {}) == before  # Order structured_data 불변


def test_shared_row_is_read_not_polluted(client, db):
    """공유(TEAM) Notification 의 legacy is_read 는 per-user read 로 오염되지 않는다."""
    a = _mk_user("as_shared_a", role="STAFF", team="CS")
    aid = a.id
    notif_id = _mk_notification(target_type="TEAM", target_team="CS").id
    _mk_state(notif_id, aid)

    _login(client, aid, "as_shared_a", "STAFF")
    assert client.post(f"/erp/api/notifications/{notif_id}/read", headers=WRITE_HEADERS).status_code == 200
    db_session.expire_all()
    assert db_session.get(Notification, notif_id).is_read is False  # 공유 row 불변


@pytest.mark.parametrize("role", ["VIEWER", "STAFF", "MANAGER"])
def test_delete_all_is_admin_only_not_ancillary(client, db, role):
    """delete-all(공유 row 하드삭제)은 ADMIN 전용 — ancillary allowlist 로 새지 않는다."""
    user = _mk_user(f"as_del_{role.lower()}", role=role, team="CS")
    uid = user.id
    _mk_notification(target_type="ALL")
    _login(client, uid, f"as_del_{role.lower()}", role)
    resp = client.post("/erp/api/notifications/delete-all", headers=WRITE_HEADERS)
    assert resp.status_code == 403


def test_delete_all_admin_allowed(client, db):
    """ADMIN 만 delete-all 200 (scope 대조군)."""
    admin = _mk_user("as_del_admin", role="ADMIN")
    aid = admin.id
    _mk_notification(target_type="ALL")
    _login(client, aid, "as_del_admin", "ADMIN")
    assert client.post("/erp/api/notifications/delete-all", headers=WRITE_HEADERS).status_code == 200


# ===========================================================================
# 7. static 계약 — actor-owned endpoint 가 manifest 에서 ancillary 로 분류됨
# ===========================================================================
def test_actor_owned_endpoints_classified_as_ancillary_allowlist(app):
    """mark/archive/ack + subscribe 가 manifest 에서 기대 ancillary policy_id 로 분류된다."""
    routes = load_policy_manifest().get("routes", {})
    for endpoint, expected_pid in _EXPECTED_POLICY.items():
        meta = routes.get(endpoint)
        assert meta is not None, f"{endpoint} manifest 미등재(static gate red)"
        assert meta.get("policy_id") == expected_pid, (endpoint, meta.get("policy_id"))
        # ancillary allowlist 소속이며 VIEWER 허용이어야 한다(own-resource positive 전제).
        assert expected_pid in ANCILLARY_ALLOWLIST
        assert POLICY_REGISTRY[expected_pid].viewer is True
