"""P1 mockup PNG gate — CSS class presence + optional Playwright hook."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

MOCKUP_CLASS_CONTRACTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "mobile-home-dashboard": (
        "templates/orders/partials/dashboard_mobile_v2_body.html",
        ("foms-shell-fab", "foms-mobile-v2-dashboard", "foms-mobile-queue-list", "dashboard_mobile_filter_sheet.html"),
    ),
    "mobile-order-detail": (
        "templates/orders/partials/order_detail_mobile_v2.html",
        ("foms-detail-hero", "foms-detail-section", "product-item", "foms-attach-grid"),
    ),
    "mobile-wizard-new-order": (
        "templates/orders/wizard/step2_products.html",
        ("foms-product-item", "data-foms-product-toggle", "foms-wizard__product-card"),
    ),
    "tablet-split-view": (
        "templates/partials/shared/foms_split_shell.html",
        ("foms-split-shell", "foms-split-detail", "data-foms-split-detail-kv"),
    ),
    "mobile-drawing-handoff": (
        "templates/drawing/partials/workbench_mobile_handoff.html",
        ("foms-drawing-handoff", "foms-drawing-sheet-list", "foms-drawing-handoff-detail", "foms-drawing-thread"),
    ),
}


@pytest.mark.parametrize(
    ("mockup_id", "rel_path", "classes"),
    [(mid, paths[0], paths[1]) for mid, paths in MOCKUP_CLASS_CONTRACTS.items()],
)
def test_p1_mockup_css_class_presence(mockup_id: str, rel_path: str, classes: tuple[str, ...]) -> None:
    """Key mockup CSS hooks exist in app templates before PNG baseline compare."""
    text = (ROOT / rel_path).read_text(encoding="utf-8")
    for cls in classes:
        assert cls in text, f"{mockup_id}: missing {cls} in {rel_path}"


@pytest.mark.skipif(
    os.getenv("FOMS_PLAYWRIGHT_BASELINE") != "1",
    reason="Playwright screenshot hook requires FOMS_PLAYWRIGHT_BASELINE=1",
)
def test_p1_mockup_playwright_screenshot_hook() -> None:
    """Optional screenshot gate — skipped unless Playwright env is configured."""
    pytest.importorskip("playwright")
    assert Path("docs/design/mockups/mobile-home-dashboard.html").is_file()
