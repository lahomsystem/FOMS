"""생산 작업 시트 뷰 모델 — 옆 시트(400px fragment)와 전체 화면 시트가 같이 쓴다(설계서 §12.2, 2026-11-09).

``foms/web/production/dashboard.py`` 에 있던 ``_prod_sheet_*`` 헬퍼를 이름 그대로 옮겼다(그 파일은 500줄
래칫 턱밑). :func:`build_production_sheet_view` 가 옆 시트 키를 만들고, ``full=True`` 면 전체 화면이 더 쓰는
키(전화·주소·일정·시공팀·도면 전체·공정 5줄·최근 불량)를 덧붙인다. 금액 키는 없다(D7).
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from models import Order, ProductionRun
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.erp_template_filters import eval_spec_width_mm, item_spec_w300_value
from foms.services.orders.drawing_confirm_partial import active_items
from foms.services.production_change_alerts import collect_production_change_alerts
from foms.services.production_dashboard_display import (
    _ensure_dict,
    _normalize_date_to_yyyymmdd,
    _production_first_item,
    _production_material,
    _production_product_label,
    _production_quest_sales_state,
    _production_stage_label_from_stage,
)
from foms.services.production_drawing_gate_display import attach_production_drawing_gate
from foms.services.production_home_read_model import production_home_steps

_PROD_SHEET_IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')
_WEEKDAY_KO = '월화수목금토일'
_KST = datetime.timezone(datetime.timedelta(hours=9))


def _prod_item_total_w_mm(item: dict[str, Any]) -> float:
    """항목의 총 가로 폭(mm). spec_rows 있으면 각 행 W 합, 없으면 spec_width/spec 평가.

    ``item_spec_w300_value``와 동일 규칙(÷300 이전의 원 폭값).
    """
    if not isinstance(item, dict):
        return 0.0
    spec_rows = item.get('spec_rows')
    if spec_rows and isinstance(spec_rows, list):
        total = 0.0
        for row in spec_rows:
            if isinstance(row, dict):
                total += eval_spec_width_mm(row.get('spec_width') or row.get('w') or '')
        return total
    return eval_spec_width_mm(item.get('spec_width') or item.get('spec') or '')


def _prod_sheet_spec_rows_view(items: list[Any]) -> list[dict[str, Any]]:
    """규격 미니테이블 행: {label(품목), w(가로 mm 표시), qty(수량)}."""
    view: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        w_mm = _prod_item_total_w_mm(item)
        view.append({
            'label': item.get('product_name') or item.get('name') or '품목',
            'w': ('%g' % w_mm) if w_mm else '-',
            'qty': item.get('quantity') or item.get('qty') or 1,
        })
    return view


def _prod_sheet_total_units(items: list[Any]) -> str:
    """총 자수(모든 항목 W/300 합)을 소수 1자리 문자열로."""
    total = 0.0
    for item in items:
        total += item_spec_w300_value(item)
    return f"{total:.1f}"


def _prod_sheet_load_md(value: Any) -> str:
    """시공(상차) 예정일 → 'M/D'. 미정/파싱 실패 시 '-'."""
    norm = _normalize_date_to_yyyymmdd(value)
    if not norm:
        return '-'
    try:
        d = datetime.datetime.strptime(norm, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return '-'
    return f"{d.month}/{d.day}"


def _prod_sheet_drawing_thumb(sd: dict[str, Any]) -> dict[str, str] | None:
    """도면 전달본 썸네일: resolve_final_drawing_files(수령 확정과 같은 함수)의 첫 이미지.

    전달 API 가 계산해 둔 현재 도면 목록(``drawing_current_files``, view_url/download_url
    same-origin)을 쓴다 — 수령 확정본과 같은 답이다. 이미지 파일을 우선 정렬해 <img> 렌더가
    가능한 항목을 앞세운다.
    """
    files = resolve_final_drawing_files(sd)
    ordered = sorted(
        files,
        key=lambda f: 0 if (f.get('filename') or '').lower().endswith(_PROD_SHEET_IMG_EXT) else 1,
    )
    for f in ordered:
        view = (f.get('view_url') or '').strip()
        if not view:
            continue
        return {
            'thumb': view,
            'view': view,
            'download': (f.get('download_url') or view).strip(),
            'label': f.get('filename') or '도면 전달본',
        }
    return None


def _prod_sheet_drawing_files(sd: dict[str, Any]) -> list[dict[str, str]]:
    """도면 전달본 **전체**(저장 순서 = 도면 번호). 이미지는 kind 'image', 그 밖(PDF 등)은 'file'."""
    out: list[dict[str, str]] = []
    for f in resolve_final_drawing_files(sd):
        view = (f.get('view_url') or '').strip()
        if not view:
            continue
        name = f.get('filename') or '도면'
        out.append({
            'kind': 'image' if name.lower().endswith(_PROD_SHEET_IMG_EXT) else 'file',
            'view': view,
            'download': (f.get('download_url') or view).strip(),
            'label': name,
        })
    return out


def _format_at_kst(value: Any) -> str:
    """공정 체크·불량 기록 시각(UTC iso) → 'M/D HH:MM'(KST). 못 읽으면 빈 글."""
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        parsed = datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return ''
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    local = parsed.astimezone(_KST)
    return f"{local.month}/{local.day} {local.hour:02d}:{local.minute:02d}"


def _construction_label(value: Any) -> str:
    norm = _normalize_date_to_yyyymmdd(value)
    if not norm:
        return '미정'
    try:
        d = datetime.datetime.strptime(norm, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return '미정'
    return f"{d.month}/{d.day} ({_WEEKDAY_KO[d.weekday()]})"


def _worker_names(sd: dict[str, Any]) -> list[str]:
    shipment = sd.get('shipment') if isinstance(sd.get('shipment'), dict) else {}
    names: list[str] = []
    for w in shipment.get('construction_workers') or []:
        name = w.get('name') if isinstance(w, dict) else w
        name = str(name or '').strip()
        if name and name not in names:
            names.append(name)
    return names


def _full_sheet_extras(sd: dict[str, Any], items: list[Any], construction_date: Any, stage_label: str) -> dict[str, Any]:
    customer = (sd.get('parties') or {}).get('customer') or {}
    orderer = (sd.get('parties') or {}).get('orderer') or {}
    site = sd.get('site') or {}
    phone = str(customer.get('phone') or '').strip()
    first_item, all_items = _production_first_item(sd)
    steps = production_home_steps(sd, mark_now=stage_label == '제작중')
    for step in steps:
        step['meta'] = ''
    raw_steps = ((sd.get('production') or {}).get('steps')) if isinstance(sd.get('production'), dict) else None
    if isinstance(raw_steps, list):
        by_key = {str(s.get('key')): s for s in raw_steps if isinstance(s, dict)}
        for step in steps:
            src = by_key.get(step['key'])
            if step['done'] and src:
                step['meta'] = ' · '.join(p for p in (str(src.get('by_name') or '').strip(), _format_at_kst(src.get('at'))) if p)
    production = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    defects = production.get('defects') if isinstance(production.get('defects'), list) else []
    latest = defects[-1] if defects and isinstance(defects[-1], dict) else None
    return {
        'phone': phone or '-',
        'orderer_name': str(orderer.get('name') or '').strip(),
        'phone_digits': re.sub(r'\D', '', phone),
        'address': (site.get('address_full') or site.get('address_main') or '-'),
        'measurement_md': _prod_sheet_load_md(((sd.get('schedule') or {}).get('measurement') or {}).get('date')),
        'construction_label': _construction_label(construction_date),
        'construction_workers': _worker_names(sd),
        'product_label': _production_product_label(all_items or items),
        'material': _production_material(first_item),
        'drawing_files': _prod_sheet_drawing_files(sd),
        'steps': steps,
        'steps_done': sum(1 for s in steps if s['done']),
        'latest_defect': {
            'reason': str(latest.get('reason') or ''),
            'meta': ' '.join(p for p in (str(latest.get('by_name') or '').strip(), _format_at_kst(latest.get('at'))) if p),
        } if latest else None,
    }


def build_production_sheet_view(db: Any, order: Order, user: Any, *, full: bool = False) -> dict[str, Any]:
    """작업 시트 뷰 모델. 쿼리: current run 1 + 도면 게이트 + 변경 알림(OrderEvent IN) — 옆 시트와 같다.

    Args:
        db: 세션. order: 이미 읽은 ``Order``. user: 보는 사람(변경 알림 ack 판정).
        full: 전체 화면 시트 키(전화·주소·도면 전체·공정·최근 불량)를 덧붙인다.
    """
    sd = _ensure_dict(order.structured_data)
    items = active_items(sd)  # 취소 품목은 생산 시트에서 뺀다(DRAWING-PARTIAL-CONFIRM)
    construction_date = (((sd.get('schedule') or {}).get('construction') or {}).get('date'))
    notes_raw = sd.get('notes')
    _prod = sd.get('production') if isinstance(sd.get('production'), dict) else {}
    _hold = _prod.get('hold') if isinstance(_prod.get('hold'), dict) else {}
    _rework = _prod.get('rework') if isinstance(_prod.get('rework'), dict) else {}
    has_run = (
        db.query(ProductionRun.id)
        .filter(ProductionRun.order_id == order.id, ProductionRun.is_current.is_(True))
        .first()
        is not None
    )
    stage_label = _production_stage_label_from_stage(order.erp_stage_code, has_run) or '기타'
    is_sales_approved = _production_quest_sales_state(sd, stage_label, order.erp_stage_code)[0]
    sheet: dict[str, Any] = {
        'id': order.id,
        'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
        'load_md': _prod_sheet_load_md(construction_date),
        'total_units_display': _prod_sheet_total_units(items),
        'spec_rows_view': _prod_sheet_spec_rows_view(items),
        'notes_text': notes_raw.strip() if isinstance(notes_raw, str) else '',
        'drawing_thumb': _prod_sheet_drawing_thumb(sd),
        'hold_active': bool(_hold.get('active')),
        'hold_reason': (_hold.get('reason') or '').strip() if isinstance(_hold.get('reason'), str) else '',
        'rework_active': bool(_rework.get('active')),
        'rework_reason': (_rework.get('reason') or '').strip() if isinstance(_rework.get('reason'), str) else '',
        'rework_count': int(_rework.get('count') or 0),
        'hold_history': _prod.get('hold_history') if isinstance(_prod.get('hold_history'), list) else [],
        'stage': stage_label,
        'is_sales_approved': bool(is_sales_approved),
    }
    attach_production_drawing_gate(db, [sheet], {order.id: order})
    _sc = collect_production_change_alerts(db, [order], user.id if user else None).get(order.id) or {"alerts": [], "history": []}
    sheet['change_alerts'] = _sc['alerts']
    sheet['has_changes'] = bool(_sc['alerts'])
    sheet['change_history'] = _sc['history']
    sheet['has_change_history'] = bool(_sc['history'])
    if full:
        sheet.update(_full_sheet_extras(sd, items, construction_date, stage_label))
    return sheet
