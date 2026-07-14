/**
 * Tablet-landscape global rail active-state sync (T2, 2026-07-12 목업 v5 정합).
 *
 * The global 72px rail (templates/partials/shared/foms_tablet_rail.html) lives in
 * layout_nav.html — OUTSIDE #main-content — so the ERP shell fast-tab swap
 * (static/js/runtime/erp-shell.js, which replaces only #main-content.innerHTML) never
 * re-renders it. Without this the rail's server-rendered .is-active highlight goes
 * stale after an in-place fragment navigation. This script re-derives the active item
 * from location.pathname on every fragment swap + popstate, applying the SAME
 * longest-segment-prefix rule as the server resolver
 * (foms.services.foms_split_view.resolve_tablet_rail_active_id) — including the
 * calculator item, whose href is /wdcalculator, so no special-case is needed here.
 *
 * Load: layout_nav.html, right after the rail include, deferred (perf guard G1). It is
 * layout-owned (not inside #main-content), so it is evaluated once per full page load,
 * never re-run by the fragment swap; the singleton guard is belt-and-braces (perf
 * guard G4). No inline styles, no jQuery.
 */
(function () {
  'use strict';

  if (window.__FOMS_TABLET_RAIL_NAV_BOUND) {
    return;
  }

  var rail = document.querySelector('.foms-tablet-rail');
  if (!rail) {
    // No rail on this page (non-cohort / non-/erp / non-calculator). The rail is
    // layout-owned and can never appear via a fragment swap, so skip listener
    // registration entirely (no-op).
    return;
  }

  window.__FOMS_TABLET_RAIL_NAV_BOUND = true;

  /**
   * Strip a single trailing slash while preserving the root "/".
   * @param {string} path
   * @returns {string}
   */
  function normalizePath(path) {
    if (!path) {
      return '';
    }
    return path.length > 1 ? path.replace(/\/+$/, '') : path;
  }

  /**
   * True when `current` equals `base` or extends it on a segment boundary, so
   * "/erp/ashley" does NOT match the "/erp/as" prefix (server parity).
   * @param {string} current
   * @param {string} base
   * @returns {boolean}
   */
  function isSegmentPrefix(current, base) {
    return current === base || current.indexOf(base + '/') === 0;
  }

  /** Re-apply .is-active + aria-current="page" to the rail item matching the path. */
  function syncActive() {
    var current = normalizePath(window.location.pathname);
    var items = rail.querySelectorAll('.foms-tablet-rail__item');
    var best = null;
    var bestLen = -1;
    var i;
    var item;
    var base;
    for (i = 0; i < items.length; i += 1) {
      // Anchor .pathname resolves the href to its absolute path (segment SSOT parity).
      base = normalizePath(items[i].pathname || '');
      if (base && isSegmentPrefix(current, base) && base.length > bestLen) {
        bestLen = base.length;
        best = items[i];
      }
    }
    for (i = 0; i < items.length; i += 1) {
      item = items[i];
      if (item === best) {
        item.classList.add('is-active');
        item.setAttribute('aria-current', 'page');
      } else {
        item.classList.remove('is-active');
        item.removeAttribute('aria-current');
      }
    }
  }

  document.addEventListener('foms:erp-shell-fragment-swapped', syncActive);
  window.addEventListener('popstate', syncActive);
})();
