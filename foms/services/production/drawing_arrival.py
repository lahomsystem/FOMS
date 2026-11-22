"""도면 내려옴 · 도면 마감 · 막힌 까닭 · 담당 이름 — 설계서 ``docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md`` §4 · §8.

순수 함수만 둔다(쿼리 0 · 요청 문맥 없음). 값은 첫 화면이 **이미 읽은 행**(단계 · 납작 시공일 · ``structured_data`` ·
``manager_name``)에서 만들고, 공휴일은 ``business_calendar`` 의 파일 캐시를 쓴다(DB 안 읽음).

- 내려옴 = 행 보기 ``home_view != 'wait'``(생산 · 시공 단계, 보류 포함). 도면 상태와 상관없다(§4-1).
- 도면 마감 = 시공일 앞 영업일 둘째 날(:data:`DRAWING_DEADLINE_WORKDAYS`, §4-2). 기준 시공일 = 장을 고르는 납작 칸(§4-6).
- 마감 상태 넷(§4-3): 늦음 빨강 · 빠듯(마감 오늘 · 다음 영업일) 주황 · 다 옴 초록 · 여유 남색. 무채색 없음.
- 막힌 까닭 다섯(§4-4)과 담당 이름(§4-5)은 화면 · 작업 시트 · 늦음 표가 같이 쓴다.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any, Iterable

from foms.services.common.business_calendar import add_business_days
from foms.services.orders.confirm_drawing_gate import effective_drawing_status
from foms.services.orders.erp_policy_permissions import get_assignee_ids

#: 도면이 늦어도 생산에 내려와야 하는 날 = 시공일 앞 영업일 수(사장님 2026-11-22 "늦어도 시공 2영업일 전").
DRAWING_DEADLINE_WORKDAYS = 2

LATE = 'late'
SOON = 'soon'
ALL_IN = 'ok'
CALM = 'calm'
#: 여러 날을 담은 줄은 가장 급한 상태를 쓴다(늦음 > 빠듯 > 여유, §4-3).
_URGENCY = {LATE: 0, SOON: 1, CALM: 2}

#: 막힌 까닭(§4-4) — 열쇠 → 화면 글. ``none`` 은 '담당 없음'(빨강)만.
BLOCKER_LABELS: dict[str, str] = {
    'sales_check': '영업 확인 기다림',
    'customer': '고객 컨펌 기다림',
    'no_owner': '담당 없음',
    'fixing': '도면 고치는 중',
    'drawing': '도면 그리는 중',
}
_WEEKDAY_KO = '월화수목금토일'


def _parse_day(value: Any) -> datetime.date | None:
    """date · 'YYYY-MM-DD…' 글 → date. 비었거나 못 읽으면 None."""
    if isinstance(value, datetime.date):
        return value
    text = str(value or '').strip()[:10]
    try:
        return datetime.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _md(day: datetime.date) -> str:
    """날 → 'M/D (요일)'."""
    return f"{day.month}/{day.day} ({_WEEKDAY_KO[day.weekday()]})"


def day_md(day: datetime.date) -> str:
    """날 → 'M/D (요일)' — 화면 마감 글과 같은 꼴을 자동 알림 글(§9-4) · 작업 시트 '알림 보냄' 줄이 같이 쓴다."""
    return _md(day)


def drawing_deadline(day: datetime.date) -> datetime.date:
    """시공일 → 도면 마감(시공일 앞 영업일 둘째 날 — 주말 · 한국 공휴일 뺌). 마감 날은 늘 영업일이다.

    Args:
        day: 기준 시공일(납작 칸).

    Returns:
        마감 날. 예: 11/25 (수) → 11/23 (월), 11/30 (월) → 11/26 (목).
    """
    return add_business_days(day, -DRAWING_DEADLINE_WORKDAYS)


def deadline_state(deadline: datetime.date | None, today: datetime.date, *, all_in: bool) -> str:
    """마감 상태 — ``'late'`` · ``'soon'`` · ``'ok'`` · ``'calm'``(§4-3).

    Args:
        deadline: 마감 날(시공일이 없으면 None — 다 옴 또는 여유만).
        today: KST 오늘(``get_today_kst()`` 또는 주입한 날).
        all_in: 그 줄의 주문이 모두 내려왔나.

    Returns:
        다 옴이면 ``'ok'``. 아니면 마감 < 오늘 = 늦음, 마감 ≤ 다음 영업일 = 빠듯(금요일의 월요일 마감 포함), 그 밖 여유.
    """
    if all_in:
        return ALL_IN
    if deadline is None:
        return CALM
    if deadline < today:
        return LATE
    if deadline <= add_business_days(today, 1):
        return SOON
    return CALM


def soon_word(deadline: datetime.date, today: datetime.date) -> str:
    """빠듯 마감의 '언제' — 오늘 · 내일 · 그 밖(주말 · 공휴일 너머 다음 영업일)은 요일 이름('월요일')."""
    if deadline == today:
        return '오늘'
    if deadline == today + datetime.timedelta(days=1):
        return '내일'
    return f"{_WEEKDAY_KO[deadline.weekday()]}요일"


def deadline_head(deadline: datetime.date, today: datetime.date, state: str) -> str:
    """하루 장 기다림 묶음 머리 · 작업 시트의 마감 글 — '마감 11/23 (월) 지났어요' · '마감 오늘 11/24 (화)' · '마감 11/26 (목)'."""
    if state == LATE:
        return f"마감 {_md(deadline)} 지났어요"
    word = soon_word(deadline, today) if state == SOON else ''
    if word in ('오늘', '내일'):
        return f"마감 {word} {_md(deadline)}"
    return f"마감 {_md(deadline)}"


def _assignee_names(sd: dict[str, Any]) -> list[str]:
    """도면 담당 이름 — ``drawing_assignees[].name``, 비면 ``shipment.drawing_managers``(같은 쓰기가 함께 남긴다, §4-5)."""
    names: list[str] = []
    for entry in sd.get('drawing_assignees') or []:
        name = entry.get('name') if isinstance(entry, dict) else entry
        name = str(name or '').strip()
        if name and name not in names:
            names.append(name)
    if names:
        return names
    shipment = sd.get('shipment') if isinstance(sd.get('shipment'), dict) else {}
    managers = shipment.get('drawing_managers')
    for entry in managers if isinstance(managers, list) else []:
        name = entry.get('name') if isinstance(entry, dict) else entry
        name = str(name or '').strip()
        if name and name not in names:
            names.append(name)
    return names


def _has_drawing_owner(sd: dict[str, Any], names: Iterable[str]) -> bool:
    """도면 담당이 있나 — 이름이 있거나 id 가 있다(id 읽기 정본 ``get_assignee_ids`` — 주문 객체 대신 같은 칸만 넘긴다)."""
    if list(names):
        return True
    return bool(get_assignee_ids(SimpleNamespace(structured_data=sd), 'DRAWING_DOMAIN'))


def drawing_blocker(sd: Any) -> dict[str, Any]:
    """안 내려온 주문의 막힌 까닭(§4-4, 위에서 처음 맞는 줄). 단계는 까닭을 바꾸지 않는다.

    Args:
        sd: 주문 ``structured_data``(읽기만).

    Returns:
        ``{'key', 'label', 'none'}`` — ``none`` 은 '담당 없음'(빨강)일 때만 True.
    """
    sd = sd if isinstance(sd, dict) else {}
    status = effective_drawing_status(sd, default='')
    if status == 'TRANSFERRED':
        key = 'sales_check'
    elif status in ('CONFIRMED', 'DONE'):
        key = 'customer'
    elif not _has_drawing_owner(sd, _assignee_names(sd)):
        key = 'no_owner'
    elif status == 'RETURNED':
        key = 'fixing'
    else:
        key = 'drawing'
    return {'key': key, 'label': BLOCKER_LABELS[key], 'none': key == 'no_owner'}


def drawing_people(sd: Any, manager_name: Any) -> dict[str, Any]:
    """도면 담당 · 영업 담당 이름(§4-5, 쿼리 0).

    Args:
        sd: 주문 ``structured_data``.
        manager_name: 행 ``manager_name``(빈 값 · '-' 이면 안 쓴다).

    Returns:
        ``{'drawing': [이름…], 'sales': 이름 또는 '', 'parts': ['도면 장미래', '영업 이하늘'], 'text': '도면 장미래 · 영업 이하늘'}``
        — 둘 이상이면 쉼표. ``parts`` 는 화면이 조각마다 한 덩이로 줄을 넘기게(이름이 '영업 / 이하늘' 로 갈리지 않게) 쓴다.
    """
    names = _assignee_names(sd if isinstance(sd, dict) else {})
    sales = str(manager_name or '').strip()
    if sales == '-':
        sales = ''
    parts = []
    if names:
        parts.append('도면 ' + ', '.join(names))
    if sales:
        parts.append(f"영업 {sales}")
    return {'drawing': names, 'sales': sales, 'parts': parts, 'text': ' · '.join(parts)}


def attach_drawing_arrival(rows: list[dict[str, Any]], today: datetime.date) -> None:
    """기다림 행(``home_view == 'wait'``)에 ``dw_deadline`` · ``dw_deadline_md`` · ``dw_state`` · ``dw_blocker`` · ``dw_people`` 을 단다.

    날짜마다 마감은 한 번만 센다. 내려온 행에는 아무것도 달지 않는다(그 행의 도면 글은 지금 그대로).

    Args:
        rows: ``build_production_home`` 행(``construction_date`` = 납작 칸 · ``structured_data`` · ``manager_name``).
        today: KST 오늘.
    """
    deadlines: dict[datetime.date, datetime.date] = {}
    for row in rows:
        if row.get('home_view') != 'wait':
            continue
        day = _parse_day(row.get('construction_date'))
        deadline = None
        if day is not None:
            if day not in deadlines:
                deadlines[day] = drawing_deadline(day)
            deadline = deadlines[day]
        sd = row.get('structured_data') or {}
        row['dw_deadline'] = deadline
        row['dw_deadline_md'] = f"{deadline.month}/{deadline.day}" if deadline else ''
        row['dw_state'] = deadline_state(deadline, today, all_in=False)
        row['dw_blocker'] = drawing_blocker(sd)
        row['dw_people'] = drawing_people(sd, row.get('manager_name'))


def _wait_state(row: dict[str, Any], today: datetime.date) -> tuple[str, datetime.date | None]:
    """기다림 행 하나의 (상태, 마감) — 단 값이 있으면 그것, 없으면(시험 · 단 값을 안 단 행) 그 자리에서 센다."""
    if 'dw_state' in row:
        return row['dw_state'], row.get('dw_deadline')
    day = _parse_day(row.get('construction_date'))
    deadline = drawing_deadline(day) if day is not None else None
    return deadline_state(deadline, today, all_in=False), deadline


def arrival_line(rows: list[dict[str, Any]], today: datetime.date) -> dict[str, Any] | None:
    """한 줄(띠 한 줄 · 장 · 찾기 묶음)의 도면 글 — 주문이 없으면 None.

    Args:
        rows: 그 줄의 행(제작 완료 포함).
        today: KST 오늘.

    Returns:
        ``{'x', 'n', 'state', 'strip', 'pane'}`` — ``strip`` = '도면 5/6 마감 지남' · '도면 3/7 마감 내일' · '도면 5/5 다 옴' ·
        '도면 0/4', ``pane`` = '도면 5/6 내려옴'. 여러 날을 담은 줄은 주문마다 상태를 매겨 가장 급한 것(§4-3).
    """
    total = len(rows)
    if not total:
        return None
    waiting = [_wait_state(r, today) for r in rows if r.get('home_view') == 'wait']
    arrived = total - len(waiting)
    if not waiting:
        state, suffix = ALL_IN, ' 다 옴'
    else:
        state = min((s for s, _d in waiting), key=lambda s: _URGENCY.get(s, 2))
        suffix = {LATE: ' 마감 지남', CALM: ''}.get(state, '')
        if state == SOON:
            nearest = min(d for s, d in waiting if s == SOON and d is not None)
            suffix = f" 마감 {soon_word(nearest, today)}"
    return {'x': arrived, 'n': total, 'state': state,
            'strip': f"도면 {arrived}/{total}{suffix}", 'pane': f"도면 {arrived}/{total} 내려옴"}


def wait_head_for_day(day: datetime.date, today: datetime.date) -> dict[str, Any]:
    """하루 장 기다림 묶음 머리의 마감 글 — ``{'text', 'state'}``(그날 주문은 마감이 같아 머리에 한 번만, §5-2)."""
    deadline = drawing_deadline(day)
    state = deadline_state(deadline, today, all_in=False)
    return {'text': deadline_head(deadline, today, state), 'state': state if state in (LATE, SOON) else ''}


#: 시공일 없음 장 기다림 묶음 머리(§4-6).
NO_DATE_WAIT_HEAD = {'text': '시공일이 없어 마감이 없어요', 'state': ''}


def sheet_wait_view(sd: Any, construction_date: Any, manager_name: Any, today: datetime.date) -> dict[str, Any]:
    """작업 시트 도면 칸의 안 내려온 주문 글(§5-7) — 까닭 · 담당 · 마감. 안 내려온 주문에만 부른다(쿼리 0).

    Args:
        sd: 주문 ``structured_data``.
        construction_date: 기준 시공일(납작 칸 ``erp_construction_date`` — 첫 화면 장과 같은 날, §4-6).
        manager_name: 영업 담당 이름(첫 화면 행 ``manager_name`` 과 같은 규칙).
        today: KST 오늘.

    Returns:
        ``{'blocker', 'people', 'deadline': {'text', 'state'}, 'alert_line'}``. ``alert_line`` 은 P3 자동 알림(§9-6)이
        '알림 보냄 …' 을 채울 자리 — 지금은 늘 빈 글이라 화면에 아무것도 안 그린다.
    """
    sd = sd if isinstance(sd, dict) else {}
    day = _parse_day(construction_date)
    if day is None:
        head = dict(NO_DATE_WAIT_HEAD)
    else:
        deadline = drawing_deadline(day)
        state = deadline_state(deadline, today, all_in=False)
        head = {'text': deadline_head(deadline, today, state), 'state': state if state in (LATE, SOON) else ''}
    return {'blocker': drawing_blocker(sd), 'people': drawing_people(sd, manager_name), 'deadline': head, 'alert_line': ''}
