/**
 * P2-04 FOMS lightbox — pinch-zoom, swipe nav, download (new surfaces).
 */
(function () {
  "use strict";

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function FomsLightbox(galleryEl) {
    this.gallery = galleryEl;
    this.images = Array.prototype.slice.call(
      galleryEl.querySelectorAll("[data-foms-lightbox-src]")
    );
    this.index = 0;
    this.scale = 1;
    this.tx = 0;
    this.ty = 0;
    this.shell = null;
    this.img = null;
    this._bindTriggers();
  }

  FomsLightbox.prototype._bindTriggers = function () {
    var self = this;
    this.images.forEach(function (node, idx) {
      node.addEventListener("click", function (ev) {
        ev.preventDefault();
        self.open(idx);
      });
    });
  };

  FomsLightbox.prototype._ensureShell = function () {
    if (this.shell) return;
    var shell = document.createElement("div");
    shell.className = "foms-lightbox";
    shell.hidden = true;
    shell.innerHTML =
      '<button type="button" class="foms-lightbox__close" aria-label="닫기">&times;</button>' +
      '<button type="button" class="foms-lightbox__nav foms-lightbox__nav--prev" aria-label="이전">&lsaquo;</button>' +
      '<button type="button" class="foms-lightbox__nav foms-lightbox__nav--next" aria-label="다음">&rsaquo;</button>' +
      '<div class="foms-lightbox__stage"><img class="foms-lightbox__img" alt="" draggable="false"></div>' +
      '<div class="foms-lightbox__toolbar">' +
      '<button type="button" class="foms-lightbox__btn" data-action="rotate" aria-label="회전">↻</button>' +
      '<a class="foms-lightbox__btn" data-action="download" download aria-label="다운로드">↓</a>' +
      "</div>";
    document.body.appendChild(shell);
    this.shell = shell;
    this.img = shell.querySelector(".foms-lightbox__img");
    this._wireShell();
  };

  FomsLightbox.prototype._wireShell = function () {
    var self = this;
    this.shell.querySelector(".foms-lightbox__close").addEventListener("click", function () {
      self.close();
    });
    this.shell.querySelector(".foms-lightbox__nav--prev").addEventListener("click", function () {
      self.open(self.index - 1);
    });
    this.shell.querySelector(".foms-lightbox__nav--next").addEventListener("click", function () {
      self.open(self.index + 1);
    });
    this.shell.querySelector('[data-action="rotate"]').addEventListener("click", function () {
      self.rotation = ((self.rotation || 0) + 90) % 360;
      self._applyTransform();
    });
    this.shell.addEventListener("click", function (ev) {
      if (ev.target === self.shell) self.close();
    });
    this._enableZoom();
    this._enableSwipeNav();
    document.addEventListener("keydown", function (ev) {
      if (!self.shell || self.shell.hidden) return;
      if (ev.key === "Escape") self.close();
      if (ev.key === "ArrowLeft") self.open(self.index - 1);
      if (ev.key === "ArrowRight") self.open(self.index + 1);
    });
  };

  FomsLightbox.prototype._applyTransform = function () {
    if (!this.img) return;
    var rot = this.rotation || 0;
    this.img.style.transform =
      "translate(" + this.tx + "px," + this.ty + "px) scale(" + this.scale + ") rotate(" + rot + "deg)";
  };

  FomsLightbox.prototype._resetTransform = function () {
    this.scale = 1;
    this.tx = 0;
    this.ty = 0;
    this.rotation = 0;
    this._applyTransform();
  };

  FomsLightbox.prototype.open = function (idx) {
    if (!this.images.length) return;
    if (idx < 0) idx = this.images.length - 1;
    if (idx >= this.images.length) idx = 0;
    this.index = idx;
    this._ensureShell();
    var src =
      this.images[idx].getAttribute("data-foms-lightbox-src") ||
      this.images[idx].getAttribute("src") ||
      "";
    this.img.src = src;
    var dl = this.shell.querySelector('[data-action="download"]');
    if (dl) dl.href = src;
    this._resetTransform();
    this.shell.hidden = false;
    document.documentElement.classList.add("foms-lightbox-open");
  };

  FomsLightbox.prototype.close = function () {
    if (!this.shell) return;
    this.shell.hidden = true;
    document.documentElement.classList.remove("foms-lightbox-open");
  };

  FomsLightbox.prototype._enableZoom = function () {
    var self = this;
    var stage = this.shell.querySelector(".foms-lightbox__stage");
    var lastDist = 0;
    stage.addEventListener("wheel", function (ev) {
      if (self.shell.hidden) return;
      ev.preventDefault();
      var delta = ev.deltaY > 0 ? -0.1 : 0.1;
      self.scale = Math.min(4, Math.max(1, self.scale + delta));
      self._applyTransform();
    }, { passive: false });
    stage.addEventListener("touchstart", function (ev) {
      if (ev.touches.length === 2) {
        lastDist = Math.hypot(
          ev.touches[0].clientX - ev.touches[1].clientX,
          ev.touches[0].clientY - ev.touches[1].clientY
        );
      }
    }, { passive: true });
    stage.addEventListener("touchmove", function (ev) {
      if (ev.touches.length !== 2 || self.shell.hidden) return;
      var dist = Math.hypot(
        ev.touches[0].clientX - ev.touches[1].clientX,
        ev.touches[0].clientY - ev.touches[1].clientY
      );
      if (lastDist) {
        self.scale = Math.min(4, Math.max(1, self.scale + (dist - lastDist) * 0.01));
        self._applyTransform();
      }
      lastDist = dist;
    }, { passive: true });
    stage.addEventListener("dblclick", function () {
      self.scale = self.scale > 1 ? 1 : 2;
      self._applyTransform();
    });
  };

  FomsLightbox.prototype._enableSwipeNav = function () {
    if (REDUCED) return;
    var self = this;
    var startX = 0;
    this.shell.querySelector(".foms-lightbox__stage").addEventListener("touchstart", function (ev) {
      if (ev.touches.length === 1) startX = ev.touches[0].clientX;
    }, { passive: true });
    this.shell.querySelector(".foms-lightbox__stage").addEventListener("touchend", function (ev) {
      if (!ev.changedTouches.length || self.scale > 1.05) return;
      var dx = ev.changedTouches[0].clientX - startX;
      if (Math.abs(dx) < 48) return;
      self.open(dx < 0 ? self.index + 1 : self.index - 1);
    }, { passive: true });
  };

  function mountAll() {
    document.querySelectorAll("[data-foms-lightbox-gallery]").forEach(function (gallery) {
      if (gallery._fomsLightboxBound) return;
      gallery._fomsLightboxBound = true;
      new FomsLightbox(gallery);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }
  document.body.addEventListener("htmx:afterSwap", mountAll);
  window.fomsMountLightboxes = mountAll;
})();
