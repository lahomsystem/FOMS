"""Canonical orders API surface including the route shell."""

from flask import Blueprint

from foms.web.auth import login_required, role_required
from foms.services.erp_display import get_today_kst
from foms.services.erp_permissions import can_edit_erp, erp_edit_required
from foms.services.jobs.queue import enqueue_geocode_order_address
from .calendar import calendar_orders_response
from .call_log import log_call_response
from .copy import copy_orders_response
from .field_update import update_order_field_response
from .nearby import nearby_orders_response
from .qr import render_order_qr_svg
from .regional import update_regional_memo_response, update_regional_status_response
from .stage_override import bulk_stage_override_response, stage_override_response
from .status import bulk_update_order_status_response, update_order_status_response

orders_bp = Blueprint("orders", __name__, url_prefix="/api")


@orders_bp.route("/orders/nearby")
@login_required
def api_orders_nearby():
    """AS 대시보드용 가까운 일정 검색 응답."""
    return nearby_orders_response()


@orders_bp.route("/orders")
@login_required
def api_orders():
    """캘린더/FullCalendar용 주문 이벤트 목록 API."""
    return calendar_orders_response()


@orders_bp.route("/update_regional_status", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def update_regional_status():
    """지방 주문 및 자가실측 체크리스트 상태 업데이트."""
    return update_regional_status_response()


@orders_bp.route("/update_regional_memo", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def update_regional_memo():
    """지방 주문 메모 업데이트."""
    return update_regional_memo_response()


@orders_bp.route("/update_order_field", methods=["POST"])
@login_required
def update_order_field():
    """주문 필드 업데이트 (수도권 및 지방 대시보드용)."""
    from foms.services.erp_display import clean_dict_like_name

    return update_order_field_response(clean_dict_like_name=clean_dict_like_name)


@orders_bp.route("/update_order_status", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def update_order_status():
    """수도권 대시보드에서 주문 상태 직접 변경."""
    return update_order_status_response(get_today_kst_func=get_today_kst)


@orders_bp.route("/bulk_update_order_status", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def bulk_update_order_status():
    """다중 선택 주문 상태 변경."""
    return bulk_update_order_status_response(get_today_kst_func=get_today_kst)


@orders_bp.route("/orders/workflow/stage-override/bulk", methods=["POST"])
@login_required
def api_bulk_stage_override():
    """선택 주문 일괄 단계 역행·건너뛰기 (사유·confirm 필수). ADMIN/MANAGER만 성공."""
    return bulk_stage_override_response()


@orders_bp.route("/orders/<int:order_id>/workflow/stage-override", methods=["POST"])
@login_required
def api_order_stage_override(order_id: int):
    """의도적 단계 역행·건너뛰기 (사유·confirm 필수). ADMIN/MANAGER만 성공."""
    return stage_override_response(order_id)


@orders_bp.route("/orders/copy", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def copy_orders():
    """선택 주문을 새 주문번호로 복사."""
    return copy_orders_response()


@orders_bp.route("/orders/<int:order_id>/call-log", methods=["POST"])
@login_required
def api_order_call_log(order_id):
    """주문 통화 결과 기록 (B1). 권한은 command ``CALL_LOGGED`` 정책(ERP_EDIT)이 handler 에서 enforce."""
    return log_call_response(order_id)


@orders_bp.route("/orders/<int:order_id>/qr.svg")
@login_required
def api_order_qr_svg(order_id):
    """주문 모바일 상세 URL QR 코드 SVG (B4)."""
    return render_order_qr_svg(order_id)


__all__ = [
    "api_bulk_stage_override",
    "api_order_call_log",
    "api_orders",
    "api_orders_nearby",
    "bulk_stage_override_response",
    "bulk_update_order_status_response",
    "bulk_update_order_status",
    "calendar_orders_response",
    "can_edit_erp",
    "copy_orders",
    "copy_orders_response",
    "enqueue_geocode_order_address",
    "erp_edit_required",
    "log_call_response",
    "get_today_kst",
    "nearby_orders_response",
    "api_order_qr_svg",
    "api_order_stage_override",
    "render_order_qr_svg",
    "orders_bp",
    "stage_override_response",
    "update_order_field",
    "update_order_field_response",
    "update_order_status",
    "update_order_status_response",
    "update_regional_memo",
    "update_regional_memo_response",
    "update_regional_status",
    "update_regional_status_response",
]
