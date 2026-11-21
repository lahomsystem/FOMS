"""ERP 출고 대시보드 행 보강·정렬·모바일 큐 표시 헬퍼 (Batch 3 shipment 구조-추출, 동작 보존).

`erp_shipment_dashboard()`의 목록 rows 후처리(표시 파생 필드 보강·정렬)와 모바일 v2 큐
카드 행 빌드를 분리한다. recommendation_link/as_content_text/as_material_text/
is_production_approved 판정, 정렬 키, 모바일 큐 메타 조립을 원본과 1:1 동일하게 유지한다(캐시 아님).
쿼리/패널 집계/derived는 shipment_read_model이 담당한다(한 슬라이스 한 경계).
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from typing import Any

from foms.services.erp_display import _ensure_dict, manager_display_name
from foms.services.as_content_safety import as_content_html_to_text
from foms.services.orders.as_log import latest_client_log_text
from foms.services.orders.schedule_row_kind import (
    ROW_AS_VISIT_TOO_ATTR,
    ROW_IS_AS_ATTR,
    is_as_status,
    is_main_flow_open,
    row_as_visit_too,
    row_is_as,
    row_kind,
)
from foms.services.shipment_dashboard_helpers import (
    extract_all_construction_dates,
    extract_as_visit_dates,
    is_as_order,
    visible_spec_units,
    _get_order_construction_date,
)
from foms.services.erp_mobile_order_display import (
    build_mobile_queue_order_row,
    build_mobile_queue_batch_context,
)

__all__ = [
    "attach_shipment_row_kinds",
    "enrich_shipment_rows",
    "sort_shipment_rows",
    "build_shipment_mobile_queue_rows",
]


def attach_shipment_row_kinds(
    rows: list[Any],
    *,
    target_date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> None:
    """목록 rows 에 그날(또는 기간) 줄 종류를 붙인다 — 시공 줄인가 AS 방문 줄인가, 같은 날 AS 방문도 있는가.

    정렬 · PC 표 · 하루치 출고표 · 폰 카드가 같은 값을 읽는다(``schedule_row_kind.row_is_as``).
    날짜가 필요한 것은 본 흐름이 열린 AS 주문뿐이라 그 주문만 일정 줄을 읽는다(그 밖은 추가 조회 없음).

    Args:
        rows: 출고 줄 Order 리스트(제자리에서 칸을 붙인다).
        target_date: 하루 보기의 고른 날(``YYYY-MM-DD``).
        date_from: 기간 보기 시작일(``date_to`` 와 같이 줘야 쓴다).
        date_to: 기간 보기 끝일.
    """
    use_range = bool(date_from and date_to)

    def _in_scope(dates: Any) -> set[str]:
        days = {str(d) for d in dates}
        if target_date:
            return days & {str(target_date)}
        if use_range:
            return {d for d in days if str(date_from) <= d <= str(date_to)}
        return days

    for r in rows:
        dated = is_as_status(r) and is_main_flow_open(r)
        cons_days = _in_scope(extract_all_construction_dates(r)) if dated else set()
        visit_days = _in_scope(extract_as_visit_dates(r)) if dated else set()
        kind = row_kind(r, on_construction_date=bool(cons_days), on_as_visit_date=bool(visit_days))
        setattr(r, ROW_IS_AS_ATTR, kind.is_as)
        # "AS 방문도"는 시공과 AS 방문이 같은 날일 때만 — 기간 보기에서 다른 날 방문까지 붙이면 그날 일로 읽힌다.
        setattr(r, ROW_AS_VISIT_TOO_ATTR, kind.as_visit_too and bool(cons_days & visit_days))


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
    """목록 rows를 AS 줄 여부→시공자→담당자→id 순으로 in-place 정렬한다(AS 줄 = 줄에 붙은 그날 줄 종류)."""
    def get_manager_name_for_sort(order):
        if order.is_erp_order and order.structured_data:
            sd = order.structured_data
            erp_manager = manager_display_name(sd.get('parties'))
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
        1 if row_is_as(o) else 0,
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
                # 카드 종류 = 그날 줄 종류(본 흐름이 열린 AS 주문의 시공일 카드는 시공 카드).
                "is_as": row_is_as(order),
                "as_visit_too": row_as_visit_too(order),
                "as_content_text": getattr(order, "as_content_text", "") or "",
                "recommendation_link": getattr(order, "shipment_as_recommendation_link", None),
                # 모바일 큐·태블릿 그리드 표시용 파생(추가 쿼리 없음 — 이미 로드된 structured_data/scheduled_date만 사용).
                # primary_date: 대표 시공일(AS 줄은 as_visit 방문일) → 날짜 그룹 헤더 키. schedule_dates
                # 지연로딩을 피하려 SSOT(sd.schedule.*) + scheduled_date 컬럼만 읽는다(N+1 가드 준수).
                "primary_date": (
                    str(((sd.get("schedule") or {}).get("as_visit") or {}).get("date") or "")
                    if row_is_as(order)
                    else (_get_order_construction_date(order) or "")
                ),
                # sales_delivery(영업택배): structured_data.shipment.sales_delivery is True 계약(field_update.py와 동일).
                "sales_delivery": shipment.get("sales_delivery") is True,
                # D: 패킹 진행 파생(패킹 N/M 라벨·배지 SSOT — v2 큐).
                "packing_present": _packing_present,
                "packing_total": len(_packing_items) if _packing_present else 0,
                "packing_checked": (
                    sum(1 for it in _packing_items if isinstance(it, dict) and it.get("checked"))
                    if _packing_present
                    else 0
                ),
                # P6: 출발 보고 완료 여부(카드 라벨을 "출발 보고됨"으로 전환).
                "packing_departed": _packing_departed,
                # 협력사 주문 "입금 대기"(설계서 2026-11-03-partner-statement §5.7) — 라우트가 행에 붙인 값(PC 표 · 태블릿과 같은 값).
                "partner_payment_pending": bool(getattr(order, "partner_payment_pending", False)),
            }
            mobile_queue_rows.append(row)
    return mobile_queue_rows
