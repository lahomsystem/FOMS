/**
 * P2-08 tablet orientation → split-view layout class sync.
 */
(function () {
  "use strict";

  function syncLayout() {
    var split = document.querySelector("[data-foms-split-shell]");
    if (!split) return;
    var landscape = window.matchMedia("(orientation: landscape)").matches && window.innerWidth >= 1024;
    document.documentElement.classList.toggle("foms-split-landscape", landscape);
    document.documentElement.classList.toggle("foms-split-portrait", !landscape);
  }

  window.addEventListener("orientationchange", syncLayout);
  window.addEventListener("resize", syncLayout);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncLayout);
  } else {
    syncLayout();
  }
})();
