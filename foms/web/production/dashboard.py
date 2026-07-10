"""
ERP 생산 대시보드 페이지 (ERP-SLIM-9) — canonical page owner.

erp.py에서 분리: /erp/production/dashboard
"""
from __future__ import annotations

import time

from flask import Blueprint, make_response, render_template, request, g

from db import get_db
from models import Order
from foms.web.auth import login_required

from foms.services.production_dashboard_filters import parse_production_dashboard_filters
from foms.services.production_read_model import (
    build_production_orders_query,
    production_stage_bucket_expr,
    compute_production_summary_blob,
    fetch_production_attachment_counts,
    paginate_production_rows,
    PRODUCTION_DASHBOARD_PAGE_SIZE,
)
from foms.services.production_dashboard_display import (
    build_production_enriched_rows,
    build_production_process_steps,
)
from foms.services.common.dashboard_cache import (
    KEY_VERSION,
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.production_dashboard_display import (
    build_production_enriched_rows,
    build_production_process_steps,
)
from foms.services.erp_permissions import (
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.erp_policy import STAGE_LABELS
# namespace surface 계약(pin): 라우트 본문 미사용이어도 erp_display 재export 유지
from foms.services.erp_display import (
    _ensure_dict,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
)
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

    # 단계 필터/버킷은 build_production_orders_query·production_stage_bucket_expr가
    # flat 컬럼 Order.erp_stage_code(index=True)를 직접 참조한다(JSONB path cast 제거).
    _q = build_production_orders_query(db, user, f_stage, f_q, erp_mine_only)

    _summary_fp = {
        "v": KEY_VERSION,
        "uid": user.id if user else None,
        "role": getattr(user, "role", None) if user else None,
        "mine": bool(erp_mine_only),
        "stage": f_stage or "",
        "q": f_q or "",
    }
    _summary_key = build_dashboard_cache_key("production", "summary_counts", _summary_fp)
    _summary_blob = get_or_compute_dashboard_slice(
        _summary_key,
        TTL_SUMMARY_COUNTS,
        lambda: compute_production_summary_blob(_q),
        page="production",
        slice_name="summary_counts",
    )
    step_stats = _summary_blob["step_stats"]
    kpis = _summary_blob["kpis"]
    total_orders = int(_summary_blob["total_orders"])
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

    _att_fp = {
        "v": KEY_VERSION,
        "uid": user.id if user else None,
        "mine": bool(erp_mine_only),
        "stage": f_stage or "",
        "q": f_q or "",
        "page": page,
        "ids": sorted(o.id for o in page_rows),
    }
    _att_key = build_dashboard_cache_key("production", "attachment_counts", _att_fp)

    def _compute_att() -> dict[str, int]:
        raw = fetch_production_attachment_counts(db, page_rows)
        return {str(k): int(v) for k, v in raw.items()}

    _att_blob = get_or_compute_dashboard_slice(
        _att_key,
        TTL_ATTACHMENT_COUNT_MAP,
        _compute_att,
        page="production",
        slice_name="attachment_counts",
    )
    att_counts = {int(k): int(v) for k, v in (_att_blob or {}).items()}
    enriched = build_production_enriched_rows(page_rows, att_counts)
    # 모바일 v2 큐 카드 썸네일: 페이지 주문 첨부 미리보기 URL 일괄 해소
    from foms.services.erp_mobile_order_display import batch_resolve_queue_attachment_preview_items
    _queue_preview_items = batch_resolve_queue_attachment_preview_items(
        db, [r["id"] for r in enriched]
    )
    for _r in enriched:
        items = _queue_preview_items.get(_r["id"], [])
        _r["attachment_preview_items"] = items
        _r["attachment_previews"] = [item["view"] for item in items if item.get("view")]
    process_steps = build_production_process_steps(step_stats)
    # detail_payload eager 조립 제거: 템플릿 preload가 lazy fetch(/api/orders/<id>/
    # detail-payload)로 전환되어 이 서버측 계산은 미사용이었다(매 요청 N행 낭비).

    template_name = (
        'production/partials/dashboard_fragment.html'
        if wants_erp_shell_tab_body(request)
        else 'production/dashboard.html'
    )
    _t0 = time.perf_counter()
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            kpis=kpis,
            process_steps=process_steps,
            step_stats=step_stats,
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
    apply_ept_b7_render_headers(
        response,
        route_id="erp_production_dashboard",
        render_ms=(time.perf_counter() - _t0) * 1000,
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
