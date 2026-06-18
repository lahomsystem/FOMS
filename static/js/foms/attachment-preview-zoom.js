/**
 * Shared attachment preview zoom + pan (tap, double-tap, wheel, pinch, drag) for Bootstrap modals.
 */
(function () {
  "use strict";

  var MODAL_BOUND_FLAG = "_fomsPreviewModalZoomResetBound";
  var MIN_SCALE = 1;
  var MAX_SCALE = 4;
  var TAP_SCALE = 2;
  var DRAG_CLICK_THRESHOLD = 4;

  function resetZoom(img) {
    if (!img) return;
    img._erpPreviewZoomState = { scale: MIN_SCALE, tx: 0, ty: 0 };
    img.classList.remove(
      "erp-attachment-preview-img--expanded",
      "erp-attachment-preview-img--dragging"
    );
    img.style.transition = "";
    applyZoom(img);
  }

  function measureBaseDisplaySize(img) {
    var prevTransform = img.style.transform;
    img.style.transform = "none";
    var size = { w: img.offsetWidth, h: img.offsetHeight };
    img.style.transform = prevTransform;
    return size;
  }

  function clampPan(img, stage) {
    var st = img._erpPreviewZoomState;
    if (!st || st.scale <= MIN_SCALE + 0.05) {
      st.tx = 0;
      st.ty = 0;
      return;
    }
    if (!stage) return;
    var stageW = stage.clientWidth;
    var stageH = stage.clientHeight;
    if (!stageW || !stageH) return;

    var base = measureBaseDisplaySize(img);
    var maxTx = Math.max(0, (base.w * st.scale - stageW) / 2);
    var maxTy = Math.max(0, (base.h * st.scale - stageH) / 2);
    st.tx = Math.min(maxTx, Math.max(-maxTx, st.tx));
    st.ty = Math.min(maxTy, Math.max(-maxTy, st.ty));
  }

  function applyZoom(img, stage) {
    var st = img._erpPreviewZoomState || { scale: MIN_SCALE, tx: 0, ty: 0 };
    if (stage) clampPan(img, stage);
    img.style.transform =
      "translate3d(" + st.tx + "px," + st.ty + "px,0) scale(" + st.scale + ")";
    var zoomed = st.scale > MIN_SCALE + 0.05;
    img.classList.toggle("erp-attachment-preview-img--expanded", zoomed);
    img.setAttribute(
      "aria-label",
      zoomed ? "이미지 이동·축소 (드래그 또는 탭)" : "이미지 확대"
    );
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

    function setScale(next) {
      var st = img._erpPreviewZoomState;
      st.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, next));
      if (st.scale <= MIN_SCALE) {
        st.scale = MIN_SCALE;
        st.tx = 0;
        st.ty = 0;
      }
      applyZoom(img, stage);
    }

    function toggleTapZoom() {
      var st = img._erpPreviewZoomState;
      if (st.scale > MIN_SCALE + 0.05) {
        resetZoom(img);
      } else {
        st.scale = TAP_SCALE;
        applyZoom(img, stage);
      }
    }

    var clickTimer = null;
    var suppressTapToggle = false;
    img.addEventListener("click", function (ev) {
      ev.preventDefault();
      if (suppressTapToggle) {
        suppressTapToggle = false;
        return;
      }
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
    stage.addEventListener(
      "touchstart",
      function (ev) {
        if (ev.touches.length === 2) {
          pinchStartDist = Math.hypot(
            ev.touches[0].clientX - ev.touches[1].clientX,
            ev.touches[0].clientY - ev.touches[1].clientY
          );
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
        }
      },
      { passive: false }
    );

    stage.addEventListener("touchend", function () {
      pinchStartDist = 0;
    });

    var panPointer = null;
    var activePanPointers = 0;

    function cancelPanPointer() {
      if (!panPointer) return;
      if (stage.releasePointerCapture) {
        try {
          stage.releasePointerCapture(panPointer.id);
        } catch (_err) {
          /* ignore stale capture */
        }
      }
      img.classList.remove("erp-attachment-preview-img--dragging");
      img.style.transition = "";
      panPointer = null;
    }

    function finishPanPointer(ev) {
      if (!panPointer || ev.pointerId !== panPointer.id) return;
      if (stage.releasePointerCapture) {
        try {
          stage.releasePointerCapture(ev.pointerId);
        } catch (_err) {
          /* ignore stale capture */
        }
      }
      if (panPointer.moved) suppressTapToggle = true;
      img.classList.remove("erp-attachment-preview-img--dragging");
      img.style.transition = "";
      panPointer = null;
    }

    stage.addEventListener("pointerdown", function (ev) {
      activePanPointers += 1;
      if (activePanPointers > 1) {
        cancelPanPointer();
        return;
      }
      if (ev.pointerType === "mouse" && ev.button !== 0) return;
      var st = img._erpPreviewZoomState;
      if (st.scale <= MIN_SCALE + 0.05) return;
      panPointer = {
        id: ev.pointerId,
        x: ev.clientX,
        y: ev.clientY,
        tx: st.tx,
        ty: st.ty,
        moved: false,
      };
      img.classList.add("erp-attachment-preview-img--dragging");
      img.style.transition = "none";
      if (stage.setPointerCapture) stage.setPointerCapture(ev.pointerId);
      ev.preventDefault();
    });

    stage.addEventListener("pointermove", function (ev) {
      if (!panPointer || ev.pointerId !== panPointer.id) return;
      if (activePanPointers > 1) return;
      var st = img._erpPreviewZoomState;
      var dx = ev.clientX - panPointer.x;
      var dy = ev.clientY - panPointer.y;
      if (
        !panPointer.moved &&
        (Math.abs(dx) > DRAG_CLICK_THRESHOLD || Math.abs(dy) > DRAG_CLICK_THRESHOLD)
      ) {
        panPointer.moved = true;
      }
      if (!panPointer.moved) return;
      st.tx = panPointer.tx + dx;
      st.ty = panPointer.ty + dy;
      applyZoom(img, stage);
      ev.preventDefault();
    });

    function onPanPointerEnd(ev) {
      activePanPointers = Math.max(0, activePanPointers - 1);
      finishPanPointer(ev);
    }

    stage.addEventListener("pointerup", onPanPointerEnd);
    stage.addEventListener("pointercancel", onPanPointerEnd);
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
