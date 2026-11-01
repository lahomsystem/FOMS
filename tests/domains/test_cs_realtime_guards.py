"""빠른 길 교차 검수 R13 (10-30) — 문제마다 먼저 실패하던 시험(증명 시험 r13 을 옮김)과 살아남은 변이를 잡는 시험.

R13-1 새 상담이 500개 상한에 굶음 · R13-2 돈 상한 · 준비 안 됨 뒤 5초마다 다시 집음 · R13-3 짧은 장애에 시도 셋을 몇 초 만에 씀 ·
R13-4 '정함' 기억이 늦게 온 물음을 재시작까지 숨김 · R13-5 'AI 냐' 물음 놓침 · 잘못 잡음(+ 두뇌 지시문 · 보내기 전 검사) · R13-6
채널톡 읽기가 늦으면 마지막 글이 '지난 초안' · R13-7 스위치 다시 읽기 · R13-8 선점 시각 · 만료 · R13-9 15분 바퀴의 'AI 냐' ·
같은 묶음 메모 한 번 · R13-10 색인 · 같은 오류 Sentry 간격 · R13-11 변이 넷. 합성 글만, 시각은 2026-11 KST(11-02 월요일).
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Index

from db import db_session
from foms.services.cs_agent import brain, drafting, loop, realtime, turns
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import settings as st
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.ask_human import ASK_HUMAN_MEMO, asks_if_human
from foms.services.cs_agent.checks import check_draft
from foms.services.cs_agent.realtime_memory import DECIDE_TTL
from foms.services.cs_agent.state import KST
from models import CsAgentChat, SystemSetting
from tests.domains.test_cs_drafting import CUSTOMER, PRIVATE, FakeBrain, FakePoster, channel  # noqa: F401
from tests.domains.test_cs_realtime import Talk, rows, sec, switch_on, tick
from tests.support.cs_agent_fakes import FakeClock, api_message, at, derived, keys, make_reader, weekdays_only  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]


def bump_settings(version, **values):
    """관리 화면 저장처럼 설정 판을 올린다."""
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, version=version,
                                   setting_value={**st.DEFAULTS, "realtime_enabled": True, **values}))
    db_session.commit()


# ── R13-1 새 것부터 · 창은 묵은 상담 기준 ────────────────────────────────
def test_r13_1_a_new_chat_is_picked_even_with_500_older_unanswered_chats(channel):
    switch_on()
    old = [derived(f"o-{i}", sec(-86400 * 3 + i), "user", "네 감사합니다", chat=f"uo-{i}")
           for i in range(realtime.MAX_CANDIDATES)]  # 금요일 맺음 인사뿐인 미답 상담 500(창 안)
    ss.store_messages(db_session, old, source="openapi")
    db_session.commit()
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain()
    talk.say("m-1", sec(0))
    tick(channel, sec(16), memory, brain_fn=brain_fn)
    assert [row.state for row in rows()] == ["stored"] and len(brain_fn.requests) == 1


@pytest.mark.parametrize("now,days,expected", [
    (at(2, 9), 1, datetime.datetime(2026, 10, 30, tzinfo=KST)),  # 월요일 → 금요일 0시(주말은 세지 않는다)
    (at(3, 9), 1, at(2, 0)),  # 화요일 → 월요일 0시
    (at(2, 9), 2, datetime.datetime(2026, 10, 29, tzinfo=KST)),  # 운영일 둘 → 목요일 0시
    (at(3, 9), 0.5, at(2, 0)),  # 반나절도 하루 앞 0시부터
])
def test_r13_1_the_window_follows_the_stale_rule_in_business_days(now, days, expected):
    got = realtime.window_start(now, days, weekdays_only)
    assert got == expected.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def test_r13_1_chats_older_than_the_window_are_not_read(channel):
    switch_on()
    ss.store_messages(db_session, [derived("o-1", at(2, 9) - datetime.timedelta(days=5), "user", f"{CUSTOMER} 문의",
                                           chat="uc-old")], source="openapi")  # 지난주 수요일 — 묵은 상담
    db_session.commit()
    result = tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(max_calls=0))
    assert (result.too_old, result.picked, rows("uc-old")) == (0, 0, [])  # 창 밖이라 읽지도 않는다


# ── R13-2 · R13-3 다시 시도 시각 한 규칙 ─────────────────────────────────
@pytest.mark.parametrize("error,later", [
    (brain.SpendCapReached(brain.DAILY_CAP_REACHED), at(3, 8, 30)),  # 돈 상한 — 그날 끝까지, 다음 날 다시
    (brain.BrainNotReady(brain.API_AUTH), sec(31 * 60)),  # 401 · 403 — 30분 뒤 다시
])
def test_r13_2_a_halt_inside_the_brain_pauses_drafting_instead_of_retrying_every_tick(channel, error, later):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    brain_fn = FakeBrain(error)
    for second in range(16, 16 + 5 * 12, 5):  # 1분
        tick(channel, sec(second), memory, brain_fn=brain_fn)
    assert len(brain_fn.requests) == 1 and memory.paused(sec(80)) is not None
    assert len([call for call in channel.calls if call.endswith("/messages")]) == 1  # 채널톡 읽기도 한 번
    result = tick(channel, later, memory, brain_fn=FakeBrain())
    assert result.paused is None and rows()[0].state == "stored"


def test_r13_2_a_new_settings_version_lifts_the_pause_at_once(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    tick(channel, sec(16), memory, brain_fn=FakeBrain(brain.SpendCapReached(brain.DAILY_CAP_REACHED)))
    assert tick(channel, sec(21), memory, brain_fn=FakeBrain(max_calls=0)).paused == "spend_cap"
    bump_settings(2)  # 관리 화면에서 하루 상한을 올린 저장
    tick(channel, sec(26), memory, brain_fn=FakeBrain())
    assert rows()[0].state == "stored"


def test_r13_3_a_half_minute_outage_does_not_burn_all_three_attempts(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    calls = []

    def flaky(request, *, session, now):  # 16초부터 45초까지 API 장애
        calls.append(now)
        if now < sec(45):
            raise brain.BrainUnavailable(brain.API_ERROR)
        return FakeBrain()(request, session=session, now=now)

    for second in range(16, 136, 5):
        tick(channel, sec(second), memory, brain_fn=flaky)
    (row,) = rows()
    assert (row.state, row.attempts) == ("stored", 2)  # 실패 뒤 30초 × 시도 수를 기다렸다
    assert [round((at_ - sec(0)).total_seconds()) for at_ in calls] == [16, 46]


# ── R13-4 판정 기억에 시간 상한 ──────────────────────────────────────────
def test_r13_4_a_late_earlier_question_is_picked_after_the_decision_expires(channel):
    switch_on()
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain()
    talk.say("m-2", sec(10), text="네 감사합니다")  # 맺음 인사뿐 — 정함(60초 뒤 기억)
    for second in range(15, 120, 5):
        tick(channel, sec(second), memory, brain_fn=brain_fn)
    assert rows() == [] and memory.decided  # 기억했다
    ss.store_messages(db_session, [derived("m-1", sec(0), "user", f"{CUSTOMER} 선반 깊이가 어떻게 되나요")],
                      source="openapi")  # 15분 보정이 웹훅이 빠뜨린 앞 물음을 넣었다
    db_session.commit()
    channel.messages["uc-1"].insert(0, api_message("m-1", sec(0), "user", f"{CUSTOMER} 선반 깊이가 어떻게 되나요"))
    drafted_at = None
    for second in range(120, 1200, 5):
        tick(channel, sec(second), memory, brain_fn=brain_fn)
        if rows():
            drafted_at = second
            break
    assert drafted_at is not None and drafted_at <= 70 + DECIDE_TTL.total_seconds() + 10


# ── R13-5 'AI 냐 사람이냐' 물음(검수 목록) · 두뇌 지시문 · 보내기 전 검사 ───────
R13_ASKS = [
    "혹시 AI세요?", "AI인가요?", "ai 인가요", "이거 AI 답변이에요?", "지금 봇이랑 대화하는 건가요?", "사람이세요?", "사람 맞나요?",
    "실제 사람인가요?", "진짜 사람이에요?", "상담원이세요?", "상담원분 맞으세요?", "사람이 답하는 거예요?", "자동응답인가요?",
    "자동으로 답장 오는 거예요?", "로봇이세요?", "챗봇이에요?", "기계가 답하는 건가요", "사람 아니죠?", "혹시 사람이 아니신가요?",
    "AI랑 얘기하는 거예요?", "지피티예요?", "챗gpt인가요?", "Are you a bot?", "are you human?", "사람이랑 얘기하고 싶어요",
    "상담원 연결해주세요", "사람한테 상담받고 싶어요", "직원분이세요?", "직원 맞으세요?", "실제 상담사님이 답하시는 건가요?",
    "답변이 너무 기계적인데 사람 맞아요?", "혹시 인공지능이 답하는 건가요?", "자동 답변이죠?", "AI 상담이에요?", "봇임?", "AI냐?",
    "사람임?", "AI야?", "에이아이에요?", "이거 매크로예요?", "자동응답 말고 사람이요", "사람이 직접 보는 거 맞죠?", "누구세요?",
    "사람 맞으시죠?", "사람이신가요", "AI 같아요", "로봇 같은데요", "사람이에요 AI에요?", "AI 아니에요?", "ai답변인가요",
    "AI가 쓴 거예요?", "상담사 분이신가요?", "진짜사람?",
]
R13_NOT_ASKS = [
    "AI로 만든 그림이에요?", "사람 몇 명 와요?", "자동으로 닫히는 문인가요", "로봇청소기 들어가나요?", "두 사람이에요",
    "실제 사람이 앉았을 때 높이가 궁금해요", "설치 기사님 몇 분 오세요?", "사람이 많이 앉아도 되나요?", "사람이 직접 조립해야 하나요?",
    "사람이 들 수 있는 무게인가요?", "한 사람이 옮길 수 있나요", "사람 키만한 장인가요?", "봇치 색상 있나요",
    "로봇청소기가 들어갈 높이인가요", "자동응답 메시지 받았어요 주문번호 1234", "AI 냉장고 들어가나요", "사람이 너무 많아서요",
    "4인 가족 사람 기준이에요", "사람마다 다르겠지만 추천해 주세요", "봇 말고 버튼 눌렀는데 안 돼요", "어떤 사람이 시공하러 오나요?",
    "설치하는 사람이 몇 명인가요?", "기사님이 사람 두 명이세요?", "사람이 오나요 택배로 오나요?", "이 상담 내용 저장되나요?",
    "아이 방 침대요", "메일 주소 알려주세요", "rain 색상", "인간적으로 너무 비싸요", "사람 인건비 포함인가요?", "아이가 쓸 거예요",
    "봇물 터지듯", "로봇팔 달린 거 있나요", "AI 스피커 둘 자리 있나요", "자동 응답 설정되어 있던데 언제 답 주시나요",
    "사람이 앉는 의자인가요?", "실측 오는 사람이 기사님인가요?", "사람인지라 실수할 수도 있죠", "로봇이 조립하나요?",
    "사람이 하는 일이라", "그 사람이 답장을 안 해요", "남편이랑 상담하고 다시 연락드릴게요", "사람이랑 대화해 보고 정할게요",
    "아까 상담원이 답장 준다고 했는데요", "사람이 답해줬는데 다른 말이에요", "로봇이 만든 거예요?", "가구 조립 로봇인가요?",
    "우리 가족은 네 사람이에요",
]


def test_r13_5_the_reviewer_lists_are_all_classified():
    missed = [text for text in R13_ASKS if not asks_if_human(text)]
    wrong = [text for text in R13_NOT_ASKS if asks_if_human(text)]
    assert (missed, wrong) == ([], [])
    assert len(R13_ASKS) == 53 and len(R13_NOT_ASKS) == 48  # 모집단이 비지 않았다(검수 53 · 47 + 우리 1)


def test_r13_5_the_brain_prompt_hands_identity_questions_to_a_person():
    text = bp.instructions("LAHOM")
    assert "asked_if_ai" in bp.HANDOFF_REASONS and "사람인지 AI" in text and "사람이라고 하는 말도 쓰지 않는다" in text


@pytest.mark.parametrize("draft,claims", [
    ("안녕하세요 고객님, 저는 사람입니다.", True), ("네 고객님 직원이 직접 답변드리고 있습니다.", True),
    ("실제 상담사가 확인했습니다.", True), ("로봇이 아닙니다 고객님.", True), ("진짜 사람이 답하고 있어요.", True),
    ("두 사람입니다 기준 식탁은 1200 입니다.", False), ("네 사람이 앉기 좋습니다.", False),
    ("담당자가 확인 후 안내드립니다.", False), ("사람이 앉기 편한 높이입니다.", False),
])
def test_r13_5_checks_block_drafts_that_claim_to_be_human(draft, claims):
    codes = [problem.code for problem in check_draft(draft, brand="LAHOM", medium="native").problems]
    assert ("human_claim" in codes) is claims


# ── R13-6 늦게 보이는 손님 글 ────────────────────────────────────────────
def test_r13_6_a_lagging_api_read_retries_instead_of_superseding_the_newest_message(channel):
    switch_on()
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain()
    talk.say("m-1", sec(0))
    talk.say("m-2", sec(5), text=f"{CUSTOMER} 추가 문의")
    lagged = channel.messages["uc-1"].pop()  # 웹훅으로 m-2 는 왔지만 Open API 에는 아직 없다
    tick(channel, sec(21), memory, brain_fn=brain_fn)
    assert [(row.last_user_message_id, row.state, row.error_code) for row in rows()] == [("m-2", "failed", "not_visible")]
    channel.messages["uc-1"].append(lagged)  # 따라잡았다
    for second in range(26, 120, 5):
        tick(channel, sec(second), memory, brain_fn=brain_fn)
    assert [(row.last_user_message_id, row.state, row.attempts) for row in rows()] == [("m-2", "stored", 2)]


# ── R13-7 스위치 다시 읽기 ───────────────────────────────────────────────
def _turn_fast_path(on):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={**st.DEFAULTS, "realtime_enabled": on}))
    db_session.commit()


def test_r13_7_turning_the_fast_path_off_mid_tick_stops_the_next_claim(channel):
    switch_on()
    for chat in ("uc-1", "uc-2"):
        Talk(channel, chat).say(f"m-{chat}", sec(0))
    result = tick(channel, sec(20), realtime.TickMemory(),
                  brain_fn=FakeBrain(on_call=lambda _request: _turn_fast_path(False)))
    assert result.drafting.halted == {"switched_off": 1} and len(rows("uc-1") + rows("uc-2")) == 1


def test_r13_7_turning_the_fast_path_on_mid_pass_stops_the_quarter_hour_drafting(channel):
    switch_on(realtime_enabled=False)
    for chat in ("uc-1", "uc-2"):
        Talk(channel, chat).say(f"m-{chat}", sec(0))
    ss.ingest_inbound(db_session, now=sec(1).astimezone(datetime.timezone.utc).replace(tzinfo=None))
    states = ss.compute_open_states(db_session, now=sec(30), brands=("LAHOM",), is_business_day=weekdays_only)
    summary = drafting.run_drafting(db_session, states=states, reader=make_reader(channel, FakeClock()), now=sec(30),
                                    stop=loop.StopFlag(), mode="store", is_business_day=weekdays_only,
                                    brain=FakeBrain(on_call=lambda _request: _turn_fast_path(True)), poster=FakePoster())
    assert summary.halted == {"switched_off": 1} and summary.brain_calls == 1


def test_r13_7_the_old_memo_is_not_removed_when_the_switch_went_off(channel, monkeypatch):
    switch_on("memo")
    talk, memory, removed = Talk(channel), realtime.TickMemory(), []
    talk.say("m-1", sec(0))
    tick(channel, sec(16), memory)
    talk.say("m-2", sec(30))
    real = realtime.mark_superseded

    def supersede_then_stop(row, **kwargs):  # 갈아 끼운 바로 뒤 누가 비상 정지를 눌렀다
        real(row, **kwargs)
        db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value={"loop": "off", "draft": "memo"}))

    monkeypatch.setattr(realtime, "mark_superseded", supersede_then_stop)
    tick(channel, sec(31), memory, memo_remover=lambda chat, memo_id: removed.append(memo_id))
    assert rows()[0].state == "superseded" and removed == []


# ── R13-8 선점 시각 · 만료 ───────────────────────────────────────────────
def test_r13_8_claims_use_the_real_time_and_expire_after_the_timeout_plus_45s(channel):
    switch_on(realtime_timeout_s=30)
    for chat in ("uc-1", "uc-2"):
        Talk(channel, chat).say(f"m-{chat}", sec(0))
    clock = {"t": 0.0}

    def slow(_request):
        clock["t"] += 25.0  # 첫 두뇌가 25초 걸렸다

    tick(channel, sec(20), realtime.TickMemory(), brain_fn=FakeBrain(on_call=slow), clock=lambda: clock["t"])
    utc = [row for chat in ("uc-1", "uc-2") for row in rows(chat)]
    naive = sec(20).astimezone(datetime.timezone.utc).replace(tzinfo=None)
    assert [row.created_at - naive for row in utc] == [datetime.timedelta(0), datetime.timedelta(seconds=25)]
    assert {row.claim_expires_at - row.created_at for row in utc} == {datetime.timedelta(seconds=30 + 45)}


# ── R13-9 15분 바퀴의 'AI 냐' · 같은 묶음 메모 한 번 ──────────────────────
def test_r13_9_the_quarter_hour_pass_also_hands_identity_questions_to_a_person(channel):
    switch_on(realtime_enabled=False)
    Talk(channel).say("m-1", sec(0), text="혹시 사람이세요?")
    ss.ingest_inbound(db_session, now=sec(1).astimezone(datetime.timezone.utc).replace(tzinfo=None))
    states = ss.compute_open_states(db_session, now=sec(30), brands=("LAHOM",), is_business_day=weekdays_only)
    drafting.run_drafting(db_session, states=states, reader=make_reader(channel, FakeClock()), now=sec(30),
                          stop=loop.StopFlag(), mode="store", is_business_day=weekdays_only,
                          brain=FakeBrain(max_calls=0), poster=FakePoster())
    (row,) = rows()
    assert (row.state, row.error_code, row.handoff_reason, row.masked_draft) == (
        "skipped", "asked_if_ai", "asked_if_ai", None)


def test_r13_9_memo_mode_posts_the_handoff_note_once_per_unanswered_run(channel):
    switch_on("memo")
    talk, memory, poster = Talk(channel), realtime.TickMemory(), FakePoster()
    talk.say("m-1", sec(0), text="혹시 AI세요?")
    tick(channel, sec(16), memory, brain_fn=FakeBrain(max_calls=0), poster=poster)
    channel.messages["uc-1"].append(api_message("note-1", sec(17), "bot", ASK_HUMAN_MEMO, **PRIVATE))  # 올라간 메모
    talk.say("m-2", sec(30), text="사람 맞으시죠?")
    tick(channel, sec(46), memory, brain_fn=FakeBrain(max_calls=0), poster=poster)
    assert len(poster.calls) == 1
    assert [(row.state, row.handoff_reason) for row in rows()] == [("superseded", "asked_if_ai"),
                                                                    ("skipped", "asked_if_ai")]


# ── R13-10 색인 · 같은 오류 간격 ─────────────────────────────────────────
def test_r13_10_the_candidate_query_has_its_index_in_model_and_migration():
    spec = importlib.util.spec_from_file_location(
        "csagent_02_r13", ROOT / "migrations" / "versions" / "csagent_02_turn_claim_owner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (index,) = [ix for ix in CsAgentChat.__table__.indexes if isinstance(ix, Index) and ix.name == module.CHATS_INDEX]
    assert [column.name for column in index.columns] == ["brand", "last_user_at"]
    assert module.CHATS_TABLE == CsAgentChat.__tablename__


def test_r13_10_the_same_tick_error_reaches_sentry_once_per_window(monkeypatch):
    spec = importlib.util.spec_from_file_location("run_cs_realtime_r13", ROOT / "scripts/maintenance/run_cs_realtime.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    now = {"t": 0.0}
    gate, sent = runner.ErrorGate(clock=lambda: now["t"]), []
    monkeypatch.setattr(runner, "run_tick", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(runner, "capture_exception", lambda *a, **k: sent.append(1))
    for second in (0, 5, 10, runner.ERROR_REPORT_SECONDS + 1):
        now["t"] = float(second)
        assert runner._tick(loop.StopFlag(), realtime.TickMemory(), gate) is None
    assert len(sent) == 2 and gate.should_report("KeyError")  # 다른 꼴은 바로 보낸다


# ── R13-11 살아남은 변이 넷 ──────────────────────────────────────────────
def test_r13_11_a_fresh_closing_message_is_not_remembered_before_decide_after(channel):
    switch_on()
    talk, memory, brain_fn = Talk(channel), realtime.TickMemory(), FakeBrain()
    talk.say("m-2", sec(10), text="네 감사합니다")
    tick(channel, sec(20), memory, brain_fn=brain_fn)  # 10초 — 아직 기억하지 않는다(늦게 커밋된 앞 글이 올 틈)
    ss.store_messages(db_session, [derived("m-1", sec(0), "user", f"{CUSTOMER} 선반 문의요")], source="openapi")
    db_session.commit()
    channel.messages["uc-1"].insert(0, api_message("m-1", sec(0), "user", f"{CUSTOMER} 선반 문의요"))
    tick(channel, sec(30), memory, brain_fn=brain_fn)
    assert [row.state for row in rows()] == ["stored"]


def test_r13_11_turns_before_a_staff_answer_are_not_superseded(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("m-1", sec(0))
    tick(channel, sec(16), memory)
    talk.say("s-1", sec(20), "manager", "직원 합성 답입니다")
    talk.say("m-2", sec(40), text=f"{CUSTOMER} 다른 문의요")
    tick(channel, sec(56), memory)
    assert [(row.last_user_message_id, row.state) for row in rows()] == [("m-1", "stored"), ("m-2", "stored")]


def test_r13_11_a_failed_turn_after_an_earlier_staff_answer_is_retried_not_closed(channel):
    switch_on()
    talk, memory = Talk(channel), realtime.TickMemory()
    talk.say("s-1", sec(5), "manager", "직원 합성 답입니다")
    talk.say("m-2", sec(10))
    row = turns.claim_turn(db_session, "LAHOM", "uc-1", "m-2", now=sec(20))
    turns.mark_failed(row, error_code="read_failed", now=sec(20))
    db_session.commit()
    tick(channel, sec(60), memory)  # 직원 답은 이 손님 글보다 앞 — 닫지 않고 다시 집는다
    assert [(row.state, row.attempts) for row in rows()] == [("stored", 2)]


def test_r13_11_term_during_supersede_stops_before_the_next_write(channel):
    switch_on("memo")
    talk, memory, stop = Talk(channel), realtime.TickMemory(), loop.StopFlag()
    for number, second in ((1, 0), (2, 20)):  # 같은 미답 묶음에 올린 차례 둘(메모 지우기 시험 전 자리)
        talk.say(f"m-{number}", sec(second))
        row = turns.claim_turn(db_session, "LAHOM", "uc-1", f"m-{number}", now=sec(second + 1))
        turns.mark_posting(row, masked_draft=None, now=sec(second + 1))
        turns.mark_posted(row, memo_message_id=f"memo-{number}", now=sec(second + 1))
        db_session.commit()
    talk.say("m-3", sec(40))
    result = tick(channel, sec(41), memory, stop=stop, memo_remover=lambda chat, memo_id: stop.set())
    assert result.outcome == "stopped"
    assert [row.state for row in rows()] == ["superseded", "posted"]  # TERM 뒤 다음 쓰기를 하지 않았다
