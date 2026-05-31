"""Mockup HTML ↔ app template class parity gate (PNG baseline precursor)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOCKUPS = ROOT / "docs/design/mockups"


def _extract_classes(html: str) -> set[str]:
    return set(re.findall(r'class="([^"]+)"', html))


def _flatten_classes(class_attr: str) -> set[str]:
    out: set[str] = set()
    for chunk in class_attr.split('"'):
        for token in chunk.split():
            if token.strip():
                out.add(token.strip())
    return out


def _required_from_mockup(filename: str, needles: tuple[str, ...]) -> None:
    mockup = (MOCKUPS / filename).read_text(encoding="utf-8")
    classes: set[str] = set()
    for match in re.finditer(r'class="([^"]+)"', mockup):
        classes |= _flatten_classes(match.group(1))
    missing = [n for n in needles if n not in mockup and n not in classes]
    assert not missing, f"{filename} missing mockup anchors: {missing}"


def test_mockup_home_dashboard_anchor_classes() -> None:
    """Home mockup retains §6.2 IA anchors referenced by app templates."""
    body = (ROOT / "templates/orders/partials/dashboard_mobile_v2_body.html").read_text(encoding="utf-8")
    _required_from_mockup(
        "mobile-home-dashboard.html",
        ("chip-strip", "queue-card", "foms-shell-fab"),
    )
    for needle in ("today=1", "sort=amount", "data-foms-mobile-queue-chunk"):
        assert needle in body


def test_mockup_order_detail_anchor_classes() -> None:
    """Detail mockup §6.2 four-section IA reflected in mobile v2 partial."""
    body = (ROOT / "templates/orders/partials/order_detail_mobile_v2.html").read_text(encoding="utf-8")
    _required_from_mockup(
        "mobile-order-detail.html",
        ("detail-hero", "quick-actions", "product-item", "attach-grid"),
    )
    for section in ("foms-detail-customer-title", "foms-detail-schedule-title", "foms-detail-amount-title"):
        assert section in body


def test_mockup_wizard_and_split_anchors_on_disk() -> None:
    """Wizard + tablet mockups remain SSOT anchors for structure tests."""
    wizard = (MOCKUPS / "mobile-wizard-new-order.html").read_text(encoding="utf-8")
    split = (MOCKUPS / "tablet-split-view.html").read_text(encoding="utf-8")
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    split_shell = (ROOT / "templates/partials/shared/foms_split_shell.html").read_text(encoding="utf-8")
    assert "wizard" in wizard.lower() and "foms-wizard-root" in shell
    assert "master-list" in split and "foms-split-shell" in split_shell
    assert "wizard-attachments.js" in shell
    assert "product-item.js" in shell
