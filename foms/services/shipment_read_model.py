"""ERP 출고 대시보드 read-model (Batch 3 shipment 구조-추출, 동작 보존).

`erp_shipment_dashboard()`의 panel aggregates(14일 창 시공 건수/배정 작업자/스펙 단위)
compute slice를 분리한다. cache 키·fingerprint·get_or_compute는 라우트가 유지하고,
이 모듈은 캐시 미스 시 동일 결과를 산출한다(lambda 위임).

flat 모듈(shipment_dashboard_helpers 등 관행, subpackage __init__ 순환 회피).
"""
from __future__ import annotations

import datetime
import logging

from foms.services.shipment_dashboard_helpers import (
    is_as_order,
    extract_all_construction_dates,
    _normalize_worker_name,
    _get_order_spec_units,
)

logger = logging.getLogger(__name__)


def compute_shipment_panel_aggregates(panel_orders, range_start, range_end, worker_name_map):
    """출고 패널 집계(시공 건수/배정 작업자/스펙 단위) (구 _compute_shipment_panel_aggregates).

    Batch 3: 라우트 캐시 슬라이스 compute closure를 read-model로 분리(동작 보존).
    cache 키·fingerprint·get_or_compute는 라우트가 유지한다.

    Args:
        panel_orders: 14일 창 패널 주문 객체 리스트.
        range_start, range_end: 패널 날짜 창(date).
        worker_name_map: 정규화 작업자명 -> 설정 dict.

    Returns:
        {"construction_counts": {...}, "assigned_workers_by_date": {...},
         "spec_units_by_date": {...}} — 원본 closure와 동일 형태.
    """
    cc = {}
    aw = {}
    su = {}
    for order in panel_orders:
        if is_as_order(order):
            continue

        for date_value in extract_all_construction_dates(order):
            try:
                d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
            except Exception:
                # 데이터 오염 진단(에러 숨김 금지). 집계/화면은 기존대로 건너뛴다.
                logger.debug("shipment panel agg(cc): malformed construction date %r (order_id=%s)", date_value, getattr(order, "id", None))
                continue
            if d < range_start or d > range_end:
                continue
            key = d.strftime('%Y-%m-%d')
            cc[key] = cc.get(key, 0) + 1

        all_construction_dates = extract_all_construction_dates(order)
        for date_value in all_construction_dates:
            try:
                d = datetime.datetime.strptime(date_value, '%Y-%m-%d').date()
            except Exception:
                # 데이터 오염 진단(에러 숨김 금지). 작업자/스펙 집계는 기존대로 건너뛴다.
                logger.debug("shipment panel agg(workers): malformed construction date %r (order_id=%s)", date_value, getattr(order, "id", None))
                continue
            if d < range_start or d > range_end:
                continue
            key = d.strftime('%Y-%m-%d')

            shipment = {}
            if order.structured_data and isinstance(order.structured_data, dict):  # type: ignore
                shipment = (order.structured_data.get('shipment') or {})
            workers = shipment.get('construction_workers') or []
            for w in workers:
                name_key = _normalize_worker_name(w)
                if not name_key:
                    continue
                if name_key in worker_name_map:
                    aw.setdefault(key, set()).add(name_key)

            su[key] = su.get(key, 0.0) + _get_order_spec_units(order)
    return {
        "construction_counts": cc,
        "assigned_workers_by_date": {k: sorted(list(v)) for k, v in aw.items()},
        "spec_units_by_date": su,
    }
