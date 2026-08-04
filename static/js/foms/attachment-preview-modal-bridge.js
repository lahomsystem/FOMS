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

  function isViewerRecord(a) {
    if (!a) return false;
    var t = String(a.file_type || "").toLowerCase();
    if (t === "image" || t === "video") return true;
    var probe = String(a.view_url || a.filename || "").toLowerCase();
    return /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif|mp4|webm|ogg)(\?|$)/.test(probe);
  }

  /**
   * @param {Object} record - 클릭된 첨부 레코드
   * @param {Array} [list] - 같은 묶음의 전체 첨부 목록(있으면 모바일에서 스와이프 목록으로 전달)
   * @param {number} [index] - list 내 record 위치(참조 불일치 대비 보조)
   */
  function openAttachmentPreviewFromRecord(record, list, index) {
    if (!record) return;
    // 모바일: 목록 컨텍스트가 있으면 이미지·영상 전체를 GlobalImageViewer 로 —
    // 단일 열림이 "옆으로 안 넘어감"의 근본 원인이라 목록째 전달한다.
    if (
      Array.isArray(list) && list.length > 1 && isViewerRecord(record) &&
      window.fomsIsMobileImageViewer && window.fomsIsMobileImageViewer()
    ) {
      var eligible = list.filter(isViewerRecord);
      var pos = eligible.indexOf(record);
      if (pos < 0 && typeof index === "number" && list[index]) {
        pos = eligible.indexOf(list[index]);
      }
      if (pos < 0) {
        pos = eligible.findIndex(function (a) {
          return String(a.view_url || "") === String(record.view_url || "");
        });
      }
      if (eligible.length > 1 && pos >= 0) {
        window.GlobalImageViewer.open(
          eligible.map(function (a) {
            return {
              view_url: a.view_url || "",
              download_url: a.download_url || a.view_url || "",
              filename: a.filename || "이미지",
              key: a.storage_key || a.key || "",
            };
          }),
          pos
        );
        return;
      }
    }
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
