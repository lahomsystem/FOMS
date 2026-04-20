"""EPT-B7: render profiling helper + static asset presence."""
from pathlib import Path

from flask import Response

from foms.services.common.ept_b7_profile import (
    HEADER_RENDER_MS,
    HEADER_ROUTE,
    apply_ept_b7_render_headers,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_apply_ept_b7_render_headers_sets_diagnostic_headers() -> None:
    """Headers document Jinja render time only; not used for authorization."""
    resp = Response()
    apply_ept_b7_render_headers(resp, route_id="erp_test", render_ms=12.3456)
    assert resp.headers[HEADER_ROUTE] == "erp_test"
    assert resp.headers[HEADER_RENDER_MS] == "12.3"


def test_ept_b7_page_scoped_assets_exist() -> None:
    """HTML diet moved inline blocks to these paths (full + fragment parity)."""
    assert (_REPO_ROOT / "static/css/contexts/orders/dashboard-gateway-notifications.css").is_file()
    assert (_REPO_ROOT / "static/js/orders/dashboard-notifications.js").is_file()
    assert (_REPO_ROOT / "static/css/contexts/cs/as-dashboard-body.css").is_file()
    assert (_REPO_ROOT / "static/css/contexts/shipment/dashboard-table-extras.css").is_file()
