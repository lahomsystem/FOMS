/**
 * P2-06 Add to Home Screen prompt (ERP mobile cohort, standalone display-mode skip).
 */
(function () {
  "use strict";

  if (window.__FOMS_A2HS_BOUND) return;
  window.__FOMS_A2HS_BOUND = true;

  var deferredPrompt = null;

  // SW 등록은 전 페이지(데스크톱 포함) — 데스크톱 full page load에서도 staticCacheFirst의
  // css/js 재검증 흡수를 받기 위해 mobile-shell 게이트를 제거한다. sw.js fetch 핸들러는
  // /static css/js만 캐시(TTL 후 백그라운드 재검증), 네비게이션·인증 fragment는 미캐시라
  // 데스크톱에서도 안전하다(networkFirst는 queue 전용, 3s timeout+캐시 폴백).
  function registerPwaServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
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
    // A2HS 설치 배너는 모바일 shell에서만 노출(동작 무변경). SW 등록만 전역화됐고,
    // 이 스크립트가 이제 데스크톱에도 로드되므로 배너 노출 경로엔 명시 게이트가 필요하다.
    if (!document.querySelector("[data-erp-mobile-shell]")) return;
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
