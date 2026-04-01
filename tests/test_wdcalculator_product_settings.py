"""Regression tests for WDCalculator product settings persistence."""
import json

import pytest

import apps.api.wdcalculator as wd_module
from wdcalculator_db import wd_calculator_engine, wd_calculator_session
from wdcalculator_models import WDCalculatorProductSettings


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

    WDCalculatorProductSettings.__table__.create(bind=wd_calculator_engine, checkfirst=True)
    wd_calculator_session.query(WDCalculatorProductSettings).delete()
    wd_calculator_session.commit()

    yield {
        "products_path": products_path,
        "additional_path": additional_path,
        "notes_path": notes_path,
    }

    wd_calculator_session.rollback()
    wd_calculator_session.query(WDCalculatorProductSettings).delete()
    wd_calculator_session.commit()
    wd_calculator_session.remove()
    WDCalculatorProductSettings.__table__.drop(bind=wd_calculator_engine, checkfirst=True)


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
