/**
 * P3-02 history mobile search-first: autofocus search when no filter applied.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var shell = document.querySelector(".erp-history-mobile-shell[data-erp-mobile-v2='true']");
    if (!shell) return;
    var input = document.getElementById("erp-history-search-q");
    if (!input) return;
    var empty = shell.querySelector(".erp-pro-empty");
    if (!empty) return;
    if (window.matchMedia("(max-width: 991.98px)").matches) {
      input.focus({ preventScroll: true });
    }
  });
})();
