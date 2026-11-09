"""생산팀 첫 화면(전체 주문 한 줄) 읽기 모델 — 설계서 §12 (2026-11-09, D10·D12).

도면 기다리는 주문부터 시공 단계까지 **시공일 순 한 줄**. 칸반(:mod:`production_read_model`)과
같은 쿼리 빌더를 쓰되 단계 목록만 도면까지 넓힌다. 금액은 어디에도 싣지 않는다(D7).

- 큰 글자(지금 단계)는 :func:`production_home_stage` — "도면 기다림 / 컨펌 기다림 / 제작 대기 /
  <공정> 중 / 검수 끝 / 제작 완료 / 보류".
- 날짜 머리줄은 :func:`production_home_day` — "오늘 11/9 (월)", "11/12 (목) · D-3", "시공일 없음".
- 공정 5칸은 ``structured_data['production']['steps']`` 그대로(API 가 처음 접근 때 만들기 전이면
  5칸 모두 미완으로 그린다). 정의는 ``foms/api/production/orders.py`` 의 ``_PRODUCTION_STEP_DEFS``
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

#: 공정 5단계(key, 라벨). API ``_PRODUCTION_STEP_DEFS`` 와 같은 순서·값.
PRODUCTION_HOME_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("cut", "재단"),
    ("edge", "엣지"),
    ("paint", "도장"),
    ("assemble", "조립"),
    ("inspect", "검수"),
)

_WEEKDAY_KO = '월화수목금토일'
_DRAWING_STAGES = ('DRAWING', '도면')
_CONFIRM_STAGES = ('CONFIRM', '고객컨펌')
_PRODUCTION_STAGES = ('PRODUCTION', '생산')
_CONSTRUCTION_STAGES = ('CONSTRUCTION', '시공')


def production_home_steps(sd: dict[str, Any], *, mark_now: bool) -> list[dict[str, Any]]:
    """공정 5칸 — ``{key, label, done, now}``. ``mark_now`` 면 첫 미완 칸을 '지금 여기'로 표시한다."""
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
        row['change_line'] = _change_line(alerts)
        row['drawing_label'] = f"도면 {drawing_count}장" if drawing_count else '도면 없음'
        row['search_text'] = ' '.join(
            str(part) for part in (
                row.get('customer_name'), f"#{row['id']}", row.get('v3_product_label'),
                row.get('address'), row.get('phone'), big,
            ) if part
        ).lower()
    return rows
