"""
ERP 생산 대시보드 페이지 (ERP-SLIM-9) — canonical page owner.

erp.py에서 분리: /erp/production/dashboard
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, make_response, render_template, request, g
from sqlalchemy import String, cast

from db import get_db
from models import Order
from foms.web.auth import login_required

from foms.services.production_dashboard_filters import parse_production_dashboard_filters
from foms.services.production_read_model import (
    build_production_orders_query,
    production_stage_bucket_expr,
    empty_production_step_stats,
    fill_production_step_counts,
    compute_production_kpis_and_badges,
    fetch_production_attachment_counts,
    paginate_production_rows,
    PRODUCTION_DASHBOARD_PAGE_SIZE,
)
from foms.services.erp_permissions import (
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.erp_mobile_order_display import resolve_manager_phone_for_queue
from foms.services.erp_policy import STAGE_LABELS
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
)
from foms.services.erp_order_detail import attach_order_detail_payloads
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body


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
        'manager_phone': resolve_manager_phone_for_queue(sd.get('parties') or {}, order=o),
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

    _pf = parse_production_dashboard_filters(request)
    f_stage = _pf.stage
    f_q = _pf.q
    erp_mine_only = _pf.erp_mine_only

    stage_col = cast(Order.structured_data['workflow']['stage'], String)
    _q = build_production_orders_query(db, user, f_stage, f_q, erp_mine_only, stage_col)
    _q = _q.order_by(Order.created_at.desc())

    stage_bucket_expr = production_stage_bucket_expr(stage_col)
    step_stats = empty_production_step_stats()
    fill_production_step_counts(_q, stage_bucket_expr, step_stats)

    kpi_rows, kpis = compute_production_kpis_and_badges(_q, step_stats)
    total_orders = len(kpi_rows)
    _q = _q.order_by(Order.created_at.desc())

    page, total_pages, page_rows = paginate_production_rows(
        _q, _pf.page, total_orders
    )

    # 검색 카드 딥링크(?focus_order=)는 단계 버킷·페이지네이션과 무관하게 착지해야 한다.
    # orders/construction/measurement 대시보드와 동일한 deep-link SSOT.
    focus_order_id = _pf.focus_order_id
    if focus_order_id and focus_order_id not in {o.id for o in page_rows}:
        focus_order = (
            db.query(Order)
            .filter(Order.id == focus_order_id, Order.active_filter(), Order.is_erp_order.is_(True))
            .first()
        )
        if focus_order is not None and (
            not erp_mine_only
            or is_order_related_to_user(focus_order, user)
        ):
            page_rows = [focus_order] + page_rows

    att_counts = fetch_production_attachment_counts(db, page_rows)
    enriched = _build_production_enriched_rows(page_rows, att_counts)
    # 모바일 v2 큐 카드 썸네일: 페이지 주문 첨부 미리보기 URL 일괄 해소
    from foms.services.erp_mobile_order_display import batch_resolve_queue_attachment_preview_items
    _queue_preview_items = batch_resolve_queue_attachment_preview_items(
        db, [r["id"] for r in enriched]
    )
    for _r in enriched:
        items = _queue_preview_items.get(_r["id"], [])
        _r["attachment_preview_items"] = items
        _r["attachment_previews"] = [item["view"] for item in items if item.get("view")]
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
            per_page=PRODUCTION_DASHBOARD_PAGE_SIZE,
            total_pages=total_pages,
            total_orders=total_orders,
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
