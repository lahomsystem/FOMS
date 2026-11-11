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

from sqlalchemy import or_

from models import Order
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
    """(큰 글자, 작은 글자, 보기 키). 보기 키는 탭 필터용 ``wait | prod | done``.
    보류는 생산 단계(제작 대기~검수)일 때만 — 도면·컨펌·시공 단계 보류는 그 단계 그대로(R1, 11-10)."""
    if hold_active and raw_stage in _PRODUCTION_STAGES:
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


def _by_line(row: dict[str, Any]) -> str:
    """만들 것 줄의 "발주 <발주사> · 담당 <영업 담당>"(사용자 11-11). 빈 쪽은 빼고, 둘 다 없으면 빈 글(요소를 안 그린다)."""
    orderer = str(row.get('orderer_name') or '').strip()
    manager = str(row.get('manager_name') or '').strip()
    parts = [f"발주 {orderer}" if orderer else '', f"담당 {manager}" if manager and manager != '-' else '']
    return ' · '.join(p for p in parts if p)


#: 시공일이 이보다 더 지난 주문은 맨 아래 "지난 시공일" 한 묶음으로 모은다(스테이징 실측 11-09: 139일 지난
#: 도면 대기 주문이 첫 줄에 오고 33묶음 중 대부분이 지난 날짜였다 — 작업자에겐 오늘·이번 주가 먼저다).
PRODUCTION_HOME_PAST_DAYS = 7
PAST_GROUP_KEY = 'past'


def production_home_groups(
    rows: list[dict[str, Any]], today: datetime.date | None = None, *, past_hidden: int = 0
) -> list[dict[str, Any]]:
    """날짜 묶음(모바일 실측 탭처럼 접었다 펴는 단위). 행은 이미 시공일 순이라 연속 구간만 자른다.
    ``past_hidden`` = 캡에 밀려 안 읽은 지난 주문 수(``build_production_home``) — 지난 묶음 머리줄에 적는다.

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
    if past['rows'] or past_hidden:
        for row in past['rows']:
            row['day_key'] = PAST_GROUP_KEY  # 카드의 data-day 가 묶음 키와 같아야 거르기가 맞다
        if past_hidden:
            past['sub'] = f"더 오래된 {past_hidden}건은 안 보여요"
        groups.append(past)
    for group in groups:
        group['count'] = len(group['rows'])
    return groups


def production_home_inbox(rows: list[dict[str, Any]], tombstones: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """탭 "바뀐 것" 받은함: 미확인 변경(주문마다 한 장, 알림 여러 줄) + 취소된 주문(묘비).

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


def production_home_queue_key(row: dict[str, Any]) -> str | None:
    """이 주문이 "내 공정" 줄에 서는 공정 키(없으면 None) — 줄과 탭 숫자가 같이 쓰는 한 규칙(R1).
    지금 공정(now) 이 있으면 그 줄, 보류는 run 이 없어도 첫 미완 공정 줄에 '보류'로."""
    if row.get('home_view') != 'prod':
        return None
    steps = row.get('home_steps') or []
    current = next((s for s in steps if s.get('now')), None)
    if current is None and row.get('hold_active'):
        current = next((s for s in steps if not s.get('done')), None)
    return current['key'] if current is not None else None


def _due_sort_key(row: dict[str, Any]) -> tuple[int, str, int]:
    """공정 줄·곧 올 것 순서 = 시공일 빠른 순(지난 날이 맨 앞) · 시공일 없음 맨 뒤 · 같은 날은 주문 번호 순(M2)."""
    day = _parse_date(row.get('construction_date'))
    return (0, day.isoformat(), int(row.get('id') or 0)) if day else (1, '', int(row.get('id') or 0))


def production_home_step_queues(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """탭 "내 공정"(안 3): 공정 4탭, 그 공정이 첫 미완인 제작 중 주문만 줄로. 일의 양은 안 보인다(D11).

    줄 아래 "곧 올 것" = 바로 앞 공정에 와 있는 주문(재단은 제작 대기) — 줄이 적어도 화면이 비지 않는다(사용자 11-10).

    보류 중인 주문은 줄에 두되 [끝] 단추 없이 '보류' 글만. 제작 대기(run 없음)·검수까지 끝난 주문은
    줄에 없고 아래 한 줄 숫자로만(시작·제작 완료는 작업 시트에서).
    """
    queues = [{'key': key, 'label': label, 'rows': []} for key, label in PRODUCTION_HOME_STEP_DEFS]
    by_key = {q['key']: q for q in queues}
    waiting_rows: list[dict[str, Any]] = []
    finished = 0
    for row in rows:
        key = production_home_queue_key(row)
        if key is not None:
            by_key[key]['rows'].append(row)
        elif row.get('home_view') == 'prod' and row.get('home_stage') == '제작 대기':
            waiting_rows.append(row)
        elif row.get('home_view') == 'prod' and row.get('home_stage') == '검수 끝':
            finished += 1
    waiting_rows.sort(key=_due_sort_key)
    prev: dict[str, Any] | None = None
    for q in queues:
        q['rows'].sort(key=_due_sort_key)
        q['count'] = len(q['rows'])
        q['incoming'] = waiting_rows if prev is None else [r for r in prev['rows'] if not r.get('hold_active')]
        q['incoming_label'] = '제작 대기' if prev is None else f"{prev['label']} 중"
        prev = q
    return {'queues': queues, 'waiting': len(waiting_rows), 'finished': finished}


def production_home_counts(rows: list[dict[str, Any]], tombstone_count: int = 0) -> dict[str, int]:
    """탭 숫자 — 전체 / 생산 중(제작 대기~검수 끝·보류) / 내 공정(공정 줄에 선 주문, R1) / 바뀐 것(받은함 장 수 =
    변경 있는 주문 + 묘비, R2)."""
    return {
        'all': len(rows),
        'prod': sum(1 for r in rows if r.get('home_view') == 'prod'),
        'making': sum(1 for r in rows if production_home_queue_key(r) is not None),
        'changed': sum(1 for r in rows if r.get('has_changes')) + tombstone_count,
    }


def build_production_home_rows(
    db: Any, user: Any, *, partner_org: str = '', today: datetime.date | None = None
) -> list[dict[str, Any]]:
    """``build_production_home`` 의 행만(시험·호환)."""
    return build_production_home(db, user, partner_org=partner_org, today=today)[0]


def build_production_home(
    db: Any, user: Any, *, partner_org: str = '', today: datetime.date | None = None
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """첫 화면 행 + 통계 ``{'past_hidden', 'total'}``(total = 캡과 무관한 실제 총계). 쿼리 4회 + run id 1회.

    시공일이 ``PRODUCTION_HOME_PAST_DAYS`` 안이거나 앞날·미정인 주문은 **전부** 읽는다(일거리). 그보다 지난 주문은
    최근 것부터 ``PRODUCTION_KANBAN_MAX_ROWS`` 에 남는 자리만 채운다 — 운영 실측(2026-11-09)에서 옛 주문이
    300건을 넘어 시공일 오름차순 캡이 최근·앞날 주문을 통째로 잘랐다(이번 주·내 공정 탭이 0).
    ``erp_construction_date`` 는 'YYYY-MM-DD' 문자열이라 ISO 문자열 비교가 날짜 비교와 같다(빈 문자열은 미정).
    """
    today = today or get_today_kst()
    cutoff = (today - datetime.timedelta(days=PRODUCTION_HOME_PAST_DAYS)).isoformat()
    base = build_production_orders_query(
        db, user, '', '', False, partner_org, stage_codes=PRODUCTION_HOME_STAGE_CODES
    )
    live_q = base.filter(or_(
        Order.erp_construction_date.is_(None), Order.erp_construction_date == '',
        Order.erp_construction_date >= cutoff,
    ))
    orders = apply_production_dashboard_sort(live_q, '', '').all()
    past_q = base.filter(Order.erp_construction_date < cutoff)
    past_total = past_q.order_by(None).count()
    live_count = len(orders)
    room = max(0, PRODUCTION_KANBAN_MAX_ROWS - len(orders))
    if room and past_total:
        orders += (
            past_q.order_by(None)
            .order_by(Order.erp_construction_date.desc(), Order.created_at.desc())
            .limit(room)
            .all()
        )
    stats = {'past_hidden': max(0, past_total - min(room, past_total)), 'total': live_count + past_total}
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
        # 바뀐 것(숫자·받은함·빨간 테두리·정렬·찾기 거르기)은 생산팀이 만들 주문만 — 도면·컨펌 기다림과 제작 완료는
        # 알림이 있어도 치지 않는다(사용자 D20 11-10 "만들 주문만": 운영 '바뀐 것 218' 대부분이 도면 단계 재전달이었다).
        alerts = ((alerts_by_id.get(row['id']) or {}).get('alerts') or []) if view == 'prod' else []
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
        row['by_line'] = _by_line(row)
        row['drawing_label'] = f"도면 {drawing_count}장" if drawing_count else '도면 없음'
        row['search_text'] = ' '.join(
            str(part) for part in (
                row.get('customer_name'), f"#{row['id']}", row.get('v3_product_label'),
                row.get('address'), row.get('phone'), big,
            ) if part
        ).lower()
    return rows, stats
