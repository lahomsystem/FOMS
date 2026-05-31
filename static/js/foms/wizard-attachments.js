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
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "foms-wizard__attachment-thumb";
      btn.setAttribute("data-attachment-index", String(idx));
      btn.setAttribute("aria-label", entry.filename || "첨부");
      if (entry.view_url) {
        var img = document.createElement("img");
        img.src = entry.view_url;
        img.alt = entry.filename || "";
        btn.appendChild(img);
      } else {
        btn.textContent = entry.filename || "파일";
      }
      preview.appendChild(btn);
    });
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
        var btn = ev.target.closest("[data-attachment-index]");
        if (!btn) {
          return;
        }
        var idx = parseInt(btn.getAttribute("data-attachment-index"), 10);
        if (isNaN(idx) || !Array.isArray(card._wizardAttachments)) {
          return;
        }
        card._wizardAttachments.splice(idx, 1);
        renderPreview(card);
        if (scheduleSave) {
          scheduleSave();
        }
      });
    }
  }

  function bindAll(root, draftKey, scheduleSave) {
    if (!root) {
      return;
    }
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
