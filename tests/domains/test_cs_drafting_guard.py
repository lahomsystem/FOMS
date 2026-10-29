"""초안 차례 막는 장치(검수 R7) — 공개 메모면 스위치 끔 · 확인 못 함이면 저장만 · 관리자 알림, 두뇌 준비가 안 됐으면 줄 0,
401 · 403 · 준비 안 됨은 시도를 세지 않음, 보내기 실패는 저장된 초안으로 다시 올림(두뇌 안 부름), 줄이 그사이 바뀌면 안 올림,
루프 읽기 도우미 넘김, 캐시 표시를 실은 요청의 캐시 읽기 0 세기 · 대체 모델 기록.

가짜만 쓴다(두뇌 · 메모 감싸개 · 채널톡) — 네트워크 · 진짜 키 없음. 손으로 꾸민 합성 글만. 재료 · 가짜는 ``test_cs_drafting``
과 같다(그 모듈의 fixture 를 그대로 쓴다). 시각은 2026-11 KST(11-02 월요일).
"""

from __future__ import annotations

import contextlib
import copy
import functools
import logging

import anthropic
import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.cs_agent import brain, drafting, drafting_post, loop, memo, turns
from foms.services.cs_agent import state_store as ss
from foms.services.cs_agent.drafting_read import MEMO_DRAFT_HEAD, MEMO_HEAD, MEMO_NOTE_HEAD
from foms.services.cs_agent.knowledge import knowledge_key
from models import CsAgentTurn, Notification, NotificationUserState, SystemSetting, User
from tests.domains.test_cs_drafting import (  # noqa: F401 — channel · keys 는 fixture
    CUSTOMER, DRAFT, KNOWLEDGE, FakeBrain, FakePoster, channel, customer, keys, loop_pass, outcome, result, run,
    set_switch, turn, turn_count,
)
from tests.support.cs_agent_fakes import FakeAnthropic, FakeClock, api_message, at, make_reader, weekdays_only

_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def admin():
    user = User(username="cs_guard_admin", password=generate_password_hash("pw"), name="합성관리자", role="ADMIN",
                is_active=True)
    db_session.add(user)
    db_session.commit()
    return int(user.id)


def notes(kind):
    return db_session.query(Notification).filter_by(notification_type=kind).all()


def switch_value():
    return db_session.get(SystemSetting, turns.SWITCH_KEY, populate_existing=True).setting_value


@contextlib.contextmanager
def debug_on(name):
    log = logging.getLogger(name)
    old = log.level
    log.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        log.setLevel(old)


# ── R7-1 · R7-2 메모 막는 장치 ──────────────────────────────────────────


def test_a_public_memo_turns_drafting_off_alerts_admins_and_the_next_pass_posts_nothing(channel, monkeypatch):
    admin_id = admin()
    set_switch({"loop": "on", "draft": "memo", "changed_at": "2026-11-01T00:00:00"})
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    public = memo.MemoResult(True, message_id="memo-1", reason=memo.REASON_NOT_PRIVATE)
    summary = run(channel, "memo", poster=FakePoster(public))
    assert (summary.halted, summary.posted, summary.unverified, turn("uc-2")) == ({"memo_not_private": 1}, 1, 1, None)
    assert outcome("uc-1") == [("posted", "memo_not_private")]
    value = switch_value()  # 초안 칸만 끔 — 루프 칸 · 바꾼 때는 그대로(loop.set_switch 와 같은 꼴)
    assert (value["draft"], value["loop"], value["changed_at"], value["draft_reason"]) == (
        "off", "on", "2026-11-01T00:00:00", "memo_not_private")
    (note,) = notes(drafting_post.NOTIFY_MEMO_PUBLIC)
    assert (note.target_type, note.target_role, note.is_urgent) == ("ROLE", "ADMIN", False)
    assert "uc-1" in note.message and "memo-1" in note.message and CUSTOMER not in note.title + note.message
    assert {s.user_id for s in db_session.query(NotificationUserState).filter_by(notification_id=note.id)} == {admin_id}
    later = FakePoster(public)  # 15분 뒤 바퀴 — 감시 루프가 스위치를 새로 읽고 초안을 돌리지 않는다
    monkeypatch.setattr(loop, "run_drafting", functools.partial(drafting.run_drafting, brain=FakeBrain(), poster=later))
    result = loop_pass(channel, at(2, 9, 15))
    assert (result.drafting, later.calls, turn("uc-2")) == (None, [], None)


@pytest.mark.parametrize("reason", [memo.REASON_NOT_FOUND, memo.REASON_READ_FAILED, memo.REASON_NO_MESSAGE_ID])
def test_an_unverified_memo_drops_to_store_alerts_and_stops(channel, reason):
    admin()
    set_switch({"loop": "on", "draft": "memo"})
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    message_id = None if reason == memo.REASON_NO_MESSAGE_ID else "memo-1"
    summary = run(channel, "memo", poster=FakePoster(memo.MemoResult(True, message_id=message_id, reason=reason)))
    assert (summary.halted, outcome("uc-1"), turn("uc-2")) == ({"memo_unverified": 1}, [("posted", reason)], None)
    assert (turns.draft_mode(db_session), switch_value()["loop"]) == ("store", "on")  # 끄지 않고 저장만으로
    (note,) = notes(drafting_post.NOTIFY_MEMO_UNVERIFIED)
    assert "Open API" in note.message and not notes(drafting_post.NOTIFY_MEMO_PUBLIC)


def test_a_switch_turned_off_mid_pass_stops_memos_right_away(channel):
    set_switch({"loop": "on", "draft": "memo"})
    customer(channel)
    poster = FakePoster()  # 두뇌를 부르는 사이 사람(또는 막는 장치)이 끈다 — 메모 직전에 스위치를 다시 읽는다
    summary = run(channel, "memo", brain_fn=FakeBrain(on_call=lambda _r: set_switch({"loop": "on", "draft": "off"})),
                  poster=poster)
    assert (poster.calls, summary.stored, turn().state) == ([], 1, "stored")


def test_the_switch_is_still_turned_off_when_the_posted_row_cannot_be_recorded(channel, monkeypatch):
    set_switch({"loop": "on", "draft": "memo"})
    customer(channel)

    def lost(*_args, **_kwargs):
        raise turns.TurnConflict("합성 — 그사이 바뀜")

    monkeypatch.setattr(drafting_post, "mark_posted", lost)
    summary = run(channel, "memo", poster=FakePoster(memo.MemoResult(True, message_id="memo-1",
                                                                      reason=memo.REASON_NOT_PRIVATE)))
    assert (summary.halted, turns.draft_mode(db_session), turn().state) == ({"memo_not_private": 1}, "off", "posting")


# ── R7-4 준비 · 시도를 세지 않음 ─────────────────────────────────────────


@pytest.mark.parametrize("broken", ["key", "cap", "knowledge", "debug", "spent"])
def test_an_unready_brain_stops_the_pass_before_any_row(channel, monkeypatch, broken):
    customer(channel)
    if broken == "key":
        monkeypatch.delenv(brain.KEY_ENV)
    elif broken == "cap":
        monkeypatch.delenv(brain.DAILY_CAP_ENV)
    elif broken == "knowledge":
        db_session.delete(db_session.get(SystemSetting, knowledge_key("LAHOM")))
        db_session.commit()
    elif broken == "spent":
        db_session.add(SystemSetting(setting_key=brain.SPEND_KEY, setting_value={
            "date": "2026-11-02", "usd": "4.5", "reserved": "0.5", "calls": 3}))  # 예약까지 세면 상한(5)
        db_session.commit()
    with debug_on("anthropic._base_client") if broken == "debug" else contextlib.nullcontext():
        summary = run(channel, brain_fn=FakeBrain(max_calls=0))
    halt = "spend_cap" if broken == "spent" else "not_ready"
    assert (summary.halted, summary.claimed, turn_count(), channel.calls) == ({halt: 1}, 0, 0, [])


@pytest.mark.parametrize("status,cls", [(401, anthropic.AuthenticationError), (403, anthropic.PermissionDeniedError)])
def test_a_rejected_key_releases_the_turn_without_spending_an_attempt(channel, status, cls):
    for chat in ("uc-1", "uc-2"):
        customer(channel, chat)
    body = {"type": "error", "error": {"type": "authentication_error", "message": "합성 거절"}}
    rejected = cls("합성", response=httpx2.Response(status, request=_REQUEST), body=body)
    summary = run(channel, brain_fn=functools.partial(brain.draft_reply, client=FakeAnthropic(rejected)))
    assert (summary.halted, summary.released, summary.failed) == ({"not_ready": 1}, 1, 0)
    assert (outcome("uc-1"), turn("uc-1").attempts, turn("uc-2")) == ([("failed", "api_auth")], 0, None)
    for minute in (15, 30, 45):  # 키를 고치기 전 바퀴가 이어져도 차례는 시도 상한에 닿지 않는다
        run(channel, brain_fn=FakeBrain(brain.BrainNotReady("api_auth")), now=at(2, 9, minute))
    assert (turn("uc-1").state, turn("uc-1").attempts) == ("failed", 0)
    fixed = run(channel, now=at(2, 10))
    assert (fixed.stored, turn("uc-1").attempts, turn("uc-2").state) == (2, 1, "stored")


# ── R7-5 보내기 실패는 저장된 초안으로 ───────────────────────────────────


def test_a_send_failure_is_reposted_from_the_stored_draft_without_the_brain(channel):
    customer(channel)
    run(channel, "memo", poster=FakePoster(memo.MemoResult(False, reason="send_provider_error")))
    assert (outcome("uc-1"), turn().masked_draft) == ([("failed", "send_provider_error")], DRAFT)
    poster = FakePoster()
    summary = run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=poster, now=at(2, 9, 15))
    (call,) = poster.calls  # 두뇌를 다시 부르지 않았다 — 저장된 초안을 다시 검사 · 다시 읽어 올렸다
    assert call.text.split("\n") == [MEMO_HEAD, MEMO_DRAFT_HEAD, DRAFT, MEMO_NOTE_HEAD, drafting.REPOST_NOTE]
    assert (turn().state, turn().attempts, summary.reposted, summary.brain_calls) == ("posted", 2, 1, 0)


def test_a_repost_still_rechecks_and_rereads(channel):
    failing = FakePoster(memo.MemoResult(False, reason="send_provider_error"))
    customer(channel, "uc-2")
    run(channel, "memo", poster=failing)  # uc-2 보내기 실패 → 멈춤
    customer(channel, "uc-1")
    run(channel, "memo", poster=FakePoster(memo.MemoResult(False, reason="send_provider_error")), now=at(2, 9, 5))
    assert [(turn(c).state, turn(c).attempts) for c in ("uc-1", "uc-2")] == [("failed", 1), ("failed", 1)]
    channel.messages["uc-1"].append(api_message("m-new", at(2, 8, 58), "user", "합성 추가 문의"))  # 그사이 손님이 더 씀
    changed = copy.deepcopy(KNOWLEDGE)  # 지식이 바뀌어 초안 속 숫자가 더는 승인 값이 아니다
    changed["items"][1]["text"] = "합성 선반 깊이는 담당자가 안내합니다"
    db_session.get(SystemSetting, knowledge_key("LAHOM")).setting_value = changed
    db_session.commit()
    poster = FakePoster()
    summary = run(channel, "memo", brain_fn=FakeBrain(max_calls=0), poster=poster, now=at(2, 9, 30))
    assert outcome("uc-1", "uc-2") == [("skipped", "stale"), ("skipped", "check_failed")]
    assert (turn("uc-2").check_codes, poster.calls, summary.brain_calls) == (["number_not_allowed"], [], 0)


# ── R7-8 줄이 그사이 바뀌면 안 올린다 ────────────────────────────────────


def test_a_turn_taken_by_another_pass_during_the_call_is_never_posted(channel):
    customer(channel)
    other = Session(bind=engine)  # 겹친 두 번째 바퀴(대표 잠금이 끊긴 때) — 정리하고 다시 집는다

    def overlap(_request):
        theirs = other.scalars(select(CsAgentTurn)).one()
        turns.mark_failed(theirs, error_code="claim_expired", now=at(2, 9, 30))
        other.commit()
        assert turns.claim_turn(other, "LAHOM", "uc-1", "m-uc-1", now=at(2, 9, 30)) is not None
        other.commit()

    poster = FakePoster()
    try:
        summary = run(channel, "memo", brain_fn=FakeBrain(on_call=overlap), poster=poster)
    finally:
        other.close()
    assert (summary.halted, poster.calls) == ({"turn_conflict": 1}, [])
    assert (turn().state, turn().attempts, turn().intent) == ("claimed", 2, None)  # 남의 줄은 손대지 않았다


# ── R7-11 · R7-12 ────────────────────────────────────────────────────────


def test_the_memo_check_uses_the_loops_reader(channel):
    customer(channel)
    set_switch({"draft": "memo"})
    reader, poster = make_reader(channel, FakeClock()), FakePoster()
    found = ss.compute_open_states(db_session, now=at(2, 9), brands=("LAHOM",), is_business_day=weekdays_only)
    drafting.run_drafting(db_session, states=found, reader=reader, now=at(2, 9), stop=loop.StopFlag(), mode="memo",
                          is_business_day=weekdays_only, brain=FakeBrain(), poster=poster)
    assert poster.calls[0].kwargs["reader"] is reader  # 다시 읽기의 기다림도 TERM 을 본다


def test_marked_cache_misses_are_counted_and_warned_once_and_fallbacks_recorded(channel, caplog):
    for chat in ("uc-1", "uc-2", "uc-3"):
        customer(channel, chat)
    caplog.set_level(logging.WARNING, logger=drafting.__name__)
    day = run(channel, brain_fn=FakeBrain(result(cache_read_tokens=0), result(cache_read_tokens=0, fallback_used=True),
                                          result(cache_read_tokens=900)))
    assert (day.cache_cold, caplog.text.count("캐시 읽기 0")) == (2, 1)
    assert [turn(c).fallback_used for c in ("uc-1", "uc-2", "uc-3")] == [False, True, False]
    customer(channel, "uc-4")
    unmarked = FakeBrain(result(cache_read_tokens=0, cache_marked=False))  # 밤엔 캐시 표시가 없다(처음 방침)
    night = run(channel, brain_fn=unmarked, now=at(2, 21))
    assert (night.stored, night.cache_cold) == (1, 0)
