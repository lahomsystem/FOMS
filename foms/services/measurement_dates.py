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
    - ERP 주문은 structured schedule의 실측일을 canonical로 본다.
    - stale/누락 데이터에 대비해 legacy 컬럼과 structured_data 원본도 합친다.
    """
    dates = []
    seen_dates = set()
    is_erp_order = is_erp_order_record(order)
    sd = order.structured_data if isinstance(getattr(order, 'structured_data', None), dict) else {}
    erp_date = (sd.get('schedule') or {}).get('measurement') or {}
    has_erp_measurement_date = False
    if is_erp_order and isinstance(erp_date, dict):
        for chunk in str(erp_date.get('date') or '').split(','):
            if _normalize_date_to_yyyymmdd(chunk.strip()):
                has_erp_measurement_date = True
                break

    schedule_dates = getattr(order, 'schedule_dates', None)
    if schedule_dates is not None:
        for d in order.schedule_dates:
            if (
                is_erp_order
                and has_erp_measurement_date
                and getattr(d, 'source', None) == 'legacy_column'
            ):
                continue
            if d.kind == 'measurement' and d.date:
                _append_unique_dates(dates, seen_dates, d.date)

    if not (is_erp_order and has_erp_measurement_date):
        _append_unique_dates(dates, seen_dates, getattr(order, 'measurement_date', None))

    if is_erp_order and sd:
        if isinstance(erp_date, dict):
            _append_unique_dates(dates, seen_dates, erp_date.get('date'))
        for it in sd.get('items') or []:
            if not isinstance(it, dict):
                continue
            _append_unique_dates(dates, seen_dates, it.get('measurement_date'))

    return dates
