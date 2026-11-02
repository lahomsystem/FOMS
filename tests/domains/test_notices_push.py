"""공지 폰 알림 + 배지(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §7).

만들기 → 받는 사람마다 ``FOMS_NOTICE`` 알림 + 수신자 상태(협력사는 ``target_user_id``), 받지 않는 사람(다른 팀 · 다른 협력사 ·
꺼진 계정 · 꺼진 협력사)은 없음(음성 대조군). 선점으로 한 번만. 예약 공지는 만들 때 안 보내고 스캔이 시작 뒤 보냄, 끝난 예약
공지는 안 보냄. 읽음 · 확인이 배지 숫자를 줄이고, 지우면 보관. 잠금화면 글은 제목 "📢 공지사항" · 본문 = 공지 제목(본문 미포함) ·
누르면 본사 ``/notices`` · 협력사 ``/partner/notices``.
"""
from __future__ import annotations

import datetime
import json

import pytest

import foms.services.notices.push as notice_push
from db import db_session
from foms.api.notifications import _resolve_notification_deep_link
from foms.services.datetime_kst import now_utc_naive
from foms.services.notices.push import dispatch_notice_push, sweep_due_notice_pushes
from foms.services.notices.service import ack_notice, create_notice, delete_notice, mark_read, update_notice
from foms.services.notifications import push_sender
from foms.services.notifications.notice_push import FOMS_NOTICE_TYPE
from models import (
    Notice,
    NoticeAck,
    Notification,
    NotificationPushSubscription,
    NotificationUserState,
    PartnerOrg,
    User,
)
from tests.security.partner_fixtures import _client, _user

SECRET_BODY = "비밀 본문 — 잠금화면에 나오면 안 된다"


@pytest.fixture
def people(app):
    org_a = PartnerOrg(name="라운즈")
    org_b = PartnerOrg(name="다라가구")
    org_off = PartnerOrg(name="꺼진가구", is_active=False)
    db_session.add_all([org_a, org_b, org_off])
    db_session.commit()
    # 요청 뒤 세션이 닫혀도 쓰도록 id 만 들고 다닌다(_id · _u 로 꺼낸다).
    made = {
        "admin": _user(role="ADMIN", team=None, name="관리자"),
        "sales": _user(team="SALES", name="영업김"),
        "measure": _user(team="MEASURE", name="실측이"),
        "drawing": _user(team="DRAWING", name="도면박"),
        "cs": _user(team="CS", name="상담최"),
        "staff_off": _user(team="SALES", name="퇴사자", is_active=False),
        "pa": _user(role="PARTNER", team=None, org=org_a, name="라운즈 직원"),
        "pa_off": _user(role="PARTNER", team=None, org=org_a, name="라운즈 꺼짐", is_active=False),
        "pb": _user(role="PARTNER", team=None, org=org_b, name="다라 직원"),
        "p_orgoff": _user(role="PARTNER", team=None, org=org_off, name="꺼진회사 직원"),
        "org_a": org_a,
        "org_b": org_b,
        "org_off": org_off,
    }
    return {key: int(obj.id) for key, obj in made.items()}


def _u(people, key: str) -> User:
    return db_session.get(User, people[key])


@pytest.fixture
def enqueued(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(notice_push, "enqueue_push_for_notification",
                        lambda nid, db=None: calls.append(int(nid)) or {"enqueued": True, "reason": None})
    return calls


@pytest.fixture
def sent_now(monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(notice_push, "send_push_for_notification",
                        lambda nid, db=None, **_kw: calls.append(int(nid)) or {"sent": 1})
    return calls


def _payload(people, *, staff_all=False, teams=(), partner_all=False, orgs=(), starts_at="", ends_at="",
             title="이번 주 공지", mode="POPUP") -> dict:
    return {
        "title": title,
        "body": SECRET_BODY,
        "audience": {"staff_all": staff_all, "staff_teams": list(teams), "partner_all": partner_all,
                     "partner_org_ids": [people[o] for o in orgs]},
        "display_mode": mode,
        "pinned": False,
        "starts_at": starts_at,
        "ends_at": ends_at,
    }


def _api_create(app, people, **kw) -> int:
    resp = _client(app, _u(people, "admin")).post("/api/admin/notices", json=_payload(people, **kw))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["id"]


def _make(people, **kw) -> Notice:
    notice = create_notice(db_session, _u(people, "admin"), _payload(people, **kw))
    db_session.commit()
    return notice


def _notice_notifs(notice_id: int | None = None) -> list[Notification]:
    query = db_session.query(Notification).filter(Notification.notification_type == FOMS_NOTICE_TYPE)
    if notice_id is not None:
        ids = [nid for (nid,) in db_session.query(NoticeAck.notification_id).filter(NoticeAck.notice_id == notice_id)]
        query = query.filter(Notification.id.in_(ids or [-1]))
    return query.order_by(Notification.id).all()


def _kst_input(delta: datetime.timedelta) -> str:
    """지금(UTC) + delta 를 한국 시간 입력 칸 모양으로."""
    return (now_utc_naive() + delta + datetime.timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M")


def _unread(user) -> int:
    uid = int(user if isinstance(user, int) else user.id)
    return push_sender._unread_counts(db_session, [uid]).get(uid, 0)


def test_create_sends_one_alert_per_recipient_only(app, people, enqueued):
    nid = _api_create(app, people, teams=["SALES"], orgs=["org_a"])
    notifs = _notice_notifs(nid)
    expected = {people[k] for k in ("sales", "measure", "pa")}
    # 음성 대조군: 다른 팀 · 관리자 · 다른 협력사 · 꺼진 계정 · 꺼진 협력사는 받지 않는다.
    assert {n.target_user_id for n in notifs} == expected
    assert all(n.target_type == "USER" and n.is_urgent is False and n.title == "이번 주 공지" for n in notifs)
    assert all(SECRET_BODY not in (n.message or "") for n in notifs)
    states = db_session.query(NotificationUserState).filter(
        NotificationUserState.notification_id.in_([n.id for n in notifs])).all()
    assert {(s.notification_id, s.user_id) for s in states} == {(n.id, n.target_user_id) for n in notifs}
    assert sorted(enqueued) == sorted(n.id for n in notifs)
    assert db_session.get(Notice, nid).push_sent_at is not None
    links = {a.user_id: a.notification_id for a in db_session.query(NoticeAck).filter_by(notice_id=nid)}
    assert links == {n.target_user_id: n.id for n in notifs}
    # 다른 사람에게는 공지 알림이 하나도 없다.
    others = [people[k] for k in ("admin", "drawing", "cs", "staff_off", "pa_off", "pb", "p_orgoff")]
    assert db_session.query(NotificationUserState).filter(NotificationUserState.user_id.in_(others)).count() == 0


def test_dispatch_twice_sends_once(app, people, enqueued):
    notice = _make(people, staff_all=True)
    assert dispatch_notice_push(db_session, notice, enqueue=True) == 5
    assert dispatch_notice_push(db_session, db_session.get(Notice, notice.id), enqueue=True) == 0
    assert sweep_due_notice_pushes(db_session)["notices"] == 0
    assert len(_notice_notifs()) == 5 and len(enqueued) == 5


def test_update_does_not_resend(app, people, enqueued):
    nid = _api_create(app, people, teams=["CS"])
    assert len(enqueued) == 1
    resp = _client(app, _u(people, "admin")).put(f"/api/admin/notices/{nid}", json=_payload(people, teams=["CS"],
                                                                                       title="고친 제목"))
    assert resp.status_code == 200
    assert len(enqueued) == 1 and len(_notice_notifs()) == 1


def test_scheduled_notice_waits_for_sweep(app, people, enqueued, sent_now):
    nid = _api_create(app, people, teams=["DRAWING"], starts_at=_kst_input(datetime.timedelta(hours=2)))
    assert enqueued == [] and _notice_notifs() == []
    assert db_session.get(Notice, nid).push_sent_at is None
    assert sweep_due_notice_pushes(db_session)["notices"] == 0  # 아직 시작 전
    assert sent_now == []

    later = now_utc_naive() + datetime.timedelta(hours=2, minutes=5)
    result = sweep_due_notice_pushes(db_session, later)
    notifs = _notice_notifs(nid)
    assert result == {"notices": 1, "notifications": 1, "expired": 0, "failed": 0}
    assert [n.target_user_id for n in notifs] == [people["drawing"]]
    assert sent_now == [notifs[0].id] and enqueued == []  # SIDEFX 는 큐 없이 바로 보낸다
    assert sweep_due_notice_pushes(db_session, later + datetime.timedelta(minutes=1))["notices"] == 0


def test_scheduled_then_switched_to_now_sends_on_update(app, people, enqueued):
    nid = _api_create(app, people, teams=["CS"], starts_at=_kst_input(datetime.timedelta(hours=3)))
    assert enqueued == []
    resp = _client(app, _u(people, "admin")).put(f"/api/admin/notices/{nid}", json=_payload(people, teams=["CS"]))
    assert resp.status_code == 200
    assert [n.target_user_id for n in _notice_notifs(nid)] == [people["cs"]] and len(enqueued) == 1


def test_ended_scheduled_notice_is_closed_without_sending(app, people, sent_now):
    notice = _make(people, staff_all=True, starts_at=_kst_input(datetime.timedelta(hours=-5)),
                   ends_at=_kst_input(datetime.timedelta(hours=-1)))
    result = sweep_due_notice_pushes(db_session)
    assert result["expired"] == 1 and result["notices"] == 0
    assert sent_now == [] and _notice_notifs() == []
    assert db_session.get(Notice, notice.id).push_sent_at is not None


def test_read_and_ack_lower_the_badge(app, people, enqueued):
    listed = _make(people, staff_all=True, mode="LIST", title="목록 공지")
    popup = _make(people, staff_all=True, mode="POPUP", title="창 공지")
    dispatch_notice_push(db_session, listed, enqueue=True)
    dispatch_notice_push(db_session, db_session.get(Notice, popup.id), enqueue=True)
    sales, cs = _u(people, "sales"), _u(people, "cs")
    assert _unread(sales) == 2 and _unread(cs) == 2

    assert mark_read(db_session, sales, listed.id) is True
    db_session.commit()
    assert _unread(sales) == 1 and _unread(cs) == 2  # 대조군: 다른 사람 숫자는 그대로

    assert ack_notice(db_session, sales, popup.id) is True
    db_session.commit()
    assert _unread(sales) == 0
    ack = db_session.query(NoticeAck).filter_by(notice_id=popup.id, user_id=sales.id).one()
    state = db_session.query(NotificationUserState).filter_by(notification_id=ack.notification_id,
                                                             user_id=sales.id).one()
    assert state.read_at is not None and state.ack_at is not None


def test_delete_archives_alerts(app, people, enqueued):
    notice = _make(people, teams=["SALES"], orgs=["org_b"])
    dispatch_notice_push(db_session, notice, enqueue=True)
    keep = _make(people, teams=["SALES"], title="남는 공지")
    dispatch_notice_push(db_session, keep, enqueue=True)
    assert _unread(people["sales"]) == 2 and _unread(people["pb"]) == 1
    assert delete_notice(db_session, _u(people, "admin"), notice.id) is True
    db_session.commit()
    ids = [n.id for n in _notice_notifs(notice.id)]
    states = db_session.query(NotificationUserState).filter(NotificationUserState.notification_id.in_(ids)).all()
    assert len(states) == 3 and all(s.archived_at is not None for s in states)
    assert _unread(people["sales"]) == 1 and _unread(people["pb"]) == 0  # 남는 공지만 남는다


class _Webpush:
    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, sub_info, data, **_kw):
        self.calls.append({"endpoint": sub_info["endpoint"], "payload": json.loads(data)})


def test_push_payload_title_only_and_deep_links(app, people, monkeypatch, enqueued):
    monkeypatch.setenv("FOMS_WEB_PUSH_ENABLED", "1")
    monkeypatch.setenv("FOMS_PUSH_P1_TYPES", "DRAWING_TRANSFERRED")  # P1 집합을 줄여도 공지는 나간다
    webpush = _Webpush()
    monkeypatch.setattr(push_sender, "_import_pywebpush", lambda: (webpush, RuntimeError))
    for key in ("sales", "pa"):
        db_session.add(NotificationPushSubscription(user_id=people[key], endpoint=f"https://push.test/{key}",
                                                    p256dh="p", auth="a"))
    db_session.commit()
    nid = _api_create(app, people, teams=["SALES"], orgs=["org_a"], title="  11월   휴무   안내  ")
    for notif in _notice_notifs(nid):
        push_sender.send_push_for_notification(notif.id, db=db_session)
    db_session.commit()
    by_endpoint = {c["endpoint"]: c["payload"] for c in webpush.calls}
    assert set(by_endpoint) == {"https://push.test/sales", "https://push.test/pa"}
    staff, partner = by_endpoint["https://push.test/sales"], by_endpoint["https://push.test/pa"]
    for payload in (staff, partner):
        assert payload["title"] == "📢 공지사항"
        assert payload["body"] == "11월 휴무 안내"
        assert SECRET_BODY not in json.dumps(payload, ensure_ascii=False)
        assert payload["tag"] == f"foms-notice-{payload['data']['notification_id']}"
        assert payload["data"]["unread_count"] == 1
        assert "requireInteraction" not in payload
    assert staff["data"]["deep_link"] == "/notices"
    assert partner["data"]["deep_link"] == "/partner/notices"


def test_long_title_is_cut_and_bell_link_follows_recipient(app, people):
    notif = Notification(id=77, notification_type=FOMS_NOTICE_TYPE, target_type="USER", title="가" * 200,
                         is_urgent=False)
    payload = push_sender._build_payload(notif)
    assert len(payload["body"]) == 120 and payload["body"].endswith("…")
    assert payload["data"]["deep_link"] == "/notices"
    assert _resolve_notification_deep_link(notif, {}, recipient=_u(people, "pa"))["deep_link_url"] == "/partner/notices"
    assert _resolve_notification_deep_link(notif, {}, recipient=_u(people, "sales"))["deep_link_url"] == "/notices"


def test_no_recipient_still_closes_and_service_update_keeps_link(app, people, enqueued):
    notice = _make(people, teams=["ACCOUNTING"])  # 회계팀 계정 없음
    assert dispatch_notice_push(db_session, notice, enqueue=True) == 0
    assert db_session.get(Notice, notice.id).push_sent_at is not None and enqueued == []
    updated = update_notice(db_session, _u(people, "admin"), notice.id, _payload(people, teams=["ACCOUNTING"],
                                                                             title="회계 공지"))
    db_session.commit()
    assert updated is not None and _notice_notifs() == []
