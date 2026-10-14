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


def _tower_cal_cell_metrics(page) -> dict[str, float | str]:
    """월간 달력 날짜 칸(달 안 첫 칸): 날짜·건수·금액이 칸 밖으로 넘치지 않는지."""
    cell = page.locator(".foms-tower__cal-cell[data-iso]").first
    cell.wait_for()
    return cell.evaluate(
        """(cell) => {
          const date = cell.querySelector(".foms-tower__cal-date");
          const counts = cell.querySelector(".foms-tower__cal-counts");
          const cellRect = cell.getBoundingClientRect();
          let contentRight = cellRect.left;
          let contentBottom = cellRect.top;
          Array.from(cell.querySelectorAll(".foms-tower__cal-date, .foms-tower__cal-temp, .foms-tower__cal-n, .foms-tower__cal-amt")).forEach((el) => {
            const rect = el.getBoundingClientRect();
            contentRight = Math.max(contentRight, rect.right);
            contentBottom = Math.max(contentBottom, rect.bottom);
          });
          return {
            cellWidth: cellRect.width,
            cellHeight: cellRect.height,
            cellRight: cellRect.right,
            cellBottom: cellRect.bottom,
            contentRight,
            contentBottom,
            dateTop: date.getBoundingClientRect().top,
            countsTop: counts.getBoundingClientRect().top,
            gridColumns: window.getComputedStyle(cell.parentElement).gridTemplateColumns,
          };
        }"""
    )


def _assert_tower_cal_cell_contained(metrics: dict[str, float | str]) -> None:
    # 주마다 날씨 띠 한 줄 = 102px, 오늘 칸은 띠 위에 뜬 렌즈라 위아래 3px 더(108px). 2026-10-14 날씨 띠.
    assert 100 <= metrics["cellHeight"] <= 110
    assert metrics["cellWidth"] <= 60
    assert metrics["dateTop"] < metrics["countsTop"]
    assert metrics["contentRight"] <= metrics["cellRight"] + 0.5
    assert metrics["contentBottom"] <= metrics["cellBottom"] + 0.5
    assert len(str(metrics["gridColumns"]).split()) == 7


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


def test_dashboard_tower_calendar_cell_contains_counts(
    page, visual_live_server_erp_v2
) -> None:
    page.set_viewport_size({"width": 390, "height": 760})
    _login(page, visual_live_server_erp_v2)

    page.goto(f"{visual_live_server_erp_v2}/erp/dashboard", wait_until="networkidle")

    _assert_tower_cal_cell_contained(_tower_cal_cell_metrics(page))
