"""PARTNER-02: 협력사 화면(HTML) — 주문 목록 · 새 주문 등록 · 주문 상세.

공용 레이아웃(내부 메뉴 · 배지 · 알림 스크립트)을 쓰지 않는 단독 화면이다(``partner/layout.html``).
금액 · 원가 · 내부 메모 · 다른 협력사 주문은 보여 주지 않는다.
스펙: docs/specs/2026-10-08-partner-portal_SPEC.md §5.1
"""
from __future__ import annotations

from flask import Blueprint, abort, g, render_template

from db import get_db
from foms.api.files.routes import build_file_view_url
from foms.api.partner import UPLOAD_OPEN_STAGES
from foms.services.auth.partner_scope import partner_can_read_order, partner_required
from foms.services.order_attachment_permissions import is_partner_original_key
from foms.services.orders.as_cycle_service import AS_IN_PROGRESS, AS_RECEIVED, current_cycle, cycle_status
from foms.services.orders.confirm_drawing_gate import confirm_exit_block
from foms.services.partners.as_intake import AS_OPEN_STAGES
from foms.services.partners.drawing_confirm import final_drawings_for_partner
from foms.services.partners.orders import list_partner_orders, partner_order_detail
from models import Order, OrderAttachment, PartnerOrg

partner_portal_bp = Blueprint("partner_portal", __name__, url_prefix="/partner")


def _org() -> PartnerOrg:
    return get_db().query(PartnerOrg).filter(PartnerOrg.id == g.current_user.partner_org_id).first()


@partner_portal_bp.route("")
@partner_required
def home():
    org = _org()
    return render_template(
        "partner/home.html",
        org=org,
        orders=list_partner_orders(get_db(), org.id),
    )


@partner_portal_bp.route("/orders/new")
@partner_required
def new_order():
    return render_template("partner/new_order.html", org=_org())


@partner_portal_bp.route("/orders/<int:order_id>")
@partner_required
def order_detail(order_id: int):
    db = get_db()
    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not partner_can_read_order(g.current_user, order):
        abort(404)
    rows = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order.id)
        .order_by(OrderAttachment.id)
        .all()
    )
    # 협력사가 낸 파일만 보여 준다(우리 작업 파일은 3단계 "도면 확인"에서 연다).
    attachments = [
        {
            "filename": a.filename,
            "kind": "초안 도면" if "/partner_draft/" in (a.storage_key or "") else "실측 사진",
            "url": build_file_view_url(a.storage_key),
        }
        for a in rows
        if is_partner_original_key(a.storage_key)
    ]
    stage = (order.erp_stage_code or "").upper()
    cycle = current_cycle(order.structured_data or {})
    as_open = cycle is not None and cycle_status(cycle) in (AS_RECEIVED, AS_IN_PROGRESS)
    finals = [
        {"filename": f.get("filename") or f.get("key", "").rsplit("/", 1)[-1], "url": build_file_view_url(f["key"])}
        for f in final_drawings_for_partner(order)
    ]
    return render_template(
        "partner/order_detail.html",
        org=_org(),
        order=partner_order_detail(order, attachments),
        can_upload=stage in UPLOAD_OPEN_STAGES,
        final_drawings=finals,
        # 도면 확인 차례(CONFIRM)이고 도면이 확정됐을 때만 버튼을 연다(서버가 다시 판정한다).
        can_approve=stage == "CONFIRM" and bool(finals) and confirm_exit_block(order.structured_data or {}) is None,
        can_revise=stage in ("DRAWING", "CONFIRM") and bool(finals)
        and (order.structured_data or {}).get("drawing_status") in ("TRANSFERRED", "CONFIRMED"),
        can_as=stage in AS_OPEN_STAGES and not as_open,
        as_open=as_open,
    )
