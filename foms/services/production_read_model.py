"""ERP 생산 대시보드 read-model (Batch 4 production 구조-추출, 동작 보존).

`erp_production_dashboard()`의 SQL 쿼리 빌드·단계 버킷 카운트·KPI/프로세스맵 배지 집계·
첨부 카운트·페이지네이션을 분리한다. 필터 적용 순서, 전체셋 KPI 스캔(의도적; 페이지 50건과
무관, 성능 최적화는 별도 웨이브), 정렬/페이지 규칙을 원본과 1:1 동일하게 유지한다.
row DTO 조립/표시는 production_dashboard_display가 담당한다(한 슬라이스 한 경계).
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import String, bindparam, case as sql_case, cast, func, or_, text
from sqlalchemy.orm import Query

from models import Order
from foms.services.erp_display import _ensure_dict, _erp_alerts, _erp_get_stage

PRODUCTION_DASHBOARD_PAGE_SIZE = 50


def build_production_orders_query(
    db: Any,
    user: Any,
    f_stage: str,
    f_q: str,
    erp_mine_only: bool,
    stage_col: Any,
) -> Query:
    """필터를 적용한 생산 대시보드용 ERP Order 쿼리(정렬 전)."""
    _q = db.query(Order).filter(Order.active_filter(), Order.is_erp_order.is_(True))
    base_stages = ['"고객컨펌"', '"생산"', '"시공"', '"CONFIRM"', '"PRODUCTION"', '"CONSTRUCTION"']
    _q = _q.filter(stage_col.in_(base_stages))

    if f_stage:
        if f_stage == '제작대기':
            _q = _q.filter(stage_col.in_(['"고객컨펌"', '"CONFIRM"']))
        elif f_stage == '제작중':
            _q = _q.filter(stage_col.in_(['"생산"', '"PRODUCTION"']))
        elif f_stage == '제작완료':
            _q = _q.filter(stage_col.in_(['"시공"', '"CONSTRUCTION"']))

    if f_q:
        search_term = f"%{f_q}%"
        _q = _q.filter(
            or_(
                Order.customer_name.ilike(search_term),
                Order.phone.ilike(search_term),
                Order.address.ilike(search_term),
                cast(Order.structured_data, String).ilike(search_term),  # perf-ok: ix_orders_structured_data_text_trgm
            )
        )

    if erp_mine_only and user:
        # lazy import: erp_permissions canonical path (namespace 계약 + circular 회피, 원본 패턴 유지)
        from foms.services.erp_permissions import build_mine_sql_filter
        conds = build_mine_sql_filter(user)
        if conds:
            _q = _q.filter(or_(*conds))
        else:
            _q = _q.filter(Order.id == -1)

    return _q


def production_stage_bucket_expr(stage_col: Any) -> Any:
    """DB 단계 JSON → 제작대기/제작중/제작완료 버킷."""
    return sql_case(
        (stage_col.in_(['"고객컨펌"', '"CONFIRM"']), '제작대기'),
        (stage_col.in_(['"생산"', '"PRODUCTION"']), '제작중'),
        (stage_col.in_(['"시공"', '"CONSTRUCTION"']), '제작완료'),
        else_='기타',
    )


def empty_production_step_stats() -> dict[str, dict[str, int]]:
    return {
        '제작대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }


def fill_production_step_counts(
    _q: Query, stage_bucket_expr: Any, step_stats: dict[str, dict[str, int]]
) -> None:
    """step_stats['*']['count']만 SQL GROUP BY로 채운다."""
    stats_rows = (
        _q.order_by(None)
        .with_entities(stage_bucket_expr.label('bucket'), func.count(Order.id).label('cnt'))
        .group_by(stage_bucket_expr)
        .all()
    )
    for row in stats_rows:
        if row.bucket in step_stats:
            step_stats[row.bucket]['count'] = row.cnt


def _kpi_stage_label_from_erp_stage(stage: str) -> str | None:
    if stage not in ('고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION'):
        return None
    if stage in ('CONFIRM', '고객컨펌'):
        return '제작대기'
    if stage in ('PRODUCTION', '생산'):
        return '제작중'
    if stage in ('CONSTRUCTION', '시공'):
        return '제작완료'
    return None


def compute_production_kpis_and_badges(
    _q: Query, step_stats: dict[str, dict[str, int]]
) -> tuple[list[Any], dict[str, int]]:
    """
    KPI 상단 알림 + 프로세스 맵 배지(임박/지연).

    필터와 동일한 전체 집합을 한 번 스캔한다(의도적; 페이지 50건과 무관).
    성능 최적화는 별도 웨이브에서 다룬다.
    """
    kpi_rows = _q.order_by(None).with_entities(Order.id, Order.structured_data).all()
    kpis = {
        'urgent_count': 0,
        'production_d2_count': 0,
        'measurement_d4_count': 0,
        'construction_d3_count': 0,
    }
    for kpi_row in kpi_rows:
        kpi_sd = _ensure_dict(kpi_row.structured_data)
        kpi_alerts = _erp_alerts(None, kpi_sd, 0)
        if kpi_alerts.get('urgent'):
            kpis['urgent_count'] += 1
        if kpi_alerts.get('production_d2'):
            kpis['production_d2_count'] += 1
        if kpi_alerts.get('measurement_d4'):
            kpis['measurement_d4_count'] += 1
        if kpi_alerts.get('construction_d3'):
            kpis['construction_d3_count'] += 1

        stage_label = _kpi_stage_label_from_erp_stage(_erp_get_stage(None, kpi_sd) or '')
        if not stage_label or stage_label not in step_stats:
            continue
        if kpi_alerts.get('production_d2'):
            step_stats[stage_label]['imminent'] += 1
        if kpi_alerts.get('drawing_overdue'):
            step_stats[stage_label]['overdue'] += 1

    return kpi_rows, kpis


def fetch_production_attachment_counts(db: Any, page_rows: list[Any]) -> dict[int, int]:
    att_counts: dict[int, int] = {}
    if not page_rows:
        return att_counts
    try:
        order_ids = [o.id for o in page_rows]
        stmt = text(
            "SELECT order_id, COUNT(*) AS cnt FROM order_attachments "
            "WHERE order_id = ANY(:order_ids) GROUP BY order_id"
        )
        stmt = stmt.bindparams(bindparam('order_ids', value=order_ids))
        rows = db.execute(stmt).fetchall()
        for r in rows:
            att_counts[int(r.order_id)] = int(r.cnt)
    except Exception as e:
        logging.getLogger(__name__).warning("att_counts query failed: %s", e)
    return att_counts


def paginate_production_rows(
    _q: Query, page_raw: int | None, total_orders: int
) -> tuple[int, int, list[Any]]:
    """페이지 인덱스·총 페이지 수·현재 페이지 행."""
    page = page_raw or 1
    if page < 1:
        page = 1
    per_page = PRODUCTION_DASHBOARD_PAGE_SIZE
    total_pages = (total_orders + per_page - 1) // per_page
    page_rows = _q.offset((page - 1) * per_page).limit(per_page).all()
    return page, total_pages, page_rows
