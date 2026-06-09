"""Visual regression for ERP mobile v2 shell (/erp/dashboard) — P0-01."""

from __future__ import annotations

from pathlib import Path

import pytest

from db import db_session
from models import Order
from tests.visual.conftest import (
    VISUAL_ADMIN_PASSWORD,
    VISUAL_ADMIN_USERNAME,
    compare_or_update_screenshot,
)


@pytest.fixture(autouse=True)
def _erp_v2_visual_env(
    monkeypatch: pytest.MonkeyPatch, visual_cohort_user_id: str
) -> None:
    """Enable ERP mobile v2 cohort for dashboard captures."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", visual_cohort_user_id)


ERP_V2_VISUAL_CASES = [
    pytest.param("erp_v2_390_light.png", 390, 844, "light", id="390-light"),
    pytest.param("erp_v2_390_dark.png", 390, 844, "dark", id="390-dark"),
    pytest.param("erp_v2_768_light.png", 768, 1024, "light", id="768-light"),
    pytest.param("erp_v2_768_dark.png", 768, 1024, "dark", id="768-dark"),
    pytest.param("erp_v2_1280_light.png", 1280, 800, "light", id="1280-light"),
    pytest.param("erp_v2_1280_dark.png", 1280, 800, "dark", id="1280-dark"),
]


def _login_and_open_erp_dashboard(page, base_url: str) -> None:
    """Authenticate and open cohort-gated ERP dashboard."""
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.fill('input[name="username"]', VISUAL_ADMIN_USERNAME)
    page.fill('input[name="password"]', VISUAL_ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    page.goto(f"{base_url}/erp/dashboard", wait_until="networkidle")
    if "/login" in page.url:
        pytest.fail(f"Visual ERP login failed; still on {page.url}")


def _reset_dashboard_orders() -> None:
    """Keep ERP visual baselines independent from other visual smoke seeds."""
    db_session.query(Order).delete(synchronize_session=False)
    db_session.commit()


def _stabilize_page_for_screenshot(page) -> None:
    page.add_style_tag(
        content=(
            "@import url('https://fonts.googleapis.com/css2?"
            "family=Noto+Sans+KR:wght@400;500;700&display=swap');"
            "html, body { font-family: 'Noto Sans KR', sans-serif !important; }"
            "*, *::before, *::after {"
            " animation: none !important; transition: none !important;"
            "}"
        )
    )
    page.wait_for_function(
        "() => document.fonts && document.fonts.status === 'loaded'",
        timeout=15_000,
    )


@pytest.mark.parametrize("baseline_name,width,height,theme", ERP_V2_VISUAL_CASES)
def test_erp_mobile_v2_dashboard_visual_regression(
    page,
    visual_live_server_erp_v2,
    update_snapshots,
    baseline_name,
    width,
    height,
    theme,
    tmp_path: Path,
):
    """Capture /erp/dashboard with ERP_MOBILE_V2 cohort and compare baseline PNG."""
    if theme == "dark":
        page.add_init_script(
            "document.documentElement.setAttribute('data-theme', 'dark')"
        )
    page.set_viewport_size({"width": width, "height": height})
    page.emulate_media(reduced_motion="reduce")

    _reset_dashboard_orders()
    _login_and_open_erp_dashboard(page, visual_live_server_erp_v2)
    _stabilize_page_for_screenshot(page)

    body = page.locator("body")
    body_class = body.get_attribute("class") or ""
    assert "erp-mobile-v2-layout" in body_class

    capture_path = tmp_path / baseline_name
    page.screenshot(path=str(capture_path), full_page=True)

    compare_or_update_screenshot(
        capture_path,
        baseline_name,
        update_snapshots=update_snapshots,
    )
