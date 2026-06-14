"""Mobile date chip geometry smoke for ERP v2 dashboards."""

from __future__ import annotations

import pytest

from tests.visual.conftest import VISUAL_ADMIN_PASSWORD, VISUAL_ADMIN_USERNAME


@pytest.fixture(autouse=True)
def _erp_mobile_v2_flags(monkeypatch: pytest.MonkeyPatch, visual_cohort_user_id: str) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", visual_cohort_user_id)


def _login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.fill('input[name="username"]', VISUAL_ADMIN_USERNAME)
    page.fill('input[name="password"]', VISUAL_ADMIN_PASSWORD)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def _date_chip_metrics(page, selector: str) -> dict[str, float | str]:
    page.locator(selector).first.wait_for()
    return page.locator(selector).first.evaluate(
        """(chip) => {
          const date = chip.querySelector(`${selector}__date`);
          const meta = chip.querySelector(`${selector}__meta`);
          const day = chip.querySelector(`${selector}__day`);
          const count = chip.querySelector(`${selector}__count`);
          const chipRect = chip.getBoundingClientRect();
          const dateRect = date.getBoundingClientRect();
          const metaRect = meta.getBoundingClientRect();
          const dayRect = day.getBoundingClientRect();
          const countRect = count.getBoundingClientRect();
          return {
            chipWidth: chipRect.width,
            chipHeight: chipRect.height,
            chipBottom: chipRect.bottom,
            dateTop: dateRect.top,
            metaTop: metaRect.top,
            dayBottom: dayRect.bottom,
            countBottom: countRect.bottom,
            metaDisplay: window.getComputedStyle(meta).display,
            chipGridRows: window.getComputedStyle(chip).gridTemplateRows
          };
        }""".replace("${selector}", selector)
    )


def _tower_day_metrics(page) -> dict[str, float | str]:
    page.locator(".foms-tower__day").first.wait_for()
    return page.locator(".foms-tower__day").first.evaluate(
        """(chip) => {
          const date = chip.querySelector(".foms-tower__day-date");
          const meta = chip.querySelector(".foms-tower__day-meta");
          const day = chip.querySelector(".foms-tower__day-dow");
          const count = chip.querySelector(".foms-tower__day-counts");
          const chipRect = chip.getBoundingClientRect();
          const dateRect = date.getBoundingClientRect();
          const metaRect = meta.getBoundingClientRect();
          const dayRect = day.getBoundingClientRect();
          const countRect = count.getBoundingClientRect();
          return {
            chipWidth: chipRect.width,
            chipHeight: chipRect.height,
            chipBottom: chipRect.bottom,
            dateTop: dateRect.top,
            metaTop: metaRect.top,
            dayBottom: dayRect.bottom,
            countBottom: countRect.bottom,
            metaDisplay: window.getComputedStyle(meta).display,
            countText: count.textContent.trim(),
            chipGridRows: window.getComputedStyle(chip).gridTemplateRows
          };
        }"""
    )


def _assert_compact_two_row_chip(metrics: dict[str, float | str]) -> None:
    assert 44 <= metrics["chipHeight"] <= 66
    assert metrics["chipWidth"] <= 84
    assert metrics["dateTop"] < metrics["metaTop"]
    assert metrics["dayBottom"] <= metrics["chipBottom"]
    assert metrics["countBottom"] <= metrics["chipBottom"]
    assert metrics["metaDisplay"] == "flex"
    assert "px" in metrics["chipGridRows"]


def test_measurement_mobile_date_chip_uses_compact_two_row_layout(
    page, visual_live_server_erp_v2
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    _login(page, visual_live_server_erp_v2)

    page.goto(f"{visual_live_server_erp_v2}/erp/measurement", wait_until="networkidle")

    _assert_compact_two_row_chip(
        _date_chip_metrics(page, ".erp-measurement-mobile-date-chip")
    )


def test_shipment_mobile_date_chip_uses_compact_two_row_layout(
    page, visual_live_server_erp_v2
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    _login(page, visual_live_server_erp_v2)

    page.goto(f"{visual_live_server_erp_v2}/erp/shipment", wait_until="networkidle")

    _assert_compact_two_row_chip(
        _date_chip_metrics(page, ".erp-shipment-mobile-date-chip")
    )


def test_dashboard_tower_day_tile_uses_compact_two_row_layout(
    page, visual_live_server_erp_v2
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    _login(page, visual_live_server_erp_v2)

    page.goto(f"{visual_live_server_erp_v2}/erp/dashboard", wait_until="networkidle")

    metrics = _tower_day_metrics(page)
    _assert_compact_two_row_chip(metrics)
    assert str(metrics["countText"]).isdigit()
