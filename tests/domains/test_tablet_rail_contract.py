"""T2 tablet-landscape global rail contracts (2026-07-12 목업 정합 공사).

Locks the wiring for the always-on 72px left rail that replaces the three-tier
legacy/ERP chrome (global brand header + global text nav + erp_sub_nav icon nav)
on every /erp page (dashboard split excepted) at the tablet-landscape surface:

  - the include gate in ``layout_nav.html`` (v2 cohort ∩ /erp ∩ not /erp/dashboard),
  - the partial root class ``foms-tablet-rail``,
  - the rail CSS show/hide contract (base hidden, coarse-landscape media,
    rail-show + #main-content padding co-located in one @supports :has block),
  - the tablet bundle @import,
  - the cache-chain ?v bumps (bundle → 20260712c, erp-pro.css bumped, bridge
    @import 20260712a),
  - the lazy Jinja global registration, and
  - the active-tab-id path resolver.

These strings are not pinned by the broader T0 / T2 / mockup-parity suites, so a
future edit that regresses the rail wiring fails fast here.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from foms.services.foms_split_view import (
    build_tablet_rail_items,
    resolve_tablet_rail_active_id,
)

ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


LAYOUT_NAV = "templates/partials/shared/layout_nav.html"
RAIL_PARTIAL = "templates/partials/shared/foms_tablet_rail.html"
RAIL_CSS = "static/css/foundation/foms-tablet-rail.css"
RAIL_NAV_JS = "static/js/foms/tablet-rail-nav.js"
SPLIT_CSS = "static/css/foundation/foms-split-view.css"
BUNDLE_CSS = "static/css/foundation/foms-tablet-bundle.css"
LAYOUT_HEAD = "templates/partials/shared/layout_head.html"
ERP_PRO_CSS = "static/css/foundation/erp-pro.css"
CONTEXT_PROCESSORS = "foms/services/context_processors.py"


# --- ① include gate --------------------------------------------------------


def test_layout_nav_includes_rail_with_correct_gate() -> None:
    """layout_nav.html includes the rail partial gated on v2 cohort ∩ (/erp ∪
    /wdcalculator). The old /erp/dashboard exclusion is GONE (2026-07-12 목업 v5 정합:
    split no longer shows at the tablet-landscape surface, so the dashboard carries the
    global rail there without a double rail — at fine/none windows the rail is coarse-only
    CSS and stays hidden, and the split shell's own rail owns that case)."""
    nav = _read(LAYOUT_NAV)
    assert "partials/shared/foms_tablet_rail.html" in nav
    assert "erp_mobile_v2_enabled" in nav
    assert "request.path.startswith('/erp')" in nav
    assert "request.path.startswith('/wdcalculator')" in nav
    assert "not request.path.startswith('/erp/dashboard')" not in nav


def test_rail_nav_js_defer_singleton_and_events() -> None:
    """The rail active-sync script exists, is loaded deferred from layout_nav (perf G1),
    guards against double-binding (perf G4), and listens for the ERP fragment-swap +
    popstate events to re-apply .is-active / aria-current to the matching rail item."""
    js = _read(RAIL_NAV_JS)
    assert "__FOMS_TABLET_RAIL_NAV_BOUND" in js
    assert "foms:erp-shell-fragment-swapped" in js
    assert "popstate" in js
    assert "is-active" in js
    assert "aria-current" in js
    nav = _read(LAYOUT_NAV)
    assert "js/foms/tablet-rail-nav.js" in nav
    # Deferred load (render-blocking sync script is banned by perf guard G1).
    assert re.search(r"tablet-rail-nav\.js[^>]*\bdefer\b", nav) is not None, (
        "rail nav script must be loaded with defer"
    )


# --- ② partial root class --------------------------------------------------


def test_rail_partial_root_class_and_lazy_call() -> None:
    """The partial root is ``<nav class="foms-tablet-rail">`` and its items come from
    the lazy Jinja global ``foms_tablet_rail_items()`` (computed only on render)."""
    partial = _read(RAIL_PARTIAL)
    assert 'class="foms-tablet-rail"' in partial
    assert "foms-tablet-rail__item" in partial
    assert "foms_tablet_rail_items()" in partial
    # Namespace isolation: the markup must not USE the split rail classes (comments may
    # mention them for context; we only forbid actual class attributes).
    assert 'class="foms-split-side-tab' not in partial


# --- ③ rail CSS show/hide contract -----------------------------------------


def test_rail_css_base_hidden_and_supports_colocated() -> None:
    """Rail CSS: base ``display: none``; coarse-landscape ≥992 media; rail-show AND
    the #main-content push (padding-left) live in the SAME ``@supports selector(:has(*))``
    block so a no-:has browser drops both (rail never overlaps content)."""
    css = _read(RAIL_CSS)
    norm = " ".join(css.split())
    # Base hidden (all conditions) — the bare rule sets display:none.
    assert ".foms-tablet-rail { display: none; }" in norm
    # Enumerated tablet-landscape media (no `not`, landscape only).
    assert "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in css
    # The @supports :has gate wraps BOTH the rail-show and the #main-content push, so a
    # no-:has browser drops both. Anchor on the full @supports token (the prose comment
    # only says "@supports 블록", never the full selector form).
    assert "@supports selector(:has(*))" in css
    supports_block = css.split("@supports selector(:has(*))", 1)[1]
    assert ".foms-tablet-rail" in supports_block
    assert (
        "body:has(.foms-tablet-rail) #main-content" in supports_block
    )
    assert "padding-left: 72px" in supports_block
    assert "width: 72px" in supports_block


def test_rail_and_split_display_media_are_mutually_exclusive() -> None:
    """String-level exclusivity (2026-07-12 목업 v5 정합): the global rail shows only on
    coarse-landscape ≥992, while the split surface shows only on fine/none 992–1365.98
    windows. The two are pointer-exclusive (coarse ⊥ fine/none), so they never display
    together — the dashboard, which carries BOTH the split markup and the rail, can never
    render a double rail."""
    rail_css = _read(RAIL_CSS)
    split_css = _read(SPLIT_CSS)
    # Rail: coarse landscape only.
    assert (
        "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in rail_css
    )
    # Split-show: fine/none only …
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: fine)" in split_css
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: none)" in split_css
    # … and NO coarse-pointer media anywhere in the split file (no overlap with the rail).
    assert "(pointer: coarse)" not in split_css


# --- ④ bundle @import ------------------------------------------------------


def test_bundle_imports_rail_css() -> None:
    """foms-tablet-bundle.css @imports the rail stylesheet (versioned)."""
    bundle = _read(BUNDLE_CSS)
    assert '@import url("foms-tablet-rail.css?v=' in bundle


# --- ⑤ cache chain ---------------------------------------------------------


def test_cache_chain_versions_bumped() -> None:
    """Cache-chain contract: bundle link ?v=20260713h (content changed = 태블릿 클린 작업 큐
    그리드 신설 = landscape.css), erp-pro.css link bumped off the old 20260711ad, and erp-pro.css @imports
    the bridge at ?v=20260712b (bridge content changed = T2 chrome-hide arm + rail-key de-scope)."""
    head = _read(LAYOUT_HEAD)
    assert "foms-tablet-bundle.css') }}?v=20260724i" in head
    # erp-pro.css link bumped (old value gone, a fresh value present).
    assert "?v=20260711ad" not in head
    assert "erp-pro.css') }}?v=20260715a" in head
    erp_pro = _read(ERP_PRO_CSS)
    assert "13-foms-shell-bridge.css?v=20260712b" in erp_pro


# --- ⑥ Jinja global registration -------------------------------------------


def test_jinja_global_registered() -> None:
    """The lazy ``foms_tablet_rail_items`` global is defined and registered as a
    context processor (added, not replacing any existing injector)."""
    src = _read(CONTEXT_PROCESSORS)
    assert "def inject_tablet_rail_helper" in src
    assert "app.context_processor(inject_tablet_rail_helper)" in src
    assert '"foms_tablet_rail_items"' in src


# --- ⑦ active-id resolver unit tests ---------------------------------------


def test_resolve_active_id_maps_paths() -> None:
    """Path → active tab id via longest segment-prefix match."""
    assert resolve_tablet_rail_active_id("/erp/as") == "as"
    assert resolve_tablet_rail_active_id("/erp/measurement") == "measurement"
    assert resolve_tablet_rail_active_id("/erp/drawing-workbench") == "drawing_workbench"
    assert resolve_tablet_rail_active_id("/erp/production/dashboard") == "production"
    assert resolve_tablet_rail_active_id("/erp/shipment") == "shipment"
    assert resolve_tablet_rail_active_id("/erp/construction/dashboard") == "construction"
    assert resolve_tablet_rail_active_id("/erp/completion") == "completion"
    assert resolve_tablet_rail_active_id("/erp/history/") == "history"
    assert resolve_tablet_rail_active_id("/erp/dashboard") == "dashboard"


def test_resolve_active_id_matches_on_segment_boundary() -> None:
    """Sub-paths match the parent tab; a name that merely shares a string prefix does
    NOT falsely match (e.g. /erp/ashley must not resolve to ``as``)."""
    assert resolve_tablet_rail_active_id("/erp/measurement/42") == "measurement"
    assert resolve_tablet_rail_active_id("/erp/ashley") == ""
    assert resolve_tablet_rail_active_id("/not/erp") == ""
    assert resolve_tablet_rail_active_id("") == ""


def test_build_tablet_rail_items_highlights_current_path() -> None:
    """build_tablet_rail_items highlights exactly the tab matching the request path."""
    user = SimpleNamespace(team="SALES", role="STAFF")
    items = build_tablet_rail_items(user, "/erp/shipment")
    active = [it for it in items if it["active"]]
    assert [it["id"] for it in active] == ["shipment"]


def test_build_tablet_rail_items_no_false_active_when_unmatched() -> None:
    """An unmatched path yields no highlighted tab (not a false dashboard highlight)."""
    user = SimpleNamespace(team="SALES", role="STAFF")
    items = build_tablet_rail_items(user, "/erp/ashley")
    assert all(not it["active"] for it in items)


def test_resolve_active_id_maps_calculator() -> None:
    """The calculator page (/wdcalculator, outside the ERP nav contract) resolves to the
    explicit ``calculator`` id so the global rail highlights 계산기; a mere string prefix
    (/wdcalculatorx) does NOT match (segment boundary)."""
    assert resolve_tablet_rail_active_id("/wdcalculator") == "calculator"
    assert resolve_tablet_rail_active_id("/wdcalculator/") == "calculator"
    assert resolve_tablet_rail_active_id("/wdcalculator/embedded") == "calculator"
    assert resolve_tablet_rail_active_id("/wdcalculatorx") == ""


def test_build_tablet_rail_items_highlights_calculator() -> None:
    """On /wdcalculator the calculator rail item is the highlighted one (non-construction
    users get a calculator item; its href is /wdcalculator)."""
    user = SimpleNamespace(team="SALES", role="STAFF")
    items = build_tablet_rail_items(user, "/wdcalculator")
    active = [it for it in items if it["active"]]
    assert [it["id"] for it in active] == ["calculator"]
