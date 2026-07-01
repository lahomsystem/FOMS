/**
 * P2-07 short haptic pulse (respects reduced motion).
 */
window.fomsHapticTap = function () {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (navigator.vibrate) navigator.vibrate(12);
};

if (!window.__FOMS_HAPTIC_BOUND) {
  window.__FOMS_HAPTIC_BOUND = true;
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".foms-btn, .erp-mobile-queue-card__action, [data-foms-haptic]");
    if (!btn) return;
    window.fomsHapticTap();
  });
}
