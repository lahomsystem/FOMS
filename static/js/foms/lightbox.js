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
    var rot = this.rotation || 0, uz = window.fomsUiZoom ? window.fomsUiZoom() : 1;  // tx · ty 는 보이는 px — 화면 크기 배율이면 나눠 넣는다
    this.img.style.transform =
      "translate(" + (this.tx / uz) + "px," + (this.ty / uz) + "px) scale(" + this.scale + ") rotate(" + rot + "deg)";
  };

  /** 옮긴 만큼을 그림이 화면 밖으로 다 나가지 않는 안쪽으로 묶는다(돌린 그림은 가로 · 세로를 바꿔 잰다). */
  FomsLightbox.prototype._clampPan = function () {
    if (!this.img) return;
    var stage = this.img.parentNode.getBoundingClientRect();
    var turned = Math.abs(this.rotation || 0) % 180 === 90, uz = window.fomsUiZoom ? window.fomsUiZoom() : 1;  // offset=배율 전 px, stage=보이는 px
    var w = (turned ? this.img.offsetHeight : this.img.offsetWidth) * uz * this.scale;
    var h = (turned ? this.img.offsetWidth : this.img.offsetHeight) * uz * this.scale;
    var mx = Math.max(0, (w - stage.width) / 2);
    var my = Math.max(0, (h - stage.height) / 2);
    this.tx = Math.min(mx, Math.max(-mx, this.tx));
    this.ty = Math.min(my, Math.max(-my, this.ty));
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
    // Mobile: delegate to GlobalImageViewer (blur backdrop + smooth focal zoom),
    // passing the whole gallery so prev/next nav and swipe still work.
    if (window.fomsIsMobileImageViewer && window.fomsIsMobileImageViewer()) {
      var files = this.images
        .map(function (node) {
          var src =
            node.getAttribute("data-foms-lightbox-src") || node.getAttribute("src") || "";
          return {
            view_url: src,
            download_url: node.getAttribute("data-foms-lightbox-download") || src,
            filename:
              node.getAttribute("alt") || node.getAttribute("data-foms-lightbox-name") || "이미지",
          };
        })
        .filter(function (f) {
          return !!f.view_url;
        });
      if (files.length) {
        window.GlobalImageViewer.open(files, idx);
        return;
      }
    }
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
      if (self.scale <= 1.05) { self.tx = 0; self.ty = 0; } else { self._clampPan(); }
      self._applyTransform();
    }, { passive: false });
    // 확대한 뒤 한 손가락(마우스)으로 끌어 옮긴다(사용자 11-04: 핀치 확대 뒤 이동이 안 돼 사진을 못 봄).
    var pan = null;
    function startPan(x, y) { pan = self.scale > 1.05 ? { x: x, y: y, tx: self.tx, ty: self.ty } : null; }
    function movePan(x, y) {
      if (!pan) return false;
      self.tx = pan.tx + (x - pan.x);
      self.ty = pan.ty + (y - pan.y);
      self._clampPan();
      self._applyTransform();
      return true;
    }
    stage.addEventListener("touchstart", function (ev) {
      if (ev.touches.length === 2) {
        self.pinched = true;
        pan = null;
        lastDist = Math.hypot(
          ev.touches[0].clientX - ev.touches[1].clientX,
          ev.touches[0].clientY - ev.touches[1].clientY
        );
      } else if (ev.touches.length === 1) {
        startPan(ev.touches[0].clientX, ev.touches[0].clientY);
      }
    }, { passive: true });
    stage.addEventListener("touchmove", function (ev) {
      if (self.shell.hidden) return;
      if (ev.touches.length === 1) {
        if (movePan(ev.touches[0].clientX, ev.touches[0].clientY)) ev.preventDefault();
        return;
      }
      if (ev.touches.length !== 2) return;
      var dist = Math.hypot(
        ev.touches[0].clientX - ev.touches[1].clientX,
        ev.touches[0].clientY - ev.touches[1].clientY
      );
      if (lastDist) {
        self.scale = Math.min(4, Math.max(1, self.scale + (dist - lastDist) * 0.01));
        if (self.scale <= 1.05) { self.tx = 0; self.ty = 0; }
        self._clampPan();
        self._applyTransform();
      }
      lastDist = dist;
      ev.preventDefault();
    }, { passive: false });
    stage.addEventListener("touchend", function (ev) {
      if (ev.touches.length === 1) startPan(ev.touches[0].clientX, ev.touches[0].clientY);  // 두 손가락 중 하나만 뗌
      if (!ev.touches.length) { lastDist = 0; pan = null; }
    }, { passive: true });
    stage.addEventListener("mousedown", function (ev) { if (ev.button === 0) { startPan(ev.clientX, ev.clientY); if (pan) ev.preventDefault(); } });
    window.addEventListener("mousemove", function (ev) { if (pan && !self.shell.hidden) movePan(ev.clientX, ev.clientY); });
    window.addEventListener("mouseup", function () { pan = null; });
    stage.addEventListener("dblclick", function () {
      self.scale = self.scale > 1 ? 1 : 2;
      if (self.scale === 1) { self.tx = 0; self.ty = 0; }
      self._applyTransform();
    });
  };

  FomsLightbox.prototype._enableSwipeNav = function () {
    if (REDUCED) return;
    var self = this;
    var startX = 0;
    this.shell.querySelector(".foms-lightbox__stage").addEventListener("touchstart", function (ev) {
      if (ev.touches.length === 1) { startX = ev.touches[0].clientX; self.pinched = false; }
    }, { passive: true });
    this.shell.querySelector(".foms-lightbox__stage").addEventListener("touchend", function (ev) {
      // 확대 중이거나 이번 손짓에 두 손가락(핀치)이 있었으면 다음 그림으로 넘기지 않는다 — 끌기 · 줄이기와 겹치지 않게.
      if (!ev.changedTouches.length || ev.touches.length || self.scale > 1.05 || self.pinched) return;
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

  /**
   * Open the shared lightbox for a single image URL (ERP attachment preview, etc.).
   * @param {string} url
   * @param {{ downloadUrl?: string }} [opts]
   */
  function openLightboxUrl(url, opts) {
    if (!url) return;
    opts = opts || {};
    // Mobile: route single-image preview through GlobalImageViewer too.
    if (window.fomsIsMobileImageViewer && window.fomsIsMobileImageViewer()) {
      window.GlobalImageViewer.open(
        [
          {
            view_url: url,
            download_url: opts.downloadUrl || url,
            filename: opts.filename || "이미지",
          },
        ],
        0
      );
      return;
    }
    var tmp = document.createElement("div");
    tmp.hidden = true;
    tmp.setAttribute("data-foms-lightbox-gallery", "");
    var stub = document.createElement("img");
    stub.setAttribute("data-foms-lightbox-src", url);
    stub.setAttribute("alt", "");
    tmp.appendChild(stub);
    document.body.appendChild(tmp);
    var lb = new FomsLightbox(tmp);
    lb.open(0);
    if (opts.downloadUrl) {
      var dl = lb.shell && lb.shell.querySelector('[data-action="download"]');
      if (dl) dl.href = opts.downloadUrl;
    }
  }

  window.fomsMountLightboxes = mountAll;
  window.fomsOpenLightboxUrl = openLightboxUrl;

  if (window.__FOMS_LIGHTBOX_BOUND) return;
  window.__FOMS_LIGHTBOX_BOUND = true;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }
  document.body.addEventListener("htmx:afterSwap", mountAll);
})();
