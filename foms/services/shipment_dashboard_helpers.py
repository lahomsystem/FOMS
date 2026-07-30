"""ERP 출고 대시보드 도메인 헬퍼 (Batch 3 shipment 구조-추출, 동작 보존).

주문 객체 기반 날짜/작업자/스펙 추출 + AS 상태 상수. 라우트와 (향후) read-model이 공유한다.
원본은 `foms/web/shipment/dashboard.py` 모듈 함수였고 verbatim 이전한다.
flat 모듈(measurement_* 관행, subpackage __init__ 순환 회피).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from foms.services.erp_order_flags import is_erp_order_record
from foms.services.erp_template_filters import item_spec_w300_value
from foms.services.order_date_sync import _normalize_date_str

logger = logging.getLogger(__name__)

AS_SHIPMENT_STATUSES = ('AS', 'AS_RECEIVED', 'AS_COMPLETED')

_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


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


def _split_date_set(raw: Any) -> set[str]:
    """콤마 다중 날짜 문자열을 정규화된 ``YYYY-MM-DD`` 집합으로 분해한다.

    Args:
        raw: ``"2026-07-30,2026-07-31"`` 같은 자유 텍스트(빈 값 허용).

    Returns:
        정규화된 날짜 문자열 집합. 빈 값이면 빈 집합.
    """
    dates: set[str] = set()
    for part in str(raw or '').split(','):
        part = part.strip()
        if not part:
            continue
        nd = str(_normalize_date_str(part))
        if not _ISO_DATE_RE.match(nd):
            # 데이터 오염 진단(에러 숨김 금지). 비교는 그대로 문자열로 시도한다.
            logger.debug("shipment item date: malformed construction date %r", part)
        dates.add(nd)
    return dates


def visible_items_for_dates(
    order: Any,
    target_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """선택 날짜(또는 범위)에 출고되는 품목만 반환한다.

    품목 날짜 = ``item['construction_date']``(콤마 다중), 비어 있으면 주문 대표
    시공일(`_get_order_construction_date`)을 상속한다. 날짜 문맥이 없거나 필터
    결과가 0건이면 전 품목을 반환한다(제품 셀이 빈칸이 되는 것을 방지).

    Args:
        order: Order ORM 객체(또는 structured_data를 가진 동등 객체).
        target_date: 단일 날짜 모드의 선택 날짜(``YYYY-MM-DD``).
        date_from: 범위 모드 시작일. ``date_to``와 함께 지정해야 적용된다.
        date_to: 범위 모드 종료일.

    Returns:
        표시할 품목 dict 리스트.
    """
    sd = order.structured_data if isinstance(getattr(order, 'structured_data', None), dict) else {}
    items = sd.get('items') or []
    use_range = bool(date_from and date_to)
    if not items or not (target_date or use_range):
        return list(items)

    td = str(_normalize_date_str(target_date)) if target_date else None
    df = str(_normalize_date_str(date_from)) if use_range else None
    dt = str(_normalize_date_str(date_to)) if use_range else None
    order_dates = _split_date_set(_get_order_construction_date(order))

    visible: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        item_dates = _split_date_set(it.get('construction_date')) or order_dates
        if td is not None:
            match = td in item_dates
        else:
            match = any(df <= d <= dt for d in item_dates)
        if match:
            visible.append(it)
    return visible or list(items)


def order_spec_units(
    order: Any,
    target_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> float:
    """선택 날짜 기준 가시 품목의 W/300 자수 합.

    날짜 인자를 모두 생략하면 전 품목 합(기존 `_get_order_spec_units`와 동일 값).

    Args:
        order: Order ORM 객체.
        target_date: 단일 날짜 모드의 선택 날짜.
        date_from: 범위 모드 시작일.
        date_to: 범위 모드 종료일.

    Returns:
        자수 합계(float).
    """
    if not order.is_erp_order or not order.structured_data:
        return 0.0
    total = 0.0
    for it in visible_items_for_dates(order, target_date, date_from, date_to):
        if isinstance(it, dict):
            total += item_spec_w300_value(it)
    return total


def visible_spec_units(order: Any) -> float:
    """행에 부착된 ``shipment_visible_items`` 기준 자수 합(미부착 시 전 품목).

    라우트가 날짜 필터로 부착한 가시 품목과 화면 표시가 어긋나지 않도록, KPI·팀
    합계는 날짜를 다시 판정하지 않고 부착 결과를 그대로 합산한다.

    Args:
        order: `visible_items_for_dates` 결과가 부착된 Order ORM 객체.

    Returns:
        자수 합계(float).
    """
    if not order.is_erp_order or not order.structured_data:
        return 0.0
    items = getattr(order, 'shipment_visible_items', None)
    if items is None:
        items = (order.structured_data or {}).get('items') or []
    return sum(item_spec_w300_value(it) for it in items if isinstance(it, dict))


def _get_order_spec_units(order):
    """(하위호환) 날짜 문맥이 없는 호출부용 전 품목 자수 합. `order_spec_units` 위임."""
    return order_spec_units(order)
