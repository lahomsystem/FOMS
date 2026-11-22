"""생산팀 첫 화면 탭 "날짜"(안 3) 읽기 모델 — 설계서 §12.3. :mod:`production_home_read_model` 에서 옮겼다(파일 500줄 래칫).

import 는 한 방향(이 모듈 → ``production_home_read_model``)만 — 거꾸로 import 하면 순환이 된다.
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.datetime_kst import get_today_kst
from foms.services.production.drawing_arrival import NO_DATE_WAIT_HEAD, arrival_line, wait_head_for_day
from foms.services.production_home_read_model import (
    PRODUCTION_HOME_PAST_DAYS,
    _WEEKDAY_KO,
    _parse_date,
    production_home_day,
)


#: 날짜 탭 왼쪽 띠에 서는 날 수(오늘 포함). 앞에 '지난 7일', 뒤에 '그 뒤' 한 줄씩 붙어 13줄.
PRODUCTION_HOME_STRIP_DAYS = 11
_BAR_ORDER = ('f', 'p', 'w', 'x')  # 막대 색 순서: 제작 완료 · 만드는 중 · 제작 대기 · 도면·컨펌 기다림


def _row_bar_kind(row: dict[str, Any]) -> str:
    view = row.get('home_view')
    if view == 'done' or row.get('home_stage') == '검수 끝':
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
    make_rows = sorted((r for r in rows if r.get('home_view') == 'prod'), key=_make_sort_key)
    bucket = {
        'key': key, 'label': label, 'sub': sub, 'title': title, 'total': total, 'segs': segs,
        'make': len(make_rows), 'make_rows': make_rows,
        'wait_rows': [r for r in rows if r.get('home_view') == 'wait'],
        'done_rows': [r for r in rows if r.get('home_view') == 'done'],
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
    """탭 "날짜"(안 3, 사용자 11-10 "3안으로"): 왼쪽 2주 띠(시공일마다 막대 + 도면 글 + 만들 것/전체) + 오른쪽 고른 날.

    띠 = 지난 7일(한 줄) · 오늘부터 ``PRODUCTION_HOME_STRIP_DAYS`` 일 · 그 뒤(한 줄). 띠 아래 = 지난 시공일(7일 넘음) ·
    시공일 없음. 오른쪽은 **그날 시공 주문만**(설계서 2026-11-22-production-drawing-arrival-upgrade §5-2 — 사장님 "당일 것만"):
    도면·컨펌 기다림(작은 칸 + 막힌 까닭 · 담당) → 만들 것(제작 대기~검수 끝·보류, 큰 줄) → 제작 완료(작은 칸). 다른 날로 아래를
    채우던 미리 보기 · 밀린 것은 뺐다(주문이 적은 날은 아래가 빈다 — 사장님 승인). ``selected`` 가 없거나 모르는 값이면 오늘
    (오늘이 비었으면 일이 있는 가장 가까운 장).

    ``focus_order``(주소 ``order=`` · 옛 ``focus_order=`` — 알림 · 검색 · 주문 목록 바로가기, 설계서 2026-11-21-production-pc-viewer
    §9-10): ``selected`` 가 없거나 모르는 값이면 그 주문이 든 장을 고르고, 그 행에 ``home_focus`` 를 켠다(줄 테두리). 장 고르기는
    사용자가 고른 것과 같이 친다(``auto`` False — [다시 받기]가 그 날을 지킨다). 그 주문이 행에 없으면 지금처럼 고른다.
    """
    today = today or get_today_kst()
    recent_from = today - datetime.timedelta(days=PRODUCTION_HOME_PAST_DAYS)
    last = today + datetime.timedelta(days=PRODUCTION_HOME_STRIP_DAYS - 1)
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        day = _parse_date(row.get('construction_date'))
        if day is None:
            key = 'none'
        elif day < recent_from:
            key = 'past'
        elif day < today:
            key = 'recent'
        elif day > last:
            key = 'later'
        else:
            key = day.isoformat()
        by_key.setdefault(key, []).append(row)

    def _md(day: datetime.date) -> str:
        return f"{day.month}/{day.day}"

    yesterday = today - datetime.timedelta(days=1)
    strip = [_home_bucket(
        'recent', '지난 7일', f"{_md(recent_from)}~{_md(yesterday)}", f"지난 7일 {_md(recent_from)}~{_md(yesterday)}",
        by_key.get('recent', []), today, show_day=True,
    )]
    for offset in range(PRODUCTION_HOME_STRIP_DAYS):
        day = today + datetime.timedelta(days=offset)
        weekday = _WEEKDAY_KO[day.weekday()]
        strip.append(_home_bucket(
            day.isoformat(),
            f"오늘 {_md(day)}" if offset == 0 else _md(day),
            weekday if offset == 0 else f"{weekday} · {'내일' if offset == 1 else f'D-{offset}'}",
            production_home_day(day, today)['label'],
            by_key.get(day.isoformat(), []), today,
            is_today=offset == 0, is_weekend=day.weekday() >= 5, wait_head=wait_head_for_day(day, today),
        ))
    after = last + datetime.timedelta(days=1)
    strip.append(_home_bucket('later', '그 뒤', f"{_md(after)}~", f"{_md(after)} 뒤", by_key.get('later', []), today,
                              show_day=True))
    footer = [
        _home_bucket(
            'past', '지난 시공일', f"{PRODUCTION_HOME_PAST_DAYS}일 넘음", f"지난 시공일 ({PRODUCTION_HOME_PAST_DAYS}일 넘음)",
            by_key.get('past', []), today, show_day=True,
            note=f"더 오래된 {past_hidden}건은 안 보여요" if past_hidden else '', hidden=past_hidden,
        ),
        _home_bucket('none', '시공일 없음', '', '시공일 없음', by_key.get('none', []), today, wait_head=dict(NO_DATE_WAIT_HEAD)),
    ]
    panes = strip + footer
    key = str(selected or '')
    auto = not any(p['key'] == key for p in panes)  # True = 사용자가 고른 날이 아니라 자동으로 고른 장(R3)
    focus = None
    if focus_order is not None:
        for bucket_key, bucket_rows in by_key.items():
            row = next((r for r in bucket_rows if r.get('id') == focus_order), None)
            if row is not None:
                row['home_focus'] = True
                focus = focus_order
                if auto:
                    key, auto = bucket_key, False
                break
    if auto:
        # 처음 여는 장 = 오늘. 오늘이 비었으면 일이 있는 가장 가까운 장(오늘 뒤 → 그 뒤 → 지난 7일 → 지난 시공일 → 시공일 없음)
        # — 스테이징처럼 앞날 주문이 없어도 첫 화면이 빈 장이 아니다(사용자 11-10 ②).
        nearest = strip[1:] + [strip[0]] + footer
        key = next((b['key'] for b in nearest if b['total']), today.isoformat())
    return {'strip': strip, 'footer': footer, 'panes': panes, 'selected': key, 'auto': auto, 'today_key': today.isoformat(),
            'focus': focus}
