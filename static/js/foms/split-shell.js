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
      // data-fragment-href = HTMX fragment body swapped into the detail pane.
      // The card's <a href> points at the canonical full edit page, so if the
      // fragment href is missing we do NOT preventDefault — the browser follows
      // the real href to the styled page instead of dead-clicking (W15).
      var href = card.getAttribute("data-fragment-href");
      if (!href) return;
      ev.preventDefault();
      var orderId = card.getAttribute("data-order-id");

      var kv = detail.querySelector("[data-foms-split-detail-kv]");
      if (kv) {
        kv.hidden = false;
        var map = {
          customer: card.getAttribute("data-customer"),
          stage: card.getAttribute("data-stage"),
          phone: card.getAttribute("data-phone"),
          address: card.getAttribute("data-address"),
          manager: card.getAttribute("data-manager"),
        };
        Object.keys(map).forEach(function (key) {
          var node = kv.querySelector('[data-foms-split-kv="' + key + '"]');
          if (node) node.textContent = map[key] || "-";
        });
      }
      var placeholder = detail.querySelector("[data-foms-split-detail-placeholder] p");
      if (placeholder) placeholder.textContent = "주문 상세 로딩 중…";

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

    // Populate the detail pane on load so no tablet size shows an empty
    // placeholder: select the ?order card if present, else the first card.
    // Guarded to when the split is actually visible (tablet band) — on phone
    // and desktop the split shell is display:none (offsetParent null), so skip
    // and avoid a wasted detail fetch.
    function selectInitial() {
      if (root.offsetParent === null) return;
      var target = activeId
        ? list.querySelector('[data-order-id="' + activeId + '"]')
        : null;
      if (!target) target = list.querySelector("[data-foms-master-card]");
      if (target) target.click();
    }
    selectInitial();

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
