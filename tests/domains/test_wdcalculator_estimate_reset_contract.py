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


def test_wdcalculator_mobile_builder_opens_editor_below_tapped_card():
    """Mobile builder owns cart-card edit placement instead of jumping to the top form."""
    mobile_js = (_REPO_ROOT / "static/js/wdcalculator/mobile-enhance.js").read_text(encoding="utf-8")
    builder_css = (_REPO_ROOT / "static/css/wdcalculator/builder.css").read_text(encoding="utf-8")
    lifecycle_js = (_REPO_ROOT / "static/js/wdcalculator/estimate-lifecycle.js").read_text(encoding="utf-8")

    assert "moveEditorAfterCard(card)" in mobile_js
    assert "e.stopPropagation();" in mobile_js
    assert "WdCalculatorLoadEstimateToInputForm.loadEstimateToInputForm" in mobile_js
    assert "scrollIntoView({ behavior: \"smooth\", block: \"nearest\" })" in mobile_js
    assert "documentRef.body.classList.contains(\"wd-builder\")" in lifecycle_js
    assert "body.wd-builder #estimatesListContainer .wd-editor-wrap" in builder_css
