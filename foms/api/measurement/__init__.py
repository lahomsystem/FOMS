"""
ERP 실측 API package (canonical: foms.api.measurement).

실측 대시보드 업데이트, 실측 동선 추천. Map helpers live in `foms.api.measurement.map`.

Import order: canonical service bindings first, then routes (routes may import from this package).
"""
from foms.web.auth import login_required
from foms.services.erp_permissions import erp_edit_required
from foms.services.erp_display import get_today_kst, self_measurement_four_checks_done
from foms.services.jobs.queue import enqueue_geocode_order_address

from foms.api.measurement.routes import (
    api_erp_measurement_update,
    erp_measurement_bp,
)
from foms.api.measurement.capture import save_measurement_capture


@erp_measurement_bp.route('/capture/<int:order_id>', methods=['POST'])
@login_required
@erp_edit_required
def api_erp_measurement_capture(order_id):
    """실측 캡처 치수/특이사항 저장 (B2)."""
    return save_measurement_capture(order_id)


__all__ = [
    "api_erp_measurement_capture",
    "api_erp_measurement_update",
    "enqueue_geocode_order_address",
    "erp_edit_required",
    "erp_measurement_bp",
    "get_today_kst",
    "save_measurement_capture",
    "self_measurement_four_checks_done",
]
