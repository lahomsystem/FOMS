"""Tests for ERP shared utility helpers."""

from foms.services.erp_utils import ensure_path


def test_ensure_path_creates_nested_dictionaries() -> None:
    structured_data = {}

    leaf = ensure_path(structured_data, "shipment", "worker")

    assert leaf == {}
    assert structured_data == {"shipment": {"worker": {}}}


def test_ensure_path_reuses_existing_nested_dictionaries() -> None:
    structured_data = {"shipment": {"worker": {"name": "Kim"}}}

    leaf = ensure_path(structured_data, "shipment", "worker")

    assert leaf is structured_data["shipment"]["worker"]
    assert leaf["name"] == "Kim"


def test_ensure_path_returns_original_dict_when_no_keys_are_given() -> None:
    structured_data = {"workflow": {"stage": "AS"}}

    leaf = ensure_path(structured_data)

    assert leaf is structured_data
