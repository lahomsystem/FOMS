"""생산 첫 화면 출고일 — 주문 하나가 어느 날 나가는지(= 제작을 끝낼 날) 한 곳에서 읽는다.

사장님 2026-11-25("실제 출고 일정과 맞는지 … 출고 일정 = 제작 일정"):

- 띠 · 날짜 판은 **출고 화면과 같은 날짜로** 주문을 놓는다 — 시공일이 여럿이면 남은 날마다, 우리 시공일이 아직 없는 협력사
  주문은 희망일에. 출고 화면(``foms/web/shipment/dashboard.py``)은 일정 표 ``order_schedule_dates``(저장 훅이
  ``structured_data`` 에서 만드는 사본)로 시공일을 모두 보고, 확정 대기 협력사 주문은 희망일(``partner_intake``)에 둔다.
- 상차 예정일(``Order.shipping_scheduled_date``, 지방 대시보드가 적는다)이 적힌 지방 주문은 그 날에, 적혀 있지 않으면 시공일에
  (출고 화면은 이번에 바꾸지 않는다 — 두 화면은 이 한 갈래만 다르다). 상차 예정일이 가장 이른 시공일보다 뒤면 잘못 적힌 것으로
  보고 시공일에 놓는다(사장님 2026-11-25 "시공일에 놓기" — 줄의 '상차 12/1' 표는 그대로 보여 어긋난 것을 알게 한다).
- 띠의 날 줄은 **내일부터**("당일은 이미 시공 중 … 내일 부터 날짜 보이면 됨") — 오늘 나가는 주문은 지난 묶음에 선다.

순수 함수만 둔다(쿼리 0 · 요청 문맥 없음). 첫 화면은 주문을 통째로 읽으므로 칸을 그대로 쓴다. 시공일 전부는 일정 표와 같은
출처 :func:`all_construction_dates`, 희망일은 출고 화면이 쓰는 :func:`pending_request` · :func:`clean_date` 그대로 —
두 화면이 같은 주문을 다른 날로 읽지 않게 한다. :func:`live_condition` 은 쿼리가 아니라 첫 화면 쿼리에 붙일 조건 식이다.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, not_, or_, select

from foms.services.orders.construction_dates import all_construction_dates
from foms.services.partners.schedule_request import clean_date, pending_request
from models import Order, OrderScheduleDate

#: 출고일 종류 — 시공일 · 지방 상차 예정일 · 협력사 희망일(화면 글 머리말과 같다).
SHIP_BUILD = '시공'
SHIP_LOAD = '상차'
SHIP_WISH = '희망일'
#: 출고일이 이보다 더 지난 주문은 "지난 출고일" 한 장으로(첫 화면 ``PRODUCTION_HOME_PAST_DAYS`` 와 같은 값).
PAST_DAYS = 7
#: 띠에 서는 날 줄 수 — 내일부터(``PRODUCTION_HOME_STRIP_DAYS`` 와 같은 값). 앞 '지난 7일' · 뒤 '그 뒤' 와 13줄.
STRIP_DAYS = 11
PANE_RECENT = 'recent'
PANE_LATER = 'later'
PANE_PAST = 'past'
PANE_NONE = 'none'


#: 상차 예정일로 읽는 글 — 앞 10자가 ``YYYY-MM-DD``(ASCII 숫자 · 달 01~12 · 날 01~31). 경계 SQL(:func:`_loading_sql`)과 같은 꼴.
_LOADING_RE = re.compile(r'[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])')
_DIGITS = tuple('0123456789')
_MONTHS = tuple(f"{m:02d}" for m in range(1, 13))
_MDAYS = tuple(f"{d:02d}" for d in range(1, 32))


def loading_day(value: Any) -> Optional[datetime.date]:
    """상차 예정일 글 → date — 앞 10자가 날짜 꼴일 때만(뒤에 시각이 붙어도 앞 10자). '미정' · '11/27' · 없는 날은 None.

    경계 SQL(:func:`_loading_sql`)과 같은 꼴 규칙이라 두 쪽이 같은 주문을 같은 묶음에 둔다(없는 날 '2026-02-30' 만 SQL 은
    꼴만 보아 상차 갈래로 본다 — 지방 대시보드는 날짜 칸으로만 적는다).
    """
    text = str(value or '').strip()[:10]
    if not _LOADING_RE.fullmatch(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _day(value: Any) -> Optional[datetime.date]:
    """date · 'YYYY-MM-DD…' 글 → date. 비었거나 못 읽으면 None."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or '').strip()[:10]
    try:
        return datetime.date.fromisoformat(text) if len(text) == 10 else None
    except ValueError:
        return None


def ship_dates(sd: Any, *, regional: bool, loading_date: Any, partner_org_id: Any,
               stage_code: Any) -> list[tuple[datetime.date, str]]:
    """주문 하나의 출고일 목록 ``[(날, 종류)]``(날 순) — 위에서 처음 맞는 갈래 하나.

    Args:
        sd: 주문 ``structured_data``(읽기만).
        regional: ``Order.is_regional``.
        loading_date: ``Order.shipping_scheduled_date``(상차 예정일, 'YYYY-MM-DD').
        partner_org_id: ``Order.partner_org_id``(협력사 주문이면 값이 있다).
        stage_code: ``Order.erp_stage_code`` — 출고 화면과 같은 칸으로 희망일을 더 받는 단계인지 본다.

    Returns:
        ① 지방 주문 + 상차 예정일(시공일이 없거나 가장 이른 시공일과 같거나 앞) → ``[(그 날, '상차')]`` ② 시공일 전부(주문 칸
        쉼표 날 + 취소 안 된 제품 날) → ``[(날, '시공'), …]`` ③ 시공일이 없는 협력사 주문의 확정 대기 희망일 → ``[(그 날, '희망일')]``
        ④ 그 밖 ``[]``(출고일 없음).
    """
    builds = [datetime.date.fromisoformat(day) for day in all_construction_dates(sd)]
    loading = loading_day(loading_date) if regional else None
    if loading is not None and (not builds or loading <= builds[0]):
        return [(loading, SHIP_LOAD)]
    if builds:
        return [(day, SHIP_BUILD) for day in builds]
    if partner_org_id is not None:
        request = pending_request(sd, str(stage_code or '')) or {}
        wish = clean_date(request.get('date'))
        if wish:
            return [(datetime.date.fromisoformat(wish), SHIP_WISH)]
    return []


def order_ship_dates(order: Any) -> list[tuple[datetime.date, str]]:
    """``Order`` 한 건의 :func:`ship_dates`(이미 읽은 칸만 — 쿼리 0)."""
    sd = order.structured_data if isinstance(getattr(order, 'structured_data', None), dict) else {}
    return ship_dates(sd, regional=bool(getattr(order, 'is_regional', False)),
                      loading_date=getattr(order, 'shipping_scheduled_date', None),
                      partner_org_id=getattr(order, 'partner_org_id', None),
                      stage_code=getattr(order, 'erp_stage_code', None))


def due_day(days: Iterable[datetime.date], today: datetime.date) -> Optional[datetime.date]:
    """판정 기준 날(도면 마감 · 늦음 · 줄 차례 · 찾기 묶음) — 띠에 놓는 날과 같은 규칙(:func:`placed_days` 의 첫 날):
    내일 이후 가장 가까운 출고일, 없으면 가장 늦은 지난 날(오늘 포함). 출고일이 없으면 None.

    오늘 출고는 이미 나가고 있어(사장님 2026-11-25 "당일은 이미 시공 중") 남은 날이 있으면 그 날로 센다. 마감 · 늦음 계산의
    기준 시각(오늘이 며칠인지)은 그대로 오늘이다.
    """
    placed = placed_days(days, today)
    return placed[0] if placed else None


def build_day(sd: Any, today: datetime.date) -> Optional[datetime.date]:
    """줄의 "시공 11/28" 표에 쓸 진짜 시공일 — 시공일이 여럿이면 :func:`due_day` 와 같은 규칙으로 하나."""
    return due_day((datetime.date.fromisoformat(day) for day in all_construction_dates(sd)), today)


def ship_fields(order: Any, today: datetime.date) -> dict[str, Any]:
    """행에 실을 출고 칸 — ``ship_days`` · ``ship_kind`` · ``ship_due`` · ``ship_mark`` · ``build_day``(쿼리 0).

    ``ship_mark`` = 줄 표 ``{'k': '상차', 'md': '12/1'}`` — 상차 예정일이 적힌 지방 주문(시공일보다 뒤라 시공일에 놓였어도) ·
    희망일로 놓인 협력사 주문. 그 밖은 None(줄의 "시공 11/28" 표가 이미 그 날이다). ``build_day`` = 그 표의 진짜 시공일.
    """
    ship = order_ship_dates(order)
    days = [day for day, _kind in ship]
    kind = ship[0][1] if ship else ''
    # 상차 표 = 적힌 상차 예정일(시공일보다 뒤라 시공일에 놓였어도 보인다 — 어긋남을 알게), 희망일 표 = 희망일로 놓인 주문
    loading = loading_day(getattr(order, 'shipping_scheduled_date', None)) if getattr(order, 'is_regional', False) else None
    marked = (SHIP_LOAD, loading) if loading is not None else ((SHIP_WISH, days[0]) if kind == SHIP_WISH else None)
    mark = {'k': marked[0], 'md': f"{marked[1].month}/{marked[1].day}"} if marked else None
    sd = order.structured_data if isinstance(getattr(order, 'structured_data', None), dict) else {}
    return {'ship_days': days, 'ship_kind': kind, 'ship_due': due_day(days, today), 'ship_mark': mark,
            'build_day': build_day(sd, today)}


def row_ship_days(row: dict[str, Any]) -> list[datetime.date]:
    """행의 출고일. 출고 칸을 싣지 않은 행(작업 시트 창 · 시험이 만든 행)은 ``construction_date`` 하나를 출고일로 본다."""
    if 'ship_days' in row:
        return list(row['ship_days'])
    day = _day(row.get('construction_date'))
    return [day] if day is not None else []


def row_due(row: dict[str, Any]) -> Optional[datetime.date]:
    """행의 판정 기준 날(:func:`due_day`) — 출고 칸이 없는 행은 ``construction_date``."""
    if 'ship_due' in row:
        return row['ship_due']
    return _day(row.get('construction_date'))


def placed_days(days: Iterable[datetime.date], today: datetime.date) -> list[datetime.date]:
    """띠 · 날짜 판에 놓을 날 — 내일 이후 출고일 전부. 하나도 없으면 가장 늦은 지난 날(오늘 포함) 하나, 출고일이 없으면 빈 목록."""
    ordered = sorted(set(days))
    ahead = [day for day in ordered if day > today]
    return ahead if ahead else ordered[-1:]


def pane_key(day: Optional[datetime.date], today: datetime.date) -> str:
    """놓을 날 → 날짜 탭 장 열쇠(``'YYYY-MM-DD'`` · ``recent`` · ``later`` · ``past`` · ``none``).

    날 줄 = 내일 ~ 오늘 + :data:`STRIP_DAYS`. 그 앞(오늘 포함 :data:`PAST_DAYS` 일 전까지) = 지난 7일 장, 더 지남 = 지난 출고일,
    뒤 = 그 뒤.
    """
    if day is None:
        return PANE_NONE
    if day < today - datetime.timedelta(days=PAST_DAYS):
        return PANE_PAST
    if day <= today:
        return PANE_RECENT
    if day > today + datetime.timedelta(days=STRIP_DAYS):
        return PANE_LATER
    return day.isoformat()


def pane_slots(row: dict[str, Any], today: datetime.date) -> list[tuple[str, Optional[datetime.date]]]:
    """행이 서는 장 ``[(열쇠, 그 장에 놓은 날)]`` — 같은 장은 한 번(그 뒤 장에 남은 날이 여럿이어도 한 번). 출고일이 없으면 ``none`` 하나."""
    slots: list[tuple[str, Optional[datetime.date]]] = []
    for day in placed_days(row_ship_days(row), today):
        key = pane_key(day, today)
        if all(key != k for k, _d in slots):
            slots.append((key, day))
    return slots or [(PANE_NONE, None)]


def _build_on(start: str, end: str | None = None) -> Any:
    """일정 표(출고 화면과 같은 표)에 ``start`` ~ ``end``(없으면 끝 없음) 시공일 줄이 있는 주문(EXISTS — 쿼리 수는 그대로)."""
    on = [OrderScheduleDate.kind == 'construction', OrderScheduleDate.date >= start]
    if end is not None:
        on.append(OrderScheduleDate.date <= end)
    return Order.schedule_dates.any(and_(*on))


def _loading_sql() -> tuple[Any, Any]:
    """(상차 예정일 앞 10자 글, 그 글이 날짜 꼴인가) — :func:`loading_day` 와 같은 꼴 규칙의 SQL.

    SQLite(시험) · PostgreSQL(운영)에서 같은 뜻이 되게 ``trim`` · ``substr`` · 같음(``IN``)만 쓴다 — 정규식 · ``GLOB`` 은 DB 마다
    다르고, 글자 크기 견주기(``BETWEEN``)는 운영 PostgreSQL 정렬 규칙(en_US)에서 한글 · 기호가 다르게 놓일 수 있다.
    """
    text = func.substr(func.trim(func.coalesce(Order.shipping_scheduled_date, '')), 1, 10)
    shape = and_(*(func.substr(text, i, 1).in_(_DIGITS) for i in (1, 2, 3, 4)),
                 func.substr(text, 5, 1) == '-', func.substr(text, 6, 2).in_(_MONTHS),
                 func.substr(text, 8, 1) == '-', func.substr(text, 9, 2).in_(_MDAYS))
    return text, shape


def _by_loading() -> Any:
    """SQL 로 본 ① 갈래 — 날짜 꼴 상차 예정일이 적힌 지방 주문이고 시공일(일정 표)이 없거나 상차 예정일이 가장 이른 시공일과 같거나 앞.

    NULL 이 되지 않게 짰다(``IS TRUE`` · ``coalesce`` · 서브쿼리 NULL 은 ``IS NULL`` 갈래가 받는다).
    """
    first_build = (select(func.min(OrderScheduleDate.date))
                   .where(OrderScheduleDate.order_id == Order.id, OrderScheduleDate.kind == 'construction')
                   .correlate(Order).scalar_subquery())
    loading, shape = _loading_sql()
    return and_(Order.is_regional.is_(True), shape, or_(first_build.is_(None), loading <= first_build))


def live_condition(cutoff: str) -> Any:
    """첫 화면이 **다** 읽는 주문 — 출고일이 ``cutoff``('YYYY-MM-DD') 뒤일 수 있는 주문(캡 · 경계는 납작 열만 보면 틀린다).

    :func:`ship_dates` 와 같은 갈래: 상차 예정일로 놓이는 지방 주문(:func:`_by_loading`)은 상차 예정일이 ``cutoff`` 뒤일 때,
    나머지는 납작 열(처음 적힌 시공일 하루)이 오래됐어도 다른 시공일(일정 표)이 ``cutoff`` 뒤일 때 다 읽는다. 시공일이 없는
    협력사 주문은 납작 열이 비어 늘 읽힌다. 각 갈래가 NULL 이 되지 않게 짰다 — ``not_(live_condition(c))`` 가 정확한 나머지다.
    """
    flat = Order.erp_construction_date
    by_loading = _by_loading()
    return or_(
        and_(by_loading, _loading_sql()[0] >= cutoff),
        and_(not_(by_loading), or_(flat.is_(None), flat == '', flat >= cutoff, _build_on(cutoff))),
    )


def window_condition(start: str, end: str) -> Any:
    """출고일이 ``start`` ~ ``end`` 안일 수 있는 주문(넉넉한 후보 — 정확한 날은 파이썬이 :func:`ship_dates` 로 다시 센다).

    도면 마감 자동 알림(``notifications/drawing_deadline_plan.due_alerts``)이 화면과 같은 출처로 후보를 고른다: 납작 열 ·
    일정 표 시공일 · 지방 상차 예정일 · 시공일 없이 희망일만 있을 수 있는 협력사 주문(희망일은 JSONB 라 SQL 에서 고르지 않는다).
    """
    flat = Order.erp_construction_date
    loading, shape = _loading_sql()
    return or_(
        and_(flat >= start, flat <= end), _build_on(start, end),
        and_(Order.is_regional.is_(True), shape, loading >= start, loading <= end),
        and_(Order.partner_org_id.isnot(None), or_(flat.is_(None), flat == '')),
    )


def kind_word(kind: Any) -> str:
    """늦음 줄 · 마우스 글의 날 이름 — 놓인 날의 종류('시공' · '상차' · '희망일'). 모르면 '시공'(사장님 2026-11-25 "놓인 날의 이름으로")."""
    return kind if kind in (SHIP_BUILD, SHIP_LOAD, SHIP_WISH) else SHIP_BUILD


__all__ = [
    'PAST_DAYS', 'STRIP_DAYS', 'SHIP_BUILD', 'SHIP_LOAD', 'SHIP_WISH', 'build_day', 'due_day', 'kind_word', 'live_condition',
    'loading_day',
    'order_ship_dates', 'pane_key', 'pane_slots', 'placed_days', 'row_due', 'row_ship_days', 'ship_dates', 'ship_fields',
    'window_condition',
]
