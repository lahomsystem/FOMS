from types import SimpleNamespace

from foms.services.erp_shipment_settings import (
    DEFAULT_ERP_WORKER_CAPACITY,
    is_order_assigned_to_user_for_construction,
    is_order_mine_for_user,
    normalize_erp_shipment_workers,
    normalize_measurement_managers,
)


def _make_order(*, structured_data=None, manager_name=""):
    return SimpleNamespace(
        structured_data=structured_data if structured_data is not None else {},
        manager_name=manager_name,
    )


def _make_user(*, name="", username=""):
    return SimpleNamespace(name=name, username=username)


def test_normalize_measurement_managers_normalizes_names_and_sort_orders() -> None:
    result = normalize_measurement_managers(
        [
            "  홍길동  ",
            {"name": "김영희", "sort_order": "2"},
            {"name": "이철수", "sort_order": "bad"},
            {"name": "   ", "sort_order": 1},
        ]
    )

    assert result == [
        {"name": "홍길동", "sort_order": 999},
        {"name": "김영희", "sort_order": 2},
        {"name": "이철수", "sort_order": 999},
    ]


def test_normalize_erp_shipment_workers_normalizes_capacity_and_off_dates() -> None:
    result = normalize_erp_shipment_workers(
        [
            {
                "name": "  김시공  ",
                "capacity": "3",
                "off_dates": ["2026-04-01", "2026-04-01", "  "],
            },
            {
                "text": "이출고",
                "daily_capacity": "bad",
                "offDays": ["2026-04-02", "2026-04-02"],
            },
            " 박지원 ",
        ]
    )

    assert result == [
        {
            "name": "김시공",
            "capacity": 3,
            "off_dates": ["2026-04-01"],
        },
        {
            "name": "이출고",
            "capacity": DEFAULT_ERP_WORKER_CAPACITY,
            "off_dates": ["2026-04-02"],
        },
        {
            "name": "박지원",
            "capacity": DEFAULT_ERP_WORKER_CAPACITY,
            "off_dates": [],
        },
    ]


def test_is_order_assigned_to_user_for_construction_matches_case_insensitively() -> None:
    order = _make_order(
        structured_data={
            "shipment": {
                "construction_workers": [
                    "김시공",
                    {"name": "이출고"},
                ]
            }
        }
    )

    assert is_order_assigned_to_user_for_construction(order, " 김시공 ")
    assert is_order_assigned_to_user_for_construction(order, "이출고")
    assert not is_order_assigned_to_user_for_construction(order, "박지원")


def test_is_order_mine_for_user_supports_manager_fields_and_username_fallback() -> None:
    order = _make_order(
        structured_data={
            "parties": {
                "manager": {
                    "name": "담당매니저",
                }
            },
            "workflow": {
                "current_quest": {
                    "owner_person": "quest-owner",
                }
            },
        },
        manager_name="컬럼담당자",
    )

    assert is_order_mine_for_user(order, _make_user(name="담당매니저"))
    assert is_order_mine_for_user(order, _make_user(username="quest-owner"))
    assert is_order_mine_for_user(order, _make_user(username="컬럼담당자"))
    assert not is_order_mine_for_user(order, _make_user(name="다른사람"))
