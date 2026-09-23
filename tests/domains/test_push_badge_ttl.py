"""웹 푸시 ttl·Urgency·수신자별 배지 숫자·관리자 구독 상태 표 계약.

기존 결함①: pywebpush 2.0.0 ``webpush(ttl=0)`` 기본값 때문에 기기가 꺼져 있으면 푸시가
바로 버려졌다. 발송 경로(알림 발송·시험 발송) 두 곳이 모두 ``ttl=86400`` 과 ``Urgency``
헤더를 넘기는지, 그리고 ``vapid_claims`` 가 호출마다 새 dict 인지(pywebpush 가 aud·exp 를
그 dict 에 직접 써 넣는다) 가짜 webpush 로 kwargs 를 잡아 확인한다. 실발송은 없다.
"""
from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path

import pytest

from db import db_session
from models import (
    Notification,
    NotificationDeliveryStatus,
    NotificationEvent,
    NotificationEventType,
    NotificationPushSubscription,
    NotificationRecipientSource,
    NotificationUserState,
    User,
)
from foms.services.notifications import push_sender
from foms.services.notifications.push_sender import (
    PUSH_TTL_SECONDS,
    send_push_for_notification,
    send_test_push,
)

ROOT = Path(__file__).resolve().parents[2]
SW = ROOT / "static/sw.js"
STATUS_URL = "/erp/api/notifications/push/subscriptions-status"


# ---------------------------------------------------------------------------
# 가짜 pywebpush
# ---------------------------------------------------------------------------

class _FakeWebPushException(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class _Recorder:
    """webpush 호출 kwargs 를 그대로 기록한다(실제 pywebpush 처럼 vapid_claims 를 고친다)."""

    def __init__(self):
        self.calls = []

    def __call__(self, subscription_info, data=None, **kwargs):
        claims = kwargs.get("vapid_claims")
        if claims is not None:
            # pywebpush 2.0.0 과 같은 부작용: 넘겨받은 dict 에 aud·exp 를 써 넣는다.
            claims.setdefault("aud", subscription_info["endpoint"].split("/send")[0])
            claims.setdefault("exp", 1)
        self.calls.append({"subscription_info": subscription_info, "data": data, **kwargs})


@pytest.fixture
def rec(monkeypatch):
    recorder = _Recorder()
    mod = types.ModuleType("pywebpush")
    mod.webpush = recorder
    mod.WebPushException = _FakeWebPushException
    monkeypatch.setitem(sys.modules, "pywebpush", mod)
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-private-key")
    monkeypatch.delenv("FOMS_PUSH_P1_TYPES", raising=False)
    return recorder


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mk_user(username, name, role="STAFF", team=None, is_active=True):
    user = User(username=username, password="x", name=name, role=role, team=team,
                is_active=is_active)
    db_session.add(user)
    db_session.flush()
    return user


def _mk_notification(ntype, is_urgent=False, **kwargs):
    defaults = dict(
        notification_type=ntype,
        target_type="TEAM",
        target_team="SALES",
        title="고객 홍길동 오늘 실측",
        message="서울시 강남구 14:00",
        is_urgent=is_urgent,
    )
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db_session.add(notif)
    db_session.flush()
    return notif


def _mk_state(notif, user, **kwargs):
    state = NotificationUserState(
        notification_id=notif.id,
        user_id=user.id,
        recipient_source=NotificationRecipientSource.TARGET_TEAM,
        last_delivery_status=NotificationDeliveryStatus.PENDING,
        **kwargs,
    )
    db_session.add(state)
    db_session.flush()
    return state


def _mk_sub(user, endpoint, **kwargs):
    sub = NotificationPushSubscription(
        user_id=user.id, endpoint=endpoint, p256dh="p", auth="a", **kwargs
    )
    db_session.add(sub)
    db_session.flush()
    return sub


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


# ---------------------------------------------------------------------------
# ttl · Urgency · vapid_claims
# ---------------------------------------------------------------------------

def test_push_ttl_constant_is_one_day():
    assert PUSH_TTL_SECONDS == 86400


@pytest.mark.parametrize(
    "ntype,is_urgent,expected",
    [
        ("MEASURE_SAME_DAY_ADDED", False, "high"),
        ("URGENT_MENTION", True, "high"),
        ("SHIPMENT_ORDER_CHANGED", False, "normal"),
        ("DRAWING_TRANSFERRED", False, "normal"),
    ],
)
def test_webpush_gets_ttl_and_urgency_header(db, rec, ntype, is_urgent, expected):
    u = _mk_user(f"ttl_{ntype.lower()}_{int(is_urgent)}", "영업", team="SALES")
    notif = _mk_notification(ntype, is_urgent=is_urgent)
    _mk_state(notif, u)
    _mk_sub(u, f"https://fcm.googleapis.com/send/{ntype}-{int(is_urgent)}")

    result = send_push_for_notification(notif.id, db=db)

    assert result["sent"] == 1
    call = rec.calls[0]
    assert call["ttl"] == 86400
    assert call["headers"] == {"Urgency": expected}


def test_vapid_claims_and_headers_are_fresh_dicts_per_call(db, rec):
    u = _mk_user("ttl_two_devices", "영업", team="SALES")
    notif = _mk_notification("MEASURE_SAME_DAY_ADDED")
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/device-a")
    _mk_sub(u, "https://web.push.apple.com/send/device-b")

    send_push_for_notification(notif.id, db=db)

    assert len(rec.calls) == 2
    first, second = rec.calls
    # pywebpush 가 첫 호출 dict 에 aud 를 써 넣어도 두 번째 호출은 새 dict 라 오염되지 않는다.
    assert first["vapid_claims"] is not second["vapid_claims"]
    assert first["vapid_claims"]["aud"] != second["vapid_claims"]["aud"]
    assert first["headers"] is not second["headers"]


def test_skip_attempted_does_not_resend_to_already_pushed_recipient(db, rec):
    """outbox 재시도(skip_attempted)는 이미 PUSH_ATTEMPTED 인 사람에게 다시 보내지 않는다."""
    done = _mk_user("ttl_retry_done", "받은영업", team="SALES")
    fresh = _mk_user("ttl_retry_fresh", "못받은영업", team="SALES")
    notif = _mk_notification("URGENT_MENTION", is_urgent=True)
    _mk_state(notif, done).last_delivery_status = NotificationDeliveryStatus.PUSH_ATTEMPTED
    _mk_state(notif, fresh)
    _mk_sub(done, "https://fcm.googleapis.com/send/retry-done")
    _mk_sub(fresh, "https://fcm.googleapis.com/send/retry-fresh")
    db.flush()

    result = send_push_for_notification(notif.id, db=db, skip_attempted=True)

    assert result["sent"] == 1
    assert [c["subscription_info"]["endpoint"] for c in rec.calls] == [
        "https://fcm.googleapis.com/send/retry-fresh"
    ]


def test_test_push_also_uses_ttl_and_normal_urgency(db, rec):
    u = _mk_user("ttl_test_send", "영업", team="SALES")
    sub = _mk_sub(u, "https://fcm.googleapis.com/send/test-send")

    result = send_test_push(sub.id, db=db)

    assert result["sent"] is True
    assert rec.calls[0]["ttl"] == 86400
    assert rec.calls[0]["headers"] == {"Urgency": "normal"}


# ---------------------------------------------------------------------------
# 수신자별 unread_count · 당일 실측 유형
# ---------------------------------------------------------------------------

def test_unread_count_differs_per_recipient(db, rec):
    a = _mk_user("badge_a", "영업A", team="SALES")
    b = _mk_user("badge_b", "영업B", team="MEASURE")
    notif = _mk_notification("MEASURE_SAME_DAY_ADDED")
    _mk_state(notif, a)
    _mk_state(notif, b)
    # a 에게만 미읽음 2건을 더 둔다(읽은 것·보관한 것은 세지 않는다).
    for i in range(2):
        extra = _mk_notification("QUEST_ASSIGNED", title=f"extra-{i}")
        _mk_state(extra, a)
    read_one = _mk_notification("QUEST_ASSIGNED", title="read")
    _mk_state(read_one, a, read_at=push_sender._now())
    archived = _mk_notification("QUEST_ASSIGNED", title="archived")
    _mk_state(archived, b, archived_at=push_sender._now())
    _mk_sub(a, "https://fcm.googleapis.com/send/badge-a")
    _mk_sub(b, "https://fcm.googleapis.com/send/badge-b")

    send_push_for_notification(notif.id, db=db)

    by_endpoint = {
        c["subscription_info"]["endpoint"]: json.loads(c["data"]) for c in rec.calls
    }
    assert by_endpoint["https://fcm.googleapis.com/send/badge-a"]["data"]["unread_count"] == 3
    assert by_endpoint["https://fcm.googleapis.com/send/badge-b"]["data"]["unread_count"] == 1


def test_measure_same_day_is_p1_and_payload_has_no_customer(db, rec):
    u = _mk_user("meas_p1", "영업", team="SALES")
    notif = _mk_notification("MEASURE_SAME_DAY_ADDED", order_id=None)
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/meas-p1")

    assert "MEASURE_SAME_DAY_ADDED" in push_sender._DEFAULT_P1_TYPES
    result = send_push_for_notification(notif.id, db=db)

    assert result["sent"] == 1
    body = rec.calls[0]["data"]
    payload = json.loads(body)
    assert payload["title"] == "긴급 실측 추가"
    assert payload["body"] == "오늘 실측이 긴급 추가됐어요"
    assert payload["tag"] == f"foms-meas-{notif.id}"
    assert payload["renotify"] is True
    assert "requireInteraction" not in payload
    for secret in ("홍길동", "강남", "14:00"):
        assert secret not in body


def test_push_attempt_event_recorded_for_admin_table(db, rec):
    u = _mk_user("meas_event", "영업", team="SALES")
    notif = _mk_notification("MEASURE_SAME_DAY_ADDED")
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/meas-event")

    send_push_for_notification(notif.id, db=db)

    events = (
        db.query(NotificationEvent)
        .filter_by(recipient_user_id=u.id, event_type=NotificationEventType.PUSH_ATTEMPTED)
        .all()
    )
    assert len(events) == 1


# ---------------------------------------------------------------------------
# sw.js push 핸들러 문자열 계약
# ---------------------------------------------------------------------------

def _push_handler_block() -> str:
    sw = SW.read_text(encoding="utf-8")
    start = re.search(r"addEventListener\(\s*['\"]push['\"]", sw).start()
    end = sw.index("function sanitizePushDeepLink", start)
    return sw[start:end]


def test_sw_push_handler_sets_badge_inside_wait_until():
    block = _push_handler_block()
    assert "setAppBadge" in block
    assert "Promise.all" in block
    assert "pushData.unread_count" in block
    # showNotification 은 waitUntil 이 기다리는 jobs 의 첫 항목이다(iOS 무음 push 해지 규칙).
    assert "var jobs = [self.registration.showNotification(title, options)];" in block
    assert "event.waitUntil(Promise.all(jobs));" in block
    assert block.count("event.waitUntil(") == 1


# ---------------------------------------------------------------------------
# 관리자 구독 상태 API
# ---------------------------------------------------------------------------

def test_subscription_status_requires_admin(client, db, monkeypatch):
    monkeypatch.delenv("FOMS_WEB_PUSH_ENABLED", raising=False)
    staff = _mk_user("status_staff", "직원", role="STAFF", team="SALES")
    _login(client, staff)

    resp = client.get(STATUS_URL)

    assert resp.status_code == 403
    assert resp.get_json()["success"] is False


def test_subscription_status_lists_sales_and_measure_for_admin(client, db, monkeypatch):
    # 웹푸시 플래그가 꺼져 있어도 진단 표는 200 이어야 한다.
    monkeypatch.delenv("FOMS_WEB_PUSH_ENABLED", raising=False)
    admin = _mk_user("status_admin", "관리자", role="ADMIN", team="CS")
    sales = _mk_user("status_sales", "가영업", team="SALES")
    measure = _mk_user("status_measure", "나실측", team="measure")
    _mk_user("status_inactive", "다퇴사", team="SALES", is_active=False)
    _mk_user("status_cs", "라씨에스", team="CS")
    _mk_sub(sales, "https://fcm.googleapis.com/send/status-1", platform="android",
            permission_state="granted", last_seen_at=push_sender._now())
    _mk_sub(sales, "https://fcm.googleapis.com/send/status-2", platform="ios",
            permission_state="granted")
    _mk_sub(measure, "https://fcm.googleapis.com/send/status-3",
            revoked_at=push_sender._now())
    notif = _mk_notification("MEASURE_SAME_DAY_ADDED")
    state = _mk_state(notif, sales)
    db.add(NotificationEvent(
        notification_id=notif.id, user_state_id=state.id, recipient_user_id=sales.id,
        event_type=NotificationEventType.PUSH_ATTEMPTED, channel="webpush",
    ))
    db.flush()
    _login(client, admin)

    resp = client.get(STATUS_URL)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    rows = {r["username"]: r for r in body["data"]["rows"]}
    assert set(rows) == {"status_sales", "status_measure"}
    assert rows["status_sales"]["active_subscriptions"] == 2
    assert rows["status_sales"]["platform"] == "ios"  # 최신 구독
    assert rows["status_sales"]["last_seen_at"]
    assert rows["status_sales"]["last_push_at"]
    assert rows["status_measure"]["active_subscriptions"] == 0
    assert rows["status_measure"]["last_push_at"] is None
    assert rows["status_measure"]["team"] == "MEASURE"
    # 구독 비밀·endpoint 원문은 응답에 없다.
    assert "fcm.googleapis.com" not in resp.get_data(as_text=True)
