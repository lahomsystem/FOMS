/**
 * SURFACE-GATE-01 — order-edit cohort surface controller (P1-27).
 *
 * The mobile shell CSS and this JS share ONE cohort predicate (byte-identical to
 * the project SSOT gate). The inline bootstrap in edit_order_body.html removes the
 * non-matching surface on load (duplicate ERP ids => exactly one surface in the
 * DOM). This module owns the *transition* across the gate boundary:
 *
 *   - Rotation flips the gate match (e.g. a coarse tablet 1024x1366 portrait
 *     [mobile] <-> 1366x1024 landscape [desktop]). A pristine form reloads so the
 *     server re-renders the opposite surface with its sections intact and exactly
 *     one form; a dirty form is frozen (inputs preserved) with a non-dismissable
 *     banner and reloads only after an explicit save.
 *   - A soft keyboard does NOT change the gate match (it shrinks only the visual
 *     viewport, not the layout viewport the gate measures), so it never fires this
 *     listener and can never flip the cohort.
 *
 * @returns {void}
 */
(function () {
  'use strict';
  if (window.__ERP_COHORT_CTRL_BOUND) {
    return;
  }

  // Byte-identical to the CSS SSOT gate (foms-detail-hero.css / foms-form-field.css
  // / foms-shell.css) and to the inline bootstrap. Divergence styles-but-removes a
  // surface (P1-27: 1024 coarse portrait).
  var GATE =
    '(max-width: 991.98px), ((min-width: 992px) and (pointer: coarse) and (orientation: portrait))';

  // Only arm where the responsive ERP order surfaces actually ship. The inline
  // bootstrap has by now dropped one of the two; either presence means cohort.
  if (
    !document.getElementById('erp-order-form-legacy') &&
    !document.getElementById('erp-order-form-mobile')
  ) {
    return;
  }

  window.__ERP_COHORT_CTRL_BOUND = true;

  var mql = window.matchMedia(GATE);
  var frozen = false;

  /**
   * Whether the ERP order form has unsaved edits, via the autosave SSOT.
   * Missing autosave (should not happen on the edit surface) is treated as clean.
   * @returns {boolean}
   */
  function isDirtyNow() {
    var autosave = window.fomsErpAutosave;
    return !!(
      autosave &&
      typeof autosave.isDirty === 'function' &&
      autosave.isDirty()
    );
  }

  /**
   * Insert a single non-dismissable banner telling the user their edits are kept
   * and a save will switch layouts. No close button by design — the layout
   * mismatch persists until the form is saved.
   * @returns {void}
   */
  function showFreezeBanner() {
    if (document.getElementById('erp-cohort-freeze-banner')) {
      return;
    }
    var host =
      document.querySelector('.erp-order-mobile-form') ||
      document.querySelector('.foms-page-form') ||
      document.body;
    var banner = document.createElement('div');
    banner.id = 'erp-cohort-freeze-banner';
    banner.className = 'alert alert-warning erp-cohort-freeze-banner';
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'assertive');
    banner.textContent =
      '화면 방향이 바뀌었습니다. ' +
      '입력 중인 내용은 그대로 유지됩니다 — ' +
      '저장하면 새 화면으로 전환됩니다.';
    host.insertBefore(banner, host.firstChild);
  }

  /**
   * Handle a gate-boundary flip (device rotation).
   * @returns {void}
   */
  function onCohortChange() {
    if (frozen) {
      return;
    }
    if (isDirtyNow()) {
      // Dirty: freeze the current cohort, keep inputs, warn. No auto-reload.
      frozen = true;
      document.documentElement.classList.add('foms-erp-cohort-frozen');
      showFreezeBanner();
      return;
    }
    // Pristine: reload so the server re-renders the correct surface (sections
    // intact, exactly one form). The inline bootstrap drops the other on load.
    window.location.reload();
  }

  if (typeof mql.addEventListener === 'function') {
    mql.addEventListener('change', onCohortChange);
  } else if (typeof mql.addListener === 'function') {
    // Safari < 14 fallback.
    mql.addListener(onCohortChange);
  }

  // A frozen form applies its new cohort only on the next load, after a save.
  document.addEventListener('erp:order-saved', function () {
    if (frozen) {
      window.location.reload();
    }
  });
})();
