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
  var VIEWER_ROOT_ID = "global-image-viewer";
  var fullscreenSession = null; // { root, modalEl, returnFocus, observer, onKeydown, onFocusin }

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
      "translate(" + st.tx + "px, " + st.ty + "px) scale(" + st.scale + ")";
    var zoomed = st.scale > MIN_SCALE + 0.05;
    img.classList.toggle("erp-attachment-preview-img--expanded", zoomed);
    img.setAttribute(
      "aria-label",
      zoomed ? "이미지 이동·축소 (드래그 또는 탭)" : "이미지 확대"
    );
  }

  function viewerRootEl() {
    return document.getElementById(VIEWER_ROOT_ID);
  }

  function viewerIsOpen(root) {
    return (
      !!root &&
      root.style.display !== "none" &&
      root.getAttribute("aria-hidden") !== "true"
    );
  }

  // 뷰어가 실제로 열 수 있는 항목만 남긴다. 항목 객체 자체는 그대로 통과시킨다
  // (뷰어가 자기 정규화에서 key 로 안정 URL 을 다시 만든다).
  function normalizeFullscreenFiles(files) {
    if (!files || !Array.isArray(files)) return [];
    var kept = [];
    for (var i = 0; i < files.length; i += 1) {
      var f = files[i];
      if (!f) continue;
      // 원본 위치를 함께 담는다 — 앞쪽에 무효 항목이 있으면 index 가 밀려
      // 클릭한 것과 다른 이미지에서 시작하기 때문이다.
      if (f.view_url || f.url || f.download_url || f.key) kept.push({ file: f, at: i });
    }
    return kept;
  }

  // 뷰어가 닫힌 순간 가드를 걷고, 모달이 살아 있으면 스크롤 잠금과 포커스를 돌려준다.
  function endFullscreenSession() {
    var s = fullscreenSession;
    if (!s) return;
    fullscreenSession = null; // 복구 작업보다 먼저 비운다(재진입 안전)
    document.removeEventListener("keydown", s.onKeydown, true);
    document.removeEventListener("focusin", s.onFocusin, true);
    if (s.observer) s.observer.disconnect();

    var modalAlive =
      !!s.modalEl &&
      document.contains(s.modalEl) &&
      s.modalEl.classList.contains("show");
    // 모달이 없거나 이미 닫혔으면 overflow 를 건드리지 않는다(배경 영구 잠금 방지).
    if (!modalAlive) return;
    document.body.style.overflow = "hidden"; // 뷰어 close() 가 지운 모달 스크롤 잠금 복구

    var target = s.returnFocus;
    if (target && document.contains(target) && typeof target.focus === "function") {
      try {
        target.focus({ preventScroll: true });
      } catch (err) {
        try {
          target.focus();
        } catch (ignored) {
          /* noop */
        }
      }
    }
  }

  // 전체화면 위임이 가능하면 뷰어를 열고 true. 불가하면 아무것도 하지 않고 false(호출부는 폴백).
  function openAttachmentPreviewFullscreen(payload) {
    if (!payload) return false;
    var viewer = window.GlobalImageViewer;
    if (!viewer || typeof viewer.open !== "function") return false;
    var root = viewerRootEl();
    if (!root) return false;
    var kept = normalizeFullscreenFiles(payload.files);
    if (!kept.length) return false;
    var files = kept.map(function (k) { return k.file; });
    var wanted =
      typeof payload.index === "number" && payload.index >= 0 ? payload.index : 0;
    var idx = kept.findIndex(function (k) { return k.at === wanted; });
    if (idx < 0) idx = 0;
    if (fullscreenSession) endFullscreenSession();
    var modalEl = payload.modalEl || document.querySelector(".modal.show");

    try {
      viewer.open(files, idx);
    } catch (err) {
      return false;
    }
    // 뷰어가 실제로 보이는 상태가 됐을 때만 위임 성공이다.
    if (!viewerIsOpen(root)) return false;

    function onKeydown(ev) {
      if (ev.key !== "Escape") return;
      if (!viewerIsOpen(root)) return;
      // 캡처 단계에서 전파를 끊어 Bootstrap 모달 ESC 와 뷰어 자체 ESC 의 이중 발화를 막고,
      // 뷰어만 우리가 직접 닫는다.
      ev.stopPropagation();
      if (
        window.GlobalImageViewer &&
        typeof window.GlobalImageViewer.close === "function"
      ) {
        window.GlobalImageViewer.close();
        // 관찰자에만 의존하지 않고 여기서 바로 세션을 닫는다. MutationObserver 가 없거나
        // 뒤에 close() 가 인라인 style 을 안 건드리게 바뀌어도 캡처 ESC 가 영원히 남지 않게 한다.
        // close() 가 overflow 를 먼저 지우므로 그 뒤에 잠금을 복구하는 순서가 맞다.
        endFullscreenSession();
      }
    }

    function onFocusin(ev) {
      // Bootstrap 모달의 포커스 트랩(document 버블 focusin)이 뷰어 버튼으로 간 포커스를
      // 모달로 되끌어오는 것을 막는다.
      if (ev.target && root.contains(ev.target)) ev.stopPropagation();
    }

    document.addEventListener("keydown", onKeydown, true);
    document.addEventListener("focusin", onFocusin, true);

    // 뷰어에는 close 콜백이 없고 닫기 버튼·배드드롭·스테이지 클릭이 내부 close 에 직접
    // 바인드돼 있으므로, 루트 속성 변화를 관찰해 닫힘을 잡는다.
    var observer = null;
    if (typeof MutationObserver === "function") {
      observer = new MutationObserver(function () {
        if (!viewerIsOpen(root)) endFullscreenSession();
      });
      observer.observe(root, {
        attributes: true,
        attributeFilter: ["style", "aria-hidden"],
      });
    }

    fullscreenSession = {
      root: root,
      modalEl: modalEl || null,
      returnFocus: payload.returnFocus || null,
      observer: observer,
      onKeydown: onKeydown,
      onFocusin: onFocusin,
    };
    return true;
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
    img.style.display = "block";
    img.draggable = false;

    var stage = img.parentElement;
    if (!stage || !stage.classList.contains("erp-attachment-preview-zoom-stage")) {
      stage = document.createElement("div");
      stage.className = "erp-attachment-preview-zoom-stage";
      img.parentNode.insertBefore(stage, img);
      stage.appendChild(img);
    }

    resetZoom(img);

    // 옵션은 매 바인드마다 갱신한다(같은 img 가 재바인드돼도 최신 resolver 를 쓰게).
    img._fomsPreviewFullscreenOption = options.fullscreen || null;
    if (
      img._fomsPreviewFullscreenOption &&
      window.GlobalImageViewer &&
      window.GlobalImageViewer.open
    ) {
      img.setAttribute("title", "클릭하면 전체화면으로 봅니다");
    }

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

    // 클릭 시점에 최신 목록을 받는다(첨부가 삭제·재로딩돼도 바인드 시점 목록에 갇히지 않게).
    function resolveFullscreenPayload(img) {
      var src = img._fomsPreviewFullscreenOption;
      if (!src) return null;
      var raw = null;
      try {
        raw = typeof src === "function" ? src(img) : src;
      } catch (err) {
        return null;
      }
      if (!raw || !raw.files || !raw.files.length) return null;
      // 호출부가 준 객체는 변형하지 않고 복사본을 만든다.
      return {
        files: raw.files,
        index: raw.index,
        modalEl: raw.modalEl || (bodyEl.closest ? bodyEl.closest(".modal") : null),
        returnFocus: raw.returnFocus || img,
      };
    }

    function tryOpenFullscreen(img) {
      var payload = resolveFullscreenPayload(img);
      if (!payload) return false;
      return window.fomsOpenAttachmentPreviewFullscreen(payload) === true;
    }

    var clickTimer = null;
    var suppressTapToggle = false;
    img.addEventListener("click", function (ev) {
      ev.preventDefault();
      // 드래그(팬) 끝의 click 은 전체화면 시도보다 먼저 삼킨다.
      if (suppressTapToggle) {
        suppressTapToggle = false;
        return;
      }
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
      }
      // 전체화면은 250ms 지연을 거치지 않고 즉시 연다.
      if (tryOpenFullscreen(img)) return;
      clickTimer = setTimeout(function () {
        clickTimer = null;
        toggleTapZoom();
      }, 250);
    });
    img.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        if (tryOpenFullscreen(img)) return;
        toggleTapZoom();
      }
    });
    img.addEventListener("dblclick", function (ev) {
      ev.preventDefault();
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
      }
      // 뷰어가 이미 화면을 덮고 있으면(전체화면 세션 활성) 아무것도 하지 않는다.
      if (fullscreenSession) return;
      if (tryOpenFullscreen(img)) return;
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

  window.fomsOpenAttachmentPreviewFullscreen = openAttachmentPreviewFullscreen;
  window.fomsResetAttachmentPreviewZoom = resetZoom;
  window.fomsApplyAttachmentPreviewZoom = applyZoom;
  window.fomsBindAttachmentPreviewImageZoom = bindImageZoom;
  window.fomsBindAttachmentPreviewModalZoomReset = bindModalZoomReset;
})();
