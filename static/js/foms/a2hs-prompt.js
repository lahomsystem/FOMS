/**
 * P2-06 Add to Home Screen prompt (ERP mobile cohort, standalone display-mode skip).
 */
(function () {
  "use strict";

  if (window.__FOMS_A2HS_BOUND) return;
  window.__FOMS_A2HS_BOUND = true;

  var deferredPrompt = null;

  function registerPwaServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    if (!document.querySelector("[data-erp-mobile-shell]")) return;
    navigator.serviceWorker.register("/static/sw.js", { scope: "/" }).catch(function (err) {
      console.warn("[foms-a2hs] service worker registration failed", err);
    });
  }

  window.addEventListener("beforeinstallprompt", function (ev) {
    ev.preventDefault();
    deferredPrompt = ev;
    maybePrompt();
  });

  function maybePrompt() {
    if (!deferredPrompt) return;
    if (window.matchMedia("(display-mode: standalone)").matches) return;
    try {
      if (localStorage.getItem("foms.a2hs.dismissed") === "1") return;
    } catch (e) {
      /* ignore */
    }
    var bar = document.createElement("div");
    bar.className = "foms-a2hs-bar";
    bar.innerHTML =
      '<span>FOMS를 홈 화면에 추가하세요</span>' +
      '<button type="button" class="foms-btn foms-btn--primary foms-btn--sm" data-a2hs-install>설치</button>' +
      '<button type="button" class="foms-btn foms-btn--ghost foms-btn--sm" data-a2hs-dismiss>나중에</button>';
    document.body.appendChild(bar);
    bar.querySelector("[data-a2hs-install]").addEventListener("click", function () {
      deferredPrompt.prompt();
      deferredPrompt.userChoice.finally(function () {
        bar.remove();
        deferredPrompt = null;
      });
    });
    bar.querySelector("[data-a2hs-dismiss]").addEventListener("click", function () {
      try {
        localStorage.setItem("foms.a2hs.dismissed", "1");
      } catch (e) {
        /* ignore */
      }
      bar.remove();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", registerPwaServiceWorker);
  } else {
    registerPwaServiceWorker();
  }
})();
