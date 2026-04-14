"""Orders API: Flask blueprint shell in `apps`; responses delegate to `foms.api.orders` (Wave 2 thin-adapter contract)."""

from flask import Blueprint

from apps.auth import login_required, role_required
from foms.api.orders import (
    bulk_update_order_status_response,
    calendar_orders_response,
    nearby_orders_response,
    update_order_field_response,
    update_order_status_response,
    update_regional_memo_response,
    update_regional_status_response,
)
from foms.services.erp_display import get_today_kst
from foms.services.erp_permissions import can_edit_erp
from foms.services.jobs.queue import enqueue_geocode_order_address

orders_bp = Blueprint("orders", __name__, url_prefix="/api")

__all__ = [
    "orders_bp",
    "can_edit_erp",
    "enqueue_geocode_order_address",
    "get_today_kst",
]


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
