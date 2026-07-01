"""Static contract checks for erp-mine-only.js."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MINE_JS = _REPO_ROOT / "static" / "js" / "foms" / "erp-mine-only.js"


def test_erp_mine_only_js_exports_api():
    src = _MINE_JS.read_text(encoding="utf-8")
    assert "window.FOMS_ERP_MINE_ONLY" in src
    assert "decorateShellUrl" in src
    assert "foms:erp-mine-only-changed" in src
    assert "window.location.reload" not in src


def test_erp_mine_only_js_hooks_shell_navigation():
    src = _MINE_JS.read_text(encoding="utf-8")
    assert "navigateByShell" in src
    assert "prefetchShellFragment" in src
    assert "_mineHookInstalled" in src


def test_erp_mine_only_js_mytasks_toggle_not_double_handled():
    """Mytasks href encodes the *target* state; anchor sync must not race the toggle click."""
    src = _MINE_JS.read_text(encoding="utf-8")
    anchor_sync = src.split("function onAnchorMineSync")[1].split("function onMytasksClick")[0]
    assert "data-foms-mytasks-toggle" in anchor_sync
    assert "__FOMS_ERP_MINE_ONLY_BOOTED" in src
