"""Phase 3C: Web Push sender / enqueue / escalation / push-event 테스트.

DB fixture 는 tests/conftest.py 의 `app`(in-memory sqlite) + `client` 를 사용한다.
``pywebpush`` 는 미설치이므로 가짜 모듈을 sys.modules 에 주입해 발송 경로를 검증한다.
"""
import datetime
import sys
import types

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
from foms.services.notifications.escalation import (
    escalate_overdue_urgent,
    finalize_escalation_delivery,
)
from foms.services.notifications.push_sender import (
    _generic_title,
    _should_push,
    enqueue_push_for_notification,
    send_push_for_notification,
)

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}
FLAG_ENV = "FOMS_WEB_PUSH_ENABLED"
EVENT_URL = "/erp/api/notifications/push/event"


# ---------------------------------------------------------------------------
# fake pywebpush
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeWebPushException(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class _Recorder:
    """webpush 호출을 기록하고, 선택적으로 예외를 발생시키는 가짜 sender."""

    def __init__(self, exc=None):
        self.calls = []
        self._exc = exc

    def __call__(self, subscription_info, data, vapid_private_key=None, vapid_claims=None):
        self.calls.append(
            {
                "subscription_info": subscription_info,
                "data": data,
                "vapid_private_key": vapid_private_key,
                "vapid_claims": vapid_claims,
            }
        )
        if self._exc is not None:
            raise self._exc


def _install_pywebpush(monkeypatch, recorder):
    mod = types.ModuleType("pywebpush")
    mod.webpush = recorder
    mod.WebPushException = _FakeWebPushException
    monkeypatch.setitem(sys.modules, "pywebpush", mod)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mk_user(username, name, role="VIEWER", team=None, is_active=True):
    user = User(
        username=username, password="x", name=name, role=role, team=team,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _mk_notification(is_urgent=True, ntype="URGENT_MENTION", **kwargs):
    defaults = dict(
        notification_type=ntype,
        target_type="USER",
        title="고객 홍길동 #123 주문",
        message="현장 주소 서울시 강남구",
        is_urgent=is_urgent,
    )
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db_session.add(notif)
    db_session.flush()
    return notif


def _mk_state(notif, user, status=NotificationDeliveryStatus.PENDING, **kwargs):
    state = NotificationUserState(
        notification_id=notif.id,
        user_id=user.id,
        recipient_source=NotificationRecipientSource.TARGET_USER,
        last_delivery_status=status,
        **kwargs,
    )
    db_session.add(state)
    db_session.flush()
    return state


def _mk_sub(user, endpoint, p256dh="p256secret", auth="authsecret"):
    sub = NotificationPushSubscription(
        user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth,
    )
    db_session.add(sub)
    db_session.flush()
    return sub


def _events(notif_id, event_type):
    return (
        db_session.query(NotificationEvent)
        .filter_by(notification_id=notif_id, event_type=event_type)
        .all()
    )


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# ---------------------------------------------------------------------------
# send_push_for_notification: 발송 성공
# ---------------------------------------------------------------------------

def test_send_success_records_attempt_and_status(db, monkeypatch):
    rec = _Recorder()
    _install_pywebpush(monkeypatch, rec)
    u = _mk_user("s_ok", "A")
    notif = _mk_notification(is_urgent=True)
    state = _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/ok")

    result = send_push_for_notification(notif.id, db=db)
    assert result["sent"] == 1
    assert result["failed"] == 0
    assert len(rec.calls) == 1

    attempts = _events(notif.id, NotificationEventType.PUSH_ATTEMPTED)
    assert len(attempts) == 1
    assert attempts[0].channel == "webpush"
    assert attempts[0].endpoint_hash and len(attempts[0].endpoint_hash) == 64
    db.refresh(state)
    assert state.last_delivery_status == NotificationDeliveryStatus.PUSH_ATTEMPTED


def test_send_payload_is_generic_and_leaks_nothing(db, monkeypatch):
    rec = _Recorder()
    _install_pywebpush(monkeypatch, rec)
    u = _mk_user("s_leak", "A")
    notif = _mk_notification(is_urgent=True)
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/leak", p256dh="TOPSECRETKEY", auth="AUTHSECRET")

    send_push_for_notification(notif.id, db=db)
    sent = rec.calls[0]["data"]
    # payload 본문에 고객명/현장/구독 비밀이 없어야 한다.
    assert "홍길동" not in sent
    assert "강남" not in sent
    assert "TOPSECRETKEY" not in sent
    assert "AUTHSECRET" not in sent
    assert "fcm.googleapis.com" not in sent
    # 구독 비밀은 transport(subscription_info)로만 전달된다.
    assert rec.calls[0]["subscription_info"]["keys"]["p256dh"] == "TOPSECRETKEY"


# ---------------------------------------------------------------------------
# send_push_for_notification: 실패 경로
# ---------------------------------------------------------------------------

def test_send_410_revokes_subscription(db, monkeypatch):
    exc = _FakeWebPushException("gone", response=_FakeResp(410))
    _install_pywebpush(monkeypatch, _Recorder(exc=exc))
    u = _mk_user("s_410", "A")
    notif = _mk_notification(is_urgent=True)
    state = _mk_state(notif, u)
    sub = _mk_sub(u, "https://fcm.googleapis.com/send/gone")

    result = send_push_for_notification(notif.id, db=db)
    assert result["revoked"] == 1
    db.refresh(sub)
    assert sub.revoked_at is not None

    failed = _events(notif.id, NotificationEventType.PUSH_FAILED)
    assert len(failed) == 1
    assert failed[0].metadata_json.get("code") == 410
    db.refresh(state)
    assert state.last_delivery_status == NotificationDeliveryStatus.PUSH_FAILED


def test_send_other_exception_marks_failed_no_revoke(db, monkeypatch):
    _install_pywebpush(monkeypatch, _Recorder(exc=ValueError("boom")))
    u = _mk_user("s_err", "A")
    notif = _mk_notification(is_urgent=True)
    _mk_state(notif, u)
    sub = _mk_sub(u, "https://fcm.googleapis.com/send/err")

    result = send_push_for_notification(notif.id, db=db)
    assert result["failed"] == 1
    assert result["revoked"] == 0
    db.refresh(sub)
    assert sub.revoked_at is None  # 일시 실패는 revoke 하지 않음
    # 알림/이벤트는 살아있다(rollback 없음).
    assert len(_events(notif.id, NotificationEventType.PUSH_FAILED)) == 1
    assert db.query(Notification).filter_by(id=notif.id).first() is not None


# ---------------------------------------------------------------------------
# severity 게이트
# ---------------------------------------------------------------------------

def test_p2_type_is_noop(db, monkeypatch):
    rec = _Recorder()
    _install_pywebpush(monkeypatch, rec)
    u = _mk_user("s_p2", "A")
    notif = _mk_notification(is_urgent=False, ntype="ANNOUNCEMENT")
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/p2")

    result = send_push_for_notification(notif.id, db=db)
    assert result["reason"] == "severity_skipped"
    assert rec.calls == []
    assert _events(notif.id, NotificationEventType.PUSH_ATTEMPTED) == []


def test_p1_type_sends(db, monkeypatch):
    rec = _Recorder()
    _install_pywebpush(monkeypatch, rec)
    u = _mk_user("s_p1", "A")
    notif = _mk_notification(is_urgent=False, ntype="DRAWING_TRANSFERRED")
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/p1")

    result = send_push_for_notification(notif.id, db=db)
    assert result["sent"] == 1
    assert len(rec.calls) == 1


# ---------------------------------------------------------------------------
# enqueue: 큐/worker 미가용
# ---------------------------------------------------------------------------

def test_enqueue_queue_unavailable_marks_states(db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    import foms.services.jobs.queue as qmod

    monkeypatch.setattr(qmod, "get_rq_queue", lambda: None)
    monkeypatch.setattr(
        qmod, "get_rq_runtime_status", lambda: {"state": "disabled", "worker_count": 0}
    )

    u = _mk_user("q_un", "A")
    notif = _mk_notification(is_urgent=True)
    state = _mk_state(notif, u)

    result = enqueue_push_for_notification(notif.id, db=db)
    assert result["enqueued"] is False
    assert result["reason"] == "queue_unavailable"

    events = _events(notif.id, NotificationEventType.PUSH_QUEUE_UNAVAILABLE)
    assert len(events) == 1
    db.refresh(state)
    assert state.last_delivery_status == NotificationDeliveryStatus.QUEUE_UNAVAILABLE


def test_enqueue_flag_off_is_silent(db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "0")
    u = _mk_user("q_off", "A")
    notif = _mk_notification(is_urgent=True)
    _mk_state(notif, u)

    result = enqueue_push_for_notification(notif.id, db=db)
    assert result == {"enqueued": False, "reason": "flag_off"}
    assert _events(notif.id, NotificationEventType.PUSH_QUEUE_UNAVAILABLE) == []


def test_enqueue_success_uses_queue(db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    import foms.services.jobs.queue as qmod

    class _FakeQueue:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, path, *args, **kwargs):
            self.enqueued.append((path, args, kwargs))

    fake_q = _FakeQueue()
    monkeypatch.setattr(qmod, "get_rq_queue", lambda: fake_q)
    monkeypatch.setattr(
        qmod, "get_rq_runtime_status", lambda: {"state": "reachable", "worker_count": 1}
    )

    u = _mk_user("q_ok", "A")
    notif = _mk_notification(is_urgent=True)
    _mk_state(notif, u)

    result = enqueue_push_for_notification(notif.id, db=db)
    assert result["enqueued"] is True
    assert len(fake_q.enqueued) == 1
    path, args, _ = fake_q.enqueued[0]
    assert path.endswith("send_push_for_notification_task")
    assert args[0] == notif.id


def test_enqueue_unknown_worker_count_still_attempts_enqueue(db, monkeypatch):
    """worker 수를 못 센 경우(worker_count_known=False)는 미보장으로 떨어지면 안 된다.

    ping 은 통했는데 그 직후 Worker.count 조회만 실패하는 짧은 창이 실재한다(같은 날
    queue.py 에 이미 고친 문제). 예전 판정은 이때도 worker_count==0 이라 큐가 멀쩡한데
    알림 하나가 조용히 queue_unavailable 로 표기되고 넣어 보지도 않았다. worker_count_known
    을 보게 고친 뒤에는 못 셌을 때 막지 않고 실제 enqueue 를 시도해야 한다.
    """
    monkeypatch.setenv(FLAG_ENV, "1")
    import foms.services.jobs.queue as qmod

    class _FakeQueue:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, path, *args, **kwargs):
            self.enqueued.append((path, args, kwargs))

    fake_q = _FakeQueue()
    monkeypatch.setattr(qmod, "get_rq_queue", lambda: fake_q)
    monkeypatch.setattr(
        qmod,
        "get_rq_runtime_status",
        lambda: {"state": "reachable", "worker_count": 0, "worker_count_known": False},
    )

    u = _mk_user("q_unknown", "A")
    notif = _mk_notification(is_urgent=True)
    state = _mk_state(notif, u)

    result = enqueue_push_for_notification(notif.id, db=db)
    assert result["enqueued"] is True
    assert result["reason"] is None
    assert len(fake_q.enqueued) == 1
    # queue_unavailable 로 표기되지 않았는지도 확인 — 못 센 것과 진짜 0대를 가르는
    # 핵심 단언이다.
    assert _events(notif.id, NotificationEventType.PUSH_QUEUE_UNAVAILABLE) == []
    db.refresh(state)
    assert state.last_delivery_status != NotificationDeliveryStatus.QUEUE_UNAVAILABLE


def test_enqueue_known_zero_workers_still_marks_unavailable(db, monkeypatch):
    """worker 가 확실히 0대(worker_count_known=True)일 때는 좁힌 판정 이후에도 예전 그대로
    미보장으로 막아야 한다.

    이번 수정은 "못 셌다"만 새로 풀어주는 것이지, "진짜로 워커가 하나도 없다"는 판정까지
    같이 느슨해지면 안 된다(못을 빼면 안 된다). worker_count_known 을 명시적으로 True 로
    줘서 이 경계가 살아 있는지 확인한다.
    """
    monkeypatch.setenv(FLAG_ENV, "1")
    import foms.services.jobs.queue as qmod

    class _FakeQueue:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, path, *args, **kwargs):
            self.enqueued.append((path, args, kwargs))
            raise AssertionError("worker 0대가 확실하면 enqueue 를 시도하면 안 된다")

    fake_q = _FakeQueue()
    monkeypatch.setattr(qmod, "get_rq_queue", lambda: fake_q)
    monkeypatch.setattr(
        qmod,
        "get_rq_runtime_status",
        lambda: {"state": "reachable", "worker_count": 0, "worker_count_known": True},
    )

    u = _mk_user("q_knownzero", "A")
    notif = _mk_notification(is_urgent=True)
    state = _mk_state(notif, u)

    result = enqueue_push_for_notification(notif.id, db=db)
    assert result["enqueued"] is False
    assert result["reason"] == "queue_unavailable"
    assert fake_q.enqueued == []
    db.refresh(state)
    assert state.last_delivery_status == NotificationDeliveryStatus.QUEUE_UNAVAILABLE


# ---------------------------------------------------------------------------
# escalation
# ---------------------------------------------------------------------------

def _now():
    return datetime.datetime(2026, 7, 4, 12, 0, 0)


def test_escalation_stage1_notifies_team_manager(db):
    now = _now()
    victim = _mk_user("e_victim", "담당자", team="CS")
    manager = _mk_user("e_mgr", "매니저", role="MANAGER", team="CS")
    notif = _mk_notification(is_urgent=True, target_user_id=victim.id)
    state = _mk_state(notif, victim)
    state.created_at = now - datetime.timedelta(minutes=6)
    db.flush()

    result = escalate_overdue_urgent(db, now=now)
    assert result["escalated"] == 1
    db.refresh(state)
    assert state.escalated_at == now
    assert len(_events(notif.id, NotificationEventType.ESCALATED)) == 1

    mgr_notif = (
        db.query(Notification)
        .filter_by(notification_type="URGENT_ESCALATION", target_user_id=manager.id)
        .first()
    )
    assert mgr_notif is not None
    assert mgr_notif.is_urgent is False  # 재-escalation 방지
    assert (
        db.query(NotificationUserState)
        .filter_by(notification_id=mgr_notif.id, user_id=manager.id)
        .first()
        is not None
    )
    assert result["created_notification_ids"] == [mgr_notif.id]
    assert result["recipient_user_ids"] == [manager.id]


def test_escalation_stage2_operator_escalates_to_admin(db):
    now = _now()
    victim = _mk_user("e2_victim", "담당자", team="CS")
    _mk_user("e2_admin", "관리자", role="ADMIN")
    notif = _mk_notification(is_urgent=True, target_user_id=victim.id)
    state = _mk_state(notif, victim)
    state.escalated_at = now - datetime.timedelta(minutes=6)
    db.flush()

    result = escalate_overdue_urgent(db, now=now)
    assert result["operator_escalated"] == 1
    assert len(_events(notif.id, NotificationEventType.OPERATOR_ESCALATED)) == 1

    # 재실행 idempotent: 중복 이벤트/알림 없음.
    before = db.query(Notification).filter_by(notification_type="URGENT_ESCALATION").count()
    result2 = escalate_overdue_urgent(db, now=now)
    assert result2["operator_escalated"] == 0
    after = db.query(Notification).filter_by(notification_type="URGENT_ESCALATION").count()
    assert before == after


def test_escalation_stage1_idempotent(db):
    now = _now()
    victim = _mk_user("e3_victim", "담당자", team="CS")
    _mk_user("e3_mgr", "매니저", role="MANAGER", team="CS")
    notif = _mk_notification(is_urgent=True, target_user_id=victim.id)
    state = _mk_state(notif, victim)
    state.created_at = now - datetime.timedelta(minutes=6)
    db.flush()

    r1 = escalate_overdue_urgent(db, now=now)
    r2 = escalate_overdue_urgent(db, now=now)
    assert r1["escalated"] == 1
    assert r2["escalated"] == 0


def test_escalation_skips_acked(db):
    now = _now()
    victim = _mk_user("e4_victim", "담당자", team="CS")
    _mk_user("e4_mgr", "매니저", role="MANAGER", team="CS")
    notif = _mk_notification(is_urgent=True, target_user_id=victim.id)
    state = _mk_state(notif, victim)
    state.created_at = now - datetime.timedelta(minutes=6)
    state.ack_at = now - datetime.timedelta(minutes=1)
    db.flush()

    result = escalate_overdue_urgent(db, now=now)
    assert result["escalated"] == 0
    db.refresh(state)
    assert state.escalated_at is None


def test_escalation_p1_gate_and_generic_title():
    """URGENT_ESCALATION 은 is_urgent=False 여도 P1 push 대상 + 전용 제목."""
    notif = Notification(
        notification_type="URGENT_ESCALATION",
        target_type="USER",
        title="[에스컬레이션] 확인되지 않은 긴급 알림이 있습니다.",
        is_urgent=False,
    )
    assert _should_push(notif) is True
    assert _generic_title(False, "URGENT_ESCALATION") == "에스컬레이션"


def test_finalize_escalation_delivery_emits_and_enqueues(db, monkeypatch):
    """commit 후 finalize = badge invalidate + socket emit + push enqueue."""
    monkeypatch.setenv(FLAG_ENV, "1")
    import foms.services.jobs.queue as qmod

    class _FakeQueue:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, path, *args, **kwargs):
            self.enqueued.append((path, args, kwargs))

    fake_q = _FakeQueue()
    monkeypatch.setattr(qmod, "get_rq_queue", lambda: fake_q)
    monkeypatch.setattr(
        qmod, "get_rq_runtime_status", lambda: {"state": "reachable", "worker_count": 1}
    )

    emitted = []

    def _fake_emit(user_ids, payload=None):
        emitted.append((list(user_ids), dict(payload or {})))
        return len(list(user_ids))

    monkeypatch.setattr(
        "foms.services.notifications.realtime_notifications.emit_erp_notification_to_users",
        _fake_emit,
    )
    monkeypatch.setattr(
        "foms.api.notifications.invalidate_badge_cache_for_user_ids",
        lambda ids: None,
    )

    mgr = _mk_user("fin_mgr", "매니저", role="MANAGER", team="CS")
    esc = _mk_notification(
        is_urgent=False,
        ntype="URGENT_ESCALATION",
        target_user_id=mgr.id,
        title="[에스컬레이션] 확인되지 않은 긴급 알림이 있습니다.",
    )
    _mk_state(esc, mgr)
    db.flush()

    delivery = finalize_escalation_delivery(
        db,
        created_notification_ids=[esc.id],
        recipient_user_ids=[mgr.id],
    )
    assert delivery["pushed"] == 1
    assert delivery["realtime_sent"] == 1
    assert delivery["recipients"] == 1
    assert len(fake_q.enqueued) == 1
    assert emitted[0][0] == [mgr.id]
    assert emitted[0][1]["urgent"] is True
    assert emitted[0][1]["notification_type"] == "URGENT_ESCALATION"


def test_finalize_escalation_delivery_empty_noop(db):
    assert finalize_escalation_delivery(db, [], []) == {
        "pushed": 0,
        "realtime_sent": 0,
        "recipients": 0,
    }


# ---------------------------------------------------------------------------
# push/event endpoint
# ---------------------------------------------------------------------------

def _login(client, user_id):
    user = db_session.get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def test_push_event_opened_records(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("ev_ok", "A")
    notif = _mk_notification(is_urgent=True, target_user_id=u.id)
    state = _mk_state(notif, u)
    sid = state.id
    nid = notif.id
    db_session.commit()
    _login(client, u.id)

    r = client.post(
        EVENT_URL,
        json={"notification_id": nid, "event": "opened"},
        headers=WRITE_HEADERS,
    )
    assert r.status_code == 200
    # 요청 teardown 이 공유 세션을 닫으므로 refresh 대신 재조회한다.
    fresh = db.query(NotificationUserState).filter_by(id=sid).first()
    assert fresh.last_opened_at is not None
    assert fresh.last_delivery_status == NotificationDeliveryStatus.OPENED
    assert len(_events(nid, NotificationEventType.OPENED)) == 1


def test_push_event_other_user_notif_404(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    owner = _mk_user("ev_owner", "A")
    other = _mk_user("ev_other", "B")
    notif = _mk_notification(is_urgent=True, target_user_id=owner.id)
    _mk_state(notif, owner)
    db_session.commit()
    _login(client, other.id)

    r = client.post(
        EVENT_URL,
        json={"notification_id": notif.id, "event": "opened"},
        headers=WRITE_HEADERS,
    )
    assert r.status_code == 404


def test_push_event_missing_write_header_403(client, db, monkeypatch):
    monkeypatch.setenv(FLAG_ENV, "1")
    u = _mk_user("ev_hdr", "A")
    notif = _mk_notification(is_urgent=True, target_user_id=u.id)
    _mk_state(notif, u)
    db_session.commit()
    _login(client, u.id)

    r = client.post(EVENT_URL, json={"notification_id": notif.id, "event": "opened"})
    assert r.status_code == 403
