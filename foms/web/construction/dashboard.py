"""
ERP 시공 대시보드 페이지 (ERP-SLIM-10)
erp.py에서 분리: /erp/construction/dashboard
"""

import logging

from flask import Blueprint, g, render_template, request
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
from foms.services.erp_permissions import build_mine_sql_filter, can_edit_erp
from foms.services.erp_policy import STAGE_LABELS
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

    f_stage = (request.args.get("stage") or "").strip()
    f_q = (request.args.get("q") or "").strip()
    is_construction = user and getattr(user, "team", None) == "CONSTRUCTION"
    mine_only = is_construction or (request.args.get("mine") == "1")

    query = db.query(Order).filter(Order.dashboard_active_filter(days=60), Order.is_erp_beta.is_(True))

    if mine_only and user:
        mine_conds = build_mine_sql_filter(user)
        if mine_conds:
            query = query.filter(or_(*mine_conds))

    kpi_rows = query.order_by(None).with_entities(Order.id, Order.structured_data, Order.is_self_measurement).all()
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

    def _display_stage_for_order(order, structured_data):
        stage = _erp_get_stage(order, structured_data)
        history = (structured_data.get("workflow") or {}).get("history") or []
        is_started = any(str(entry.get("note")).strip() == "시공 시작" for entry in history)
        if stage in ("CONSTRUCTION", "시공"):
            return "시공중" if is_started else "시공대기"
        if stage in ("COMPLETED", "완료", "AS_WAIT") or stage == "CS":
            return "시공완료"
        if stage == "CONSTRUCTING":
            return "시공중"
        return None

    for row in kpi_rows:
        if row.is_self_measurement and not self_measurement_four_checks_done(row):
            continue
        structured_data = _ensure_dict(row.structured_data)
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

    orders = query.order_by(Order.created_at.desc()).limit(300).all()

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

    enriched = []
    for order in orders:
        if getattr(order, "is_self_measurement", False) and not self_measurement_four_checks_done(order):
            continue
        structured_data = _ensure_dict(order.structured_data)
        display_stage = _display_stage_for_order(order, structured_data)
        if not display_stage:
            continue
        if f_stage and display_stage != f_stage:
            continue
        if f_q:
            haystack = " ".join(
                [
                    str((((structured_data.get("parties") or {}).get("customer") or {}).get("name")) or ""),
                    str((((structured_data.get("parties") or {}).get("customer") or {}).get("phone")) or ""),
                    str(
                        (((structured_data.get("site") or {}).get("address_full"))
                        or ((structured_data.get("site") or {}).get("address_main")))
                        or ""
                    ),
                ]
            ).lower()
            if f_q.lower() not in haystack:
                continue

        alerts = _erp_alerts(order, structured_data, att_counts.get(order.id, 0))
        enriched.append(
            {
                "id": order.id,
                "is_erp_beta": order.is_erp_beta,
                "is_self_measurement": getattr(order, "is_self_measurement", False),
                "structured_data": structured_data,
                "customer_name": (((structured_data.get("parties") or {}).get("customer") or {}).get("name")) or "-",
                "address": (
                    ((structured_data.get("site") or {}).get("address_full"))
                    or ((structured_data.get("site") or {}).get("address_main"))
                )
                or "-",
                "stage": display_stage,
                "alerts": alerts,
                "has_media": _erp_has_media(order, att_counts.get(order.id, 0)),
                "attachments_count": att_counts.get(order.id, 0),
                "orderer_name": (((structured_data.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
                or None,
                "owner_team": "CONSTRUCTION",
                "measurement_date": (((structured_data.get("schedule") or {}).get("measurement") or {}).get("date")),
                "construction_date": (((structured_data.get("schedule") or {}).get("construction") or {}).get("date")),
                "manager_name": (((structured_data.get("parties") or {}).get("manager") or {}).get("name")) or "-",
                "phone": (((structured_data.get("parties") or {}).get("customer") or {}).get("phone")) or "-",
                "as_received_date": getattr(order, "as_received_date", None) or "",
                "as_received_done": bool((getattr(order, "as_received_date", None) or "").strip()),
            }
        )

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
    attach_order_detail_payloads(db, paginated_orders)

    return render_template(
        "construction/dashboard.html",
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
        total_pages=total_pages,
        total_orders=total_orders,
    )
