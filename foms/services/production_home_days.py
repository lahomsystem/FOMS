"""생산팀 첫 화면 탭 "날짜"(안 3) 읽기 모델 — 설계서 §12.3. :mod:`production_home_read_model` 에서 옮겼다(파일 500줄 래칫).

import 는 한 방향(이 모듈 → ``production_home_read_model``)만 — 거꾸로 import 하면 순환이 된다.
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.datetime_kst import get_today_kst
from foms.services.production.drawing_arrival import NO_DATE_WAIT_HEAD, arrival_line, wait_head_for_day
from foms.services.production.ship_dates import PANE_PAST, STRIP_DAYS, pane_slots
from foms.services.production_home_read_model import (
    PRODUCTION_HOME_PAST_DAYS,
    _WEEKDAY_KO,
    production_home_day,
)


#: 날짜 탭 왼쪽 띠에 서는 날 수 — **내일부터**(사장님 2026-11-25 "당일은 이미 시공 중 … 내일 부터"). 앞에 '지난 7일'(오늘까지),
#: 뒤에 '그 뒤' 한 줄씩 붙어 13줄(줄 수는 그대로 — 띠 칸 높이 · 줄 나누기 CSS 가 13줄을 잰다).
PRODUCTION_HOME_STRIP_DAYS = STRIP_DAYS
_BAR_ORDER = ('f', 'p', 'w', 'x')  # 막대 색 순서: 제작 완료 · 만드는 중 · 제작 대기 · 도면·컨펌 기다림


def _row_bar_kind(row: dict[str, Any]) -> str:
    view = row.get('home_view')
    if view == 'done' or row.get('home_stage') == '검수 끝' or row.get('fac_done'):  # 내 공장 완료(2공장, §4-14)도 완료 색
        return 'f'
    if view == 'prod':
        return 'w' if row.get('home_stage') == '제작 대기' else 'p'
    return 'x'


def _make_sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
    """만들 것 줄 순서 — 바뀐 것 먼저, 만드는 중(공정이 많이 간 것부터), 제작 대기."""
    done_steps = sum(1 for s in (row.get('home_steps') or []) if s.get('done'))
    return (0 if row.get('has_changes') else 1, {'p': 0, 'w': 1, 'f': 2}.get(_row_bar_kind(row), 3), -done_steps)


def _home_bucket(key: str, label: str, sub: str, title: str, rows: list[dict[str, Any]], today: datetime.date,
                 **flags: Any) -> dict[str, Any]:
    """띠 한 줄 + 오른쪽 한 장. 막대는 SVG 가로 100 기준 좌표(x, w) — 템플릿에 인라인 style 을 쓰지 않으려고.

    ``arrival`` = 도면 글(띠 '도면 5/6 마감 지남' · 장 제목 '도면 5/6 내려옴', 주문이 없으면 None — 설계서
    2026-11-22-production-drawing-arrival-upgrade §5-1 · §5-2). ``wait_head`` = 기다림 묶음 머리의 마감 글(하루 장 · 시공일 없음 장만,
    ``flags`` 로 받는다). 여러 날 장(지난 7일 · 그 뒤 · 지난 시공일)은 머리 대신 칸마다 마감을 쓴다(``show_day``).
    """
    counts = dict.fromkeys(_BAR_ORDER, 0)
    for row in rows:
        counts[_row_bar_kind(row)] += 1
    total = len(rows)
    segs: list[dict[str, Any]] = []
    x = 0.0
    for kind in _BAR_ORDER:
        if counts[kind]:
            width = round(100 * counts[kind] / total, 2)
            segs.append({'k': kind, 'x': round(x, 2), 'w': width})
            x += width
    # 2공장(설계서 2026-11-23 §4-13 · §4-14, factory_home 이 단 칸 — 2공장 그림이 꺼지면 칸이 없어 지금 그대로): 내 공장 완료가
    # 살아 있는 섞인 주문은 '제작 완료' 묶음으로, 남의 공장 장만 있는 줄은 만들 것 묶음 끝 작은 머리 아래(elsewhere_rows)로.
    make_all = sorted((r for r in rows if r.get('home_view') == 'prod' and not r.get('fac_done')), key=_make_sort_key)
    make_rows = [r for r in make_all if not r.get('fac_elsewhere')]
    bucket = {
        'key': key, 'label': label, 'sub': sub, 'title': title, 'total': total, 'segs': segs,
        'make': len(make_all), 'make_rows': make_rows, 'elsewhere_rows': [r for r in make_all if r.get('fac_elsewhere')],
        'wait_rows': [r for r in rows if r.get('home_view') == 'wait'],
        'done_rows': [r for r in rows if r.get('home_view') == 'done' or r.get('fac_done')],
        'is_today': False, 'is_weekend': False, 'show_day': False, 'note': '', 'hidden': 0,
        'arrival': arrival_line(rows, today), 'wait_head': None,
    }
    bucket.update(flags)
    if not bucket['wait_rows']:
        bucket['wait_head'] = None
    return bucket


def production_home_days(
    rows: list[dict[str, Any]], today: datetime.date | None = None, selected: Any = None, *, past_hidden: int = 0,
    focus_order: int | None = None,
) -> dict[str, Any]:
    """탭 "날짜"(안 3, 사용자 11-10 "3안으로"): 왼쪽 2주 띠(출고일마다 막대 + 도면 글 + 만들 것/전체) + 오른쪽 고른 날.

    주문은 출고일(:mod:`foms.services.production.ship_dates` — 출고 화면과 같은 날 · 지방 상차 예정일, 사장님 2026-11-25)로 놓는다:
    내일 이후 출고일마다 그 날 줄에(시공일이 여럿이면 남은 날마다 — 그 뒤 장에는 한 번), 남은 날이 없으면 가장 늦은 지난 날
    (오늘 포함) 하나에. 띠 = 지난 7일(오늘까지, 한 줄) · **내일부터** ``PRODUCTION_HOME_STRIP_DAYS`` 일 · 그 뒤(한 줄) — 오늘
    출고는 이미 나가고 있어 날 줄이 없다(사장님 2026-11-25). 띠 아래 = 지난 출고일(7일 넘음) · 출고일 없음. 오른쪽은 **그날
    출고 주문만**(설계서 2026-11-22-production-drawing-arrival-upgrade §5-2 — 사장님 "당일 것만"): 도면·컨펌 기다림(작은 칸 +
    막힌 까닭 · 담당) → 만들 것(제작 대기~검수 끝·보류, 큰 줄) → 제작 완료(작은 칸). ``selected`` 가 없거나 모르는 값이면 내일
    (내일이 비었으면 일이 있는 가장 가까운 장).

    ``focus_order``(주소 ``order=`` · 옛 ``focus_order=`` — 알림 · 검색 · 주문 목록 바로가기, 설계서 2026-11-21-production-pc-viewer
    §9-10): ``selected`` 가 없거나 모르는 값이면 그 주문이 선 첫 장을 고르고, 그 행에 ``home_focus`` 를 켠다(줄 테두리). 장 고르기는
    사용자가 고른 것과 같이 친다(``auto`` False — [다시 받기]가 그 날을 지킨다). 그 주문이 행에 없으면 지금처럼 고른다.
    """
    today = today or get_today_kst()
    recent_from = today - datetime.timedelta(days=PRODUCTION_HOME_PAST_DAYS)
    last = today + datetime.timedelta(days=PRODUCTION_HOME_STRIP_DAYS)
    placed: dict[str, list[tuple[datetime.date, dict[str, Any]]]] = {}
    first_key: dict[int, str] = {}
    for row in rows:
        slots = pane_slots(row, today)
        first_key.setdefault(id(row), slots[0][0])
        for key, day in slots:
            placed.setdefault(key, []).append((day or datetime.date.min, row))
    # 여러 날 장(지난 7일 · 그 뒤 · 지난 출고일)은 놓은 날 순 — 지난 출고일은 최근 것부터(같은 날은 지금 행 순서)
    by_key = {key: [row for _day, row in sorted(items, key=lambda item: item[0], reverse=key == PANE_PAST)]
              for key, items in placed.items()}

    def _md(day: datetime.date) -> str:
        return f"{day.month}/{day.day}"

    strip = [_home_bucket(
        'recent', '지난 7일', f"{_md(recent_from)}~{_md(today)}", f"지난 7일 {_md(recent_from)}~{_md(today)}",
        by_key.get('recent', []), today, show_day=True,
    )]
    for offset in range(1, PRODUCTION_HOME_STRIP_DAYS + 1):
        day = today + datetime.timedelta(days=offset)
        weekday = _WEEKDAY_KO[day.weekday()]
        strip.append(_home_bucket(
            day.isoformat(), _md(day), f"{weekday} · {'내일' if offset == 1 else f'D-{offset}'}",
            production_home_day(day, today)['label'],
            by_key.get(day.isoformat(), []), today,
            is_weekend=day.weekday() >= 5, wait_head=wait_head_for_day(day, today),
        ))
    after = last + datetime.timedelta(days=1)
    strip.append(_home_bucket('later', '그 뒤', f"{_md(after)}~", f"{_md(after)} 뒤", by_key.get('later', []), today,
                              show_day=True))
    footer = [
        _home_bucket(
            'past', '지난 출고일', f"{PRODUCTION_HOME_PAST_DAYS}일 넘음", f"지난 시공일 ({PRODUCTION_HOME_PAST_DAYS}일 넘음)",
            by_key.get('past', []), today, show_day=True,
            note=f"더 오래된 {past_hidden}건은 안 보여요" if past_hidden else '', hidden=past_hidden,
        ),
        _home_bucket('none', '출고일 없음', '', '시공일 없음', by_key.get('none', []), today, wait_head=dict(NO_DATE_WAIT_HEAD)),
    ]
    panes = strip + footer
    key = str(selected or '')
    auto = not any(p['key'] == key for p in panes)  # True = 사용자가 고른 날이 아니라 자동으로 고른 장(R3)
    focus = None
    if focus_order is not None:
        row = next((r for r in rows if r.get('id') == focus_order), None)
        if row is not None:
            row['home_focus'] = True
            focus = focus_order
            if auto:
                key, auto = first_key[id(row)], False
    if auto:
        # 처음 여는 장 = 내일. 내일이 비었으면 일이 있는 가장 가까운 장(내일 뒤 → 그 뒤 → 지난 7일 → 지난 출고일 → 출고일 없음)
        # — 스테이징처럼 앞날 주문이 없어도 첫 화면이 빈 장이 아니다(사용자 11-10 ②).
        nearest = strip[1:] + [strip[0]] + footer
        key = next((b['key'] for b in nearest if b['total']), strip[1]['key'])
    return {'strip': strip, 'footer': footer, 'panes': panes, 'selected': key, 'auto': auto, 'today_key': today.isoformat(),
            'focus': focus}
