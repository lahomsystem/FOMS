"""CS 상담 상태 계산(플랜 C1-1) — 손으로 꾸민 합성 글만 쓴다(손님 글 · 전화 꼴 숫자 없음).

달력은 대부분 '주말만 쉼' 가짜 달력으로 고정하고, 공휴일 하나(2026-10-09 한글날)만 진짜 달력으로 본다.
2026-11-02 는 월요일이다.
"""

from __future__ import annotations

import datetime
import random

import pytest

from foms.services.cs_agent import state
from foms.services.cs_agent.state import (
    KST,
    PRIORITY_BROKEN_PROMISE,
    PRIORITY_NEEDS_REPLY,
    PRIORITY_NONE,
    PRIORITY_PROMISE_PENDING,
    PRIORITY_STALE,
    ChatMessage,
    ChatState,
    business_minutes_between,
    compute_chat_state,
    detect_promise,
    is_closing_text,
    sort_by_priority,
)


def at(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 11, day, hour, minute, second, tzinfo=KST)


def weekdays_only(day: datetime.date) -> bool:
    return day.weekday() < 5


def calendar_without(*holidays: datetime.date):
    return lambda day: day.weekday() < 5 and day not in holidays


def user(n: int, when: datetime.datetime, text: str = "", **kw) -> ChatMessage:
    return ChatMessage(f"m{n}", "user", when, text, **kw)


def staff(n: int, when: datetime.datetime, text: str = "", **kw) -> ChatMessage:
    return ChatMessage(f"m{n}", "manager", when, text, **kw)


def bot(n: int, when: datetime.datetime, text: str = "", **kw) -> ChatMessage:
    return ChatMessage(f"m{n}", "bot", when, text, **kw)


def run(messages, now, brand="LAHOM", cal=weekdays_only, **kw) -> ChatState:
    return compute_chat_state("c1", brand, messages, now=now, is_business_day=cal, **kw)


def promise_of(text: str, when: datetime.datetime, brand="LAHOM", cal=weekdays_only):
    return detect_promise(staff(1, when, text), brand, is_business_day=cal)


# ── 답 필요 ──────────────────────────────────────────────────────────────


def test_customer_last_needs_reply():
    s = run([staff(1, at(2, 9), "안녕하세요 라홈입니다"), user(2, at(2, 10), "식탁 견적 부탁드려요")], at(2, 11))
    assert s.needs_reply and s.waiting_since == at(2, 10)
    assert s.waited_business_minutes == 60 and s.priority == PRIORITY_NEEDS_REPLY


def test_public_staff_reply_answers():
    s = run([user(1, at(2, 10), "식탁 견적 부탁드려요"), staff(2, at(2, 10, 20), "네 고객님 사이즈 알려 주세요")], at(2, 11))
    assert not s.needs_reply and s.priority == PRIORITY_NONE


def test_ai_draft_memo_is_not_an_answer():
    """음성 대조군: 우리 AI 초안 메모(비공개 봇 글)만 붙은 상담은 여전히 답 필요."""
    s = run([user(1, at(2, 10), "식탁 견적 부탁드려요"), bot(2, at(2, 10, 5), "AI 초안", private=True)], at(2, 11))
    assert s.needs_reply and s.waiting_since == at(2, 10)


def test_auto_notice_at_night_is_not_an_answer():
    """음성 대조군: 운영 시간 밖 자동 안내(공개 봇 글)만 있는 밤 상담은 답 필요. 기다린 시간은 아침부터 센다."""
    msgs = [user(1, at(2, 21), "내일 실측 되나요"), bot(2, at(2, 21, 0, 5), "지금은 운영 시간이 아닙니다")]
    s = run(msgs, at(3, 9))
    assert s.needs_reply and s.waited_business_minutes == 60


def test_staff_internal_memo_is_not_an_answer():
    s = run([user(1, at(2, 10), "색상 문의요"), staff(2, at(2, 10, 3), "샘플 확인 필요", private=True)], at(2, 11))
    assert s.needs_reply


def test_system_log_is_ignored():
    s = run([user(1, at(2, 10), "색상 문의요"), staff(2, at(2, 10, 3), "배정", is_log=True)], at(2, 11))
    assert s.needs_reply


def test_closing_only_is_not_needs_reply():
    msgs = [user(1, at(2, 9), "견적 문의요"), staff(2, at(2, 9, 10), "견적 보내드렸습니다"), user(3, at(2, 9, 20), "네 감사합니다!")]
    s = run(msgs, at(2, 11))
    assert not s.needs_reply and s.closing_only and s.priority == PRIORITY_NONE


def test_question_starting_with_closing_word_needs_reply():
    """옛 앞머리 규칙의 구멍: '네'로 시작하는 물음은 맺음이 아니다."""
    msgs = [staff(1, at(2, 9), "실측 가능합니다"), user(2, at(2, 9, 30), "네 그럼 내일 오시나요")]
    s = run(msgs, at(2, 11))
    assert s.needs_reply and not s.closing_only


def test_closing_word_with_photo_needs_reply():
    msgs = [staff(1, at(2, 9), "사진 부탁드려요"), user(2, at(2, 9, 30), "넵", has_file=True)]
    assert run(msgs, at(2, 11)).needs_reply


def test_wait_counts_from_first_substantive_message():
    msgs = [
        staff(1, at(2, 9), "견적 보내드렸습니다"),
        user(2, at(2, 10), "감사합니다"),
        user(3, at(2, 10, 30), "아 그리고 색상은 어떤 게 있나요"),
    ]
    s = run(msgs, at(2, 11))
    assert s.waiting_since == at(2, 10, 30) and s.waited_business_minutes == 30


def test_closed_chat_has_no_work():
    s = run([user(1, at(2, 10), "식탁 견적 부탁드려요")], at(2, 11), chat_state="closed")
    assert not s.is_open and not s.needs_reply and s.priority == PRIORITY_NONE


def test_snoozed_chat_stays_open():
    assert run([user(1, at(2, 10), "식탁 견적 부탁드려요")], at(2, 11), chat_state="snoozed").needs_reply


def test_message_order_does_not_matter():
    msgs = [
        user(1, at(2, 9), "견적 문의요"),
        staff(2, at(2, 9, 10), "확인 후 안내드리겠습니다"),
        user(3, at(2, 9, 20), "네 감사합니다"),
        bot(4, at(2, 9, 21), "AI 초안", private=True),
        user(5, at(2, 9, 40), "혹시 언제쯤 될까요"),
    ]
    first = run(msgs, at(2, 12))
    shuffled = msgs[:]
    random.Random(7).shuffle(shuffled)
    assert run(shuffled, at(2, 12)) == first
    assert first.waiting_since == at(2, 9, 40)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("네 감사합니다!", True),
        ("넵넵 😊", True),
        ("확인했습니다 수고하세요", True),
        ("네네 알겠습니다~", True),
        ("네 그럼 내일 오시나요", False),
        ("네 견적 부탁드려요", False),
        ("감사합니다 혹시 색상은요?", False),
        ("", False),
        # 손님이 다음 차례를 가져간 글(10-28 PC 시범에서 엄격 규칙이 '답 필요'로 잘못 올린 꼴)
        ("네 확인해보고 톡톡 드리겠습니다", True),
        ("생각해보고 다시 연락드릴게요~", True),
        ("남편이랑 상의하고 연락드릴게요", True),
        ("사이즈 재보고 말씀드릴게요", True),
        ("확인해보고 연락드릴게요 그런데 색상은 어떤 게 있나요", False),
    ],
)
def test_is_closing_text(text, expected):
    assert is_closing_text(text) is expected


# ── 운영 시간 · 3일+ ─────────────────────────────────────────────────────


def test_business_minutes_skip_weekend():
    assert business_minutes_between(at(6, 16), at(9, 9), "LAHOM", is_business_day=weekdays_only) == 120


def test_business_minutes_skip_holiday():
    cal = calendar_without(datetime.date(2026, 11, 9))
    assert business_minutes_between(at(6, 16), at(10, 9), "LAHOM", is_business_day=cal) == 120


def test_real_calendar_skips_hangul_day():
    """진짜 달력: 2026-10-09(금) 한글날은 운영일이 아니다."""
    start = datetime.datetime(2026, 10, 8, 16, tzinfo=KST)
    end = datetime.datetime(2026, 10, 12, 9, tzinfo=KST)
    assert business_minutes_between(start, end, "LAHOM") == 120


def test_brand_hours_differ():
    assert business_minutes_between(at(2, 17, 30), at(2, 18, 30), "HAUD", is_business_day=weekdays_only) == 30
    assert business_minutes_between(at(2, 17, 30), at(2, 18, 30), "LAHOM", is_business_day=weekdays_only) == 0


def test_utc_input_is_converted():
    start = datetime.datetime(2026, 11, 2, 1, tzinfo=datetime.timezone.utc)  # KST 10:00
    assert business_minutes_between(start, at(2, 11), "LAHOM", is_business_day=weekdays_only) == 60


def test_stale_after_three_business_days():
    msgs = [user(1, at(2, 8), "견적 문의요")]
    assert run(msgs, at(4, 16, 59)).stale is False
    s = run(msgs, at(5, 8))
    assert s.stale and s.waited_business_minutes == 3 * 9 * 60 and s.priority == PRIORITY_STALE


# ── 직원 약속 ────────────────────────────────────────────────────────────


def test_promise_tomorrow_pending_then_broken():
    msgs = [user(1, at(2, 9, 50), "실측 날짜 문의요"), staff(2, at(2, 10), "내일 다시 연락드리겠습니다")]
    pending = run(msgs, at(3, 11))
    assert pending.open_promise.due_at == at(3, 17) and pending.open_promise.rule == "내일"
    assert not pending.promise_overdue and pending.priority == PRIORITY_PROMISE_PENDING
    broken = run(msgs, at(3, 17, 1))
    assert broken.promise_overdue and broken.priority == PRIORITY_BROKEN_PROMISE


def test_promise_tomorrow_said_on_friday_is_monday():
    assert promise_of("내일 안내드릴게요", at(6, 15)).due_at == at(9, 17)


def test_promise_kept_by_later_staff_message():
    msgs = [staff(1, at(2, 10), "확인 후 안내드리겠습니다"), staff(2, at(2, 14), "견적서 보내드립니다")]
    assert run(msgs, at(3, 9)).open_promise is None


def test_happy_call_promise_is_call_kind():
    p = promise_of("해피콜 드리겠습니다", at(2, 8, 3))
    assert p.kind == "call" and p.due_at == at(2, 17) and p.rule == "같은 날"


def test_clock_promise():
    p = promise_of("3시에 연락드릴게요", at(2, 10))
    assert p.due_at == at(2, 15) and p.rule == "시각" and p.kind == "chat"


def test_clock_after_word_is_not_a_deadline():
    p = promise_of("11시 이후 오후로 해피콜 드리도록 전달해 두겠습니다", at(2, 8, 48))
    assert p.kind == "call" and p.due_at == at(2, 17)


def test_hour_duration_is_not_a_clock():
    assert promise_of("1시간 뒤 연락드릴게요", at(2, 10)).due_at == at(2, 17)


def test_promise_after_close_moves_to_next_day():
    assert promise_of("확인 후 안내드리겠습니다", at(2, 18, 30)).due_at == at(3, 17)


def test_same_day_promise_near_close_gets_next_day():
    assert promise_of("확인해 보겠습니다", at(2, 16, 30)).due_at == at(3, 17)


def test_conditional_guidance_is_not_a_promise():
    assert promise_of("사진 보내 주시면 확인 후 안내드리겠습니다", at(2, 10)) is None


def test_wait_a_moment_is_a_promise():
    p = promise_of("잠시만 기다려 주시면 안내 도와 드리겠습니다!", at(2, 10))
    assert p is not None and p.kind == "chat" and p.due_at == at(2, 17)


def test_plain_answer_is_not_a_promise():
    assert promise_of("내일부터 실측 가능하십니다", at(2, 10)) is None


def test_weekday_promises():
    assert promise_of("월요일에 연락드릴게요", at(4, 10)).due_at == at(9, 17)
    assert promise_of("다음 주 수요일에 안내드릴게요", at(4, 10)).due_at == at(11, 17)
    assert promise_of("다음 주 금요일에 연락드리겠습니다", at(2, 10)).due_at == at(13, 17)


def test_morning_and_this_week_promises():
    p = promise_of("내일 오전 중으로 연락드리겠습니다", at(2, 15))
    assert p.due_at == at(3, 12) and p.rule == "내일"
    assert promise_of("오전 중으로 연락드리겠습니다", at(2, 14)).due_at == at(3, 12)
    assert promise_of("이번 주 안에 안내드릴게요", at(4, 10)).due_at == at(6, 17)


def test_private_or_customer_text_is_never_a_promise():
    assert detect_promise(staff(1, at(2, 10), "내일 연락드릴게요", private=True), "LAHOM", is_business_day=weekdays_only) is None
    assert detect_promise(user(1, at(2, 10), "내일 연락드릴게요"), "LAHOM", is_business_day=weekdays_only) is None


# ── 우선순위 · 입력 검사 ─────────────────────────────────────────────────


def test_sort_by_priority():
    def mk(chat_id, priority, waited=0):
        return ChatState(chat_id, "LAHOM", True, priority in (1, 3), False, None, waited, priority == 1, None, priority == 2, priority)

    states = [
        mk("none", PRIORITY_NONE),
        mk("pending", PRIORITY_PROMISE_PENDING),
        mk("reply-short", PRIORITY_NEEDS_REPLY, 30),
        mk("broken", PRIORITY_BROKEN_PROMISE),
        mk("reply-long", PRIORITY_NEEDS_REPLY, 300),
        mk("stale", PRIORITY_STALE, 2000),
    ]
    assert [s.chat_id for s in sort_by_priority(states)] == [
        "stale", "broken", "reply-long", "reply-short", "pending", "none",
    ]


def test_stale_beats_broken_promise_in_same_chat():
    msgs = [user(1, at(2, 8), "견적 문의요"), staff(2, at(2, 8, 10), "확인 후 안내드리겠습니다"), user(3, at(2, 9), "아직인가요")]
    s = run(msgs, at(5, 9))
    assert s.needs_reply and s.stale and s.priority == PRIORITY_STALE


def test_unknown_brand_raises():
    with pytest.raises(ValueError):
        run([user(1, at(2, 10), "문의요")], at(2, 11), brand="OTHER")


def test_naive_datetime_raises():
    with pytest.raises(ValueError):
        run([ChatMessage("m1", "user", datetime.datetime(2026, 11, 2, 10), "문의요")], at(2, 11))


def test_brand_hours_match_channel_keys():
    assert set(state.BRAND_HOURS) == {"LAHOM", "HAUD"}
