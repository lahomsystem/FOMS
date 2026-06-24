"""Chunk-level Node contracts for WDCalculator `estimate-lifecycle.js`.

Wave 5 (W5-B4): lifecycle/state/search/save/load bands now read from the
single canonical source `static/js/wdcalculator/estimate-lifecycle.js`.
"""

from __future__ import annotations

import shutil

import pytest

from tests.contracts.wdcalculator._node_runner import run_wdcalculator_node_check

_ESTIMATE_LIFECYCLE_SCRIPTS: tuple[str, ...] = (
    "tests/support/wdcalculator_current_database_estimate_id_contract_node_checks.js",
    "tests/support/wdcalculator_editing_estimate_id_contract_node_checks.js",
    "tests/support/wdcalculator_estimates_state_contract_node_checks.js",
    "tests/support/wdcalculator_loading_state_contract_node_checks.js",
    "tests/support/wdcalculator_products_state_contract_node_checks.js",
    "tests/support/wdcalculator_add_estimate_contract_node_checks.js",
    "tests/support/wdcalculator_save_estimate_contract_node_checks.js",
    "tests/support/wdcalculator_load_estimate_to_input_form_contract_node_checks.js",
    "tests/support/wdcalculator_load_saved_estimate_to_form_contract_node_checks.js",
    "tests/support/wdcalculator_reset_input_form_keep_customer_contract_node_checks.js",
    "tests/support/wdcalculator_refresh_after_save_contract_node_checks.js",
    "tests/support/wdcalculator_estimate_list_events_contract_node_checks.js",
    "tests/support/wdcalculator_estimate_mutation_bridge_contract_node_checks.js",
    "tests/support/wdcalculator_render_list_contract_node_checks.js",
    "tests/support/wdcalculator_search_load_contract_node_checks.js",
    "tests/support/wdcalculator_sidebar_delete_contract_node_checks.js",
    "tests/support/wdcalculator_url_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_order_match_contract_node_checks.js",
)


@pytest.mark.parametrize("support_script", _ESTIMATE_LIFECYCLE_SCRIPTS)
@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_estimate_lifecycle_chunk_contract_node_checks(support_script: str) -> None:
    """Runs one estimate-lifecycle contract check script under Node."""
    run_wdcalculator_node_check(support_script)
