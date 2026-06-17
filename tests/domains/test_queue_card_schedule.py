"""Mobile v2 queue card schedule SSOT (stage-aware 실측/시공)."""

from foms.services.erp_mobile_order_display import (
    format_queue_card_schedule_summary,
    resolve_queue_card_schedule,
)


def test_construction_sub_stage_prefers_construction_date() -> None:
    """시공대기 + both dates → 시공일 (search/construction queue parity)."""
    schedule = resolve_queue_card_schedule(
        stage="시공대기",
        measurement_date="2026-06-16",
        construction_date="2026-06-20",
    )
    assert schedule == {"label": "시공", "value": "2026-06-20"}


def test_production_sub_stage_prefers_construction_date() -> None:
    schedule = resolve_queue_card_schedule(
        stage="제작대기",
        stage_code="PRODUCTION",
        measurement_date="2026-06-10",
        construction_date="2026-06-25",
    )
    assert schedule == {"label": "시공", "value": "2026-06-25"}


def test_measure_stage_prefers_measurement_date() -> None:
    schedule = resolve_queue_card_schedule(
        stage="실측",
        measurement_date="2026-06-16",
        construction_date="2026-06-20",
    )
    assert schedule == {"label": "실측", "value": "2026-06-16"}


def test_construction_code_without_sub_stage_label() -> None:
    schedule = resolve_queue_card_schedule(
        stage_code="CONSTRUCTION",
        measurement_date="2026-06-16",
        construction_date="2026-06-20",
    )
    assert schedule == {"label": "시공", "value": "2026-06-20"}


def test_fallback_measurement_when_construction_missing() -> None:
    schedule = resolve_queue_card_schedule(
        stage="시공중",
        measurement_date="2026-06-16",
        construction_date=None,
    )
    assert schedule == {"label": "실측", "value": "2026-06-16"}


def test_ignores_placeholder_schedule_values() -> None:
    schedule = resolve_queue_card_schedule(
        stage="시공대기",
        measurement_date="상담",
        construction_date="2026-06-20",
    )
    assert schedule == {"label": "시공", "value": "2026-06-20"}


def test_sub_stage_prefix_overrides_conflicting_stage_code() -> None:
    """제작대기 display label wins over CONFIRM stage_code (production tab parity)."""
    schedule = resolve_queue_card_schedule(
        stage="제작대기",
        stage_code="CONFIRM",
        measurement_date="2026-06-16",
        construction_date="2026-06-25",
    )
    assert schedule == {"label": "시공", "value": "2026-06-25"}


def test_format_queue_card_schedule_summary() -> None:
    text = format_queue_card_schedule_summary({"label": "시공", "value": "2026-06-20"})
    assert text == "시공 2026-06-20"
