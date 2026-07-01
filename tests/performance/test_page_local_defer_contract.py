"""Page-local script loading contracts for perf-audit reductions."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(.*?)\1[^>]*>", re.I | re.S)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _script_tag_containing(html: str, needle: str) -> str:
    for match in SCRIPT_TAG_RE.finditer(html):
        tag = match.group(0)
        if needle in tag:
            return tag
    raise AssertionError(f"script tag not found: {needle}")


def _assert_deferred(html: str, needle: str) -> None:
    tag = _script_tag_containing(html, needle)
    assert re.search(r"\bdefer\b", tag), tag


def test_chat_page_route_script_is_deferred() -> None:
    html = _read("templates/channel/chat.html")

    _assert_deferred(html, "channel_chat_pages.chat_scripts_js")


def test_measurement_dashboard_external_scripts_are_deferred() -> None:
    html = _read("templates/measurement/partials/dashboard_scripts.html")
    scripts = [
        "js/runtime/common_utils.js",
        "js/measurement/dashboard.js",
        "js/measurement/mobile.js",
        "js/runtime/column-resizer.js",
        "js/measurement/dashboard-columns.js",
        "js/measurement/manual-rows.js",
        "js/measurement/image-export.js",
    ]

    for needle in scripts:
        _assert_deferred(html, needle)

    assert "html2canvas" not in html
    export_js = _read("static/js/measurement/image-export.js")
    assert "ensureHtml2canvas" in export_js


def test_order_detail_fragment_scripts_are_deferred_but_keep_include_order() -> None:
    orders = _read("templates/orders/partials/dashboard_scripts.html")
    production = _read("templates/production/partials/dashboard_body.html")
    construction = _read("templates/construction/partials/dashboard_body.html")

    _assert_deferred(orders, "js/orders/order-detail-fragment.js")
    assert orders.index("js/orders/order-detail-fragment.js") < orders.index(
        "dashboard_scripts_detail_dom.html"
    )
    _assert_deferred(production, "js/orders/order-detail-fragment.js")
    _assert_deferred(construction, "js/orders/order-detail-fragment.js")


def test_shipment_dashboard_scripts_are_deferred() -> None:
    html = _read("templates/shipment/partials/dashboard_scripts.html")

    _assert_deferred(html, "js/shipment/image-export.js")
    _assert_deferred(html, "js/shipment/dashboard-columns.js")


def test_drawing_handoff_script_is_deferred() -> None:
    html = _read("templates/drawing/partials/workbench_detail_body.html")

    _assert_deferred(html, "js/foms/drawing-handoff.js")


def test_mobile_order_detail_zoom_helper_is_deferred_before_mobile_bundles() -> None:
    html = _read("templates/orders/mobile_order_detail.html")

    _assert_deferred(html, "js/foms/attachment-preview-zoom.js")
    assert html.index("js/foms/attachment-preview-zoom.js") < html.index(
        "js/foms/mobile-detail-attachments.js"
    )


def test_cs_schedule_map_leaflet_is_deferred() -> None:
    html = _read("templates/cs/partials/as_dashboard_body.html")

    _assert_deferred(html, "leaflet.js")


def test_measurement_map_blocking_scripts_are_deferred() -> None:
    html = _read("templates/measurement/map_view.html")

    _assert_deferred(html, "bootstrap.bundle.min.js")
    _assert_deferred(html, "js/runtime/common_utils.js")


def test_erp_order_shared_scripts_are_deferred_with_preserved_globals() -> None:
    html = _read("templates/orders/partials/erp_order_js.html")
    shared_js = _read("static/js/orders/erp-order-shared.js")

    _assert_deferred(html, "js/foms/attachment-preview-zoom.js")
    _assert_deferred(html, "js/orders/erp-order-shared.js")
    assert html.index("js/foms/attachment-preview-zoom.js") < html.index(
        "js/orders/erp-order-shared.js"
    )
    assert 'var ORDER_ID = parseInt(String(window.ORDER_ID || "0"), 10) || 0;' in shared_js
    assert 'typeof window.ERP_ORDER_ENABLED !== "undefined"' in shared_js
    assert "window.ERP_ORDER_ENABLED = ERP_ORDER_ENABLED;" in shared_js


def test_wdcalculator_bootstrap_chunks_are_deferred_before_dom_ready_host() -> None:
    html = _read("templates/wdcalculator/partials/wdcalculator_scripts_config.html")
    host = _read("templates/wdcalculator/partials/wdcalculator_scripts.html")
    chunks = [
        "js/wdcalculator/shared.js",
        "js/wdcalculator/unsaved-exit-guard.js",
        "js/wdcalculator/layout-sync-wiring.js",
        "js/wdcalculator/composition.js",
        "js/wdcalculator/estimate-lifecycle.js",
        "js/wdcalculator/spec-width-eval.js",
        "js/wdcalculator/primary-form.js",
        "js/wdcalculator/pricing-core.js",
    ]

    for needle in chunks:
        _assert_deferred(html, needle)
    assert "document.addEventListener('DOMContentLoaded', function() {" in host


def test_deferred_page_scripts_are_removed_from_global_sync_allowlist() -> None:
    guard = _read("tests/performance/test_perf_regression_guard.py")
    retired_keys = [
        "attachment-preview-zoom.js",
        "cdn:leaflet.js",
        "common_utils.js",
        "endpoint:channel_chat_pages.chat_scripts_js",
        "column-resizer.js",
        "composition.js",
        "dashboard-columns.js",
        "dashboard.js",
        "drawing-handoff.js",
        "erp-order-shared.js",
        "estimate-lifecycle.js",
        "image-export.js",
        "layout-sync-wiring.js",
        "manual-rows.js",
        "mobile.js",
        "order-detail-fragment.js",
        "pricing-core.js",
        "primary-form.js",
        "shared.js",
        "spec-width-eval.js",
        "unsaved-exit-guard.js",
    ]

    for key in retired_keys:
        assert key not in guard
