"""P1 mockup chrome parity — single shell header + collapsed split on mobile.

Static contract guards for the 2026-05-31 gap fix: when the ERP mobile v2 shell
is active the legacy global `layout-header` is hidden (mockup shows one shell
header), the tablet split detail pane collapses below 1024px (no
"좌측에서 주문을 선택하세요" leak on mobile), and account actions (logout) move
into the bottom menu drawer so nothing is stranded by hiding the header.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _css(rel: str) -> str:
    return (ROOT / "static/css" / rel).read_text(encoding="utf-8")


def test_legacy_layout_header_hidden_on_mobile_and_tablet() -> None:
    """Bridge CSS hides the legacy global header for the v2 cohort on mobile
    (≤991.98px) and the tablet split band (992–1365.98px); true desktop
    (≥1366px), where the legacy ERP dashboard renders, keeps it."""
    css = _css("foundation/erp-pro/13-foms-shell-bridge.css")
    mobile = re.search(r"@media \(max-width: 991\.98px\) \{.*?\n\}", css, re.S)
    assert mobile, "expected a max-width:991.98px media block"
    assert "body.erp-mobile-v2-layout .layout-header" in mobile.group(0)
    tablet = re.search(
        r"@media \(min-width: 992px\) and \(max-width: 1365\.98px\) \{.*?\n\}", css, re.S
    )
    assert tablet, "expected a tablet 992–1365.98px media block"
    assert "body.erp-mobile-v2-layout .layout-header" in tablet.group(0)
    # Desktop ≥1366px must keep the legacy header: no min-width:1366px hide here.
    assert "min-width: 1366px" not in css


def test_split_hidden_on_mobile_and_desktop() -> None:
    """3-tier (D03): the split renders only in the tablet band; it is hidden
    below 992px (mobile single-column queue) and at/above 1366px (legacy desktop
    ERP dashboard) so the two surfaces never double up."""
    css = _css("foundation/foms-split-view.css")
    hide = re.search(
        r"@media \(max-width: 991\.98px\), \(min-width: 1366px\) \{.*?\n\}",
        css,
        re.S,
    )
    assert hide, "expected combined mobile+desktop split hide media query"
    assert "body.erp-mobile-v2-layout .foms-split-enabled" in hide.group(0)


def test_tablet_split_grid_and_legacy_hidden() -> None:
    """Tablet band (992–1365.98px): the split grid (72/360/fluid) shows and the
    legacy desktop dashboard chrome is hidden."""
    css = _css("foundation/foms-split-view.css")
    grid = re.search(
        r"@media \(min-width: 992px\) and \(max-width: 1365\.98px\) \{"
        r".*?grid-template-columns: 72px 360px",
        css,
        re.S,
    )
    assert grid, "expected tablet split grid 72px 360px in the 992–1365.98px band"
    shell = _css("foundation/foms-shell.css")
    legacy = re.search(
        r"@media \(min-width: 992px\) and \(max-width: 1365\.98px\) \{"
        r".*?\.foms-shell-desktop-only.*?display: none !important",
        shell,
        re.S,
    )
    assert legacy, "tablet band must hide .foms-shell-desktop-only (legacy dashboard)"
    # Mobile single-column queue still hidden at >=992px.
    assert "body.erp-mobile-v2-layout .foms-mobile-v2-dashboard" in shell
    master = (ROOT / "templates/partials/shared/foms_master_list.html").read_text(
        encoding="utf-8"
    )
    for selector in (
        "foms-split-master__head",
        "foms-master-card__stage",
        "foms-master-card__subtitle",
    ):
        assert selector in master


def test_drawer_exposes_account_actions() -> None:
    """Menu drawer keeps logout/profile reachable once header is hidden."""
    drawer = (
        ROOT / "templates/partials/shared/erp_mobile_menu_drawer.html"
    ).read_text(encoding="utf-8")
    assert "erp-mobile-menu-drawer__account" in drawer
    assert "auth.logout" in drawer
    assert "auth.profile" in drawer


def test_wizard_suppresses_legacy_header_on_mobile() -> None:
    """New-order wizard (/add) hides legacy global header + nav below 992px.

    The wizard is a mobile-first focused flow with its own stepper header; the
    legacy global brand bar must not double up on mobile (mockup parity).
    """
    css = _css("foundation/erp-pro/13-foms-shell-bridge.css")
    block = re.search(r"@media \(max-width: 991\.98px\) \{.*?\n\}", css, re.S)
    assert block, "expected a max-width:991.98px media block"
    body = block.group(0)
    assert "body.foms-wizard-active .layout-header" in body
    assert "body.foms-wizard-active .layout-global-nav" in body
    layout = (ROOT / "templates/orders/layout.html").read_text(encoding="utf-8")
    assert "foms-wizard-active" in layout
    assert "order_pages.add_order" in layout
