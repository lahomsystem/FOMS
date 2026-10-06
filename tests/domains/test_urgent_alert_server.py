"""긴급 알림 어디서나 띄우기 — 서버 계약(SPEC 2026-10-02 §C·§D).

왜: 받는 쪽 빨간 창의 "확인" 은 payload 에 ``notification_id`` 가 있어야 ack 를 기록한다.
긴급 멘션·긴급 공지 둘 다 id 를 안 실어 ack 가 안 됐고, 소켓이 끊긴 동안 온 긴급은
다시 뜨지 않았으며, PC 팝업 클릭은 창을 다시 읽어 빨간 창을 지웠다.
여기서 고정하는 것:
  - 긴급 멘션 socket payload 에 ``notification_id``.
  - 긴급 공지는 수신자마다 **자기** Notification id 를 실어 따로 emit.
  - ``GET /erp/api/notifications/pending-urgent`` 는 본인·미확인·미보관·긴급·24시간 이내만.
  - web push payload ``data.urgent`` (sw.js 가 navigate 하지 않는 표지).
"""

from __future__ import annotations

import datetime as dt

import pytest

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.notifications import push_sender
from foms.services.notifications import realtime_notifications
from foms.services.notifications.push_sender import _build_payload
from models import (
    Notification,
    NotificationRecipientSource,
    NotificationUserState,
    Order,
    User,
)

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}
ENDPOINT = "/erp/api/notifications/pending-urgent"


def _mk_user(username, name, role="STAFF", team="SALES"):
    user = User(
        username=username, password="x", name=name, team=team, role=role, is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _mk_order():
    order = Order(
        received_date=dt.date(2026, 7, 4),
        customer_name="고객",
        phone="010-0000-0000",
        address="Seoul",
        product="가구",
        status="ERPORDER",
        manager_name="담당",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "ERPORDER"}},
    )
    db_session.add(order)
    db_session.flush()
    return order


def _login(client, info):
    with client.session_transaction() as sess:
        sess["user_id"] = info["id"]
        sess["username"] = info["username"]
        sess["role"] = info["role"]


def _info(user):
    return {"id": user.id, "username": user.username, "role": user.role}


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def emitted(monkeypatch):
    calls = []

    def _fake_emit(user_ids, payload=None):
        ids = list(user_ids)
        calls.append((ids, dict(payload or {})))
        return len(ids)

    monkeypatch.setattr(realtime_notifications, "emit_erp_notification_to_users", _fake_emit)
    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", lambda *_a, **_k: None)
    return calls


# --------------------------------------------------------------------------- #
# socket payload 에 notification_id
# --------------------------------------------------------------------------- #
def test_urgent_mention_emit_carries_notification_id(client, db, emitted):
    order = _mk_order()
    sender = _mk_user("ua_sender", "보내는이")
    target = _mk_user("ua_target", "받는이")
    oid, tid, sender_info = order.id, target.id, _info(sender)
    db_session.commit()
    _login(client, sender_info)

    resp = client.post(
        "/erp/api/urgent-call",
        json={"order_id": oid, "target_user_id": tid, "message": "확인 부탁"},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    notif = (
        db_session.query(Notification)
        .filter(Notification.notification_type == "URGENT_MENTION",
                Notification.target_user_id == tid)
        .one()
    )
    assert len(emitted) == 1
    ids, payload = emitted[0]
    assert ids == [tid]
    assert payload["urgent"] is True
    assert payload["notification_id"] == notif.id


def test_urgent_announcement_emits_each_recipient_own_notification_id(client, db, emitted):
    admin = _mk_user("ua_admin", "관리자", role="ADMIN", team=None)
    r1 = _mk_user("ua_r1", "수신1")
    r2 = _mk_user("ua_r2", "수신2")
    admin_info, r1_id, r2_id = _info(admin), r1.id, r2.id
    db_session.commit()
    _login(client, admin_info)

    resp = client.post(
        "/erp/api/notifications/send",
        json={"title": "긴급 공지", "message": "모두 확인", "is_urgent": True,
              "target_type": "USER", "target_user_ids": [r1_id, r2_id]},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()

    rows = (
        db_session.query(Notification)
        .filter(Notification.notification_type == "URGENT_ANNOUNCEMENT")
        .all()
    )
    own_id = {n.target_user_id: n.id for n in rows}
    assert len(set(own_id.values())) == len(own_id) >= 2

    # 수신자마다 한 번씩, 자기 row id 를 싣는다.
    assert all(len(ids) == 1 for ids, _ in emitted)
    by_uid = {ids[0]: payload for ids, payload in emitted}
    assert set(by_uid) == set(own_id)
    for uid, payload in by_uid.items():
        assert payload["notification_id"] == own_id[uid]
        assert payload["urgent"] is True
    # realtime_sent 는 실제 전송된 수신자 수 합계(의미 불변).
    assert body["realtime_sent"] == len(own_id) == body["sent_count"]


def test_plain_announcement_keeps_single_broadcast_without_id(client, db, emitted):
    admin = _mk_user("ua_admin2", "관리자", role="ADMIN", team=None)
    r1 = _mk_user("ua_r3", "수신3")
    admin_info, r1_id = _info(admin), r1.id
    db_session.commit()
    _login(client, admin_info)

    resp = client.post(
        "/erp/api/notifications/send",
        json={"title": "공지", "target_type": "USER", "target_user_ids": [r1_id]},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(emitted) == 1
    assert "notification_id" not in emitted[0][1]


# --------------------------------------------------------------------------- #
# pending-urgent 재조회
# --------------------------------------------------------------------------- #
def _mk_notif(*, urgent=True, created_at=None, title="긴급", order_id=None):
    notif = Notification(
        order_id=order_id,
        notification_type="URGENT_MENTION" if urgent else "ANNOUNCEMENT",
        target_type="USER",
        is_urgent=urgent,
        title=title,
        message="사유",
        created_by_name="호출자",
        created_at=created_at or now_utc_naive(),
    )
    db_session.add(notif)
    db_session.flush()
    return notif


def _mk_state(notif, user, **kwargs):
    db_session.add(NotificationUserState(
        notification_id=notif.id,
        user_id=user.id,
        recipient_source=NotificationRecipientSource.TARGET_USER,
        **kwargs,
    ))
    db_session.flush()


def _items(client):
    res = client.get(ENDPOINT)
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()
    assert body["success"] is True
    assert body["error"] is None
    return body["data"]["items"]


def test_pending_urgent_returns_only_my_unacked_unarchived_recent_urgent(client, db):
    me = _mk_user("ua_me", "나")
    other = _mk_user("ua_other", "남")
    order = _mk_order()
    now = now_utc_naive()

    mine = _mk_notif(order_id=order.id, title="내 긴급")
    _mk_state(mine, me)

    # 음성 대조군 — 모두 같은 모집단(긴급 알림 + state) 안에서 하나씩만 어긋난다.
    others_only = _mk_notif()
    _mk_state(others_only, other)
    acked = _mk_notif()
    _mk_state(acked, me, ack_at=now)
    archived = _mk_notif()
    _mk_state(archived, me, archived_at=now)
    not_urgent = _mk_notif(urgent=False)
    _mk_state(not_urgent, me)
    too_old = _mk_notif(created_at=now - dt.timedelta(hours=24, minutes=1))
    _mk_state(too_old, me)

    mine_id, order_id, others_id = mine.id, order.id, others_only.id
    me_info, other_info = _info(me), _info(other)
    db_session.commit()

    _login(client, me_info)
    items = _items(client)
    assert [i["notification_id"] for i in items] == [mine_id]
    assert items[0] == {
        "urgent": True,
        "notification_id": mine_id,
        "notification_type": "URGENT_MENTION",
        "title": "내 긴급",
        "message": "사유",
        "order_id": order_id,
        "created_by_name": "호출자",
    }

    _login(client, other_info)
    assert [i["notification_id"] for i in _items(client)] == [others_id]


def test_pending_urgent_oldest_first_and_capped_at_five(client, db):
    me = _mk_user("ua_cap", "나")
    base = now_utc_naive() - dt.timedelta(minutes=5)
    created = []
    for i in range(7):
        n = _mk_notif(created_at=base + dt.timedelta(seconds=i))
        _mk_state(n, me)
        created.append(n.id)
    me_info = _info(me)
    db_session.commit()
    _login(client, me_info)
    assert [i["notification_id"] for i in _items(client)] == created[:5]


def test_pending_urgent_requires_login(client):
    res = client.get(ENDPOINT)
    assert res.status_code in (301, 302, 401, 403)


# --------------------------------------------------------------------------- #
# web push payload
# --------------------------------------------------------------------------- #
def test_push_payload_marks_urgent_in_data(db):
    urgent = _mk_notif()
    plain = _mk_notif(urgent=False)
    up = _build_payload(urgent)
    assert up["data"]["urgent"] is True
    assert up["data"]["notification_id"] == urgent.id
    assert "deep_link" in up["data"]
    assert up["requireInteraction"] is True
    assert "urgent" not in _build_payload(plain)["data"]
