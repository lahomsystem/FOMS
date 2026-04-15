"""Chunk-level Node contracts for WDCalculator `pricing-core.js`.

Wave 5 (W5-B5): pricing math, totals, resolvers, orchestration, and coupon/shipping
wiring now read from the single canonical source `static/js/wdcalculator/pricing-core.js`.
"""

from __future__ import annotations

import shutil

import pytest

from tests.contracts.wdcalculator._node_runner import run_wdcalculator_node_check

_PRICING_CORE_SCRIPTS: tuple[str, ...] = (
    "tests/support/wdcalculator_current_estimate_contract_node_checks.js",
    "tests/support/wdcalculator_estimate_totals_node_checks.js",
    "tests/support/wdcalculator_calculation_resolvers_contract_node_checks.js",
    "tests/support/wdcalculator_calculate_total_estimates_contract_node_checks.js",
    "tests/support/wdcalculator_coupon_shipping_wiring_contract_node_checks.js",
)


@pytest.mark.parametrize("support_script", _PRICING_CORE_SCRIPTS)
@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_pricing_core_chunk_contract_node_checks(support_script: str) -> None:
    """Runs one pricing-core-band contract check script under Node."""
    run_wdcalculator_node_check(support_script)
