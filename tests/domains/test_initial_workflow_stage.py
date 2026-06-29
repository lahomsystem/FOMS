"""Tests for initial ERP workflow stage resolution."""

from __future__ import annotations

from foms.services.orders.initial_workflow_stage import resolve_initial_workflow_stage


def test_resolve_stage_default_lahom_no_measurement() -> None:
    assert (
        resolve_initial_workflow_stage(orderer="라홈", schedule={}, items=[])
        == "RECEIVED"
    )


def test_resolve_stage_haud_orderer() -> None:
    assert (
        resolve_initial_workflow_stage(orderer="하우드", schedule={}, items=[])
        == "MEASURE"
    )


def test_resolve_stage_custom_orderer() -> None:
    assert (
        resolve_initial_workflow_stage(orderer="협력사A", schedule={}, items=[])
        == "MEASURE"
    )


def test_resolve_stage_measurement_date_overrides_lahom() -> None:
    assert (
        resolve_initial_workflow_stage(
            orderer="라홈",
            schedule={"measurement_date": "2026-06-26"},
            items=[],
        )
        == "MEASURE"
    )


def test_resolve_stage_item_measurement_date() -> None:
    assert (
        resolve_initial_workflow_stage(
            orderer="라홈",
            schedule={},
            items=[{"measurement_date": "2026-06-26"}],
        )
        == "MEASURE"
    )
