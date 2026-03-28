(function initWAMAttachments(window, document) {
  if (window.WAMAttachments) {
    return;
  }

  function createAttachmentItem(item) {
    var wrapper = document.createElement("article");
    wrapper.className = "wam-attachment-item";

    var header = document.createElement("div");
    header.className = "wam-attachment-item__header";

    var copy = document.createElement("div");
    var title = document.createElement("p");
    title.textContent = item.name || item.label || "첨부 파일";
    copy.appendChild(title);

    var meta = document.createElement("p");
    meta.className = "wam-attachment-item__meta";
    meta.textContent = item.category || "분류 없음";
    copy.appendChild(meta);

    var actions = document.createElement("div");
    actions.className = "wam-attachment-item__actions";

    if (item.open_url || item.url) {
      var openLink = document.createElement("a");
      openLink.className = "wam-inline-action";
      openLink.href = item.open_url || item.url;
      openLink.target = "_blank";
      openLink.rel = "noopener noreferrer";
      openLink.textContent = "보기";
      actions.appendChild(openLink);
    }

    if (item.download_url) {
      var downloadLink = document.createElement("a");
      downloadLink.className = "wam-inline-action";
      downloadLink.href = item.download_url;
      downloadLink.target = "_blank";
      downloadLink.rel = "noopener noreferrer";
      downloadLink.textContent = "다운로드";
      actions.appendChild(downloadLink);
    }

    header.appendChild(copy);
    header.appendChild(actions);
    wrapper.appendChild(header);
    return wrapper;
  }

  function renderItems(list, items) {
    list.innerHTML = "";

    if (!items.length) {
      return;
    }

    items.forEach(function append(item) {
      list.appendChild(createAttachmentItem(item));
    });
  }

  function fetchAttachments(root, rail, bootstrap) {
    var core = window.WAMCore;
    var list = core.qs(rail, "[data-attachment-list]");
    var skeleton = core.qs(rail, "[data-attachment-skeleton]");
    var url = (((bootstrap || {}).api || {}).attachments_url);

    if (!list || !url || rail.dataset.attachmentLoaded === "true") {
      return;
    }

    if (window.WAMTelemetry) {
      window.WAMTelemetry.emit("wam_attachments_opened", {});
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
    if (!core) {
      return;
    }

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
        fetchAttachments(root, rail, bootstrap);
      }
    });

    core.on(root, "click", "[data-attachment-retry]", function retry(event) {
      event.preventDefault();
      rail.dataset.attachmentLoaded = "false";
      fetchAttachments(root, rail, bootstrap);
    });

    if (rail.dataset.attachmentCount === "0") {
      rail.dataset.attachmentLoaded = "true";
    }

    core.on(root, "click", ".wam-attachment-item__actions a", function trackClick() {
      if (window.WAMTelemetry) {
        window.WAMTelemetry.emit("wam_attachment_clicked", {});
      }
    });
  }

  window.WAMAttachments = {
    init: init
  };
})(window, document);
