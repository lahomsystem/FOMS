"""P1 mobile/tablet UX smoke (Playwright) — gate UX actual confirmation."""

from __future__ import annotations

from datetime import date

import pytest

from db import db_session
from models import Order
from tests.visual.conftest import VISUAL_ADMIN_PASSWORD, VISUAL_ADMIN_USERNAME


@pytest.fixture(autouse=True)
def _p1_all_flags(monkeypatch: pytest.MonkeyPatch, visual_cohort_user_id: str) -> None:
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", visual_cohort_user_id)
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    monkeypatch.setenv("FOMS_INLINE_EDIT_ENABLED", "true")
    monkeypatch.setenv("FOMS_TABLET_SPLIT_VIEW_ENABLED", "true")


def _login(page, base_url: str) -> None:
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.fill('input[name="username"]', VISUAL_ADMIN_USERNAME)
    page.fill('input[name="password"]', VISUAL_ADMIN_PASSWORD)
    page.locator('button[type="submit"]').click()
    page.wait_for_load_state("networkidle")
    if "/login" in page.url:
        page.goto(f"{base_url}/erp/dashboard", wait_until="networkidle")


def _seed_drawing_order() -> Order:
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"),
        customer_name="모바일 도면 QA",
        phone="010-9999-0000",
        address="Seoul",
        product="문지영",
        status="DRAWING",
        manager_name="최상용",
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {"name": "모바일 도면 QA"},
                "manager": {"name": "최상용"},
            },
            "workflow": {"stage": "DRAWING"},
            "drawing": {"status": "TRANSFERRED"},
            "drawing_status": "TRANSFERRED",
            "drawing_current_files": [
                {
                    "key": "drawings/mobile-qa.png",
                    "filename": "mobile-qa.png",
                    "view_url": "/static/images/lahom-logo.png",
                }
            ],
            "drawing_transfer_history": [
                {
                    "action": "TRANSFER",
                    "at": "2026-06-09 10:00:00",
                    "by_user_name": "도면팀",
                    "note": "도면 1차 전달",
                    "files": [],
                }
            ],
            "drawing_assignees": [],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


@pytest.mark.parametrize("width,height", [(390, 844), (1280, 800)])
def test_p1_mobile_tablet_ux_smoke(page, visual_live_server_erp_v2, width, height) -> None:
    """Smoke: search overlay, split shell, nav badges wiring on dashboard."""
    page.set_viewport_size({"width": width, "height": height})
    _login(page, visual_live_server_erp_v2)
    page.goto(f"{visual_live_server_erp_v2}/erp/dashboard")
    page.wait_for_load_state("networkidle")

    assert page.locator('[data-foms-split-shell]').count() >= 1

    if width >= 1024:
        assert page.locator(".foms-split-side-tab").count() >= 1
        assert page.locator(".foms-split-master").count() >= 1
    else:
        assert page.locator('[data-foms-search-open]').count() >= 1
        assert page.locator(".erp-mobile-shell-chrome").count() >= 1
        assert page.locator('[data-foms-tower]').count() >= 1
        page.locator('[data-foms-search-open]').first.click()
        assert page.locator("#foms-search-overlay").is_visible()

        page.goto(f"{visual_live_server_erp_v2}/erp/dashboard?view=queue")
        page.wait_for_load_state("networkidle")
        assert page.locator('[data-foms-mobile-filter-open]').count() >= 1


def test_p1_wizard_shell_smoke(page, visual_live_server_erp_v2) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, visual_live_server_erp_v2)
    page.goto(f"{visual_live_server_erp_v2}/add", wait_until="networkidle")
    if "/login" in page.url:
        pytest.fail(f"Wizard smoke login failed; still on {page.url}")
    assert page.locator("#foms-wizard-root").count() == 1
    assert page.locator('[data-wizard-step="1"]').count() >= 1


def test_p1_drawing_mobile_queue_smoke(page, visual_live_server_erp_v2) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    _seed_drawing_order()
    _login(page, visual_live_server_erp_v2)

    page.goto(f"{visual_live_server_erp_v2}/erp/dashboard", wait_until="networkidle")
    page.get_by_role("button", name="더보기 메뉴").click()
    page.locator('a.erp-mobile-menu-drawer__link[href="/erp/drawing-workbench"]').click()
    page.wait_for_load_state("networkidle")

    assert page.locator(".foms-drawing-mobile-dashboard").is_visible()
    assert page.locator(".foms-mobile-queue-list").is_visible()
    assert page.locator(".foms-drawing-queue-card").count() >= 1
    assert page.locator(".foms-drawing-mobile-v2").count() == 0
    assert page.locator(".erp-drawing-dashboard-desktop-card").is_hidden()
    metrics = page.locator(".foms-drawing-queue-card").first.evaluate(
        """card => {
          const grid = card.querySelector('.foms-drawing-queue-card__grid');
          const thumb = card.querySelector('.foms-drawing-queue-card__thumb');
          const gridStyle = window.getComputedStyle(grid);
          const thumbRect = thumb.getBoundingClientRect();
          return {
            display: gridStyle.display,
            columns: gridStyle.gridTemplateColumns,
            thumbWidth: Math.round(thumbRect.width),
            thumbHeight: Math.round(thumbRect.height),
            cardWidth: Math.round(card.getBoundingClientRect().width),
          };
        }"""
    )
    assert metrics["display"] == "grid"
    assert metrics["thumbWidth"] <= 90
    assert metrics["thumbHeight"] <= 90
    assert metrics["cardWidth"] > metrics["thumbWidth"] * 2
    assert not any("Identifier 'TEAM_LABELS'" in error for error in errors)
