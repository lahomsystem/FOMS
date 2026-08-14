/**
 * HISTORY-01: re-executes on every ERP shell fragment swap (`activateScripts`
 * recreates the `<script src>` tag), but by then `document`'s DOMContentLoaded has
 * already fired once — a `DOMContentLoaded`-only bind never re-runs on swap.
 * `window.__HISTORY_ORDERS_BOUND` singleton guard (perf 가드 G4) + `foms:erp-shell-fragment-swapped`
 * keeps this to exactly one live bind that re-queries the fresh DOM each swap.
 *
 * Mobile history cards are queue-card-v2 (same as 실측/홈). Expand/toggle of the
 * old inquiry card is gone; this script only highlights `?focus_order=`.
 */
(function () {
  if (window.__HISTORY_ORDERS_BOUND) return;
  window.__HISTORY_ORDERS_BOUND = true;

  function init() {
    var root = document.querySelector('.erp-history-mobile-shell[data-erp-mobile-v2="true"]');
    if (!root) return;

    var focusOrder = new URLSearchParams(window.location.search).get('focus_order');
    if (!focusOrder) return;

    var focusCard = root.querySelector('.foms-queue-card-v2[data-order-id="' + focusOrder + '"]')
      || root.querySelector('.erp-history-mobile-card[data-order-id="' + focusOrder + '"]');
    if (!focusCard) return;

    focusCard.classList.add('is-focused');
    window.setTimeout(function () {
      focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 120);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
  document.addEventListener('foms:erp-shell-fragment-swapped', init);
})();
