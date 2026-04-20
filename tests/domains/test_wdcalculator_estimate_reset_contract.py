"""Contract tests for WDCalculator save-reset + unit-price UI markers (2026-04-20 batch)."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_save_estimate_api_inserts_without_estimate_id():
    """Server uses presence of `estimate_id` in JSON to choose update vs insert (see blueprint)."""
    text = (_REPO_ROOT / "foms/api/wdcalculator/blueprint.py").read_text(encoding="utf-8")
    assert "estimate_id = data.get('estimate_id')" in text
    assert "if estimate_id:" in text
    assert "Estimate(customer_name=customer_name, estimate_data=estimate_data)" in text


def test_unit_price_meta_localstorage_key_stable():
    """Toggle persistence key must stay namespaced to avoid clashing with other WD prefs."""
    text = (_REPO_ROOT / "static/js/wdcalculator/pricing-core.js").read_text(encoding="utf-8")
    assert "foms.wdcalculator.unitPriceMetaVisible" in text


def test_wdcalculator_page_includes_unit_price_slots_and_full_reset_wiring(
    wdcalculator_settings_env, login
):
    """Rendered `/wdcalculator` exposes DOM hooks and wires full reset after save."""
    client = login
    response = client.get("/wdcalculator")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="currentQuoteUnitPriceMeta"' in body
    assert 'id="wdUnitPriceMetaToggle"' in body
    assert "resetInputFormToNewEstimate" in body
    assert "initWdCalculatorUnitPriceMetaToggle" in body
    assert "WdCalculatorUnitPriceMeta" in body
