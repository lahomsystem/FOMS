"""맨 위 줄 ⚡ 긴급 호출 — ``POST /erp/api/urgent-call`` · ``GET /erp/api/urgent-targets``.

SPEC ``docs/specs/2026-10-01-urgent-call-global_SPEC.md`` §3·§6. 주문은 골라도 되고 안 골라도 된다.
- 주문 없음: 로그인 사용자 누구나, 횟수 제한 없음, ``Notification.order_id is None``, 감사 로그는 사용자 대상.
- 주문 있음: 기존 주문 문맥 규칙 그대로(read scope · 주문당 5회/시간 · 같은 tx).
- 검증(빈 사유·자기 자신·비활성·없는 사용자)은 둘 다 같다.
"""

from __future__ import annotations

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
    SecurityLog,
    User,
)

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}


def _mk_user(username, name, role="STAFF", team=None, is_active=True):
    user = User(username=username, password="x", name=name, team=team, role=role, is_active=is_active)
    db_session.add(user)
    db_session.flush()
    return user


def _mk_order(**kwargs):
    order = Order(
        received_date=datetime.date(2026, 10, 1),
        customer_name=kwargs.get("customer_name", "고객"),
        phone="010-0000-0000",
        address="Seoul",
        product="가구",
        status="ERPORDER",
        manager_name="담당자",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "ERPORDER"}},
    )
    db_session.add(order)
    db_session.flush()
    return order


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _call(client, target_id, message="확인 부탁", order_id=None, headers=WRITE_HEADERS):
    body = {"target_user_id": target_id, "message": message}
    if order_id is not None:
        body["order_id"] = order_id
    return client.post("/erp/api/urgent-call", json=body, headers=headers)


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# --------------------------------------------------------------------------- #
# 주문 없음
# --------------------------------------------------------------------------- #
def test_no_order_writes_notification_state_event_outbox_and_user_audit(client, db):
    sender = _mk_user("ucg_no_sender", "보낸이", role="STAFF", team="SALES")
    target = _mk_user("ucg_no_target", "받는이", role="STAFF", team="DRAWING")
    sid, tid = sender.id, target.id
    _login(client, sender)

    resp = _call(client, tid, "도면 확인 부탁")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json() == {"success": True, "message": "받는이님에게 긴급 호출을 보냈습니다."}

    notif = db.query(Notification).filter(Notification.created_by_user_id == sid).one()
    assert notif.order_id is None
    assert notif.notification_type == "URGENT_MENTION"
    assert notif.is_urgent is True
    assert notif.target_user_id == tid
    assert notif.title == "[긴급 호출] 보낸이님이 호출했습니다"
    assert notif.message == "도면 확인 부탁"

    states = db.query(NotificationUserState).filter(NotificationUserState.notification_id == notif.id).all()
    assert [s.user_id for s in states] == [tid]
    created = (
        db.query(NotificationEvent)
        .filter(NotificationEvent.notification_id == notif.id,
                NotificationEvent.event_type == NotificationEventType.CREATED)
        .all()
    )
    assert len(created) == 1
    outbox = db.query(DomainSideEffectOutbox).all()
    assert len(outbox) == 1
    assert outbox[0].notification_event_id == created[0].id
    assert outbox[0].payload == {"notification_id": notif.id, "recipient_user_id": tid,
                                 "order_id": None, "kind": "URGENT_MENTION"}

    audit = db.query(SecurityLog).filter(SecurityLog.action == "URGENT_MENTION_SENT").all()
    assert len(audit) == 1
    assert audit[0].target_type == "user" and audit[0].target_id == tid


def test_no_order_has_no_rate_limit(client, db):
    """사용자 결정 2026-10-01: 주문 없는 호출은 횟수 제한 없음(주문 있는 5회 상한과 다르다)."""
    sender = _mk_user("ucg_rl_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_rl_target", "받는이")
    tid = target.id
    _login(client, sender)
    for i in range(8):
        r = _call(client, tid, f"호출 {i}")
        assert r.status_code == 200, (i, r.get_data(as_text=True))


def test_no_order_viewer_can_send(client, db):
    """⚡ 는 모든 직원에게 보인다 — VIEWER 도 보낸다(SEND_URGENT_CALL ancillary)."""
    sender = _mk_user("ucg_v_sender", "뷰어", role="VIEWER", team="PRODUCTION")
    target = _mk_user("ucg_v_target", "받는이")
    tid = target.id
    _login(client, sender)
    assert _call(client, tid).status_code == 200


@pytest.mark.parametrize(
    "case, status",
    [("empty_message", 400), ("too_long", 400), ("self", 400), ("missing_target", 400),
     ("bad_target", 400), ("unknown_target", 404), ("inactive_target", 422)],
)
def test_no_order_validation(client, db, case, status):
    sender = _mk_user(f"ucg_val_s_{case}", "보낸이", role="ADMIN")
    active = _mk_user(f"ucg_val_a_{case}", "받는이")
    inactive = _mk_user(f"ucg_val_i_{case}", "비활성", is_active=False)
    sid, aid, iid = sender.id, active.id, inactive.id
    _login(client, sender)
    target, message = {
        "empty_message": (aid, "   "),
        "too_long": (aid, "x" * 501),
        "self": (sid, "확인"),
        "missing_target": (None, "확인"),
        "bad_target": ("abc", "확인"),
        "unknown_target": (999_999, "확인"),
        "inactive_target": (iid, "확인"),
    }[case]
    resp = _call(client, target, message)
    assert resp.status_code == status, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is False
    assert db.query(Notification).filter(Notification.created_by_user_id == sid).count() == 0


def test_requires_write_header(client, db):
    sender = _mk_user("ucg_h_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_h_target", "받는이")
    tid = target.id
    _login(client, sender)
    resp = _call(client, tid, headers={})
    assert resp.status_code in (400, 403)


def test_requires_login(client, db):
    target = _mk_user("ucg_l_target", "받는이")
    resp = _call(client, target.id)
    assert resp.status_code in (302, 401, 403)


# --------------------------------------------------------------------------- #
# 주문 있음 — 기존 주문 문맥 규칙 그대로
# --------------------------------------------------------------------------- #
def test_with_order_binds_order_and_keeps_title_and_order_audit(client, db):
    order = _mk_order(customer_name="홍길동")
    sender = _mk_user("ucg_o_sender", "보낸이", role="STAFF", team="SALES")
    target = _mk_user("ucg_o_target", "받는이")
    oid, sid, tid = order.id, sender.id, target.id
    _login(client, sender)

    resp = _call(client, tid, "급해요", order_id=oid)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    notif = db.query(Notification).filter(Notification.created_by_user_id == sid).one()
    assert notif.order_id == oid
    assert notif.title == f"[긴급 멘션] 보낸이님이 #{oid} 홍길동 주문에서 호출했습니다"
    audit = db.query(SecurityLog).filter(SecurityLog.action == "URGENT_MENTION_SENT").one()
    assert audit.target_type == "order" and audit.target_id == oid


def test_with_order_string_id_accepted(client, db):
    order = _mk_order()
    sender = _mk_user("ucg_os_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_os_target", "받는이")
    oid, tid = order.id, target.id
    _login(client, sender)
    assert _call(client, tid, order_id=str(oid)).status_code == 200


def test_with_order_rate_limit_five_per_hour_shared_with_old_route(client, db):
    """주문을 고르면 주문당 5회/시간 — 옛 주문 라우트와 같은 카운터를 쓴다."""
    order = _mk_order()
    sender = _mk_user("ucg_orl_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_orl_target", "받는이")
    oid, tid = order.id, target.id
    _login(client, sender)
    for i in range(3):
        assert _call(client, tid, f"새 {i}", order_id=oid).status_code == 200
    for i in range(2):
        r = client.post(f"/erp/api/orders/{oid}/urgent-mention",
                        json={"target_user_id": tid, "message": f"옛 {i}"}, headers=WRITE_HEADERS)
        assert r.status_code == 200
    assert _call(client, tid, "여섯번째", order_id=oid).status_code == 429
    # 주문 없이는 여전히 보낼 수 있다.
    assert _call(client, tid, "주문 없이").status_code == 200


def test_with_unknown_order_404(client, db):
    sender = _mk_user("ucg_uo_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_uo_target", "받는이")
    tid = target.id
    _login(client, sender)
    assert _call(client, tid, order_id=987_654).status_code == 404


def test_with_bad_order_id_400(client, db):
    sender = _mk_user("ucg_bo_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_bo_target", "받는이")
    tid = target.id
    _login(client, sender)
    assert _call(client, tid, order_id="abc").status_code == 400


def test_empty_string_order_id_means_no_order(client, db):
    sender = _mk_user("ucg_eo_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_eo_target", "받는이")
    sid, tid = sender.id, target.id
    _login(client, sender)
    assert _call(client, tid, order_id="").status_code == 200
    assert db.query(Notification).filter(Notification.created_by_user_id == sid).one().order_id is None


def test_atomic_rollback_on_sidefx_failure_no_order(client, db, monkeypatch):
    sender = _mk_user("ucg_at_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucg_at_target", "받는이")
    sid, tid = sender.id, target.id
    _login(client, sender)

    def boom(*a, **k):
        raise RuntimeError("sidefx enqueue failed")

    monkeypatch.setattr("foms.api.notifications.enqueue_side_effect", boom)
    assert _call(client, tid).status_code == 500
    assert db.query(Notification).filter(Notification.created_by_user_id == sid).count() == 0
    assert db.query(DomainSideEffectOutbox).count() == 0


# --------------------------------------------------------------------------- #
# 주문 없는 대상 목록
# --------------------------------------------------------------------------- #
def test_targets_without_order_excludes_self_and_inactive_sorted_by_team(client, db):
    caller = _mk_user("ucg_t_caller", "부르는이", role="VIEWER")
    cs = _mk_user("ucg_t_cs", "가CS", team="CS")
    _mk_user("ucg_t_off", "비활성동료", is_active=False)
    nobody = _mk_user("ucg_t_none", "가팀없음", team=None)
    cid, cs_id, none_id = caller.id, cs.id, nobody.id
    _login(client, caller)
    resp = client.get("/erp/api/urgent-targets")
    assert resp.status_code == 200
    targets = resp.get_json()["targets"]
    ids = [t["id"] for t in targets]
    assert cs_id in ids and none_id in ids and cid not in ids
    assert all(t["name"] != "비활성동료" for t in targets)
    by_id = {t["id"]: t for t in targets}
    assert by_id[none_id]["team_label"] == "기타"
    # 팀 없음(기타)은 팀이 있는 사람 뒤.
    assert ids.index(cs_id) < ids.index(none_id)


def test_targets_without_order_same_list_as_order_route(client, db):
    order = _mk_order()
    caller = _mk_user("ucg_ts_caller", "부르는이", role="ADMIN")
    _mk_user("ucg_ts_a", "동료A", team="SALES")
    oid = order.id
    _login(client, caller)
    a = client.get("/erp/api/urgent-targets").get_json()["targets"]
    b = client.get(f"/erp/api/orders/{oid}/urgent-targets").get_json()["targets"]
    assert a == b
