"""Device QA contract proxies — photo capture + bottom nav HTMX wiring (automated)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_device_qa_photo_capture_environment_on_wizard() -> None:
    step2 = (ROOT / "templates/orders/wizard/step2_products.html").read_text(encoding="utf-8")
    assert 'capture="environment"' in step2
    assert "data-foms-photo-capture" in step2
    photo_js = (ROOT / "static/js/foms/photo-capture.js").read_text(encoding="utf-8")
    assert "capture" in photo_js


def test_device_qa_photo_capture_on_erp_order_tab() -> None:
    tab = (ROOT / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    assert 'capture="environment"' in tab or "capture=environment" in tab


def test_device_qa_bottom_nav_htmx_wiring_when_flag_on() -> None:
    shell = (ROOT / "templates/partials/shared/foms_app_shell.html").read_text(encoding="utf-8")
    assert "data-bottom-nav-htmx" in shell
    assert "flag_bottom_nav_htmx" in shell
    js = (ROOT / "static/js/foms/bottom-nav-shell.js").read_text(encoding="utf-8")
    assert "navigateBottomNavHtmx" in js


def test_device_qa_offline_sw_gated_by_data_attr() -> None:
    sync_js = (ROOT / "static/js/foms/sync.js").read_text(encoding="utf-8")
    assert "data-offline-sw" in sync_js or "offlineSw" in sync_js.lower()


def test_device_qa_rum_baseline_assets() -> None:
    rum = ROOT / "static/js/foms/rum-baseline.js"
    api = ROOT / "foms/api/foms_rum.py"
    assert rum.is_file()
    assert api.is_file()
