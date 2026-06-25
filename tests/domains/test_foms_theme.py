"""P0-07: FOMS theme tokens, head bootstrap, drawer toggle."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_foms_tokens_css_defines_light_and_dark_surfaces():
    css = _read("static/css/foundation/foms-tokens.css")
    assert ":root" in css
    assert "[data-theme='dark']" in css
    assert "--foms-surface-base:" in css
    assert "--foms-text-primary:" in css


def test_theme_js_storage_and_api():
    js = _read("static/js/foms/theme.js")
    assert "foms-theme" in js
    assert "FomsTheme" in js
    assert "localStorage.setItem" in js
    assert "prefers-color-scheme" in js
    assert "data-foms-theme-option" in js
    assert "data-bs-theme" in js


def test_layout_head_fouc_bootstrap_and_token_stylesheets():
    head = _read("templates/partials/shared/layout_head.html")
    assert "localStorage.getItem(key)" in head or "localStorage.getItem('foms-theme')" in head
    assert "data-theme" in head
    assert "data-bs-theme" in head
    assert "foms-tokens.css" in head
    assert head.index("foms-tokens.css") < head.index("erp-pro.css")


def test_erp_mobile_drawer_includes_theme_toggle():
    drawer = _read("templates/partials/shared/erp_mobile_menu_drawer.html")
    assert "foms_theme_toggle.html" in drawer


def test_foms_theme_toggle_partial_markup():
    partial = _read("templates/partials/shared/foms_theme_toggle.html")
    assert 'data-foms-theme-option="light"' in partial
    assert 'data-foms-theme-option="dark"' in partial
    assert 'data-foms-theme-option="system"' in partial


def test_layout_scripts_loads_theme_js():
    scripts = _read("templates/partials/shared/layout_scripts.html")
    assert "js/foms/theme.js" in scripts


def test_erp_tokens_bridge_to_foms_semantics():
    css = _read("static/css/foundation/erp-pro/01-intro-tokens.css")
    assert "--erp-bg-card: var(--foms-surface-base)" in css
    assert "--erp-text-primary: var(--foms-text-primary)" in css


def test_foms_tokens_define_surface_subtle_and_muted():
    css = _read("static/css/foundation/foms-tokens.css")
    assert "--foms-surface-subtle:" in css
    assert "--foms-surface-muted:" in css
    assert "--bg-app: var(--foms-surface-overlay)" in css
    css = _read("static/css/components/foms-sticky-action-bar.css")
    assert "var(--foms-surface-base)" in css
    assert "var(--foms-border-subtle)" in css


def test_foms_tokens_define_chip_and_primary_soft():
    css = _read("static/css/foundation/foms-tokens.css")
    assert "--foms-interactive-primary-soft:" in css
    assert "--foms-chip-date-selected-bg:" in css
    assert "--foms-chip-badge-bg:" in css


def test_inline_error_pages_support_dark_theme():
    http_py = _read("foms/platform/http.py")
    assert "data-theme='dark'" in http_py or "data-theme','dark'" in http_py
    assert "foms-theme" in http_py
    assert "--err-page-bg" in http_py


def test_mobile_print_utilities_documents_p0_07_theme():
    css = _read("static/css/foundation/erp-pro/06-mobile-print-utilities.css")
    assert "foms-tokens.css" in css
    assert "theme.js" in css
