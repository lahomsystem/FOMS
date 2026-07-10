"""
ERP 시공 대시보드 페이지 (ERP-SLIM-10)
erp.py에서 분리: /erp/construction/dashboard
"""

import time

from flask import Blueprint, g, make_response, render_template, request
from sqlalchemy import or_

from foms.web.auth import login_required
from db import get_db
from foms.services.erp_order_detail import attach_order_detail_payloads
from foms.services.common.dashboard_cache import (
    KEY_VERSION,
    TTL_ATTACHMENT_COUNT_MAP,
    TTL_SUMMARY_COUNTS,
    build_dashboard_cache_key,
    get_or_compute_dashboard_slice,
)
from foms.services.common.ept_b7_profile import apply_ept_b7_render_headers
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.erp_permissions import (
    build_mine_sql_filter,
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
    self_measurement_four_checks_done,
)
from foms.services.construction_dashboard_filters import parse_construction_dashboard_filters
from foms.services.construction_dashboard_display import (
    enrich_construction_mobile_rows,
    build_construction_row_dtos,
)
from foms.services.construction_read_model import (
    CONSTRUCTION_BROWSE_CAP,
    CONSTRUCTION_DASHBOARD_PAGE_SIZE,
    CONSTRUCTION_SEARCH_CAP,
    apply_construction_search_filter,
    apply_construction_stage_sql_filter,
    build_construction_process_steps,
    compute_construction_summary_blob,
    fetch_construction_attachment_counts,
    paginate_construction_orders,
)
from foms.services.feature_flags import is_mobile_v2_shell, resolve_shell_variant_cached
from foms.services.datetime_kst import get_today_kst
from models import Order

erp_construction_page_bp = Blueprint("erp_construction_page", __name__, url_prefix="/erp")

TEAM_LABELS = {
    "CS": "라홈팀",
    "SALES": "영업팀",
    "MEASURE": "실측팀",
    "DRAWING": "도면팀",
    "PRODUCTION": "생산팀",
    "CONSTRUCTION": "시공팀",
}


@erp_construction_page_bp.route("/construction/dashboard")
@login_required
def erp_construction_dashboard():
    """시공 대시보드"""
    db = get_db()
    user = getattr(g, "current_user", None)
    is_admin = user and user.role == "ADMIN"

    _cf = parse_construction_dashboard_filters(request, user)
    f_stage = _cf.stage
    f_q = _cf.q
    focus_order_id = _cf.focus_order_id
    is_construction = _cf.is_construction
    mine_only = _cf.mine_only

    query = db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_order.is_(True))

    if mine_only and user:
        mine_conds = build_mine_sql_filter(user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))
        else:
            query = query.filter(Order.id == -1)

    _summary_fp = {
        "v": KEY_VERSION,
        "uid": user.id if user else None,
        "role": getattr(user, "role", None) if user else None,
        "mine": bool(mine_only),
    }
    _summary_key = build_dashboard_cache_key("construction", "summary_counts", _summary_fp)
    _summary_blob = get_or_compute_dashboard_slice(
        _summary_key,
        TTL_SUMMARY_COUNTS,
        lambda: compute_construction_summary_blob(query),
        page="construction",
        slice_name="summary_counts",
    )
    step_stats = _summary_blob["step_stats"]
    kpis = _summary_blob["kpis"]

    list_query = apply_construction_stage_sql_filter(query, f_stage)

    page = request.args.get("page", 1, type=int)
    per_page = CONSTRUCTION_DASHBOARD_PAGE_SIZE
    total_pages = 0
    total_orders = 0
    orders: list[Order] = []

    if focus_order_id:
        focus = (
            db.query(Order)
            .filter(
                Order.id == focus_order_id,
                Order.active_filter(),
                Order.is_erp_order.is_(True),
            )
            .first()
        )
        orders = (
            [focus]
            if focus
            and (not mine_only or is_order_related_to_user(focus, user))
            else []
        )
        total_orders = len(orders)
        total_pages = 1
        page = 1
    elif f_q:
        list_query = apply_construction_search_filter(list_query, f_q)
        page, total_pages, total_orders, orders = paginate_construction_orders(
            list_query,
            page=page,
            per_page=per_page,
            total_cap=CONSTRUCTION_SEARCH_CAP,
        )
    else:
        page, total_pages, total_orders, orders = paginate_construction_orders(
            list_query,
            page=page,
            per_page=per_page,
            total_cap=CONSTRUCTION_BROWSE_CAP,
        )

    _att_fp = {
        "v": KEY_VERSION,
        "uid": user.id if user else None,
        "mine": bool(mine_only),
        "stage": f_stage or "",
        "q": f_q or "",
        "page": page,
        "ids": sorted(o.id for o in orders),
    }
    _att_key = build_dashboard_cache_key("construction", "attachment_counts", _att_fp)

    def _compute_att_counts() -> dict[str, int]:
        raw = fetch_construction_attachment_counts(db, orders)
        return {str(k): int(v) for k, v in raw.items()}

    _att_blob = get_or_compute_dashboard_slice(
        _att_key,
        TTL_ATTACHMENT_COUNT_MAP,
        _compute_att_counts,
        page="construction",
        slice_name="attachment_counts",
    )
    att_counts = {int(k): int(v) for k, v in (_att_blob or {}).items()}

    enriched = build_construction_row_dtos(orders, att_counts, f_stage)

    if f_q or focus_order_id:
        step_stats = {
            "시공대기": {"count": 0, "overdue": 0, "imminent": 0},
            "시공중": {"count": 0, "overdue": 0, "imminent": 0},
            "시공완료": {"count": 0, "overdue": 0, "imminent": 0},
        }
        for item in enriched:
            stage_name = item.get("stage")
            if stage_name in step_stats:
                step_stats[stage_name]["count"] += 1
                alerts = item.get("alerts") or {}
                if alerts.get("construction_d3"):
                    step_stats[stage_name]["imminent"] += 1

    process_steps = build_construction_process_steps(step_stats)

    current_user = getattr(g, "current_user", None)
    mobile_v2_active = is_mobile_v2_shell(
        resolve_shell_variant_cached(current_user.id if current_user else None)
    )
    enrich_construction_mobile_rows(
        enriched,
        db,
        mobile_v2_active=mobile_v2_active,
        drawing_only=bool(is_construction),
    )
    attach_order_detail_payloads(db, enriched)

    template_name = (
        "construction/partials/dashboard_fragment.html"
        if wants_erp_shell_tab_body(request)
        else "construction/dashboard.html"
    )
    _t0 = time.perf_counter()
    response = make_response(
        render_template(
            template_name,
            orders=enriched,
            kpis=kpis,
            process_steps=process_steps,
            filters={"stage": f_stage, "q": f_q},
            team_labels=TEAM_LABELS,
            stage_labels=STAGE_LABELS,
            is_admin=is_admin,
            can_edit_erp=can_edit_erp(user),
            erp_mine_only=mine_only,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            total_orders=total_orders,
            today_iso=get_today_kst().isoformat(),
        )
    )
    apply_ept_b7_render_headers(
        response,
        route_id="erp_construction_dashboard",
        render_ms=(time.perf_counter() - _t0) * 1000,
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
