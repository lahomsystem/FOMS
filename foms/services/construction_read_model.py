"""ERP 시공 대시보드 read-model — SQL pagination + KPI slim scan (production 패턴).

`erp_construction_dashboard()`의 쿼리·KPI·첨부·페이지네이션을 분리한다.
브라우즈/검색은 SQL offset/limit으로 full-row 300 hydrate를 피한다.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Query

from models import Order
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    self_measurement_four_checks_done,
)
from foms.services.construction_dashboard_display import _display_stage_for_order
from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.foms_unified_search import _compact

CONSTRUCTION_DASHBOARD_PAGE_SIZE = 50
CONSTRUCTION_BROWSE_CAP = 300
CONSTRUCTION_SEARCH_CAP = 500


def apply_construction_stage_sql_filter(query: Query, f_stage: str) -> Query:
    """Coarse workflow stage filter (display module may refine further).

    단계 필터는 flat 컬럼 ``Order.erp_stage_code``(index=True)를 직접 참조한다.
    JSONB path cast(``structured_data['workflow']['stage']``, 인덱스 없음)를 제거해
    ``ix_orders_erp_stage_code`` 인덱스 스캔으로 전환한다. erp_stage_code는
    workflow.stage 원문 그대로(JSON 따옴표 없음)이므로 IN 목록은 따옴표를 제거한다.
    스코프 값은 기존 JSONB 필터와 1:1 동일(순수 인덱스 전환, 스코프 변경 없음).
    한글 값(시공/완료)은 운영에 없으나 sync가 원문 복사라 미래 방어로 유지(비용 0).
    """
    if not f_stage:
        return query
    if f_stage in ("시공대기", "시공중"):
        return query.filter(Order.erp_stage_code.in_(['CONSTRUCTION', '시공', 'CONSTRUCTING']))
    if f_stage == "시공완료":
        return query.filter(Order.erp_stage_code.in_(['COMPLETED', '완료', 'AS_WAIT', 'CS']))
    return query


def compute_construction_kpis_and_badges(query: Query) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    """60일 ERP 윈도우 KPI + step_stats (slim JSONB projection)."""
    sd_json = Order.structured_data
    kpi_rows = query.order_by(None).with_entities(
        Order.id,
        sd_json["flags"].label("sd_flags"),
        sd_json["schedule"].label("sd_schedule"),
        sd_json["workflow"].label("sd_workflow"),
        Order.is_self_measurement,
    ).all()
    step_stats = {
        "시공대기": {"count": 0, "overdue": 0, "imminent": 0},
        "시공중": {"count": 0, "overdue": 0, "imminent": 0},
        "시공완료": {"count": 0, "overdue": 0, "imminent": 0},
    }
    kpis = {
        "urgent_count": 0,
        "construction_d3_count": 0,
        "measurement_d4_count": 0,
        "production_d2_count": 0,
    }
    for row in kpi_rows:
        if row.is_self_measurement and not self_measurement_four_checks_done(row):
            continue
        structured_data = {
            "flags": _ensure_dict(row.sd_flags),
            "schedule": _ensure_dict(row.sd_schedule),
            "workflow": _ensure_dict(row.sd_workflow),
        }
        display_stage = _display_stage_for_order(row, structured_data)
        if not display_stage:
            continue
        alerts = _erp_alerts(row, structured_data, 0)
        if display_stage in step_stats:
            step_stats[display_stage]["count"] += 1
            if alerts.get("construction_d3"):
                step_stats[display_stage]["imminent"] += 1
        if alerts.get("urgent"):
            kpis["urgent_count"] += 1
        if alerts.get("construction_d3"):
            kpis["construction_d3_count"] += 1
    return step_stats, kpis


def fetch_construction_attachment_counts(db: Any, orders: list[Any]) -> dict[int, int]:
    """Batch attachment counts for page orders."""
    att_counts: dict[int, int] = {}
    if not orders:
        return att_counts
    try:
        order_ids = [order.id for order in orders]
        stmt = text(
            "SELECT order_id, COUNT(*) AS cnt FROM order_attachments "
            "WHERE order_id = ANY(:order_ids) GROUP BY order_id"
        )
        stmt = stmt.bindparams(bindparam("order_ids", value=order_ids))
        rows = db.execute(stmt).fetchall()
        for row in rows:
            att_counts[int(row.order_id)] = int(row.cnt)
    except Exception as exc:
        logging.getLogger(__name__).warning("att_counts query failed: %s", exc)
    return att_counts


def capped_list_total(list_query: Query, *, cap: int) -> int:
    """Return min(count, cap) without loading rows."""
    return min(int(list_query.order_by(None).count()), cap)


def paginate_construction_orders(
    list_query: Query,
    *,
    page: int,
    per_page: int = CONSTRUCTION_DASHBOARD_PAGE_SIZE,
    total_cap: int,
) -> tuple[int, int, int, list[Any]]:
    """SQL page fetch; total_orders uses cap for browse/search windows."""
    if page < 1:
        page = 1
    total_orders = capped_list_total(list_query, cap=total_cap)
    total_pages = max(1, (total_orders + per_page - 1) // per_page) if total_orders else 0
    if total_pages and page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page
    page_rows = (
        list_query.order_by(Order.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    return page, total_pages, total_orders, page_rows


def compute_construction_summary_blob(query: Query) -> dict[str, Any]:
    """KPI + step_stats JSON DTO for micro-cache."""
    step_stats, kpis = compute_construction_kpis_and_badges(query)
    return {"step_stats": step_stats, "kpis": kpis}


def build_construction_process_steps(step_stats: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    """Process step tiles from step_stats."""
    return [
        {"label": "시공대기", "display": "시공대기", **step_stats["시공대기"]},
        {"label": "시공중", "display": "시공중", **step_stats["시공중"]},
        {"label": "시공완료", "display": "시공완료", **step_stats["시공완료"]},
    ]


def apply_construction_search_filter(list_query: Query, f_q: str) -> Query:
    """Search predicate on list query."""
    term = f"%{_compact(f_q)}%"
    if term.strip("%"):
        return list_query.filter(erp_order_dashboard_search_predicate(term))
    return list_query
