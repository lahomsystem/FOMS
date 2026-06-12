/**
 * §6.5 AS camera-first modal (mobile v2).
 */
(function () {
  "use strict";

  function initAsCameraBar(root) {
    var scope = root || document;
    var openBtn = scope.querySelector("[data-foms-as-camera-open]");
    var modal = scope.querySelector("#foms-as-camera-modal");
    if (!openBtn || !modal || modal.dataset.fomsAsCameraBound === "1") {
      return;
    }
    modal.dataset.fomsAsCameraBound = "1";

    openBtn.addEventListener("click", function () {
      modal.hidden = false;
      document.body.classList.add("foms-as-camera-open");
    });

    modal.querySelectorAll("[data-foms-as-camera-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        modal.hidden = true;
        document.body.classList.remove("foms-as-camera-open");
      });
    });

    if (window.FOMSPhotoCapture && typeof window.FOMSPhotoCapture.initPhotoCapture === "function") {
      window.FOMSPhotoCapture.initPhotoCapture(modal);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initAsCameraBar(document);
    });
  } else {
    initAsCameraBar(document);
  }
})();
