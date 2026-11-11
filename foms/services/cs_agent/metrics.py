"""시간 지표 — 초안 뜸 · 발송(운영 시간 안) 중간 · 90% 와 비율 다섯(플랜 C10-5 · 설계서 17.3 '잰다' · 원장 R10-7 · 검수 R16).

관리 화면 'AI 상담팀원' 기록판(:mod:`.panel`)과 아침 보고 한 줄 묶음(:mod:`.report`)이 이 모듈만 부른다. **숫자만** —
직원 번호 · 이름 · 상담 id · 글은 읽지도 내지도 않는다(직원별 수치 없음 — 원장 R10-28 · Q20).

재료는 차례 줄(``cs_agent_turns``)과 상태 표의 손님 글 시각(``cs_agent_messages``)이다. 기간은 차례를 연 때(``created_at``)의
KST 날짜 [시작, 끝). 정의(:data:`DEFINITIONS` — 기록판에도 같은 글이 보인다):

- **초안 뜸**(초): 차례를 연 마지막 손님 글 → 초안을 메모로 올리거나 저장한 때(``placed_at``). 모든 시간(밤 · 주말 포함).
- **발송**(초): 같은 마지막 손님 글 → [보내기]로 보낸 때(``sent_at``) — 둘 다 마지막 손님 글부터 잰다(총괄 결정 10-31, 설계서
  17.3 표 · 목표 10~90초). 그 손님 글이 그 브랜드 운영 시간(:data:`.state.BRAND_HOURS` · 영업일 달력) 안인 것만 — 1단계는 사람이
  누르므로 밤 · 주말 발송은 목표 밖이다(17.0). 밖은 수로만.
- **재지 못함**: 손님 글 줄이 없거나 시각이 거꾸로라 잴 수 없는 표본 수(말없이 빠지지 않게 — R16-5).
- **갈아 끼움** = 지난 초안 / 초안이 보였거나 두뇌를 부른 차례(놓은 때 · 두뇌 시간이 있는 올림 · 저장만 · 지난 초안 — 두뇌 전에
  손님 새 글로 닫힌 차례는 빼고, R16-4).
- **직원이 먼저 답함** = 집은 뒤 직원이 먼저 답한 차례(직원 답함 · 직원 답이 와 건너뜀) / 끝난 차례(일하는 중 · 올리는 중 · 실패는
  빼고, R16-6). 조용 기다림 안의 직원 답은 차례 줄이 없어 세지 않는다.
- **버튼으로 보냄** = [보내기]로 보낸 차례 / 메모를 올린 차례 가운데 답이 나간 것([보내기] + 데스크에서 직접 · 복사 · 고쳐 보낸 답).
- **그대로 보냄** = 끝난 꼴 '그대로' / [보내기]로 보낸 차례.
- **5초 안에 누름** = 누름 밀리초 < :data:`FAST_CLICK_MS` / 누름 밀리초가 있는 '그대로' 보낸 차례(읽지 않고 누르기 신호 — 17.6 ·
  고쳐 보낸 글은 읽은 것이라 뺀다, R16-8).

중간 · 90% 는 가장 가까운 순위(nearest-rank)다. 표본이 없으면 ``None``(화면은 '—').
"""

from __future__ import annotations

import datetime
import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence

from sqlalchemy import and_, select

from foms.persistence.main.models import CsAgentMessage, CsAgentTurn
from foms.services.common.business_calendar import is_business_day as calendar_is_business_day
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.state import BRAND_HOURS, KST

__all__ = ["DEFINITIONS", "FAST_CLICK_MS", "BrandMetrics", "Ratio", "Spread", "compute_metrics", "format_seconds",
           "in_business_hours", "metrics_lines", "metrics_view", "percentile"]

#: '5초 안에 누름'의 문턱(밀리초).
FAST_CLICK_MS = 5000
#: 기록판 · 아침 보고가 보는 기간(오늘 앞 7일).
WINDOW_DAYS = 7
_DRAFTED = ("posted", "stored", "superseded")
_DESK_OUTCOMES = ("direct", "edited", "copied")
#: 끝난 차례(직원이 먼저 답함 분모) — 일하는 중 · 올리는 중 · 실패(다시 집힘)는 아직 끝나지 않았다.
_FINISHED = ("posted", "stored", "skipped", "superseded", "staff_replied")
UTC = datetime.timezone.utc
#: 기록판에 보이는 정의(모듈 설명과 같은 뜻).
DEFINITIONS: tuple[str, ...] = (
    "초안 뜸 · 발송은 둘 다 그 차례 마지막 손님 글부터 잽니다(설계서 17.3 — 목표 10~90초). 발송은 그 손님 글이 운영 시간 안인 것만.",
    "재지 못함 = 손님 글 줄이 없거나 시각이 거꾸로라 잴 수 없는 표본 수.",
    "갈아 끼움 = 지난 초안 / 초안이 보였거나 두뇌를 부른 차례. 직원이 먼저 답함 = 집은 뒤 직원 답 / 끝난 차례.",
    "버튼으로 보냄 = [보내기] / 메모 차례 가운데 답이 나간 것. 5초 안에 누름 = 그대로 보낸 차례만.",
)


@dataclass(frozen=True)
class Spread:
    """시간 분포 — 표본 수 · 중간 · 90%(초) · 운영 시간 밖이라 안 잰 수(발송만) · 재지 못한 수."""

    count: int
    median: Optional[float]
    p90: Optional[float]
    excluded: int = 0
    unmeasured: int = 0


@dataclass(frozen=True)
class Ratio:
    """비율 — 분자 · 분모 · 값(분모 0 이면 ``None``)."""

    hits: int
    total: int

    @property
    def value(self) -> Optional[float]:
        """0~1 값."""
        return self.hits / self.total if self.total else None


@dataclass(frozen=True)
class BrandMetrics:
    """브랜드 하나의 지표 — 숫자만."""

    brand: str
    turns: int
    draft_shown: Spread
    send: Spread
    superseded: Ratio
    staff_first: Ratio
    button: Ratio
    as_is: Ratio
    fast_click: Ratio


def percentile(values: Sequence[float], share: float) -> Optional[float]:
    """가장 가까운 순위 백분위(``share`` 0~1). 빈 목록은 ``None``."""
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def _spread(values: Sequence[float], *, excluded: int = 0, unmeasured: int = 0) -> Spread:
    return Spread(len(values), percentile(values, 0.5), percentile(values, 0.9), excluded, unmeasured)


def in_business_hours(brand: str, at: datetime.datetime,
                      is_business_day: Optional[Callable[[datetime.date], bool]] = None) -> bool:
    """그 브랜드 운영 시간 안인가 — 영업일이고 KST 시각이 [여는 때, 닫는 때). ``at`` 이 시간대 없는 값이면 UTC 로 본다."""
    cal = is_business_day or calendar_is_business_day
    local = (at.replace(tzinfo=UTC) if at.tzinfo is None else at).astimezone(KST)
    open_hour, close_hour = BRAND_HOURS[brand]
    return bool(cal(local.date())) and open_hour <= local.hour < close_hour


def _seconds(start: Optional[datetime.datetime], end: Optional[datetime.datetime]) -> Optional[float]:
    """두 UTC naive 시각 사이 초(음수 · 빈 값은 ``None`` — 재지 못함)."""
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds()


def _rows(session: Any, start: datetime.date, end: datetime.date, brands: Sequence[str]) -> list[Any]:
    """기간 차례 줄의 코드 · 시각 칸 + 그 차례 손님 글 시각(직원 번호 · 글 칸은 고르지 않는다)."""
    since = naive_utc(datetime.datetime(start.year, start.month, start.day, tzinfo=KST))
    until = naive_utc(datetime.datetime(end.year, end.month, end.day, tzinfo=KST))
    turn, message = CsAgentTurn, CsAgentMessage
    stmt = (select(turn.brand, turn.state, turn.error_code, turn.send_state, turn.outcome, turn.placed_at,
                   turn.sent_at, turn.click_ms, turn.latency_ms, message.created_at.label("asked_at"))
            .outerjoin(message, and_(message.chat_id == turn.chat_id, message.message_id == turn.last_user_message_id))
            .where(turn.brand.in_(list(brands)), turn.created_at >= since, turn.created_at < until))
    return list(session.execute(stmt))


def _brand(brand: str, rows: Iterable[Any], cal: Callable[[datetime.date], bool]) -> BrandMetrics:
    rows = list(rows)
    placed = [row for row in rows if row.placed_at is not None]
    shown = [s for row in placed if (s := _seconds(row.asked_at, row.placed_at)) is not None]
    sent = [row for row in rows if row.send_state == "sent" and row.state != "skipped"]  # 초안 보냄만(넘김 [배우기] 빼고)
    timed = [(row, s) for row in sent if (s := _seconds(row.asked_at, row.sent_at)) is not None]
    inside = [s for row, s in timed if _in_hours(brand, row.asked_at, cal)]
    drafted = [row for row in rows if row.state in _DRAFTED and (row.placed_at is not None or row.latency_ms is not None)]
    finished = [row for row in rows if row.state in _FINISHED]
    desk = [row for row in rows if row.state == "posted" and row.send_state != "sent" and row.outcome in _DESK_OUTCOMES]
    as_is = [row for row in sent if row.outcome == "as_is"]
    clicked = [row for row in as_is if row.click_ms is not None]
    return BrandMetrics(
        brand=brand, turns=len(rows), draft_shown=_spread(shown, unmeasured=len(placed) - len(shown)),
        send=_spread(inside, excluded=len(timed) - len(inside), unmeasured=len(sent) - len(timed)),
        superseded=Ratio(sum(r.state == "superseded" for r in drafted), len(drafted)),
        staff_first=Ratio(sum(r.state == "staff_replied" or (r.state == "skipped" and r.error_code == "human_replied")
                              for r in finished), len(finished)),
        button=Ratio(len(sent), len(sent) + len(desk)), as_is=Ratio(len(as_is), len(sent)),
        fast_click=Ratio(sum(r.click_ms < FAST_CLICK_MS for r in clicked), len(clicked)))


def _in_hours(brand: str, at_utc: datetime.datetime, cal: Callable[[datetime.date], bool]) -> bool:
    """표의 UTC naive 시각이 그 브랜드 운영 시간 안인가."""
    return in_business_hours(brand, at_utc.replace(tzinfo=UTC), cal)


def compute_metrics(session: Any, *, start: datetime.date, end: datetime.date, brands: Sequence[str] = ("LAHOM", "HAUD"),
                    is_business_day: Optional[Callable[[datetime.date], bool]] = None) -> dict[str, BrandMetrics]:
    """기간 [시작, 끝) · 브랜드별 지표(읽기만 — 커밋은 부르는 쪽)."""
    cal = is_business_day or calendar_is_business_day
    rows = _rows(session, start, end, brands)
    return {brand: _brand(brand, (row for row in rows if row.brand == brand), cal) for brand in brands}


def format_seconds(value: Optional[float]) -> str:
    """초 → '28초' · '1분 32초' · '1시간 5분'(없으면 '—')."""
    if value is None:
        return "—"
    seconds = int(round(value))
    if seconds < 60:
        return f"{seconds}초"
    if seconds < 3600:
        return f"{seconds // 60}분 {seconds % 60}초" if seconds % 60 else f"{seconds // 60}분"
    return f"{seconds // 3600}시간 {seconds % 3600 // 60}분"


def _percent(ratio: Ratio) -> str:
    return "—" if ratio.value is None else f"{round(ratio.value * 100)}%({ratio.hits}/{ratio.total})"


def _time(spread: Spread, extra: str = "") -> str:
    tail = f"재지 못함 {spread.unmeasured}건" + (f" · {extra}" if extra else "")
    return f"중간 {format_seconds(spread.median)} · 90% {format_seconds(spread.p90)} · {spread.count}건({tail})"


def _items(m: BrandMetrics) -> list[tuple[str, str]]:
    """(이름, 값) 줄 — 기록판 · 아침 보고가 같이 쓴다."""
    return [
        ("초안 뜸(모든 시간)", _time(m.draft_shown)),
        ("발송(운영 시간 안)", _time(m.send, f"밖 {m.send.excluded}건")),
        ("갈아 끼움", _percent(m.superseded)), ("직원이 먼저 답함", _percent(m.staff_first)),
        ("버튼으로 보냄", _percent(m.button)), ("그대로 보냄", _percent(m.as_is)),
        ("5초 안에 누름", _percent(m.fast_click)),
    ]


def _window(now: datetime.datetime) -> tuple[datetime.date, datetime.date]:
    today = now.astimezone(KST).date()
    return today - datetime.timedelta(days=WINDOW_DAYS), today


def metrics_lines(session: Any, *, now: datetime.datetime, labels: dict[str, str],
                  is_business_day: Optional[Callable[[datetime.date], bool]] = None) -> list[str]:
    """아침 보고 한 줄 묶음 — 차례가 있던 브랜드만, 브랜드마다 한 줄(숫자만)."""
    start, end = _window(now)
    found = compute_metrics(session, start=start, end=end, brands=tuple(labels), is_business_day=is_business_day)
    return [f"[{labels[b]} 지난 {WINDOW_DAYS}일 시간 지표] " + " · ".join(f"{name} {value}" for name, value in _items(m))
            for b, m in found.items() if m.turns]


def metrics_view(session: Any, *, now: datetime.datetime, labels: dict[str, str],
                 is_business_day: Optional[Callable[[datetime.date], bool]] = None) -> dict[str, Any]:
    """기록판 재료 — 기간 · 정의 · 브랜드마다 (이름, 값) 줄(숫자만)."""
    start, end = _window(now)
    found = compute_metrics(session, start=start, end=end, brands=tuple(labels), is_business_day=is_business_day)
    return {"start": start.isoformat(), "end": (end - datetime.timedelta(days=1)).isoformat(),
            "definitions": list(DEFINITIONS),
            "brands": [{"brand": labels[b], "turns": m.turns, "rows": _items(m)} for b, m in found.items()]}
