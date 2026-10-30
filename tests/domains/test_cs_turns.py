"""초안 차례 기록(플랜 C3-3 · C3-1 중복 방지) — 선점 · 상태 · 시도 상한 · '올리는 중' 복구 재료 · 가린 글만 · 초안 스위치.

완료 기준(브리프): 두 번 선점해도 한 줄 · 상태 바꾸기 · 시도 상한 3 · 오래 남은 '올리는 중' 찾기 · 받은 가린 칸 말고는
손님 글이 안 남는다 · 초안 스위치(줄 · 칸이 없거나 비었거나 꼴이 틀리면 off, ``loop`` 칸은 그대로). 진짜 PostgreSQL 에서
두 세션이 겹치는 선점은 ``tests/postgres/test_cs_turns_pg.py``. 손으로 꾸민 합성 글만(전화 꼴 숫자 없음).
"""

from __future__ import annotations

import datetime
import enum
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import db_session, engine
from foms.services.cs_agent import loop, turns, turns_fields
from foms.services.cs_agent.checks import Problem
from foms.services.cs_agent.masking import MaskLeak
from models import CsAgentTurn, SystemSetting
from tests.support.cs_agent_fakes import at, naive

#: 두뇌 결과의 글 칸 표지 — 표 어디에도 남으면 안 된다.
BRAIN_MARK = "보라고래초안표지"
#: 부르는 쪽이 넘긴 가린 초안의 표지 — ``masked_draft`` 에만 있어야 한다.
DRAFT_MARK = "푸른고래가린표지"
ADDRESS = "가상로 12"
NOW = at(2, 9)


def claim(chat="uc-1", message="m-1", now=NOW, brand="LAHOM"):
    row = turns.claim_turn(db_session, brand, chat, message, now=now)
    db_session.commit()
    return row


def count():
    return db_session.scalar(select(func.count()).select_from(CsAgentTurn.__table__))


def brain_result(**overrides):
    values = dict(intent="quote", handoff=False, handoff_reason=None, model="claude-opus-5-5", effort="high",
                  input_tokens=1200, output_tokens=300, cache_read_tokens=1000, cache_write_tokens=0,
                  cost_usd=0.0123, latency_ms=4321, draft=f"{BRAIN_MARK} 합성 초안", staff_note=f"{BRAIN_MARK} 참고",
                  raw={"text": BRAIN_MARK}, fallback_used=True)
    values.update(overrides)
    return SimpleNamespace(**values)


def set_switch_value(value):
    row = db_session.get(SystemSetting, turns.SWITCH_KEY)
    if row is None:
        db_session.add(SystemSetting(setting_key=turns.SWITCH_KEY, setting_value=value))
    else:
        row.setting_value = value
    db_session.commit()


# ── 선점 ─────────────────────────────────────────────────────────────────


def test_a_second_claim_of_the_same_turn_gets_nothing(app):
    first = claim()
    assert (first.state, first.attempts, first.brand, first.chat_id, first.last_user_message_id) == (
        "claimed", 1, "LAHOM", "uc-1", "m-1")
    assert first.created_at == first.updated_at == naive(NOW)
    assert claim(now=at(2, 9, 1)) is None and claim(now=at(2, 9, 2)) is None
    assert count() == 1
    assert claim(message="m-2").id != first.id and claim(chat="uc-2").id != first.id  # 음성 대조군: 다른 차례는 새 줄
    assert count() == 3


def test_the_unique_turn_is_enforced_by_the_database(app):
    db_session.add(CsAgentTurn(brand="LAHOM", chat_id="uc-1", last_user_message_id="m-1", state="claimed"))
    db_session.commit()
    db_session.add(CsAgentTurn(brand="LAHOM", chat_id="uc-1", last_user_message_id="m-1", state="claimed"))
    with pytest.raises(IntegrityError):  # 선점 함수를 거치지 않아도 둘째 줄은 DB 가 막는다
        db_session.commit()
    db_session.rollback()
    db_session.add(CsAgentTurn(brand="LAHOM", chat_id="uc-1", last_user_message_id="m-9", state="bogus"))
    with pytest.raises(IntegrityError):  # 상태는 여섯 가지만
        db_session.commit()
    db_session.rollback()
    assert count() == 1


def test_claim_refuses_bad_input_without_writing(app):
    for args in (("XYZ", "uc-1", "m-1"), ("LAHOM", "합성 상담", "m-1"), ("LAHOM", "uc-1", "m 1"),
                 ("LAHOM", "", "m-1"), ("LAHOM", "uc-1", "x" * 65)):
        with pytest.raises(ValueError):
            turns.claim_turn(db_session, *args, now=NOW)
    with pytest.raises(ValueError):
        turns.claim_turn(db_session, "LAHOM", "uc-1", "m-1", now=datetime.datetime(2026, 11, 2, 9))  # 시간대 없음
    db_session.commit()
    assert count() == 0


# ── 상태 ─────────────────────────────────────────────────────────────────


def test_the_memo_path_moves_claimed_posting_posted(app):
    row = claim()
    turns.record_brain_result(row, brain_result())
    turns.mark_posting(row, masked_draft="합성 초안입니다", check_codes=[], now=at(2, 9, 1))
    db_session.commit()  # '올리는 중'을 커밋한 뒤에 채널톡을 부른다
    assert (row.state, row.updated_at, row.masked_draft, row.check_codes) == (
        "posting", naive(at(2, 9, 1)), "합성 초안입니다", [])
    turns.mark_posted(row, memo_message_id="memo-1", now=at(2, 9, 2))
    db_session.commit()
    assert (row.state, row.memo_message_id, row.error_code) == ("posted", "memo-1", None)
    for illegal in (lambda: turns.mark_posting(row, masked_draft=None, now=NOW),
                    lambda: turns.mark_posted(row, memo_message_id="memo-2", now=NOW),
                    lambda: turns.mark_stored(row, masked_draft=None, now=NOW),
                    lambda: turns.mark_skipped(row, reason="human_replied", now=NOW),
                    lambda: turns.mark_failed(row, error_code="send_provider_error", now=NOW),
                    lambda: turns.record_brain_result(row, brain_result())):
        with pytest.raises(turns.TurnStateError):
            illegal()
        assert (row.state, row.memo_message_id, row.updated_at) == ("posted", "memo-1", naive(at(2, 9, 2)))
    db_session.commit()
    db_session.expire_all()
    assert (row.state, row.memo_message_id, row.updated_at, row.intent) == (
        "posted", "memo-1", naive(at(2, 9, 2)), "quote")


def test_store_skip_and_unverified_posts(app):
    stored = claim(message="m-1")
    turns.mark_stored(stored, masked_draft="합성 초안", check_codes=["tone_emoji"], now=NOW)
    skipped = claim(message="m-2")
    turns.mark_skipped(skipped, reason="human_replied", check_codes=[Problem("date_promise", "날짜 확답")], now=NOW)
    posted = claim(message="m-3")
    turns.mark_posting(posted, masked_draft=None, now=NOW)
    turns.mark_posted(posted, memo_message_id=None, error_code="memo_not_found", now=NOW)
    db_session.commit()
    db_session.expire_all()
    assert (stored.state, stored.masked_draft, stored.check_codes) == ("stored", "합성 초안", ["tone_emoji"])
    assert (skipped.state, skipped.error_code, skipped.check_codes, skipped.masked_draft) == (
        "skipped", "human_replied", ["date_promise"], None)
    assert (posted.state, posted.memo_message_id, posted.error_code) == ("posted", None, "memo_not_found")
    row = claim(message="m-4")
    for bad in ("사람 답함", "", None, "x" * 49):
        with pytest.raises(ValueError):
            turns.mark_skipped(row, reason=bad, now=NOW)
    for codes in (["Date Promise"], ["날짜확답"], [Problem("", "")]):
        with pytest.raises(ValueError):
            turns.mark_stored(row, masked_draft=None, check_codes=codes, now=NOW)
    with pytest.raises(TypeError):
        turns.mark_stored(row, masked_draft=None, check_codes="tone_emoji", now=NOW)
    assert (row.state, row.error_code, row.check_codes) == ("claimed", None, None)  # 걸리면 아무것도 안 바뀐다


def test_a_failed_turn_is_reclaimed_until_the_attempt_cap(app):
    row = claim()
    retry = []
    for attempt in (1, 2, 3):
        assert (row.state, row.attempts, row.error_code) == ("claimed", attempt, None)
        retry.append(turns.mark_failed(row, error_code="send_provider_error", now=at(2, 9, attempt)))
        db_session.commit()
        again = claim(now=at(2, 9, attempt))
        if attempt < 3:
            assert again is not None and again.id == row.id  # 같은 줄을 다시 집는다
            row = again
        else:
            assert again is None
    assert retry == [True, True, False]
    db_session.expire_all()
    final = db_session.get(CsAgentTurn, row.id)
    assert (final.state, final.attempts, final.error_code, count()) == ("failed", 3, "send_provider_error", 1)


def test_only_failed_turns_are_reclaimed(app):
    posting = claim(message="m-1")
    turns.mark_posting(posting, masked_draft=None, now=NOW)
    for message, mark in (("m-2", lambda r: turns.mark_stored(r, masked_draft=None, now=NOW)),
                          ("m-3", lambda r: turns.mark_skipped(r, reason="handoff", now=NOW))):
        mark(claim(message=message))
    db_session.commit()
    # '올리는 중'(올라갔는지 모름) · 끝난 줄 · 아직 일하는 줄은 다시 집지 않는다 — 메모가 둘이 될 수 있다.
    assert [claim(message=m) for m in ("m-1", "m-2", "m-3")] == [None, None, None]
    assert claim(message="m-4") is not None and claim(message="m-4") is None
    assert count() == 4


def test_stale_posting_finds_only_old_posting_rows_oldest_first(app):
    rows = {}
    for message, minute, final in (("m-old", 0, None), ("m-new", 10, None), ("m-done", 0, "posted")):
        rows[message] = claim(message=message, now=at(2, 9, minute))
        turns.mark_posting(rows[message], masked_draft=None, now=at(2, 9, minute))
        if final:
            turns.mark_posted(rows[message], memo_message_id="memo-1", now=at(2, 9, minute))
    claim(message="m-claimed", now=at(2, 9))
    db_session.commit()
    ids = lambda found: [r.last_user_message_id for r in found]  # noqa: E731
    assert ids(turns.stale_posting(db_session, at(2, 9, 5))) == ["m-old"]
    assert ids(turns.stale_posting(db_session, at(2, 9, 20))) == ["m-old", "m-new"]
    assert ids(turns.stale_posting(db_session, at(2, 9, 20), limit=1)) == ["m-old"]
    assert turns.stale_posting(db_session, at(2, 8)) == []
    # 복구: 우리 봇 메모를 찾으면 '올림', 없으면 '실패'(다시 집을 수 있음).
    found, lost = turns.stale_posting(db_session, at(2, 9, 20))
    turns.mark_posted(found, memo_message_id="memo-7", now=at(2, 9, 21))
    assert turns.mark_failed(lost, error_code="posting_lost", now=at(2, 9, 21)) is True
    db_session.commit()
    assert turns.stale_posting(db_session, at(2, 10)) == []
    assert claim(message="m-new", now=at(2, 9, 22)).attempts == 2


# ── 두뇌 결과 · 가린 글만 ─────────────────────────────────────────────────


def test_brain_results_copy_codes_and_numbers_only(app, caplog):
    class Intent(enum.Enum):
        QUOTE = "견적"

    row = claim()
    turns.record_brain_result(row, brain_result(intent=Intent.QUOTE, handoff=True, handoff_reason="refund_rule",
                                                cache_read_tokens=None, cache_read_input_tokens=900,
                                                cache_write_tokens=None, cache_creation_input_tokens=40,
                                                latency_ms=4321.6))
    db_session.commit()
    db_session.expire_all()
    assert (row.intent, row.handoff, row.handoff_reason, row.model, row.effort, row.fallback_used) == (
        "견적", True, "refund_rule", "claude-opus-5-5", "high", True)  # 대체 모델이 답했는지도 남긴다(R7-12)
    assert (row.input_tokens, row.output_tokens, row.cache_read_tokens, row.cache_write_tokens, row.latency_ms) == (
        1200, 300, 900, 40, 4322)
    assert row.cost_usd == Decimal("0.0123")
    caplog.set_level(logging.WARNING, logger=turns.__name__)
    other = claim(message="m-2")
    turns.record_brain_result(other, brain_result(intent="합성 의도 글", handoff="yes", handoff_reason="x" * 65,
                                                  input_tokens=-1, output_tokens=True, cost_usd=float("nan"),
                                                  latency_ms="빠름"))
    assert (other.intent, other.handoff, other.handoff_reason, other.input_tokens, other.output_tokens,
            other.cost_usd, other.latency_ms) == (None, None, None, None, None, None, None)
    assert "합성 의도 글" not in caplog.text and "field=intent" in caplog.text
    empty = claim(message="m-3")
    turns.record_brain_result(empty, object())  # 속성이 없으면 비운다
    assert (empty.intent, empty.model, empty.input_tokens, empty.cost_usd) == (None, None, None, None)


def test_no_customer_text_is_stored_except_the_masked_fields(app):
    row = claim()
    turns.record_brain_result(row, brain_result())
    turns.mark_posting(row, masked_draft=f"{DRAFT_MARK} 주소: 합성시 {ADDRESS} 합성빌라 앞입니다", now=NOW)
    turns.mark_posted(row, memo_message_id="memo-1", now=NOW)
    turns.record_staff_reply(row, f"합성 답 {ADDRESS} 로 오세요", judgment="same_meaning", now=at(2, 9, 30))
    db_session.commit()
    stored = db_session.execute(select(CsAgentTurn.__table__)).mappings().all()
    assert len(stored) == 1
    cells = {key: str(value) for key, value in stored[0].items() if value is not None}
    assert not [key for key, value in cells.items() if BRAIN_MARK in value]  # 두뇌 글 칸은 어디에도 없다
    assert [key for key, value in cells.items() if DRAFT_MARK in value] == ["masked_draft"]
    assert not [key for key, value in cells.items() if ADDRESS in value]  # 받은 글도 한 번 더 가렸다
    assert "[주소]" in cells["masked_draft"] and "[도로명주소]" in cells["staff_reply_masked"]
    assert cells["judgment"] == "same_meaning"


def test_text_that_fails_the_mask_check_is_refused_and_nothing_changes(app, monkeypatch):
    row = claim()
    monkeypatch.setattr(turns_fields, "mask", lambda text: text)  # 가림이 구멍 난 때 — 검사가 마지막 문이다(칸 꼴 모듈)
    for store in (lambda: turns.mark_posting(row, masked_draft=f"{ADDRESS} 앞입니다", now=at(2, 9, 5)),
                  lambda: turns.mark_stored(row, masked_draft=f"{ADDRESS} 앞입니다", now=at(2, 9, 5))):
        with pytest.raises(MaskLeak) as caught:
            store()
        assert ADDRESS not in str(caught.value) and caught.value.counts == {"도로": 1}
    assert (row.state, row.masked_draft, row.updated_at) == ("claimed", None, naive(NOW))
    turns.mark_stored(row, masked_draft=None, now=NOW)
    with pytest.raises(MaskLeak):
        turns.record_staff_reply(row, f"합성 답 {ADDRESS}", now=NOW)
    assert row.staff_reply_masked is None
    with pytest.raises(turns.TurnStateError):  # 직원 답은 끝난 줄에만
        turns.record_staff_reply(claim(message="m-2"), "합성 답", now=NOW)


# ── 초안 스위치 ──────────────────────────────────────────────────────────


def test_draft_mode_fails_closed(app, caplog):
    assert turns.draft_mode(db_session) == "off"  # 줄이 없다
    caplog.set_level(logging.WARNING, logger=turns.__name__)
    set_switch_value({"loop": "on"})
    assert turns.draft_mode(db_session) == "off" and not caplog.records  # 칸이 없는 것은 꼴이 틀린 것이 아니다
    for broken in (None, "memo", ["memo"], {"draft": "MEMO"}, {"draft": " memo"}, {"draft": "memo "},
                   {"draft": "on"}, {"draft": 1}, {"draft": True}, {"draft": None}, {"draft": ["memo"]}):
        set_switch_value(broken)
        assert turns.draft_mode(db_session) == "off", broken
    assert len(caplog.records) == 11
    for mode in ("off", "store", "memo"):
        set_switch_value({"loop": "on", "draft": mode})
        assert turns.draft_mode(db_session) == mode


def test_the_draft_key_leaves_the_loop_switch_alone(app):
    assert turns.SWITCH_KEY == loop.SWITCH_KEY
    set_switch_value({"draft": "memo"})
    assert loop.read_switch(db_session) is True and turns.draft_mode(db_session) == "memo"  # loop 칸 없음 = 돈다
    set_switch_value({"loop": "off", "draft": "store"})
    assert loop.read_switch(db_session) is False and turns.draft_mode(db_session) == "store"
    loop.set_switch(db_session, on=True)  # 루프 스위치를 써도 draft 칸은 남는다
    assert loop.read_switch(db_session) is True and turns.draft_mode(db_session) == "store"
    loop.set_switch(db_session, on=False)
    assert loop.read_switch(db_session) is False and turns.draft_mode(db_session) == "store"
    set_switch_value({"loop": "on", "draft": "of"})  # draft 오타는 draft 만 끈다
    assert loop.read_switch(db_session) is True and turns.draft_mode(db_session) == "off"


def test_draft_mode_reads_the_row_fresh_every_time(app):
    set_switch_value({"draft": "memo"})
    assert turns.draft_mode(db_session) == "memo"
    table = SystemSetting.__table__
    db_session.execute(update(table).where(table.c.setting_key == turns.SWITCH_KEY)
                       .values(setting_value={"draft": "off"}))  # 다른 길(관리자 스크립트)이 끈다 — 커밋 전
    assert turns.draft_mode(db_session) == "off"
    db_session.rollback()


# ── 조건부 쓰기 · 시도를 세지 않는 돌려놓기 · 스위치 쓰기(검수 R7) ────────


def test_a_stale_object_never_writes_over_a_turn_another_pass_took(app):
    row = claim()  # 이 세션의 선점(시도 1) — 커밋 뒤 줄을 다시 읽어도 선점 표지는 남는다
    other = Session(bind=engine)  # 겹친 다른 바퀴: 오래된 선점 정리 → 다시 집기(시도 2)
    try:
        turns.mark_failed(other.get(CsAgentTurn, row.id), error_code="claim_expired", now=at(2, 9, 30))
        other.commit()
        assert turns.claim_turn(other, "LAHOM", "uc-1", "m-1", now=at(2, 9, 30)).attempts == 2
        other.commit()
    finally:
        other.close()
    writes = (lambda: turns.mark_posting(row, masked_draft="합성 초안", now=at(2, 9, 31)),
              lambda: turns.mark_stored(row, masked_draft="합성 초안", now=at(2, 9, 31)),
              lambda: turns.mark_skipped(row, reason="stale", now=at(2, 9, 31)),
              lambda: turns.mark_failed(row, error_code="error", now=at(2, 9, 31)),
              lambda: turns.release_turn(row, error_code="api_auth", now=at(2, 9, 31)),
              lambda: turns.record_brain_result(row, brain_result()))
    for write in writes:  # 다시 읽은 줄은 'claimed' 지만 시도 수가 다르다 — 바뀐 줄 0 → 쓰지 않는다
        with pytest.raises(turns.TurnConflict):
            write()
        db_session.rollback()
    db_session.expire_all()
    final = db_session.get(CsAgentTurn, row.id)
    assert (final.state, final.attempts, final.masked_draft, final.intent) == ("claimed", 2, None, None)
    db_session.execute(update(CsAgentTurn.__table__).values(state="failed"))  # 정리만 하고 다시 집지 않은 때(시도 그대로)
    db_session.commit()
    with pytest.raises(turns.TurnStateError):  # 다시 읽은 상태가 'failed' — 올리기로 가지 않는다
        turns.mark_posting(row, masked_draft="합성 초안", now=at(2, 9, 32))


def test_release_puts_a_turn_back_without_spending_an_attempt(app):
    row = claim()
    for minute in (1, 2, 3, 4):  # 키 · 설정 문제가 이어져도 차례는 시도 상한에 닿지 않는다
        turns.release_turn(row, error_code="api_auth", now=at(2, 9, minute))
        db_session.commit()
        assert (row.state, row.attempts, row.error_code) == ("failed", 0, "api_auth")
        row = claim(now=at(2, 9, minute))
        assert (row.state, row.attempts, row.error_code) == ("claimed", 1, None)
    turns.mark_stored(row, masked_draft=None, now=NOW)
    with pytest.raises(turns.TurnStateError):  # 선점한 줄만 돌려놓는다
        turns.release_turn(row, error_code="api_auth", now=NOW)
    assert count() == 1


def test_set_draft_mode_changes_only_the_draft_field(app):
    loop.set_switch(db_session, on=True, now=at(2, 8))
    before = dict(db_session.get(SystemSetting, turns.SWITCH_KEY).setting_value)
    version = db_session.get(SystemSetting, turns.SWITCH_KEY).version
    turns.set_draft_mode(db_session, "off", reason="memo_not_private", now=at(2, 9, 5))
    db_session.commit()
    row = db_session.get(SystemSetting, turns.SWITCH_KEY, populate_existing=True)
    assert row.setting_value == {**before, "draft": "off", "draft_changed_at": "2026-11-02T00:05:00",
                                 "draft_reason": "memo_not_private"} and row.version == version + 1
    assert (turns.draft_mode(db_session), loop.read_switch(db_session)) == ("off", True)
    for bad in (("on", "memo_not_private"), ("store", "합성 까닭")):
        with pytest.raises(ValueError):
            turns.set_draft_mode(db_session, bad[0], reason=bad[1], now=NOW)
    db_session.delete(row)
    db_session.commit()
    turns.set_draft_mode(db_session, "store", reason="memo_not_found", now=NOW)  # 줄이 없으면 만든다
    db_session.commit()
    assert turns.draft_mode(db_session) == "store" and loop.read_switch(db_session) is True
