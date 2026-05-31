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


def test_legacy_layout_header_hidden_on_mobile_v2() -> None:
    """Bridge CSS hides .layout-header for the v2 cohort below 992px only."""
    css = _css("foundation/erp-pro/13-foms-shell-bridge.css")
    block = re.search(r"@media \(max-width: 991\.98px\) \{.*?\n\}", css, re.S)
    assert block, "expected a max-width:991.98px media block"
    assert "body.erp-mobile-v2-layout .layout-header" in block.group(0)
    # Desktop must keep the header: no unscoped/min-width hide of layout-header.
    assert ".layout-header" not in _css("foundation/erp-pro/13-foms-shell-bridge.css").split(
        "@media (min-width: 992px)"
    )[-1]


def test_split_detail_collapses_below_tablet() -> None:
    """foms-split-detail joins side-tab/master in the <=1023px hide rule."""
    css = _css("foundation/foms-split-view.css")
    block = re.search(r"@media \(max-width: 1023px\) \{.*?\n\}", css, re.S)
    assert block, "expected a max-width:1023px media block"
    body = block.group(0)
    for sel in (".foms-split-side-tab", ".foms-split-master", ".foms-split-detail"):
        assert sel in body, f"{sel} must be hidden below tablet breakpoint"


def test_drawer_exposes_account_actions() -> None:
    """Menu drawer keeps logout/profile reachable once header is hidden."""
    drawer = (
        ROOT / "templates/partials/shared/erp_mobile_menu_drawer.html"
    ).read_text(encoding="utf-8")
    assert "erp-mobile-menu-drawer__account" in drawer
    assert "auth.logout" in drawer
    assert "auth.profile" in drawer
