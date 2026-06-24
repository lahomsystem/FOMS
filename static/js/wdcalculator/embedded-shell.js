(function () {
  "use strict";

  if (window.__wdCalculatorEmbeddedShellBound) {
    return;
  }
  window.__wdCalculatorEmbeddedShellBound = true;

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  ready(function () {
    var root = document.querySelector(".wdcalculator-container--embedded");
    if (!root) {
      return;
    }

    var toggle = document.getElementById("wdEmbeddedSavedToggle");
    var close = document.getElementById("wdEmbeddedSavedClose");
    var backdrop = document.getElementById("wdEmbeddedSavedBackdrop");

    function setOpen(open) {
      root.classList.toggle("is-saved-estimates-open", open);
      if (backdrop) {
        backdrop.hidden = !open;
      }
      if (toggle) {
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      }
      if (open && typeof window.loadSidebarEstimates === "function") {
        window.loadSidebarEstimates();
      }
    }

    if (toggle) {
      toggle.setAttribute("aria-controls", "savedEstimatesListContainer");
      toggle.setAttribute("aria-expanded", "false");
      toggle.addEventListener("click", function () {
        setOpen(!root.classList.contains("is-saved-estimates-open"));
      });
    }

    if (close) {
      close.addEventListener("click", function () {
        setOpen(false);
      });
    }

    if (backdrop) {
      backdrop.addEventListener("click", function () {
        setOpen(false);
      });
    }

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && root.classList.contains("is-saved-estimates-open")) {
        setOpen(false);
      }
    });

    root.addEventListener("click", function (event) {
      if (event.target && event.target.closest && event.target.closest(".load-estimate-btn")) {
        window.setTimeout(function () {
          setOpen(false);
        }, 120);
      }
    });
  });
})();
