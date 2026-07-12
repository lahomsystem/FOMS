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
    (≤991.98px) and every non-desktop shell (2026-07-12 목업 v5 정합): the split arm hides
    it on the narrow-desktop-window band (992–1365.98 fine/none, keyed on the split
    markup), the tablet-rail arm hides it on tablet landscape (≥992 landscape coarse,
    keyed on the rail), and the portrait-coarse arm hides it on tablet portrait. Only the
    true desktop (≥1366 fine/none), where the legacy ERP dashboard renders, keeps it."""
    css = _css("foundation/erp-pro/13-foms-shell-bridge.css")
    mobile = re.search(r"@media \(max-width: 991\.98px\) \{.*?\n\}", css, re.S)
    assert mobile, "expected a max-width:991.98px media block"
    assert "body.erp-mobile-v2-layout .layout-header" in mobile.group(0)
    # Split arm (fine/none 992–1365.98) hides the header when the split markup is present.
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: fine)" in css
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: none)" in css
    assert "body.erp-mobile-v2-layout:has(.foms-split-enabled) .layout-header" in css
    # Tablet-rail arm (coarse landscape ≥992) hides the header when the rail is present.
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in css
    assert "body:has(.foms-tablet-rail) .layout-header" in css
    # Tablet-portrait-coarse arm hides the header unconditionally (mobile interface).
    assert "(min-width: 992px) and (pointer: coarse) and (orientation: portrait)" in css
    # No bare/unconditional ≥1366 desktop hide: the true-desktop header must survive.
    assert "(min-width: 1366px) {" not in css


def test_split_hidden_on_mobile_and_desktop() -> None:
    """T0 (2026-07-10 shell-selection overhaul): the split is hidden by default and
    opted in only by the orientation+pointer matrix, so it never leaks onto the
    mobile queue (<992 / ≥992 portrait coarse) or the true desktop dashboard
    (≥1366 fine/none). The old unconditional `min-width: 1366px` hide is gone —
    ≥1366 landscape coarse is now a split surface."""
    css = _css("foundation/foms-split-view.css")
    # Flip: the base wrapper rule (the one carrying width:100%) is display:none.
    base = re.search(r"\.foms-split-enabled \{[^}]*width: 100%[^}]*\}", css, re.S)
    assert base is not None, "expected base .foms-split-enabled rule"
    assert "display: none" in base.group(0), "split wrapper must be hidden by default"
    # No bare unconditional min-width:1366px block (the matrix makes ≥1366 conditional).
    assert "(min-width: 1366px) {" not in css
    # Escape hatch: forcing desktop hides the split regardless of viewport.
    assert 'html[data-foms-shell="desktop"] .foms-split-enabled' in css


def test_tablet_split_grid_and_legacy_hidden() -> None:
    """Split band shows the 72/360/fluid grid — now selected by the pointer-aware matrix
    (fine / none 992–1365.98) rather than a bare width band or the old coarse-landscape
    arm — and the legacy desktop dashboard chrome is hidden in that same narrow-window
    band (2026-07-12 목업 v5 정합: coarse tablets keep the legacy PC grid + global rail
    instead of split)."""
    css = _css("foundation/foms-split-view.css")
    # Grid geometry lives on the base shell; the matrix query flips it to display:grid.
    assert "grid-template-columns: 72px 360px minmax(0, 1fr)" in css
    grid = re.search(
        r"@media\s+\(min-width: 992px\) and \(max-width: 1365\.98px\) and "
        r"\(pointer: fine\).*?\.foms-split-shell \{\s*display: grid;",
        css,
        re.S,
    )
    assert grid, "expected pointer-aware split-show query flipping the shell to display:grid"
    shell = _css("foundation/foms-shell.css")
    # The desktop-hide block mirrors the split-show query (fine/none 992–1365.98).
    # Anchor on the fine arm; the intent is unchanged (the split/tablet narrow window
    # still hides the legacy .foms-shell-desktop-only — only the coarse arms were dropped).
    legacy = re.search(
        r"@media\s+\(\(min-width: 992px\) and \(max-width: 1365\.98px\) and "
        r"\(pointer: fine\)\).*?\.foms-shell-desktop-only.*?display: none !important",
        shell,
        re.S,
    )
    assert legacy, "narrow window must hide .foms-shell-desktop-only (legacy dashboard)"
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
    assert "show_new_order_wizard" in layout
    processors = (ROOT / "foms/services/context_processors.py").read_text(encoding="utf-8")
    assert 'request.endpoint == "order_pages.add_order"' in processors
