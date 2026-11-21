"""PC(마우스) 생산 화면 — 보기 전용 · [고치기] · 시공일 칸 · 누가 · 언제 · 늦음.

설계서 ``docs/specs/2026-11-21-production-pc-viewer_SPEC.md`` §4(기기) · §5(권한) · §6(꼴) · §7([고치기]) · §8(늦음).

- :func:`production_screen_flags` — 한 요청의 화면 판정(PC 꼴인가 · 쓰기 단추를 그리나 · [확인했어요] · [고치기]).
  쓰기를 그린다 = ``can_write_production(user) and (foms_ptr == 'coarse' or 고치기 켬)``. 쿠키가 없는 첫 요청은 안 그린다(§4).
- :func:`attach_pc_rows` — PC 줄이 쓰는 값(시공일 칸 · 공정 칸 마우스 글 · 늦음 표)을 이미 읽은 행에 단다(쿼리 0).
  PC 응답에서만 부른다 — 태블릿 · 폰 출력은 그대로다.
"""

from __future__ import annotations

import datetime
import time
from typing import Any

from foms.services.orders.construction_dates import all_construction_dates, pick_nearest_date
from foms.services.production.home_step_panel import _hold_reason, _prev_line, _run_start_text
from foms.services.production.late_rule import production_late_view
from foms.services.production.write_access import can_write_production
from foms.services.production_home_read_model import production_home_queue_key

#: [고치기] 쿠키 — 값 = 켠 시각(epoch 초, 서버 시각 기준으로 JS 가 심는다). Path=/erp/production · 세션 쿠키 · SameSite=Lax.
EDIT_COOKIE = 'foms_prod_edit'
EDIT_COOKIE_PATH = '/erp/production'
#: 켠 뒤 이 시간이 지나면 서버가 끈 것으로 본다(§7 — 켠 채 잊어 보기만 하려던 날 잘못 누르지 않게).
EDIT_TTL_SECONDS = 2 * 60 * 60
_WEEKDAY_KO = '월화수목금토일'


def _pointer(request: Any) -> str:
    """``foms_ptr`` 쿠키 → 'fine' · 'coarse' · ''(없음 · 이상한 값)."""
    cookies = getattr(request, 'cookies', None) or {}
    value = cookies.get('foms_ptr')
    return value if value in ('fine', 'coarse') else ''


def edit_cookie_fresh(request: Any, now_epoch: float | None = None) -> bool:
    """[고치기] 쿠키가 있고 켠 지 2시간 안이면 True(누가 켰는지는 보지 않는다 — :func:`production_screen_flags` 몫)."""
    cookies = getattr(request, 'cookies', None) or {}
    raw = str(cookies.get(EDIT_COOKIE) or '').strip()
    if not raw.isdigit():
        return False
    age = (time.time() if now_epoch is None else now_epoch) - int(raw)
    return 0 <= age < EDIT_TTL_SECONDS


def production_screen_flags(user: Any, request: Any, now_epoch: float | None = None) -> dict[str, Any]:
    """생산 첫 화면 · 작업 시트의 화면 판정 한 곳.

    Args:
        user: 로그인 사용자.
        request: Flask 요청(쿠키 ``foms_ptr`` · ``foms_prod_edit``).
        now_epoch: 시험용 지금 시각(epoch 초). 없으면 서버 시각.

    Returns:
        ``pc_view``(PC 꼴 · 마우스 기기) · ``can_act``(쓰기 단추) · ``can_ack``([확인했어요] — PC 보기 전용에서도 허용, §13 결정 5)
        · ``edit_on``([고치기] 켬) · ``edit_toggle``([고치기] 단추를 그림) · ``edit_now``(JS 가 심을 서버 시각).
    """
    now = time.time() if now_epoch is None else now_epoch
    pointer = _pointer(request)
    pc = pointer == 'fine'
    writer = can_write_production(user)
    edit_on = bool(writer and pc and edit_cookie_fresh(request, now))
    return {
        'pc_view': pc,
        'can_act': bool(writer and (pointer == 'coarse' or edit_on)),
        'can_ack': writer,
        'edit_on': edit_on,
        'edit_toggle': bool(writer and pc),
        'edit_now': int(now),
    }


def _md(day: datetime.date) -> str:
    """날 → 'M/D (요일)'."""
    return f"{day.month}/{day.day} ({_WEEKDAY_KO[day.weekday()]})"


def _rel(day: datetime.date, today: datetime.date) -> tuple[str, str]:
    """(D-n 글, 상태 열쇠). 달력 날 — 날짜 띠 · ``production_home_day`` 와 같은 수."""
    delta = (day - today).days
    if delta == 0:
        return '오늘', 'today'
    if delta == 1:
        return '내일', 'soon'
    return (f"D-{delta}", 'later') if delta > 0 else (f"{-delta}일 지남", 'past')


def _due_day(row: dict[str, Any], today: datetime.date) -> tuple[datetime.date | None, int]:
    """(칸에 쓸 시공일, 외 n). 여러 시공일 주문은 납작 칸을 넣은 날 모음에서 가장 가까운 날 + 나머지 수(§6-3 · 결정 5)."""
    flat = str(row.get('construction_date') or '').strip()[:10]
    days = set(all_construction_dates(row.get('structured_data') or {}))
    if flat:
        days.add(flat)
    if len(days) >= 2:
        return pick_nearest_date(days, today), len(days) - 1
    if not flat:
        return None, 0
    try:
        return datetime.date.fromisoformat(flat), 0
    except ValueError:
        return None, 0


def _prev_date(row: dict[str, Any]) -> str:
    """시공일이 바뀐 줄의 옛 날 'M/D'(가장 최근 시공일 변경의 앞 값). 없거나 '미정'이면 빈 글."""
    for alert in row.get('home_alerts') or []:
        if alert.get('kind') == 'construction_date':
            old = str(alert.get('from_md') or '').strip()
            return '' if old in ('', '미정') else old
    return ''


def pc_due(row: dict[str, Any], today: datetime.date) -> dict[str, Any]:
    """① 시공일 칸 — ``{md, rel, state, more, prev, day}``. 시공일이 없으면 md 가 '시공일 없음'(빈칸 아님)."""
    day, more = _due_day(row, today)
    if day is None:
        return {'md': '시공일 없음', 'rel': '', 'state': 'none', 'more': 0, 'prev': '', 'day': None}
    rel, state = _rel(day, today)
    return {'md': _md(day), 'rel': rel, 'state': state, 'more': more, 'prev': _prev_date(row), 'day': day}


def _step_cells(row: dict[str, Any]) -> list[dict[str, Any]]:
    """공정 칸 — 마우스 글(``tip``)과 아주 넓은 화면 칸 안 글(``cell``). 보류 줄의 멈춘 칸은 '보류'."""
    hold = bool(row.get('hold_active'))
    stopped = next((s['key'] for s in row.get('home_steps') or [] if not s.get('done')), None) if hold else None
    cells = []
    for s in row.get('home_steps') or []:
        label = s['label']
        if s.get('done'):
            who = ' · '.join(p for p in (s.get('by'), s.get('at_label')) if p)
            tip = f"{label} 끝 · {who}" if who else f"{label} 끝 · 기록 없음"
            short = ' '.join(p for p in (s.get('by'), (s.get('at_label') or '').split(' ')[0]) if p)
            cell = short or '기록 없음'
        elif s['key'] == stopped:
            tip, cell = f"{label} · 보류", '보류'
        elif s.get('now'):
            tip, cell = f"{label} · 지금 여기(아직)", '지금 여기'
        else:
            tip, cell = f"{label} · 아직", '아직'
        cells.append({**s, 'tip': tip, 'cell': cell, 'stopped': s['key'] == stopped})
    return cells


def _status_sub(row: dict[str, Any], late_line: str) -> str:
    """② 상태 칸 아래 한 줄 — 늦음 · 빠듯 까닭이 먼저, 없으면 보류 자리('재단에서 멈춤')."""
    if late_line:
        return late_line
    if row.get('hold_active'):
        stopped = next((s['label'] for s in row.get('home_steps') or [] if not s.get('done')), None)
        return f"{stopped}에서 멈춤" if stopped and row.get('home_has_run') else '시작 전 멈춤'
    return ''


def _prev_parts(row: dict[str, Any]) -> dict[str, str] | None:
    """'내 공정' PC 줄의 앞 공정 — ``{head: '재단 끝', meta: '김재단 · 11/20 14:05' | '기록 없음'}``."""
    key = production_home_queue_key(row)
    if key is None:
        return None
    line = _prev_line(row.get('structured_data') or {}, key, row.get('run_started_at'))
    head, _, meta = line.partition(' · ')
    return {'head': head, 'meta': meta or '기록 없음'}


def attach_pc_rows(rows: list[dict[str, Any]], today: datetime.date) -> None:
    """PC 줄 값을 행마다 단다 — ``pc_due`` · ``pc_late`` · ``pc_steps`` · ``pc_status_sub`` · ``pc_status_tip`` · ``pc_prev``.

    이미 읽은 행(``structured_data`` · ``home_steps`` · ``run_started_at``)만 쓴다(쿼리 0). PC 응답에서만 부른다.
    """
    for row in rows:
        due = pc_due(row, today)
        late = production_late_view(row, today, due=due['day']) if due['day'] else {'level': None, 'line': '', 'tip': ''}
        row['pc_due'] = due
        row['pc_late'] = late
        row['pc_steps'] = _step_cells(row)
        row['pc_status_sub'] = _status_sub(row, late['line'])
        started = _run_start_text(row.get('run_started_at')) if row.get('run_started_at') else ''
        row['pc_status_tip'] = f"제작 시작 {started}" if started else ''
        row['pc_prev'] = _prev_parts(row)
        row['pc_hold_reason'] = _hold_reason(row.get('structured_data') or {}) if row.get('hold_active') else ''


def attach_pc_inbox(changes: dict[str, Any] | None, rows: list[dict[str, Any]]) -> None:
    """'바뀐 것' 받은함 장(미확인 · 확인한 것)에 그 주문 행의 ① 시공일 칸 값을 단다(묘비는 행이 없어 안 단다)."""
    if not changes:
        return
    by_id = {row['id']: row for row in rows}
    for item in list(changes.get('inbox') or []) + list(changes.get('done') or []):
        row = by_id.get(item.get('id'))
        if row is not None and item.get('kind') != 'cancelled':
            item['pc_due'] = row.get('pc_due')
            item['pc_late'] = row.get('pc_late')
