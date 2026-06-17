/**
 * Thin bridge: legacy openAttachmentPreviewModal(name) → shared ERP modal SSOT.
 * Loaded after erp-attachment-preview-open.js on dashboard surfaces.
 */
(function () {
  "use strict";

  function openAttachmentPreviewModal(attachmentId, viewUrl, downloadUrl, filename, fileType) {
    if (typeof window.fomsOpenErpAttachmentPreviewModal === "function") {
      if (
        window.fomsOpenErpAttachmentPreviewModal({
          viewUrl: viewUrl,
          downloadUrl: downloadUrl,
          filename: filename,
          fileType: fileType,
          readOnly: true,
        })
      ) {
        return;
      }
    }
    if (window.GlobalImageViewer) {
      window.GlobalImageViewer.open(
        [
          {
            view_url: viewUrl,
            download_url: downloadUrl,
            filename: filename,
            file_type: fileType,
          },
        ],
        0
      );
      return;
    }
    console.error("Attachment preview unavailable: modal helper and GlobalImageViewer missing");
    alert("이미지 뷰어를 불러올 수 없습니다.");
  }

  function openAttachmentPreviewFromRecord(record) {
    if (!record) return;
    openAttachmentPreviewModal(
      record.id || 0,
      record.view_url || "",
      record.download_url || record.view_url || "",
      record.filename || "",
      record.file_type || "image"
    );
  }

  window.openAttachmentPreviewModal = openAttachmentPreviewModal;
  window.fomsOpenAttachmentPreviewFromRecord = openAttachmentPreviewFromRecord;
})();
