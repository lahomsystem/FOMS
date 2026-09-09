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
    _build_payload,
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


@pytest.fixture(autouse=True)
def web_push_flag_on(monkeypatch):
    """웹푸시 기능 플래그를 켠 상태를 이 파일의 기본으로 둔다.

    발송 함수(``_send_push_impl``)가 맨 앞에서 플래그를 보게 되면서 — rq 를 안 거치는
    직접 호출자(워커 정지 감시자)의 우회를 막는 게이트다 — 발송 경로 테스트는 플래그가
    켜져 있어야 실제 발송까지 간다. 꺼진 상태를 보는 테스트는 각자 다시 끈다.
    """
    monkeypatch.setenv(FLAG_ENV, "1")


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


def test_send_is_skipped_when_the_web_push_flag_is_off(db, monkeypatch):
    """플래그가 꺼져 있으면 **직접 호출자**도 발송하지 못한다.

    감시자(SIDEFX)는 큐가 죽었다는 사실을 알리는 알림이라 rq 를 거치지 않고
    ``send_push_for_notification`` 을 직접 부른다. 검사가 enqueue 경로에만 있던 동안
    그 경로는 "웹푸시 꺼짐" 을 통째로 우회했다 — 규칙의 정본은 발송 함수 하나다.
    긴급(P0) 알림으로 확인한다: severity 가 아니라 플래그가 먼저 막아야 한다.
    """
    monkeypatch.setenv(FLAG_ENV, "0")
    rec = _Recorder()
    _install_pywebpush(monkeypatch, rec)
    u = _mk_user("s_flagoff", "A")
    notif = _mk_notification(is_urgent=True)
    _mk_state(notif, u)
    _mk_sub(u, "https://fcm.googleapis.com/send/flagoff")

    result = send_push_for_notification(notif.id, db=db)
    assert result["reason"] == "flag_off"
    assert rec.calls == [], "플래그가 꺼졌는데 실제로 발송했다"
    assert _events(notif.id, NotificationEventType.PUSH_ATTEMPTED) == []


# ---------------------------------------------------------------------------
# 워커 건강 push (2026-09-08: 무내용 push 20건이 쌓인 사건)
# ---------------------------------------------------------------------------

def _worker_payload(ntype):
    """감시자가 만드는 알림 1건의 실제 push payload.

    :param ntype: ``WORKER_STALLED`` 또는 ``WORKER_RECOVERED``
    :return: ``_build_payload`` 결과 dict
    """
    notif = _mk_notification(
        is_urgent=False,
        ntype=ntype,
        target_type="ROLE",
        target_role="ADMIN",
        title="백그라운드 작업이 멈췄습니다",
        message="RQ_WORKER(11분째) 응답 없음",
    )
    return _build_payload(notif)


def test_worker_health_push_titles_name_the_event(db):
    """제목이 "새 알림" 이면 잠금화면만 보고는 무슨 일인지 알 수 없다(그게 그날 밤이었다)."""
    assert _worker_payload("WORKER_STALLED")["title"] == "백그라운드 작업 멈춤"
    assert _worker_payload("WORKER_RECOVERED")["title"] == "백그라운드 작업 복구"


def test_worker_health_push_body_says_what_to_do_without_details(db):
    """본문은 "앱을 열어라" 까지다 — kind 이름도 경과 분도 넣지 않는다(generic 규약)."""
    stalled = _worker_payload("WORKER_STALLED")["body"]
    assert "앱을 열어" in stalled
    assert _worker_payload("WORKER_RECOVERED")["body"] == "자동 처리가 다시 시작됐습니다."
    # 알림 센터 message 에는 있는 정보다 — push payload 에만 안 담는다.
    assert "RQ_WORKER" not in stalled, "push 본문에 kind 이름이 새어 들어갔다"
    assert "분째" not in stalled, "push 본문에 경과 분이 새어 들어갔다"


def test_worker_health_push_shares_one_fixed_tag(db):
    """두 유형이 같은 고정 tag 를 쓴다 — OS 알림이 쌓이지 않고 **교체**된다.

    id 를 tag 에 섞으면 건마다 새 배너가 되어 20건이 쌓이던 그 사건이 그대로 돌아온다
    (긴급 알림의 ``foms-urgent-<id>`` 와 의도적으로 다른 규칙이다).
    """
    stalled = _worker_payload("WORKER_STALLED")
    recovered = _worker_payload("WORKER_RECOVERED")
    assert stalled["tag"] == "foms-worker-health"
    assert recovered["tag"] == stalled["tag"], "복구가 다른 tag 면 배너가 둘로 남는다"
    assert str(stalled["data"]["notification_id"]) not in stalled["tag"], (
        "tag 에 알림 id 가 섞였다 — 사건마다 배너가 쌓인다")


def test_stalled_renotifies_but_recovery_replaces_quietly(db):
    """멎음은 진동·소리로 알리고, 복구는 조용히 배너만 바꾼다(소음 0, 잠금화면은 진실)."""
    assert _worker_payload("WORKER_STALLED")["renotify"] is True
    assert _worker_payload("WORKER_RECOVERED")["renotify"] is False, (
        "복구가 다시 울리면 한밤중에 두 번 깨운다")
    # 인프라 사건은 긴급이 아니다 — 손으로 지워야 하는 배너로 만들지 않는다.
    assert "requireInteraction" not in _worker_payload("WORKER_STALLED")


def test_recovery_push_carries_an_empty_vibration_pattern(db):
    """복구는 진동도 없어야 한다 — renotify=False 만으로는 조용해지지 않는다.

    ``renotify=False`` 는 같은 tag 의 **기존 알림을 교체할 때만** 무음이다. 사람이 멎음
    배너를 이미 지웠으면 복구는 새 알림이 되고, ``static/sw.js`` 의
    ``vibrate: payload.vibrate || [80, 40, 80]`` 이 기본 패턴을 붙여 새벽에 울린다.
    JS 에서 빈 배열은 truthy 라 ``[]`` 를 실어 보내면 그 기본값이 안 걸린다.
    """
    assert _worker_payload("WORKER_RECOVERED")["vibrate"] == [], (
        "복구 push 에 빈 진동 패턴이 없다 — sw.js 기본값이 붙어 한밤중에 울린다")
    assert _worker_payload("WORKER_STALLED")["vibrate"] == [80, 40, 80], (
        "멎음은 진동으로 알려야 한다")


def test_worker_health_types_match_the_watchdog_constants(db):
    """두 유형 이름이 감시자 상수와 갈리면 push 가 조용히 옛 모습으로 돌아간다.

    이름은 push_sender 안에서 네 군데(P1 집합·_WORKER_HEALTH_TYPES·제목·본문)에 리터럴로
    적혀 있다. 감시자 쪽 상수만 바꾸면 ``_build_payload`` 의 분기가 통째로 빠져 고정 tag 가
    사라지고(2026-09-08 20건 사건 재현) 본문도 "확인이 필요한 새 알림" 으로 되돌아가는데,
    그 사실을 아무 테스트도 못 잡는다 — 그 구멍을 여기서 막는다.
    """
    from foms.services import worker_watchdog
    from foms.services.notifications import push_sender

    assert set(push_sender._WORKER_HEALTH_TYPES) == {
        worker_watchdog.NOTIFICATION_TYPE,
        worker_watchdog.NOTIFICATION_TYPE_RECOVERED,
    }, "push 쪽 유형 이름이 감시자 상수와 갈렸다"
    for ntype in (worker_watchdog.NOTIFICATION_TYPE,
                  worker_watchdog.NOTIFICATION_TYPE_RECOVERED):
        assert ntype in push_sender._DEFAULT_P1_TYPES, (
            f"{ntype} 이 P1 집합에 없다 — push 가 조용히 no-op 된다")
        assert _worker_payload(ntype)["title"] != "새 알림", (
            f"{ntype} 이 제목 분기를 못 탄다")


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
