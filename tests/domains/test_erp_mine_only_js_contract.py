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
