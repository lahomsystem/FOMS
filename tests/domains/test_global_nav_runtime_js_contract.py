"""EPT: static checks for `static/js/global-nav-runtime.js` (G1-A warm swap + G2 prefetch)."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GLOBAL_NAV = _REPO_ROOT / "static" / "js" / "global-nav-runtime.js"


@pytest.fixture(scope="module")
def global_nav_src() -> str:
    assert _GLOBAL_NAV.is_file(), f"missing {_GLOBAL_NAV}"
    return _GLOBAL_NAV.read_text(encoding="utf-8")


def test_global_nav_g1_swap_contract(global_nav_src: str) -> None:
    """G1-A: intercept clicks, fetch fragment, swap #main-content; must not mirror ERP shell."""
    assert "preventDefault" in global_nav_src
    assert "#main-content" in global_nav_src or "main-content" in global_nav_src
    assert "X-FOMS-GNAV" in global_nav_src
    assert "X-FOMS-ERP-SHELL" not in global_nav_src


def test_global_nav_same_origin_guard(global_nav_src: str) -> None:
    assert "location.origin" in global_nav_src


def test_global_nav_prefetch_fallback_for_g2(global_nav_src: str) -> None:
    assert "'prefetch'" in global_nav_src or '"prefetch"' in global_nav_src
