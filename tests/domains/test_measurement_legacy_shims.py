"""Regression tests for measurement static bundles (canonical paths only; legacy erp/* mirrors removed)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Canonical measurement JS entrypoints (must exist; no document.write).
CANONICAL_MEASUREMENT_JS: tuple[str, ...] = (
    "static/js/measurement/dashboard.js",
    "static/js/measurement/mobile.js",
    "static/js/measurement/dashboard-columns.js",
    "static/js/measurement/manual-rows.js",
    "static/js/measurement/image-export.js",
)


@pytest.mark.parametrize("rel", CANONICAL_MEASUREMENT_JS)
def test_canonical_measurement_js_has_no_document_write(rel: str) -> None:
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "document.write" not in text, f"{rel} must not use document.write"


def test_legacy_erp_measurement_mirror_paths_absent() -> None:
    """§2.2.1: no static/js/erp/* measurement shims (canonical is under js/measurement/)."""
    legacy = REPO_ROOT / "static/js/erp"
    assert not legacy.exists(), "static/js/erp/ must not exist after canonical asset tree migration"


def test_legacy_root_measurement_image_export_shim_absent() -> None:
    assert not (REPO_ROOT / "static/js/measurement-image-export.js").exists()
