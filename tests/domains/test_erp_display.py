import datetime
from types import SimpleNamespace

from foms.services.erp_display import (
    _ensure_dict,
    _normalize_date_to_yyyymmdd,
    apply_erp_display_fields,
    clean_dict_like_name,
    erp_deposit_amount_from_structured,
    erp_payment_amount_from_structured,
    normalize_manager_name,
    self_measurement_four_checks_done,
)


def test_normalize_manager_name_keeps_plain_text_names() -> None:
    assert normalize_manager_name("  홍길동  ") == "홍길동"
    assert clean_dict_like_name("{'name': '김영희'}") == "김영희"


def test_ensure_dict_and_normalize_date_helpers_handle_common_inputs() -> None:
    assert _ensure_dict({"name": "라홈"}) == {"name": "라홈"}
    assert _ensure_dict('{"name": "라홈"}') == {"name": "라홈"}
    assert _ensure_dict("not-json") == {}

    assert _normalize_date_to_yyyymmdd(datetime.date(2026, 4, 7)) == "2026-04-07"
    assert _normalize_date_to_yyyymmdd({"year": 2026, "month": 4, "day": 7}) == "2026-04-07"


def test_self_measurement_four_checks_done_requires_all_flags() -> None:
    complete = SimpleNamespace(
        is_self_measurement=True,
        measurement_completed=True,
        regional_sales_order_upload=True,
        regional_blueprint_sent=True,
        regional_order_upload=True,
    )
    incomplete = SimpleNamespace(
        is_self_measurement=True,
        measurement_completed=True,
        regional_sales_order_upload=False,
        regional_blueprint_sent=True,
        regional_order_upload=True,
    )

    assert self_measurement_four_checks_done(complete) is True
    assert self_measurement_four_checks_done(incomplete) is False


def test_erp_payment_amount_prefers_totals_items_total() -> None:
    sd = {
        "totals": {"items_total": 1_198_400},
        "items": [{"price": 1}],
    }
    assert erp_payment_amount_from_structured(sd) == 1_198_400


def test_erp_payment_amount_sums_items_when_totals_missing() -> None:
    sd = {
        "items": [
            {"price": "500,000"},
            {"price": 698400},
        ],
    }
    assert erp_payment_amount_from_structured(sd) == 1_198_400


def test_erp_payment_amount_falls_back_when_items_total_unparsable() -> None:
    sd = {
        "totals": {"items_total": "not-a-number"},
        "items": [{"price": 100}],
    }
    assert erp_payment_amount_from_structured(sd) == 100


def test_erp_deposit_amount_reads_payment_deposit() -> None:
    sd = {
        "totals": {"items_total": 1_198_400},
        "payment": {"deposit": 500_000},
    }
    assert erp_deposit_amount_from_structured(sd) == 500_000


def test_erp_deposit_amount_falls_back_to_payments_key() -> None:
    sd = {"payments": {"deposit": {"amount": "250,000"}}}
    assert erp_deposit_amount_from_structured(sd) == 250_000


def test_erp_deposit_amount_returns_zero_for_explicit_zero_deposit() -> None:
    sd = {"payment": {"deposit": 0}}
    assert erp_deposit_amount_from_structured(sd) == 0


def test_erp_deposit_amount_reads_zero_from_dict_amount() -> None:
    sd = {"payment": {"deposit": {"amount": 0}}}
    assert erp_deposit_amount_from_structured(sd) == 0


def test_erp_deposit_amount_returns_none_for_null_deposit() -> None:
    sd = {"payment": {"deposit": None}}
    assert erp_deposit_amount_from_structured(sd) is None


def test_erp_deposit_amount_returns_none_when_deposit_missing() -> None:
    sd = {"payment": {"discount": 10_000}, "totals": {"items_total": 100}}
    assert erp_deposit_amount_from_structured(sd) is None


def test_apply_erp_display_fields_sets_payment_for_erp_order() -> None:
    order = SimpleNamespace(
        is_erp_order=True,
        payment_amount=0,
        structured_data={
            "totals": {"items_total": "1,198,400"},
            "payment": {"deposit": 500_000},
        },
    )
    apply_erp_display_fields(order)
    assert order.payment_amount == 500_000
