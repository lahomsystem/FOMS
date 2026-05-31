"""Local asset existence for mobile v2 staging smoke (no live HTTP)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_ASSETS = (
    "static/css/foundation/foms-mobile-surfaces.css",
    "static/css/foundation/foms-shell.css",
    "static/js/foms/mobile-queue-scroll.js",
    "static/js/foms/wizard-attachments.js",
)


def test_staging_mobile_v2_assets_exist_locally() -> None:
    """P1 deploy assets must exist in repo for Railway static serving."""
    for rel in REQUIRED_ASSETS:
        path = ROOT / rel
        assert path.is_file(), f"missing asset: {rel}"


def test_foms_mobile_surfaces_bundle_imports_shell_css() -> None:
    """Mobile surfaces bundle must chain mockup CSS entrypoints."""
    bundle = (ROOT / "static/css/foundation/foms-mobile-surfaces.css").read_text(encoding="utf-8")
    assert "foms-shell.css" in bundle
    assert "foms-queue-card-v2.css" in bundle
