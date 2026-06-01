"""
ERP 생산 대시보드 페이지 (ERP-SLIM-9) — canonical page owner.

erp.py에서 분리: /erp/production/dashboard
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Blueprint, make_response, render_template, request, g
from sqlalchemy import bindparam, case as sql_case, cast, func, or_, String, text
from sqlalchemy.orm import Query

from db import get_db
from models import Order
from foms.web.auth import login_required

from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_policy import STAGE_LABELS
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
)
from foms.services.erp_order_detail import attach_order_detail_payloads
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.request_utils import get_search_query_arg


erp_production_page_bp = Blueprint(
    'erp_production_page', __name__, url_prefix='/erp'
)


TEAM_LABELS = {
    'CS': '라홈팀',
    'SALES': '영업팀',
    'MEASURE': '실측팀',
    'DRAWING': '도면팀',
    'PRODUCTION': '생산팀',
    'CONSTRUCTION': '시공팀',
}


def _build_production_orders_query(
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
                cast(Order.structured_data, String).ilike(search_term),
            )
        )

    if erp_mine_only and user:
        u_name = (user.name or '').strip()
        u_username = (user.username or '').strip()
        conds = []
        if u_name:
            conds.append(Order.manager_name.ilike(f"%{u_name}%"))
            conds.append(cast(Order.structured_data, String).ilike(f'%"{u_name}"%'))
        if u_username:
            conds.append(Order.manager_name.ilike(f"%{u_username}%"))
            conds.append(cast(Order.structured_data, String).ilike(f'%"{u_username}"%'))
        if conds:
            _q = _q.filter(or_(*conds))

    return _q


def _sql_stage_bucket_expr(stage_col: Any) -> Any:
    """DB 단계 JSON → 제작대기/제작중/제작완료 버킷."""
    return sql_case(
        (stage_col.in_(['"고객컨펌"', '"CONFIRM"']), '제작대기'),
        (stage_col.in_(['"생산"', '"PRODUCTION"']), '제작중'),
        (stage_col.in_(['"시공"', '"CONSTRUCTION"']), '제작완료'),
        else_='기타',
    )


def _empty_step_stats() -> dict[str, dict[str, int]]:
    return {
        '제작대기': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작중': {'count': 0, 'overdue': 0, 'imminent': 0},
        '제작완료': {'count': 0, 'overdue': 0, 'imminent': 0},
    }


def _fill_sql_stage_counts(
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


def _compute_kpis_and_pipeline_badges(
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


def _fetch_attachment_counts(db: Any, page_rows: list[Any]) -> dict[int, int]:
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


def _production_stage_label_from_stage(stage: str) -> str | None:
    if stage not in ['고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION']:
        return None
    label = stage
    if stage in ('CONFIRM', '고객컨펌'):
        label = '제작대기'
    if stage in ('PRODUCTION', '생산'):
        label = '제작중'
    if stage in ('CONSTRUCTION', '시공'):
        label = '제작완료'
    return label


def _production_quest_sales_state(
    sd: dict[str, Any], stage_label: str
) -> tuple[bool | None, Any]:
    """제작대기일 때 퀘스트·영업 승인 상태."""
    if stage_label != '제작대기':
        return True, None
    is_sales_approved = False
    quests = sd.get('quests') or []
    active_quest = next((q for q in quests if q.get('stage') in ('CONFIRM', '고객컨펌')), None)
    if not active_quest:
        return is_sales_approved, active_quest
    assignee_approval = active_quest.get('assignee_approval') or {}
    if isinstance(assignee_approval, dict):
        is_sales_approved = assignee_approval.get('approved') is True
    else:
        is_sales_approved = bool(assignee_approval)
    if not is_sales_approved:
        team_approvals = active_quest.get('team_approvals') or {}
        sales_val = team_approvals.get('SALES') or team_approvals.get('영업팀')
        if isinstance(sales_val, dict):
            is_sales_approved = sales_val.get('approved') is True
        else:
            is_sales_approved = bool(sales_val)
    return is_sales_approved, active_quest


def _enrich_one_production_order(
    o: Any, sd: dict[str, Any], stage_label: str, att_n: int
) -> dict[str, Any]:
    """단일 Order → 목록 행 dict."""
    is_sales_approved, active_quest = _production_quest_sales_state(sd, stage_label)
    alerts = _erp_alerts(o, sd, att_n)
    return {
        'id': o.id,
        'is_erp_order': o.is_erp_order,
        'is_self_measurement': getattr(o, 'is_self_measurement', False),
        'structured_data': sd,
        'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
        'address': (((sd.get('site') or {}).get('address_full')) or ((sd.get('site') or {}).get('address_main'))) or '-',
        'stage': stage_label,
        'alerts': alerts,
        'has_media': _erp_has_media(o, att_n),
        'attachments_count': att_n,
        'orderer_name': (((sd.get('parties') or {}).get('orderer') or {}).get('name') or '').strip() or None,
        'current_quest': active_quest if stage_label == '제작대기' else None,
        'is_sales_approved': is_sales_approved if stage_label == '제작대기' else True,
        'owner_team': 'PRODUCTION',
        'measurement_date': (((sd.get('schedule') or {}).get('measurement') or {}).get('date')),
        'construction_date': (((sd.get('schedule') or {}).get('construction') or {}).get('date')),
        'manager_name': (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-',
        'phone': (((sd.get('parties') or {}).get('customer') or {}).get('phone')) or '-',
    }


def _build_production_enriched_rows(
    page_rows: list[Any], att_counts: dict[int, int]
) -> list[dict[str, Any]]:
    """현재 페이지 주문만 목록용 dict로 변환."""
    enriched: list[dict[str, Any]] = []
    for o in page_rows:
        sd = _ensure_dict(o.structured_data)
        raw_stage = _erp_get_stage(o, sd)
        if not raw_stage:
            continue
        stage_label = _production_stage_label_from_stage(raw_stage)
        if not stage_label:
            continue
        att_n = att_counts.get(o.id, 0)
        enriched.append(_enrich_one_production_order(o, sd, stage_label, att_n))
    return enriched


PRODUCTION_DASHBOARD_PAGE_SIZE = 50


def _paginate_production_rows(
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


def _production_process_steps_bar(
    step_stats: dict[str, dict[str, int]]
) -> list[dict[str, Any]]:
    """프로세스 맵 카드용 상단 2단계(제작대기·제작중)."""
    return [
        {'label': '제작대기', 'display': '제작대기', **step_stats['제작대기']},
        {'label': '제작중', 'display': '제작중', **step_stats['제작중']},
    ]


@erp_production_page_bp.route('/production/dashboard')
@login_required
def erp_production_dashboard():
    """생산 대시보드"""
    db = get_db()
    user = getattr(g, 'current_user', None)
    is_admin = user and user.role == 'ADMIN'

    f_stage = (request.args.get('stage') or '').strip()
    f_q = get_search_query_arg('q', 'search')
    erp_mine_only = request.args.get('mine') == '1'

    stage_col = cast(Order.structured_data['workflow']['stage'], String)
    _q = _build_production_orders_query(db, user, f_stage, f_q, erp_mine_only, stage_col)
    _q = _q.order_by(Order.created_at.desc())

    stage_bucket_expr = _sql_stage_bucket_expr(stage_col)
    step_stats = _empty_step_stats()
    _fill_sql_stage_counts(_q, stage_bucket_expr, step_stats)

    kpi_rows, kpis = _compute_kpis_and_pipeline_badges(_q, step_stats)
    total_orders = len(kpi_rows)
    _q = _q.order_by(Order.created_at.desc())

    page, total_pages, page_rows = _paginate_production_rows(
        _q, request.args.get('page', 1, type=int), total_orders
    )

    att_counts = _fetch_attachment_counts(db, page_rows)
    enriched = _build_production_enriched_rows(page_rows, att_counts)
    # 모바일 v2 큐 카드 썸네일: 페이지 주문 첨부 미리보기 URL 일괄 해소
    from foms.services.erp_mobile_order_display import batch_resolve_queue_attachment_urls
    _queue_previews = batch_resolve_queue_attachment_urls(db, [r['id'] for r in enriched])
    for _r in enriched:
        _r['attachment_previews'] = _queue_previews.get(_r['id'], [])
    process_steps = _production_process_steps_bar(step_stats)
    attach_order_detail_payloads(db, enriched)

    template_name = (
        'production/partials/dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'production/dashboard.html'
    )
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            kpis=kpis,
            process_steps=process_steps,
            filters={'stage': f_stage, 'q': f_q},
            team_labels=TEAM_LABELS,
            stage_labels=STAGE_LABELS,
            is_admin=is_admin,
            can_edit_erp=can_edit_erp(user),
            erp_mine_only=erp_mine_only,
            page=page,
            total_pages=total_pages,
            total_orders=total_orders,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
