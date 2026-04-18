"""Static contract for shared nav loading feedback UX."""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_GLOBAL_NAV_RUNTIME = _REPO_ROOT / "static" / "js" / "global-nav-runtime.js"
_LAYOUT_HEAD = _REPO_ROOT / "templates" / "partials" / "shared" / "layout_head.html"
_LAYOUT_NAV = _REPO_ROOT / "templates" / "partials" / "shared" / "layout_nav.html"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def test_global_nav_runtime_sets_and_clears_loading_state() -> None:
    src = _read(_GLOBAL_NAV_RUNTIME)

    assert "is-nav-loading" in src
    assert "aria-busy" in src
    assert "layout-nav-loading-status" in src
    assert "pageshow" in src
    assert "isSameOriginDocumentHref" in src


def test_shared_layout_nav_exposes_live_region() -> None:
    src = _read(_LAYOUT_NAV)

    assert 'id="layout-nav-loading-status"' in src
    assert 'aria-live="polite"' in src
    assert 'aria-atomic="true"' in src


def test_shared_layout_head_contains_visual_loading_feedback_rules() -> None:
    src = _read(_LAYOUT_HEAD)

    assert "layoutNavLoadingSlide" in src
    assert ".layout-global-nav::after" in src
    assert ".is-nav-loading-target::after" in src
