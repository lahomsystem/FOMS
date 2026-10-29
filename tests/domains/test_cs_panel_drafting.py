"""초안 바퀴 × 관리 패널(설계서 16.1 · 단계 1 검수) — 상한을 올리면 그날 다음 바퀴부터 다시 돎 · 콘솔 상한만 그날 멈춤 ·
바퀴 도중 비상 정지 · 초안 끔이면 두뇌 전에 멈춤(시도로 세지 않음) · 두뇌를 부르는 동안 비상 정지면 메모 없이 저장만(설계서
16.4) · 캐시 읽기 0 은 캐시 표시를 실은 요청만 셈 · 잠긴 칸(한 바퀴 상한 · 묵은 기준)은 줄에 무엇이 있어도 상수 그대로 ·
틀린 설정 경고는 바퀴당 한 번.

두뇌 · 채널톡은 가짜(네트워크 · 키 없음), 재료는 ``test_cs_drafting`` 과 같은 합성 글 · 2026-11 KST 시각 · 주말만 쉬는 달력.
"""

from __future__ import annotations

import functools
import logging

import pytest

from db import db_session
from foms.services.cs_agent import brain, drafting, turns
from foms.services.cs_agent import settings as st
from models import CsAgentTurn, SystemSetting, User
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    DRAFT, NOTE, FakeBrain, FakePoster, channel, customer, run, turn,
)
from tests.support.cs_agent_fakes import FakeAnthropic, at, keys  # noqa: F401 — keys 는 fixture


@pytest.fixture
def actor(app):
    user = User(username="cs-panel-drafting", password="x", role="ADMIN", name="합성 관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def configure(actor_id, **values):
    version = st.read_settings(db_session).version
    st.save_settings(db_session, values, expected_version=version, actor_user_id=actor_id)
    db_session.commit()


def put_spend(usd, day="2026-11-02"):
    db_session.merge(SystemSetting(setting_key=brain.SPEND_KEY, setting_value={"date": day, "usd": usd, "calls": 1}))
    db_session.commit()


def switch(**value):
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value=value))
    db_session.commit()


ANSWER = {"intent": "hours", "draft": DRAFT, "evidence_ids": ["shelf-depth"], "handoff": False,
          "handoff_reason": "none", "staff_note": NOTE}


# ── 돈 멈춤은 지금 상한과 오늘 돈으로 ───────────────────────────────────
def test_raising_the_panel_cap_resumes_the_same_day(channel, actor):
    customer(channel, "uc-1")
    configure(actor, daily_cap_usd_panel="1")
    put_spend("1")  # 오늘 돈 = 화면 상한
    stopped = run(channel, brain_fn=FakeBrain(max_calls=0))
    assert (stopped.halted, stopped.claimed, turn("uc-1")) == ({"spend_cap": 1}, 0, None)
    configure(actor, daily_cap_usd_panel="3")  # 그날 상한을 올린다
    resumed = run(channel, now=at(2, 9, 15))
    assert (resumed.halted, resumed.stored, turn("uc-1").state) == ({}, 1, "stored")


def test_raising_the_worker_env_cap_resumes_the_same_day(channel, monkeypatch):
    customer(channel, "uc-1")
    put_spend("5")  # env 5 를 다 썼다
    assert run(channel, brain_fn=FakeBrain(max_calls=0)).halted == {"spend_cap": 1}
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "10")
    assert run(channel, now=at(2, 9, 15)).stored == 1


def test_a_cap_failure_from_earlier_today_no_longer_stops_the_day_but_a_console_limit_does(channel):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    first = run(channel, brain_fn=FakeBrain(brain.SpendCapReached("daily_cap_reached")))
    assert (first.halted, turn("uc-1").error_code) == ({"spend_cap": 1}, "daily_cap_reached")
    same_day = run(channel, now=at(2, 9, 15))  # 돈 줄은 상한 아래 — 예전엔 그날 멈췄다
    assert (same_day.halted, same_day.stored, turn("uc-1").state, turn("uc-2").state) == ({}, 2, "stored", "stored")
    customer(channel, "uc-3", when=at(2, 9, 20))
    run(channel, brain_fn=FakeBrain(brain.SpendCapReached("api_spend_limit")), now=at(2, 9, 25))
    console = run(channel, brain_fn=FakeBrain(max_calls=0), now=at(2, 9, 40))  # 콘솔 상한은 화면으로 못 푼다
    assert (console.halted, console.claimed) == ({"spend_cap": 1}, 0)


def test_one_draft_must_fit_in_what_is_left(channel):
    customer(channel, "uc-1")
    put_spend("4.9")  # 5 - 4.9 = 0.1 < Opus 16천 토큰 한 번 최소 예약 — 선점하지 않는다
    summary = run(channel, brain_fn=FakeBrain(max_calls=0))
    assert (summary.halted, summary.claimed, turn("uc-1")) == ({"spend_cap": 1}, 0, None)


# ── 바퀴 도중 끄기 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("value", [{"draft": "store", "loop": "off"}, {"draft": "off"}], ids=["emergency-stop", "draft-off"])
def test_switching_off_after_a_brain_call_stops_before_the_next_claim(channel, value):
    for chat in ("uc-1", "uc-2", "uc-3"):
        customer(channel, chat)
    brain_fn = FakeBrain(on_call=lambda _request: switch(**value))
    summary = run(channel, brain_fn=brain_fn)
    assert (summary.brain_calls, summary.halted, summary.stored) == (1, {"switched_off": 1}, 1)
    assert [r.chat_id for r in brain_fn.requests] == ["uc-1"] and turn("uc-2") is None and turn("uc-3") is None


def test_switching_off_between_claim_and_brain_releases_the_turn(channel, monkeypatch):
    customer(channel, "uc-1")
    real_read = drafting.read_lines

    def read_then_stop(reader, brand, chat_id):
        lines = real_read(reader, brand, chat_id)
        switch(draft="store", loop="off")  # 선점 뒤 · 두뇌 전에 비상 정지
        return lines

    monkeypatch.setattr(drafting, "read_lines", read_then_stop)
    summary = run(channel, brain_fn=FakeBrain(max_calls=0))
    row = turn("uc-1")
    assert (summary.halted, summary.released, summary.brain_calls) == ({"switched_off": 1}, 1, 0)
    assert (row.state, row.attempts, row.error_code) == ("failed", 0, "switched_off")  # 시도로 세지 않았다
    monkeypatch.setattr(drafting, "read_lines", real_read)
    switch(draft="store", loop="on")
    assert run(channel, now=at(2, 9, 15)).stored == 1  # 다시 켜면 그 차례를 다시 집는다


@pytest.mark.parametrize("loop_value", ["off", "on"], ids=["emergency-stop", "still-on"])
def test_an_emergency_stop_during_the_brain_call_stores_the_draft_without_a_memo(channel, loop_value):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    poster = FakePoster()
    brain_fn = FakeBrain(on_call=lambda _request: switch(draft="memo", loop=loop_value))  # 두뇌를 부르는 동안
    summary = run(channel, "memo", brain_fn=brain_fn, poster=poster)
    if loop_value == "off":  # 끈 동안 만들던 초안은 저장만 · 다음 차례는 선점하지 않는다(설계서 16.4)
        assert (turn("uc-1").state, poster.calls, turn("uc-2")) == ("stored", [], None)
        assert (summary.stored, summary.posted, summary.not_allowed, summary.halted) == (1, 0, 0, {"switched_off": 1})
    else:  # 음성 대조: 켜져 있으면 메모로 올린다
        assert ([c.chat_id for c in poster.calls], summary.posted, summary.stored) == (["uc-1", "uc-2"], 2, 0)


def test_a_pass_with_the_switch_on_is_unchanged(channel):
    for chat in ("uc-1", "uc-2", "uc-3"):
        customer(channel, chat)
    summary = run(channel, brain_fn=FakeBrain())
    assert (summary.brain_calls, summary.halted, summary.stored) == (3, {}, 3)  # 음성 대조


# ── 캐시 읽기 0 은 표시를 실은 요청만(검수 R9) ───────────────────────────
@pytest.mark.parametrize("policy,now,cold", [
    ("daytime", at(2, 9), 1),  # 운영 시간 · 표시 실음 · 캐시 읽기 0 — 센다
    ("off", at(2, 9), 0),  # 낮이어도 표시가 없으면 세지 않는다(예전엔 셌다)
    ("always", at(2, 21), 1),  # 밤이어도 표시를 실었으면 센다
    ("daytime", at(2, 21), 0),  # 밤 · 운영 시간만 방침 — 표시 없음
], ids=["day-marked", "day-off", "night-always", "night-daytime-only"])
def test_cache_misses_count_only_requests_that_carried_the_marker(channel, actor, policy, now, cold):
    if policy != "daytime":
        configure(actor, cache_policy=policy)
    customer(channel, "uc-1")
    client = FakeAnthropic(ANSWER)  # 진짜 두뇌 길 — 가짜 응답의 캐시 읽기는 늘 0
    summary = run(channel, brain_fn=functools.partial(brain.draft_reply, client=client), now=now)
    assert summary.stored == 1 and ("cache_control" in client.params[0]["system"][-1]) is bool(cold)
    assert summary.cache_cold == cold


# ── 잠긴 칸 · 경고 한 번 ─────────────────────────────────────────────────
def test_locked_knobs_stay_constants_even_if_the_row_says_otherwise(channel):
    db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={
        **st.DEFAULTS, "max_brain_calls_per_pass": 1, "max_wait_business_days": 2}))
    db_session.commit()
    customer(channel, "uc-1")  # 월요일 08:50 — 화요일 10:00 이면 운영 시간 610분(하루 540분 넘음 · 이틀 안)
    for chat in ("uc-2", "uc-3"):
        customer(channel, chat, when=at(3, 9, 30))
    summary = run(channel, brain_fn=FakeBrain(), now=at(3, 10))
    assert (summary.too_old, summary.brain_calls, summary.halted) == (1, 2, {})  # 묵은 기준 1일 · 상한 10 그대로


def test_a_broken_settings_row_warns_once_per_pass(channel, caplog):
    db_session.add(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={"draft_model": "claude-fable-5-1"}))
    db_session.commit()
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    caplog.set_level(logging.WARNING, logger="foms.services.cs_agent")
    client = FakeAnthropic(ANSWER)
    summary = run(channel, brain_fn=functools.partial(brain.draft_reply, client=client))
    assert summary.stored == 2 and len(client.params) == 2 and client.params[0]["model"] == brain.MODEL
    assert caplog.text.count("[CS 설정]") == 1  # 준비 확인 · 두뇌 두 번은 남기지 않는다 — 바퀴가 한 번
    assert db_session.query(CsAgentTurn).count() == 2
