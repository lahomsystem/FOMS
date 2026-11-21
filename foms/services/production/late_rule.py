"""생산 첫 화면 늦음 · 빠듯 규칙 — 설계서 ``docs/specs/2026-11-21-production-pc-viewer_SPEC.md`` §8 · §13 결정 3.

**일하는 날로 센다**(주말 · 공휴일 뺌, 사장님 2026-11-21). W = 오늘(KST) 다음 날부터 시공일까지의 일하는 날 수 —
달력은 ``foms/services/common/business_calendar.py`` 한 곳만 쓴다(새 달력 금지). 줄에 쓰는 D-n 글은 달력 날 그대로다.

순수 함수만 둔다(쿼리 0 · 요청 문맥 없음). 숫자 표는 :data:`LATE_THRESHOLDS` 한 곳 — 제안값으로 시작한다(결정 3).
기준점 = 옛 '생산 D-2' 배지(``foms/services/erp_display.py`` — 영업일 0~2, 제작 대기 늦음 W ≤ 2 와 맞춤).
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.common.business_calendar import business_days_between

LATE = 'late'
TIGHT = 'tight'

#: 지금 자리 → (빠듯 W 상한, 늦음 W 상한). 표에 없는 자리(제작 완료 · 시공 단계 · 시공일 없음)는 색이 없다.
LATE_THRESHOLDS: dict[str, tuple[int, int]] = {
    'wait': (5, 3),   # 도면 · 컨펌 기다림
    'ready': (4, 2),  # 제작 대기(회차 없음 · 재단 전)
    'early': (3, 1),  # 재단 중 · 엣지 중
    'final': (2, 0),  # 조립 중 · 검수 중
}
#: 공정 열쇠 → 자리(보류는 멈춘 공정의 자리를 쓴다).
_STEP_SPOT = {'cut': 'early', 'edge': 'early', 'assemble': 'final', 'inspect': 'final'}
_WAIT_STAGES = ('도면 기다림', '컨펌 기다림')
_DONE_STAGE = '제작 완료'
_FINISHED_STAGE = '검수 끝'


def _first_undone(row: dict[str, Any]) -> dict[str, Any] | None:
    """첫 미완 공정 칸(없으면 None)."""
    return next((s for s in (row.get('home_steps') or []) if not s.get('done')), None)


def late_spot(row: dict[str, Any]) -> tuple[str | None, str]:
    """(자리 열쇠 또는 None, '아직 …' 뒤에 붙는 글). 자리가 None 이면 색 표가 없는 자리다.

    Args:
        row: 첫 화면 행(``home_stage`` · ``home_steps`` · ``hold_active`` · ``home_has_run``).

    Returns:
        ``('ready', '시작 전')`` · ``('early', '엣지')`` · ``(None, '제작 완료 전')`` 같은 쌍.
    """
    stage = str(row.get('home_stage') or '')
    if stage in _WAIT_STAGES:
        return 'wait', stage
    if stage == '제작 대기':
        return 'ready', '시작 전'
    if stage == '보류':
        step = _first_undone(row)
        has_run = bool(row.get('home_has_run')) or any(s.get('done') for s in (row.get('home_steps') or []))
        if not has_run:
            return 'ready', '시작 전 보류'
        if step is None:
            return None, '제작 완료 전'
        return _STEP_SPOT.get(str(step.get('key')), 'early'), f"{step.get('label')}에서 보류"
    if stage.endswith(' 중'):
        step = _first_undone(row)
        if step is not None:
            return _STEP_SPOT.get(str(step.get('key')), 'early'), str(step.get('label'))
    if stage == _FINISHED_STAGE:
        return None, '제작 완료 전'
    return None, ''


def _parse_day(value: Any) -> datetime.date | None:
    """date · 'YYYY-MM-DD…' 글 → date. 비었거나 못 읽으면 None."""
    if isinstance(value, datetime.date):
        return value
    text = str(value or '').strip()[:10]
    try:
        return datetime.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def production_late_level(row: dict[str, Any], today: datetime.date, *, due: Any = None) -> str | None:
    """늦음(``'late'``) · 빠듯(``'tight'``) · 없음(None). 쿼리 0.

    시공일이 오늘보다 앞(지남)인데 제작 완료가 아니면 자리와 상관없이 늦음. 그 밖은 W(일하는 날)와 자리 표를 견준다.

    Args:
        row: 첫 화면 행. ``home_view`` 가 'done'(제작 완료)이면 늘 None.
        today: KST 오늘(``get_today_kst()``).
        due: 견줄 시공일(여러 시공일 주문의 가장 가까운 날). 없으면 ``row['construction_date']``.

    Returns:
        ``'late'`` · ``'tight'`` · None.
    """
    day = _parse_day(due if due is not None else row.get('construction_date'))
    if day is None or row.get('home_view') == 'done' or row.get('home_stage') == _DONE_STAGE:
        return None
    spot, where = late_spot(row)
    if day < today:
        return LATE if (spot is not None or where) else None
    if spot is None:
        return None
    tight_max, late_max = LATE_THRESHOLDS[spot]
    work = business_days_between(today, day)
    if work <= late_max:
        return LATE
    return TIGHT if work <= tight_max else None


def _when_text(day: datetime.date, today: datetime.date) -> str:
    """까닭 한 줄의 '언제' — 오늘 시공 · 내일 시공 · 시공 D-n · 시공 n일 지남(달력 날)."""
    delta = (day - today).days
    if delta == 0:
        return '오늘 시공'
    if delta == 1:
        return '내일 시공'
    return f"시공 D-{delta}" if delta > 0 else f"시공 {-delta}일 지남"


def production_late_view(row: dict[str, Any], today: datetime.date, *, due: Any = None) -> dict[str, Any]:
    """PC 줄의 늦음 표 — ``{'level', 'line', 'tip'}``. 시공일이 없으면 모두 빈 값.

    ``line`` = 상태 칸 아래 한 줄(``늦음 — 내일 시공, 아직 시작 전``), ``tip`` = 시공일 칸 마우스 글
    (``시공까지 일하는 날 2일`` — 색 기준이 일하는 날임을 적는다, §8).
    """
    day = _parse_day(due if due is not None else row.get('construction_date'))
    if day is None:
        return {'level': None, 'line': '', 'tip': ''}
    work = business_days_between(today, day) if day >= today else None
    tip = f"시공까지 일하는 날 {work}일" if work is not None else f"시공일 {(today - day).days}일 지남"
    level = production_late_level(row, today, due=day)
    line = ''
    if level is not None:
        _spot, where = late_spot(row)
        line = f"{'늦음' if level == LATE else '빠듯'} — {_when_text(day, today)}, 아직 {where}"
    return {'level': level, 'line': line, 'tip': tip}
