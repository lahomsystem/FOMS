"""Tests for ERP template filters."""

from flask import Blueprint, Flask

from foms.services.erp_template_filters import (
    format_phone_filter,
    item_spec_w300_display,
    item_spec_w300_value,
    payment_confirmed_bool,
    register_erp_template_filters,
    schedule_datetime_display,
    spec_w300_filter,
    split_count_filter,
    split_list_filter,
    strip_product_w_filter,
)


def test_string_filters_cover_common_dashboard_cases() -> None:
    assert split_count_filter("A, ,B") == 2
    assert split_list_filter("A, ,B") == ["A", "B"]
    assert strip_product_w_filter("제품명 120W, 몰딩여닫이 3600 3600") == "제품명, 몰딩여닫이 3600"


def test_spec_and_schedule_filters_render_expected_values() -> None:
    assert spec_w300_filter("3600x600") == 12.0
    assert schedule_datetime_display("2026-04-09", "09:30") == "2026-04-09 09:30"
    assert schedule_datetime_display("", "09:30") == "-"


def test_phone_and_payment_filters_normalize_values() -> None:
    assert format_phone_filter("01012345678") == "010-1234-5678"
    assert payment_confirmed_bool("true") is True
    assert payment_confirmed_bool("false") is False
    assert payment_confirmed_bool(1) is True
    assert payment_confirmed_bool(2) is False


def test_item_spec_w300_value_sums_spec_rows() -> None:
    item = {
        "spec_rows": [
            {"spec_width": "600"},
            {"w": "300"},
        ]
    }

    assert item_spec_w300_display(item) == 3.0
    assert item_spec_w300_value(item) == 3.0


def test_register_erp_template_filters_registers_expected_jinja_filters() -> None:
    app = Flask(__name__)
    blueprint = Blueprint("erp_template_filters_test", __name__)

    register_erp_template_filters(blueprint)
    app.register_blueprint(blueprint)

    for filter_name in [
        "split_count",
        "split_list",
        "strip_product_w",
        "spec_w300",
        "format_phone",
        "item_spec_w300",
        "schedule_datetime_display",
        "payment_confirmed_bool",
    ]:
        assert filter_name in app.jinja_env.filters

    assert app.jinja_env.filters["payment_confirmed_bool"]("true") is True
    assert app.jinja_env.filters["spec_w300"]("3600") == 12.0
    assert app.jinja_env.filters["item_spec_w300"]({"spec_width": "900"}) == 3.0
