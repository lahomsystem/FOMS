/**
 * Mobile order detail C14 accordion (read-only mockup parity).
 */
(function () {
  "use strict";

  function toggleProduct(row) {
    var collapsed = row.classList.toggle("foms-product-item--collapsed");
    var head = row.querySelector("[data-foms-mobile-product-toggle]");
    var expand = row.querySelector(".foms-product-item__expand");
    if (head) {
      head.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    if (expand) {
      expand.textContent = collapsed ? "⌄" : "⌃";
      expand.setAttribute("aria-label", collapsed ? "펼치기" : "접기");
    }
  }

  function initMobileDetailProducts(root) {
    (root || document).querySelectorAll("[data-foms-mobile-product]").forEach(function (row) {
      if (row.dataset.fomsMobileProductBound === "1") {
        return;
      }
      row.dataset.fomsMobileProductBound = "1";
      var head = row.querySelector("[data-foms-mobile-product-toggle]");
      if (!head) {
        return;
      }
      head.addEventListener("click", function () {
        toggleProduct(row);
      });
      head.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          toggleProduct(row);
        }
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initMobileDetailProducts(document);
    });
  } else {
    initMobileDetailProducts(document);
  }
  document.addEventListener("foms:main-content-swapped", function () {
    initMobileDetailProducts(document);
  });
})();
