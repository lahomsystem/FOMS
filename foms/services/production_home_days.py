"""생산팀 첫 화면 탭 "날짜"(안 3) 읽기 모델 — 설계서 §12.3. :mod:`production_home_read_model` 에서 옮겼다(파일 500줄 래칫).

import 는 한 방향(이 모듈 → ``production_home_read_model``)만 — 거꾸로 import 하면 순환이 된다.
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.datetime_kst import get_today_kst
from foms.services.production_home_read_model import (
    PRODUCTION_HOME_PAST_DAYS,
    _WEEKDAY_KO,
    _parse_date,
    production_home_day,
)


#: 날짜 탭 왼쪽 띠에 서는 날 수(오늘 포함). 앞에 '지난 7일', 뒤에 '그 뒤' 한 줄씩 붙어 13줄.
PRODUCTION_HOME_STRIP_DAYS = 11
PREVIEW_MAX_ROWS = 6  # 날짜 한 장 아래 미리 보기 줄 수 상한(다음에 만들 것 + 밀린 것 합)
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


def _home_bucket(key: str, label: str, sub: str, title: str, rows: list[dict[str, Any]], **flags: Any) -> dict[str, Any]:
    """띠 한 줄 + 오른쪽 한 장. 막대는 SVG 가로 100 기준 좌표(x, w) — 템플릿에 인라인 style 을 쓰지 않으려고."""
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
        'is_today': False, 'is_weekend': False, 'show_day': False, 'note': '', 'hidden': 0, 'previews': [],
    }
    bucket.update(flags)
    return bucket


def production_home_days(
    rows: list[dict[str, Any]], today: datetime.date | None = None, selected: Any = None, *, past_hidden: int = 0
) -> dict[str, Any]:
    """탭 "날짜"(안 3, 사용자 11-10 "3안으로"): 왼쪽 2주 띠(시공일마다 막대 + 만들 것/전체) + 오른쪽 고른 날.

    띠 = 지난 7일(한 줄) · 오늘부터 ``PRODUCTION_HOME_STRIP_DAYS`` 일 · 그 뒤(한 줄). 띠 아래 = 지난 시공일(7일 넘음) ·
    시공일 없음. 오른쪽은 그날의 만들 것(제작 대기~검수 끝·보류)을 큰 줄로, 도면·컨펌 기다림과 제작 완료는 작은 칸으로.
    날짜 한 장 아래에는 뒤 장들(그 뒤 포함)의 만들 것과 모자라면 밀린 지난 7일을 6줄까지 미리 보여 화면이 비지 않게 한다. ``selected`` 가 없거나 모르는 값이면 오늘
    (오늘이 비었으면 일이 있는 가장 가까운 장).
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
        by_key.get('recent', []), show_day=True,
    )]
    for offset in range(PRODUCTION_HOME_STRIP_DAYS):
        day = today + datetime.timedelta(days=offset)
        weekday = _WEEKDAY_KO[day.weekday()]
        strip.append(_home_bucket(
            day.isoformat(),
            f"오늘 {_md(day)}" if offset == 0 else _md(day),
            weekday if offset == 0 else f"{weekday} · {'내일' if offset == 1 else f'D-{offset}'}",
            production_home_day(day, today)['label'],
            by_key.get(day.isoformat(), []),
            is_today=offset == 0, is_weekend=day.weekday() >= 5,
        ))
    after = last + datetime.timedelta(days=1)
    strip.append(_home_bucket('later', '그 뒤', f"{_md(after)}~", f"{_md(after)} 뒤", by_key.get('later', []), show_day=True))
    footer = [
        _home_bucket(
            'past', '지난 시공일', f"{PRODUCTION_HOME_PAST_DAYS}일 넘음", f"지난 시공일 ({PRODUCTION_HOME_PAST_DAYS}일 넘음)",
            by_key.get('past', []), show_day=True,
            note=f"더 오래된 {past_hidden}건은 안 보여요" if past_hidden else '', hidden=past_hidden,
        ),
        _home_bucket('none', '시공일 없음', '', '시공일 없음', by_key.get('none', [])),
    ]
    recent = strip[0]
    for index, bucket in enumerate(strip):
        # 미리 보기 = 최대 6줄을 채우는 묶음들(M4 §18): 이 장 뒤 장들(그 뒤 포함)의 만들 것을 띠 순서로 이어 붙이고,
        # 모자라면 남은 자리만큼 밀린 것(지난 7일). 자기 자신은 안 단다 — 지난 7일 장에는 밀린 것이 없다.
        after = [b for b in strip[index + 1:] if b['make_rows']]
        rows_next: list[dict[str, Any]] = []
        used: list[dict[str, Any]] = []
        for nxt in after:
            if len(rows_next) >= PREVIEW_MAX_ROWS:
                break
            rows_next += nxt['make_rows'][:PREVIEW_MAX_ROWS - len(rows_next)]
            used.append(nxt)
        if len(used) == 1:
            bucket['previews'].append({'title': f"{used[0]['title']} 만들 것 {used[0]['make']}", 'hint': '미리 보기',
                                       'show_day': used[0]['show_day'], 'rows': rows_next})
        elif used:
            bucket['previews'].append({'title': f"다음에 만들 것 {sum(b['make'] for b in after)}", 'hint': '미리 보기',
                                       'show_day': True, 'rows': rows_next})
        room = PREVIEW_MAX_ROWS - len(rows_next)
        if room and bucket is not recent and recent['make_rows']:
            bucket['previews'].append({'title': f"지난 7일 만들 것 {recent['make']}", 'hint': '밀린 것',
                                       'show_day': True, 'rows': recent['make_rows'][:room]})
    panes = strip + footer
    key = str(selected or '')
    auto = not any(p['key'] == key for p in panes)  # True = 사용자가 고른 날이 아니라 자동으로 고른 장(R3)
    if auto:
        # 처음 여는 장 = 오늘. 오늘이 비었으면 일이 있는 가장 가까운 장(오늘 뒤 → 그 뒤 → 지난 7일 → 지난 시공일 → 시공일 없음)
        # — 스테이징처럼 앞날 주문이 없어도 첫 화면이 빈 장이 아니다(사용자 11-10 ②).
        nearest = strip[1:] + [strip[0]] + footer
        key = next((b['key'] for b in nearest if b['total']), today.isoformat())
    return {'strip': strip, 'footer': footer, 'panes': panes, 'selected': key, 'auto': auto, 'today_key': today.isoformat()}
