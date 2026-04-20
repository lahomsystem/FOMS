(function initWAMAttachments(window, document) {
  if (window.WAMAttachments) {
    return;
  }

  var IMAGE_PATTERN = /\.(jpg|jpeg|png|gif|webp|bmp|svg|heic|heif)(\?|$)/i;
  var VIDEO_PATTERN = /\.(mp4|webm|ogg|mov)(\?|$)/i;
  var PDF_PATTERN = /\.(pdf)(\?|$)/i;

  var modalState = {
    openItem: null,
    scale: 1,
    pinchStartDistance: 0,
    pinchStartScale: 1,
    modalBound: false
  };

  function qs(root, selector) {
    return root ? root.querySelector(selector) : null;
  }

  function textOrFallback(value, fallback) {
    var text = value == null ? "" : String(value).trim();
    return text || fallback;
  }

  function normalizeAttachment(item) {
    var fileType = String(item && item.file_type ? item.file_type : "").toLowerCase();
    var viewUrl = String(item && (item.open_url || item.view_url || item.url) ? (item.open_url || item.view_url || item.url) : "").trim();
    var downloadUrl = String(item && item.download_url ? item.download_url : "").trim();
    var filename = textOrFallback(item && (item.filename || item.name || item.label), "Attachment file");
    var category = textOrFallback(item && item.category, "Uncategorized");
    var thumbnailUrl = String(item && item.thumbnail_url ? item.thumbnail_url : "").trim();
    return {
      id: item && item.id ? item.id : null,
      file_type: fileType || "file",
      filename: filename,
      category: category,
      view_url: viewUrl,
      download_url: downloadUrl,
      thumbnail_url: thumbnailUrl,
      size_label: textOrFallback(item && item.size_label, ""),
      created_at_label: textOrFallback(item && item.created_at_label, ""),
      kind_label: item && item.kind_label ? String(item.kind_label) : ""
    };
  }

  function isImage(item) {
    var fileType = String(item && item.file_type ? item.file_type : "").toLowerCase();
    var probe = String(item && (item.view_url || item.filename || "")).toLowerCase();
    return fileType === "image" || IMAGE_PATTERN.test(probe);
  }

  function isVideo(item) {
    var fileType = String(item && item.file_type ? item.file_type : "").toLowerCase();
    var probe = String(item && (item.view_url || item.filename || "")).toLowerCase();
    return fileType === "video" || VIDEO_PATTERN.test(probe);
  }

  function isPdf(item) {
    var fileType = String(item && item.file_type ? item.file_type : "").toLowerCase();
    var probe = String(item && (item.view_url || item.filename || "")).toLowerCase();
    return fileType === "pdf" || PDF_PATTERN.test(probe);
  }

  function emitTelemetry(eventName, payload) {
    if (window.WAMTelemetry && typeof window.WAMTelemetry.emit === "function") {
      window.WAMTelemetry.emit(eventName, payload || {});
    }
  }

  function buildPreviewCard(item) {
    var normalized = normalizeAttachment(item);
    var article = document.createElement("article");
    article.className = "wam-attachment-rail__preview wam-attachment-rail__preview--clickable";
    article.setAttribute("role", "button");
    article.setAttribute("tabindex", "0");
    article.setAttribute("aria-label", normalized.filename);
    article.dataset.attachmentOpen = "true";
    article.dataset.attachmentId = normalized.id != null ? String(normalized.id) : "";
    article.dataset.attachmentViewUrl = normalized.view_url;
    article.dataset.attachmentDownloadUrl = normalized.download_url;
    article.dataset.attachmentFilename = normalized.filename;
    article.dataset.attachmentFileType = normalized.file_type;
    article.dataset.attachmentCategory = normalized.category;
    article.dataset.attachmentThumbnailUrl = normalized.thumbnail_url;
    article.dataset.attachmentSizeLabel = normalized.size_label;
    article.dataset.attachmentCreatedAtLabel = normalized.created_at_label;

    var thumb = document.createElement("div");
    thumb.className = "wam-attachment-rail__thumb";
    thumb.setAttribute("aria-hidden", "true");
    if (normalized.thumbnail_url) {
      var img = document.createElement("img");
      img.src = normalized.thumbnail_url;
      img.alt = "";
      thumb.appendChild(img);
    } else {
      thumb.textContent = normalized.kind_label || (isImage(normalized) ? "IMAGE" : "FILE");
    }

    var copy = document.createElement("div");
    copy.className = "wam-attachment-rail__copy";

    var name = document.createElement("p");
    name.className = "wam-attachment-rail__name";
    name.textContent = normalized.filename;
    copy.appendChild(name);

    var meta = document.createElement("p");
    meta.className = "wam-attachment-rail__meta";
    meta.textContent = normalized.category;
    copy.appendChild(meta);

    article.appendChild(thumb);
    article.appendChild(copy);
    return article;
  }

  function buildListItem(item) {
    var normalized = normalizeAttachment(item);
    var article = document.createElement("article");
    article.className = "wam-attachment-item wam-attachment-item--interactive";
    article.setAttribute("role", "button");
    article.setAttribute("tabindex", "0");
    article.setAttribute("aria-label", normalized.filename);
    article.dataset.attachmentOpen = "true";
    article.dataset.attachmentId = normalized.id != null ? String(normalized.id) : "";
    article.dataset.attachmentViewUrl = normalized.view_url;
    article.dataset.attachmentDownloadUrl = normalized.download_url;
    article.dataset.attachmentFilename = normalized.filename;
    article.dataset.attachmentFileType = normalized.file_type;
    article.dataset.attachmentCategory = normalized.category;
    article.dataset.attachmentThumbnailUrl = normalized.thumbnail_url;
    article.dataset.attachmentSizeLabel = normalized.size_label;
    article.dataset.attachmentCreatedAtLabel = normalized.created_at_label;

    var header = document.createElement("div");
    header.className = "wam-attachment-item__header";

    var main = document.createElement("div");
    main.className = "wam-attachment-item__main";

    var thumb = document.createElement("div");
    thumb.className = "wam-attachment-rail__thumb wam-attachment-item__thumb";
    thumb.setAttribute("aria-hidden", "true");
    if (normalized.thumbnail_url) {
      var img = document.createElement("img");
      img.src = normalized.thumbnail_url;
      img.alt = "";
      thumb.appendChild(img);
    } else {
      thumb.textContent = normalized.kind_label || (isImage(normalized) ? "IMAGE" : "FILE");
    }

    var copy = document.createElement("div");
    copy.className = "wam-attachment-rail__copy wam-attachment-item__copy";

    var name = document.createElement("p");
    name.className = "wam-attachment-item__name";
    name.textContent = normalized.filename;
    copy.appendChild(name);

    var meta = document.createElement("p");
    meta.className = "wam-attachment-item__meta";
    var metaBits = [normalized.category, normalized.size_label, normalized.created_at_label].filter(Boolean);
    meta.textContent = metaBits.length ? metaBits.join(" · ") : normalized.category;
    copy.appendChild(meta);

    main.appendChild(thumb);
    main.appendChild(copy);
    header.appendChild(main);

    var actions = document.createElement("div");
    actions.className = "wam-attachment-item__actions";
    if (normalized.download_url) {
      var downloadLink = document.createElement("a");
      downloadLink.className = "wam-inline-action wam-inline-action--button wam-attachment-download";
      downloadLink.href = normalized.download_url;
      downloadLink.target = "_blank";
      downloadLink.rel = "noopener noreferrer";
      downloadLink.textContent = "다운로드";
      downloadLink.setAttribute("data-attachment-download", "true");
      actions.appendChild(downloadLink);
    }

    header.appendChild(actions);
    article.appendChild(header);
    return article;
  }

  function renderItems(list, items) {
    list.innerHTML = "";
    items.forEach(function append(item) {
      list.appendChild(buildListItem(item));
    });
  }

  function getViewerElements() {
    var modal = document.getElementById("wam-attachment-modal");
    if (!modal) {
      return null;
    }
    return {
      modal: modal,
      title: document.getElementById("wam-attachment-modal-title"),
      meta: document.getElementById("wam-attachment-modal-meta"),
      stage: document.getElementById("wam-attachment-modal-stage"),
      download: document.getElementById("wam-attachment-modal-download")
    };
  }

  function clampScale(value) {
    return Math.max(1, Math.min(4, value));
  }

  function updateImageScale(shell, scale) {
    var nextScale = clampScale(scale);
    modalState.scale = nextScale;
    shell.style.setProperty("--wam-attachment-scale", String(nextScale));
  }

  function bindZoom(shell) {
    shell.addEventListener("wheel", function onWheel(event) {
      if (!modalState.openItem || modalState.openItem.kind !== "image") {
        return;
      }
      event.preventDefault();
      var delta = event.deltaY > 0 ? -0.12 : 0.12;
      updateImageScale(shell, modalState.scale + delta);
    }, { passive: false });

    shell.addEventListener("dblclick", function onDoubleClick() {
      if (modalState.openItem && modalState.openItem.kind === "image") {
        updateImageScale(shell, 1);
      }
    });

    shell.addEventListener("touchstart", function onTouchStart(event) {
      if (!modalState.openItem || modalState.openItem.kind !== "image" || event.touches.length < 2) {
        return;
      }
      var dx = event.touches[0].clientX - event.touches[1].clientX;
      var dy = event.touches[0].clientY - event.touches[1].clientY;
      modalState.pinchStartDistance = Math.sqrt(dx * dx + dy * dy);
      modalState.pinchStartScale = modalState.scale;
    }, { passive: true });

    shell.addEventListener("touchmove", function onTouchMove(event) {
      if (!modalState.openItem || modalState.openItem.kind !== "image" || event.touches.length < 2) {
        return;
      }
      if (!modalState.pinchStartDistance) {
        return;
      }
      event.preventDefault();
      var dx = event.touches[0].clientX - event.touches[1].clientX;
      var dy = event.touches[0].clientY - event.touches[1].clientY;
      var distance = Math.sqrt(dx * dx + dy * dy);
      if (!distance) {
        return;
      }
      updateImageScale(shell, modalState.pinchStartScale * (distance / modalState.pinchStartDistance));
    }, { passive: false });

    shell.addEventListener("touchend", function onTouchEnd(event) {
      if (event.touches.length < 2) {
        modalState.pinchStartDistance = 0;
      }
    }, { passive: true });
  }

  function renderImageStage(shell, item) {
    shell.innerHTML = "";
    shell.style.setProperty("--wam-attachment-scale", "1");

    var imageShell = document.createElement("div");
    imageShell.className = "wam-attachment-modal__image-shell";

    var image = document.createElement("img");
    image.className = "wam-attachment-modal__image";
    image.src = item.view_url;
    image.alt = item.filename;
    image.loading = "eager";
    imageShell.appendChild(image);

    var hint = document.createElement("p");
    hint.className = "wam-attachment-modal__footer-note";
    hint.textContent = "핀치로 확대/축소하고, 확대 후에는 스크롤로 이동할 수 있습니다.";
    imageShell.appendChild(hint);

    shell.appendChild(imageShell);
    bindZoom(imageShell);
  }

  function renderVideoStage(shell, item) {
    shell.innerHTML = "";

    var panel = document.createElement("div");
    panel.className = "wam-attachment-modal__file-panel";

    var video = document.createElement("video");
    video.className = "wam-attachment-modal__iframe";
    video.src = item.view_url;
    video.controls = true;
    video.playsInline = true;
    panel.appendChild(video);

    var note = document.createElement("p");
    note.className = "wam-attachment-modal__footer-note";
    note.textContent = "비디오 파일은 재생 컨트롤을 사용할 수 있습니다.";
    panel.appendChild(note);

    shell.appendChild(panel);
  }

  function renderIframeStage(shell, item) {
    shell.innerHTML = "";

    var panel = document.createElement("div");
    panel.className = "wam-attachment-modal__file-panel";

    if (item.view_url) {
      var iframe = document.createElement("iframe");
      iframe.className = "wam-attachment-modal__iframe";
      iframe.src = item.view_url;
      iframe.title = item.filename;
      iframe.loading = "eager";
      panel.appendChild(iframe);
    } else {
      var fallback = document.createElement("div");
      fallback.className = "wam-attachment-modal__fallback";

      var fallbackTitle = document.createElement("p");
      fallbackTitle.className = "wam-attachment-modal__fallback-title";
      fallbackTitle.textContent = item.filename;
      fallback.appendChild(fallbackTitle);

      var fallbackBody = document.createElement("p");
      fallbackBody.className = "wam-attachment-modal__fallback-body";
      fallbackBody.textContent = "이 파일 형식은 미리보기를 지원하지 않습니다. 다운로드 버튼을 사용해 주세요.";
      fallback.appendChild(fallbackBody);

      panel.appendChild(fallback);
    }

    shell.appendChild(panel);
  }

  function openModal(item) {
    var normalized = normalizeAttachment(item);
    var elements = getViewerElements();
    if (!elements) {
      return;
    }

    modalState.openItem = {
      id: normalized.id,
      kind: isImage(normalized) ? "image" : (isVideo(normalized) ? "video" : (isPdf(normalized) ? "document" : "file")),
      view_url: normalized.view_url,
      download_url: normalized.download_url,
      filename: normalized.filename,
      file_type: normalized.file_type,
      category: normalized.category,
      size_label: normalized.size_label,
      created_at_label: normalized.created_at_label
    };

    elements.title.textContent = normalized.filename;
    var metaBits = [normalized.category, normalized.size_label, normalized.created_at_label].filter(Boolean);
    elements.meta.textContent = metaBits.length ? metaBits.join(" · ") : "";
    elements.download.href = normalized.download_url || normalized.view_url || "#";
    elements.download.hidden = !normalized.download_url && !normalized.view_url;

    if (modalState.openItem.kind === "image") {
      renderImageStage(elements.stage, modalState.openItem);
    } else if (modalState.openItem.kind === "video") {
      renderVideoStage(elements.stage, modalState.openItem);
    } else {
      renderIframeStage(elements.stage, modalState.openItem);
    }

    elements.modal.hidden = false;
    elements.modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("is-attachment-modal-open");
    document.body.style.overflow = "hidden";

    emitTelemetry("wam_attachment_clicked", {
      attachment_id: normalized.id,
      file_type: normalized.file_type,
      category: normalized.category
    });

    if (typeof elements.download.focus === "function") {
      elements.download.focus();
    }
  }

  function closeModal() {
    var elements = getViewerElements();
    if (!elements) {
      return;
    }

    elements.modal.hidden = true;
    elements.modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-attachment-modal-open");
    document.body.style.overflow = "";
    modalState.openItem = null;
    modalState.scale = 1;
    modalState.pinchStartDistance = 0;
    modalState.pinchStartScale = 1;
    if (elements.stage) {
      elements.stage.innerHTML = "";
    }
  }

  function openFromElement(element) {
    openModal({
      id: element.getAttribute("data-attachment-id"),
      view_url: element.getAttribute("data-attachment-view-url"),
      download_url: element.getAttribute("data-attachment-download-url"),
      filename: element.getAttribute("data-attachment-filename"),
      file_type: element.getAttribute("data-attachment-file-type"),
      category: element.getAttribute("data-attachment-category"),
      thumbnail_url: element.getAttribute("data-attachment-thumbnail-url"),
      size_label: element.getAttribute("data-attachment-size-label"),
      created_at_label: element.getAttribute("data-attachment-created-at-label")
    });
  }

  function bindModalEvents() {
    if (modalState.modalBound) {
      return;
    }
    modalState.modalBound = true;

    document.addEventListener("click", function onDocumentClick(event) {
      var closeTarget = event.target.closest("[data-attachment-modal-close]");
      if (closeTarget) {
        event.preventDefault();
        closeModal();
        return;
      }

      var openTarget = event.target.closest("[data-attachment-open]");
      if (openTarget) {
        if (event.target.closest("[data-attachment-download]")) {
          return;
        }
        event.preventDefault();
        openFromElement(openTarget);
      }
    });

    document.addEventListener("keydown", function onDocumentKeyDown(event) {
      if (event.key === "Escape" && !document.getElementById("wam-attachment-modal").hidden) {
        closeModal();
        return;
      }

      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }

      var trigger = event.target.closest("[data-attachment-open]");
      if (!trigger) {
        return;
      }

      event.preventDefault();
      openFromElement(trigger);
    });
  }

  function loadAttachments(root, rail, bootstrap) {
    var core = window.WAMCore;
    var list = core.qs(rail, "[data-attachment-list]");
    var skeleton = core.qs(rail, "[data-attachment-skeleton]");
    var url = (((bootstrap || {}).api || {}).attachments_url);

    if (!list || !url || rail.dataset.attachmentLoaded === "true") {
      return;
    }

    if (window.WAMTelemetry) {
      emitTelemetry("wam_attachments_opened", {});
    }

    fetch(url, { credentials: "same-origin" })
      .then(function (response) { return response.json(); })
      .then(function (payload) {
        if (!payload || payload.ok === false) {
          throw new Error("attachment_fetch_failed");
        }

        var items = [];
        (payload.groups || []).forEach(function (group) {
          (group.items || []).forEach(function (item) {
            items.push(item);
          });
        });

        if (skeleton) {
          skeleton.remove();
        }

        renderItems(list, items);
        rail.dataset.attachmentLoaded = "true";
      })
      .catch(function () {
        if (skeleton) {
          skeleton.innerHTML = '<p class="wam-attachment-rail__hint">첨부 정보를 불러오지 못했습니다.</p><button type="button" class="wam-inline-action wam-inline-action--button" data-attachment-retry>다시 시도</button>';
        }
      });
  }

  function init(root, bootstrap) {
    var core = window.WAMCore;
    if (!core || !root) {
      return;
    }

    bindModalEvents();

    var rail = core.qs(root, "[data-attachment-rail]");
    if (!rail) {
      return;
    }

    if ((((bootstrap || {}).flags || {}).attachments_lazy_enabled) === false) {
      renderItems(
        core.qs(rail, "[data-attachment-list]"),
        ((((bootstrap || {}).attachments || {}).items) || [])
      );
      rail.dataset.attachmentLoaded = "true";
      return;
    }

    root.addEventListener("wam:section-toggled", function onToggle(event) {
      if (event.detail && event.detail.key === "attachments" && event.detail.expanded) {
        loadAttachments(root, rail, bootstrap);
      }
    });

    core.on(root, "click", "[data-attachment-retry]", function retry(event) {
      event.preventDefault();
      rail.dataset.attachmentLoaded = "false";
      loadAttachments(root, rail, bootstrap);
    });

    if (rail.dataset.attachmentCount === "0") {
      rail.dataset.attachmentLoaded = "true";
    }
  }

  window.WAMAttachments = {
    init: init,
    open: openModal,
    close: closeModal
  };
})(window, document);
