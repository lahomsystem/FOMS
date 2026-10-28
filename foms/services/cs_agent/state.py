"""상담 상태 계산 — 상담 하나의 글 목록에서 '답 필요 · 기다린 시간 · 3일+ · 약속 기한 · 맺음 · 우선순위'를 낸다.

순수 함수다: 네트워크 · DB · 채널톡 쓰기가 없다. 글 목록은 C1-2 가 수신 기록과 Open API 에서 모은다
(플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C1-1 · 설계서 1절 · 3.1 '눈').

'답'의 정의(원장 R1-6): **공개 상담원(manager) 글만** 답이다. 우리 AI 초안 메모 · 직원 내부 메모 ·
워크플로 자동 안내 · FOMS 봇 글(bot) · 시스템 기록(배정 · 종료)은 답이 아니다.

종료 후보는 내지 않는다(원장 D23 — AI 는 종료를 누르지 않고 감시는 '답 필요'만 센다). 대신 손님의 남은
글이 맺음 인사뿐이면 '답 필요'에서 뺀다(``closing_only``).
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence

from foms.services.common.business_calendar import is_business_day as _calendar_is_business_day

KST = datetime.timezone(datetime.timedelta(hours=9), "KST")

#: 채널톡 운영 시간(평일, 공휴일 쉼) — 2026-10-28 데스크 설정 읽기(원장 F7). 키는 channel_client 와 같다.
BRAND_HOURS: dict[str, tuple[int, int]] = {"LAHOM": (8, 17), "HAUD": (8, 18)}

#: 이만큼 운영일을 기다리면 '3일+'(밀린 상담). 금요일 저녁 글이 월요일 아침까지 기다린 것은 넣지 않는다.
STALE_BUSINESS_DAYS = 3

#: 우선순위(작을수록 먼저). 같은 칸 안에서는 오래 기다린 상담이 먼저다.
PRIORITY_STALE = 1  # 답 필요 + 3일+
PRIORITY_BROKEN_PROMISE = 2  # 직원이 한 약속의 기한이 지났는데 아직 후속 글이 없다
PRIORITY_NEEDS_REPLY = 3
PRIORITY_PROMISE_PENDING = 4  # 약속 기한 전
PRIORITY_NONE = 9

BusinessDayFn = Callable[[datetime.date], bool]


@dataclass(frozen=True)
class ChatMessage:
    """상담 글 하나. ``text`` 는 가린 글이고 약속 꼴 · 맺음 꼴 판정에만 쓴다."""

    message_id: str
    person_type: str  # 'user' | 'manager' | 'bot'
    created_at: datetime.datetime  # 시간대가 있는 값
    text: str = ""
    private: bool = False  # 내부 메모(손님에게 안 보임)
    is_log: bool = False  # 시스템 기록(배정 · 종료 · 태그)
    has_file: bool = False  # 사진 · 파일


@dataclass(frozen=True)
class StaffPromise:
    """직원 공개 글 속 약속. ``kind`` 가 'call' 이면 채팅으로는 지켰는지 알 수 없다(보고에서 따로 보인다)."""

    message_id: str
    made_at: datetime.datetime
    kind: str  # 'chat' | 'call'
    due_at: datetime.datetime
    rule: str  # 기한을 정한 꼴: '같은 날' · '오전 중' · '시각' · '내일' · '모레' · '요일' · '이번 주' · '다음 주'


@dataclass(frozen=True)
class ChatState:
    chat_id: str
    brand: str
    is_open: bool
    needs_reply: bool
    closing_only: bool
    waiting_since: Optional[datetime.datetime]
    waited_business_minutes: int
    stale: bool
    open_promise: Optional[StaffPromise]
    promise_overdue: bool
    priority: int


# ── 맺음 글 ──────────────────────────────────────────────────────────────
# 글 전체가 맺음 낱말뿐일 때만 맺음이다. 앞머리만 보면 "네 그럼 내일 오시나요" 같은 물음이 빠진다
# (2026-10-28 PC 시범 대기열에서 실제로 1건).
_CLOSE_WORD = (
    r"(?:네+|넵+|넹+|예+|옙|감사(?:합니다|해요|드립니다|드려요|요)?|고맙(?:습니다|습니당|네요)|고마워요|"
    r"알겠(?:습니다|어요|습니당)|알았어요|확인(?:했습니다|했어요|했습니당|완료)|좋아요|좋습니다|"
    r"수고(?:하세요|하셨습니다|많으셨습니다|많으세요)|오케이|ok|okay|ㅇㅋ|ㅎ+|ㅋ+)"
)
_CLOSE_TOKEN = re.compile(rf"(?:{_CLOSE_WORD})+", re.IGNORECASE)
_EMOJI = re.compile("[☀-➿\U0001f000-\U0001faff️‍]")
_CLOSE_SPLIT = re.compile(r"[\s!.,~^♡♥ㅠㅜ]+")
# 손님이 다음 차례를 가져간 글("확인해 보고 톡톡 드리겠습니다" · "상의하고 연락드릴게요") — 답을 기다리는 글이 아니다.
_CUSTOMER_DEFER = re.compile(
    r"(?:보고|보구|하고|해서|한\s?뒤|한\s?후|본\s?뒤|본\s?후)\s?(?:다시\s?)?(?:톡톡|톡|연락|말씀|문의|카톡|메시지)\s?"
    r"(?:을|를|으로|로)?\s?(?:드릴게|드리겠|드릴께|할게|하겠|줄게|주겠|남길게|남기겠)"
    r"|(?:다시|나중에|추후에?)\s?(?:톡톡|톡|연락|말씀|문의|카톡)\s?(?:을|를)?\s?(?:드릴게|드리겠|드릴께|할게|하겠)"
)
_QUESTION_HINT = re.compile(r"까요|나요|인가요|는지|어떻게|언제|얼마|몇|무엇|뭐|어디|왜")


def is_closing_text(text: str) -> bool:
    """맺음 글인가 — 맺음 인사뿐("네 감사합니다!")이거나 손님이 다음 차례를 가져간 글("확인해 보고 톡톡 드리겠습니다").

    물음표나 물음 말(까요 · 언제 · 얼마 …)이 있으면 아니다.
    """
    body = _EMOJI.sub(" ", text or "")
    if "?" in body:
        return False
    tokens = [t for t in _CLOSE_SPLIT.split(body) if t]
    if len(body) <= 30 and tokens and all(_CLOSE_TOKEN.fullmatch(t) for t in tokens):
        return True
    return len(body) <= 60 and bool(_CUSTOMER_DEFER.search(body)) and not _QUESTION_HINT.search(body)


# ── 직원 약속 ────────────────────────────────────────────────────────────
_PROMISE_CALL = re.compile(
    r"(?:전화|통화|해피\s?콜)\s?(?:을|를|로)?\s?(?:꼭\s?|바로\s?|다시\s?)?"
    r"(?:드리겠|드릴게|드릴께|드리도록|드릴\s?예정|연락\s?드리)"
)
_PROMISE_CHAT = re.compile(
    r"(?:연락|안내|답변|회신|말씀)\s?(?:을|를|은|도)?\s?(?:꼭\s?|바로\s?|다시\s?)?(?:도와\s?)?"
    r"(?:드리겠|드릴게|드릴께|드리도록|드릴\s?예정)"
    r"|확인\s?(?:해\s?보겠|해\s?보고|후|하고|하여|해서)"
    r"|잠시만\s?기다려"
)
# 손님이 먼저 해야 하는 조건부 안내는 우리 약속이 아니다("사진 보내 주시면 확인 후 안내드리겠습니다").
# "잠시만 기다려 주시면 안내 도와 드리겠습니다"는 조건이 아니라 곧 답하겠다는 약속이다.
_CONDITIONAL = re.compile(r"(?<!기다려)(?<!기다려\s)(?:주시면|주실\s?때)|하시면|하실\s?때")
_WEEKDAY = re.compile(r"([월화수목금토])요일")
_WEEKDAY_INDEX = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5}
_NEXT_WEEK = re.compile(r"다음\s?주|차주")
_DAY_RULES: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("다음 주", _NEXT_WEEK, 5),
    ("모레", re.compile(r"모레"), 2),
    ("내일", re.compile(r"내일|명일"), 1),
)
_THIS_WEEK = re.compile(r"이번\s?주|금주")
_MORNING = re.compile(r"오전\s?중")
# "3시에 · 오후 2시까지" — "1시간" · "11시 이후 · 2시부터"(그 뒤 언제든)는 시각 약속이 아니다.
_CLOCK = re.compile(r"(오전|오후)?\s?(\d{1,2})\s?시(?![간공])(?!\s?(?:이후|부터|넘|지나))")

#: '같은 날' 약속이 마감 이만큼(분) 안쪽에서 나왔으면 다음 운영일 마감까지로 본다(16:55 "확인해 보겠습니다").
SAME_DAY_GRACE_MINUTES = 60


def _kst(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        raise ValueError("시간대가 없는 시각은 받지 않는다(UTC/KST 가 섞이면 조용히 틀린다)")
    return value.astimezone(KST)


def _hours(brand: str) -> tuple[int, int]:
    try:
        return BRAND_HOURS[brand]
    except KeyError as exc:
        raise ValueError(f"모르는 브랜드: {brand!r}") from exc


def _at(day: datetime.date, hour: int) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day, hour, tzinfo=KST)


def _business_day_after(day: datetime.date, count: int, is_business_day: BusinessDayFn) -> datetime.date:
    """``day`` 다음부터 운영일을 ``count`` 개 센 날."""
    while count > 0:
        day += datetime.timedelta(days=1)
        if is_business_day(day):
            count -= 1
    return day


def business_minutes_between(
    start: datetime.datetime,
    end: datetime.datetime,
    brand: str,
    *,
    is_business_day: Optional[BusinessDayFn] = None,
) -> int:
    """``start``~``end`` 사이에서 그 브랜드 운영 시간(운영일만)에 든 분."""
    cal = is_business_day or _calendar_is_business_day
    open_hour, close_hour = _hours(brand)
    start, end = _kst(start), _kst(end)
    total = 0.0
    day = start.date()
    while day <= end.date():
        if cal(day):
            lo = max(start, _at(day, open_hour))
            hi = min(end, _at(day, close_hour))
            if hi > lo:
                total += (hi - lo).total_seconds()
        day += datetime.timedelta(days=1)
    return int(total // 60)


def detect_promise(
    message: ChatMessage,
    brand: str,
    *,
    is_business_day: Optional[BusinessDayFn] = None,
) -> Optional[StaffPromise]:
    """직원 공개 글이 약속이면 기한을 붙여 돌려준다. 시각 · 요일 말이 없으면 그 운영일 마감까지."""
    if message.person_type != "manager" or message.private or message.is_log:
        return None
    text = message.text or ""
    is_call = bool(_PROMISE_CALL.search(text))
    if not (is_call or _PROMISE_CHAT.search(text)) or _CONDITIONAL.search(text):
        return None
    cal = is_business_day or _calendar_is_business_day
    _, close_hour = _hours(brand)
    made = _kst(message.created_at)
    day, rule = _promise_day(text, made.date(), cal)
    if day is None:
        cutoff = _at(made.date(), close_hour) - datetime.timedelta(minutes=SAME_DAY_GRACE_MINUTES)
        day = made.date() if cal(made.date()) and made <= cutoff else _business_day_after(made.date(), 1, cal)
    due = _at(day, close_hour)
    clock = _CLOCK.search(text)
    target_hour = 12 if _MORNING.search(text) else None
    if target_hour is None and clock:
        hour = int(clock.group(2))
        if (clock.group(1) == "오후" or 1 <= hour <= 7) and hour < 12:
            hour += 12
        target_hour = hour if hour <= 23 else None
    if target_hour is not None:
        # 요일 말이 없으면 그 시각은 오늘 것이다(마감 여유를 따지지 않는다). 이미 지났으면 다음 운영일.
        due = _at(day if rule != "같은 날" else made.date(), target_hour)
        if due <= made:
            due = _at(_business_day_after(made.date(), 1, cal), target_hour)
        if rule == "같은 날":
            rule = "오전 중" if target_hour == 12 and _MORNING.search(text) else "시각"
    return StaffPromise(message.message_id, made, "call" if is_call else "chat", due, rule)


def _promise_day(
    text: str, made_day: datetime.date, cal: BusinessDayFn
) -> tuple[Optional[datetime.date], str]:
    """약속 글의 날 말(요일 · 내일 · 모레 · 다음 주 · 이번 주). 없으면 ``(None, '같은 날')``."""
    weekday = _WEEKDAY.search(text)
    if weekday:
        target = _WEEKDAY_INDEX[weekday.group(1)]
        day = made_day + datetime.timedelta(days=1)
        while day.weekday() != target:
            day += datetime.timedelta(days=1)
        if _NEXT_WEEK.search(text) and day.isocalendar()[1] == made_day.isocalendar()[1]:
            day += datetime.timedelta(days=7)
        if not cal(day):
            day = _business_day_after(day, 1, cal)
        return day, "요일"
    for name, pattern, count in _DAY_RULES:
        if pattern.search(text):
            return _business_day_after(made_day, count, cal), name
    if _THIS_WEEK.search(text):
        week_end = made_day + datetime.timedelta(days=6 - made_day.weekday())
        days = [made_day + datetime.timedelta(days=i) for i in range((week_end - made_day).days + 1)]
        last = max((d for d in days if cal(d)), default=None)
        return (last if last else _business_day_after(made_day, 1, cal)), "이번 주"
    return None, "같은 날"


def _is_answer(message: ChatMessage) -> bool:
    return message.person_type == "manager" and not message.private and not message.is_log


def compute_chat_state(
    chat_id: str,
    brand: str,
    messages: Iterable[ChatMessage],
    *,
    now: datetime.datetime,
    chat_state: str = "opened",
    is_business_day: Optional[BusinessDayFn] = None,
) -> ChatState:
    """상담 하나의 상태. ``chat_state`` 는 채널톡 값('opened' · 'snoozed' · 'closed')."""
    _hours(brand)
    now = _kst(now)
    ordered = sorted((m for m in messages if not m.is_log), key=lambda m: (_kst(m.created_at), m.message_id))
    is_open = chat_state != "closed"
    last_answer = max((i for i, m in enumerate(ordered) if _is_answer(m)), default=-1)
    pending = [m for m in ordered[last_answer + 1:] if m.person_type == "user"]
    substantive = [m for m in pending if m.has_file or not is_closing_text(m.text)]
    needs_reply = is_open and bool(substantive)
    waiting_since = _kst(substantive[0].created_at) if needs_reply else None
    waited = (
        business_minutes_between(waiting_since, now, brand, is_business_day=is_business_day)
        if waiting_since
        else 0
    )
    open_hour, close_hour = BRAND_HOURS[brand]
    stale = needs_reply and waited >= STALE_BUSINESS_DAYS * (close_hour - open_hour) * 60

    promise = None
    if is_open and last_answer >= 0:
        promise = detect_promise(ordered[last_answer], brand, is_business_day=is_business_day)
    overdue = bool(promise and now > promise.due_at)

    if stale:
        priority = PRIORITY_STALE
    elif overdue:
        priority = PRIORITY_BROKEN_PROMISE
    elif needs_reply:
        priority = PRIORITY_NEEDS_REPLY
    elif promise:
        priority = PRIORITY_PROMISE_PENDING
    else:
        priority = PRIORITY_NONE
    return ChatState(
        chat_id=chat_id,
        brand=brand,
        is_open=is_open,
        needs_reply=needs_reply,
        closing_only=is_open and bool(pending) and not substantive,
        waiting_since=waiting_since,
        waited_business_minutes=waited,
        stale=stale,
        open_promise=promise,
        promise_overdue=overdue,
        priority=priority,
    )


def sort_by_priority(states: Sequence[ChatState]) -> list[ChatState]:
    """보고 순서: 우선순위 → 오래 기다린 상담 → 약속 기한이 이른 상담 → 상담 id."""
    far = datetime.datetime.max.replace(tzinfo=KST)
    return sorted(
        states,
        key=lambda s: (
            s.priority,
            -s.waited_business_minutes,
            s.open_promise.due_at if s.open_promise else far,
            s.chat_id,
        ),
    )
