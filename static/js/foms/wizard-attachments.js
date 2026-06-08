/**
 * Wizard step2 per-product attachments (P2: photo capture + draft upload).
 */
(function () {
  "use strict";

  var UPLOAD_URL = "/api/erp/order-draft/attachments";

  function readAttachments(card) {
    if (!card || !Array.isArray(card._wizardAttachments)) {
      return [];
    }
    return card._wizardAttachments.map(function (entry) {
      return { tmp_key: entry.tmp_key, filename: entry.filename };
    });
  }

  function renderPreview(card) {
    var preview = card.querySelector("[data-wizard-attachment-preview]");
    if (!preview) {
      return;
    }
    var entries = card._wizardAttachments || [];
    preview.innerHTML = "";
    if (!entries.length) {
      preview.setAttribute("data-empty", "true");
      return;
    }
    preview.removeAttribute("data-empty");
    entries.forEach(function (entry, idx) {
      // 클릭 시 ERP order 방식 미리보기 모달을 연다(삭제는 모달 내부 버튼으로).
      var thumb = document.createElement("button");
      thumb.type = "button";
      thumb.className = "foms-wizard__attachment-thumb";
      thumb.setAttribute("data-attachment-index", String(idx));
      thumb.setAttribute("title", entry.filename || "첨부");
      thumb.setAttribute("aria-label", (entry.filename || "첨부") + " 미리보기");
      if (entry.view_url) {
        var img = document.createElement("img");
        img.src = entry.view_url;
        img.alt = entry.filename || "";
        thumb.appendChild(img);
      } else {
        var name = document.createElement("span");
        name.className = "foms-wizard__attachment-name";
        name.textContent = entry.filename || "파일";
        thumb.appendChild(name);
      }
      preview.appendChild(thumb);
    });
  }

  var VIDEO_RE = /\.(mp4|mov|webm|avi|mkv|m4v)$/i;
  var activePreview = null;

  function fillPreviewBody(entry) {
    var body = document.getElementById("wizard-attachment-preview-body");
    if (!body) {
      return;
    }
    body.innerHTML = "";
    var url = entry.view_url || "";
    if (url && VIDEO_RE.test(entry.filename || url)) {
      var video = document.createElement("video");
      video.src = url;
      video.controls = true;
      video.className = "foms-wizard__preview-media";
      body.appendChild(video);
    } else if (url) {
      var img = document.createElement("img");
      img.src = url;
      img.alt = entry.filename || "";
      img.className = "foms-wizard__preview-media";
      body.appendChild(img);
    } else {
      var p = document.createElement("p");
      p.className = "text-muted";
      p.textContent = entry.filename || "미리보기를 사용할 수 없습니다.";
      body.appendChild(p);
    }
  }

  function openPreviewModal(card, idx, scheduleSave) {
    var entry = (card._wizardAttachments || [])[idx];
    if (!entry) {
      return;
    }
    var modalEl = document.getElementById("wizardAttachmentPreviewModal");
    if (!modalEl || !window.bootstrap || !window.bootstrap.Modal) {
      // Bootstrap 미가용 시 새 탭 폴백.
      if (entry.view_url) {
        window.open(entry.view_url, "_blank", "noopener");
      }
      return;
    }
    activePreview = { card: card, idx: idx, scheduleSave: scheduleSave };
    fillPreviewBody(entry);
    var dl = document.getElementById("wizard-attachment-preview-download");
    if (dl) {
      dl.href = entry.view_url || "#";
    }
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function bindPreviewModal() {
    var modalEl = document.getElementById("wizardAttachmentPreviewModal");
    if (!modalEl || modalEl.dataset.wizardPreviewBound) {
      return;
    }
    modalEl.dataset.wizardPreviewBound = "1";
    var del = document.getElementById("wizard-attachment-preview-delete");
    if (del) {
      del.addEventListener("click", function () {
        if (!activePreview || !activePreview.card) {
          return;
        }
        var card = activePreview.card;
        if (Array.isArray(card._wizardAttachments)) {
          card._wizardAttachments.splice(activePreview.idx, 1);
          renderPreview(card);
          if (activePreview.scheduleSave) {
            activePreview.scheduleSave();
          }
        }
        activePreview = null;
        if (window.bootstrap && window.bootstrap.Modal) {
          window.bootstrap.Modal.getOrCreateInstance(modalEl).hide();
        }
      });
    }
  }

  function uploadFiles(card, draftKey, files, onDone) {
    if (!files || !files.length) {
      if (onDone) {
        onDone();
      }
      return;
    }
    var index = parseInt(card.getAttribute("data-product-index") || "0", 10);
    var queue = Array.prototype.slice.call(files);
    var next = function () {
      if (!queue.length) {
        if (onDone) {
          onDone();
        }
        return;
      }
      var file = queue.shift();
      var body = new FormData();
      body.append("draft_key", draftKey);
      body.append("item_index", String(index));
      body.append("file", file, file.name);
      fetch(UPLOAD_URL, { method: "POST", credentials: "same-origin", body: body })
        .then(function (res) {
          return res.json();
        })
        .then(function (payload) {
          if (payload && payload.success && payload.data) {
            if (!Array.isArray(card._wizardAttachments)) {
              card._wizardAttachments = [];
            }
            card._wizardAttachments.push({
              tmp_key: payload.data.tmp_key,
              filename: payload.data.filename,
              view_url: payload.data.view_url || "",
            });
            renderPreview(card);
          }
          next();
        })
        .catch(function () {
          next();
        });
    };
    next();
  }

  function bindCard(card, draftKey, scheduleSave) {
    if (!card || card._wizardAttachmentsBound) {
      return;
    }
    card._wizardAttachmentsBound = true;
    card._wizardAttachments = card._wizardAttachments || [];

    var input = card.querySelector("[data-wizard-attachment-input]");
    if (input) {
      input.addEventListener("change", function () {
        uploadFiles(card, draftKey, input.files, function () {
          input.value = "";
          if (scheduleSave) {
            scheduleSave();
          }
        });
      });
    }

    var preview = card.querySelector("[data-wizard-attachment-preview]");
    if (preview) {
      preview.addEventListener("click", function (ev) {
        // 썸네일 클릭 → ERP order 방식 미리보기 모달(삭제는 모달 내부 버튼).
        var thumb = ev.target.closest("[data-attachment-index]");
        if (!thumb) {
          return;
        }
        var idx = parseInt(thumb.getAttribute("data-attachment-index"), 10);
        if (isNaN(idx)) {
          return;
        }
        openPreviewModal(card, idx, scheduleSave);
      });
    }
  }

  function bindAll(root, draftKey, scheduleSave) {
    if (!root) {
      return;
    }
    bindPreviewModal();
    root.querySelectorAll("[data-product-index]").forEach(function (card) {
      bindCard(card, draftKey, scheduleSave);
    });
    if (window.FOMSPhotoCapture && typeof window.FOMSPhotoCapture.initPhotoCapture === "function") {
      window.FOMSPhotoCapture.initPhotoCapture(root);
    }
  }

  function applyAttachments(card, attachments) {
    if (!card) {
      return;
    }
    card._wizardAttachments = [];
    if (Array.isArray(attachments)) {
      attachments.forEach(function (raw) {
        if (!raw || !raw.tmp_key) {
          return;
        }
        card._wizardAttachments.push({
          tmp_key: raw.tmp_key,
          filename: raw.filename || "",
          view_url: raw.view_url || "/api/files/view/" + encodeURIComponent(raw.tmp_key),
        });
      });
    }
    renderPreview(card);
  }

  function resetCard(card) {
    if (!card) {
      return;
    }
    card._wizardAttachments = [];
    renderPreview(card);
  }

  window.FomsWizardAttachments = {
    readAttachments: readAttachments,
    bindAll: bindAll,
    bindCard: bindCard,
    applyAttachments: applyAttachments,
    resetCard: resetCard,
    renderPreview: renderPreview,
  };
})();
