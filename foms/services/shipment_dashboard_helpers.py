"""ERP 출고 대시보드 도메인 헬퍼 (Batch 3 shipment 구조-추출, 동작 보존).

주문 객체 기반 날짜/작업자/스펙 추출 + AS 상태 상수. 라우트와 (향후) read-model이 공유한다.
원본은 `foms/web/shipment/dashboard.py` 모듈 함수였고 verbatim 이전한다.
flat 모듈(measurement_* 관행, subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_template_filters import item_spec_w300_value

AS_SHIPMENT_STATUSES = ('AS', 'AS_RECEIVED', 'AS_COMPLETED')


def _normalize_worker_name(name):
    return str(name or '').strip().lower()


def _get_order_construction_date(order):
    """출고 대시보드용 시공일 결정 로직."""
    date_value = None
    if order.is_erp_order and order.structured_data:
        sd = order.structured_data
        cons = (sd.get('schedule') or {}).get('construction') or {}
        cons_date = cons.get('date')
        if cons_date:
            date_value = str(cons_date)

    # Legacy(기존 주문) 또는 Beta Fallback: scheduled_date가 있으면 사용
    if not date_value and order.scheduled_date:
        date_value = str(order.scheduled_date)
    return date_value


def is_as_order(order):
    return getattr(order, 'status', None) in AS_SHIPMENT_STATUSES


def extract_as_visit_dates(order):
    dates = set()
    if getattr(order, 'schedule_dates', None) is not None:
        for d in order.schedule_dates:
            if d.kind == 'as_visit' and d.date:
                dates.add(str(d.date))
        if dates:
            return dates

    structured_data = getattr(order, 'structured_data', None)
    if isinstance(structured_data, dict):
        schedule = structured_data.get('schedule') or {}
        visit = (schedule.get('as_visit') or {}).get('date') or ''
        for d in str(visit).split(','):
            if d.strip():
                dates.add(d.strip())
    return dates


def extract_dashboard_target_dates(order):
    if is_as_order(order):
        dates = extract_as_visit_dates(order)
        dates.update(extract_all_construction_dates(order))
        return dates
    return extract_all_construction_dates(order)


def extract_all_construction_dates(order):
    """주문에서 대표 시공일 + 항목별 시공일을 모두 추출 (schedule_dates DB 기반)."""
    dates = set()
    if getattr(order, 'schedule_dates', None) is not None:
        for d in order.schedule_dates:
            if d.kind == 'construction' and d.date:
                dates.add(d.date)
    else:
        # Fallback to legacy behavior if not loaded
        base_date = _get_order_construction_date(order)
        if base_date:
            for d in str(base_date).split(','):
                if d.strip():
                    dates.add(d.strip())
        if is_erp_order_record(order) and getattr(order, 'structured_data', None):
            sd = order.structured_data if isinstance(order.structured_data, dict) else {}
            for it in sd.get('items') or []:
                if not isinstance(it, dict):
                    continue
                date_val = it.get('construction_date')
                if date_val:
                    for d in str(date_val).split(','):
                        if d.strip():
                            dates.add(d.strip())
    return dates


def _get_order_spec_units(order):
    """주문의 spec_w300 단위 합산. 항목별 W합/300 (spec_rows 있으면 W 합산 후 /300)."""
    if not order.is_erp_order or not order.structured_data:
        return 0.0
    sd = order.structured_data or {}
    items = sd.get('items') or []
    total = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        total += item_spec_w300_value(it)
    return total
