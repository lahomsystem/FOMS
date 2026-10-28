"""초안 차례(플랜 C3-1) — 감시 루프 끝에서 라홈 '답 필요' 상담에 AI 초안: 고르기 · 선점 · 읽기 · 두뇌 · 검사 · 직전 다시
읽기 · 저장만 · 메모 · 오류 · TERM · 정리 · 감시 루프 고리.

완료 기준(브리프): 끔이면 선점 0 · 저장만은 감싸개 0 · 메모는 '올리는 중'이 커밋된 뒤 감싸개 · 두 번 돌아도 메모 하나 · 그사이
새 손님 글 · 사람 답이면 안 올림 · 검사에 걸리면 안 올림 · 가림 · 준비 안 됨은 건너뜀 · 두뇌 못 씀은 실패(다시 집음) · 돈 상한은
그날 멈춤 · 닿았는지 모름은 '올리는 중' 그대로 · 오래 남은 선점 정리 · TERM · 하우드 · 이메일 · 메모 꼴 · 로그 · 요약에 손님 글
없음 · 끈 바퀴는 예전 그대로. 두뇌 · 메모 감싸개 · 채널톡은 가짜(네트워크 · 키 없음), 손으로 꾸민 합성 글만(전화 꼴 숫자 ·
실제 가격 없음). 시각은 2026-11 KST(11-02 월요일), 달력은 '주말만 쉼' 가짜 달력이다.
"""

from __future__ import annotations

import functools
import itertools
import json
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.services.cs_agent import brain, drafting, loop, memo, turns
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.drafting_read import MEMO_DRAFT_HEAD, MEMO_HEAD, MEMO_NOTE_HEAD, memo_text, read_medium
from foms.services.cs_agent.knowledge import knowledge_key
from foms.services.cs_agent.masking import MaskLeak
from models import CsAgentTurn, SystemSetting
from tests.support.cs_agent_fakes import (  # noqa: F401 — keys 는 fixture
    HAUD_CHANNEL, LAHOM_CHANNEL, FakeAnthropic, FakeChannel, FakeClock, api_message, at, derived, keys, make_reader,
    weekdays_only,
)

CUSTOMER = "주황고래손님표지"  # 손님 글 표지 — 로그 · 요약 · 표 어디에도 나오면 안 된다
NOTE = "파랑고래참고표지 합성 규격만 확인해 주세요"  # 직원 참고 표지 — 메모에만 실린다
DRAFT = "안녕하세요 고객님, 합성 선반 깊이는 350mm 로 안내드립니다."  # 승인 지식의 숫자만 쓴 초안(검사 통과)
NOW = at(2, 9)  # 월요일 운영 시간
PRIVATE = {"options": ["MESSAGE_OPTION_PRIVATE"]}


def item(item_id, kind, text, intents=(), checked_at=None):
    return {"id": item_id, "kind": kind, "intents": list(intents), "text": text, "status": "approved",
            "approved_by": "synthetic-owner", "approved_at": "2026-10-20", "checked_at": checked_at, "source": None,
            "tags": []}


KNOWLEDGE = {"schema_version": 1, "brand": "LAHOM", "items": [
    item("hours-day", "template", "평일 낮에 상담을 도와 드립니다", intents=("hours",)),
    item("shelf-depth", "fact", "합성 선반 깊이는 350mm 입니다"),
    item("far-fee", "price_rule", "합성 지방 운임 4,321원(가짜 값) [사람]", checked_at="2026-10-20"),
]}


@pytest.fixture
def channel(app, keys, monkeypatch):
    """승인 지식 · 라홈 Open API 키(가짜) · 두뇌 준비 env(가짜 키 · 하루 상한) · 운영 밖 시험 상담 허용 목록 · 가짜 채널톡."""
    db_session.add(SystemSetting(setting_key=knowledge_key("LAHOM"), setting_value=KNOWLEDGE, version=1))
    db_session.commit()
    for key in ("FOMS_ENV", "RAILWAY_PROJECT_NAME", "RAILWAY_ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(memo.TEST_CHAT_IDS_ENV, "uc-1,uc-2,uc-3,uc-4,uc-5")
    monkeypatch.setenv(brain.KEY_ENV, "synthetic-placeholder")  # 선점 전 준비 확인(R7-4)만 지난다 — 진짜 호출은 없다
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")
    monkeypatch.setattr(brain, "_default_client", lambda: pytest.fail("진짜 SDK 클라이언트를 만들려 했다"))
    return FakeChannel()


def customer(channel, chat="uc-1", *, text=None, extra=None, medium="native", channel_id=LAHOM_CHANNEL, more=()):
    """손님 글 하나로 '답 필요'인 상담 — 상태 표(파생 칸)와 가짜 채널톡(원문)에 같은 글. ``more`` = (id, 시각, 사람, 글, 칸)."""
    first = (f"m-{chat}", at(2, 8, 50), "user", f"{CUSTOMER} 선반 깊이 문의드려요" if text is None else text, extra or {})
    rows = [first, *more]
    ss.store_messages(db_session, [derived(m, w, p, t, chat=chat, channel=channel_id, **x) for m, w, p, t, x in rows],
                      source="openapi")
    db_session.commit()
    channel.chat(chat, *[api_message(m, w, p, t, **x) for m, w, p, t, x in rows], medium=medium)


def result(draft=DRAFT, **overrides):
    values = dict(intent="hours", draft=draft, evidence_ids=("shelf-depth",), handoff=False, handoff_reason="none",
                  staff_note=NOTE, model=brain.MODEL, effort="high", input_tokens=900, output_tokens=200,
                  cache_read_tokens=0, cache_write_tokens=0, cost_usd=Decimal("0.01"), latency_ms=1200,
                  stop_reason="end_turn", refused=False, fallback_used=False)
    values.update(overrides)
    return brain.DraftResult(**values)


class FakeBrain:
    """두뇌 대역 — 재료를 남기고 정한 결과(예외도)를 차례로 낸다(마지막 것은 계속). 실제처럼 세션을 두 번 커밋한다(21행)."""

    def __init__(self, *outcomes, on_call=None, max_calls=None):
        self.outcomes, self.on_call, self.max_calls = list(outcomes) or [result()], on_call, max_calls
        self.requests = []

    def __call__(self, request, *, session, now):
        assert self.max_calls is None or len(self.requests) < self.max_calls, "두뇌를 또 불렀다 — 선점이 막아야 한다"
        self.requests.append(request)
        session.commit()
        if self.on_call:
            self.on_call(request)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        session.commit()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakePoster:
    """메모 감싸개 대역 — 부를 때 그 차례가 '올리는 중'으로 **커밋**됐는지 본다(되돌려도 남아야 커밋된 것). 결과는 차례로."""

    def __init__(self, *results, raises=None):
        self.results = list(results) or [memo.MemoResult(True, verified=True, message_id="memo-1")]
        self.raises, self.calls = raises, []

    def __call__(self, chat_id, text, *, brand, **kwargs):
        db_session.rollback()  # 커밋 안 된 바꿈은 여기서 사라진다
        state = db_session.scalar(select(CsAgentTurn.state).where(CsAgentTurn.chat_id == chat_id)
                                  .order_by(CsAgentTurn.id.desc()).limit(1))
        self.calls.append(SimpleNamespace(chat_id=chat_id, text=text, brand=brand, state=state, kwargs=kwargs))
        assert state == "posting", f"'올리는 중'을 커밋하기 전에 메모를 불렀다(지금 {state})"
        if self.raises:
            raise self.raises
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def run(channel, mode="store", *, brain_fn=None, poster=None, now=NOW, stop=None, **kwargs):
    if mode in turns.DRAFT_MODES and db_session.get(SystemSetting, turns.SWITCH_KEY) is None:
        set_switch({"draft": mode})  # 감시 루프처럼 스위치 줄이 있다(메모 직전에 다시 읽는다) — 있으면 건드리지 않는다
    states = ss.compute_open_states(db_session, now=now, brands=("LAHOM", "HAUD"), is_business_day=weekdays_only)
    return drafting.run_drafting(db_session, states=states, reader=make_reader(channel, FakeClock()), now=now,
                                 stop=stop or loop.StopFlag(), mode=mode, is_business_day=weekdays_only,
                                 brain=brain_fn or FakeBrain(), poster=poster or FakePoster(), **kwargs)


def turn(chat="uc-1"):
    db_session.expire_all()
    return db_session.scalars(select(CsAgentTurn).where(CsAgentTurn.chat_id == chat)
                              .order_by(CsAgentTurn.id.desc())).first()


def turn_count():
    return db_session.scalar(select(func.count()).select_from(CsAgentTurn.__table__))


def outcome(*chats):
    return [(turn(chat).state, turn(chat).error_code) for chat in chats]


# ── 스위치 · 저장만 · 메모 ──────────────────────────────────────────────


def test_mode_off_claims_nothing(channel):
    customer(channel)
    brain_fn = FakeBrain()
    for mode in ("off", "", "MEMO"):
        assert run(channel, mode, brain_fn=brain_fn).counts() == drafting.DraftSummary().counts()
    assert turn_count() == 0 and not brain_fn.requests and channel.calls == []
    with pytest.raises(ValueError):  # 시간대 없는 시각은 받지 않는다(KST · UTC 가 섞이면 조용히 틀린다)
        drafting.run_drafting(db_session, states=[], reader=None, now=NOW.replace(tzinfo=None), stop=loop.StopFlag(),
                              mode="store")


def test_store_mode_keeps_the_masked_draft_and_never_posts(channel):
    old_memo = memo_text(DRAFT, "이전 합성 참고입니다")  # 같은 답이 다시 나와도 우리 메모의 초안 칸 때문에 막히지 않는다
    customer(channel, more=[("p-1", at(2, 8, 55), "manager", "직원끼리 합성 메모입니다", PRIVATE),
                            ("b-1", at(2, 8, 56), "bot", "합성 자동 안내입니다", {}),
                            ("c-1", at(2, 8, 57), "bot", old_memo, PRIVATE)])
    brain_fn, poster = FakeBrain(), FakePoster()
    summary = run(channel, brain_fn=brain_fn, poster=poster)
    row = turn()
    assert (row.state, row.attempts, row.last_user_message_id, row.intent, row.model) == (
        "stored", 1, "m-uc-1", "hours", brain.MODEL)
    assert (row.masked_draft, row.check_codes, poster.calls) == (DRAFT, [], [])
    (request,) = brain_fn.requests
    assert request.messages == (("user", f"{CUSTOMER} 선반 깊이 문의드려요"),)  # 내부 메모 · 봇 · AI 메모는 재료에서 빠진다
    assert (request.brand, request.purpose, request.realtime, request.daytime, request.medium) == (
        "LAHOM", "draft", False, True, "native")
    assert request.customer_names == request.staff_names == () and request.knowledge.version == 1
    assert (summary.candidates, summary.claimed, summary.brain_calls, summary.stored) == (1, 1, 1, 1)
    assert channel.calls == ["user-chats/uc-1", "user-chats/uc-1/messages", "user-chats/uc-1/messages"]  # 직전 다시 읽기


def test_memo_mode_commits_posting_before_the_wrapper_then_posts(channel):
    customer(channel)
    poster = FakePoster()
    summary = run(channel, "memo", poster=poster)
    assert [call.state for call in poster.calls] == ["posting"]  # 감싸개 안에서 되돌려도 남았다 = 커밋됐다
    row = turn()
    assert (row.state, row.memo_message_id, row.error_code, row.masked_draft) == ("posted", "memo-1", None, DRAFT)
    assert (summary.posted, summary.unverified, summary.stored) == (1, 0, 0)


def test_memo_text_is_the_pilot_shape_with_a_masked_staff_note(channel):
    customer(channel)
    poster = FakePoster()
    run(channel, "memo", brain_fn=FakeBrain(result(staff_note=f"{NOTE} 가상로 12 앞")), poster=poster)
    (call,) = poster.calls
    assert (call.chat_id, call.brand, set(call.kwargs)) == ("uc-1", "LAHOM", {"reader"})  # 루프 읽기 도우미(R7-11)
    assert call.text.split("\n") == ["[AI 초안 · 손님에게 보내지 않음 · 직원이 고쳐서 보내 주세요]", "■ 손님께 보낼 답(초안)",
                                     DRAFT, "■ 직원 참고(손님에게 보내지 마세요)", f"{NOTE} [도로명주소] 앞"]
    assert (MEMO_HEAD, MEMO_DRAFT_HEAD, MEMO_NOTE_HEAD) == tuple(call.text.split("\n")[i] for i in (0, 1, 3))


def test_handoff_and_refusal_are_recorded_without_a_memo(channel):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    poster = FakePoster()
    brain_fn = FakeBrain(result("", handoff=True, handoff_reason="complaint"),
                         result("", handoff=True, handoff_reason="refused", refused=True, staff_note=""))
    summary = run(channel, "memo", brain_fn=brain_fn, poster=poster)
    assert outcome("uc-1", "uc-2") == [("skipped", "handoff"), ("skipped", "refused")] and not poster.calls
    assert (turn("uc-1").handoff, turn("uc-1").handoff_reason) == (True, "complaint")  # 넘김 까닭 코드는 남는다
    assert summary.skipped == {"handoff": 1, "refused": 1}


def test_memo_mode_outside_the_test_allowlist_only_stores(channel):
    customer(channel, "uc-9")
    poster = FakePoster()
    summary = run(channel, "memo", poster=poster)
    assert (turn("uc-9").state, summary.stored, summary.not_allowed, poster.calls) == ("stored", 1, 1, [])


# ── 겹침 · 그사이 · 검사 ─────────────────────────────────────────────────


def test_a_second_run_or_a_death_after_posting_writes_one_memo(channel):
    customer(channel)
    brain_fn, poster = FakeBrain(max_calls=1), FakePoster()
    assert run(channel, "memo", brain_fn=brain_fn, poster=poster).posted == 1
    again = run(channel, "memo", brain_fn=brain_fn, poster=poster, now=at(2, 9, 15))
    assert (again.already, again.claimed, again.brain_calls, len(poster.calls)) == (1, 0, 0, 1)
    customer(channel, "uc-2")  # 감싸개를 부른 직후 프로세스가 죽었다 — '올리는 중'이 남아 다시 집지 않는다
    with pytest.raises(RuntimeError):
        run(channel, "memo", poster=FakePoster(raises=RuntimeError("합성 죽음")), now=at(2, 9, 30))
    assert turn("uc-2").state == "posting"
    later = FakePoster()
    assert run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=later, now=at(2, 9, 45)).already == 2
    assert not later.calls and turn_count() == 2


def test_a_customer_message_during_the_call_makes_the_draft_stale(channel):
    customer(channel)

    def newer(_request):
        channel.messages["uc-1"].append(api_message("m-new", at(2, 8, 58), "user", "합성 추가 문의"))

    poster = FakePoster()
    summary = run(channel, "memo", brain_fn=FakeBrain(on_call=newer), poster=poster)
    row = turn()
    assert (row.state, row.error_code, row.masked_draft, poster.calls) == ("skipped", "stale", DRAFT, [])
    assert summary.skipped == {"stale": 1}


def test_a_human_reply_is_not_selected_or_skips_the_turn(channel):
    customer(channel, "uc-1", more=[("a-1", at(2, 8, 55), "manager", "합성 답입니다", {})])  # 상태 표가 안다 → 안 고름
    customer(channel, "uc-2")
    channel.messages["uc-2"].append(api_message("a-2", at(2, 8, 55), "manager", "합성 답입니다"))  # 웹훅이 빠뜨린 답

    def replied(_request):
        channel.messages["uc-3"].append(api_message("a-3", at(2, 8, 59), "manager", "합성 답입니다"))

    customer(channel, "uc-3")
    brain_fn, poster = FakeBrain(on_call=replied), FakePoster()
    summary = run(channel, "memo", brain_fn=brain_fn, poster=poster)
    assert turn("uc-1") is None and summary.candidates == 2
    assert outcome("uc-2", "uc-3") == [("skipped", "human_replied")] * 2
    assert [r.chat_id for r in brain_fn.requests] == ["uc-3"] and not poster.calls


def test_check_problems_are_recorded_and_never_posted(channel):
    customer(channel, "uc-1", text=f"{CUSTOMER} 예산은 9,876원이에요")
    customer(channel, "uc-2")
    customer(channel, "uc-3", medium="app")  # 어느 앱인지 몰라 톡톡 규칙(막는 쪽)
    staff_memo = "직원끼리만 보는 합성 메모 문장입니다"
    customer(channel, "uc-4", more=[("p-4", at(2, 8, 55), "manager", staff_memo, PRIVATE)])
    customer(channel, "uc-5")  # 음성 대조 — 승인 지식의 숫자는 통과
    brain_fn = FakeBrain(result("합성 선반은 9,876원입니다."),  # 손님 글의 금액은 허용 목록이 아니다
                         result("합성 지방 운임은 4,321원입니다.", evidence_ids=("far-fee",)),  # [사람] 항목
                         result("카톡으로 사진 보내 주세요."), result(f"{staff_memo}."), result())
    poster = FakePoster()
    summary = run(channel, "memo", brain_fn=brain_fn, poster=poster)
    assert [turn(c).check_codes for c in ("uc-1", "uc-2", "uc-3", "uc-4")] == [
        ["number_not_allowed"], ["human_only_amount"], ["talktalk_outside"], ["private_memo_leak"]]
    assert outcome("uc-1", "uc-2", "uc-3", "uc-4") == [("skipped", "check_failed")] * 4
    assert turn("uc-1").masked_draft == "합성 선반은 9,876원입니다."  # 걸린 초안도 가린 사본은 남긴다(검토용)
    assert [call.chat_id for call in poster.calls] == ["uc-5"] and turn("uc-5").state == "posted"
    assert brain_fn.requests[2].medium is None and summary.skipped == {"check_failed": 4}


# ── 오류 · 돈 · 메모 결과 ────────────────────────────────────────────────


def test_mask_leak_skips_one_chat_and_not_ready_stops_the_pass(channel, caplog):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    caplog.set_level(logging.WARNING, logger=drafting.__name__)
    first = run(channel, brain_fn=FakeBrain(MaskLeak({"전화": 1, "주소": 0}), result()))
    assert outcome("uc-1", "uc-2") == [("skipped", "mask_leak"), ("stored", None)]
    assert first.skipped == {"mask_leak": 1} and not first.halted and "counts={'전화': 1}" in caplog.text  # 칸별 숫자만
    for chat in ("uc-3", "uc-4"):
        customer(channel, chat)
    second = run(channel, brain_fn=FakeBrain(brain.BrainNotReady("no_api_key")), now=at(2, 9, 15))
    # 설정 문제는 차례 탓이 아니다 — 시도를 세지 않고 돌려놓고(다음 바퀴가 같은 시도 수로 다시 집음) 멈춘다(R7-4)
    assert (outcome("uc-3"), turn("uc-3").attempts, turn("uc-4")) == ([("failed", "no_api_key")], 0, None)
    assert (second.halted, second.brain_calls, second.released) == ({"not_ready": 1}, 1, 1)


def test_brain_unavailable_fails_and_the_next_pass_reclaims(channel):
    for chat in ("uc-1", "uc-2", "uc-3"):
        customer(channel, chat)
    first = run(channel, brain_fn=FakeBrain(brain.BrainUnavailable("bad_response"), brain.BrainUnavailable("timeout")))
    assert outcome("uc-1", "uc-2") == [("failed", "bad_response"), ("failed", "timeout")]
    assert turn("uc-3") is None and first.halted == {"brain_unavailable": 1}  # 답 꼴만 틀리면 다음 상담, 그 밖엔 멈춤
    run(channel, now=at(2, 9, 15))
    assert [(turn(c).state, turn(c).attempts) for c in ("uc-1", "uc-2", "uc-3")] == [
        ("stored", 2), ("stored", 2), ("stored", 1)]


@pytest.mark.parametrize("code", ["daily_cap_reached", "api_spend_limit"])
def test_spend_cap_stops_the_day_and_a_later_day_resumes(channel, code):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    first = run(channel, brain_fn=FakeBrain(brain.SpendCapReached(code)))
    assert (first.halted, outcome("uc-1"), turn("uc-2")) == ({"spend_cap": 1}, [("failed", code)], None)
    same_day = run(channel, brain_fn=FakeBrain(max_calls=0), now=at(2, 23, 50))  # 그날은 선점도 두뇌도 없다
    assert (same_day.halted, same_day.claimed, turn("uc-2")) == ({"spend_cap": 1}, 0, None)
    next_day = run(channel, now=at(3, 9))  # 돈 상한은 차례 탓이 아니라 시도를 세지 않았다(R7-4)
    assert (next_day.stored, turn("uc-1").attempts, turn("uc-2").state) == (2, 1, "stored")


def test_a_send_failure_fails_the_turn_and_stops_the_pass(channel, caplog):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    caplog.set_level(logging.WARNING, logger="foms.services.cs_agent")
    brain_fn = FakeBrain()
    refused = FakePoster(memo.MemoResult(False, reason="send_provider_error"))
    summary = run(channel, "memo", brain_fn=brain_fn, poster=refused)
    assert (outcome("uc-1"), turn("uc-2"), len(brain_fn.requests)) == ([("failed", "send_provider_error")], None, 1)
    assert (summary.failed, summary.halted) == (1, {"memo_send_failed": 1})  # 채널톡 쓰기가 멈췄으면 두뇌 돈만 쓴다(R7-5)
    assert "못 올렸다" in caplog.text


def test_outcome_unknown_stays_posting_and_is_never_reposted(channel):
    customer(channel)
    customer(channel, "uc-2")
    summary = run(channel, "memo", poster=FakePoster(memo.MemoResult(False, reason=memo.SEND_UNKNOWN)))
    assert (turn().state, summary.unknown, summary.failed, summary.halted) == ("posting", 1, 0, {"memo_unknown": 1})
    assert turn("uc-2") is None  # 닿았는지 모르면 이번 바퀴를 멈춘다(R7-5)
    ss.store_messages(db_session, [derived("a-2", at(2, 8, 55), "manager", "합성 답입니다", chat="uc-2")],
                      source="openapi")  # 아래 바퀴는 uc-1 만 본다(uc-2 는 사람이 답함)
    db_session.commit()
    later = FakePoster()
    second = run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=later, now=at(2, 9, 15))
    third = run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=later, now=at(2, 9, 40))
    assert (second.already, second.stale_posting, third.stale_posting) == (1, 0, 1)  # 20분 넘게 남으면 세기만(복구 몫)
    assert turn().state == "posting" and not later.calls


# ── 정리 · TERM · 거름 · 상한 ────────────────────────────────────────────


def test_a_stale_claim_is_failed_then_reclaimed_but_a_fresh_one_is_left(channel):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    turns.claim_turn(db_session, "LAHOM", "uc-1", "m-uc-1", now=at(2, 8, 30))  # 두뇌를 부르다 죽은 바퀴가 남긴 줄
    turns.claim_turn(db_session, "LAHOM", "uc-2", "m-uc-2", now=at(2, 8, 55))  # 아직 20분 안
    db_session.commit()
    summary = run(channel)
    assert (summary.recovered, summary.claimed, summary.already) == (1, 1, 1)
    assert [(turn(c).state, turn(c).attempts) for c in ("uc-1", "uc-2")] == [("stored", 2), ("claimed", 1)]


def test_term_mid_call_fails_the_current_row_and_writes_nothing_else(channel):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    stop, poster = loop.StopFlag(), FakePoster()
    brain_fn = FakeBrain(on_call=lambda _request: stop.set())  # 두뇌를 부르는 동안 TERM
    with pytest.raises(loop.PassStopped):
        run(channel, "memo", brain_fn=brain_fn, poster=poster, stop=stop)
    row = turn("uc-1")
    assert (row.state, row.error_code, row.attempts, row.intent) == ("failed", "stopped", 1, None)  # LLM 답은 버렸다
    assert turn("uc-2") is None and not poster.calls and len(brain_fn.requests) == 1
    with pytest.raises(loop.PassStopped):  # 깃발이 선 채 시작한 바퀴는 아무것도 쓰지 않는다
        run(channel, "memo", stop=stop, now=at(2, 9, 15))
    assert (turn_count(), turn("uc-1").attempts) == (1, 1)
    assert run(channel, "memo", now=at(2, 9, 30)).posted == 2 and turn("uc-1").attempts == 2  # 다음 바퀴가 다시 집는다


def test_haud_email_and_photo_only_chats_never_reach_the_brain(channel):
    customer(channel, "uc-1", medium="email")
    customer(channel, "uc-h", channel_id=HAUD_CHANNEL)
    customer(channel, "uc-2", text="", extra={"files": [{"id": "f-1"}]})
    customer(channel, "uc-3")
    brain_fn = FakeBrain()
    summary = run(channel, brain_fn=brain_fn)
    assert turn("uc-h") is None and summary.candidates == 3
    assert outcome("uc-1", "uc-2", "uc-3") == [("skipped", "email"), ("skipped", "photo_only"), ("stored", None)]
    assert [r.chat_id for r in brain_fn.requests] == ["uc-3"] and "user-chats/uc-1/messages" not in channel.calls


def test_brain_call_cap_time_budget_and_the_night_flag(channel):
    for chat in ("uc-1", "uc-2", "uc-3"):
        customer(channel, chat)
    brain_fn = FakeBrain()
    capped = run(channel, brain_fn=brain_fn, now=at(2, 21), limit=1)
    assert (capped.brain_calls, capped.halted, turn("uc-2")) == (1, {"call_cap": 1}, None)
    assert brain_fn.requests[0].daytime is False  # 운영 시간 밖(라홈 평일 8~17시)
    ticks = itertools.chain([0.0, 0.0], itertools.repeat(999.0))  # 시작 · uc-2(uc-1 은 이미 — 시계 안 봄) · 그 뒤 넘김
    timed = run(channel, now=at(2, 21, 15), clock=lambda: next(ticks), budget_seconds=10)
    assert (timed.claimed, timed.halted, turn("uc-3")) == (1, {"time_budget": 1}, None)


def test_read_medium_trusts_only_known_kinds(channel):
    reader = make_reader(channel, FakeClock())
    kinds = {"uc-1": "native", "uc-2": "EMAIL", "uc-3": "app", "uc-4": "appNaverTalk", "uc-5": None, "uc-6": "합성"}
    for chat, medium in kinds.items():
        channel.chat(chat, medium=medium)
    got = [read_medium(reader, "LAHOM", chat) for chat in (*kinds, "uc-gone")]
    assert got == ["native", "email", None, "appNaverTalk", None, None, None]  # 모르면(404 포함) 톡톡 규칙 — 막는 쪽


# ── 진짜 두뇌 길 · 글이 새지 않음 ────────────────────────────────────────


def test_no_customer_text_in_logs_summary_or_tables_through_the_real_brain(channel, monkeypatch, caplog):
    monkeypatch.setenv(brain.DAILY_CAP_ENV, "5")
    caplog.set_level(logging.DEBUG, logger="foms.services.cs_agent")
    customer(channel, "uc-1")
    customer(channel, "uc-2", text=f"{CUSTOMER} 예산은 9,876원이에요")
    client = FakeAnthropic(*({"intent": "hours", "draft": draft, "evidence_ids": ["shelf-depth"], "handoff": False,
                              "handoff_reason": "none", "staff_note": NOTE}
                             for draft in (DRAFT, "합성 선반은 9,876원입니다.")))
    summary = run(channel, brain_fn=functools.partial(brain.draft_reply, client=client))
    assert (summary.stored, summary.skipped) == (1, {"check_failed": 1})
    assert CUSTOMER in json.dumps(client.params[0]["messages"], ensure_ascii=False)  # 양성 대조: 손님 글은 모델에 갔다
    assert "[CS 두뇌]" in caplog.text and "[CS 초안]" in caplog.text
    for mark in (CUSTOMER, NOTE, DRAFT, "9,876"):
        assert mark not in caplog.text and mark not in json.dumps(summary.counts(), ensure_ascii=False)
    cells = [str(value) for table in (CsAgentTurn.__table__, SystemSetting.__table__)
             for row in db_session.execute(select(table)).mappings() for value in row.values()]
    assert not [cell for cell in cells if CUSTOMER in cell or NOTE in cell]
    assert db_session.get(SystemSetting, brain.SPEND_KEY).setting_value["calls"] == 2  # 진짜 두뇌 길(돈 셈)을 지났다


# ── 감시 루프 고리 ──────────────────────────────────────────────────────


def loop_pass(channel, now=NOW):
    return loop.run_pass(db_session, config=loop.LoopConfig(), stop=loop.StopFlag(),
                         reader=make_reader(channel, FakeClock()), now=now, clock=lambda: 0.0,
                         is_business_day=weekdays_only)


def set_switch(value):
    db_session.merge(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value=value))
    db_session.commit()


def test_loop_with_the_draft_switch_off_is_the_old_pass(channel, monkeypatch):
    customer(channel)
    monkeypatch.setattr(loop, "run_drafting", lambda *a, **k: pytest.fail("초안 스위치가 꺼졌는데 초안을 돌렸다"))
    old_keys = {"outcome", "ingested", "reconciled", "checks", "needs_reply", "alerts", "report_sent"}
    switches = ((0, None), (15, {"loop": "on"}), (30, {"loop": "on", "draft": "off"}), (45, {"draft": "of"}))
    for minute, switch in switches:  # 줄 없음 · 칸 없음 · off · 오타 — 모두 예전 바퀴
        if switch is not None:
            set_switch(switch)
        result = loop_pass(channel, at(2, 9, minute))
        assert (result.outcome, result.drafting, set(result.summary()), result.summary()["needs_reply"]) == (
            "ok", None, old_keys, 1)
    assert turn_count() == 0 and set(channel.calls) == {"user-chats"}  # 보정 목록만 — 초안 읽기 0


def test_loop_runs_drafting_after_the_report_when_the_switch_is_on(channel, monkeypatch):
    customer(channel)
    set_switch({"loop": "on", "draft": "store"})
    brain_fn = FakeBrain()
    wired = functools.partial(drafting.run_drafting, brain=brain_fn, poster=FakePoster())
    monkeypatch.setattr(loop, "run_drafting", wired)
    result = loop_pass(channel)
    expected = {**drafting.DraftSummary().counts(), "candidates": 1, "claimed": 1, "brain_calls": 1, "stored": 1,
                "cache_cold": 1}  # 월요일 9시(운영 시간)인데 가짜 결과의 캐시 읽기가 0(R7-12)
    assert (result.outcome, result.report_sent, result.summary()["drafting"]) == ("ok", True, expected)
    assert turn().state == "stored" and brain_fn.requests[0].daytime is True
    assert json.loads(json.dumps(result.summary()))["drafting"] == expected  # JSON 한 줄 — 숫자만
