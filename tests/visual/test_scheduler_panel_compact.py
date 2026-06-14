"""Legacy scheduler side-panel geometry smoke."""

from __future__ import annotations

from tests.visual.conftest import VISUAL_ADMIN_PASSWORD, VISUAL_ADMIN_USERNAME


def _login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.fill('input[name="username"]', VISUAL_ADMIN_USERNAME)
    page.fill('input[name="password"]', VISUAL_ADMIN_PASSWORD)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")


def _scheduler_metrics(page, selector: str) -> dict[str, float]:
    return page.locator(selector).first.evaluate(
        """(item) => {
          const row = item.querySelector('.erp-scheduler-panel-row');
          const badge = item.querySelector('.erp-scheduler-count');
          const list = item.closest('.measurement-panel-list');
          const parts = Array.from(row.children);
          const prev = parts[parts.length - 2];
          const itemRect = item.getBoundingClientRect();
          const rowRect = row.getBoundingClientRect();
          const prevRect = prev.getBoundingClientRect();
          const badgeRect = badge.getBoundingClientRect();
          const listRect = list.getBoundingClientRect();
          return {
            itemWidth: itemRect.width,
            rowWidth: rowRect.width,
            badgeGap: badgeRect.left - prevRect.right,
            badgeRight: badgeRect.right,
            itemRight: itemRect.right,
            listRight: listRect.right
          };
        }"""
    )


def _assert_compact(metrics: dict[str, float]) -> None:
    assert metrics["itemWidth"] <= 250
    assert metrics["rowWidth"] <= metrics["itemWidth"] - 8
    assert metrics["badgeGap"] >= 16
    assert abs(metrics["itemRight"] - metrics["badgeRight"]) <= 8
    assert metrics["badgeRight"] <= metrics["listRight"] - 4


def test_legacy_measurement_scheduler_panel_stays_compact(
    page, visual_live_server_legacy, monkeypatch
) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    page.set_viewport_size({"width": 482, "height": 680})
    _login(page, visual_live_server_legacy)

    page.goto(f"{visual_live_server_legacy}/erp/measurement", wait_until="networkidle")
    _assert_compact(_scheduler_metrics(page, ".measurement-panel-item-oneline"))


def test_legacy_shipment_scheduler_panel_stays_compact(
    page, visual_live_server_legacy, monkeypatch
) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    page.set_viewport_size({"width": 482, "height": 680})
    _login(page, visual_live_server_legacy)

    page.goto(f"{visual_live_server_legacy}/erp/shipment", wait_until="networkidle")
    _assert_compact(_scheduler_metrics(page, ".measurement-panel-item-oneline"))

    remaining = page.locator(".remaining-panel-table").first.evaluate(
        """(panel) => {
          const schedulerCard = document.querySelector('.erp-shipment-scheduler-col .erp-scheduler-card');
          const remainingCard = panel.closest('.erp-scheduler-card');
          const schedulerRect = schedulerCard.getBoundingClientRect();
          const remainingRect = remainingCard.getBoundingClientRect();
          const panelRect = panel.getBoundingClientRect();
          const firstRow = panel.querySelector('tbody tr:first-child');
          const dateCell = firstRow.querySelector('td:first-child');
          const firstBadge = firstRow.querySelector('td:last-child .badge:first-child');
          const lastBadge = firstRow.querySelector('td:last-child .badge:last-child');
          const dateRect = dateCell.getBoundingClientRect();
          const firstBadgeRect = firstBadge.getBoundingClientRect();
          const badgeRect = lastBadge.getBoundingClientRect();
          return {
            schedulerCardWidth: schedulerRect.width,
            remainingCardWidth: remainingRect.width,
            badgeGap: firstBadgeRect.left - dateRect.right,
            badgeRight: badgeRect.right,
            panelRight: panelRect.right
          };
        }"""
    )
    assert abs(remaining["schedulerCardWidth"] - remaining["remainingCardWidth"]) <= 1
    assert remaining["badgeGap"] <= 80
    assert remaining["badgeRight"] <= remaining["panelRight"] - 4
