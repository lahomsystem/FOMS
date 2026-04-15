"""Chunk-level Node contracts for WDCalculator `composition.js` band (startup/bootstrap/order/load).

Wave 7 (W7-B5): consolidates former 1:1 `test_wdcalculator_*_contract_node.py` wrappers for the
scripts listed below. Physical checks remain in ``tests/support/wdcalculator/*_contract_node_checks.js``.

Deferred (estimate-lifecycle / cross-chunk): see ``docs/plans/2026-04-14-wave7-batch4-wdcalculator-chunk-freeze-run-record.md``.
"""

from __future__ import annotations

import shutil

import pytest

from tests.contracts.wdcalculator._node_runner import run_wdcalculator_node_check

_COMPOSITION_SCRIPTS: tuple[str, ...] = (
    "tests/support/wdcalculator_early_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_late_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_startup_init_contract_node_checks.js",
    "tests/support/wdcalculator_terminal_init_contract_node_checks.js",
    "tests/support/wdcalculator_primary_ui_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_totals_startup_terminal_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_totals_startup_terminal_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_estimates_early_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_estimates_early_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_catalog_buttons_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_catalog_buttons_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_sidebar_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_loading_database_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_loading_database_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_products_editing_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_products_editing_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_post_mutation_ui_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_post_mutation_ui_host_bootstrap_contract_node_checks.js",
    "tests/support/wdcalculator_base_live_events_contract_node_checks.js",
    "tests/support/wdcalculator_layout_sync_wiring_contract_node_checks.js",
)


@pytest.mark.parametrize("support_script", _COMPOSITION_SCRIPTS)
@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_composition_chunk_contract_node_checks(support_script: str) -> None:
    """Runs one composition-band contract check script under Node."""
    run_wdcalculator_node_check(support_script)
