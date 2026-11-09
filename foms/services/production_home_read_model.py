"""생산팀 첫 화면(전체 주문 한 줄) 읽기 모델 — 설계서 §12 (2026-11-09, D10·D12).

도면 기다리는 주문부터 시공 단계까지 **시공일 순 한 줄**. 칸반(:mod:`production_read_model`)과
같은 쿼리 빌더를 쓰되 단계 목록만 도면까지 넓힌다. 금액은 어디에도 싣지 않는다(D7).

- 큰 글자(지금 단계)는 :func:`production_home_stage` — "도면 기다림 / 컨펌 기다림 / 제작 대기 /
  <공정> 중 / 검수 끝 / 제작 완료 / 보류".
- 날짜 머리줄은 :func:`production_home_day` — "오늘 11/9 (월)", "11/12 (목) · D-3", "시공일 없음".
- 공정 4칸은 ``structured_data['production']['steps']`` 그대로(API 가 처음 접근 때 만들기 전이면
  4칸 모두 미완으로 그린다). 정의는 ``foms/api/production/orders.py`` 의 ``_PRODUCTION_STEP_DEFS``
  와 같아야 한다(``tests/domains/test_production_home.py`` 가 고정).
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.datetime_kst import get_today_kst
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.production_change_alerts import collect_production_change_alerts
from foms.services.production_dashboard_display import build_production_home_enriched_rows
from foms.services.production_read_model import (
    PRODUCTION_BASE_STAGE_CODES,
    PRODUCTION_KANBAN_MAX_ROWS,
    apply_production_dashboard_sort,
    build_production_orders_query,
    fetch_production_current_run_ids,
)

#: 첫 화면에 싣는 단계 — 도면 + 칸반 단계(고객컨펌·생산·시공). 접수·실측은 생산과 무관해 뺀다.
PRODUCTION_HOME_STAGE_CODES: tuple[str, ...] = ('도면', 'DRAWING') + PRODUCTION_BASE_STAGE_CODES

#: 공정 4단계(key, 라벨). API ``_PRODUCTION_STEP_DEFS`` 와 같은 순서·값. 도장은 우리 공장에 없어 뺐다(D15, 11-09).
#: 옛 주문에 남은 ``paint`` 항목은 여기 없으니 자연히 걸러진다.
PRODUCTION_HOME_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("cut", "재단"),
    ("edge", "엣지"),
    ("assemble", "조립"),
    ("inspect", "검수"),
)

_WEEKDAY_KO = '월화수목금토일'
_DRAWING_STAGES = ('DRAWING', '도면')
_CONFIRM_STAGES = ('CONFIRM', '고객컨펌')
_PRODUCTION_STAGES = ('PRODUCTION', '생산')
_CONSTRUCTION_STAGES = ('CONSTRUCTION', '시공')


def production_home_steps(sd: dict[str, Any], *, mark_now: bool) -> list[dict[str, Any]]:
    """공정 4칸 — ``{key, label, done, now}``. ``mark_now`` 면 첫 미완 칸을 '지금 여기'로 표시한다."""
    prod = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    raw = prod.get('steps') if isinstance(prod.get('steps'), list) else []
    done_by_key: dict[str, bool] = {}
    for item in raw:
        if isinstance(item, dict) and item.get('key'):
            done_by_key[str(item['key'])] = bool(item.get('done'))
    steps: list[dict[str, Any]] = []
    now_taken = False
    for key, label in PRODUCTION_HOME_STEP_DEFS:
        done = done_by_key.get(key, False)
        now = bool(mark_now and not done and not now_taken)
        if now:
            now_taken = True
        steps.append({'key': key, 'label': label, 'done': done, 'now': now})
    return steps


def production_home_stage(
    raw_stage: str | None, has_run: bool, steps: list[dict[str, Any]], hold_active: bool
) -> tuple[str, str, str]:
    """(큰 글자, 작은 글자, 보기 키). 보기 키는 탭 필터용 ``wait | prod | done``."""
    if hold_active:
        return '보류', '생산', 'prod'
    if raw_stage in _DRAWING_STAGES:
        return '도면 기다림', '도면팀', 'wait'
    if raw_stage in _CONFIRM_STAGES:
        return '컨펌 기다림', '영업', 'wait'
    if raw_stage in _PRODUCTION_STAGES:
        if not has_run:
            return '제작 대기', '생산', 'prod'
        for step in steps:
            if not step['done']:
                return f"{step['label']} 중", '생산', 'prod'
        return '검수 끝', '생산', 'prod'
    if raw_stage in _CONSTRUCTION_STAGES:
        return '제작 완료', '시공 대기', 'done'
    return (raw_stage or '-'), '', 'wait'


def _parse_date(value: Any) -> datetime.date | None:
    if isinstance(value, datetime.date):
        return value
    text = str(value or '').strip()[:10]
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def production_home_day(construction_date: Any, today: datetime.date) -> dict[str, Any]:
    """날짜 머리줄 — ``{key, label, sub, is_today}``. 시공일이 없으면 맨 뒤 '시공일 없음'."""
    day = _parse_date(construction_date)
    if day is None:
        return {'key': 'none', 'label': '시공일 없음', 'sub': '', 'is_today': False}
    md = f"{day.month}/{day.day} ({_WEEKDAY_KO[day.weekday()]})"
    delta = (day - today).days
    if delta == 0:
        return {'key': day.isoformat(), 'label': f"오늘 {md}", 'sub': '', 'is_today': True}
    if delta == 1:
        return {'key': day.isoformat(), 'label': f"내일 {md}", 'sub': '', 'is_today': False}
    if delta < 0:
        return {'key': day.isoformat(), 'label': md, 'sub': f"{-delta}일 지남", 'is_today': False}
    return {'key': day.isoformat(), 'label': md, 'sub': f"D-{delta}", 'is_today': False}


def _change_line(alerts: list[dict[str, Any]]) -> str:
    if not alerts:
        return ''
    first = alerts[0]
    label = str(first.get('label') or '').strip()
    detail = str(first.get('detail') or '').strip()
    if first.get('kind') == 'construction_date' and first.get('to_md'):
        detail = f"{first.get('from_md') or '미정'} → {first.get('to_md')}"
    line = f"{label} {detail}".strip()
    if len(alerts) > 1:
        line = f"{line} · 그 외 {len(alerts) - 1}건"
    return line


#: 시공일이 이보다 더 지난 주문은 맨 아래 "지난 시공일" 한 묶음으로 모은다(스테이징 실측 11-09: 139일 지난
#: 도면 대기 주문이 첫 줄에 오고 33묶음 중 대부분이 지난 날짜였다 — 작업자에겐 오늘·이번 주가 먼저다).
PRODUCTION_HOME_PAST_DAYS = 7
PAST_GROUP_KEY = 'past'


def production_home_groups(rows: list[dict[str, Any]], today: datetime.date | None = None) -> list[dict[str, Any]]:
    """날짜 묶음(모바일 실측 탭처럼 접었다 펴는 단위). 행은 이미 시공일 순이라 연속 구간만 자른다.

    - 시공일이 ``PRODUCTION_HOME_PAST_DAYS`` 보다 더 지난 행은 맨 아래 "지난 시공일" 한 묶음(접힘)으로.
      일주일 안에 지난 것은 아직 급한 일이라 제자리(맨 위)에 둔다.
    - 처음 펼쳐 두는 묶음 = 오늘·내일. 둘 다 없으면 첫 묶음 하나만 펼친다(화면이 비어 보이지 않게).
    """
    today = today or get_today_kst()
    cutoff = today - datetime.timedelta(days=PRODUCTION_HOME_PAST_DAYS)
    groups: list[dict[str, Any]] = []
    past: dict[str, Any] = {
        'key': PAST_GROUP_KEY, 'label': f"지난 시공일 ({PRODUCTION_HOME_PAST_DAYS}일 넘음)", 'sub': '',
        'is_today': False, 'is_open': False, 'rows': [], 'changed': 0,
    }
    for row in rows:
        day = _parse_date(row.get('day_key'))
        if day is not None and day < cutoff:
            past['rows'].append(row)
            if row.get('has_changes'):
                past['changed'] += 1
            continue
        if not groups or groups[-1]['key'] != row['day_key']:
            groups.append({
                'key': row['day_key'],
                'label': row['day_label'],
                'sub': row['day_sub'],
                'is_today': bool(row['day_is_today']),
                'is_open': bool(row['day_is_today']) or str(row['day_label']).startswith('내일'),
                'rows': [],
                'changed': 0,
            })
        groups[-1]['rows'].append(row)
        if row.get('has_changes'):
            groups[-1]['changed'] += 1
    if groups and not any(g['is_open'] for g in groups):
        groups[0]['is_open'] = True
    if past['rows']:
        for row in past['rows']:
            row['day_key'] = PAST_GROUP_KEY  # 카드의 data-day 가 묶음 키와 같아야 거르기가 맞다
        groups.append(past)
    for group in groups:
        group['count'] = len(group['rows'])
    return groups


def _monday_of(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def production_home_week(
    rows: list[dict[str, Any]], today: datetime.date, week_start: Any = None
) -> dict[str, Any]:
    """탭 "이번 주"(안 4): 월~토 6칸(일요일에 일이 있으면 7칸)에 시공일 기준으로 주문을 놓는다.

    출고·시공은 같은 날짜 키(상차 = 시공일)라 한 칸에 단계 색으로 가른다: 생산 전 / 생산 중 / 제작 완료.
    ``week_start`` 는 그 주 월요일(ISO 문자열 또는 date). 없거나 못 읽으면 오늘의 주.
    """
    start = _parse_date(week_start) if week_start is not None else None
    start = _monday_of(start or today)
    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = row.get('construction_date')
        day = _parse_date(key)
        if day is None:
            continue
        by_day.setdefault(day.isoformat(), []).append(row)
    days: list[dict[str, Any]] = []
    for offset in range(7):
        day = start + datetime.timedelta(days=offset)
        events = by_day.get(day.isoformat(), [])
        if offset == 6 and not events:
            break  # 일요일은 일이 있을 때만
        days.append({
            'key': day.isoformat(),
            'num': day.day,
            'weekday': _WEEKDAY_KO[day.weekday()],
            'is_today': day == today,
            'is_past': day < today,
            'events': events,
            'count_wait': sum(1 for r in events if r.get('home_view') == 'wait'),
            'count_prod': sum(1 for r in events if r.get('home_view') == 'prod'),
            'count_done': sum(1 for r in events if r.get('home_view') == 'done'),
        })
    end = start + datetime.timedelta(days=len(days) - 1 if days else 5)
    return {
        'start': start.isoformat(),
        'label': f"{start.month}/{start.day} ({_WEEKDAY_KO[start.weekday()]}) – {end.month}/{end.day} ({_WEEKDAY_KO[end.weekday()]})",
        'is_this_week': start == _monday_of(today),
        'prev': (start - datetime.timedelta(days=7)).isoformat(),
        'next': (start + datetime.timedelta(days=7)).isoformat(),
        'this': _monday_of(today).isoformat(),
        'days': days,
        'total': sum(len(d['events']) for d in days),
    }


def production_home_inbox(rows: list[dict[str, Any]], tombstones: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """탭 "이번 주" 오른쪽 받은함: 미확인 변경(주문마다 한 장, 알림 여러 줄) + 취소된 주문(묘비).

    [확인했어요] 는 기존 change-ack API(사람마다 확인). 순서 = 시공일 순(행 순서 그대로), 묘비는 뒤.
    """
    items: list[dict[str, Any]] = []
    for row in rows:
        alerts = row.get('home_alerts') or []
        if not alerts:
            continue
        items.append({
            'kind': 'change',
            'id': row['id'],
            'customer_name': row.get('customer_name') or '-',
            'product_label': row.get('v3_product_label') or '',
            'stage': row.get('home_stage') or '',
            'day_label': row.get('day_label') or '',
            'alerts': alerts,
        })
    for tomb in tombstones or []:
        items.append({
            'kind': 'cancelled',
            'id': tomb.get('id'),
            'customer_name': tomb.get('customer_name') or '-',
            'product_label': tomb.get('product_label') or '',
            'stage': '주문 취소',
            'day_label': f"취소 {tomb.get('deleted_md')}" if tomb.get('deleted_md') else '취소됨',
            'alerts': [{'kind': 'cancelled', 'label': '주문 취소', 'detail': '만들고 있었다면 멈춰요'}],
        })
    return items


def production_home_step_queues(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """탭 "내 공정"(안 3): 공정 5탭, 그 공정이 첫 미완인 제작 중 주문만 줄로. 일의 양은 안 보인다(D11).

    보류 중인 주문은 줄에 두되 [끝] 단추 없이 '보류' 글만. 제작 대기(run 없음)·검수까지 끝난 주문은
    줄에 없고 아래 한 줄 숫자로만(시작·제작 완료는 작업 시트에서).
    """
    queues = [{'key': key, 'label': label, 'rows': []} for key, label in PRODUCTION_HOME_STEP_DEFS]
    by_key = {q['key']: q for q in queues}
    waiting = 0
    finished = 0
    for row in rows:
        if row.get('home_view') != 'prod':
            continue
        steps = row.get('home_steps') or []
        current = next((s for s in steps if s.get('now')), None)
        if current is None:
            if row.get('home_stage') == '제작 대기':
                waiting += 1
            elif row.get('home_stage') == '검수 끝':
                finished += 1
            elif row.get('hold_active'):
                # 보류는 run 이 있어도 now 표시가 없다 — 첫 미완 공정 줄에 '보류'로 둔다
                first_undone = next((s for s in steps if not s.get('done')), None)
                if first_undone is not None:
                    by_key[first_undone['key']]['rows'].append(row)
            continue
        by_key[current['key']]['rows'].append(row)
    for q in queues:
        q['count'] = len(q['rows'])
    return {'queues': queues, 'waiting': waiting, 'finished': finished}


def production_home_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """탭 숫자 — 전체 / 생산 중(제작 대기~검수 끝·보류) / 바뀐 것."""
    return {
        'all': len(rows),
        'prod': sum(1 for r in rows if r.get('home_view') == 'prod'),
        'changed': sum(1 for r in rows if r.get('has_changes')),
    }


def build_production_home_rows(
    db: Any, user: Any, *, partner_org: str = '', today: datetime.date | None = None
) -> list[dict[str, Any]]:
    """첫 화면 행 전부(시공일 순, 캡 ``PRODUCTION_KANBAN_MAX_ROWS``). 쿼리 3회 + run id 1회."""
    today = today or get_today_kst()
    query = build_production_orders_query(
        db, user, '', '', False, partner_org, stage_codes=PRODUCTION_HOME_STAGE_CODES
    )
    query = apply_production_dashboard_sort(query, '', '')
    orders = query.limit(PRODUCTION_KANBAN_MAX_ROWS).all()
    run_ids = fetch_production_current_run_ids(db, orders)
    rows = build_production_home_enriched_rows(orders, run_ids)
    alerts_by_id = collect_production_change_alerts(db, orders, user.id if user else None)

    for row in rows:
        sd = row.get('structured_data') or {}
        raw_stage = row.get('raw_stage')
        has_run = row['id'] in run_ids
        in_production = raw_stage in _PRODUCTION_STAGES and has_run
        steps = production_home_steps(sd, mark_now=in_production)
        big, sub, view = production_home_stage(raw_stage, has_run, steps, bool(row.get('hold_active')))
        day = production_home_day(row.get('construction_date'), today)
        alerts = (alerts_by_id.get(row['id']) or {}).get('alerts') or []
        drawing_count = len(resolve_final_drawing_files(sd))
        row['home_steps'] = steps
        row['home_stage'] = big
        row['home_stage_sub'] = sub
        row['home_view'] = view
        row['home_soon'] = view == 'wait'
        row['day_key'] = day['key']
        row['day_label'] = day['label']
        row['day_sub'] = day['sub']
        row['day_is_today'] = day['is_today']
        row['has_changes'] = bool(alerts)
        row['home_alerts'] = alerts
        row['change_line'] = _change_line(alerts)
        row['drawing_label'] = f"도면 {drawing_count}장" if drawing_count else '도면 없음'
        row['search_text'] = ' '.join(
            str(part) for part in (
                row.get('customer_name'), f"#{row['id']}", row.get('v3_product_label'),
                row.get('address'), row.get('phone'), big,
            ) if part
        ).lower()
    return rows
