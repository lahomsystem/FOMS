"""ERP 시공 대시보드 read-model — SQL pagination + KPI slim scan (production 패턴).

`erp_construction_dashboard()`의 쿼리·KPI·첨부·페이지네이션을 분리한다.
브라우즈/검색은 SQL offset/limit으로 full-row 300 hydrate를 피한다.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import bindparam, case as sql_case, text
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

# 시공 표시단계 ↔ flat erp_stage_code(ix_orders_erp_stage_code) 스코프 SSOT.
# _display_stage_for_order 매핑과 1:1 (시공대기/중=활성 codes, 시공완료=완료 codes).
CONSTRUCTION_ACTIVE_STAGE_CODES = ['CONSTRUCTION', '시공', 'CONSTRUCTING']
CONSTRUCTION_DONE_STAGE_CODES = ['COMPLETED', '완료', 'AS_WAIT', 'CS']
CONSTRUCTION_ALL_STAGE_CODES = CONSTRUCTION_ACTIVE_STAGE_CODES + CONSTRUCTION_DONE_STAGE_CODES


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
        return query.filter(Order.erp_stage_code.in_(CONSTRUCTION_ACTIVE_STAGE_CODES))
    if f_stage == "시공완료":
        return query.filter(Order.erp_stage_code.in_(CONSTRUCTION_DONE_STAGE_CODES))
    return query


def apply_construction_list_scope_filter(query: Query, f_stage: str) -> Query:
    """시공 대시보드 리스트를 시공 표시단계로 SQL 선(先)스코프한다(페이지네이션 정합).

    근본 원인: 단계 미선택 기본 뷰가 전체 60일 활성 리스트(모든 워크플로 단계)의
    newest-N 페이지 위에서 동작하면, 시공 단계 주문이 최근 접수 주문에 밀려 1페이지 밖으로
    나가 board가 0건이 된다(display 필터 ``build_construction_row_dtos``는 이미 로드된 페이지
    안에서만 시공 단계를 골라내므로, 페이지에 시공 주문이 없으면 살릴 게 없다).

    수정: display 필터가 유지하는 표시단계(시공대기/시공중/시공완료)와 **동일 스코프**를
    SQL에 선적용해, 페이지네이션이 전체 활성 리스트가 아닌 시공 주문 위에서 동작하게 한다.
    완료 단계도 포함한다 — 시공 대시보드는 완료 주문을 사진 재업로드·AS 액션과 함께
    렌더하는 계약(test_construction_mobile_completed_renders_reupload_as_and_edit)을 가진다.
    신규 무거운 쿼리 없음: 기존 ``ix_orders_erp_stage_code`` 인덱스 IN 필터를 60일 스코프에
    결합할 뿐이다(스테이지 칩과 동일한 flat 컬럼 경로 재사용).

    Args:
        query: 60일 활성 ERP 기본 쿼리(mine 필터 등 상위 조건 이미 적용).
        f_stage: 명시 단계('' 또는 시공대기/시공중/시공완료). 값이 있으면 그 단계로 좁히고,
            없으면(기본 뷰·검색) 전 시공 단계로 스코프한다.

    Returns:
        Query: 시공 단계로 스코프된 리스트 쿼리.
    """
    if f_stage:
        return apply_construction_stage_sql_filter(query, f_stage)
    return query.filter(Order.erp_stage_code.in_(CONSTRUCTION_ALL_STAGE_CODES))


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
        # ATTACH-LIFE-01: raw SQL 은 ORM 전역 tombstone 필터를 안 받는다 — 삭제된 첨부가
        # 카운트에 남지 않도록 여기서 명시적으로 제외한다(allowlist 대상, 계약 테스트가 고정).
        stmt = text(
            "SELECT order_id, COUNT(*) AS cnt FROM order_attachments "
            "WHERE order_id = ANY(:order_ids) AND deleted_at IS NULL GROUP BY order_id"
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


def construction_list_order_clauses(sort: str = '', sort_dir: str = 'asc') -> list[Any]:
    """시공 리스트 정렬 절을 만든다.

    Args:
        sort: 컬럼 헤더 정렬 키(``measure_date``/``construction_date``). 빈 값이면 기본.
        sort_dir: ``asc``/``desc``. 날짜 정렬일 때만 의미가 있다.

    Returns:
        `order_by`에 그대로 펼칠 절 목록. 기본은 기존과 같은 접수 최신순이고,
        날짜 정렬이면 빈 날짜를 항상 뒤로 보낸 뒤 방향을 적용한다.
    """
    column = {
        'measure_date': Order.erp_measurement_date,
        'construction_date': Order.erp_construction_date,
    }.get(sort)
    if column is None:
        return [Order.created_at.desc()]
    blank_last = sql_case((column.is_(None), 1), ((column == ''), 1), else_=0)
    direction = column.desc() if sort_dir == 'desc' else column.asc()
    return [blank_last.asc(), direction, Order.created_at.desc()]


def paginate_construction_orders(
    list_query: Query,
    *,
    page: int,
    per_page: int = CONSTRUCTION_DASHBOARD_PAGE_SIZE,
    total_cap: int,
    sort: str = '',
    sort_dir: str = 'asc',
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
        list_query.order_by(*construction_list_order_clauses(sort, sort_dir))
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
