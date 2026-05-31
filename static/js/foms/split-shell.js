/**
 * P1-05 tablet landscape split-view (1024px+).
 */
(function () {
  "use strict";

  function init() {
    var root = document.querySelector("[data-foms-split-shell]");
    if (!root) return;

    var list = root.querySelector("[data-foms-master-list]");
    var detail = root.querySelector("[data-foms-split-detail]");
    if (!list || !detail) return;

    list.addEventListener("click", function (ev) {
      var card = ev.target.closest("[data-foms-master-card]");
      if (!card) return;
      var href = card.getAttribute("data-href");
      var orderId = card.getAttribute("data-order-id");
      if (!href) return;

      list.querySelectorAll("[data-foms-master-card].is-active").forEach(function (el) {
        el.classList.remove("is-active");
      });
      card.classList.add("is-active");

      if (window.htmx && typeof window.htmx.ajax === "function") {
        window.htmx.ajax("GET", href, { target: detail, swap: "innerHTML" });
      } else if (detail.tagName === "IFRAME") {
        detail.src = href;
      } else {
        fetch(href, { credentials: "same-origin", headers: { "X-Requested-With": "foms-split" } })
          .then(function (res) {
            return res.text();
          })
          .then(function (html) {
            detail.innerHTML = html;
          })
          .catch(function () {
            window.location.href = href;
          });
      }

      if (orderId && window.history && window.history.replaceState) {
        var url = new URL(window.location.href);
        url.searchParams.set("order", orderId);
        window.history.replaceState({}, "", url.toString());
      }
    });

    var params = new URLSearchParams(window.location.search);
    var activeId = params.get("order");
    if (activeId) {
      var active = list.querySelector('[data-order-id="' + activeId + '"]');
      if (active) active.classList.add("is-active");
    }

    document.body.addEventListener("htmx:afterSwap", function (event) {
      if (!detail.contains(event.detail.target) && event.detail.target !== detail) {
        return;
      }
      document.dispatchEvent(
        new CustomEvent("foms:main-content-swapped", { detail: { source: "split-htmx" } })
      );
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
