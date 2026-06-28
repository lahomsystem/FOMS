"""
ERP 시공 대시보드 페이지 (ERP-SLIM-10)
erp.py에서 분리: /erp/construction/dashboard
"""

import logging

from flask import Blueprint, g, make_response, render_template, request
from sqlalchemy import String, bindparam, cast, or_, text

from foms.web.auth import login_required
from db import get_db
from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
    self_measurement_four_checks_done,
)
from foms.services.erp_order_detail import attach_order_detail_payloads
from foms.services.common.erp_shell_http import apply_erp_shell_fragment_headers, wants_erp_shell_tab_body
from foms.services.erp_permissions import (
    build_mine_sql_filter,
    can_edit_erp,
    is_order_related_to_user,
)
from foms.services.erp_policy import STAGE_LABELS
from foms.services.erp_dashboard_search import erp_order_dashboard_search_predicate
from foms.services.foms_unified_search import _compact
from foms.services.construction_dashboard_filters import parse_construction_dashboard_filters
from foms.services.construction_dashboard_display import (
    enrich_construction_mobile_rows,
    build_construction_row_dtos,
    _display_stage_for_order,
)
from foms.services.feature_flags import is_enabled_for_user
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

_CONSTRUCTION_BROWSE_LIMIT = 300
_CONSTRUCTION_SEARCH_LIMIT = 500


@erp_construction_page_bp.route("/construction/dashboard")
@login_required
def erp_construction_dashboard():
    """시공 대시보드"""
    db = get_db()
    user = getattr(g, "current_user", None)
    is_admin = user and user.role == "ADMIN"

    # Batch 4: 상단 request.args 파싱·is_construction/mine_only는
    # parse_construction_dashboard_filters로 분리(동작 보존). 아래는 다운스트림 호환 바인딩.
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

    # Batch 4: KPI 전체스캔은 전체 structured_data(items/parties/quests 등 대용량)를 행마다
    # 로드/파싱했다(시공 대시보드 KPI 잔여 비용의 핵심). KPI 산출은 flags/schedule/workflow
    # 서브트리만 읽으므로(_erp_alerts·_display_stage_for_order) 해당 3개 경로만 투영해 전송·파싱
    # 비용을 줄인다. 동작은 _ensure_dict(dict/JSON문자열 양쪽 처리)로 byte 동일하게 보존.
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

    if f_stage:
        stage_col = cast(Order.structured_data["workflow"]["stage"], String)
        if f_stage in ("시공대기", "시공중"):
            query = query.filter(stage_col.in_(['"CONSTRUCTION"', '"시공"', '"CONSTRUCTING"']))
        elif f_stage == "시공완료":
            query = query.filter(stage_col.in_(['"COMPLETED"', '"완료"', '"AS_WAIT"', '"CS"']))

    list_query = query
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
        orders = [
            focus
        ] if focus and (
            not mine_only
            or is_order_related_to_user(focus, user)
        ) else []
    elif f_q:
        term = f"%{_compact(f_q)}%"
        if term.strip("%"):
            list_query = list_query.filter(erp_order_dashboard_search_predicate(term))
        list_limit = _CONSTRUCTION_SEARCH_LIMIT
        orders = list_query.order_by(Order.created_at.desc()).limit(list_limit).all()
    else:
        list_limit = _CONSTRUCTION_BROWSE_LIMIT
        orders = list_query.order_by(Order.created_at.desc()).limit(list_limit).all()

    att_counts = {}
    if orders:
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
            att_counts = {}

    # Batch 4: 표시용 row DTO 조립은 build_construction_row_dtos(display 모듈)로 분리(동작 보존, 캐시 아님).
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

    process_steps = [
        {"label": "시공대기", "display": "시공대기", **step_stats["시공대기"]},
        {"label": "시공중", "display": "시공중", **step_stats["시공중"]},
        {"label": "시공완료", "display": "시공완료", **step_stats["시공완료"]},
    ]

    page = request.args.get("page", 1, type=int)
    if page < 1:
        page = 1
    per_page = 50
    total_orders = len(enriched)
    total_pages = (total_orders + per_page - 1) // per_page
    paginated_orders = enriched[(page - 1) * per_page : page * per_page]
    current_user = getattr(g, "current_user", None)
    mobile_v2_active = is_enabled_for_user(
        "ERP_MOBILE_V2_ENABLED",
        current_user.id if current_user else None,
        cohort_key="FOMS_V3_SHELL_COHORT",
    )
    enrich_construction_mobile_rows(
        paginated_orders,
        db,
        mobile_v2_active=mobile_v2_active,
        drawing_only=bool(is_construction),
    )
    attach_order_detail_payloads(db, paginated_orders)

    template_name = (
        "construction/partials/dashboard_fragment.html"
        if wants_erp_shell_tab_body(request)
        else "construction/dashboard.html"
    )
    response = make_response(
        render_template(
            template_name,
            orders=paginated_orders,
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
        )
    )
    apply_erp_shell_fragment_headers(response, request)
    return response
