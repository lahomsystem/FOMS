"""시간 지표 — 초안 뜸 · 발송(운영 시간 안) 중간 · 90% 와 비율 다섯(플랜 C10-5 · 설계서 17.3 '잰다' · 원장 R10-7).

관리 화면 'AI 상담팀원' 기록판(:mod:`.panel`)과 아침 보고 한 줄 묶음(:mod:`.report`)이 이 모듈만 부른다. **숫자만** —
직원 번호 · 이름 · 상담 id · 글은 읽지도 내지도 않는다(직원별 수치 없음 — 원장 R10-28 · Q20).

재료는 차례 줄(``cs_agent_turns``)과 상태 표의 손님 글 시각(``cs_agent_messages``)이다. 기간은 차례를 연 때(``created_at``)의
KST 날짜 [시작, 끝). 정의:

- **초안 뜸**(초): 차례를 연 손님 글 시각 → 초안을 메모로 올리거나 저장한 때(``placed_at``). 모든 시간(밤 · 주말 포함).
- **발송**(초): 첫 미답 손님 글(``waiting_since``) → [보내기]로 보낸 때(``sent_at``). 첫 미답 손님 글이 그 브랜드 운영 시간
  (:data:`.state.BRAND_HOURS` · 영업일 달력) 안인 것만 잰다 — 1단계는 사람이 누르므로 밤 · 주말 발송은 목표 밖이다(17.0). 밖은 수로만.
- **갈아 끼움** = 지난 초안 / 초안을 낸 차례(올림 · 저장만 · 지난 초안).
- **직원이 먼저 답함** = (직원 답함 + 직원 답이 와 건너뜀) / 연 차례 전부.
- **버튼으로 보냄** = [보내기]로 보낸 차례 / 메모를 올린 차례 가운데 답이 나간 것([보내기] + 데스크에서 직접 · 복사 · 고쳐 보낸 답).
- **그대로 보냄** = 끝난 꼴 '그대로' / [보내기]로 보낸 차례.
- **5초 안에 누름** = 누름 밀리초 < :data:`FAST_CLICK_MS` / 누름 밀리초가 있는 보낸 차례(읽지 않고 누르기 신호 — 17.6).

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

__all__ = ["FAST_CLICK_MS", "BrandMetrics", "Ratio", "Spread", "compute_metrics", "format_seconds", "metrics_lines",
           "metrics_view", "percentile"]

#: '5초 안에 누름'의 문턱(밀리초).
FAST_CLICK_MS = 5000
#: 기록판 · 아침 보고가 보는 기간(오늘 앞 7일).
WINDOW_DAYS = 7
_DRAFTED = ("posted", "stored", "superseded")
_DESK_OUTCOMES = ("direct", "edited", "copied")
UTC = datetime.timezone.utc


@dataclass(frozen=True)
class Spread:
    """시간 분포 — 표본 수 · 중간 · 90%(초). ``excluded`` 는 운영 시간 밖이라 재지 않은 수(발송만)."""

    count: int
    median: Optional[float]
    p90: Optional[float]
    excluded: int = 0


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


def _spread(values: Sequence[float], excluded: int = 0) -> Spread:
    return Spread(len(values), percentile(values, 0.5), percentile(values, 0.9), excluded)


def _in_hours(brand: str, at_utc: datetime.datetime, cal: Callable[[datetime.date], bool]) -> bool:
    """그 브랜드 운영 시간 안인가 — 영업일이고 시각이 [여는 때, 닫는 때)."""
    local = at_utc.replace(tzinfo=UTC).astimezone(KST)
    open_hour, close_hour = BRAND_HOURS[brand]
    return bool(cal(local.date())) and open_hour <= local.hour < close_hour


def _seconds(start: Optional[datetime.datetime], end: Optional[datetime.datetime]) -> Optional[float]:
    """두 UTC naive 시각 사이 초(음수 · 빈 값은 ``None``)."""
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds()


def _rows(session: Any, start: datetime.date, end: datetime.date, brands: Sequence[str]) -> list[Any]:
    """기간 차례 줄의 코드 · 시각 칸 + 그 차례 손님 글 시각(직원 번호 · 글 칸은 고르지 않는다)."""
    since = naive_utc(datetime.datetime(start.year, start.month, start.day, tzinfo=KST))
    until = naive_utc(datetime.datetime(end.year, end.month, end.day, tzinfo=KST))
    turn, message = CsAgentTurn, CsAgentMessage
    stmt = (select(turn.brand, turn.state, turn.error_code, turn.send_state, turn.outcome, turn.placed_at,
                   turn.sent_at, turn.waiting_since, turn.click_ms, message.created_at.label("asked_at"))
            .outerjoin(message, and_(message.chat_id == turn.chat_id, message.message_id == turn.last_user_message_id))
            .where(turn.brand.in_(list(brands)), turn.created_at >= since, turn.created_at < until))
    return list(session.execute(stmt))


def _brand(brand: str, rows: Iterable[Any], cal: Callable[[datetime.date], bool]) -> BrandMetrics:
    rows = list(rows)
    shown = [s for row in rows if (s := _seconds(row.asked_at, row.placed_at)) is not None]
    sent = [row for row in rows if row.send_state == "sent"]
    timed = [(row, s) for row in sent if (s := _seconds(row.waiting_since, row.sent_at)) is not None]
    inside = [s for row, s in timed if _in_hours(brand, row.waiting_since, cal)]
    desk = [row for row in rows if row.state == "posted" and row.send_state != "sent" and row.outcome in _DESK_OUTCOMES]
    clicked = [row for row in sent if row.click_ms is not None]
    return BrandMetrics(
        brand=brand, turns=len(rows), draft_shown=_spread(shown), send=_spread(inside, len(timed) - len(inside)),
        superseded=Ratio(sum(r.state == "superseded" for r in rows), sum(r.state in _DRAFTED for r in rows)),
        staff_first=Ratio(sum(r.state == "staff_replied" or (r.state == "skipped" and r.error_code == "human_replied")
                              for r in rows), len(rows)),
        button=Ratio(len(sent), len(sent) + len(desk)),
        as_is=Ratio(sum(r.outcome == "as_is" for r in sent), len(sent)),
        fast_click=Ratio(sum(r.click_ms < FAST_CLICK_MS for r in clicked), len(clicked)))


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


def _items(m: BrandMetrics) -> list[tuple[str, str]]:
    """(이름, 값) 줄 — 기록판 · 아침 보고가 같이 쓴다."""
    return [
        ("초안 뜸(모든 시간)", f"중간 {format_seconds(m.draft_shown.median)} · 90% {format_seconds(m.draft_shown.p90)}"
                         f" · {m.draft_shown.count}건"),
        ("발송(운영 시간 안)", f"중간 {format_seconds(m.send.median)} · 90% {format_seconds(m.send.p90)} · {m.send.count}건"
                         f"(밖 {m.send.excluded}건)"),
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
    """기록판 재료 — 기간 · 브랜드마다 (이름, 값) 줄(숫자만)."""
    start, end = _window(now)
    found = compute_metrics(session, start=start, end=end, brands=tuple(labels), is_business_day=is_business_day)
    return {"start": start.isoformat(), "end": (end - datetime.timedelta(days=1)).isoformat(),
            "brands": [{"brand": labels[b], "turns": m.turns, "rows": _items(m)} for b, m in found.items()]}
