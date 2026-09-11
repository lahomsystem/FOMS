"""EPT-B7: render profiling helper + static asset presence."""
import time
from pathlib import Path

from flask import Response

from foms.services.common.ept_b7_profile import (
    HEADER_RENDER_MS,
    HEADER_ROUTE,
    apply_ept_b7_render_headers,
    format_phases,
    template_mark,
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


def test_template_mark_records_a_span_between_paired_calls() -> None:
    """템플릿 안 쌍 호출이 구간 하나를 만들어 헤더로 나온다."""
    import app as _app_module

    flask_app = _app_module.app
    with flask_app.test_request_context("/"):
        assert template_mark("hist_rows") == ""
        time.sleep(0.01)
        assert template_mark("hist_rows") == ""
        phases = format_phases()
    assert "hist_rows=" in phases
    value = float(phases.split("hist_rows=")[1].split(";")[0])
    assert value >= 9.0


def test_template_mark_alone_records_nothing() -> None:
    """짝이 없는 한 번 호출은 기록하지 않는다(음성 대조군)."""
    import app as _app_module

    with _app_module.app.test_request_context("/"):
        template_mark("lonely")
        assert "lonely" not in format_phases()


def test_template_mark_outside_request_is_silent() -> None:
    """요청 밖에서 불려도 예외 없이 빈 문자열."""
    assert template_mark("no_request") == ""
