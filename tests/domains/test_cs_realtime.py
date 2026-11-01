"""빠른 길(플랜 C10-1 · 설계서 17.3) — 합성 수신 줄로 완료 기준 ①~⑩ 을 시험한다.

① 조용 기다림 → 한 번 집음 ② 집은 뒤 손님 새 글 → 지난 초안 + 새 초안 ③ 직원 공개 글 → 닫힘 ④ 우리 봇 글 · 부재 안내 ·
확인코드 글은 시작 신호 아님 ⑤ 같은 손님 글 두 번 안 집음 ⑥ TERM 뒤 새 두뇌 호출 안 함 · 죽은 선점은 만료 뒤 풀림 ⑦ 15분 바퀴가
대표 잠금을 쥐고 도는 중에 온 손님 글도 '조용 기다림 + 시간 상한 + 10초' 안에 초안(가짜 시계 · 두 잠금) ⑧ 거른 줄의 원본을
두 번 열지 않음 ⑨ 'AI 냐' 물음 → 두뇌 안 부름 · 초안 없음(음성 대조군 포함) ⑩ 바로 끄기와 초안 스위치를 같이 써도 서로 덮지
않음. 배선 · 설정 · 마이그레이션 · 15분 바퀴와의 관계는 ``test_cs_realtime_wiring.py``.

두뇌 · 메모 감싸개 · 채널톡은 가짜(네트워크 · 키 없음), 손으로 꾸민 합성 글만 쓴다. 시각은 2026-11 KST(11-02 월요일),
달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import datetime
import itertools

import pytest
import sqlalchemy as sa
from sqlalchemy import func, select

from db import db_session
from foms.services.cs_agent import loop, memo, realtime, turns
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.ask_human import ASK_HUMAN_MEMO, asks_if_human
from models import CsAgentTurn, SystemSetting
from tests.domains.test_cs_drafting import CUSTOMER, DRAFT, PRIVATE, FakeBrain, FakePoster, channel  # noqa: F401
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    CODE_TEXT, FakeClock, api_message, at, entity, inbound, keys, make_reader, weekdays_only,
)

T0 = at(2, 9)  # 월요일 운영 시간


def sec(seconds: float) -> datetime.datetime:
    return T0 + datetime.timedelta(seconds=seconds)


def switch_on(mode="store", **settings):
    """초안 스위치 · 비상 정지 켬 · 관리 화면 빠른 길 스위치 켬(나머지 칸은 처음 값)."""
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "on", "draft": mode}))
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY,
                                   setting_value={**st.DEFAULTS, "realtime_enabled": True, **settings}))
    db_session.commit()


class Talk:
    """합성 상담 — 웹훅 수신 줄(빠른 길이 뒤돌아 읽음)과 가짜 채널톡(초안 재료 · 직전 다시 읽기)에 같은 글을 쓴다."""

    def __init__(self, channel, chat="uc-1"):
        self.channel, self.chat = channel, chat
        channel.media.setdefault(chat, "native")
        channel.messages.setdefault(chat, [])
        if not hasattr(channel, "log_ids"):
            channel.log_ids = itertools.count(1)  # 시험마다 1부터 — 수신 줄 id(커밋 순서 = id 순서)

    def say(self, msg_id, when, person="user", text=None, **extra):
        text = f"{CUSTOMER} 선반 깊이 문의드려요" if text is None else text
        inbound(next(self.channel.log_ids), entity(msg_id, when, person, text, chat=self.chat, **extra))
        self.channel.messages[self.chat].append(api_message(msg_id, when, person, text, **extra))


def tick(channel, now, memory, *, brain_fn=None, poster=None, stop=None, clock=None, **kwargs):
    return realtime.run_tick(db_session, memory=memory, stop=stop or loop.StopFlag(), now=now,
                             reader=make_reader(channel, FakeClock()), clock=clock or (lambda: 0.0),
                             is_business_day=weekdays_only, brain=brain_fn or FakeBrain(),
                             poster=poster or FakePoster(), **kwargs)


def rows(chat="uc-1"):
    db_session.expire_all()
    return list(db_session.scalars(select(CsAgentTurn).where(CsAgentTurn.chat_id == chat).order_by(CsAgentTurn.id)))


def turn_count():
    return db_session.scalar(select(func.count()).select_from(CsAgentTurn.__table__))


# ── ① 조용 기다림 → 한 번 집음 ───────────────────────────────────────────
def test_quiet_wait_gathers_several_messages_into_one_pick(channel):
    switch_on()
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain()
    talk.say("m-1", sec(0))
    talk.say("m-2", sec(8), text="합성 깊이도 알려 주세요")
    for at_second in (10, 22):  # 마지막 글 뒤 2초 · 14초 — 아직 조용 기다림(15초) 전
        result = tick(channel, sec(at_second), memory, brain_fn=brain_fn)
        assert (result.outcome, result.pending, result.picked, turn_count()) == ("ok", 1, 0, 0)
    result = tick(channel, sec(23), memory, brain_fn=brain_fn)  # 15초 찼다
    (row,) = rows()
    assert (result.picked, row.state, row.last_user_message_id, row.masked_draft) == (1, "stored", "m-2", DRAFT)
    (request,) = brain_fn.requests
    assert request.realtime is True and [role for role, _ in request.messages] == ["user", "user"]  # 두 글을 한 번에
    assert row.claim_owner.startswith("realtime:")
    assert row.claim_expires_at == realtime.CLAIM_TTL + sec(23).astimezone(datetime.timezone.utc).replace(tzinfo=None)


def test_max_wait_picks_a_chatty_customer_once_then_waits_for_quiet(channel):
    switch_on(max_wait_s=40)
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain()
    for second in range(0, 50, 9):  # 9초마다 계속 쓴다 — 조용 기다림이 안 찬다
        talk.say(f"m-{second}", sec(second), text=f"{CUSTOMER} 합성 {second}")
        tick(channel, sec(second + 1), memory, brain_fn=brain_fn)
    assert [row.last_user_message_id for row in rows()] == ["m-45"]  # 첫 미답 글(0초)부터 40초 지난 첫 차례(46초)에 한 번
    talk.say("m-50", sec(50), text=f"{CUSTOMER} 하나 더요")
    tick(channel, sec(51), memory, brain_fn=brain_fn)  # 이 묶음엔 초안이 있었다 — 최대 기다림으로 또 집지 않는다
    assert [row.state for row in rows()] == ["superseded"] and len(brain_fn.requests) == 1
    tick(channel, sec(65), memory, brain_fn=brain_fn)  # 조용 기다림이 차면 새 초안
    assert [row.state for row in rows()] == ["superseded", "stored"] and len(brain_fn.requests) == 2


# ── ② 집은 뒤 손님 새 글 → 지난 초안 + 새 초안 ───────────────────────────
def test_a_new_message_after_posting_supersedes_and_drafts_again(channel):
    switch_on("memo")
    talk, memory, removed = Talk(channel), realtime.TickMemory(), []
    talk.say("m-1", sec(0))
    tick(channel, sec(16), memory)
    assert [(row.state, row.memo_message_id) for row in rows()] == [("posted", "memo-1")]
    talk.say("m-2", sec(30), text=f"{CUSTOMER} 하나 더 여쭤요")
    result = tick(channel, sec(31), memory, memo_remover=lambda chat, memo_id: removed.append((chat, memo_id)))
    assert (result.superseded, [row.state for row in rows()], removed) == (1, ["superseded"], [("uc-1", "memo-1")])
    tick(channel, sec(46), memory, poster=FakePoster(memo.MemoResult(True, verified=True, message_id="memo-2")))
    assert [(row.state, row.last_user_message_id) for row in rows()] == [("superseded", "m-1"), ("posted", "m-2")]


def test_without_a_remover_the_old_memo_stays_and_a_message_during_the_call_supersedes(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    brain_fn = FakeBrain(on_call=lambda _request: talk.say("m-2", sec(17), text=f"{CUSTOMER} 아 그리고요"))
    result = tick(channel, sec(16), memory, brain_fn=brain_fn)  # 두뇌를 부르는 동안 손님이 또 씀
    (row,) = rows()
    assert (row.state, row.masked_draft, result.drafting.superseded) == ("superseded", DRAFT, 1)  # 만든 초안은 남긴다
    tick(channel, sec(33), memory)  # 기본(지우는 함수 없음)은 메모를 건드리지 않는다 — 새 글 조용 기다림 뒤 새 차례
    assert [(row.state, row.last_user_message_id) for row in rows()] == [("superseded", "m-1"), ("stored", "m-2")]


# ── ③ 직원 공개 글 → 닫힘 ────────────────────────────────────────────────
def test_a_public_staff_reply_closes_the_turn_and_nothing_is_placed(channel):
    switch_on("memo")
    talk, memory, poster = Talk(channel), realtime.TickMemory(), FakePoster()
    talk.say("m-1", sec(0))
    brain_fn = FakeBrain(on_call=lambda _request: talk.say("s-1", sec(17), "manager", "직원 합성 답입니다"))
    result = tick(channel, sec(16), memory, brain_fn=brain_fn, poster=poster)
    (row,) = rows()
    assert (row.state, poster.calls, result.drafting.staff_replied) == ("staff_replied", [], 1)
    later = tick(channel, sec(60), memory, brain_fn=brain_fn)  # 직원이 답한 상담은 다시 고르지 않는다
    assert (later.picked, len(brain_fn.requests)) == (0, 1)


def test_a_retryable_failed_turn_is_closed_when_staff_answers(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    row = turns.claim_turn(db_session, "LAHOM", "uc-1", "m-1", now=sec(5))
    turns.mark_failed(row, error_code="read_failed", now=sec(5))
    db_session.commit()
    talk.say("s-1", sec(10), "manager", "직원 합성 답입니다")
    tick(channel, sec(30), memory)
    assert [row.state for row in rows()] == ["staff_replied"]


# ── ④ 시작 신호는 손님 글만 ──────────────────────────────────────────────
def test_bot_notices_our_memo_and_code_messages_never_open_a_turn(channel):
    switch_on()
    memory, brain_fn = realtime.TickMemory(), FakeBrain()
    quiet = Talk(channel, "uc-1")
    quiet.say("b-1", sec(0), "bot", "합성 운영 시간이 아닙니다 — 내일 답드릴게요")  # 부재 안내(공개 봇 글)
    quiet.say("b-2", sec(1), "bot", "[AI 초안 · 합성] 우리 봇 메모", **PRIVATE)  # 우리 AI 메모
    quiet.say("p-1", sec(2), "manager", "직원끼리 합성 메모", **PRIVATE)  # 직원 내부 메모
    quiet.say("c-1", sec(3), "user", CODE_TEXT)  # 확인코드 글 — share_consult 가 링크로 답한다
    Talk(channel, "uc-2").say("m-1", sec(0))  # 음성 대조군: 진짜 손님 글
    tick(channel, sec(30), memory, brain_fn=brain_fn)
    assert rows("uc-1") == [] and [row.state for row in rows("uc-2")] == ["stored"]
    assert [request.chat_id for request in brain_fn.requests] == ["uc-2"]


# ── ⑤ 같은 손님 글 두 번 안 집음 ─────────────────────────────────────────
def test_the_same_customer_message_is_drafted_once_even_across_both_paths(channel):
    switch_on()
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain(max_calls=1)
    talk.say("m-1", sec(0))
    for second in (16, 21, 26, 300):
        tick(channel, sec(second), memory, brain_fn=brain_fn)
    fresh = realtime.TickMemory()  # 재시작해 메모리가 비어도 DB 고유 키가 막는다
    assert tick(channel, sec(320), fresh, brain_fn=brain_fn).drafting is None
    other = Talk(channel, "uc-3")
    other.say("m-3", sec(500))
    turns.claim_turn(db_session, "LAHOM", "uc-3", "m-3", now=sec(510), owner=turns.claim_owner("pass"),
                     ttl=datetime.timedelta(minutes=20))  # 15분 바퀴가 쥔 살아 있는 선점
    db_session.commit()
    tick(channel, sec(530), memory, brain_fn=FakeBrain(max_calls=0))
    assert [row.state for row in rows("uc-3")] == ["claimed"] and len(rows("uc-1")) == 1


# ── ⑥ TERM · 죽은 선점 ──────────────────────────────────────────────────
def test_term_during_the_call_drops_the_answer_and_calls_no_new_brain(channel):
    switch_on()
    memory, stop = realtime.TickMemory(), loop.StopFlag()
    for chat in ("uc-1", "uc-2"):
        Talk(channel, chat).say(f"m-{chat}", sec(0))
    brain_fn = FakeBrain(on_call=lambda _request: stop.set())  # 두뇌를 부르는 동안 TERM
    result = tick(channel, sec(20), memory, brain_fn=brain_fn, stop=stop)
    assert result.outcome == "stopped" and len(brain_fn.requests) == 1
    assert [(row.state, row.error_code) for row in rows("uc-1") + rows("uc-2")] == [("failed", "stopped")]
    assert tick(channel, sec(25), memory, brain_fn=brain_fn, stop=stop).outcome == "stopped"  # 깃발 뒤 차례는 일 0
    assert len(brain_fn.requests) == 1


def test_a_dead_claim_is_freed_only_after_it_expires(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    turns.claim_turn(db_session, "LAHOM", "uc-1", "m-1", now=sec(16), owner="realtime:dead-host:1",
                     ttl=realtime.CLAIM_TTL)  # 두뇌를 부르다 죽은 차례
    db_session.commit()
    early = tick(channel, sec(16 + 60), memory, brain_fn=FakeBrain(max_calls=0))  # 만료 전 — 손대지 않는다
    assert (early.expired, [row.state for row in rows()]) == (0, ["claimed"])
    brain_fn = FakeBrain()
    late = tick(channel, sec(16 + 91), memory, brain_fn=brain_fn)  # 만료 뒤 — 실패로 정리하고 다시 집는다
    (row,) = rows()
    assert (late.expired, row.state, row.attempts, len(brain_fn.requests)) == (1, "stored", 2, 1)
    assert row.claim_owner != "realtime:dead-host:1"


# ── ⑦ 15분 바퀴가 대표 잠금을 쥔 동안에도 시간 안에 초안 ─────────────────
def test_a_message_during_the_quarter_hour_pass_is_drafted_within_quiet_plus_timeout_plus_ten(channel, app):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    timeout = st.DEFAULTS["realtime_timeout_s"]
    wall = {"now": sec(0)}  # 가짜 벽시계 — 두뇌가 시간 상한을 다 쓴다

    def slow(_request):
        wall["now"] += datetime.timedelta(seconds=timeout)

    brain_fn = FakeBrain(on_call=slow)
    with loop.leader_lock(db_session.get_bind()) as leader:  # 15분 바퀴가 보정 · 아침 보고로 잠금을 쥐고 있다
        assert leader
        talk.say("m-1", sec(3))
        blocked = tick(channel, sec(4), memory, lock_key=loop.LEADER_LOCK_KEY)  # 음성 대조: 같은 키면 막힌다
        assert blocked.outcome == "not_leader"
        while not rows():
            assert wall["now"] < sec(300), "초안이 뜨지 않았다"
            result = tick(channel, wall["now"], memory, brain_fn=brain_fn,
                          clock=lambda: (wall["now"] - T0).total_seconds())
            assert result.outcome == "ok"  # 따로 잠금 — 15분 바퀴가 쥐고 있어도 돈다
            if not rows():
                wall["now"] += datetime.timedelta(seconds=realtime.TICK_SECONDS)
    drafted_after = (wall["now"] - sec(3)).total_seconds()
    assert rows()[0].state == "stored"
    assert drafted_after <= st.DEFAULTS["quiet_wait_s"] + timeout + 10, drafted_after


# ── ⑧ 거른 줄의 원본은 두 번 열지 않음 ───────────────────────────────────
def test_filtered_inbound_rows_are_remembered_and_not_reopened(channel):
    switch_on()
    memory = realtime.TickMemory()
    inbound(901, {**entity("g-1", sec(0), text="합성 그룹 글"), "chatType": "group"})  # 상담 글이 아님
    inbound(902, entity("x-1", sec(0), text="합성 모르는 채널", channel="999999"))
    talk = Talk(channel)
    talk.say("m-1", sec(1))
    inbound(903, entity("m-1", sec(1), text=f"{CUSTOMER} 같은 글의 두 번째 수신 줄"))
    first = tick(channel, sec(2), memory)
    assert (first.examined, first.ingested, first.filtered) == (4, 1, 3)
    again = tick(channel, sec(7), memory)
    assert (again.examined, again.filtered) == (0, 0)  # 같은 원본을 다시 열지 않는다
    forgetful = tick(channel, sec(12), realtime.TickMemory())  # 음성 대조: 기억이 없으면 거른 줄을 다시 연다
    assert forgetful.examined == 3


def test_the_memory_is_bounded():
    memory = realtime.TickMemory(limit=3)
    for log_id in range(10):
        memory.filtered.add(log_id)
    assert list(memory.filtered) == [7, 8, 9]


# ── ⑨ 'AI 냐 사람이냐' 물음 ──────────────────────────────────────────────
ASKS = ["혹시 AI세요?", "지금 답하시는 분 사람이에요?", "사람 맞나요?", "챗봇인가요", "로봇이랑 얘기하는 건가요?",
        "자동응답인가요?", "자동으로 답장 오는 거예요?", "실제 사람이 답하는 거죠?", "인공지능이 상담해 주나요",
        "봇 아니죠?", "are you a bot?", "상담원이세요?"]
NOT_ASKS = ["AI 로 만든 그림이에요?", "사람 몇 명 와요?", "자동으로 닫히는 문이에요?", "로봇청소기 들어가는 높이인가요?",
            "두 사람이 쓸 책상이에요", "어른 두 사람이에요", "실제 사람이 앉았을 때 높이가 어때요?", "AI 추천 기능 있나요?",
            "기계식 서랍이에요?", "메일이에요?", "AI가 만든 디자인 같아요", "사람이 많아서 큰 식탁이 필요해요"]


@pytest.mark.parametrize("text", ASKS)
def test_identity_questions_are_caught(text):
    assert asks_if_human(text)


@pytest.mark.parametrize("text", NOT_ASKS)
def test_negative_controls_are_not_identity_questions(text):
    assert not asks_if_human(text)


def test_an_identity_question_skips_the_brain_and_leaves_no_draft(channel):
    switch_on()
    memory, brain_fn = realtime.TickMemory(), FakeBrain()
    Talk(channel, "uc-1").say("m-1", sec(0), text=f"{CUSTOMER} 선반 문의요")
    Talk(channel, "uc-1").say("m-2", sec(2), text="그런데 혹시 AI세요?")
    Talk(channel, "uc-2").say("m-3", sec(0), text=NOT_ASKS[0])  # 음성 대조: 'AI' 낱말이 있어도 물음이 아니면 초안
    tick(channel, sec(20), memory, brain_fn=brain_fn)
    (asked,) = rows("uc-1")
    assert (asked.state, asked.error_code, asked.handoff, asked.handoff_reason) == (
        "skipped", "asked_if_ai", True, "asked_if_ai")
    assert asked.masked_draft is None and asked.model is None  # 초안 없음 · 두뇌 안 부름
    assert [request.chat_id for request in brain_fn.requests] == ["uc-2"] and rows("uc-2")[0].state == "stored"


def test_in_memo_mode_an_identity_question_posts_a_private_one_liner(channel):
    switch_on("memo")
    memory, poster = realtime.TickMemory(), FakePoster()
    Talk(channel).say("m-1", sec(0), text="사람이랑 대화하고 싶어요 혹시 자동응답인가요?")
    tick(channel, sec(20), memory, brain_fn=FakeBrain(max_calls=0), poster=poster)
    ((call,),) = [poster.calls]
    assert (call.text, call.state) == (ASK_HUMAN_MEMO, "posting")  # 같은 메모 길 — '올리는 중' 먼저 커밋
    (row,) = rows()
    assert (row.state, row.memo_message_id, row.masked_draft, row.handoff_reason) == (
        "posted", "memo-1", None, "asked_if_ai")


# ── ⑩ 바로 끄기 ↔ 초안 스위치 ────────────────────────────────────────────
def _switch_row():
    db_session.expire_all()
    row = db_session.get(SystemSetting, turns.SWITCH_KEY)
    return row.setting_value, row.version


def test_set_switch_reads_the_row_fresh_and_never_resurrects_an_old_draft_mode(app):
    db_session.add(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "on", "draft": "memo"},
                                 version=1))
    db_session.commit()
    stale = db_session.get(SystemSetting, turns.SWITCH_KEY)  # 이 세션이 들고 있는 옛 값(draft=memo)
    assert stale.setting_value["draft"] == "memo"
    db_session.execute(sa.update(SystemSetting.__table__).where(SystemSetting.setting_key == turns.SWITCH_KEY)
                       .values(setting_value={"loop": "on", "draft": "off"}, version=2))  # 막는 장치가 그사이 끔
    loop.set_switch(db_session, on=False, now=sec(0))
    value, version = _switch_row()
    assert (value["loop"], value["draft"], version) == ("off", "off", 3)  # 옛 memo 로 되돌리지 않았다


def test_set_switch_checks_the_version_and_retries_when_it_moved(app, monkeypatch, caplog):
    db_session.add(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "on", "draft": "memo"},
                                 version=1))
    db_session.commit()
    injected = []

    def racing_update(*args):  # 읽은 뒤 · 쓰기 전에 초안 스위치 쓰기가 끼어든다(판 1 → 2)
        if not injected:
            injected.append(1)
            turns.set_draft_mode(db_session, "store", reason="guard", now=sec(0))
            db_session.flush()
        return sa.update(*args)

    monkeypatch.setattr(loop, "update", racing_update)
    loop.set_switch(db_session, on=False, now=sec(1))
    value, version = _switch_row()
    assert (value["loop"], value["draft"], value["draft_reason"], version) == ("off", "store", "guard", 3)
    assert "판이 바뀌었다" in caplog.text  # 옛 판으로 쓰지 않고 다시 읽었다
    turns.set_draft_mode(db_session, "memo", reason="panel", now=sec(2))  # 거꾸로도: 초안 스위치는 loop 칸을 남긴다
    db_session.commit()
    value, version = _switch_row()
    assert (value["loop"], value["draft"], version) == ("off", "memo", 4)
