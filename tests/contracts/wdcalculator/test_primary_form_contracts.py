"""Chunk-level Node contracts for WDCalculator `primary-form.js` owner band.

Wave 7 (W7-B5): consolidates former 1:1 pytest wrappers for primary-form owner modules per W5-B1.

Excluded by design: ``pricing-core`` / ``estimate-lifecycle`` chunks (defer register).
"""

from __future__ import annotations

import shutil

import pytest

from tests.contracts.wdcalculator._node_runner import run_wdcalculator_node_check

_PRIMARY_FORM_SCRIPTS: tuple[str, ...] = (
    "tests/support/wdcalculator_spec_width_eval_contract_node_checks.js",
    "tests/support/wdcalculator_base_components_contract_node_checks.js",
    "tests/support/wdcalculator_notes_contract_node_checks.js",
    "tests/support/wdcalculator_notes_ui_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_notes_ui_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_coupon_display_contract_node_checks.js",
    "tests/support/wdcalculator_coupon_search_render_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_coupon_search_render_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_additional_options_contract_node_checks.js",
    "tests/support/wdcalculator_product_catalog_contract_node_checks.js",
    "tests/support/wdcalculator_add_option_button_contract_node_checks.js",
    "tests/support/wdcalculator_calculate_button_contract_node_checks.js",
)


@pytest.mark.parametrize("support_script", _PRIMARY_FORM_SCRIPTS)
@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_primary_form_chunk_contract_node_checks(support_script: str) -> None:
    """Runs one primary-form-band contract check script under Node."""
    run_wdcalculator_node_check(support_script)
