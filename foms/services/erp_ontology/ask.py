"""물어보기 ↔ ERP 주문 읽기 잇기(설계서 2026-11-14-foms-graft 3.7 · 3.10 · 7절). services — DB 는 읽기만(기록 두 줄 빼고).

물어보기 길(:mod:`foms.services.brain.chat_answer`)이 ``erp_read`` 스위치가 켜진 사람에게만 부른다. 순서(지금 순서 사이에 낀다):
가림 → **번호 찾기 → 주문 읽기 권한 → 주문 · 방문 읽기** → 회사 지식 찾기 → 모델 → 코드 확인 → 기록.

- **번호 찾기**(:func:`find_order_number`): 가리기 **전** 원문에서 ``#123`` · ``주문 123`` · ``주문번호 123`` · ``123번 주문``. 서로
  다른 번호가 둘 이상이면 읽지 않는다. 원문 · 찾은 글은 로그 · 기록에 싣지 않는다(번호와 가린 글만).
- **주문 읽기**(:func:`load_order`): 삭제 · 초안 제외(:meth:`models.Order.active_filter`) · :func:`user_can_read_order`(프리랜서는
  자기 주문만 · 협력사는 자기 협력사 주문만). 읽을 수 없는 주문은 **없는 주문과 같은 결과**(``None`` — 기록 단계 글도 같다).
- **읽기 도구**는 :mod:`.read` 의 허용 칸만(손님 이름 · 전화 · 주소 · 금액 · 메모는 읽지 않는다). 모델 줄은 :func:`.read.prompt_lines`.
- **코드 확인 재료**(:func:`dates_known`): 답 속 날짜(연-월-일 · 월 일 · 월/일 · 월.일 · 뒤 요일 · 오늘 · 내일 · 모레 ·
  이번 주 · 다음 주 · 따로 쓴 요일)가 주문 줄 또는 근거 지식
  글에 있는 날이어야 한다 — 숫자 확인(:func:`foms.services.brain.gates.numbers_known`)만으로는 '11월 3일'(11 은 실측 달 · 3 은
  시공 날)을 막지 못한다.
- **걸린 시간**(:class:`Trace`): 도구마다 ms. 실행 기록 ``ai_agent_runs`` 한 줄(:func:`record_run` — 직원 ``ask``, 코드 · 수만).
"""

from __future__ import annotations

import datetime
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Optional

from sqlalchemy import select

from foms.persistence.graft.models import AiAgentRun
from foms.services.ai_staff.registry import TOOLS
from foms.services.cs_agent.masking import MASK_TOKENS
from foms.services.cs_agent.masking_contacts import normalize
from foms.services.erp_ontology.objects import OBJECT_TYPES
from foms.services.erp_ontology.read import OrderCard, Visit, order_card, order_id_of, order_key, prompt_lines, visits
from foms.services.orders.order_mutation_policy import user_can_read_order
from models import Order

__all__ = [
    "AGENT", "ErpRead", "MASKED_LABELS", "STAGE_TONES", "TOOL_MASK", "TOOL_ORDER", "TOOL_SEARCH", "TOOL_VISITS",
    "Trace", "answer_kind", "change_asked", "dates_known", "erp_view", "find_order_number", "load_order",
    "mask_note", "question_uses", "read_question_order", "record_run", "stage_tone",
]

AGENT = "ask"
TOOL_MASK, TOOL_ORDER, TOOL_VISITS, TOOL_SEARCH = "mask.apply", "erp.order.get", "erp.visit.list", "knowledge.search"
_MAX_ORDER_ID = 2_147_483_647
#: 화면 '가린 것' — AI 에 가지 않는 물건 종류 이름(손님 · 현장).
MASKED_LABELS: tuple[str, ...] = tuple(obj.label for obj in OBJECT_TYPES if obj.masked)
#: 단계 → 디자인 시스템 꼬리표 색 갈래(무채색 없음). 모르는 단계는 primary.
STAGE_TONES: dict[str, str] = {"COMPLETED": "success", "AS_COMPLETED": "success", "CS": "warning", "AS": "warning",
                               "AS_RECEIVED": "warning", "CONFIRM": "warning"}

# ── 번호 찾기 ─────────────────────────────────────────────────────────────
#: 수에 **붙어** 오면 주문 번호가 아닌 말(개수 · 날 · 돈 · 길이 · '두 번 했다'). 띄어 쓴 다음 낱말('123 시공')은 막지 않는다.
_NOT_ID_TAIL = (r"(?![\d.,])(?!(?:개|건|일|월|년|시|분|초|원|만|천|명|차|회|장|층|평|자|통|cm|mm|센티|미터|"
                r"번\s*(?:째|했|하|한|할|해|씩)))")
_ORDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<![\w&])#\s?(\d{1,7})(?!\d)"),
    re.compile(r"주문\s*번호\s*(?:는|은|가|:|：)?\s*#?\s*(\d{1,7})(?!\d)"),
    re.compile(r"주문\s*(\d{1,7})" + _NOT_ID_TAIL),
    re.compile(r"(?<![\d.,#])(\d{1,7})\s*번\s*주문(?!\s*(?:했|하|한|할|해|함|됐|되|된))"),
)
_CHANGE_WORDS = re.compile(r"바꿔|바꾸|바꿀|옮겨|옮기|옮길|변경|미뤄|미루|미룰|당겨|당기|당길|연기")


def find_order_number(text: Any) -> Optional[int]:
    """원문(가리기 전) 속 주문 번호 — 서로 다른 번호가 정확히 하나일 때만 그 번호, 없거나 둘 이상이면 ``None``."""
    if not isinstance(text, str) or not text:
        return None
    body = normalize(text)
    found = {int(m.group(1)) for pattern in _ORDER_PATTERNS for m in pattern.finditer(body)}
    found = {number for number in found if 0 < number <= _MAX_ORDER_ID}
    return next(iter(found)) if len(found) == 1 else None


def change_asked(masked: str) -> bool:
    """일정을 바꿔 달라는 질문인가(화면 '방문 옮기기는 승인 대기로 가요' 줄 — 물어보기는 바꾸지 않는다)."""
    return bool(_CHANGE_WORDS.search(masked or ""))


def mask_note(raw: str, masked: str) -> str:
    """가림 도구 한 일 — 가림 표시가 몇 곳 생겼나(글 없이 수만)."""
    added = sum(max(0, masked.count(token) - raw.count(token)) for token in MASK_TOKENS)
    return f"가림 {added}곳"


# ── 걸린 시간 ─────────────────────────────────────────────────────────────
@dataclass
class Step:
    """도구 한 번 — 이름 · 한 일(수만) · 결과 코드 · 걸린 ms."""

    tool: str
    what: str = ""
    detail: str = ""
    ms: int = 0


@dataclass
class Trace:
    """도구마다 걸린 시간을 모은다. 같은 도구를 다시 재면 시간을 더한다(찾기 = 질문 벡터 + 후보 찾기)."""

    clock: Callable[[], float] = time.perf_counter
    steps: list[Step] = field(default_factory=list)
    started: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        """시작 때를 적는다."""
        self.started = self.clock()

    @contextmanager
    def step(self, tool: str) -> Iterator[Step]:
        """``with trace.step(이름) as s:`` — 안에서 ``s.what`` · ``s.detail`` 을 적는다."""
        current = Step(tool)
        begin = self.clock()
        try:
            yield current
        finally:
            current.ms = max(0, round((self.clock() - begin) * 1000))
            same = next((s for s in self.steps if s.tool == tool), None)
            if same is None:
                self.steps.append(current)
            else:
                same.ms += current.ms
                same.what, same.detail = current.what or same.what, current.detail or same.detail

    def total_ms(self) -> int:
        """시작부터 지금까지 ms."""
        return max(0, round((self.clock() - self.started) * 1000))

    def rows(self) -> list[dict[str, Any]]:
        """실행 기록 ``steps`` 칸(코드 · 수만)."""
        return [{"tool": s.tool, "what": s.what, "detail": s.detail, "ms": s.ms} for s in self.steps]

    def tools(self) -> list[dict[str, Any]]:
        """화면 '쓴 도구' — 이름 · 한 일 · ms(도구 화면 말은 AI 직원 목록 :data:`TOOLS`)."""
        return [{"name": s.tool, "label": TOOLS.get(s.tool, s.tool), "what": s.what, "ms": s.ms} for s in self.steps]


# ── 주문 읽기 ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ErpRead:
    """질문 하나가 읽은 주문 — 허용 칸 값 · 방문 · 모델 줄 · 일정 바꾸기 질문인가."""

    card: OrderCard
    visits: tuple[Visit, ...]
    lines: tuple[str, ...]
    change_asked: bool = False

    @property
    def order_id(self) -> int:
        """주문 번호."""
        return self.card.order_id

    @property
    def key(self) -> str:
        """ERP 물건 키(``erp:order/<번호>`` — 근거 키 · 쓰인 곳)."""
        return order_key(self.card.order_id)


def load_order(session: Any, user: Any, order_id: int) -> Optional[Any]:
    """주문 한 줄(기본 키) — 삭제 · 초안이거나 이 사람이 읽을 수 없으면 ``None``(없는 주문과 같다)."""
    order = session.execute(select(Order).where(Order.id == int(order_id), Order.active_filter())).scalar_one_or_none()
    if order is None or not user_can_read_order(user, order):
        return None
    return order


def read_question_order(session: Any, user: Any, raw: str, masked: str, trace: Trace) -> Optional[ErpRead]:
    """질문 속 주문 하나를 읽는다 — 번호가 없거나 둘 이상이면 도구를 돌리지 않고 ``None``, 못 읽으면 ``None``.

    Args:
        session: DB 세션(읽기만).
        user: 묻는 사람(읽기 권한 판정).
        raw: 가리기 전 원문(번호 찾기에만 쓴다 — 어디에도 남기지 않는다).
        masked: 가린 질문(일정 바꾸기 질문인가).
        trace: 걸린 시간 모음(``erp.order.get`` · ``erp.visit.list``).

    Returns:
        읽은 주문 또는 ``None``.
    """
    number = find_order_number(raw)
    if number is None:
        return None
    with trace.step(TOOL_ORDER) as step:
        order = load_order(session, user, number)
        card = order_card(order) if order is not None else None
        step.what, step.detail = ("주문 1 · 읽기만", "found") if card is not None else ("주문 0", "none")
    if card is None:
        return None
    with trace.step(TOOL_VISITS) as step:
        found = tuple(visits(order))
        step.what, step.detail = f"방문 {len(found)}", "found"
    return ErpRead(card, found, tuple(prompt_lines(card, found)), change_asked(masked))


# ── 코드 확인 — 답 속 날짜 ─────────────────────────────────────────────────
_WEEKDAYS = "월화수목금토일"
_YMD = re.compile(r"(?<!\d)(\d{4})\s*(?:-|\.|/|년)\s*(\d{1,2})\s*(?:-|\.|/|월)\s*(\d{1,2})(?!\d)\s*일?")
_MD = (re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일"), re.compile(r"(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])"),
       re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?![\d.])"))
#: 날 바로 뒤 요일 — 괄호 안('(금)' · '(금요일)') 또는 '금요일'만(맨 '월' 한 글자는 '월 단위' 같은 말과 헷갈린다).
_WEEKDAY_AFTER = re.compile(r"\s*(?:\(\s*([월화수목금토일])(?:요일)?\s*\)|([월화수목금토일])요일)")
#: 날 없이 따로 쓴 요일('금요일' · '(금)').
_WEEKDAY_ALONE = re.compile(r"\(\s*([월화수목금토일])(?:요일)?\s*\)|([월화수목금토일])요일")
_RELATIVE = {"오늘": 0, "내일": 1, "모레": 2, "글피": 3}
_RELATIVE_RE = re.compile("|".join(_RELATIVE))
#: '이번 주' · '다음 주'(뒤에 요일이 오면 그 주의 그 요일, 없으면 그 주 안 어느 날).
_WEEK_RE = re.compile(r"(이번|다음)\s*주")
_WEEK_OFFSET = {"이번": 0, "다음": 7}


@dataclass(frozen=True)
class _Day:
    """글 속 날 하나 — 연(없으면 ``None``) · 월 · 일 · 바로 뒤에 적힌 요일(없으면 ``None``)."""

    year: Optional[int]
    month: int
    day: int
    weekday: Optional[int] = None


@dataclass
class _Said:
    """답이 말한 날들 — 날 · 날 없이 쓴 요일(0 ~ 6) · 주 안 어느 날(그 주 월요일)."""

    days: list[_Day] = field(default_factory=list)
    weekdays: list[int] = field(default_factory=list)
    weeks: list[datetime.date] = field(default_factory=list)


def _weekday_at(text: str, end: int) -> tuple[Optional[int], int]:
    """``end`` 바로 뒤 요일 글자(괄호 · '요일' 있어도) → (0 ~ 6, 요일 글 끝). 없으면 (None, end)."""
    match = _WEEKDAY_AFTER.match(text, end)
    if not match:
        return None, end
    return _WEEKDAYS.index(match.group(1) or match.group(2)), match.end()


def _take_dates(text: str) -> tuple[list[_Day], str]:
    """글 속 날짜들(연-월-일 먼저 지우고 월 일 꼴) · 날과 그 뒤 요일을 빈칸으로 바꾼 글. 달 1 ~ 12 · 날 1 ~ 31 밖은 빼낸다."""
    found, rest = [], text or ""
    for pattern in (_YMD, *_MD):
        for match in list(pattern.finditer(rest)):
            year = int(match.group(1)) if pattern is _YMD else None
            month, day = (int(match.group(i)) for i in ((2, 3) if pattern is _YMD else (1, 2)))
            weekday, end = _weekday_at(rest, match.end())
            found.append(_Day(year, month, day, weekday))
            rest = rest[:match.start()] + " " * (end - match.start()) + rest[end:]
    return [day for day in found if 1 <= day.month <= 12 and 1 <= day.day <= 31], rest


def _said(answer: str, today: datetime.date) -> _Said:
    """답이 말한 날 — 날짜 · '오늘' · '내일' · '모레'(뒤 요일까지) · '이번 주' · '다음 주'(뒤 요일까지) · 따로 쓴 요일."""
    days, rest = _take_dates(answer)
    said = _Said(days=days)
    for match in list(_RELATIVE_RE.finditer(rest)):
        day = today + datetime.timedelta(days=_RELATIVE[match.group(0)])
        weekday, end = _weekday_at(rest, match.end())
        said.days.append(_Day(day.year, day.month, day.day, weekday))
        rest = rest[:match.start()] + " " * (end - match.start()) + rest[end:]
    for match in list(_WEEK_RE.finditer(rest)):
        monday = today + datetime.timedelta(days=_WEEK_OFFSET[match.group(1)] - today.weekday())
        weekday, end = _weekday_at(rest, match.end())
        if weekday is None:
            said.weeks.append(monday)
        else:
            day = monday + datetime.timedelta(days=weekday)
            said.days.append(_Day(day.year, day.month, day.day))
        rest = rest[:match.start()] + " " * (end - match.start()) + rest[end:]
    said.weekdays = [_WEEKDAYS.index(m.group(1) or m.group(2)) for m in _WEEKDAY_ALONE.finditer(rest)]
    return said


def _matches(said: _Day, known: _Day) -> bool:
    """답 속 날이 아는 날과 같은가 — 월 · 일 같고, 둘 다 연이 있으면 같고, 요일을 적었으면 그 날의 요일과 같다."""
    if (said.month, said.day) != (known.month, known.day):
        return False
    if said.year is not None and known.year is not None and said.year != known.year:
        return False
    if said.weekday is None:
        return True
    year = known.year if known.year is not None else said.year
    if year is None:
        return True
    try:
        return datetime.date(year, known.month, known.day).weekday() == said.weekday
    except ValueError:
        return False


def _dated(days: Iterable[_Day]) -> list[datetime.date]:
    """연이 있는 아는 날 → 날 값(틀린 날 빼고)."""
    out = []
    for day in days:
        if day.year is None:
            continue
        try:
            out.append(datetime.date(day.year, day.month, day.day))
        except ValueError:
            continue
    return out


def dates_known(answer: str, known: str, *, today: datetime.date) -> bool:
    """답 속 날짜가 모두 아는 글(주문 줄 · 근거 지식 글)의 날인가.

    '오늘' · '내일' · '모레' · '이번 주 X요일' · '다음 주 X요일'은 오늘(한국)에서 센 날, 요일 없는 '이번 주' · '다음 주'는 그 주
    안에 아는 날이 있어야 한다. 날 없이 따로 쓴 요일은 아는 날 가운데 그 요일이 있거나, 아는 글에 같은 요일 글이 있어야 한다.
    """
    allowed, _rest = _take_dates(known)
    said = _said(answer, today)
    dated = _dated(allowed)
    known_weekdays = {_WEEKDAYS.index(m.group(1) or m.group(2)) for m in _WEEKDAY_ALONE.finditer(known or "")}
    if not all(any(_matches(day, ok) for ok in allowed) for day in said.days):
        return False
    if not all(any(monday <= day <= monday + datetime.timedelta(days=6) for day in dated) for monday in said.weeks):
        return False
    return all(weekday in known_weekdays or any(day.weekday() == weekday for day in dated) for weekday in said.weekdays)


# ── 답 값 · 기록 ──────────────────────────────────────────────────────────
def stage_tone(stage: str) -> str:
    """단계 꼬리표 색 갈래(무채색 없음)."""
    return STAGE_TONES.get(stage, "primary")


def erp_view(read: ErpRead, trace: Trace) -> dict[str, Any]:
    """답 값 ``erp`` 칸(설계서 3.7) — 화면 옆 창 '이 답이 읽은 것'. 손님 이름 · 전화 · 주소 · 금액은 없다(담당 영업은 화면 전용)."""
    card = read.card
    return {"order": {"id": card.order_id, "stage": card.stage, "stage_label": card.stage_label,
                      "stage_tone": stage_tone(card.stage), "products": list(card.products),
                      "manager_label": card.manager_label, "masked": list(MASKED_LABELS)},
            "visits": [visit.as_dict() for visit in read.visits], "tools": trace.tools(),
            "change_asked": read.change_asked}


def answer_kind(evidence: Iterable[str], unknown: bool) -> str:
    """답 갈래 — ``unknown``(모름) · ``erp``(주문 키를 근거로 단 답) · ``knowledge``(회사 지식만)."""
    if unknown:
        return "unknown"
    return "erp" if any(order_id_of(key) is not None for key in evidence) else "knowledge"


def question_uses(evidence: Iterable[str], unknown: bool, read: Optional[ErpRead]) -> list[str]:
    """쓰인 곳에 남길 키 — 받아들인 답의 근거 키(지식 · 주문) + 읽은 주문 키(모름이어도 읽은 일은 남긴다)."""
    keys = [] if unknown else [key for key in evidence if isinstance(key, str)]
    if read is not None:
        keys.append(read.key)
    return list(dict.fromkeys(keys))


def record_run(session: Any, *, question_id: int, trace: Trace, outcome: str,
               now_utc: datetime.datetime) -> AiAgentRun:
    """실행 기록 한 줄(직원 ``ask`` · 무엇 때문에 = 질문 번호 · 단계마다 ms · 끝 코드). flush 하지 않는다 — 커밋은 부르는 쪽."""
    row = AiAgentRun(agent=AGENT, started_at=now_utc, total_ms=trace.total_ms(), source_kind="question",
                     source_ref=str(int(question_id)), steps=trace.rows(), outcome=str(outcome)[:24], proposals=0)
    session.add(row)
    return row
