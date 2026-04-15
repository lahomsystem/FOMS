from werkzeug.datastructures import ImmutableMultiDict

from foms.services.request_utils import get_preserved_filter_args


def test_get_preserved_filter_args_keeps_known_keys() -> None:
    request_args = {
        "search": "kitchen",
        "status": "MEASURE",
        "page": "3",
        "ignored": "x",
    }

    assert get_preserved_filter_args(request_args) == {
        "search": "kitchen",
        "status": "MEASURE",
        "page": "3",
    }


def test_get_preserved_filter_args_keeps_dynamic_filter_keys() -> None:
    request_args = {
        "filter_customer_name": "홍길동",
        "filter_manager_name": "김담당",
        "sort_by": "received_date",
        "other": "skip",
    }

    assert get_preserved_filter_args(request_args) == {
        "filter_customer_name": "홍길동",
        "filter_manager_name": "김담당",
        "sort_by": "received_date",
    }


def test_get_preserved_filter_args_ignores_missing_keys() -> None:
    assert get_preserved_filter_args({}) == {}


def test_get_preserved_filter_args_supports_immutable_multi_dict() -> None:
    request_args = ImmutableMultiDict(
        [
            ("search", "wardrobe"),
            ("filter_status", "MEASURE"),
            ("page", "2"),
            ("ignored", "skip"),
        ]
    )

    assert get_preserved_filter_args(request_args) == {
        "search": "wardrobe",
        "filter_status": "MEASURE",
        "page": "2",
    }
