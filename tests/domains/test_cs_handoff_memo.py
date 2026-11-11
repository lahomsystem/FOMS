"""넘김 메모(:mod:`foms.services.cs_agent.handoff_memo`) — AI 가 초안을 안 쓰고 넘긴 차례에 '직원이 직접 답해 주세요' 메모 한 번.

끔(처음 값)이면 예전 그대로 기록만 · 두뇌 넘김 · 검사 걸림만(다른 건너뜀은 없음) · 메모 스위치만 · 차례 하나에 메모 하나(다시 집기
· 같은 까닭 묶음) · 직원 답 · 손님 새 글 뒤엔 안 올림 · 감싸개 실패해도 바퀴는 그대로 · 비공개 확인 못 함은 초안 메모와 같은
막는 장치 · 15분 바퀴도 같다. 두뇌 · 메모 감싸개 · 채널톡은 가짜(네트워크 · 키 없음), 손으로 꾸민 합성 글만 쓴다.
"""

from __future__ import annotations

import datetime
import re
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from db import db_session
from foms.services.cs_agent import brain, drafting, loop, memo, realtime, send, turns
from foms.services.cs_agent import handoff_memo as hm
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.ask_human import ASK_HUMAN_MEMO_HEAD
from foms.services.cs_agent.brain_prompt import HANDOFF_NONE, HANDOFF_REASONS
from foms.services.cs_agent.checks import REASONS
from foms.services.cs_agent.drafting_read import HANDOFF_MEMO_HEAD, MEMO_NOTE_HEAD, ChatLine, memo_snippets
from foms.services.cs_agent.handoff_memo_settings import HANDOFF_BUTTONS_FIELD, HANDOFF_MEMO_FIELD
from foms.services.cs_agent.memo import REASON_BAD_BUTTONS, MemoResult
from foms.services.cs_agent.masking import MaskLeak, mask
from models import CsAgentTurn, SystemSetting
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel 은 fixture
    CUSTOMER, NOTE, NOW, PRIVATE, FakeBrain, FakePoster, channel, customer, result, run,
)
from tests.domains.test_cs_realtime import Talk, rows, sec, switch_on, tick
from tests.support.cs_agent_fakes import api_message, derived, keys  # noqa: F401 — keys 는 fixture

HANDOFF = result(draft="", handoff=True, handoff_reason="unsure")  # 회사 지식에 없음 — 직원 참고는 NOTE
BAD = "안녕하세요 고객님, 합성 선반 깊이는 777mm 로 안내드립니다."  # 승인 지식에 없는 숫자 — 검사가 막는다
UNSURE_MEMO = "\n".join((HANDOFF_MEMO_HEAD, "까닭: 회사 지식에 없는 내용이에요", MEMO_NOTE_HEAD, NOTE))


class Poster(FakePoster):
    """메모 감싸개 대역 — 초안 메모는 '올리는 중', 넘김 메모는 '건너뜀'이 **커밋된 뒤에** 불려야 한다. ``fail`` 은 넘김 메모만
    (예외면 던지고, 결과면 그 결과)."""

    def __init__(self, *results, fail=None):
        super().__init__(*results)
        self.fail = fail

    def __call__(self, chat_id, text, *, brand, **kwargs):
        db_session.rollback()  # 커밋 안 된 바꿈은 여기서 사라진다
        state = db_session.scalar(select(CsAgentTurn.state).where(CsAgentTurn.chat_id == chat_id)
                                  .order_by(CsAgentTurn.id.desc()).limit(1))
        self.calls.append(SimpleNamespace(chat_id=chat_id, text=text, brand=brand, state=state, kwargs=kwargs))
        handoff = text.startswith(HANDOFF_MEMO_HEAD)
        assert state == ("skipped" if handoff else "posting"), f"차례가 {state} 일 때 메모를 불렀다"
        if handoff and isinstance(self.fail, BaseException):
            raise self.fail
        if handoff and self.fail is not None:
            return self.fail
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]

    @property
    def memos(self):
        return [call for call in self.calls if call.text.startswith(HANDOFF_MEMO_HEAD)]


class ChatBrain(FakeBrain):
    """상담마다 정한 결과를 내는 두뇌 대역(한 차례에 상담 여럿)."""

    def __init__(self, by_chat):
        super().__init__()
        self.by_chat = by_chat

    def __call__(self, request, *, session, now):
        self.requests.append(request)
        session.commit()
        return self.by_chat[request.chat_id]


def memo_on(mode="memo", **settings):
    switch_on(mode, **{HANDOFF_MEMO_FIELD: True, **settings})


# ── 끔 · 켬 ─────────────────────────────────────────────────────────────
def test_by_default_a_handoff_is_only_recorded_and_nothing_is_posted(channel):
    switch_on("memo")  # 넘김 메모 칸은 처음 값(끔)
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    outcome = tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(HANDOFF), poster=poster)
    (row,) = rows()
    assert poster.calls == [] and outcome.drafting.handoff_memos == 0
    assert (row.state, row.error_code, row.handoff_reason, row.memo_message_id) == (
        "skipped", "handoff", "unsure", None)


def test_a_handoff_posts_one_memo_with_the_plain_reason_and_the_staff_note(channel):
    memo_on()
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    outcome = tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(HANDOFF), poster=poster)
    ((call,),) = [poster.calls]
    assert (call.text, call.state, call.brand) == (UNSURE_MEMO, "skipped", "LAHOM")
    assert "buttons" not in call.kwargs and CUSTOMER not in call.text and "unsure" not in call.text
    (row,) = rows()
    assert (row.state, row.error_code, row.handoff_reason, row.memo_message_id, row.placed_at) == (
        "skipped", "handoff", "unsure", "memo-1", None)  # 차례 기록 · 초안 지표는 예전 그대로, 메모 id 만 더했다
    assert (outcome.drafting.handoff_memos, outcome.drafting.posted, outcome.drafting.halted) == (1, 0, {})


def test_without_a_staff_note_the_memo_is_head_and_reason_only(channel):
    memo_on()
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    complaint = result(draft="", handoff=True, handoff_reason="complaint", staff_note="  ")
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(complaint), poster=poster)
    assert [call.text for call in poster.calls] == [f"{HANDOFF_MEMO_HEAD}\n까닭: 불만 상담이라 사람이 답해야 해요"]


def test_a_blocked_draft_posts_the_reason_without_the_draft_or_buttons(channel, monkeypatch):
    monkeypatch.setenv("FOMS_BASE_URL", "https://foms.example")  # 초안 메모라면 단추가 붙는 설정
    memo_on(send_buttons_enabled=True)
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(result(draft=BAD)), poster=poster)
    ((call,),) = [poster.calls]
    assert call.text == "\n".join((HANDOFF_MEMO_HEAD, "까닭: 초안에 승인 안 된 숫자가 있어 막았어요", MEMO_NOTE_HEAD, NOTE))
    assert "buttons" not in call.kwargs and "777" not in call.text  # 걸린 초안 · [수정하기] 단추 없음
    (row,) = rows()
    assert (row.state, row.error_code, row.check_codes, row.masked_draft, row.memo_message_id) == (
        "skipped", "check_failed", ["number_not_allowed"], mask(BAD), "memo-1")


class ButtonsRefused(Poster):
    """단추 꼴이 틀렸다고 돌려주는 대역(단추가 있을 때만) — 단추 없이 다시 올리는지 본다."""

    def __call__(self, chat_id, text, *, brand, **kwargs):
        if kwargs.get("buttons"):
            self.calls.append(SimpleNamespace(chat_id=chat_id, text=text, brand=brand, state="skipped", kwargs=kwargs))
            return MemoResult(False, reason=REASON_BAD_BUTTONS)
        return super().__call__(chat_id, text, brand=brand, **kwargs)


@pytest.mark.parametrize("path, buttons_field, wanted", [
    ("wam", True, True), ("link", True, False), ("wam", False, False)])
def test_learn_and_skip_buttons_ride_only_the_window_path_when_switched_on(channel, monkeypatch, path, buttons_field,
                                                                          wanted):
    monkeypatch.setenv(send.WAM_APP_ENV, "app0public0wam01")
    memo_on(send_buttons_enabled=True, send_button_path=path, **{HANDOFF_BUTTONS_FIELD: buttons_field})
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(HANDOFF), poster=poster)
    ((call,),) = [poster.memos]
    (row,) = rows()
    if not wanted:
        assert "buttons" not in call.kwargs
        return
    assert [(title, target["args"]) for title, target in call.kwargs["buttons"]] == [
        ("배우기", {"turn": row.id, "mode": "learn"}), ("흘리기", {"turn": row.id, "mode": "skip"})]


def test_a_refused_button_shape_posts_the_memo_again_without_buttons(channel, monkeypatch):
    monkeypatch.setenv(send.WAM_APP_ENV, "app0public0wam01")
    memo_on(send_buttons_enabled=True, send_button_path="wam", **{HANDOFF_BUTTONS_FIELD: True})
    poster = ButtonsRefused()
    Talk(channel).say("m-1", sec(0))
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(HANDOFF), poster=poster)
    assert [bool(call.kwargs.get("buttons")) for call in poster.memos] == [True, False]
    (row,) = rows()
    assert row.memo_message_id == "memo-1"  # 메모는 잃지 않는다(단추만 빠진다)


def test_store_mode_posts_no_memo(channel):
    memo_on("store")
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(HANDOFF), poster=poster)
    assert poster.calls == [] and [(row.state, row.error_code) for row in rows()] == [("skipped", "handoff")]


# ── 다른 건너뜀은 메모 없음 ─────────────────────────────────────────────
@pytest.mark.parametrize("code", ["email", "photo_only", "no_text", "mask_leak", "quote_min_width", "stale",
                                  "human_replied", "not_visible", "refused", "bad_request", "draft_mask_leak"])
def test_other_skip_codes_never_reach_the_memo_wrapper(code):
    ctx = SimpleNamespace(stop=loop.StopFlag(), poster=lambda *a, **k: pytest.fail("메모를 불렀다"))
    row = SimpleNamespace(state="skipped", memo_message_id=None, chat_id="uc-1")
    assert hm.post_handoff_memo(ctx, row, code) is None


@pytest.mark.parametrize("case", ["refused", "mask_leak", "email"])
def test_refusal_mask_leak_and_email_stay_silent_end_to_end(channel, case):
    memo_on()
    poster = Poster()
    Talk(channel).say("m-1", sec(0))
    if case == "email":
        channel.media["uc-1"] = "email"
    outcome = {"refused": result(draft="", handoff=True, handoff_reason="refused", refused=True, staff_note=""),
               "mask_leak": MaskLeak({"전화": 1})}.get(case, HANDOFF)
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(outcome), poster=poster)
    assert poster.calls == [] and [row.error_code for row in rows()] == [case]


@pytest.mark.parametrize("person", ["manager", "user"])
def test_no_memo_when_staff_replied_or_the_customer_wrote_more_meanwhile(channel, person):
    memo_on()
    talk, poster = Talk(channel), Poster()
    talk.say("m-1", sec(0))
    meanwhile = FakeBrain(HANDOFF, on_call=lambda _r: talk.say("x-1", sec(17), person, "합성 다른 글이에요"))
    tick(channel, sec(16), realtime.TickMemory(), brain_fn=meanwhile, poster=poster)
    assert poster.calls == [] and [(row.state, row.memo_message_id) for row in rows()] == [("skipped", None)]


# ── 차례 하나에 메모 하나 ───────────────────────────────────────────────
def test_retries_and_repeated_ticks_post_only_one_memo(channel):
    memo_on()
    memory, poster = realtime.TickMemory(), Poster()
    Talk(channel).say("m-1", sec(0))
    brain_fn = FakeBrain(brain.BrainUnavailable(brain.BAD_RESPONSE), HANDOFF)  # 첫 시도는 답 꼴이 틀려 실패(다시 집음)
    tick(channel, sec(16), memory, brain_fn=brain_fn, poster=poster)
    assert poster.calls == [] and [row.state for row in rows()] == ["failed"]
    for second in (60, 120, 300):  # 다시 집기 간격 뒤 넘김 → 메모, 그 뒤 차례는 끝난 줄이라 다시 안 집는다
        tick(channel, sec(second), memory, brain_fn=brain_fn, poster=poster)
    assert [call.text for call in poster.calls] == [UNSURE_MEMO] and len(brain_fn.requests) == 2
    assert [(row.state, row.attempts, row.memo_message_id) for row in rows()] == [("skipped", 2, "memo-1")]


def test_the_same_reason_in_the_same_unanswered_run_is_not_repeated(channel):
    memo_on()
    talk, memory, poster = Talk(channel), realtime.TickMemory(), Poster()
    talk.say("m-1", sec(0))
    tick(channel, sec(16), memory, brain_fn=FakeBrain(HANDOFF), poster=poster)
    channel.messages["uc-1"].append(api_message("memo-1", sec(17), "bot", UNSURE_MEMO, **PRIVATE))  # 올라간 메모
    talk.say("m-2", sec(30), text=f"{CUSTOMER} 하나 더요")
    tick(channel, sec(46), memory, brain_fn=FakeBrain(HANDOFF), poster=poster)  # 같은 까닭 — 직원은 이미 안다
    talk.say("m-3", sec(60), text=f"{CUSTOMER} 화가 나요")
    complaint = result(draft="", handoff=True, handoff_reason="complaint")
    tick(channel, sec(76), memory, brain_fn=FakeBrain(complaint), poster=poster)  # 까닭이 바뀌면 다시 알린다
    assert [call.text.split("\n")[1] for call in poster.calls] == ["까닭: 회사 지식에 없는 내용이에요",
                                                                   "까닭: 불만 상담이라 사람이 답해야 해요"]
    assert [row.memo_message_id for row in rows()] == ["memo-1", None, "memo-1"]


# ── 실패 · 막는 장치 ────────────────────────────────────────────────────
@pytest.mark.parametrize("fail", [RuntimeError("합성 오류"), memo.MemoResult(False, reason="send_provider_error"),
                                  memo.MemoResult(False, reason=memo.SEND_UNKNOWN)])
def test_a_memo_failure_never_breaks_the_pass(channel, fail):
    memo_on()
    poster = Poster(fail=fail)
    Talk(channel, "uc-1").say("a-1", sec(0))
    Talk(channel, "uc-2").say("b-1", sec(1))
    outcome = tick(channel, sec(20), realtime.TickMemory(), poster=poster,
                   brain_fn=ChatBrain({"uc-1": HANDOFF, "uc-2": result()}))
    assert (outcome.outcome, outcome.drafting.halted, outcome.drafting.handoff_memos) == ("ok", {}, 0)
    assert [(row.state, row.memo_message_id) for row in rows("uc-1")] == [("skipped", None)]
    assert [(row.state, row.memo_message_id) for row in rows("uc-2")] == [("posted", "memo-1")]  # 다음 상담은 그대로


@pytest.mark.parametrize("reason,mode,halt", [(memo.REASON_NOT_FOUND, "store", "memo_unverified"),
                                              (memo.REASON_NOT_PRIVATE, "off", "memo_not_private")])
def test_an_unverified_memo_trips_the_same_guard_as_draft_memos(channel, reason, mode, halt):
    memo_on()
    poster = Poster(fail=memo.MemoResult(True, verified=False, message_id="memo-9", reason=reason))
    Talk(channel).say("m-1", sec(0))
    outcome = tick(channel, sec(16), realtime.TickMemory(), brain_fn=FakeBrain(HANDOFF), poster=poster)
    assert (turns.draft_mode(db_session), outcome.drafting.halted, outcome.drafting.unverified) == (mode, {halt: 1}, 1)
    assert [(row.state, row.memo_message_id) for row in rows()] == [("skipped", "memo-9")]


# ── 15분 바퀴 ───────────────────────────────────────────────────────────
def test_the_fifteen_minute_loop_posts_the_same_memo_once(channel):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY,
                                   setting_value={**st.DEFAULTS, HANDOFF_MEMO_FIELD: True}))  # 빠른 길은 끔
    db_session.commit()
    customer(channel)
    poster = Poster()
    first = run(channel, "memo", brain_fn=FakeBrain(HANDOFF, max_calls=1), poster=poster)
    second = run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=poster,
                 now=NOW + datetime.timedelta(minutes=15))  # 다음 바퀴 — 끝난 차례라 다시 집지 않는다
    assert [call.text for call in poster.calls] == [UNSURE_MEMO]
    assert (first.handoff_memos, second.handoff_memos, second.already) == (1, 0, 1)


# ── 글 ──────────────────────────────────────────────────────────────────
def test_every_reason_and_check_code_has_plain_words():
    for reason in HANDOFF_REASONS:
        if reason != HANDOFF_NONE:
            assert reason in hm.HANDOFF_TEXTS, reason
    blocking = {code for code in REASONS if not code.startswith("tone_")} - {"empty"}
    assert blocking == set(hm.CHECK_WORDS)
    texts = [*hm.HANDOFF_TEXTS.values(), *hm.CHECK_WORDS.values(), hm.HANDOFF_UNKNOWN, hm.CHECK_EMPTY, hm.CHECK_UNKNOWN]
    assert not [text for text in texts if re.search(r"[a-z_]{2,}", text)]  # 코드 글자 없음('AI' 는 낱말)
    assert hm.MEMO_CODES == (drafting.SKIP_HANDOFF, drafting.SKIP_CHECK)


def test_reason_lines_join_once_and_pick_the_right_particle():
    line = hm.reason_text
    assert line("check_failed", check_codes=["refund_promise"]) == "초안에 환불 약속처럼 보이는 말이 있어 막았어요"
    assert line("check_failed", check_codes=["number_not_allowed", "date_not_confirmed", "number_not_allowed"]) == (
        "초안에 승인 안 된 숫자 · 확정 안 된 날짜가 있어 막았어요")
    assert line("check_failed", check_codes=["private_memo_leak"]) == "초안에 내부 메모에 있던 문장이 있어 막았어요"
    assert line("check_failed", check_codes=["empty", "other_brand"]) == hm.CHECK_EMPTY
    assert line("check_failed", check_codes=["something_new"]) == hm.CHECK_UNKNOWN
    assert line("handoff", handoff_reason="something_new") == line("handoff", handoff_reason=None) == hm.HANDOFF_UNKNOWN


def test_the_head_is_distinct_and_the_leak_check_reads_only_the_note():
    assert not HANDOFF_MEMO_HEAD.startswith(ASK_HUMAN_MEMO_HEAD)  # 'AI 냐' 한 줄 메모의 '이미 올림' 거름과 안 겹친다
    assert not ASK_HUMAN_MEMO_HEAD.startswith(HANDOFF_MEMO_HEAD)
    when = sec(0)

    def private(text):
        return ChatLine(derived("memo-1", when, "bot", text, **PRIVATE), text)

    bare = hm.memo_body("handoff", handoff_reason="unsure")
    assert memo_snippets([private(bare)]) == [""]  # 정한 까닭 말은 다음 초안 검사의 섞임 재료가 아니다
    assert memo_snippets([private(UNSURE_MEMO)]) == [f"\n{NOTE}"]
