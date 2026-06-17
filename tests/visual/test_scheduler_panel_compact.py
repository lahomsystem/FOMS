"""Legacy scheduler side-panel geometry smoke."""

from __future__ import annotations

import datetime
import os

import pytest

from db import db_session
from models import Order
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
            rowRight: rowRect.right,
            badgeGap: badgeRect.left - prevRect.right,
            badgeRight: badgeRect.right,
            itemRight: itemRect.right,
            listRight: listRect.right
          };
        }"""
    )


def _assert_badge_not_clipped(metrics: dict[str, float]) -> None:
    """건수 뱃지가 스크롤 영역 안에 완전히 들어오는지 확인."""
    assert metrics["badgeRight"] <= metrics["listRight"] - 4
    assert abs(metrics["rowRight"] - metrics["badgeRight"]) <= 4


def _assert_compact(metrics: dict[str, float], *, max_item_width: float = 250) -> None:
    assert metrics["itemWidth"] <= max_item_width
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
    _assert_compact(_scheduler_metrics(page, ".measurement-panel-item-oneline"), max_item_width=285)


def test_legacy_shipment_scheduler_panel_stays_compact(
    page, visual_live_server_legacy, monkeypatch
) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    page.set_viewport_size({"width": 482, "height": 680})
    _login(page, visual_live_server_legacy)

    page.goto(f"{visual_live_server_legacy}/erp/shipment", wait_until="networkidle")
    _assert_compact(
        _scheduler_metrics(page, ".measurement-panel-item-oneline"),
        max_item_width=285,
    )

    remaining = page.locator(".remaining-panel-table").first.evaluate(
        """(panel) => {
          const schedulerCard = document.querySelector('.erp-shipment-scheduler-col .erp-scheduler-card');
          const remainingCard = panel.closest('.erp-scheduler-card');
          const schedulerRect = schedulerCard.getBoundingClientRect();
          const remainingRect = remainingCard.getBoundingClientRect();
          const panelRect = panel.getBoundingClientRect();
          const firstRow = panel.querySelector('tbody tr:first-child');
          const dateCell = firstRow.querySelector('td:first-child');
          const dateText = firstRow.querySelector('.remaining-panel-date');
          const firstBadge = firstRow.querySelector('td:last-child .badge:first-child');
          const lastBadge = firstRow.querySelector('td:last-child .badge:last-child');
          const dateRect = dateCell.getBoundingClientRect();
          const dateTextRect = dateText.getBoundingClientRect();
          const firstBadgeRect = firstBadge.getBoundingClientRect();
          const badgeRect = lastBadge.getBoundingClientRect();
          return {
            schedulerCardWidth: schedulerRect.width,
            remainingCardWidth: remainingRect.width,
            dateCellWhiteSpace: window.getComputedStyle(dateCell).whiteSpace,
            dateTextWidth: dateTextRect.width,
            dateCellWidth: dateRect.width,
            badgeGap: firstBadgeRect.left - dateRect.right,
            badgeRight: badgeRect.right,
            panelRight: panelRect.right
          };
        }"""
    )
    assert abs(remaining["schedulerCardWidth"] - remaining["remainingCardWidth"]) <= 1
    assert remaining["dateCellWhiteSpace"] == "nowrap"
    assert remaining["dateTextWidth"] < remaining["dateCellWidth"]
    assert remaining["badgeGap"] <= 80
    assert remaining["badgeRight"] <= remaining["panelRight"] - 4


@pytest.mark.skipif(
    "sqlite:///tests/visual/" not in os.environ.get("DATABASE_URL", "").replace("\\", "/"),
    reason="Playwright scheduler smoke requires DATABASE_URL=sqlite:///tests/visual/visual_local.sqlite",
)
def test_erp_order_measurement_panel_count_badge_not_clipped(
    page,
    visual_live_server_legacy,
    monkeypatch,
) -> None:
    """PC ERP Order 실측 일정 패널 건수 뱃지가 스크롤바에 가려지지 않는다."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "false")
    measurement_date = datetime.date.today().isoformat()
    order = Order(
        received_date=measurement_date,
        customer_name="실측패널 검증",
        phone="010-1111-2222",
        address="서울시 패널테스트",
        product="테스트",
        is_erp_order=True,
        measurement_date=measurement_date,
        structured_data={
            "parties": {"customer": {"name": "실측패널 검증"}},
            "site": {"address_full": "서울시 패널테스트"},
            "schedule": {"measurement": {"date": measurement_date}},
        },
    )
    db_session.add(order)
    db_session.commit()

    page.set_viewport_size({"width": 1280, "height": 900})
    _login(page, visual_live_server_legacy)
    page.goto(
        f"{visual_live_server_legacy}/edit/{order.id}?open=erp-order",
        wait_until="networkidle",
    )
    page.wait_for_selector(
        "#erp-order-measurement-panel .measurement-panel-item-oneline .erp-scheduler-count"
    )
    metrics = _scheduler_metrics(
        page, "#erp-order-measurement-panel .measurement-panel-item-oneline"
    )
    _assert_badge_not_clipped(metrics)
    assert metrics["itemWidth"] <= 320
