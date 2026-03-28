(function initWAMOrderDetail(window, document) {
  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
    } else {
      callback();
    }
  }

  function isObject(value) {
    return !!value && typeof value === "object" && !Array.isArray(value);
  }

  function getSections(bootstrap) {
    var page = isObject(bootstrap && bootstrap.page) ? bootstrap.page : {};
    return Array.isArray(page.sections) ? page.sections : [];
  }

  function getAttachmentCount(bootstrap) {
    var attachments = isObject(bootstrap && bootstrap.attachments) ? bootstrap.attachments : {};
    var count = attachments.count;
    return typeof count === "number" && isFinite(count) ? count : 0;
  }

  function getPageState(bootstrap) {
    var page = isObject(bootstrap && bootstrap.page) ? bootstrap.page : {};
    return (
      page.page_state ||
      (bootstrap && (bootstrap.pageState || bootstrap.page_state)) ||
      document.body.getAttribute("data-page-state") ||
      "unknown"
    );
  }

  function getViewKey() {
    return document.body.getAttribute("data-view-key") || "order-detail";
  }

  function buildTelemetryContext(bootstrap, stickyBar) {
    var sections = getSections(bootstrap);
    return {
      viewKey: getViewKey(),
      context: {
        page_state: getPageState(bootstrap),
        section_count: sections.length,
        section_keys: sections
          .map(function mapSection(section) {
            return section && section.key ? section.key : null;
          })
          .filter(Boolean),
        attachment_count: getAttachmentCount(bootstrap),
        sticky_bar_present: !!stickyBar
      }
    };
  }

  onReady(function startOrderDetail() {
    var core = window.WAMCore;
    var telemetry = window.WAMTelemetry;
    var root = document.getElementById("wam-shell");

    if (!core || !root) {
      return;
    }

    var bootstrap = core.parseBootstrap();
    var stickyBar = core.qs(root, ".wam-sticky-bar");
    var bootAt = window.performance && typeof window.performance.now === "function"
      ? window.performance.now()
      : 0;
    var sections = getSections(bootstrap);
    var telemetryContext = buildTelemetryContext(bootstrap, stickyBar);

    function syncStickyBarHeight() {
      if (!stickyBar) {
        return;
      }
      document.documentElement.style.setProperty(
        "--wam-runtime-sticky-bar-height",
        stickyBar.offsetHeight + "px"
      );
    }

    if (telemetry && typeof telemetry.configure === "function") {
      telemetry.configure(bootstrap, telemetryContext);
    }

    if (telemetry) {
      telemetry.emit("wam_page_opened", {
        view_key: telemetryContext.viewKey,
        page_state: getPageState(bootstrap),
        section_count: sections.length,
        attachment_count: getAttachmentCount(bootstrap),
        latency_ms: Math.round(bootAt)
      });
    }

    if (bootstrap) {
      if (telemetry) {
        telemetry.emit("wam_bootstrap_succeeded", {
          page_state: getPageState(bootstrap),
          section_count: sections.length,
          attachment_count: getAttachmentCount(bootstrap),
          telemetry_url_present: !!(
            bootstrap.api &&
            typeof bootstrap.api.telemetry_url === "string" &&
            bootstrap.api.telemetry_url
          ),
          telemetry_enabled: !!(
            bootstrap.flags &&
            bootstrap.flags.telemetry_enabled === true
          )
        });
      }
    } else if (telemetry) {
      telemetry.emit("wam_bootstrap_failed", {
        page_state: getPageState(null),
        section_count: 0,
        attachment_count: 0,
        reason: "bootstrap_parse_failed"
      });
    }

    core.bindSectionToggles(root);
    core.bindCopyButtons(root);
    syncStickyBarHeight();

    if (stickyBar && window.ResizeObserver) {
      var observer = new ResizeObserver(syncStickyBarHeight);
      observer.observe(stickyBar);
    }

    core.on(root, "click", "[data-open-section]", function handleOpenSection(event, target) {
      event.preventDefault();
      core.openSection(root, target.getAttribute("data-open-section"), true);
    });

    root.addEventListener("wam:section-toggled", function onSectionToggle(event) {
      if (!telemetry || !event.detail || !event.detail.expanded) {
        return;
      }

      if (event.detail.key === "timeline") {
        telemetry.emit("wam_timeline_opened", {
          section_key: event.detail.key,
          attachment_count: getAttachmentCount(bootstrap),
          latency_ms: Math.round(
            window.performance && typeof window.performance.now === "function"
              ? window.performance.now()
              : 0
          )
        });
      }

      telemetry.emit("wam_section_opened", {
        key: event.detail.key,
        section_key: event.detail.key,
        section_count: sections.length,
        attachment_count: getAttachmentCount(bootstrap),
        latency_ms: Math.round(
          window.performance && typeof window.performance.now === "function"
            ? window.performance.now()
            : 0
        )
      });
    });

    if (window.WAMAttachments) {
      window.WAMAttachments.init(root, bootstrap || {});
    }
  });
})(window, document);
