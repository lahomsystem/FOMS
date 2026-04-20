"""Shared helpers for extracting measurement dates from orders."""

from __future__ import annotations

from foms.services.erp_display import _normalize_date_to_yyyymmdd
from foms.services.erp_order_flags import is_erp_order_record


def _append_unique_dates(target_dates, seen_dates, raw_value) -> None:
    if not raw_value:
        return
    for chunk in str(raw_value).split(','):
        normalized = _normalize_date_to_yyyymmdd(chunk.strip())
        if not normalized or normalized in seen_dates:
            continue
        seen_dates.add(normalized)
        target_dates.append(normalized)


def extract_all_measurement_dates(order):
    """주문에서 대표 실측일 + 항목별 실측일을 모두 추출.

    원칙:
    - 우선 schedule_dates read model을 읽는다.
    - stale/누락 데이터에 대비해 legacy 컬럼과 structured_data 원본도 합친다.
    """
    dates = []
    seen_dates = set()
    schedule_dates = getattr(order, 'schedule_dates', None)
    if schedule_dates is not None:
        for d in order.schedule_dates:
            if d.kind == 'measurement' and d.date:
                _append_unique_dates(dates, seen_dates, d.date)

    _append_unique_dates(dates, seen_dates, getattr(order, 'measurement_date', None))

    if is_erp_order_record(order) and getattr(order, 'structured_data', None):
        sd = order.structured_data if isinstance(order.structured_data, dict) else {}
        erp_date = (sd.get('schedule') or {}).get('measurement') or {}
        _append_unique_dates(dates, seen_dates, erp_date.get('date'))
        for it in sd.get('items') or []:
            if not isinstance(it, dict):
                continue
            _append_unique_dates(dates, seen_dates, it.get('measurement_date'))

    return dates
