"""Structural contracts for the Step 5 measurement vertical slice (alias shims + canonical modules)."""

import importlib
import inspect

import foms.api.measurement as canonical_measurement_api
import foms.web.measurement.dashboard as canonical_measurement_dashboard
from foms.services.measurement_dates import extract_all_measurement_dates as canonical_extract_dates


def test_legacy_measurement_dashboard_import_aliases_canonical_module() -> None:
    """Importing apps.erp_measurement_dashboard should yield the canonical dashboard module."""
    legacy = importlib.import_module("apps.erp_measurement_dashboard")
    assert legacy is canonical_measurement_dashboard
    assert legacy.erp_measurement_dashboard_bp is canonical_measurement_dashboard.erp_measurement_dashboard_bp
    assert legacy.extract_all_measurement_dates is canonical_extract_dates


def test_legacy_measurement_api_import_aliases_canonical_module() -> None:
    """Importing apps.api.erp_measurement should yield the canonical measurement API module."""
    legacy = importlib.import_module("apps.api.erp_measurement")
    assert legacy is canonical_measurement_api
    assert legacy.erp_measurement_bp is canonical_measurement_api.erp_measurement_bp


def test_measurement_dashboard_renders_canonical_template() -> None:
    """Dashboard view should reference the namespaced measurement template."""
    src = inspect.getsource(canonical_measurement_dashboard.erp_measurement_dashboard)
    assert "measurement/dashboard.html" in src


def test_measurement_map_helpers_export_self_measurement_filter() -> None:
    """measurement_map should keep the self-measurement exclusion import for map flows."""
    from foms.api import measurement_map

    src = inspect.getsource(measurement_map)
    assert "from foms.services.erp_display import self_measurement_four_checks_done" in src
