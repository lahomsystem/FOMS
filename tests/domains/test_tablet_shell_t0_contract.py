"""T0 tablet-shell selection + quick-win gate contracts (2026-07-10 overhaul).

Static file contracts for the tablet-shell T0 work
(docs/plans/2026-07-10-tablet-shell-t0-implementation-spec.md):

  - T0-1 CSS shell-selection matrix (``static/css/foundation/foms-split-view.css``):
    the enumerated width x orientation x pointer split-show queries are present,
    the old *unconditional* ``min-width: 1366px`` desktop hide is gone, the P2-08
    portrait-overlay re-introduction ban comment survives, and the
    ``data-foms-shell`` escape-hatch hooks exist.
  - Escape-hatch boot (``static/js/runtime/foms-shell-mode-boot.js`` + the
    ``layout_head.html`` pre-paint inline copy): the boot exists and is inlined
    (never a render-blocking ``<script src>`` per perf guards G1/G2).
  - T0-2 quick-win media-query gates: ``layout-scripts-core.js`` and
    ``foms-mobile-select.js`` adopt the ``<=991.98px OR coarse pointer`` tablet
    gate and no longer carry the old ``max-width: 768px`` / bare ``991.98px`` MQ.

These lock strings the broader mockup-parity / P2 gate suites do not pin, so a
future edit that regresses the matrix or the tablet gates fails fast here.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SPLIT_CSS = "static/css/foundation/foms-split-view.css"
SHELL_CSS = "static/css/foundation/foms-shell.css"
SHELL10_CSS = "static/css/foundation/erp-pro/10-erp-mobile-v2-shell.css"
BOOT_JS = "static/js/runtime/foms-shell-mode-boot.js"
LAYOUT_HEAD = "templates/partials/shared/layout_head.html"
IMAGE_VIEWER_JS = "static/js/runtime/layout-scripts-core.js"
MOBILE_SELECT_JS = "static/js/components/foms-mobile-select.js"

# The two enumerated split-show conditions the matrix now carries (2026-07-12 목업 v5
# 정합). Split is a narrow-desktop-window shell only, so the query is pointer-aware
# (fine/none) with NO orientation token — coarse-pointer tablets get the legacy PC
# surface + the global 72px rail instead of split.
SPLIT_SHOW_QUERIES = (
    "(min-width: 992px) and (max-width: 1365.98px) and (pointer: fine)",
    "(min-width: 992px) and (max-width: 1365.98px) and (pointer: none)",
)

# The old coarse split-show arms that must NO LONGER appear — they moved to the
# tablet-landscape "legacy PC surface + global rail" mode.
SPLIT_SHOW_REMOVED_QUERIES = (
    "(min-width: 992px) and (max-width: 1365.98px) and (orientation: landscape)",
    "(min-width: 1366px) and (orientation: landscape) and (pointer: coarse)",
)


def _read(rel: str) -> str:
    """Return the UTF-8 text of a repo-relative file."""
    return (ROOT / rel).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """Collapse every whitespace run to a single space so multi-line CSS selector
    chains can be matched as a stable one-line substring."""
    return re.sub(r"\s+", " ", text)


# --- T0-1: CSS shell-selection matrix --------------------------------------


def test_split_show_matrix_queries_present() -> None:
    """Both enumerated split-show conditions (fine/none 992–1365.98) are present verbatim."""
    css = _read(SPLIT_CSS)
    for query in SPLIT_SHOW_QUERIES:
        assert query in css, f"missing split-show matrix query: {query}"


def test_split_show_matrix_removed_coarse_arms() -> None:
    """The old coarse split-show arms (landscape 992–1365.98 + ≥1366 landscape-coarse)
    are gone — coarse-pointer tablets no longer select split (2026-07-12 목업 v5 정합)."""
    css = _read(SPLIT_CSS)
    for query in SPLIT_SHOW_REMOVED_QUERIES:
        assert query not in css, f"stale split-show arm still present: {query}"


def test_no_unconditional_desktop_hide_query() -> None:
    """The old bare ``@media (min-width: 1366px) {`` desktop hide is gone.

    >=1366 is now conditional: it only selects split (landscape+coarse) or
    desktop (fine/none), never a lone unconditional width block.
    """
    css = _read(SPLIT_CSS)
    assert "(min-width: 1366px) {" not in css


def test_no_raw_portrait_orientation_token() -> None:
    """The split-show query is orientation-AWARE (landscape only) and must never
    emit a raw ``orientation: portrait`` token (the P2-08 blank-screen cause)."""
    css = _read(SPLIT_CSS)
    assert "orientation: portrait" not in css


def test_p2_08_reintroduction_ban_comment_preserved() -> None:
    """The P2-08 portrait-overlay post-mortem + re-introduction ban comment survives."""
    css = _read(SPLIT_CSS)
    assert "P2-08 orientation overlay" in css
    assert "Do NOT re-introduce a portrait band-aid" in css


def test_grid_geometry_on_base_and_default_hidden() -> None:
    """Grid geometry lives on the base shell (so forced-split lays out), and the
    split wrapper is display:none by default — the matrix is the only opt-in."""
    css = _read(SPLIT_CSS)
    assert "grid-template-columns: 72px 360px minmax(0, 1fr)" in css
    # The base wrapper rule is the one carrying `width: 100%` (the media-query
    # opt-in copy only flips display), so anchor on that marker.
    base = re.search(r"\.foms-split-enabled \{[^}]*width: 100%[^}]*\}", css, re.S)
    assert base is not None, "expected base .foms-split-enabled rule"
    assert "display: none" in base.group(0), "split wrapper must default to hidden"


def test_split_base_hide_precedes_opt_in() -> None:
    """Source-order contract: the base ``.foms-split-enabled { display: none }``
    must come BEFORE the split-show ``@media`` opt-in block.

    Same specificity means source order decides the cascade; a base hide placed
    after the opt-in silently blanks the whole 992–1365 band (2026-07-11
    staging incident — string-presence contracts alone could not see cascade
    order, only the viewport smoke caught it).
    """
    css = _read(SPLIT_CSS)
    base = re.search(r"\.foms-split-enabled \{[^}]*width: 100%[^}]*\}", css, re.S)
    assert base is not None, "expected base .foms-split-enabled rule"
    assert "display: none" in base.group(0)
    opt_in = css.index(SPLIT_SHOW_QUERIES[0])
    assert base.start() < opt_in, (
        "base .foms-split-enabled hide must precede the split-show @media block"
    )


def test_data_foms_shell_escape_hatch_hooks() -> None:
    """Manual override hooks exist and win over the matrix via !important."""
    css = _read(SPLIT_CSS)
    assert 'html[data-foms-shell="desktop"] .foms-split-enabled' in css
    assert 'html[data-foms-shell="split"] .foms-split-enabled' in css
    assert 'html[data-foms-shell="split"] .foms-split-shell' in css
    assert "display: none !important" in css
    assert "display: block !important" in css
    assert "display: grid !important" in css


# --- Escape-hatch boot (physical SSOT + inline pre-paint copy) -------------


def test_shell_mode_boot_reads_localstorage_and_stamps_attr() -> None:
    """The boot script reads ``foms_shell_mode`` and stamps html[data-foms-shell]."""
    boot = _read(BOOT_JS)
    assert "foms_shell_mode" in boot
    assert "setAttribute('data-foms-shell'" in boot
    assert "removeAttribute('data-foms-shell')" in boot


def test_shell_mode_boot_is_inlined_not_render_blocking_src() -> None:
    """layout_head carries the pre-paint inline copy, NOT a render-blocking
    ``<script src>`` (perf guards G1/G2 forbid a new sync head script)."""
    head = _read(LAYOUT_HEAD)
    assert "foms_shell_mode" in head
    assert "data-foms-shell" in head
    # No src reference to the physical file in head → it stays inline pre-paint.
    assert "foms-shell-mode-boot.js" not in head


# --- T0-2: quick-win tablet media-query gates ------------------------------


def test_image_viewer_gate_uses_tablet_mq_not_768() -> None:
    """fomsIsMobileImageViewer gates on <=991.98px OR coarse pointer, not 768px,
    and keeps the GlobalImageViewer.open existence guard.

    Locks BOTH the SSOT .js file and the inline delivery copy in
    layout_scripts.html — the inline copy is what actually ships (the .js is not
    loaded via <script src>), so an unsynced inline silently reverts the gate.
    """
    js = _read(IMAGE_VIEWER_JS)
    assert "'(max-width: 991.98px), (pointer: coarse)'" in js
    assert "max-width: 768px" not in js
    assert "window.GlobalImageViewer && window.GlobalImageViewer.open" in js

    inline = _read("templates/partials/shared/layout_scripts.html")
    gate_start = inline.index("window.fomsIsMobileImageViewer")
    gate_body = inline[gate_start : gate_start + 600]
    assert "'(max-width: 991.98px), (pointer: coarse)'" in gate_body
    assert "max-width: 768px" not in gate_body


def test_mobile_select_gate_uses_tablet_mq_not_bare_width() -> None:
    """foms-mobile-select adopts the coarse-pointer tablet gate; the old bare
    ``matchMedia("(max-width: 991.98px)")`` (no pointer clause) is gone."""
    js = _read(MOBILE_SELECT_JS)
    assert 'matchMedia("(max-width: 991.98px), (pointer: coarse)")' in js
    assert 'matchMedia("(max-width: 991.98px)")' not in js
    assert "max-width: 768px" not in js


# --- W5: foms-shell.css shell-exclusivity (mobile opt-in / surface + desktop hide / hatch) ---

# Item 2 surface hide — 992+ non-mobile (landscape / fine / none), enumerated.
SHELL_SURFACE_HIDE_QUERIES = (
    "((min-width: 992px) and (orientation: landscape))",
    "((min-width: 992px) and (pointer: fine))",
    "((min-width: 992px) and (pointer: none))",
)

# Item 3 legacy-desktop hide — now the two narrow-window split combos (fine/none,
# split-sibling gated) + tablet-portrait-coarse (separate block). (2026-07-12 목업 v5
# 정합: the coarse-landscape and ≥1366 landscape-coarse arms were removed — coarse
# tablets keep the legacy PC grid + the global rail.)
SHELL_DESKTOP_HIDE_QUERIES = (
    "((min-width: 992px) and (max-width: 1365.98px) and (pointer: fine))",
    "((min-width: 992px) and (max-width: 1365.98px) and (pointer: none))",
    "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))",
)

# The coarse-landscape legacy-hide arms that must NO LONGER appear (moved to rail mode).
SHELL_DESKTOP_HIDE_REMOVED_QUERIES = (
    "((min-width: 992px) and (max-width: 1365.98px) and (orientation: landscape))",
    "((min-width: 1366px) and (orientation: landscape) and (pointer: coarse))",
)


def test_shell_mobile_opt_in_query_and_p2_08_comment() -> None:
    """The mobile shell block opts in phones (<992) AND tablet-portrait-coarse
    (≥992), and the comment records that this is a display opt-in, not a
    content-blanking P2-08-style overlay. (The portrait token is allowed here —
    test_p2_gate's ``orientation: portrait`` ban is scoped to foms-split-view.css.)"""
    css = _read(SHELL_CSS)
    assert (
        "(max-width: 991.98px), "
        "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))"
    ) in css
    assert "P2-08형 오버레이가 아님" in css


def test_shell_surface_hide_three_enumerations_present() -> None:
    """The mobile-v2 surface hide is the 3-way non-mobile enumeration; the old bare
    ``@media (min-width: 992px) {`` surface hide is gone (portrait-coarse keeps its
    surfaces so the tablet-portrait mobile shell is not blanked)."""
    css = _read(SHELL_CSS)
    for query in SHELL_SURFACE_HIDE_QUERIES:
        assert query in css, f"missing surface-hide enumeration: {query}"
    assert "@media (min-width: 992px) {" not in css


def test_shell_desktop_hide_enumerations_present() -> None:
    """The legacy-desktop hide is now the two narrow-window split combos (fine/none,
    split-sibling gated) + the tablet-portrait-coarse arm (separate block); the old bare
    992–1365.98 width band is gone, and the coarse-landscape / ≥1366 landscape-coarse
    arms were removed (2026-07-12 목업 v5 정합 — coarse tablets keep the legacy PC grid +
    global rail, so the split-hide must not fire there)."""
    css = _read(SHELL_CSS)
    for query in SHELL_DESKTOP_HIDE_QUERIES:
        assert query in css, f"missing desktop-hide enumeration: {query}"
    for query in SHELL_DESKTOP_HIDE_REMOVED_QUERIES:
        assert query not in css, f"stale desktop-hide arm still present: {query}"
    assert "@media (min-width: 992px) and (max-width: 1365.98px) {" not in css


def test_shell_escape_hatch_hooks_desktop_and_split() -> None:
    """foms-shell.css carries the desktop/split escape-hatch hooks so the manual
    override decides the mobile + desktop surfaces too, not only the split file
    (defect C). Desktop force restores the legacy wrapper (display:block) and hides
    the mobile surfaces/chrome; split force hides only the legacy wrapper."""
    css = _read(SHELL_CSS)
    assert 'html[data-foms-shell="desktop"]' in css
    assert 'html[data-foms-shell="split"]' in css
    assert "display: block !important" in css
    assert (
        'html[data-foms-shell="desktop"] body.erp-mobile-v2-layout .foms-shell-fab'
        in css
    )
    assert (
        'html[data-foms-shell="desktop"] body.erp-mobile-v2-layout .erp-mobile-shell-chrome'
        in css
    )


# --- W6: 10-shell.css chrome restore (Task 1) + inner-chrome hatch (Task 2) ---


def test_shell10_chrome_hide_is_three_enumerations_not_bare_992() -> None:
    """W6 Task 1: 10-shell.css의 모바일 chrome/드로어 숨김이 non-mobile 992+ 3열거
    (landscape / fine / none)로 바뀌고, 구 단순 폭 쿼리 ``@media (min-width: 992px) {``
    는 사라졌다. 구 쿼리는 portrait-coarse(태블릿 세로=모바일 모드)까지 !important로
    죽여 하단 nav를 없앴다."""
    css = _read(SHELL10_CSS)
    for query in SHELL_SURFACE_HIDE_QUERIES:
        assert query in css, f"missing 10-shell chrome-hide enumeration: {query}"
    assert "@media (min-width: 992px) {" not in css


def test_shell10_mobile_opt_in_extends_to_portrait_coarse() -> None:
    """W6 Task 1 근본 복원: 10-shell.css의 모바일 chrome opt-in 블록이 phones(<992)에
    더해 tablet-portrait(≥992 portrait+coarse)까지 열거로 확장돼야 chrome wrapper의
    ``display: contents`` + 하단 nav 고정 geometry가 실제로 렌더된다. (992+ 숨김만 3열거로
    풀면 base ``.erp-mobile-shell-chrome{display:none}``가 남아 여전히 숨겨진 채가 된다.)
    foms-shell.css line 11 opt-in과 동일 열거."""
    css = _read(SHELL10_CSS)
    assert (
        "(max-width: 991.98px), "
        "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))"
    ) in css


def test_desktop_hatch_restores_inner_chrome_one_to_one() -> None:
    """W6 Task 2: desktop 강제 해치가 모바일 opt-in 블록이 !important로 숨기는 내부
    chrome(.erp-pro-header/.erp-pro-nav → flex, .erp-dashboard-layout/.table-responsive
    .d-none.d-lg-block → block)를 1:1 복원한다. 없으면 portrait-coarse ≥992 desktop 강제
    시 래퍼만 뜨고 내부가 비어 빈 화면이 된다."""
    css = _norm(_read(SHELL_CSS))
    prefix = (
        'html[data-foms-shell="desktop"] body.erp-mobile-v2-layout '
        ".erp-mobile-shell[data-erp-mobile-v2='true'] "
    )
    assert (
        prefix + ".erp-pro-header, " + prefix + ".erp-pro-nav { display: flex !important; }"
    ) in css
    assert (
        prefix
        + ".erp-dashboard-layout, "
        + prefix
        + ".table-responsive.d-none.d-lg-block { display: block !important; }"
    ) in css


def test_split_hatch_hides_mobile_chrome() -> None:
    """W6 Task 2: split 강제 해치가 모바일 표면·chrome도 숨긴다(split=대형 화면 인터페이스).
    Task 1이 모바일 opt-in을 portrait-coarse까지 확장했으므로, 이 은닉이 없으면 split 강제가
    portrait-coarse에서 모바일 하단 nav를 누출한다."""
    css = _norm(_read(SHELL_CSS))
    for surface in (
        ".erp-mobile-shell-chrome",
        ".erp-mobile-menu-drawer",
        ".foms-shell-fab",
    ):
        assert (
            'html[data-foms-shell="split"] body.erp-mobile-v2-layout ' + surface
        ) in css, f"split hatch must hide mobile surface: {surface}"


# --- W7: bridge header double-chrome + workbench tablet-portrait + rail scroll ---

BRIDGE_CSS = "static/css/foundation/erp-pro/13-foms-shell-bridge.css"
DRAWING_CARD_CSS = "static/css/components/foms-drawing-mobile-card.css"
WORKBENCH_BODY = "templates/drawing/partials/workbench_dashboard_body.html"


def test_bridge_header_hide_covers_split_fine_none_and_tablet_portrait() -> None:
    """2026-07-12 목업 v5 정합: the :has(.foms-split-enabled) header/nav hide now fires
    only where split is actually shown — the two narrow-desktop-window combos
    (992–1365.98 fine/none, mirroring the split-show query) — plus the unconditional
    ≥992 portrait-coarse tablet-mobile arm. The old ≥1366 landscape-coarse split
    header-hide arm is GONE (coarse landscape is now the global-rail tablet mode, whose
    chrome hide is the separate :has(.foms-tablet-rail) arm). Only ≥1366 fine/none
    (desktop) keeps the legacy header."""
    css = _read(BRIDGE_CSS)
    # Split header-hide is now pointer-aware fine/none (mirrors the split-show query).
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: fine)" in css
    assert "(min-width: 992px) and (max-width: 1365.98px) and (pointer: none)" in css
    assert (
        "(min-width: 992px) and (pointer: coarse) and (orientation: portrait)" in css
    ), "missing ≥992 portrait-coarse (tablet-mobile) header-hide arm"
    # The ≥1366 landscape-coarse SPLIT header-hide arm was removed (the rail arm owns
    # coarse landscape now); no bare ≥1366 desktop hide either.
    assert (
        "(min-width: 1366px) and (orientation: landscape) and (pointer: coarse)" not in css
    ), "stale ≥1366 landscape-coarse split header-hide arm still present"
    assert "(min-width: 1366px) {" not in css


def test_bridge_tablet_rail_arm_replaces_chrome_and_keeps_split_arm() -> None:
    """T2 (2026-07-12 목업 정합): a NEW bridge arm hides the three-tier legacy/ERP chrome
    (global brand header + global text nav + erp_sub_nav ``.erp-pro-nav``) on the
    tablet-landscape surface (≥992 landscape coarse) when the global rail
    (``.foms-tablet-rail``) is present, so those pages show rail + erp-pro-header only.
    The pre-existing ``:has(.foms-split-enabled)`` arm must survive unchanged (split
    pages own their chrome-hide via that marker — no double ownership)."""
    css = _read(BRIDGE_CSS)
    # New arm is @supports selector(:has(*)) gated (same accepted degradation as split).
    assert "@supports selector(:has(*))" in css
    # New arm media: coarse landscape ≥992 (distinct from the 1366 split + portrait arms).
    assert (
        "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)" in css
    ), "missing the T2 tablet-landscape rail chrome-hide media arm"
    # Keyed on the rail marker, hides all three chrome tiers incl. .erp-pro-nav.
    assert "body:has(.foms-tablet-rail) .layout-header" in css
    assert "body:has(.foms-tablet-rail) .layout-global-nav" in css
    assert "body:has(.foms-tablet-rail) .erp-pro-nav" in css
    # Pre-existing split-enabled arm still present (ownership boundary preserved).
    assert "body.erp-mobile-v2-layout:has(.foms-split-enabled) .layout-header" in css
    # True-desktop header still never killed by a bare ≥1366 hide.
    assert "(min-width: 1366px) {" not in css


def test_workbench_mobile_queue_shows_on_tablet_portrait() -> None:
    """W7 defect 2: the drawing workbench mobile queue opts in on phones AND tablet
    portrait (≥992 portrait coarse), matching the shell matrix, instead of the old
    width-only Bootstrap `d-lg-none`."""
    css = _read(DRAWING_CARD_CSS)
    assert (
        "(max-width: 991.98px), "
        "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))"
    ) in css, "mobile queue show query must enumerate tablet-portrait-coarse"


def test_workbench_desktop_content_hidden_on_tablet_portrait() -> None:
    """W7 defect 2: on tablet portrait the desktop-only process map + dashboard card
    (filter/table/pagination) are hidden so they do not leak over the mobile queue,
    the queue's d-lg-none children are re-shown so the container is not empty, and the
    non-mobile bands (992+ landscape/fine/none) keep the queue hidden (workbench is not
    split-wired → those bands keep the legacy desktop)."""
    css = _read(DRAWING_CARD_CSS)
    assert (
        "((min-width: 992px) and (pointer: coarse) and (orientation: portrait))" in css
    )
    assert ".dw-process-map" in css
    assert ".erp-drawing-dashboard-desktop-card" in css
    # Queue children (shared with the non-cohort fallback) re-shown, cohort-scoped.
    assert ".foms-drawing-mobile-dashboard .foms-drawing-queue" in css
    assert ".foms-drawing-mobile-dashboard .foms-mobile-filter-bar--drawing" in css
    # Non-mobile enumeration hides the queue (legacy desktop kept on landscape/PC).
    assert "((min-width: 992px) and (orientation: landscape))" in css
    assert "((min-width: 992px) and (pointer: fine))" in css
    assert "((min-width: 992px) and (pointer: none))" in css


def test_workbench_mobile_queue_section_drops_width_only_dlg_gate() -> None:
    """W7 defect 2: the .foms-drawing-mobile-dashboard section no longer gates on the
    width-only Bootstrap `d-lg-none` (which blanked the queue on tablet portrait); the
    shell-matrix media queries in foms-drawing-mobile-card.css govern show/hide."""
    body = _read(WORKBENCH_BODY)
    m = re.search(
        r'class="(foms-shell-body foms-drawing-mobile-dashboard[^"]*)"', body
    )
    assert m is not None, "expected the .foms-drawing-mobile-dashboard section"
    assert "d-lg-none" not in m.group(1)


def test_split_shell_rail_internal_scroll_capped() -> None:
    """W7 defect 4: the split shell is height-capped + clipped so the rail (and the
    master/detail columns) scroll inside their own tracks; master/detail get
    min-height:0 so the grid columns can shrink below content (the rail already did)."""
    css = _read(SPLIT_CSS)
    assert "max-height: calc(100dvh - 4rem)" in css
    assert "overflow: hidden" in css
    # side-tab (pre-existing) + master + detail each need min-height:0.
    assert _norm(css).count("min-height: 0") >= 3


# --- W8: split-UNWIRED page legacy fallback (992+ landscape blank seal) --------

CONSTRUCTION_BODY = "templates/construction/partials/dashboard_body.html"
ORDERS_DASHBOARD = "templates/orders/partials/dashboard_main.html"

# Every cohort page that ships .foms-shell-desktop-only must also render a mobile
# surface, otherwise the tablet-portrait hide would blank it (W8 scan). Only orders
# includes the split shell; the rest are the split-UNWIRED fallback set.
_SPLIT_UNWIRED_COHORT_BODIES = (
    CONSTRUCTION_BODY,
    "templates/production/partials/dashboard_body.html",
    "templates/shipment/partials/dashboard_main.html",
    "templates/measurement/partials/dashboard_main.html",
    "templates/orders/partials/history_dashboard_body.html",
)


def test_shell_legacy_hide_is_split_sibling_gated_on_landscape() -> None:
    """W8: the 992+ landscape/split legacy-desktop hide fires ONLY when the split
    markup (.foms-split-enabled) is a preceding sibling, so split-UNWIRED cohort
    pages keep the legacy desktop instead of collapsing to a blank at 992–1365
    landscape (staging 2026-07-11: split surface absent AND mobile surface hidden)."""
    css = _norm(_read(SHELL_CSS))
    assert (
        "body.erp-mobile-v2-layout .erp-mobile-shell[data-erp-mobile-v2='true'] "
        ".foms-split-enabled ~ .foms-shell-desktop-only"
    ) in css, "split-sibling-gated legacy-desktop hide selector missing"


def test_shell_legacy_fallback_contract_comment_present() -> None:
    """W8: the split-UNWIRED fallback contract is documented in-file so a future edit
    that reverts to the unconditional hide (which caused the blank) is caught in review."""
    css = _read(SHELL_CSS)
    assert "W8 split-UNWIRED fallback contract" in css


def test_bridge_header_hide_split_gated_under_has_supports_guard() -> None:
    """W8: the global-header hide for the split/large-screen arms is gated on
    body:has(.foms-split-enabled) — the header sits OUTSIDE the .erp-mobile-shell
    tree so a sibling combinator can't reach it — and the whole thing is wrapped in an
    @supports selector(:has(*)) guard (legacy browsers keep the header, documented)."""
    css = _norm(_read(BRIDGE_CSS))
    assert "@supports selector(:has(*))" in css
    for suffix in (".layout-header", ".layout-global-nav"):
        assert (
            "body.erp-mobile-v2-layout:has(.foms-split-enabled) " + suffix
        ) in css, f"missing :has-gated header hide for {suffix}"
    # The tablet-portrait arm stays unconditional (mobile surface guaranteed).
    assert "(min-width: 992px) and (pointer: coarse) and (orientation: portrait)" in css


def test_construction_is_split_unwired_so_fallback_holds() -> None:
    """W8: construction (and the other fallback-set dashboards) do NOT include the
    split shell, so the sibling-gated hide never fires there and the legacy desktop is
    the 992+ landscape fallback. Orders IS split-wired — the contrast proves the gate is
    meaningful (not vacuously true). If any fallback page later includes the split shell,
    update this list and confirm the sibling gate still fits."""
    orders = _read(ORDERS_DASHBOARD)
    assert "partials/shared/foms_split_shell.html" in orders, (
        "orders is expected to be the split-wired page"
    )
    for rel in _SPLIT_UNWIRED_COHORT_BODIES:
        body = _read(rel)
        assert "foms_split_shell.html" not in body, f"{rel} unexpectedly split-wired"
        assert "foms-split-enabled" not in body, f"{rel} unexpectedly has split markup"
        # …but each fallback page DOES ship a mobile surface, so tablet portrait is safe.
        assert "erp_mobile_shell.html" in body, f"{rel} missing mobile shell chrome"
