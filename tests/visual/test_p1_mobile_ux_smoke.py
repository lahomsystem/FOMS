"""P1 mobile/tablet UX smoke (Playwright) — gate UX actual confirmation."""

from __future__ import annotations

import pytest

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
        assert page.locator('[data-foms-mobile-filter-open]').count() >= 1
        assert page.locator(".erp-mobile-shell-chrome").count() >= 1
        page.locator('[data-foms-search-open]').first.click()
        assert page.locator("#foms-search-overlay").is_visible()


def test_p1_wizard_shell_smoke(page, visual_live_server_erp_v2) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, visual_live_server_erp_v2)
    page.goto(f"{visual_live_server_erp_v2}/add", wait_until="networkidle")
    if "/login" in page.url:
        pytest.fail(f"Wizard smoke login failed; still on {page.url}")
    assert page.locator("#foms-wizard-root").count() == 1
    assert page.locator('[data-wizard-step="1"]').count() >= 1
