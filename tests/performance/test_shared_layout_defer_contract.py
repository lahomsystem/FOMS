"""Shared layout script loading contracts for the performance guard."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAYOUT_HEAD = ROOT / "templates" / "partials" / "shared" / "layout_head.html"
LAYOUT_SCRIPTS = ROOT / "templates" / "partials" / "shared" / "layout_scripts.html"
PERF_GUARD = ROOT / "tests" / "performance" / "test_perf_regression_guard.py"

SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(.*?)\1[^>]*>", re.I | re.S)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _script_tag_containing(html: str, needle: str) -> str:
    for match in SCRIPT_TAG_RE.finditer(html):
        tag = match.group(0)
        if needle in tag:
            return tag
    raise AssertionError(f"script tag not found: {needle}")


def _assert_deferred(html: str, needle: str) -> None:
    tag = _script_tag_containing(html, needle)
    assert re.search(r"\bdefer\b", tag), tag


def test_socketio_loader_is_deferred_without_breaking_inline_init_order() -> None:
    head = _read(LAYOUT_HEAD)
    init_js = _read(ROOT / "static/js/runtime/layout-head-init.js")

    _assert_deferred(head, "socket.io.min.js")
    assert 'id="global-socketio-loader"' in head
    assert "function initGlobalSocketIO()" in head
    assert "js/runtime/layout-head-init.js" not in head
    assert "function initGlobalSocketIO()" in init_js
    assert "loader.addEventListener('load', initGlobalSocketIO" in init_js
    assert "window.__globalSocketInitialized" in init_js


def test_safe_shared_layout_scripts_are_deferred() -> None:
    scripts = _read(LAYOUT_SCRIPTS)
    deferred_scripts = [
        "bootstrap.bundle.min.js",
        "js/foms/photo-capture.js",
        "js/foms/visual-viewport.js",
        "js/foms/theme.js",
        "js/foms/rum-baseline.js",
        "js/runtime/script.js",
        "js/runtime/upload-progress.js",
        "cdn.jsdelivr.net/npm/flatpickr",
        "cdn.jsdelivr.net/npm/flatpickr/dist/l10n/ko.js",
    ]

    for needle in deferred_scripts:
        _assert_deferred(scripts, needle)

    assert "layout-shared.bundle.js" not in scripts


def test_deferred_scripts_are_removed_from_sync_allowlist() -> None:
    guard = _read(PERF_GUARD)
    retired_sync_keys = [
        "cdn:bootstrap.bundle.min.js",
        "cdn:flatpickr",
        "cdn:ko.js",
        "cdn:socket.io.min.js",
        "photo-capture.js",
        "rum-baseline.js",
        "script.js",
        "theme.js",
        "upload-progress.js",
        "visual-viewport.js",
    ]

    for key in retired_sync_keys:
        assert key not in guard
