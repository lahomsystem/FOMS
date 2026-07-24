/**
 * P3-02 history mobile search-first: autofocus search when no filter applied.
 *
 * HISTORY-01: this JS re-executes on every ERP shell fragment swap (`activateScripts`
 * recreates the `<script src>` tag), but `document`'s DOMContentLoaded already fired
 * for the underlying page — a plain `DOMContentLoaded`-only bind is dead code on every
 * swap after the first. `window.__HISTORY_FOMS_BOUND` singleton guard (perf 가드 G4) +
 * `foms:erp-shell-fragment-swapped` delegation (same event as the sibling inline
 * chevron-toggle script in history_dashboard_body.html) keeps this to exactly one
 * live bind that re-queries the fresh DOM on every swap.
 */
(function () {
  "use strict";

  if (window.__HISTORY_FOMS_BOUND) return;
  window.__HISTORY_FOMS_BOUND = true;

  function init() {
    var shell = document.querySelector(".erp-history-mobile-shell[data-erp-mobile-v2='true']");
    if (!shell) return;
    var input = document.getElementById("erp-history-search-q");
    if (!input) return;
    var empty = shell.querySelector(".erp-history-mobile-empty");
    if (!empty) return;
    if (window.matchMedia("(max-width: 991.98px)").matches) {
      input.focus({ preventScroll: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.addEventListener("foms:erp-shell-fragment-swapped", init);
})();
