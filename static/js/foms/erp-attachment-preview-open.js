/**
 * ERP 첨부 미리보기 모달 (#erpAttachmentPreviewModal) — 큐·대시보드·wizard·legacy 표면 공통.
 * zoom/pinch: attachment-preview-zoom.js (fomsBindAttachmentPreviewImageZoom).
 */
(function () {
  "use strict";

  if (window.__FOMS_ERP_ATTACHMENT_PREVIEW_OPEN_BOUND === "1") {
    return;
  }
  window.__FOMS_ERP_ATTACHMENT_PREVIEW_OPEN_BOUND = "1";

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

  function bindBodyZoom(body, modalEl) {
    ensureModalLifecycle(modalEl);
    if (typeof window.fomsBindAttachmentPreviewImageZoom === "function") {
      window.fomsBindAttachmentPreviewImageZoom(body, { ensureModalReset: ensureModalLifecycle });
    }
  }

  function showModal(modalEl) {
    if (window.bootstrap && window.bootstrap.Modal) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
  }

  /**
   * Full attachment preview (image zoom / video / non-preview file).
   * @param {Object} opts - viewUrl, downloadUrl, filename, fileType, readOnly
   */
  function openErpAttachmentPreviewModal(opts) {
    opts = opts || {};
    var modalEl = document.getElementById("erpAttachmentPreviewModal");
    var body = document.getElementById("erp-attachment-preview-body");
    var dl = document.getElementById("erp-attachment-preview-download");
    if (!modalEl || !body || !dl) return false;

    var viewUrl = (opts.viewUrl || "").trim();
    if (!viewUrl) return false;

    var downloadUrl = (opts.downloadUrl || viewUrl).trim();
    var filename = opts.filename || "";
    var fileType = String(opts.fileType || "image").toLowerCase();
    var readOnly = opts.readOnly !== false;

    dl.href = downloadUrl;
    dl.classList.toggle("d-none", !downloadUrl || downloadUrl === "#");
    syncFooterActions(readOnly);

    if (fileType === "video") {
      body.innerHTML =
        '<div class="ratio ratio-16x9 bg-dark rounded" style="overflow:hidden;">' +
        '<video src="' +
        escapeHtml(viewUrl) +
        '" controls autoplay style="width:100%;height:100%;"></video>' +
        "</div>" +
        '<div class="small text-muted mt-2">' +
        escapeHtml(filename) +
        "</div>";
    } else if (fileType === "file") {
      body.innerHTML =
        '<div class="d-flex flex-column align-items-center justify-content-center text-center p-4" style="min-height:280px;">' +
        '<i class="fas fa-file-alt text-secondary mb-3" style="font-size:3rem;"></i>' +
        '<div class="fw-semibold mb-2">' +
        escapeHtml(filename || "파일") +
        "</div>" +
        '<div class="small text-muted mb-3">문서 파일은 미리보기를 지원하지 않습니다.</div>' +
        '<a class="btn btn-primary" href="' +
        escapeHtml(downloadUrl) +
        '" target="_blank" rel="noopener">' +
        '<i class="fas fa-download"></i> 다운로드</a></div>';
    } else {
      body.innerHTML =
        '<img src="' +
        escapeHtml(viewUrl) +
        '" alt="' +
        escapeHtml(filename) +
        '" class="img-fluid rounded erp-attachment-preview-img">' +
        '<div class="small text-muted mt-2">' +
        escapeHtml(filename) +
        "</div>";
      bindBodyZoom(body, modalEl);
    }

    showModal(modalEl);
    return true;
  }

  /** Lightweight image-only preview (queue card gallery). */
  function openErpAttachmentPreview(opts) {
    return openErpAttachmentPreviewModal({
      viewUrl: opts && opts.viewUrl,
      downloadUrl: opts && opts.downloadUrl,
      filename: opts && opts.label,
      fileType: "image",
      readOnly: opts && opts.readOnly !== false,
    });
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
  window.fomsOpenErpAttachmentPreviewModal = openErpAttachmentPreviewModal;
  window.fomsMountErpAttachmentPreviewGalleries = mountAll;
})();
