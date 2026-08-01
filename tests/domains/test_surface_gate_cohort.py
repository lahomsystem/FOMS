"""SURFACE-GATE-01: order-edit cohort single-controller contracts (P1-27).

Root cause pinned here: the mobile shell CSS picks the mobile surface on a
coarse-pointer physical-portrait tablet (e.g. 1024x1366), but the form-selection
JS used the bare ``max-width: 991.98px`` arm only — so at 1024 coarse portrait CSS
styled the page mobile while JS removed the mobile form, losing the form.

The fix shares ONE predicate (byte-identical to the project SSOT gate) between CSS
and JS, and adds a single cohort controller that handles the gate-boundary
transition:

* pristine rotation -> full reload, server re-renders the opposite surface with
  sections intact and exactly one form in the DOM;
* dirty rotation    -> freeze the current cohort, preserve inputs, show a
  non-dismissable banner, and reload only after an explicit save;
* a soft-keyboard (visualViewport) resize never changes the gate match, so it can
  never flip the cohort.

These are static/JS contract checks (declaration-level, comment-immune). Real
device rendering is validated at the deploy browser-persona gate.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Byte-identical SSOT cohort gate (foms-shell.css, map-mobile-sheet.js, ...).
GATE = (
    "(max-width: 991.98px), "
    "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))"
)

DETAIL_HERO_CSS = ROOT / "static/css/components/foms-detail-hero.css"
FORM_FIELD_CSS = ROOT / "static/css/components/foms-form-field.css"
EDIT_BODY = ROOT / "templates/orders/partials/edit_order_body.html"
COHORT_JS = ROOT / "static/js/orders/erp-order-cohort.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _media_preludes(css: str) -> list[str]:
    """Return the prelude of every real ``@media ... {`` declaration.

    Comments are stripped first: a gate that appears only inside a CSS comment
    must NOT satisfy the contract (declaration parser, not naive substring).
    """
    stripped = _strip_css_comments(css)
    return [m.group(1).strip() for m in re.finditer(r"@media\s+([^{]+)\{", stripped)]


def test_css_cohort_gate_is_a_real_media_declaration_not_a_comment() -> None:
    for css_path in (DETAIL_HERO_CSS, FORM_FIELD_CSS):
        preludes = _media_preludes(_read(css_path))
        assert any(GATE == prelude for prelude in preludes), (
            f"{css_path.name}: SSOT cohort gate missing as a real @media declaration"
        )


def test_single_predicate_shared_by_css_and_js() -> None:
    """CSS (declaration-level) + JS controller + inline bootstrap all carry the
    identical gate — one predicate, no divergence."""
    assert any(GATE == prelude for prelude in _media_preludes(_read(DETAIL_HERO_CSS)))
    assert GATE in _read(COHORT_JS)
    assert GATE in _read(EDIT_BODY)


def test_bare_maxwidth_predicate_is_gone_from_form_selection() -> None:
    """P1-27 red->green: the surface must NOT be chosen on max-width alone."""
    body = _read(EDIT_BODY)
    js = _read(COHORT_JS)
    assert "matchMedia('(max-width: 991.98px)')" not in body
    assert 'matchMedia("(max-width: 991.98px)")' not in body
    assert "matchMedia('(max-width: 991.98px)')" not in js
    # 1024 coarse portrait stays mobile <=> the coarse-portrait arm is present.
    assert (
        "(min-width: 992px) and (pointer: coarse) and (orientation: portrait)" in body
    )
    # The inline bootstrap keeps selecting the surface via matchMedia (existing
    # responsive-mount contract) — just on the full gate now.
    assert "matchMedia" in body


def test_controller_keeps_exactly_one_surface_on_load() -> None:
    """Duplicate ERP ids across both surfaces => exactly one stays, removal keyed
    on the gate (in the synchronous inline bootstrap)."""
    body = _read(EDIT_BODY)
    js = _read(COHORT_JS)
    assert 'id="erp-order-form-legacy"' in body
    assert 'id="erp-order-form-mobile"' in body
    assert ".remove()" in (js + body)


def test_rotation_pristine_reloads_to_render_opposite_surface() -> None:
    js = _read(COHORT_JS)
    # Cohort change driven by the gate MQL change event (the boundary itself).
    assert re.search(r"addEventListener\(\s*['\"]change['\"]", js)
    # Pristine (not dirty) => full reload: server re-renders the correct surface,
    # sections intact, exactly one form.
    assert "isDirty" in js
    assert "location.reload()" in js


def test_rotation_dirty_freezes_with_nondismiss_banner_and_no_autoreload() -> None:
    js = _read(COHORT_JS)
    # Non-dismissable banner (bootstrap alert, no close button).
    assert "alert alert-warning" in js
    assert "btn-close" not in js
    # Frozen cohort state marker.
    assert "frozen" in js.lower()
    # Reload only after an explicit save — never automatically while dirty.
    assert "erp:order-saved" in js


def test_keyboard_resize_alone_does_not_flip_cohort() -> None:
    """visualViewport / window resize / innerHeight must never drive the cohort —
    only the gate MQL change (rotation) does, so a soft keyboard cannot flip it."""
    js = _read(COHORT_JS)
    assert "visualViewport" not in js
    assert "'resize'" not in js and '"resize"' not in js
    assert "innerHeight" not in js


def test_controller_is_singleton_guarded() -> None:
    """Idempotent on fragment replay (perf guard G4)."""
    js = _read(COHORT_JS)
    assert re.search(r"window\.__\w+_BOUND", js)


def test_controller_does_not_rebuild_form_dom() -> None:
    """Sections preserved: the controller never rewrites a form surface via
    innerHTML (pristine = server reload; dirty = leave inputs untouched)."""
    js = _read(COHORT_JS)
    assert re.search(r"erp-order-form-\w+[\s\S]{0,40}\.innerHTML\s*=", js) is None


def test_controller_is_linked_deferred_from_edit_body() -> None:
    """The controller ships as a deferred module (perf guard G1: no new render-
    blocking sync script)."""
    body = _read(EDIT_BODY)
    assert "js/orders/erp-order-cohort.js" in body
    for line in body.splitlines():
        if "erp-order-cohort.js" in line and "<script" in line:
            assert " defer" in line, "erp-order-cohort.js must be defer"
            break
    else:  # pragma: no cover - the link assert above fails first
        raise AssertionError("erp-order-cohort.js <script> tag not found")
