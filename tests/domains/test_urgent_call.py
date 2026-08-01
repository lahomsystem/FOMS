"""URGENT-CALL-01 canonical contract — order urgent target/send.

SSOT: docs/plans/2026-07-22-foms-full-system-bug-audit-report.md §5.2 URGENT-CALL-01
(line ~1034) + line 157:

    SEND_URGENT_CALL {order_id,target_user_id,message}는 Order read scope/participant인
    authenticated actor에게 허용하므로 관련 주문을 조회할 수 있는 VIEWER도 쓸 수 있다.
    target은 active FOMS user, message trim 1..500, actor+order당 5회/시간 ...
    notification, recipient urgent state, urgent-call NotificationEvent,
    source_domain=NOTIFICATION_EVENT side-effect row를 한 transaction에 commit하고
    Order version은 바꾸지 않는다. target list도 같은 order read scope를 요구하며
    ... 타 주문/비활성 target/rate 초과는 403/422/429와 child 변화 0이다.

DB fixture 는 tests/conftest.py 의 `app`(in-memory sqlite) + `client` 를 사용한다.
"""
import datetime

import pytest

from db import db_session
from models import (
    DomainSideEffectOutbox,
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationUserState,
    Order,
    User,
)

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _mk_user(username, name, role="VIEWER", team=None, is_active=True):
    user = User(
        username=username,
        password="x",
        name=name,
        team=team,
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _mk_order(manager_name="관련영업", **kwargs):
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name=kwargs.get("customer_name", "고객"),
        phone="010-0000-0000",
        address="Seoul",
        product="가구",
        status=kwargs.get("status", "ERPORDER"),
        manager_name=manager_name,
        is_erp_order=True,
        structured_data=kwargs.get("structured_data") or {"workflow": {"stage": "ERPORDER"}},
    )
    db_session.add(order)
    db_session.flush()
    return order


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _send(client, order_id, target_id, message="확인 부탁", headers=WRITE_HEADERS):
    return client.post(
        f"/erp/api/orders/{order_id}/urgent-mention",
        json={"target_user_id": target_id, "message": message},
        headers=headers,
    )


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# --------------------------------------------------------------------------- #
# sender 게이트 = order read scope (participant incl VIEWER) — P1-25 fix
# --------------------------------------------------------------------------- #
def test_unrelated_viewer_reader_can_send_200(client, db):
    """주문과 무관한 VIEWER 도 order read scope 이므로 긴급 호출 send 200 (P1-25)."""
    order = _mk_order(manager_name="담당자")
    sender = _mk_user("uc_viewer_sender", "무관뷰어", role="VIEWER", team="PRODUCTION")
    target = _mk_user("uc_viewer_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)
    resp = _send(client, oid, tid, "빨리 확인 부탁")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True


def test_target_is_any_active_user_not_just_participant(client, db):
    """target 은 active FOMS user 면 충분(주문 참여자일 필요 없음)."""
    order = _mk_order(manager_name="담당자")
    sender = _mk_user("uc_any_sender", "관리자", role="ADMIN")
    outsider = _mk_user("uc_any_target", "무관동료", role="VIEWER", team="CS")
    oid, tid = order.id, outsider.id
    _login(client, sender)
    resp = _send(client, oid, tid)
    assert resp.status_code == 200, resp.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# target/message 검증 — 비활성 target 422, 없는 target 404, self 400, message 1..500
# --------------------------------------------------------------------------- #
def test_inactive_target_422(client, db):
    order = _mk_order()
    sender = _mk_user("uc_it_sender", "보낸이", role="ADMIN")
    inactive = _mk_user("uc_it_target", "비활성대상", role="STAFF", is_active=False)
    oid, tid = order.id, inactive.id
    _login(client, sender)
    resp = _send(client, oid, tid)
    assert resp.status_code == 422


def test_nonexistent_target_404(client, db):
    order = _mk_order()
    sender = _mk_user("uc_ne_sender", "보낸이", role="ADMIN")
    oid = order.id
    _login(client, sender)
    resp = _send(client, oid, 999_999)
    assert resp.status_code == 404


def test_self_target_400(client, db):
    order = _mk_order()
    sender = _mk_user("uc_self_sender", "보낸이", role="ADMIN")
    oid, sid = order.id, sender.id
    _login(client, sender)
    resp = _send(client, oid, sid)
    assert resp.status_code == 400


def test_empty_message_400(client, db):
    """message trim 1..500 — 빈 사유는 400."""
    order = _mk_order()
    sender = _mk_user("uc_em_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_em_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)
    resp = _send(client, oid, tid, message="   ")
    assert resp.status_code == 400


def test_too_long_message_400(client, db):
    order = _mk_order()
    sender = _mk_user("uc_tl_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_tl_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)
    resp = _send(client, oid, tid, message="x" * 501)
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# rate: actor+order당 5회/시간 → 6번째 429
# --------------------------------------------------------------------------- #
def test_rate_limit_five_per_hour_per_actor_order(client, db):
    order = _mk_order()
    sender = _mk_user("uc_rl_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_rl_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)
    for i in range(5):
        r = _send(client, oid, tid, message=f"호출 {i}")
        assert r.status_code == 200, (i, r.get_data(as_text=True))
    r6 = _send(client, oid, tid, message="여섯번째")
    assert r6.status_code == 429


def test_rate_limit_is_per_order(client, db):
    """rate 는 actor+order 단위 — 다른 order 는 별도 카운터."""
    order_a = _mk_order(manager_name="A")
    order_b = _mk_order(manager_name="B")
    sender = _mk_user("uc_rl2_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_rl2_target", "대상", role="STAFF")
    oid_a, oid_b, tid = order_a.id, order_b.id, target.id
    _login(client, sender)
    for i in range(5):
        assert _send(client, oid_a, tid, message=f"a{i}").status_code == 200
    # order_a 는 소진됐지만 order_b 는 첫 호출 → 200
    assert _send(client, oid_b, tid, message="b0").status_code == 200


# --------------------------------------------------------------------------- #
# one transaction: notification + child receipt state + NotificationEvent
#                  + source_domain=NOTIFICATION_EVENT side-effect row
# --------------------------------------------------------------------------- #
def test_send_writes_notification_state_event_and_sidefx_row_one_tx(client, db):
    order = _mk_order()
    sender = _mk_user("uc_tx_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_tx_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)
    resp = _send(client, oid, tid, "긴급")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    notif = (
        db.query(Notification)
        .filter(Notification.order_id == oid,
                Notification.notification_type == "URGENT_MENTION")
        .one()
    )
    # child receipt: 수신자 state 1건.
    states = (
        db.query(NotificationUserState)
        .filter(NotificationUserState.notification_id == notif.id)
        .all()
    )
    assert len(states) == 1 and states[0].user_id == target.id

    # NotificationEvent(created) 존재.
    created = (
        db.query(NotificationEvent)
        .filter(NotificationEvent.notification_id == notif.id,
                NotificationEvent.event_type == NotificationEventType.CREATED)
        .all()
    )
    assert len(created) == 1

    # source_domain=NOTIFICATION_EVENT side-effect row 정확히 1건, one-of FK 충족.
    outbox = db.query(DomainSideEffectOutbox).all()
    assert len(outbox) == 1
    row = outbox[0]
    assert row.source_domain == "NOTIFICATION_EVENT"
    assert row.notification_event_id == created[0].id
    assert row.order_event_id is None
    assert row.effect_type == "NOTIFICATION"
    assert row.status == "PENDING"
    assert row.payload.get("notification_id") == notif.id


def test_send_does_not_mutate_order_version(client, db):
    """Order/JSONB/version 무변경 (urgent send 는 notification 만)."""
    order = _mk_order(structured_data={"workflow": {"stage": "ERPORDER"}, "marker": 1})
    before_sd = dict(order.structured_data)
    sender = _mk_user("uc_om_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_om_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)
    assert _send(client, oid, tid, "긴급").status_code == 200

    fresh = db.get(Order, oid)
    assert fresh.structured_data == before_sd


def test_send_is_atomic_no_partial_on_sidefx_failure(client, db, monkeypatch):
    """side-effect enqueue 실패 시 notification/state/event/outbox 전부 롤백(부분 배달 0)."""
    order = _mk_order()
    sender = _mk_user("uc_atom_sender", "보낸이", role="ADMIN")
    target = _mk_user("uc_atom_target", "대상", role="STAFF")
    oid, tid = order.id, target.id
    _login(client, sender)

    def boom(*a, **k):
        raise RuntimeError("sidefx enqueue failed")

    monkeypatch.setattr("foms.api.notifications.enqueue_side_effect", boom)
    resp = _send(client, oid, tid, "긴급")
    assert resp.status_code == 500

    assert db.query(Notification).filter(Notification.order_id == oid).count() == 0
    assert db.query(NotificationUserState).count() == 0
    assert db.query(NotificationEvent).count() == 0
    assert db.query(DomainSideEffectOutbox).count() == 0


# --------------------------------------------------------------------------- #
# target list = order read scope (unrelated reader 통과), active·self 제외
# --------------------------------------------------------------------------- #
def test_target_list_unrelated_reader_200(client, db):
    """target list 도 order read scope 만 요구 → 무관 VIEWER 도 200 (P1-25)."""
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("uc_tl_reader", "무관뷰어", role="VIEWER", team="PRODUCTION")
    oid = order.id
    _login(client, caller)
    resp = client.get(f"/erp/api/orders/{oid}/urgent-targets")
    assert resp.status_code == 200


def test_target_list_excludes_inactive_and_self(client, db):
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("uc_tls_caller", "부르는이", role="ADMIN")
    active = _mk_user("uc_tls_active", "활성동료", role="STAFF", team="CS")
    _mk_user("uc_tls_inactive", "비활성동료", role="STAFF", is_active=False)
    oid, caller_id, active_id = order.id, caller.id, active.id
    _login(client, caller)
    resp = client.get(f"/erp/api/orders/{oid}/urgent-targets")
    assert resp.status_code == 200
    targets = resp.get_json()["targets"]
    ids = {t["id"] for t in targets}
    assert active_id in ids
    assert caller_id not in ids
    assert all(t["name"] != "비활성동료" for t in targets)
