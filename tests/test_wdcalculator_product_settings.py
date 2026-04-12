"""Regression tests for WDCalculator product settings persistence."""
import json
import re

import pytest

import apps.api.wdcalculator as wd_module
from wdcalculator_db import init_wdcalculator_db, wd_calculator_engine, wd_calculator_session
from wdcalculator_models import (
    Estimate,
    EstimateHistory,
    EstimateOrderMatch,
    WDCalculatorProductSettings,
)


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def wdcalculator_settings_env(app, tmp_path, monkeypatch):
    """Use temp seed files and isolated WDCalculator tables."""
    products_path = tmp_path / "products.json"
    additional_path = tmp_path / "additional_options.json"
    notes_path = tmp_path / "notes_categories.json"

    _write_json(
        products_path,
        {
            "products": [
                {
                    "id": 1,
                    "name": "Seed Product",
                    "pricing_type": "30cm",
                    "additional_options": [],
                    "coupon_type": "percentage",
                    "coupon_value": 0,
                    "price_30cm": 1000,
                    "price_1cm": 10,
                }
            ]
        },
    )
    _write_json(
        additional_path,
        {
            "categories": [
                {
                    "id": 1,
                    "name": "기본 옵션",
                    "options": [
                        {
                            "id": 1000,
                            "name": "기본 추가옵션",
                            "price": 5000,
                        }
                    ],
                }
            ]
        },
    )
    _write_json(
        notes_path,
        {
            "categories": [
                {
                    "id": 1,
                    "name": "기본 비고",
                    "options": [
                        {
                            "id": 1000,
                            "name": "기본 비고 문구",
                            "price": 0,
                        }
                    ],
                }
            ]
        },
    )

    monkeypatch.setattr(wd_module, "WD_CALCULATOR_DATA_PATH", str(products_path))
    monkeypatch.setattr(wd_module, "WD_ADDITIONAL_OPTIONS_PATH", str(additional_path))
    monkeypatch.setattr(wd_module, "WD_NOTES_CATEGORIES_PATH", str(notes_path))

    init_wdcalculator_db()
    wd_calculator_session.query(EstimateOrderMatch).delete()
    wd_calculator_session.query(EstimateHistory).delete()
    wd_calculator_session.query(Estimate).delete()
    wd_calculator_session.query(WDCalculatorProductSettings).delete()
    wd_calculator_session.commit()

    yield {
        "products_path": products_path,
        "additional_path": additional_path,
        "notes_path": notes_path,
    }

    wd_calculator_session.rollback()
    wd_calculator_session.query(EstimateOrderMatch).delete()
    wd_calculator_session.query(EstimateHistory).delete()
    wd_calculator_session.query(Estimate).delete()
    wd_calculator_session.query(WDCalculatorProductSettings).delete()
    wd_calculator_session.commit()
    wd_calculator_session.remove()


def test_wdcalculator_page_renders_inline_config_contract(wdcalculator_settings_env, login):
    """`/wdcalculator` must keep the inline config and shared.js load-order contract."""
    client = login

    response = client.get("/wdcalculator")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    categories_idx = body.index("var wdCalculatorCategories =")
    notes_idx = body.index("var wdNotesCategories =")
    shared_idx = body.index("js/wdcalculator/shared.js")
    sidebar_idx = body.index("js/wdcalculator/sidebar-estimates.js")
    estimate_totals_idx = body.index("js/wdcalculator/estimate-totals.js")
    current_estimate_math_idx = body.index("js/wdcalculator/current-estimate-math.js")
    notes_ui_idx = body.index("js/wdcalculator/notes-ui.js")
    base_components_ui_idx = body.index("js/wdcalculator/base-components-ui.js")
    coupon_display_helpers_idx = body.index("js/wdcalculator/coupon-display-helpers.js")
    additional_options_ui_idx = body.index("js/wdcalculator/additional-options-ui.js")
    product_catalog_ui_idx = body.index("js/wdcalculator/product-catalog-ui.js")
    dom_ready_idx = body.index("document.addEventListener('DOMContentLoaded'")
    categories_match = re.search(
        r"var wdCalculatorCategories = (.+?) \|\| \[\];",
        body,
        re.S,
    )
    notes_match = re.search(
        r"var wdNotesCategories = (.+?) \|\| \[\];",
        body,
        re.S,
    )

    assert (
        categories_idx
        < shared_idx
        < sidebar_idx
        < estimate_totals_idx
        < current_estimate_math_idx
        < notes_ui_idx
        < base_components_ui_idx
        < coupon_display_helpers_idx
        < additional_options_ui_idx
        < product_catalog_ui_idx
        < dom_ready_idx
    )
    assert notes_idx < shared_idx
    assert categories_match is not None
    assert notes_match is not None
    categories_payload = json.loads(categories_match.group(1))
    notes_payload = json.loads(notes_match.group(1))
    assert categories_payload[0]["name"] == "기본 옵션"
    assert notes_payload[0]["name"] == "기본 비고"


def test_wdcalculator_products_api_keeps_legacy_success_shape(
    wdcalculator_settings_env, login
):
    """Product catalog loader must keep the legacy `{success, products}` payload shape."""
    client = login

    response = client.get("/api/wdcalculator/products")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert isinstance(payload["products"], list)
    first_product = payload["products"][0]
    assert first_product["id"] == 1
    assert first_product["name"] == "Seed Product"
    assert first_product["pricing_type"] == "30cm"
    assert first_product["additional_options"] == []
    assert first_product["coupon_type"] == "percentage"
    assert first_product["coupon_value"] == 0
    assert first_product["price_30cm"] == 1000
    assert first_product["price_1cm"] == 10


def test_wdcalculator_calculate_save_and_load_estimate_smoke(wdcalculator_settings_env, login):
    """Core WDCalculator API flow must keep calculate -> save -> load roundtrip working."""
    client = login

    calculate_response = client.post(
        "/api/wdcalculator/calculate",
        json={
            "product_id": 1,
            "width_mm": 300,
            "additional_options": [],
            "coupon_type": "percentage",
            "coupon_value": 0,
        },
    )

    assert calculate_response.status_code == 200
    calculate_payload = calculate_response.get_json()
    assert calculate_payload["success"] is True
    assert calculate_payload["base_price"] == 1000
    assert calculate_payload["final_price"] == 1000

    estimate_data = {
        "items": [{"product_id": 1, "width_mm": 300}],
        "totals": {
            "base_price": calculate_payload["base_price"],
            "final_price": calculate_payload["final_price"],
        },
    }
    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={"customer_name": "WD Smoke", "estimate_data": estimate_data},
    )

    assert save_response.status_code == 200
    save_payload = save_response.get_json()
    assert save_payload["success"] is True
    assert isinstance(save_payload["estimate_id"], int)

    load_response = client.get(f"/api/wdcalculator/estimate/{save_payload['estimate_id']}")

    assert load_response.status_code == 200
    load_payload = load_response.get_json()
    assert load_payload["success"] is True
    assert load_payload["estimate"]["customer_name"] == "WD Smoke"
    assert load_payload["estimate"]["estimate_data"] == estimate_data


def test_wdcalculator_search_and_delete_estimate_smoke(wdcalculator_settings_env, login):
    """Sidebar estimate APIs must preserve search -> delete behavior."""
    client = login
    estimate_data = {"items": [{"product_id": 1, "width_mm": 300}]}

    save_response = client.post(
        "/api/wdcalculator/save-estimate",
        json={"customer_name": "WD Sidebar", "estimate_data": estimate_data},
    )

    assert save_response.status_code == 200
    saved_id = save_response.get_json()["estimate_id"]

    search_response = client.get("/api/wdcalculator/search-estimates?customer_name=Sidebar")

    assert search_response.status_code == 200
    search_payload = search_response.get_json()
    assert search_payload["success"] is True
    assert any(estimate["id"] == saved_id for estimate in search_payload["estimates"])

    delete_response = client.delete(f"/api/wdcalculator/estimate/{saved_id}")

    assert delete_response.status_code == 200
    delete_payload = delete_response.get_json()
    assert delete_payload["success"] is True

    post_delete_search = client.get("/api/wdcalculator/search-estimates?customer_name=Sidebar")
    post_delete_payload = post_delete_search.get_json()
    assert post_delete_payload["success"] is True
    assert all(estimate["id"] != saved_id for estimate in post_delete_payload["estimates"])


def test_wdcalculator_products_persist_in_db_after_seed_file_changes(wdcalculator_settings_env, login):
    """Saved products must come from DB, not revert to file seed."""
    client = login

    initial_response = client.get("/api/wdcalculator/products")
    assert initial_response.status_code == 200
    initial_products = initial_response.get_json()["products"]
    assert initial_products[0]["name"] == "Seed Product"

    save_response = client.post(
        "/api/wdcalculator/products",
        json={
            "id": 1,
            "name": "Updated Product",
            "pricing_type": "30cm",
            "additional_options": [],
            "coupon_type": "percentage",
            "coupon_value": 0,
            "price_30cm": 2222,
            "price_1cm": 22,
        },
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["products_path"],
        {
            "products": [
                {
                    "id": 1,
                    "name": "Wrong Seed Value",
                    "pricing_type": "30cm",
                    "additional_options": [],
                    "coupon_type": "percentage",
                    "coupon_value": 0,
                    "price_30cm": 9999,
                    "price_1cm": 99,
                }
            ]
        },
    )

    wd_calculator_session.expire_all()
    reloaded_response = client.get("/api/wdcalculator/products")
    reloaded_products = reloaded_response.get_json()["products"]
    assert reloaded_products[0]["name"] == "Updated Product"
    assert reloaded_products[0]["price_30cm"] == 2222

    wd_calculator_session.expire_all()
    settings = wd_calculator_session.query(WDCalculatorProductSettings).filter(
        WDCalculatorProductSettings.id == 1
    ).first()
    assert settings is not None
    assert settings.products[0]["name"] == "Updated Product"


def test_wdcalculator_additional_options_persist_in_db_after_seed_file_changes(wdcalculator_settings_env, login):
    """Additional options must keep DB state even if seed files change."""
    client = login

    initial_response = client.get("/api/wdcalculator/additional-options/categories")
    assert initial_response.status_code == 200
    initial_categories = initial_response.get_json()["categories"]
    assert initial_categories[0]["name"] == "기본 옵션"

    save_response = client.post(
        "/api/wdcalculator/additional-options/categories/1/options",
        json={"name": "신규 추가옵션", "price": 12345},
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["additional_path"],
        {
            "categories": [
                {
                    "id": 1,
                    "name": "파일 기준값",
                    "options": [],
                }
            ]
        },
    )

    wd_calculator_session.expire_all()
    reloaded_response = client.get("/api/wdcalculator/additional-options/categories")
    reloaded_categories = reloaded_response.get_json()["categories"]

    assert reloaded_categories[0]["name"] == "기본 옵션"
    assert any(
        option["name"] == "신규 추가옵션"
        for option in reloaded_categories[0]["options"]
    )


def test_wdcalculator_notes_persist_in_db_after_seed_file_changes(wdcalculator_settings_env, login):
    """Notes categories must keep DB state even if seed files change."""
    client = login

    initial_response = client.get("/api/wdcalculator/notes/categories")
    assert initial_response.status_code == 200
    initial_categories = initial_response.get_json()["categories"]
    assert initial_categories[0]["name"] == "기본 비고"

    save_response = client.post(
        "/api/wdcalculator/notes/categories/1/options",
        json={"name": "신규 비고 문구"},
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["success"] is True

    _write_json(
        wdcalculator_settings_env["notes_path"],
        {
            "categories": [
                {
                    "id": 1,
                    "name": "파일 비고 기준값",
                    "options": [],
                }
            ]
        },
    )

    wd_calculator_session.expire_all()
    reloaded_response = client.get("/api/wdcalculator/notes/categories")
    reloaded_categories = reloaded_response.get_json()["categories"]

    assert reloaded_categories[0]["name"] == "기본 비고"
    assert any(
        option["name"] == "신규 비고 문구"
        for option in reloaded_categories[0]["options"]
    )
