"""시간 지표 · 직원 알림 교차 검수 R16 반영(플랜 C10-5) — 검수가 보인 것을 고친 뒤 막는 시험 · 살아남은 변이를 잡는 시험.

R16-1 알림은 라홈 운영 시간 · 영업일에만 · R16-2 상담마다 같은 꼬리표 + 다시 울림, 같은 상담의 안 읽은 앞 알림은 읽음 · R16-3 [보내기]
버튼이 켜졌을 때만 · R16-4 '갈아 끼움'은 초안이 보였거나 두뇌를 부른 차례만 · R16-5 '재지 못함' 수 · R16-6 '직원이 먼저 답함'은 끝난
차례만 · R16-7 '발송' · '초안 뜸' 모두 마지막 손님 글부터(총괄 결정, 설계서 17.3 표) · R16-8 '5초 안에 누름'은 그대로 보낸 것만 ·
R16-9 지표가 실패해도 아침 보고 · 경보 · 관리 화면은 산다 · R16-10 살아남은 변이 · R16-11 링크 꼴 한 곳 · 푸시 넣기 실패 이유 기록.

손으로 꾸민 합성 값만. 시각은 2026-11 KST(11-02 월요일), 달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import datetime
import logging

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db import db_session
from foms.services.cs_agent import metrics, report, send, staff_alert
from foms.services.cs_agent.state import ChatState  # noqa: F401
from foms.services.notifications import cs_draft_link, push_sender
from models import Notification, NotificationUserState
from tests.domains.test_cs_drafting import FakePoster, channel, customer, run  # noqa: F401
from tests.domains.test_cs_realtime_metrics import (  # noqa: F401 — pushes 는 fixture
    DAY, admin, alert_switch, compute, person, pushes, secs, turn,
)
from tests.support.cs_agent_fakes import at, keys, weekdays_only  # noqa: F401

T0 = at(2, 9)


def notify(chat="uc-1", turn_id=1, now=T0):
    return staff_alert.notify_draft_ready(db_session, turn_id=turn_id, brand="LAHOM", chat_id=chat, now=now,
                                         is_business_day=weekdays_only)


def drafts(user_id=None):
    query = db_session.query(Notification).filter_by(notification_type=cs_draft_link.NOTIFY_DRAFT_READY)
    return query.filter_by(target_user_id=user_id).order_by(Notification.id).all() if user_id else query.all()


# ── R16-1 · R16-3 알림은 운영 시간 · 버튼이 켜졌을 때만 ─────────────────────
@pytest.mark.parametrize("now,expected", [(at(2, 8), 1), (at(2, 16, 59), 1), (at(2, 7, 59), 0), (at(2, 17), 0),
                                          (at(2, 23), 0), (at(7, 10), 0)])  # 11-07 토요일
def test_alerts_go_out_only_inside_lahom_hours(app, pushes, now, expected):
    alert_switch()
    person("cs-on")
    assert len(notify(now=now)) == expected and len(pushes) == expected


def test_no_alert_when_the_send_buttons_are_off(app, pushes):
    alert_switch(buttons=False)
    person("cs-on")
    assert notify() == [] and pushes == []


# ── R16-2 같은 상담은 하나로 ─────────────────────────────────────────────
def test_a_newer_draft_for_the_same_chat_folds_the_older_alert(app, pushes):
    alert_switch()
    uid = person("cs-on")
    notify(turn_id=1)
    notify(chat="uc-2", turn_id=2)
    notify(turn_id=3)  # 같은 상담에 새 초안 — 앞 알림은 읽음
    by_chat = {cs_draft_link.cs_draft_chat(n.message): n for n in drafts(uid) if not n.is_read}
    assert sorted(by_chat) == ["uc-1", "uc-2"] and "/turns/3/" in by_chat["uc-1"].message
    old = drafts(uid)[0]
    state = db_session.query(NotificationUserState).filter_by(notification_id=old.id, user_id=uid).one()
    assert old.is_read is True and state.read_at is not None
    tags = [push_sender._build_payload(n)["tag"] for n in drafts(uid)]
    assert tags == ["foms-cs-draft-uc-1", "foms-cs-draft-uc-2", "foms-cs-draft-uc-1"]
    assert all(push_sender._build_payload(n)["renotify"] is True for n in drafts(uid))


# ── R16-4 ~ R16-8 지표 정의 ──────────────────────────────────────────────
def test_superseded_counts_only_turns_whose_draft_showed_or_reached_the_brain(app):
    turn(1, state="superseded", asked=T0)  # 두뇌 전에 손님 새 글 — 초안 없음
    turn(2, state="superseded", asked=T0, latency=7000)  # 두뇌를 불렀다
    turn(3, state="posted", asked=T0, placed=secs(T0, 20))
    turn(4, state="stored", asked=T0)  # 초안이 안 보였고 두뇌 기록도 없다
    m = compute()["LAHOM"]
    assert (m.superseded.hits, m.superseded.total) == (1, 2)


def test_unmeasurable_samples_are_counted_not_dropped(app):
    turn(1, state="posted", placed=secs(T0, 20), created=T0)  # 손님 글 줄 없음
    turn(2, state="posted", asked=T0, placed=secs(T0, -5))  # 시각이 거꾸로
    turn(3, state="posted", send_state="sent", sent=secs(T0, 60), created=T0, outcome="as_is")  # 손님 글 줄 없음
    turn(4, state="posted", asked=T0, placed=secs(T0, 10), send_state="sent", sent=secs(T0, 30), outcome="as_is")
    m = compute()["LAHOM"]
    assert (m.draft_shown.count, m.draft_shown.unmeasured) == (1, 2)
    assert (m.send.count, m.send.excluded, m.send.unmeasured) == (1, 0, 1)
    assert "재지 못함 2건" in " ".join(v for _n, v in metrics._items(m))


def test_staff_first_counts_finished_turns_only(app):
    turn(1, state="claimed", asked=T0)
    turn(2, state="posting", asked=T0)
    turn(3, state="failed", asked=T0)
    turn(4, state="staff_replied", asked=T0)
    turn(5, state="skipped", error="human_replied", asked=T0)
    turn(6, state="skipped", error="handoff", asked=T0)  # 다른 건너뜀 — 분모에만
    turn(7, state="posted", asked=T0, placed=secs(T0, 10))
    m = compute()["LAHOM"]
    assert (m.staff_first.hits, m.staff_first.total) == (2, 4)


def test_send_time_starts_at_the_last_customer_message(app):
    turn(1, asked=secs(T0, 100), waiting=T0, placed=secs(T0, 110), send_state="sent", sent=secs(T0, 160),
         outcome="as_is")
    m = compute()["LAHOM"]
    assert m.send.median == 60.0 and m.draft_shown.median == 10.0  # 둘 다 마지막 손님 글(100초)부터
    assert any("마지막 손님 글" in line for line in metrics.DEFINITIONS)


def test_fast_click_counts_as_is_sends_only(app):
    turn(1, asked=T0, send_state="sent", sent=secs(T0, 30), click=1000, outcome="as_is")
    turn(2, asked=T0, send_state="sent", sent=secs(T0, 30), click=1000, outcome="edited")  # 고친 글 — 빼고 센다
    turn(3, asked=T0, send_state="sent", sent=secs(T0, 30), click=metrics.FAST_CLICK_MS, outcome="as_is")  # 5초 꼭
    m = compute()["LAHOM"]
    assert (m.fast_click.hits, m.fast_click.total) == (1, 2)


# ── R16-9 지표가 실패해도 산다 ───────────────────────────────────────────
def test_a_failing_metric_never_costs_the_morning_report_or_the_panel(app, client, monkeypatch, caplog):
    def broken(*_a, **_k):
        raise SQLAlchemyError("합성 질의 고장")

    monkeypatch.setattr(metrics, "_rows", broken)
    caplog.set_level(logging.WARNING)
    published = report.publish(db_session, states=[], missing=[], checks={"LAHOM": "ok"}, watch_missing_inbound=False,
                               now=at(2, 9), is_business_day=weekdays_only)
    assert published.report_sent is True and "시간 지표를 못 셌다" in caplog.text
    admin(client)
    page = client.get("/admin/cs-agent")
    assert page.status_code == 200 and "시간 지표를 지금 셀 수 없어요" in page.get_data(as_text=True)


# ── R16-10 살아남은 변이 ─────────────────────────────────────────────────
def test_mutation_guards_for_window_desk_and_partners(app, pushes):
    turn(1, asked=T0, placed=secs(T0, 10), created=at(3, 0))  # 기간 끝(11-03 0시)은 들어가지 않는다
    turn(2, state="stored", asked=T0, outcome="direct")  # 저장만 차례의 직접 답은 버튼 비율 분모가 아니다
    turn(3, state="posted", asked=T0, outcome="direct")
    m = compute()["LAHOM"]
    assert (m.turns, m.button.hits, m.button.total) == (2, 0, 1)
    alert_switch()
    person("partner-cs", partner=True)  # 협력사 계정은 CS 팀이어도 받지 않는다
    assert staff_alert.recipients(db_session) == []


def test_a_one_line_ask_human_memo_alerts_nobody(channel, pushes):
    alert_switch()
    person("cs-on")
    customer(channel, text="혹시 AI 인가요 사람인가요?")
    run(channel, "memo", poster=FakePoster())
    assert drafts() == [] and pushes == []


@pytest.mark.parametrize("message", ["x[보내기 화면] /cs-agent/turns/1/send?c=uc-1",
                                     "[보내기 화면] /cs-agent/turns/1/send?c=uc 1",
                                     "[보내기 화면] /cs-agent/turns/1/send?c=<b>",
                                     "[보내기 화면] /cs-agent/turns/1/send?c=uc-1&next=//evil.example"])
def test_the_link_must_be_the_exact_same_site_path(message):
    assert cs_draft_link.cs_send_link(message) is None


# ── R16-11 링크 한 곳 · 상수 · 넣기 실패 이유 ─────────────────────────────
def test_links_are_built_in_one_place_and_queue_refusals_are_logged(app, monkeypatch, caplog):
    path = cs_draft_link.send_path(12, "uc-1")
    assert cs_draft_link.cs_send_link(cs_draft_link.alert_message(path, "https://desk.example/x")) == path
    monkeypatch.setenv(send.BASE_URL_ENV, "https://foms.example")
    assert send.memo_buttons(12, "uc-1")[0][1] == "https://foms.example" + path
    source = (push_sender.__file__ and open(push_sender.__file__, encoding="utf-8").read())
    assert '"CS_DRAFT_READY"' not in source  # 유형 이름은 상수 하나
    alert_switch()
    person("cs-on")
    monkeypatch.setattr(push_sender, "enqueue_push_for_notification",
                        lambda nid, db=None: {"enqueued": False, "reason": "queue_unavailable"})
    caplog.set_level(logging.INFO)
    notify()
    assert "queue_unavailable" in caplog.text
