/**
 * ERP 첨부 미리보기 모달 (#erpAttachmentPreviewModal) — 큐 카드·경량 표면용.
 * zoom/pinch: attachment-preview-zoom.js (fomsBindAttachmentPreviewImageZoom).
 */
(function () {
  "use strict";

  function escapeHtml(text) {
    if (text == null || text === "") return "";
    var div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
  }

  function ensureModalLifecycle(modalEl) {
    if (!modalEl || typeof window.fomsBindAttachmentPreviewModalZoomReset !== "function") return;
    window.fomsBindAttachmentPreviewModalZoomReset(modalEl, "erp-attachment-preview-body", {});
  }

  function syncFooterActions(readOnly) {
    var deleteBtn = document.getElementById("erp-attachment-preview-delete");
    var unlinkBtn = document.getElementById("erp-attachment-preview-unlink");
    var selectEl = document.getElementById("erp-attachment-preview-item-select");
    if (deleteBtn) deleteBtn.classList.toggle("d-none", !!readOnly);
    if (unlinkBtn) unlinkBtn.classList.add("d-none");
    if (selectEl) selectEl.classList.add("d-none");
  }

  function openErpAttachmentPreview(opts) {
    opts = opts || {};
    var modalEl = document.getElementById("erpAttachmentPreviewModal");
    var body = document.getElementById("erp-attachment-preview-body");
    var dl = document.getElementById("erp-attachment-preview-download");
    if (!modalEl || !body || !dl) return;

    var viewUrl = (opts.viewUrl || "").trim();
    if (!viewUrl) return;

    var downloadUrl = (opts.downloadUrl || viewUrl).trim();
    var label = opts.label || "";
    var readOnly = opts.readOnly !== false;

    dl.href = downloadUrl;
    syncFooterActions(readOnly);

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
    if (typeof window.fomsBindAttachmentPreviewImageZoom === "function") {
      window.fomsBindAttachmentPreviewImageZoom(body, { ensureModalReset: ensureModalLifecycle });
    }

    if (window.bootstrap && window.bootstrap.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  }

  function bindGallery(galleryEl) {
    var readOnly = galleryEl.getAttribute("data-foms-erp-attachment-preview-readonly") === "true";
    galleryEl.querySelectorAll("[data-foms-erp-attachment-view-url]").forEach(function (node) {
      if (node.dataset.fomsErpAttachmentPreviewBound === "1") return;
      node.dataset.fomsErpAttachmentPreviewBound = "1";
      node.style.cursor = "pointer";
      node.setAttribute("role", "button");
      node.setAttribute("tabindex", "0");
      node.addEventListener("keydown", function (ev) {
        if (ev.key !== "Enter" && ev.key !== " ") return;
        ev.preventDefault();
        node.click();
      });
      node.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openErpAttachmentPreview({
          viewUrl: node.getAttribute("data-foms-erp-attachment-view-url") || "",
          downloadUrl: node.getAttribute("data-foms-erp-attachment-download-url") || "",
          label: node.getAttribute("data-foms-erp-attachment-label") || "",
          readOnly: readOnly,
        });
      });
    });
  }

  function mountAll(root) {
    (root || document)
      .querySelectorAll("[data-foms-erp-attachment-preview-gallery]")
      .forEach(function (gallery) {
        if (gallery._fomsErpAttachmentPreviewGalleryBound) return;
        gallery._fomsErpAttachmentPreviewGalleryBound = true;
        bindGallery(gallery);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      mountAll(document);
    });
  } else {
    mountAll(document);
  }
  document.body.addEventListener("htmx:afterSwap", function () {
    mountAll(document);
  });
  document.addEventListener("foms:main-content-swapped", function () {
    mountAll(document);
  });

  window.fomsOpenErpAttachmentPreview = openErpAttachmentPreview;
  window.fomsMountErpAttachmentPreviewGalleries = mountAll;
})();
