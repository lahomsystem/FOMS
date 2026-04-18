from types import SimpleNamespace

from foms.services.geocode_helpers import (
    compute_address_hash,
    extract_address_from_order,
    extract_address_from_structured_data,
)


def test_compute_address_hash_normalizes_whitespace() -> None:
    assert compute_address_hash("서울시  강남구") == compute_address_hash("  서울시 강남구  ")


def test_compute_address_hash_returns_blank_for_invalid_input() -> None:
    assert compute_address_hash("") == ""
    assert compute_address_hash(None) == ""  # type: ignore[arg-type]


def test_extract_address_from_structured_data_prefers_full_address() -> None:
    structured_data = {
        "site": {
            "address_full": "서울시 강남구 테헤란로 1",
            "address_main": "서울시 강남구",
            "address_detail": "101호",
        }
    }

    assert extract_address_from_structured_data(structured_data) == "서울시 강남구 테헤란로 1"


def test_extract_address_from_structured_data_combines_main_and_detail() -> None:
    structured_data = {
        "site": {
            "address_main": "서울시 강남구",
            "address_detail": "101호",
        }
    }

    assert extract_address_from_structured_data(structured_data) == "서울시 강남구 101호"


def test_extract_address_from_structured_data_falls_back_when_full_address_is_dash() -> None:
    structured_data = {
        "site": {
            "address_full": "-",
            "address_main": "서울시 강남구",
            "address_detail": "101호",
        }
    }

    assert extract_address_from_structured_data(structured_data) == "서울시 강남구 101호"


def test_extract_address_from_order_uses_erp_order_structured_address() -> None:
    order = SimpleNamespace(
        is_erp_order=True,
        structured_data={
            "site": {
                "address_main": "서울시 강남구",
                "address_detail": "101호",
            }
        },
        address="레거시 주소",
    )

    assert extract_address_from_order(order) == "서울시 강남구 101호"


def test_extract_address_from_order_falls_back_to_legacy_address() -> None:
    order = SimpleNamespace(
        is_erp_order=False,
        structured_data=None,
        address="  부산시 해운대구  ",
    )

    assert extract_address_from_order(order) == "부산시 해운대구"


def test_extract_address_from_order_falls_back_when_erp_order_has_no_valid_site_address() -> None:
    order = SimpleNamespace(
        is_erp_order=True,
        structured_data={
            "site": {
                "address_full": "-",
                "address_main": "",
                "address_detail": "",
            }
        },
        address="  대구시 수성구  ",
    )

    assert extract_address_from_order(order) == "대구시 수성구"
