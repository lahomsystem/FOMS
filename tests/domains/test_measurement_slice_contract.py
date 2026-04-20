"""Structural contracts for the Step 5 measurement vertical slice (canonical modules + W8 retirement sentinels)."""

import inspect

from tests.contracts.runtime.importlib_contract_helpers import find_spec_or_none

import foms.api.measurement as canonical_measurement_api
import foms.web.measurement.dashboard as canonical_measurement_dashboard
from foms.services.measurement_dates import extract_all_measurement_dates as canonical_extract_dates


def test_wave8_legacy_measurement_dashboard_bridge_retired() -> None:
    """W8-B5: apps.erp_measurement_dashboard shim file removed from import path."""
    assert find_spec_or_none("apps.erp_measurement_dashboard") is None


def test_wave8_legacy_erp_measurement_api_bridge_retired() -> None:
    """W8-B5: apps.api.erp_measurement shim file removed from import path."""
    assert find_spec_or_none("apps.api.erp_measurement") is None


def test_canonical_measurement_dashboard_module_smoke() -> None:
    """Canonical measurement dashboard exposes blueprint and date helpers."""
    assert canonical_measurement_dashboard.erp_measurement_dashboard_bp is not None
    assert canonical_measurement_dashboard.extract_all_measurement_dates is canonical_extract_dates


def test_canonical_measurement_api_module_smoke() -> None:
    """Canonical measurement API exposes the erp_measurement blueprint."""
    assert canonical_measurement_api.erp_measurement_bp is not None


def test_measurement_dashboard_renders_canonical_template() -> None:
    """Dashboard view should reference the namespaced measurement template."""
    src = inspect.getsource(canonical_measurement_dashboard.erp_measurement_dashboard)
    assert "measurement/dashboard.html" in src


def test_measurement_map_helpers_export_self_measurement_filter() -> None:
    """measurement_map should keep the self-measurement exclusion import for map flows."""
    from foms.api.measurement import map as measurement_map

    src = inspect.getsource(measurement_map)
    assert "from foms.services.erp_display import self_measurement_four_checks_done" in src
