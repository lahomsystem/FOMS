"""Visual regression for order list (/) — P0-00D."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.visual.conftest import (
    VISUAL_ADMIN_PASSWORD,
    VISUAL_ADMIN_USERNAME,
    compare_or_update_screenshot,
)

VISUAL_CASES = [
    pytest.param("orders_320_light.png", 320, 568, "light", id="320-light"),
    pytest.param("orders_320_dark.png", 320, 568, "dark", id="320-dark"),
    pytest.param("orders_390_light.png", 390, 844, "light", id="390-light"),
    pytest.param("orders_390_dark.png", 390, 844, "dark", id="390-dark"),
    pytest.param("orders_767_light.png", 767, 1024, "light", id="767-light"),
    pytest.param("orders_767_dark.png", 767, 1024, "dark", id="767-dark"),
]


def _login_and_open_orders(page, base_url: str) -> None:
    """Authenticate via /login POST flow then open order list at /."""
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.fill('input[name="username"]', VISUAL_ADMIN_USERNAME)
    page.fill('input[name="password"]', VISUAL_ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.goto(f"{base_url}/", wait_until="networkidle")


@pytest.mark.parametrize("baseline_name,width,height,theme", VISUAL_CASES)
def test_orders_page_visual_regression(
    page,
    visual_live_server,
    update_snapshots,
    baseline_name,
    width,
    height,
    theme,
    tmp_path: Path,
):
    """Capture order_pages.index (/) and compare to baseline PNG."""
    if theme == "dark":
        page.add_init_script(
            "document.documentElement.setAttribute('data-bs-theme', 'dark')"
        )
    page.set_viewport_size({"width": width, "height": height})
    page.emulate_media(reduced_motion="reduce")

    _login_and_open_orders(page, visual_live_server)

    capture_path = tmp_path / baseline_name
    page.screenshot(path=str(capture_path), full_page=True)

    ratio = compare_or_update_screenshot(
        capture_path,
        baseline_name,
        update_snapshots=update_snapshots,
    )
    assert ratio <= 0.001, f"{baseline_name}: diff ratio {ratio:.6f}"
