"""ERP 출고 대시보드 행 보강·정렬·모바일 큐 표시 헬퍼 (Batch 3 shipment 구조-추출, 동작 보존).

`erp_shipment_dashboard()`의 목록 rows 후처리(표시 파생 필드 보강·정렬)와 모바일 v2 큐
카드 행 빌드를 분리한다. recommendation_link/as_content_text/as_material_text/
is_production_approved 판정, 정렬 키, 모바일 큐 메타 조립을 원본과 1:1 동일하게 유지한다(캐시 아님).
쿼리/패널 집계/derived는 shipment_read_model이 담당한다(한 슬라이스 한 경계).
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from typing import Any

from foms.services.erp_display import _ensure_dict
from foms.services.as_content_safety import as_content_html_to_text
from foms.services.orders.as_log import latest_client_log_text
from foms.services.shipment_dashboard_helpers import (
    is_as_order,
    visible_spec_units,
    _get_order_construction_date,
)
from foms.services.erp_mobile_order_display import (
    build_mobile_queue_order_row,
    build_mobile_queue_batch_context,
)

__all__ = [
    "enrich_shipment_rows",
    "sort_shipment_rows",
    "build_shipment_mobile_queue_rows",
]


def enrich_shipment_rows(rows: list[Any]) -> None:
    """목록 rows에 표시용 파생 필드를 in-place 보강한다.

    shipment_as_recommendation_link / as_content_text / as_material_text /
    is_production_approved를 원본 라우트와 1:1 동일하게 설정한다.
    """
    # lazy import: api 레이어 상수(services→api 순환 회피, 원본 패턴 유지)
    from foms.api.shipment.recommendations import SHREC_SOURCE

    for r in rows:
        r.shipment_as_recommendation_link = None
        r.structured_data = _ensure_dict(r.structured_data)  # type: ignore[assignment]
        sd = r.structured_data
        shipment = (sd.get('shipment') or {}) if isinstance(sd, dict) else {}
        r.as_content_text = as_content_html_to_text(shipment.get('as_content') or '')
        r.as_material_text = ""

        if is_as_order(r):
            r.as_material_text = as_content_html_to_text(
                latest_client_log_text(sd, log_type="material"), already_sanitized=True
            )
            sched = (sd.get("schedule") or {}) if isinstance(sd, dict) else {}
            av = sched.get("as_visit") if isinstance(sched, dict) else {}
            sr = av.get("shipment_recommendation") if isinstance(av, dict) else None
            if isinstance(sr, dict) and sr.get("source") == SHREC_SOURCE:
                sid_raw = sr.get("shipment_order_id")
                try:
                    sid_int = int(sid_raw) if sid_raw is not None else None
                except (TypeError, ValueError):
                    sid_int = None
                info_raw = sr.get("as_info_id")
                try:
                    info_int = int(info_raw) if info_raw is not None else None
                except (TypeError, ValueError):
                    info_int = None
                r.shipment_as_recommendation_link = {
                    "shipment_order_id": sid_int,
                    "as_order_id": r.id,
                    "as_info_id": info_int,
                    "applied_date": str(sr.get("applied_date") or av.get("date") or ""),
                }

        r.is_production_approved = False
        quests = sd.get('quests') or []
        production_quest = next((q for q in quests if q.get('stage') in ('PRODUCTION', '생산')), None)

        if production_quest:
            quest_status = production_quest.get('status', 'OPEN')
            if quest_status == 'COMPLETED':
                r.is_production_approved = True
            else:
                team_approvals = production_quest.get('team_approvals') or {}
                required_teams = production_quest.get('required_approvals') or []
                if required_teams:
                    all_approved = all(
                        (team_approvals.get(team, {}).get('approved') if isinstance(team_approvals.get(team), dict) else team_approvals.get(team))
                        for team in required_teams
                    )
                    r.is_production_approved = all_approved


def sort_shipment_rows(rows: list[Any]) -> None:
    """목록 rows를 AS여부→시공자→담당자→id 순으로 in-place 정렬한다."""
    def get_manager_name_for_sort(order):
        if order.is_erp_order and order.structured_data:
            sd = order.structured_data
            erp_manager = (((sd.get('parties') or {}).get('manager') or {}).get('name'))
            if erp_manager:
                return erp_manager
        return order.manager_name or ''

    def get_construction_worker_key_for_sort(order):
        """시공자별 그룹·정렬용: 첫 번째 유효한 시공자 또는 빈 문자열."""
        if not order.is_erp_order or not order.structured_data:
            return ''
        shipment = (order.structured_data.get('shipment') or {})
        workers = shipment.get('construction_workers') or []
        for w in workers:
            w_str = str(w).strip() if w else ''
            if w_str:
                return w_str
        return ''

    rows.sort(key=lambda o: (
        1 if is_as_order(o) else 0,
        get_construction_worker_key_for_sort(o) or 'ZZZ',
        get_manager_name_for_sort(o) or 'ZZZ',
        o.id
    ))


def build_shipment_mobile_queue_rows(
    db, rows: list[Any], current_user, *, mobile_v2_active: bool
) -> list[dict[str, Any]]:
    """모바일 v2 활성 시 목록 rows로 모바일 큐 카드 행을 만든다.

    mobile_v2_active가 False면 빈 리스트를 반환한다(원본 동작 동일).
    """
    mobile_queue_rows: list[dict[str, Any]] = []
    if mobile_v2_active:
        batch_ctx = build_mobile_queue_batch_context(db, rows, drawing_preview_only=True)
        for order in rows:
            row = build_mobile_queue_order_row(db, order, current_user, batch_ctx=batch_ctx)
            sd = order.structured_data if isinstance(order.structured_data, dict) else {}
            shipment = sd.get("shipment") or {}
            drawing_managers = [
                str(value).strip()
                for value in (shipment.get("drawing_managers") or [])
                if str(value or "").strip()
            ]
            if not drawing_managers and shipment.get("drawing_manager"):
                drawing_managers = [str(shipment.get("drawing_manager")).strip()]
            construction_workers = [
                str(value).strip()
                for value in (shipment.get("construction_workers") or [])
                if str(value or "").strip()
            ]
            site_extra = []
            for value in (shipment.get("site_extra") or []):
                if isinstance(value, dict):
                    text_value = str(value.get("text") or "").strip()
                else:
                    text_value = str(value or "").strip()
                if text_value:
                    site_extra.append(text_value)
            row["customer_name"] = row.get("customer_name") or order.customer_name or "-"
            if row["customer_name"] == "-":
                row["customer_name"] = order.customer_name or "-"
            row["phone"] = row.get("phone") if row.get("phone") not in (None, "", "-") else (order.phone or "-")
            row["address"] = row.get("address") if row.get("address") not in (None, "", "-") else (order.address or "-")
            row["manager_name"] = row.get("manager_name") if row.get("manager_name") not in (None, "", "-") else (order.manager_name or "-")
            row["orderer_name"] = row.get("orderer_name") or getattr(order, "orderer_name", None)
            row["product_subtitle"] = row.get("product_subtitle") or (getattr(order, "product", None) or "")
            # D: 패킹 카운터 파생(추가 쿼리 없음 — 이미 로드된 sd.shipment.packing만). 없으면 present=False.
            _packing = shipment.get("packing")
            _packing_items = _packing.get("items") if isinstance(_packing, dict) else None
            _packing_present = isinstance(_packing_items, list) and len(_packing_items) > 0
            # P6: 출발 보고(상차 완료) 여부 — departed_at 존재 시 카드 라벨을 "출발 보고됨" 배지로 전환.
            _packing_departed = bool(_packing.get("departed_at")) if isinstance(_packing, dict) else False
            row["shipment_meta"] = {
                "construction_time": shipment.get("construction_time") or "",
                "drawing_managers": drawing_managers,
                "construction_workers": construction_workers,
                "site_extra": site_extra,
                # 선택 날짜에 출고되는 품목 기준(라우트가 부착한 shipment_visible_items).
                # 미부착이면 전 품목 합 — PC 그리드/KPI와 같은 규칙.
                "spec_units": visible_spec_units(order),
                "is_as": is_as_order(order),
                "as_content_text": getattr(order, "as_content_text", "") or "",
                "recommendation_link": getattr(order, "shipment_as_recommendation_link", None),
                # v3 홈 표시용 파생(추가 쿼리 없음 — 이미 로드된 structured_data/scheduled_date만 사용).
                # primary_date: 대표 시공일(AS는 as_visit 방문일) → v3 날짜 그룹 헤더 키. schedule_dates
                # 지연로딩을 피하려 SSOT(sd.schedule.*) + scheduled_date 컬럼만 읽는다(N+1 가드 준수).
                "primary_date": (
                    str(((sd.get("schedule") or {}).get("as_visit") or {}).get("date") or "")
                    if is_as_order(order)
                    else (_get_order_construction_date(order) or "")
                ),
                # sales_delivery(영업택배): structured_data.shipment.sales_delivery is True 계약(field_update.py와 동일).
                "sales_delivery": shipment.get("sales_delivery") is True,
                # D: 패킹 진행 파생(패킹 N/M 라벨·배지 SSOT — v2 큐 + v3 홈 공용).
                "packing_present": _packing_present,
                "packing_total": len(_packing_items) if _packing_present else 0,
                "packing_checked": (
                    sum(1 for it in _packing_items if isinstance(it, dict) and it.get("checked"))
                    if _packing_present
                    else 0
                ),
                # P6: 출발 보고 완료 여부(카드 라벨을 "출발 보고됨"으로 전환).
                "packing_departed": _packing_departed,
            }
            mobile_queue_rows.append(row)
    return mobile_queue_rows
