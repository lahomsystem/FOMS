/**
 * Mobile order detail attach grid — compact modal preview with shared zoom gestures.
 */
(function () {
  "use strict";

  function escapeHtml(text) {
    if (!text) return "";
    var div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  function ensureModalLifecycle(modalEl) {
    if (!modalEl || !window.fomsBindAttachmentPreviewModalZoomReset) return;
    window.fomsBindAttachmentPreviewModalZoomReset(modalEl, "foms-attachment-preview-body", {});
  }

  function openAttachmentPreview(opts) {
    var modalEl = document.getElementById("fomsAttachmentPreviewModal");
    var body = document.getElementById("foms-attachment-preview-body");
    var dl = document.getElementById("foms-attachment-preview-download");
    if (!modalEl || !body || !dl) return;

    var viewUrl = opts.viewUrl || "";
    if (!viewUrl) return;

    var label = opts.label || "";
    var downloadUrl = opts.downloadUrl || viewUrl;

    dl.href = downloadUrl;
    dl.classList.toggle("d-none", !downloadUrl || downloadUrl === "#");

    body.innerHTML =
      '<img src="' +
      escapeHtml(viewUrl) +
      '" alt="' +
      escapeHtml(label) +
      '" class="img-fluid rounded erp-attachment-preview-img">' +
      '<div class="small text-muted mt-2">' +
      escapeHtml(label) +
      "</div>";

    ensureModalLifecycle(modalEl);
    if (window.fomsBindAttachmentPreviewImageZoom) {
      window.fomsBindAttachmentPreviewImageZoom(body, { ensureModalReset: ensureModalLifecycle });
    }

    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  }

  function bindGallery(galleryEl) {
    galleryEl.querySelectorAll("[data-foms-attachment-preview]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        openAttachmentPreview({
          viewUrl:
            btn.getAttribute("data-foms-attachment-view-url") ||
            btn.getAttribute("data-foms-lightbox-src") ||
            "",
          label:
            btn.getAttribute("data-foms-attachment-label") || btn.getAttribute("title") || "",
          downloadUrl: btn.getAttribute("data-foms-attachment-download-url") || "",
        });
      });
    });
  }

  function mountAll() {
    document.querySelectorAll("[data-foms-attachment-preview-gallery]").forEach(function (gallery) {
      if (gallery._fomsAttachmentPreviewBound) return;
      gallery._fomsAttachmentPreviewBound = true;
      bindGallery(gallery);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }
  document.body.addEventListener("htmx:afterSwap", mountAll);
  window.fomsMountMobileDetailAttachmentPreview = mountAll;
})();
