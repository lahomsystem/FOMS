/**
 * Mobile order detail attach grid — category tabs, collapsed panel, modal preview.
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
      if (btn.dataset.fomsAttachmentPreviewBound === "1") return;
      btn.dataset.fomsAttachmentPreviewBound = "1";
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

  function activateAttachTab(panel, tabKey) {
    panel.querySelectorAll("[data-foms-mobile-attach-tab]").forEach(function (tabBtn) {
      var active = tabBtn.getAttribute("data-foms-mobile-attach-tab") === tabKey;
      tabBtn.classList.toggle("is-active", active);
      tabBtn.setAttribute("aria-selected", active ? "true" : "false");
    });
    panel.querySelectorAll("[data-foms-mobile-attach-tabpanel]").forEach(function (tabPanel) {
      var active = tabPanel.getAttribute("data-foms-mobile-attach-tabpanel") === tabKey;
      tabPanel.classList.toggle("is-hidden", !active);
    });
  }

  function bindAttachPanel(panel) {
    if (panel.dataset.fomsMobileAttachPanelBound === "1") return;
    panel.dataset.fomsMobileAttachPanelBound = "1";

    var toggle = panel.querySelector("[data-foms-mobile-attach-panel-toggle]");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var collapsed = panel.classList.toggle("foms-mobile-attach-panel--collapsed");
        toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        if (!collapsed) {
          panel.querySelectorAll("[data-foms-attachment-preview-gallery]").forEach(bindGallery);
        }
      });
    }

    panel.querySelectorAll("[data-foms-mobile-attach-tab]").forEach(function (tabBtn) {
      tabBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        activateAttachTab(panel, tabBtn.getAttribute("data-foms-mobile-attach-tab") || "");
      });
    });
  }

  function mountAll(root) {
    (root || document).querySelectorAll("[data-foms-mobile-attach-panel]").forEach(bindAttachPanel);
    (root || document).querySelectorAll("[data-foms-attachment-preview-gallery]").forEach(function (gallery) {
      if (gallery._fomsAttachmentPreviewBound) return;
      gallery._fomsAttachmentPreviewBound = true;
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
  window.fomsMountMobileDetailAttachmentPreview = mountAll;
})();
