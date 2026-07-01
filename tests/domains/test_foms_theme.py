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
    theme_boot = _read("static/js/runtime/foms-theme-boot.js")
    assert "foms-theme-boot.js" in head
    assert "localStorage.getItem(key)" in theme_boot or "localStorage.getItem('foms-theme')" in theme_boot
    assert "data-theme" in theme_boot
    assert "data-bs-theme" in theme_boot
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


def test_mobile_fixed_overlays_outside_shell_chrome():
    shell = _read("templates/partials/shared/foms_app_shell.html")
    chrome_close = shell.index("</div>", shell.index("erp-mobile-shell-chrome"))
    drawer_pos = shell.index("erp_mobile_menu_drawer.html")
    search_pos = shell.index("foms_search_overlay.html")
    assert drawer_pos > chrome_close
    assert search_pos > chrome_close
    assert "display:contents" in shell


def test_foms_z_menu_drawer_token():
    css = _read("static/css/foundation/foms-tokens.css")
    assert "--foms-z-menu-drawer:" in css
    mobile = _read("static/css/foundation/erp-pro/10-erp-mobile-v2-shell.css")
    assert "--foms-z-menu-drawer" in mobile
    assert "#erp-mobile-menu-drawer.offcanvas.show" in mobile


def test_theme_js_document_delegation_and_htmx_resync():
    js = _read("static/js/foms/theme.js")
    assert "__FOMS_THEME_CLICK_BOUND" in js
    assert "bindThemeClickDelegation" in js
    assert "document.addEventListener('click'" in js
    assert "foms:main-content-swapped" in js
    assert "shown.bs.offcanvas" in js
    assert "bindToggles" not in js


def test_theme_js_scopes_dark_to_mobile_viewport_only():
    js = _read("static/js/foms/theme.js")
    assert "MOBILE_THEME_MQ" in js
    assert "isMobileThemeViewport" in js
    assert "resolveAppliedTheme" in js
    assert "return 'light'" in js
    assert "__FOMS_THEME_VIEWPORT_BOUND" in js
    assert "bindViewportThemeListener" in js


def test_layout_head_fouc_forces_light_on_desktop_viewport():
    theme_boot = _read("static/js/runtime/foms-theme-boot.js")
    assert "max-width: 991.98px" in theme_boot.split("localStorage.getItem(key)")[1].split("data-theme")[0]
    assert ": 'light'" in theme_boot.split("localStorage.getItem(key)")[1].split("data-theme")[0]


def test_layout_head_desktop_chrome_dark_rules_are_mobile_scoped():
    head = _read("templates/partials/shared/layout_head.html")
    block = head.split("[data-theme='dark'] .layout-global-nav")[0]
    assert "@media (max-width: 991.98px)" in block[-400:]
    assert head.index("@media (max-width: 991.98px)") < head.index(
        "[data-theme='dark'] .layout-global-nav"
    )


def test_search_overlay_closed_does_not_capture_pointer():
    css = _read("static/css/components/foms-search-overlay.css")
    assert ".foms-search-overlay:not([open])" in css
    assert "pointer-events: none" in css


def test_flatpickr_dark_theme_follows_foms_tokens():
    css = _read("static/css/components/foms-flatpickr-theme.css")
    assert "[data-theme='dark'] .flatpickr-calendar" in css
    assert "var(--foms-surface-base)" in css
    head = _read("templates/partials/shared/layout_head.html")
    assert "foms-flatpickr-theme.css" in head


def test_completion_mobile_css_uses_semantic_tokens_not_inline_hex():
    partial = _read("templates/cs/partials/completion_styles.html")
    assert "foms-completion-mobile.css" in partial
    assert "<style>" not in partial
    css = _read("static/css/components/foms-completion-mobile.css")
    assert "var(--foms-surface-base)" in css
    assert "var(--foms-text-primary)" in css
    assert "background: #fff" not in css


def test_drawing_queue_card_has_theme_aware_surface():
    css = _read("static/css/components/foms-drawing-mobile-card.css")
    assert ".foms-drawing-queue-card {" in css
    assert "background: var(--foms-surface-base)" in css
    assert "[data-theme='dark']" in css
    assert "--bs-card-bg: var(--foms-surface-base)" in css


def test_shipment_mobile_css_uses_tokens_for_labels():
    css = _read("static/css/components/foms-shipment-mobile.css")
    assert "color: var(--foms-text-secondary)" in css
    assert "color: #556b82" not in css
    assert "[data-theme='dark'] .erp-shipment-mobile-date-chip" in css


def test_as_schedule_equal_columns_and_no_row_class_on_dates():
    css = _read("static/css/components/foms-as-mobile-card.css")
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    card = _read("templates/cs/partials/as_mobile_order_card.html")
    assert "erp-as-mobile-card__date--received erp-pro-order-card__row" not in card
    assert "erp-as-mobile-card__date--visit erp-pro-order-card__row" not in card
    assert "white-space: nowrap" not in css.split("erp-as-mobile-card__date-value")[1].split("}")[0]
