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
    if (!modalEl || typeof window.fomsBindAttachmentPreviewModalZoomReset !== "function") return;
    window.fomsBindAttachmentPreviewModalZoomReset(modalEl, "erp-attachment-preview-body", {});
  }

  function openAttachmentPreview(opts) {
    var modalEl = document.getElementById("erpAttachmentPreviewModal");
    var body = document.getElementById("erp-attachment-preview-body");
    var dl = document.getElementById("erp-attachment-preview-download");
    if (!modalEl || !body || !dl) return;

    var viewUrl = opts.viewUrl || "";
    if (!viewUrl) return;

    var label = opts.label || "";
    var downloadUrl = opts.downloadUrl || viewUrl;

    // Mobile: route read-only image preview through GlobalImageViewer (blur + smooth zoom).
    if (window.fomsIsMobileImageViewer && window.fomsIsMobileImageViewer()) {
      window.GlobalImageViewer.open(
        [{ view_url: viewUrl, download_url: downloadUrl, filename: label }],
        0
      );
      return;
    }

    dl.href = downloadUrl;
    dl.classList.toggle("d-none", !downloadUrl || downloadUrl === "#");

    body.innerHTML =
      '<img src="' +
      escapeHtml(viewUrl) +
      '" alt="' +
      escapeHtml(label) +
      '" class="img-fluid rounded erp-attachment-preview-img" draggable="false">' +
      '<div class="small text-muted mt-2 erp-attachment-preview-caption">' +
      escapeHtml(label) +
      "</div>";

    ensureModalLifecycle(modalEl);
    if (window.fomsBindAttachmentPreviewImageZoom) {
      window.fomsBindAttachmentPreviewImageZoom(body, { ensureModalReset: ensureModalLifecycle });
    }

    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  }

  function attachViewUrl(btn) {
    return (
      btn.getAttribute("data-foms-attachment-view-url") ||
      btn.getAttribute("data-foms-lightbox-src") ||
      ""
    );
  }

  function bindGallery(galleryEl) {
    // Capture the whole gallery so clicking one image opens a swipeable viewer.
    var btns = Array.prototype.slice.call(
      galleryEl.querySelectorAll("[data-foms-attachment-preview]")
    );
    btns.forEach(function (btn) {
      if (btn.dataset.fomsAttachmentPreviewBound === "1") return;
      btn.dataset.fomsAttachmentPreviewBound = "1";
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        // Multi-image gallery → GlobalImageViewer (mobile swipe / PC arrows) for sibling nav.
        if (window.GlobalImageViewer && window.GlobalImageViewer.open) {
          var files = btns
            .map(function (n) {
              return {
                view_url: attachViewUrl(n),
                download_url: n.getAttribute("data-foms-attachment-download-url") || "",
                filename:
                  n.getAttribute("data-foms-attachment-label") || n.getAttribute("title") || "이미지",
              };
            })
            .filter(function (f) {
              return !!f.view_url;
            });
          if (files.length > 1) {
            var clickedUrl = attachViewUrl(btn);
            var startIndex = files.findIndex(function (f) {
              return f.view_url === clickedUrl;
            });
            window.GlobalImageViewer.open(files, startIndex >= 0 ? startIndex : 0);
            return;
          }
        }
        openAttachmentPreview({
          viewUrl: attachViewUrl(btn),
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
