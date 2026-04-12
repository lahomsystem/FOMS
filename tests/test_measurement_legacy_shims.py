"""Regression tests for legacy measurement static URL shims (no document.write; body mirrors canonical)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# (legacy_path relative to repo, canonical path relative to repo)
LEGACY_SHIM_PAIRS: tuple[tuple[str, str], ...] = (
    ("static/js/erp/measurement.js", "static/js/measurement/dashboard.js"),
    ("static/js/erp/measurement-mobile.js", "static/js/measurement/mobile.js"),
    (
        "static/js/erp/measurement-dashboard-columns.js",
        "static/js/measurement/dashboard-columns.js",
    ),
    ("static/js/erp/measurement-manual-rows.js", "static/js/measurement/manual-rows.js"),
    ("static/js/measurement-image-export.js", "static/js/measurement/image-export.js"),
)


def _strip_legacy_shim_header(source: str) -> str:
    """Remove leading blank lines and consecutive full-line // comments (shim header only)."""
    lines = source.splitlines(keepends=True)
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith("//"):
            i += 1
            continue
        break
    while i < len(lines) and not lines[i].strip():
        i += 1
    return "".join(lines[i:])


@pytest.mark.parametrize("legacy_rel,canonical_rel", LEGACY_SHIM_PAIRS)
def test_legacy_shim_has_no_document_write(legacy_rel: str, canonical_rel: str) -> None:
    del canonical_rel
    text = (REPO_ROOT / legacy_rel).read_text(encoding="utf-8")
    assert "document.write" not in text, f"{legacy_rel} must not use document.write"


@pytest.mark.parametrize("legacy_rel,canonical_rel", LEGACY_SHIM_PAIRS)
def test_legacy_shim_body_matches_canonical(legacy_rel: str, canonical_rel: str) -> None:
    legacy_text = (REPO_ROOT / legacy_rel).read_text(encoding="utf-8")
    canonical_text = (REPO_ROOT / canonical_rel).read_text(encoding="utf-8")
    body = _strip_legacy_shim_header(legacy_text)
    assert body == canonical_text, (
        f"{legacy_rel} body after stripping // header must equal {canonical_rel}"
    )
