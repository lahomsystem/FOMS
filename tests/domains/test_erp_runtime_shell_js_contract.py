"""EPT-B6: static checks for `static/js/erp/runtime-shell.js` (no JS runtime in CI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from foms.services.common import erp_navigation_contract as enc

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_SHELL = _REPO_ROOT / "static" / "js" / "erp" / "runtime-shell.js"


@pytest.fixture(scope="module")
def runtime_shell_src() -> str:
    assert _RUNTIME_SHELL.is_file(), f"missing {_RUNTIME_SHELL}"
    return _RUNTIME_SHELL.read_text(encoding="utf-8")


def test_runtime_shell_lists_match_python_fragment_ready(runtime_shell_src: str) -> None:
    """Client FRAGMENT_READY_PATHS array must match enc.ERP_FRAGMENT_READY_PATHS order and values."""
    for path in enc.ERP_FRAGMENT_READY_PATHS:
        assert f"'{path}'" in runtime_shell_src, path


def test_runtime_shell_subordinate_fragment_patterns(runtime_shell_src: str) -> None:
    """B6: subordinate shell-swap allowlist (B5 server contract) present."""
    assert "isSubordinateShellFragmentPath" in runtime_shell_src
    assert "/erp/shipment-settings" in runtime_shell_src
    assert "/erp/drawing-workbench/" in runtime_shell_src or "drawing-workbench" in runtime_shell_src
    assert r"^\/edit\/\d+$" in runtime_shell_src


def test_runtime_shell_excludes_map_view_prefetch(runtime_shell_src: str) -> None:
    """map_view is full-document-only; must not appear as a prefetch/swap target."""
    assert "map_view" not in runtime_shell_src


def test_runtime_shell_prefetch_warm_nav_hooks(runtime_shell_src: str) -> None:
    """B6: idle stagger, hover delegation, LRU cache, popstate restore."""
    assert "scheduleIdlePrimaryPrefetch" in runtime_shell_src
    assert "prefetchShellFragment" in runtime_shell_src
    assert "fragmentHtmlCache" in runtime_shell_src or "cachePut" in runtime_shell_src
    assert "popstate" in runtime_shell_src
    assert "fromPopState" in runtime_shell_src
    assert "scrollMemory" in runtime_shell_src


def test_runtime_shell_fragment_loading_overlay(runtime_shell_src: str) -> None:
    """UX: network fragment fetch shows loading overlay (not for cache-only swap)."""
    assert "setShellFragmentLoading" in runtime_shell_src
    assert "foms-erp-shell-loading-overlay" in runtime_shell_src
