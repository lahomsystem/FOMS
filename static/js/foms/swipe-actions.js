/**
 * P2-07 swipe actions on ERP mobile queue cards.
 */
(function () {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function bindCard(card) {
    if (!card || card.dataset.fomsSwipeBound) return;
    card.dataset.fomsSwipeBound = "1";
    var startX = 0;
    var currentX = 0;
    var open = false;

    card.addEventListener("touchstart", function (ev) {
      if (ev.touches.length !== 1) return;
      startX = ev.touches[0].clientX;
      currentX = 0;
    }, { passive: true });

    card.addEventListener("touchmove", function (ev) {
      if (ev.touches.length !== 1) return;
      currentX = ev.touches[0].clientX - startX;
      if (Math.abs(currentX) < 8) return;
      if (REDUCED) return;
      card.style.transform = "translateX(" + Math.max(-96, Math.min(96, currentX)) + "px)";
    }, { passive: true });

    card.addEventListener("touchend", function () {
      card.style.transform = "";
      if (currentX < -72) {
        open = !open;
        card.classList.toggle("is-swipe-open", open);
        if (window.fomsHapticTap) window.fomsHapticTap();
      } else if (currentX > 72) {
        card.classList.remove("is-swipe-open");
        open = false;
      }
    }, { passive: true });

    card.querySelectorAll("[data-foms-swipe-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var action = btn.getAttribute("data-foms-swipe-action");
        var orderId = card.getAttribute("data-order-id");
        if (!orderId) return;
        fetch("/api/foms/queue/" + orderId + "/action", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: action }),
        })
          .then(function (res) {
            return res.json();
          })
          .then(function (data) {
            if (!data.success) {
              throw new Error(data.error || "failed");
            }
            if (window.fomsShowToast) {
              window.fomsShowToast(action === "approve" ? "승인 처리됨" : "보류 처리됨");
            }
            card.remove();
          })
          .catch(function () {
            if (window.fomsShowToast) window.fomsShowToast("처리 실패");
          });
        card.classList.remove("is-swipe-open");
        open = false;
      });
    });
  }

  function init() {
    document.querySelectorAll(".erp-mobile-queue-card[data-foms-swipe-card]").forEach(bindCard);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  document.body.addEventListener("htmx:afterSwap", init);
})();
