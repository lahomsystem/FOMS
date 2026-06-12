/**
 * Shared attachment preview zoom (tap, double-tap, wheel, pinch) for compact Bootstrap modals.
 */
(function () {
  "use strict";

  var MODAL_BOUND_FLAG = "_fomsPreviewModalZoomResetBound";

  function resetZoom(img) {
    if (!img) return;
    img._erpPreviewZoomState = { scale: 1, tx: 0, ty: 0 };
    img.classList.remove("erp-attachment-preview-img--expanded");
    applyZoom(img);
  }

  function applyZoom(img) {
    var st = img._erpPreviewZoomState || { scale: 1, tx: 0, ty: 0 };
    img.style.transform =
      "translate3d(" + st.tx + "px," + st.ty + "px,0) scale(" + st.scale + ")";
    var zoomed = st.scale > 1.05;
    img.classList.toggle("erp-attachment-preview-img--expanded", zoomed);
    img.setAttribute("aria-label", zoomed ? "이미지 축소" : "이미지 확대");
  }

  function bindImageZoom(bodyEl, options) {
    if (!bodyEl) return;
    options = options || {};
    var img = bodyEl.querySelector("img");
    if (!img) return;

    if (typeof options.ensureModalReset === "function") {
      options.ensureModalReset();
    }

    img.classList.add("erp-attachment-preview-img");
    img.setAttribute("role", "button");
    img.setAttribute("tabindex", "0");
    img.draggable = false;

    var stage = img.parentElement;
    if (!stage || !stage.classList.contains("erp-attachment-preview-zoom-stage")) {
      stage = document.createElement("div");
      stage.className = "erp-attachment-preview-zoom-stage";
      img.parentNode.insertBefore(stage, img);
      stage.appendChild(img);
    }

    resetZoom(img);

    if (img._erpPreviewZoomBound) return;
    img._erpPreviewZoomBound = true;

    var MIN_SCALE = 1;
    var MAX_SCALE = 4;
    var TAP_SCALE = 2;

    function setScale(next) {
      var st = img._erpPreviewZoomState;
      st.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
      if (st.scale <= MIN_SCALE) {
        st.scale = MIN_SCALE;
        st.tx = 0;
        st.ty = 0;
      }
      applyZoom(img);
    }

    function toggleTapZoom() {
      var st = img._erpPreviewZoomState;
      if (st.scale > MIN_SCALE + 0.05) {
        resetZoom(img);
      } else {
        st.scale = TAP_SCALE;
        applyZoom(img);
      }
    }

    var clickTimer = null;
    img.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (clickTimer) clearTimeout(clickTimer);
      clickTimer = setTimeout(function () {
        clickTimer = null;
        toggleTapZoom();
      }, 250);
    });
    img.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        toggleTapZoom();
      }
    });
    img.addEventListener("dblclick", function (ev) {
      ev.preventDefault();
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
      }
      toggleTapZoom();
    });

    stage.addEventListener(
      "wheel",
      function (ev) {
        if (!img.isConnected) return;
        ev.preventDefault();
        var st = img._erpPreviewZoomState;
        var delta = ev.deltaY > 0 ? -0.12 : 0.12;
        setScale(st.scale + delta);
      },
      { passive: false }
    );

    var pinchStartDist = 0;
    var panStart = null;
    stage.addEventListener(
      "touchstart",
      function (ev) {
        if (ev.touches.length === 2) {
          pinchStartDist = Math.hypot(
            ev.touches[0].clientX - ev.touches[1].clientX,
            ev.touches[0].clientY - ev.touches[1].clientY
          );
        } else if (ev.touches.length === 1 && img._erpPreviewZoomState.scale > MIN_SCALE) {
          panStart = {
            x: ev.touches[0].clientX,
            y: ev.touches[0].clientY,
            tx: img._erpPreviewZoomState.tx,
            ty: img._erpPreviewZoomState.ty,
          };
        }
      },
      { passive: true }
    );

    stage.addEventListener(
      "touchmove",
      function (ev) {
        var st = img._erpPreviewZoomState;
        if (ev.touches.length === 2 && pinchStartDist) {
          ev.preventDefault();
          var dist = Math.hypot(
            ev.touches[0].clientX - ev.touches[1].clientX,
            ev.touches[0].clientY - ev.touches[1].clientY
          );
          setScale(st.scale + (dist - pinchStartDist) * 0.01);
          pinchStartDist = dist;
        } else if (ev.touches.length === 1 && panStart && st.scale > MIN_SCALE) {
          ev.preventDefault();
          st.tx = panStart.tx + (ev.touches[0].clientX - panStart.x);
          st.ty = panStart.ty + (ev.touches[0].clientY - panStart.y);
          applyZoom(img);
        }
      },
      { passive: false }
    );

    stage.addEventListener("touchend", function () {
      pinchStartDist = 0;
      panStart = null;
    });
  }

  function bindModalZoomReset(modalEl, bodyId, hooks) {
    if (!modalEl || modalEl[MODAL_BOUND_FLAG]) return;
    modalEl[MODAL_BOUND_FLAG] = true;
    hooks = hooks || {};

    modalEl.addEventListener("show.bs.modal", function () {
      if (hooks.saveFocusOnShow) {
        var active = document.activeElement;
        if (active && active !== document.body && active !== document.documentElement) {
          modalEl._fomsPreviewReturnFocus = active;
        }
      }
      if (typeof hooks.onShow === "function") hooks.onShow();
    });

    modalEl.addEventListener("hide.bs.modal", function () {
      if (typeof hooks.releaseFocusOnHide === "function") hooks.releaseFocusOnHide();
      if (typeof hooks.onHide === "function") hooks.onHide();
    });

    modalEl.addEventListener("hidden.bs.modal", function () {
      var body = document.getElementById(bodyId);
      var img = body && body.querySelector("img");
      if (img) resetZoom(img);
      if (typeof hooks.restoreFocusOnHidden === "function") hooks.restoreFocusOnHidden();
      if (typeof hooks.onHidden === "function") hooks.onHidden();
    });
  }

  window.fomsResetAttachmentPreviewZoom = resetZoom;
  window.fomsApplyAttachmentPreviewZoom = applyZoom;
  window.fomsBindAttachmentPreviewImageZoom = bindImageZoom;
  window.fomsBindAttachmentPreviewModalZoomReset = bindModalZoomReset;
})();
