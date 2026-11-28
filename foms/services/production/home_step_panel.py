"""생산 첫 화면 '내 공정' 탭 오른쪽 판 — 설계서 ``docs/specs/2026-11-21-production-my-steps-panel_SPEC.md`` §3-3 · §3-6.

판 자료는 첫 화면이 **이미 읽은 행**(``build_production_home`` → ``production_home_step_queues``)에서 만든다.
DB 를 읽지 않는다(쿼리 0개 더함). 금액은 싣지 않는다(D7). 엣지 사양 같은 ERP 에 없는 값은 안 그린다(D11).

- :func:`production_home_step_panel` — 줄 하나의 판(이름 · 품목 · 그림 · 색 · 앞 공정 · 다음 공정 · [끝] · 보류 · 다음 손님).
- :func:`attach_step_panels` — 공정 줄마다 고른 줄(주소 ``order=`` · 멈추지 않은 첫 줄 · 모두 멈추면 첫 줄 — 멈춤 = 보류 · 도면 고치는 중,
  [끝] 자리 막힘 줄은 고른다 — UI 평가 B3 2026-11-28)과 **그 줄의 판 하나**를
  붙이고, ``order=`` 가 선 공정 탭 열쇠를 돌려준다(그 탭이 첫 화면 탭 — 마지막 탭 기억보다 앞).
- :func:`step_panel_for` — 다른 줄을 누를 때 받는 판 하나 조각(``view=panel&step=&order=``)의 자료. 같은 공정 줄에서 만들어
  '끝내면 다음은' 이 한 화면에 다 그릴 때와 같다.
- :func:`step_confirm_ids` · :func:`attach_step_confirm` — 도면 있는 줄의 [<공정> 끝] 자리 막힘(옛 확인 창 자료는 2026-11-27 지움 — 도면
  있는 줄은 늘 아래 막힘이 먼저였다). 표시 줄은 부르는 쪽(``foms.web.production.home``)이 한 번에 읽어 넘긴다 — 이 모듈은 그대로 DB 를 읽지 않는다.
- [끝] 자리 막힘 ``step_block``(비평 C02 · C03, 보류 · 도면 고치는 중과 같은 자리 · 꼴): 장이 모두 남의 공장인 주문 = "2공장 작업"
  (:func:`attach_step_blocks` — 공정 API 와 같은 :func:`~foms.services.production.factory_scope.order_factory_gate`, 줄 끝으로 — 날짜 탭
  남의 공장 줄처럼 빼지 않고 뒤에) · 그 파트가 도면 칸을 쓴 주문 = "재단 3/5 · 2장 미완료"(공정 API 와 같은 거절 ``PART_USES_CARDS`` —
  누르면 그 주문 도면 판) · 도면이 있는 주문 = "재단 0/1 · 1장 미완료"(같은 자리 · 꼴, 거절 ``STEP_PER_SHEET`` — 사장님 2026-11-27 "도면이
  주, 작업 시트는 보기": 도면 0장 주문만 [<공정> 완료] 단추).

2026-11-22 터치 점검: 숨은 판을 줄마다 다 그리면(주문 150건 · 판 96개) 조각이 396KB · DOM 13,100 이 되어 탭 바꾸기 ·
[다시 받기] · [끝] 뒤 화면이 1~2초 얼고 그동안 누름이 버려졌다 — 날짜 탭(11-14)처럼 고른 판만 그리고 나머지는 누를 때 받는다.
"""

from __future__ import annotations

import datetime
from typing import Any

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_fix import blocked_left_numbers, fixing_label, per_drawing_numbers
from foms.services.production.factory_scope import order_elsewhere
from foms.services.production.part_card_state import BLOCK_REVISE
from foms.services.production.part_mark_gates import (
    DRAWING_REVISING,
    PART_USES_CARDS,
    REVISING_MESSAGE,
    STEP_PER_SHEET,
    step_cell_gate,
)
from foms.services.files.list_thumb import mid_thumb_url
from foms.services.production.part_progress import part_progress
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
    """앞 공정 한 줄 — '재단 완료 · 김재단 · 11/21 09:12'(재단 탭은 '제작 시작 · 11/21 08:40'). 빈 칸은 뺀다."""
    idx = _KEYS.index(key)
    if idx == 0:
        parts = [STEP_PANEL_RUN_START, _run_start_text(run_started_at)]
    else:
        prev_key = _KEYS[idx - 1]
        src = _raw_steps(sd).get(prev_key) or {}
        parts = [f"{_LABELS[prev_key]} 완료", str(src.get('by_name') or '').strip(), _format_at_kst(src.get('at'))]
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
        'ship_mark': row.get('ship_mark'),  # 상차 · 희망일 표(사장님 2026-11-25) — 시공일 표 옆
        'pic': _picture(sd),
        'color': _color_line(row),
        'prev': _prev_line(sd, key, row.get('run_started_at')),
        'next_step': _LABELS[_KEYS[idx + 1]] if idx + 1 < len(_KEYS) else STEP_PANEL_LAST_NEXT,
        'key': key,
        'label': label,
        'hold_active': bool(row.get('hold_active')),
        'hold_reason': _hold_reason(sd),
        'revise_block': row.get('revise_block'),  # 도면 고치는 중 — [끝] 대신 까닭(보류와 같은 자리, 2026-11-25)
        'step_block': row.get('step_block'),  # 남의 공장 주문 · 도면 칸을 쓴 파트 — [끝] 대신(비평 C02 · C03)
        'confirm': row.get('step_confirm'),  # 늘 None — 확인 창 자료 길은 2026-11-27 지웠다(템플릿 ``p.confirm`` 을 치운 뒤 이 칸도 뺀다)
        'latest_defect': _latest_defect(sd),
        'next_id': next_row['id'] if next_row else None,
        'next_name': (next_row.get('customer_name') or '-') if next_row else '',
    }


def parse_step_order(raw: Any) -> int | None:
    """주소 ``order=`` — 숫자만 읽는다(그 밖은 None, 읽기 · 표시만 — 설계서 §3-6)."""
    text = str(raw or '').strip()
    return int(text) if text.isdigit() and len(text) <= 12 else None


def _blocked(row: dict[str, Any]) -> bool:
    """[끝]이 막힌 줄 — 보류 · 도면 고치는 중(사장님 2026-11-25 "보류처럼") · [끝] 자리 막힘(비평 C02 · C03). '끝내면 다음은' · 처음 고른
    줄에서 건너뛴다."""
    return bool(row.get('hold_active') or row.get('revise_block') or row.get('step_block'))


def _panel_at(q: dict[str, Any], index: int) -> dict[str, Any]:
    """공정 줄 ``q`` 의 ``index`` 번째 줄 판 — '끝내면 다음은' = 그 뒤의 막히지 않은 줄(보류 · 도면 고치는 중은 건너뛴다)."""
    rows = q.get('rows') or []
    next_row = next((r for r in rows[index + 1:] if not _blocked(r)), None)
    return production_home_step_panel(rows[index], q['key'], next_row)


def _stopped(row: dict[str, Any]) -> bool:
    """멈춘 줄 — 보류 · 도면 고치는 중. 판이 처음 고르는 줄에서만 건너뛴다(:func:`attach_step_panels`)."""
    return bool(row.get('hold_active') or row.get('revise_block'))


def attach_step_panels(queues: dict[str, Any], order_id: int | None) -> str | None:
    """공정 줄마다 ``selected_id`` 와 그 줄의 판 하나(``panels`` = 0 · 1개)를 붙인다. ``order_id`` 가 선 공정 열쇠를 돌려준다.

    고른 줄 = 그 공정 줄에 ``order_id`` 가 있으면 그 줄, 없으면 멈추지 않은(보류 · 도면 고치는 중 아닌) 첫 줄, 모두 멈추면 첫 줄(줄이 없으면 None).
    [끝] 자리 막힘(``step_block`` — 도면 칸 "재단 0/3 · 3장 미완료" · 남의 공장)이 있는 줄도 고른다(UI 평가 B3, 2026-11-28): 예전에는 그 줄을
    건너뛰어 판이 목록 첫 화면 밖 '도면 없음' 주문(7번째 줄)의 큰 [재단 완료]를 보였다 — 판이 목록 맨 위 줄을 보이면 그 칸이 [끝] 대신 선다.
    다른 줄의 판은 그 줄을 누를 때 :func:`step_panel_for` 조각으로 받는다(숨은 판을 다 그리지 않는다, 2026-11-22).
    """
    pinned = None
    for q in queues.get('queues') or []:
        rows = q.get('rows') or []
        ids = [r['id'] for r in rows]
        if order_id is not None and order_id in ids:
            q['selected_id'] = order_id
            pinned = q['key']
        else:
            free = next((r['id'] for r in rows if not _stopped(r)), None)
            q['selected_id'] = free if free is not None else (ids[0] if ids else None)
        q['panels'] = [_panel_at(q, ids.index(q['selected_id']))] if q['selected_id'] is not None else []
    return pinned


def step_panel_for(queues: dict[str, Any], key: str, order_id: int | None) -> dict[str, Any] | None:
    """판 하나 조각(``view=panel``)의 자료 — 공정 ``key`` 줄에 ``order_id`` 가 있을 때만(없으면 None → 404).

    Args:
        queues: :func:`production_home_step_queues` 결과(이 요청이 읽은 행 — 한 화면을 다 그릴 때와 같은 줄 · 순서).
        key: 누른 줄이 선 공정 열쇠(``cut`` · ``edge`` · ``assemble`` · ``inspect``).
        order_id: 누른 줄 주문 번호.

    Returns:
        :func:`production_home_step_panel` 판 자료, 또는 그 사이 줄이 다른 공정으로 옮겨 갔거나 없는 번호면 None.
    """
    if order_id is None:
        return None
    for q in queues.get('queues') or []:
        if q.get('key') != key:
            continue
        ids = [r['id'] for r in q.get('rows') or []]
        return _panel_at(q, ids.index(order_id)) if order_id in ids else None
    return None


def step_confirm_ids(queues: dict[str, Any], *, fix_only: bool = False) -> list[int]:
    """[<공정> 끝] 자리 막힘을 보려고 표시 줄을 읽을 줄 — [끝]이 있는(보류 · 도면 고치는 중이 아닌) 생산 줄 전부: 도면 있는 줄 **과** 도면이
    0장인 줄(2026-11-28 흐름 §3-5 — 그 주문의 '도면 없음' 카드 ``@order`` 를 누가 작업 중이면 [끝] 대신 "재단 0/1 · 1장 미완료"). 같은 ``IN``
    한 번(둘 다 있어도 +1, 줄이 없으면 0 — 쿼리 계약 ``test_steps_tab_writer_reads_marks_once_for_any_production_row``). 낡은 화면에서 누르면
    공정 API 가 같은 판정으로 409 ``PART_USES_CARDS``.
    ``fix_only``([끝]이 없는 사람 — 읽기 전용 · 보기만 PC)면 그중 도면별로 막힌 장이 있는 줄만(쿼리 0 — 이미 든 주문 JSON, 지금 그대로) —
    그 사람에게도 "도면 2 고치는 중" 판정(:func:`attach_step_confirm`)을 하려고 읽는 줄."""
    rows = [r for q in queues.get('queues') or [] for r in q.get('rows') or [] if not _blocked(r)]
    if fix_only:
        return [r['id'] for r in rows if per_drawing_numbers(r.get('structured_data') or {})]
    return [r['id'] for r in rows]


def attach_step_blocks(queues: dict[str, Any], user: Any) -> None:
    """장이 모두 남의 공장인 줄의 [끝] 자리 = "2공장 작업"(비평 C02 — 공정 API 403 과 같은 판정, 반장 · 파트 계정은 자기 공장만 ·
    관리자는 막힘 없음). 보류 · 도면 고치는 중 줄은 그 막힘이 먼저다. 막힌 줄은 그 공정 줄 끝으로(날짜 탭 남의 공장 줄처럼 빼지 않고
    뒤에, 같은 칸 안 순서 그대로). [끝]을 그리는 사람(``can_check_steps``)만 부른다 — 쿼리 0(이미 든 주문 JSON)."""
    for q in queues.get('queues') or []:
        for row in q.get('rows') or []:
            if not _blocked(row):
                row['step_block'] = order_elsewhere(user, row.get('structured_data') or {})
        q['rows'].sort(key=lambda r: (r.get('step_block') or {}).get('kind') == 'elsewhere')


def _cards_block(sd: dict[str, Any], marks: list[Any], key: str) -> dict[str, str] | None:
    """그 파트가 도면 칸을 쓴 주문 · 도면이 있는 주문의 [끝] 자리(비평 C03 · 사장님 2026-11-27 "도면이 주, 작업 시트는 보기") — 누르면
    서버가 거절(409 ``PART_USES_CARDS`` · ``STEP_PER_SHEET`` — 같은 함수 :func:`step_cell_gate`)하는 줄만. 칸 글 = 날짜 줄 칸 이름 꼴
    "재단 3/5 · 2장 미완료"(아무도 안 건드린 파트는 "재단 0/5 · 5장 미완료"), 까닭 = 거절 글 그대로, 누르면 그 주문 도면 판(같은 class)."""
    gate = step_cell_gate(sd, marks, key, True)
    if gate is None or gate.code not in (PART_USES_CARDS, STEP_PER_SHEET):
        return None
    left, total = gate.extra['left'], gate.extra['total']
    return {'kind': 'cards', 'text': f"{_LABELS[key]} {total - left}/{total} · {left}장 미완료", 'why': gate.message,
            'code': gate.code}


def _fix_wait_block(sd: dict[str, Any], marks: list[Any], key: str) -> dict[str, str] | None:
    """그 공정 파트에 남은 장이 도면별로 막힌 장뿐이면 [끝] 자리 막힘(통째 '도면 고치는 중'과 같은 자리 · 꼴, 글만 "도면 2 고치는 중")."""
    numbers = blocked_left_numbers(sd, part_progress(sd, marks, key)['left_keys'])
    if not numbers:
        return None
    return {'kind': BLOCK_REVISE, 'text': fixing_label(numbers), 'why': REVISING_MESSAGE, 'code': DRAWING_REVISING}


def attach_step_confirm(queues: dict[str, Any], marks: dict[int, list[Any]], *, confirm: bool = True) -> None:
    """도면 있는 줄의 [<공정> 끝] 자리 막힘(아래 둘). 옛 ``step_confirm``(누르기 전 확인 창 자료)은 2026-11-27 지웠다 — 도면이 1장이라도
    있는 줄은 [끝]을 그리는 사람에게 늘 ``step_block`` 이 먼저 붙어(공정 API 409 ``STEP_PER_SHEET`` 와 같은 :func:`step_cell_gate`) 그 자료가
    실리는 줄이 없었다.

    그 공정 파트에 남은 장이 도면별로 막힌 장뿐이면(풀어 쓴 뒤 · 지금 도면이 모두 막힘) [끝] 대신 ``revise_block`` "도면 2 고치는 중"을
    단다 — 누르면 처리할 장이 없어 거절되는 길을 없앤다(2026-11-25 D1 검토 판결 D). 그 줄은 보류처럼 흐리고 처음 고른 줄 · '끝내면 다음은'
    에서 빠지지만, 다음 공정의 '곧 올 것'에는 남는다 — 끝난 장은 다음 공정으로 간다(사장님 답 "나머지는 계속 작업", 둘째 판 1). '곧 올 것'
    에서 빠지는 것은 :func:`~foms.services.production_home_read_model.production_home_step_queues` 가 이미 뺀 통째 막힘 · 보류 줄뿐이다.

    [끝]을 그리는 사람(``confirm``)에게는 그 파트가 도면 칸을 쓴 줄(눌러도 409 ``PART_USES_CARDS``)의 [끝] 대신 ``step_block`` "재단 3/5 · 2장
    미완료"를 단다(비평 C03 — 같은 표시 줄, 쿼리 0 더함). '곧 올 것'은 그대로다(도면 칸이 끝나면 다음 공정으로 간다).

    Args:
        queues: :func:`production_home_step_queues` 결과(행을 그 자리에서 고친다).
        marks: :func:`step_confirm_ids` 주문들의 표시 줄(``marks_by_order`` — 열쇠가 있는 주문만 싣는다).
        confirm: [끝]을 그리는 사람인지(``step_block`` 은 그 사람에게만 — 아니면 "도면 2 고치는 중" 판정만).
    """
    for q in queues.get('queues') or []:
        for row in q.get('rows') or []:
            if row['id'] not in marks:
                continue
            sd = row.get('structured_data') or {}
            wait = _fix_wait_block(sd, marks[row['id']], q['key'])
            if wait is not None:
                row['revise_block'] = wait
                continue
            cards = _cards_block(sd, marks[row['id']], q['key']) if confirm else None
            if cards is not None:  # 도면 칸을 쓴 파트 · 도면이 있는 주문 — [끝] 대신 남은 장(눌러도 늘 거절되던 길, 비평 C03)
                row['step_block'] = cards
