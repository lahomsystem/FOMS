"""Tests for ERP flat column synchronization helpers."""

from types import SimpleNamespace

from foms.services.erp_sync_columns import sync_erp_flat_columns


def test_sync_erp_flat_columns_returns_early_for_non_erp_order() -> None:
    order = SimpleNamespace(
        is_erp_order=False,
        manager_name="before",
        erp_measurement_date="2025-01-01",
        erp_construction_date="2025-01-02",
        erp_stage_code="OLD",
        erp_urgent=False,
        erp_drawing_updated_at="unchanged",
        erp_stage_updated_at="unchanged",
        erp_owner_team_code="legacy",
    )

    sync_erp_flat_columns(order, {"workflow": {"stage": "MEASURE"}})

    assert order.manager_name == "before"
    assert order.erp_measurement_date == "2025-01-01"
    assert order.erp_stage_code == "OLD"
    assert order.erp_drawing_updated_at == "unchanged"
    assert order.erp_stage_updated_at == "unchanged"


def test_sync_erp_flat_columns_updates_expected_flat_columns() -> None:
    order = SimpleNamespace(
        is_erp_order=True,
        manager_name="",
        erp_measurement_date=None,
        erp_construction_date=None,
        erp_stage_code=None,
        erp_urgent=False,
        erp_drawing_updated_at=None,
        erp_stage_updated_at=None,
        erp_owner_team_code=None,
        payment_amount=0,
    )
    structured_data = {
        "parties": {"manager": {"name": "Manager Kim"}},
        "schedule": {
            "measurement": {"date": "2026-04-08T09:30:00"},
            "construction": {"date": {"year": 2026, "month": 4, "day": 9}},
        },
        "workflow": {
            "stage": "DRAWING",
            "stage_updated_at": "2026-04-08T12:34:56Z",
        },
        "flags": {"urgent": True},
        "assignments": {"owner_team": "CONSTRUCTION"},
        "totals": {"items_total": 1_198_400},
    }

    sync_erp_flat_columns(order, structured_data)

    assert order.manager_name == "Manager Kim"
    assert order.erp_measurement_date == "2026-04-08"
    assert order.erp_construction_date == "2026-04-09"
    assert order.erp_stage_code == "DRAWING"
    assert order.erp_urgent is True
    assert order.erp_drawing_updated_at.isoformat() == "2026-04-08T12:34:56+00:00"
    assert order.erp_stage_updated_at.isoformat() == "2026-04-08T12:34:56+00:00"
    assert order.erp_owner_team_code == "CONSTRUCTION"
    assert order.payment_amount == 1_198_400
