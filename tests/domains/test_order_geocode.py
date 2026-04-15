from types import SimpleNamespace

import foms.services.order_geocode as order_geocode_module
from foms.services.order_geocode import (
    apply_erp_beta_site_address_to_sd,
    clear_order_geocode_coords,
    reset_order_geocode_on_address_change,
)


def test_apply_erp_beta_site_address_to_sd_sets_site_fields_and_clears_detail() -> None:
    structured_data = {
        "site": {
            "address_full": "기존 주소",
            "address_main": "기존 주소",
            "address_detail": "101호",
        }
    }

    changed = apply_erp_beta_site_address_to_sd(structured_data, " 서울시 강남구 테헤란로 1 ")

    assert changed is True
    assert structured_data["site"] == {
        "address_full": "서울시 강남구 테헤란로 1",
        "address_main": "서울시 강남구 테헤란로 1",
        "address_detail": "",
    }


def test_apply_erp_beta_site_address_to_sd_returns_false_when_already_normalized() -> None:
    structured_data = {
        "site": {
            "address_full": "서울시 강남구 테헤란로 1",
            "address_main": "서울시 강남구 테헤란로 1",
            "address_detail": "",
        }
    }

    changed = apply_erp_beta_site_address_to_sd(structured_data, "서울시 강남구 테헤란로 1")

    assert changed is False


def test_apply_erp_beta_site_address_to_sd_creates_site_and_clears_blank_address() -> None:
    structured_data = {}

    changed = apply_erp_beta_site_address_to_sd(structured_data, "")

    assert changed is False
    assert structured_data["site"] == {}


def test_reset_order_geocode_on_address_change_syncs_beta_site_and_resets_coords(monkeypatch) -> None:
    flagged_fields: list[str] = []
    monkeypatch.setattr(
        order_geocode_module,
        "flag_modified",
        lambda _order, field_name: flagged_fields.append(field_name),
    )

    order = SimpleNamespace(
        is_erp_beta=True,
        structured_data={
            "site": {
                "address_full": "기존 주소",
                "address_main": "기존 주소",
                "address_detail": "101호",
            }
        },
        address="기존 주소",
        lat=37.123,
        lng=127.456,
        geocode_status="success",
    )

    normalized = reset_order_geocode_on_address_change(order, " 서울시 강남구 테헤란로 1 ")

    assert normalized == "서울시 강남구 테헤란로 1"
    assert order.address == "서울시 강남구 테헤란로 1"
    assert order.structured_data["site"] == {
        "address_full": "서울시 강남구 테헤란로 1",
        "address_main": "서울시 강남구 테헤란로 1",
        "address_detail": "",
    }
    assert order.lat is None
    assert order.lng is None
    assert order.geocode_status == "pending"
    assert flagged_fields == ["structured_data"]


def test_reset_order_geocode_on_address_change_handles_non_beta_orders_without_structured_data(monkeypatch) -> None:
    flagged_fields: list[str] = []
    monkeypatch.setattr(
        order_geocode_module,
        "flag_modified",
        lambda _order, field_name: flagged_fields.append(field_name),
    )

    order = SimpleNamespace(
        is_erp_beta=False,
        structured_data=None,
        address="기존 주소",
        lat=37.123,
        lng=127.456,
        geocode_status="success",
    )

    normalized = reset_order_geocode_on_address_change(order, " 부산시 해운대구 ")

    assert normalized == "부산시 해운대구"
    assert order.address == "부산시 해운대구"
    assert order.lat is None
    assert order.lng is None
    assert order.geocode_status == "pending"
    assert flagged_fields == []


def test_clear_order_geocode_coords_resets_only_coords_and_status() -> None:
    order = SimpleNamespace(
        lat=37.123,
        lng=127.456,
        geocode_status="success",
        structured_data={"site": {"address_full": "서울시 강남구 테헤란로 1"}},
    )

    clear_order_geocode_coords(order)

    assert order.lat is None
    assert order.lng is None
    assert order.geocode_status == "pending"
    assert order.structured_data == {"site": {"address_full": "서울시 강남구 테헤란로 1"}}
