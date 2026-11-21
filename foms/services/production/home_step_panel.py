"""생산 첫 화면 '내 공정' 탭 오른쪽 판 — 설계서 ``docs/specs/2026-11-21-production-my-steps-panel_SPEC.md`` §3-3 · §3-6.

판 자료는 첫 화면이 **이미 읽은 행**(``build_production_home`` → ``production_home_step_queues``)에서 만든다.
DB 를 읽지 않는다(쿼리 0개 더함). 금액은 싣지 않는다(D7). 엣지 사양 같은 ERP 에 없는 값은 안 그린다(D11).

- :func:`production_home_step_panel` — 줄 하나의 판(이름 · 품목 · 그림 · 색 · 앞 공정 · 다음 공정 · [끝] · 보류 · 다음 손님).
- :func:`attach_step_panels` — 공정 줄마다 판 목록 · 고른 줄(주소 ``order=`` · 보류 아닌 첫 줄 · 모두 보류면 첫 줄)을 붙이고,
  ``order=`` 가 선 공정 탭 열쇠를 돌려준다(그 탭이 첫 화면 탭 — 마지막 탭 기억보다 앞).
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.files.list_thumb import mid_thumb_url
from foms.services.production_dashboard_display import _production_first_item
from foms.services.production_home_read_model import PRODUCTION_HOME_STEP_DEFS
from foms.services.production_sheet_view import _PROD_SHEET_IMG_EXT, _format_at_kst

#: 검수 탭의 '다음 공정' — 공정 4칸 뒤는 작업 시트의 [제작 완료](설계서 §3-3).
STEP_PANEL_LAST_NEXT = '제작 완료'
#: 재단 탭의 '앞 공정' — 회차 시작(누가는 저장 칸이 없어 안 쓴다, 설계서 §8).
STEP_PANEL_RUN_START = '제작 시작'

_LABELS = dict(PRODUCTION_HOME_STEP_DEFS)
_KEYS = [key for key, _ in PRODUCTION_HOME_STEP_DEFS]


def _raw_steps(sd: dict[str, Any]) -> dict[str, dict[str, Any]]:
    prod = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    raw = prod.get('steps') if isinstance(prod.get('steps'), list) else []
    return {str(s.get('key')): s for s in raw if isinstance(s, dict) and s.get('key')}


def _run_start_text(value: Any) -> str:
    """회차 ``started_at``(UTC naive datetime · iso 글) → 'M/D HH:MM'(KST, 시트 공정 칸과 같은 글). 없으면 빈 글."""
    if isinstance(value, datetime.datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
        value = aware.isoformat()
    return _format_at_kst(value)


def _prev_line(sd: dict[str, Any], key: str, run_started_at: Any) -> str:
    """앞 공정 한 줄 — '재단 끝 · 김재단 · 11/21 09:12'(재단 탭은 '제작 시작 · 11/21 08:40'). 빈 칸은 뺀다."""
    idx = _KEYS.index(key)
    if idx == 0:
        parts = [STEP_PANEL_RUN_START, _run_start_text(run_started_at)]
    else:
        prev_key = _KEYS[idx - 1]
        src = _raw_steps(sd).get(prev_key) or {}
        parts = [f"{_LABELS[prev_key]} 끝", str(src.get('by_name') or '').strip(), _format_at_kst(src.get('at'))]
    return ' · '.join(p for p in parts if p)


def _color_line(row: dict[str, Any]) -> str:
    """색 줄 — 색(``v3_material``) + 첫 품목 손잡이 → '그레이 · 손잡이 없음'. 둘 다 없으면 빈 글(줄을 안 그린다)."""
    first, _ = _production_first_item(row.get('structured_data') or {})
    raw = (first or {}).get('handle')
    handle = raw.strip() if isinstance(raw, str) else ''
    parts = [str(row.get('v3_material') or '').strip(), f"손잡이 {handle}" if handle else '']
    return ' · '.join(p for p in parts if p)


def _picture(sd: dict[str, Any]) -> dict[str, Any]:
    """그림 칸 — 첫 그림의 640 중간 그림(만들 수 없는 key 면 원본) + 눌러 크게 볼 그림 원본 전부(작업 시트와 같은 목록).

    그림 · 파일 가르기는 시트와 같은 파일 이름 확장자. 그림 없이 파일만 = 첫 파일 새 탭, 0장 = '도면 없음'.
    """
    files = resolve_final_drawing_files(sd)
    images = [f for f in files if f.get('view_url') and (f.get('filename') or '').lower().endswith(_PROD_SHEET_IMG_EXT)]
    count = len(files)
    label = f"도면 {count}장" if count else '도면 없음'
    if images:
        first = images[0]
        return {
            'kind': 'image', 'label': label, 'alt': first.get('filename') or '도면',
            'src': mid_thumb_url(first.get('key')) or first['view_url'],
            # 뷰어는 보기 주소(/api/files/view/<key>)에서 key 를 읽어 내려받기 주소를 스스로 만든다 — 판마다 싣는 글을 줄인다
            'files': [{'view_url': f['view_url'], 'filename': f.get('filename') or '도면'} for f in images],
        }
    viewable = [f for f in files if f.get('view_url')]
    if viewable:
        return {'kind': 'file', 'label': f"{label} · 파일", 'href': viewable[0]['view_url'], 'files': []}
    return {'kind': 'none', 'label': '도면 없음', 'files': []}


def _latest_defect(sd: dict[str, Any]) -> dict[str, str] | None:
    """최근 불량 한 줄(작업 시트와 같은 글) — 사유 · '이름 M/D HH:MM'."""
    prod = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    defects = prod.get('defects') if isinstance(prod.get('defects'), list) else []
    latest = defects[-1] if defects and isinstance(defects[-1], dict) else None
    if not latest:
        return None
    meta = ' '.join(p for p in (str(latest.get('by_name') or '').strip(), _format_at_kst(latest.get('at'))) if p)
    return {'reason': str(latest.get('reason') or ''), 'meta': meta}


def _hold_reason(sd: dict[str, Any]) -> str:
    prod = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    hold = prod.get('hold') if isinstance(prod.get('hold'), dict) else {}
    reason = hold.get('reason')
    return reason.strip() if isinstance(reason, str) else ''


def production_home_step_panel(row: dict[str, Any], key: str, next_row: dict[str, Any] | None) -> dict[str, Any]:
    """줄 하나의 판 자료(순수 함수 — 이미 읽은 행만). ``key`` = 이 줄이 선 공정, ``next_row`` = 같은 공정 줄에서 이 줄 다음의
    보류 아닌 줄(없으면 None → '끝내면 다음은' 을 안 그린다)."""
    sd = row.get('structured_data') or {}
    idx = _KEYS.index(key)
    label = _LABELS[key]
    product = row.get('v3_product_label') or '품목 없음'
    spec = row.get('v3_spec_display') or ''
    return {
        'id': row['id'],
        'name': row.get('customer_name') or '-',
        'sub': f"{product} · {spec}" if spec else product,
        # 시공일 표(fph_due) — 줄 행이 이미 가진 값(사용자 11-21 "아주 중요한 정보")
        'day_label': row.get('day_label') or '',
        'day_sub': row.get('day_sub') or '',
        'day_is_today': bool(row.get('day_is_today')),
        'pic': _picture(sd),
        'color': _color_line(row),
        'prev': _prev_line(sd, key, row.get('run_started_at')),
        'next_step': _LABELS[_KEYS[idx + 1]] if idx + 1 < len(_KEYS) else STEP_PANEL_LAST_NEXT,
        'key': key,
        'label': label,
        'hold_active': bool(row.get('hold_active')),
        'hold_reason': _hold_reason(sd),
        'latest_defect': _latest_defect(sd),
        'next_id': next_row['id'] if next_row else None,
        'next_name': (next_row.get('customer_name') or '-') if next_row else '',
    }


def parse_step_order(raw: Any) -> int | None:
    """주소 ``order=`` — 숫자만 읽는다(그 밖은 None, 읽기 · 표시만 — 설계서 §3-6)."""
    text = str(raw or '').strip()
    return int(text) if text.isdigit() and len(text) <= 12 else None


def attach_step_panels(queues: dict[str, Any], order_id: int | None) -> str | None:
    """공정 줄마다 ``panels``(줄 순서 그대로) · ``selected_id`` 를 붙인다. ``order_id`` 가 선 공정 열쇠를 돌려준다(없으면 None).

    고른 줄 = 그 공정 줄에 ``order_id`` 가 있으면 그 줄, 없으면 보류 아닌 첫 줄, 모두 보류면 첫 줄(줄이 없으면 None).
    '끝내면 다음은' = 이 줄 다음의 보류 아닌 줄(보류 줄은 건너뛴다).
    """
    pinned = None
    for q in queues.get('queues') or []:
        rows = q.get('rows') or []
        panels = []
        for i, row in enumerate(rows):
            next_row = next((r for r in rows[i + 1:] if not r.get('hold_active')), None)
            panels.append(production_home_step_panel(row, q['key'], next_row))
        q['panels'] = panels
        ids = [r['id'] for r in rows]
        if order_id is not None and order_id in ids:
            q['selected_id'] = order_id
            pinned = q['key']
        else:
            free = next((r['id'] for r in rows if not r.get('hold_active')), None)
            q['selected_id'] = free if free is not None else (ids[0] if ids else None)
    return pinned
