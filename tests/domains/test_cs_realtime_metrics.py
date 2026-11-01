"""시간 지표 + 직원 알림(플랜 C10-5 · 설계서 17.3 '잰다' · 원장 R10-7 · R4-18) — 합성 차례 줄로 완료 기준을 본다.

① 각 지표 값(초안 뜸 · 발송 중간 · 90%, 갈아 끼움 · 직원이 먼저 답함 · 버튼으로 보냄 · 그대로 보냄 · 5초 안에 누름) ② 운영 시간 안 ·
밖 가르기(영업일 달력 · 브랜드 시간) ③ 빈 기간 ④ 직원별 수치 · 직원 번호가 어디에도 안 나옴(기록판 · 아침 보고 · 지표 결과) ⑤ 기록판 ·
아침 보고에 숫자 ⑥ 알림은 구독한 상담 직원에게만 · 손님 글 · 초안 없음 · 스위치 끔이면 없음 ⑦ 푸시 문구 · 바로가기.

손으로 꾸민 합성 값만(전화 꼴 숫자 없음). 시각은 2026-11 KST(11-02 월요일), 달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.cs_agent import metrics, report, staff_alert
from foms.services.cs_agent import settings as st
from foms.services.notifications import push_sender
from models import (
    CsAgentMessage, CsAgentTurn, Notification, NotificationPushSubscription, PartnerOrg, SystemSetting, User,
)
from tests.domains.test_cs_drafting import CUSTOMER, DRAFT, NOTE, FakePoster, channel, customer, run  # noqa: F401
from tests.support.cs_agent_fakes import at, keys, naive, weekdays_only  # noqa: F401 — keys 는 fixture

ROOT = Path(__file__).resolve().parents[2]
STAFF_NO = 4242  # 보낸 직원 번호 표지 — 지표 · 화면 · 보고 어디에도 나오면 안 된다
DAY = datetime.date(2026, 11, 2)  # 월요일


def turn(n, *, brand="LAHOM", state="posted", asked=None, placed=None, send_state=None, waiting=None, sent=None,
         click=None, outcome=None, error=None, created=None, latency=None):
    """합성 차례 줄 하나(+ 그 차례 손님 글 시각을 상태 표에)."""
    chat, message = f"uc-m{n}", f"m-{n}"
    db_session.add(CsAgentTurn(brand=brand, chat_id=chat, last_user_message_id=message, state=state, attempts=1,
                               placed_at=naive(placed) if placed else None, send_state=send_state,
                               waiting_since=naive(waiting) if waiting else None, sent_at=naive(sent) if sent else None,
                               click_ms=click, outcome=outcome, error_code=error, sent_by_user_id=STAFF_NO,
                               latency_ms=latency,
                               created_at=naive(created or asked or at(2, 9))))
    if asked is not None:
        db_session.add(CsAgentMessage(chat_id=chat, message_id=message, brand=brand, person_type="user",
                                      created_at=naive(asked), source="webhook"))
    db_session.commit()


def secs(base, seconds):
    return base + datetime.timedelta(seconds=seconds)


def compute(start=DAY, end=DAY + datetime.timedelta(days=1)):
    return metrics.compute_metrics(db_session, start=start, end=end, is_business_day=weekdays_only)


# ── ① 지표 값 ────────────────────────────────────────────────────────────
def test_each_metric_comes_out_of_synthetic_turns(app):
    t0 = at(2, 9)
    for n, shown in enumerate((20, 30, 40, 100)):  # 초안 뜸 표본 넷 — 중간 30초 · 90% 100초
        turn(n, asked=t0, placed=secs(t0, shown))
    turn(10, asked=t0, placed=secs(t0, 15), send_state="sent", waiting=t0, sent=secs(t0, 60), click=3000,
         outcome="as_is")  # 발송 60초 · 5초 안 누름 · 그대로
    turn(11, asked=t0, placed=secs(t0, 15), send_state="sent", waiting=t0, sent=secs(t0, 90), click=9000,
         outcome="edited")
    turn(12, state="superseded", asked=t0, placed=secs(t0, 25))
    turn(13, state="stored", asked=t0)  # 저장만(놓은 때 없음 — 초안 뜸 표본 아님)
    turn(14, state="staff_replied", asked=t0)
    turn(15, state="skipped", error="human_replied", asked=t0)
    turn(16, state="posted", asked=t0, outcome="direct")  # 데스크에서 직접 답(버튼 아님)
    m = compute()["LAHOM"]
    assert m.turns == 11
    assert (m.draft_shown.count, m.draft_shown.median, m.draft_shown.p90) == (7, 25.0, 100.0)
    assert (m.send.count, m.send.median, m.send.p90, m.send.excluded) == (2, 60.0, 90.0, 0)
    assert (m.superseded.hits, m.superseded.total) == (1, 7)  # 초안이 보인 차례만 — 올림 6 · 지난 초안 1(R16-4)
    assert (m.staff_first.hits, m.staff_first.total) == (2, 11)
    assert (m.button.hits, m.button.total, m.as_is.hits, m.as_is.total) == (2, 3, 1, 2)
    assert (m.fast_click.hits, m.fast_click.total) == (1, 1)  # 그대로 보낸 차례만(R16-8)
    assert metrics.percentile([5, 1, 3], 0.5) == 3 and metrics.percentile([], 0.9) is None


# ── ② 운영 시간 안 · 밖 ──────────────────────────────────────────────────
@pytest.mark.parametrize("brand,waiting,inside", [
    ("LAHOM", at(2, 8, 0), True), ("LAHOM", at(2, 16, 59), True), ("LAHOM", at(2, 7, 59), False),
    ("LAHOM", at(2, 17, 0), False), ("HAUD", at(2, 17, 30), True), ("LAHOM", at(7, 10), False),  # 11-07 토요일
])
def test_send_time_counts_only_inside_business_hours(app, brand, waiting, inside):
    turn(1, brand=brand, asked=waiting, send_state="sent", waiting=waiting, sent=secs(waiting, 120), created=waiting)
    m = compute(start=DAY, end=DAY + datetime.timedelta(days=7))[brand]
    assert (m.send.count, m.send.excluded) == ((1, 0) if inside else (0, 1))
    assert m.send.median == (120.0 if inside else None)


# ── ③ 빈 기간 · 브랜드 나눔 ──────────────────────────────────────────────
def test_an_empty_period_has_no_numbers_and_brands_stay_apart(app):
    turn(1, brand="HAUD", asked=at(2, 9), placed=at(2, 9, 1))
    empty = compute(start=DAY - datetime.timedelta(days=3), end=DAY)
    assert all(m.turns == 0 and m.draft_shown.median is None and m.button.value is None for m in empty.values())
    found = compute()
    assert (found["LAHOM"].turns, found["HAUD"].turns, found["HAUD"].draft_shown.median) == (0, 1, 60.0)
    assert metrics.metrics_lines(db_session, now=at(2, 9), labels=report.BRAND_LABELS) == []  # 오늘 앞 7일 — 비었다
    assert metrics.format_seconds(None) == "—" and metrics.format_seconds(92) == "1분 32초"


# ── ④ ⑤ 직원별 수치 없음 · 기록판 · 아침 보고 ─────────────────────────────
def admin(client):
    user = User(username="metrics-admin", password=generate_password_hash("pw"), role="ADMIN", team="CS",
                name="합성 관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id


def test_the_board_and_morning_report_show_numbers_but_no_staff(app, client):
    yesterday = at(2, 9) - datetime.timedelta(days=1)  # 일요일 — 초안 뜸은 모든 시간
    turn(1, asked=yesterday, placed=secs(yesterday, 28), send_state="sent", waiting=yesterday,
         sent=secs(yesterday, 300), click=2000, outcome="as_is")
    lines = metrics.metrics_lines(db_session, now=at(2, 9), labels=report.BRAND_LABELS, is_business_day=weekdays_only)
    assert lines == ["[라홈 지난 7일 시간 지표] 초안 뜸(모든 시간) 중간 28초 · 90% 28초 · 1건(재지 못함 0건) · 발송(운영 "
                     "시간 안) 중간 — · 90% — · 0건(재지 못함 0건 · 밖 1건) · 갈아 끼움 0%(0/1) · 직원이 먼저 답함 0%(0/1) · "
                     "버튼으로 보냄 100%(1/1) · 그대로 보냄 100%(1/1) · 5초 안에 누름 100%(1/1)"]
    facts = report.ReportFacts(day=DAY, states=[], pending_webhooks=0, missing_inbound_24h=None, checks={"LAHOM": "ok"},
                               last_success_at=None, metrics_lines=lines)
    _title, body = report.morning_report(facts)
    assert lines[0] in body
    real = datetime.datetime.now(datetime.timezone.utc).astimezone(at(2, 9).tzinfo) - datetime.timedelta(days=1)
    turn(2, asked=real, placed=secs(real, 28))  # 기록판은 실제 지금 기준 지난 7일
    admin(client)
    html = client.get("/admin/cs-agent").get_data(as_text=True)
    for needle in ("시간 지표", "초안 뜸(모든 시간)", "중간 28초", "버튼으로 보냄", "상담 직원 알림 구독"):
        assert needle in html, needle
    found = metrics.compute_metrics(db_session, start=DAY - datetime.timedelta(days=7), end=DAY)
    for text in (html, body, repr(found), repr(metrics.metrics_view(db_session, now=at(2, 9),
                                                                     labels=report.BRAND_LABELS))):
        assert str(STAFF_NO) not in text
    source = (ROOT / "foms/services/cs_agent/metrics.py").read_text(encoding="utf-8")
    assert "sent_by_user_id" not in source and "desk_manager_id" not in source  # 직원 칸은 고르지도 않는다


# ── ⑥ 직원 알림: 구독한 상담 직원만 · 글 없음 · 스위치 ───────────────────────
def person(name, *, role="STAFF", team="CS", subscribed=True, revoked=False, active=True, partner=False):
    user = User(username=f"alert-{name}", password=generate_password_hash("pw"), role=role, team=team,
                name=f"합성 {name}", is_active=active)
    if partner:
        org = PartnerOrg(name=f"합성 협력사 {name}")
        db_session.add(org)
        db_session.flush()
        user.partner_org_id, user.role = org.id, "PARTNER"  # 협력사 계정은 role 도 PARTNER(ck_users_partner_role_org)
    db_session.add(user)
    db_session.flush()
    if subscribed:
        db_session.add(NotificationPushSubscription(user_id=user.id, endpoint=f"https://push.example/{name}",
                                                    revoked_at=naive(at(1, 9)) if revoked else None))
    db_session.commit()
    return user.id


@pytest.fixture
def pushes(monkeypatch):
    sent = []
    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", lambda nid, db=None: sent.append(nid) or {})
    return sent


def alert_switch(on=True, draft="memo", buttons=True):
    db_session.merge(SystemSetting(setting_key="cs_agent_switch", setting_value={"loop": "on", "draft": draft}))
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "staff_push_enabled": on, "send_buttons_enabled": buttons}))
    db_session.commit()


def test_a_new_draft_memo_alerts_only_subscribed_cs_staff_without_any_text(channel, pushes):
    alert_switch()
    wanted = [person("cs-on"), person("acct-on", team="ACCOUNTING"), person("mgr-on", role="MANAGER")]
    for name, kwargs in (("cs-off", {"subscribed": False}), ("cs-revoked", {"revoked": True}),
                         ("sales-on", {"team": "SALES"}), ("viewer-on", {"role": "VIEWER"}),
                         ("gone-on", {"active": False})):
        person(name, **kwargs)
    customer(channel)
    run(channel, "memo", poster=FakePoster())
    notes = db_session.query(Notification).filter_by(notification_type=staff_alert.NOTIFY_DRAFT_READY).all()
    assert sorted(n.target_user_id for n in notes) == sorted(wanted) and sorted(pushes) == sorted(n.id for n in notes)
    turn_id = db_session.query(CsAgentTurn.id).scalar()
    for note in notes:
        text = f"{note.title}\n{note.message}"
        assert CUSTOMER not in text and DRAFT not in text and NOTE not in text  # 손님 글 · 초안 · 직원 참고 없음
        assert f"/cs-agent/turns/{turn_id}/send?c=uc-1" in note.message and "desk.channel.io" in note.message
    assert staff_alert.subscription_counts(db_session) == {"staff": 5, "subscribed": 3}  # 끊은 구독은 안 센다


@pytest.mark.parametrize("on,draft", [(False, "memo"), (True, "store")])
def test_no_alert_when_switched_off_or_only_stored(channel, pushes, on, draft):
    alert_switch(on=on, draft=draft)
    person("cs-on")
    customer(channel)
    run(channel, draft, poster=FakePoster())
    assert db_session.query(Notification).filter_by(notification_type=staff_alert.NOTIFY_DRAFT_READY).count() == 0
    assert pushes == []


def test_a_failing_push_queue_never_stops_the_draft(channel, monkeypatch):
    alert_switch()
    person("cs-on")

    def broken(_nid, db=None):
        raise RuntimeError("합성 큐 끊김")

    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", broken)
    customer(channel)
    summary = run(channel, "memo", poster=FakePoster())
    db_session.expire_all()
    assert summary.posted == 1 and db_session.query(CsAgentTurn.state).scalar() == "posted"  # 초안 메모는 그대로


# ── ⑦ 푸시 문구 · 바로가기 ───────────────────────────────────────────────
def test_the_push_banner_is_generic_and_links_to_the_send_screen():
    note = Notification(id=7, notification_type=staff_alert.NOTIFY_DRAFT_READY, is_urgent=False, title="t",
                        message="[보내기 화면] /cs-agent/turns/12/send?c=uc-1\n[상담] https://desk.channel.io/x")
    assert staff_alert.NOTIFY_DRAFT_READY in push_sender._DEFAULT_P1_TYPES
    assert push_sender._should_push(note) and push_sender._urgency(note) == "high"
    payload = push_sender._build_payload(note)
    assert payload["data"]["deep_link"] == "/cs-agent/turns/12/send?c=uc-1"
    assert "desk" not in payload["body"] and "uc-1" not in payload["title"] + payload["body"]
    evil = Notification(id=8, notification_type=staff_alert.NOTIFY_DRAFT_READY, is_urgent=False, title="t",
                        message="[보내기 화면] //evil.example/cs-agent/turns/1/send?c=x")
    assert push_sender._build_payload(evil)["data"]["deep_link"] == "/erp"  # 같은 출처 경로 꼴이 아니면 첫 화면
    from foms.api.notifications import _resolve_notification_deep_link
    assert _resolve_notification_deep_link(note, {})["deep_link_url"] == "/cs-agent/turns/12/send?c=uc-1"
