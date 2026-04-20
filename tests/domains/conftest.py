"""Domain-test fixtures shared across WDCalculator domain tests."""

import json

import pytest

import foms.api.wdcalculator.blueprint as wd_module
from wdcalculator_db import init_wdcalculator_db, wd_calculator_session
from wdcalculator_models import Estimate, EstimateHistory, EstimateOrderMatch, WDCalculatorProductSettings


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
