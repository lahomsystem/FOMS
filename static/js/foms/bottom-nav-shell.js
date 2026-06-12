/**
 * P3-01: ERP mobile bottom-nav shell navigation + chrome sync after fragment swap.
 * Uses HTMX ajax when FOMS_BOTTOM_NAV_HTMX_ENABLED; always syncs active tab + header.
 */
(function () {
  "use strict";

  var NAV_PATH_MAP = [
    { id: "dashboard", prefix: "/erp/dashboard" },
    { id: "measurement", prefix: "/erp/measurement" },
    { id: "drawing_workbench", prefix: "/erp/drawing-workbench" },
    { id: "production", prefix: "/erp/production" },
    { id: "shipment", prefix: "/erp/shipment" },
    { id: "as", prefix: "/erp/as" },
    { id: "construction", prefix: "/erp/construction" },
    { id: "completion", prefix: "/erp/completion" },
    { id: "history", prefix: "/erp/history" },
  ];

  var NAV_LABELS = {
    dashboard: "대시보드",
    measurement: "실측",
    drawing_workbench: "도면",
    production: "생산",
    shipment: "출고",
    as: "AS",
    construction: "시공",
    completion: "완료",
    history: "이력",
  };

  function pathToNavId(pathname) {
    var best = null;
    NAV_PATH_MAP.forEach(function (row) {
      if (pathname === row.prefix || pathname.indexOf(row.prefix + "/") === 0) {
        if (!best || row.prefix.length > best.prefix.length) {
          best = row;
        }
      }
    });
    return best ? best.id : null;
  }

  function syncMobileChrome(activeId, pathname) {
    var nav = document.querySelector(".erp-mobile-bottom-nav");
    if (nav) {
      nav.querySelectorAll(".erp-mobile-bottom-nav__item").forEach(function (el) {
        el.classList.remove("is-active");
        el.setAttribute("aria-current", "false");
      });
      if (activeId) {
        var link = nav.querySelector('[data-foms-nav-id="' + activeId + '"]');
        if (link) {
          link.classList.add("is-active");
          link.setAttribute("aria-current", "page");
        }
      }
    }
    var title = document.querySelector(".erp-mobile-shell-header__title");
    if (title && activeId && NAV_LABELS[activeId]) {
      title.textContent = NAV_LABELS[activeId];
    }
    if (pathname) {
      document.documentElement.setAttribute("data-foms-active-nav", activeId || "");
    }
  }

  function dispatchShellSwapped(url) {
    try {
      document.dispatchEvent(
        new CustomEvent("foms:erp-shell-fragment-swapped", { detail: { url: url || "" } })
      );
      document.dispatchEvent(
        new CustomEvent("foms:main-content-swapped", { detail: { url: url || "" } })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function activateScripts(container) {
    if (!container) return;
    container.querySelectorAll("script").forEach(function (old) {
      var s = document.createElement("script");
      if (old.type) s.type = old.type;
      if (old.src) {
        s.src = old.src;
        s.async = old.async;
        s.defer = old.defer;
      } else {
        s.textContent = old.textContent;
      }
      old.parentNode.replaceChild(s, old);
    });
  }

  function navigateBottomNavHtmx(href, navId) {
    var target = document.getElementById("main-content");
    if (!target || !window.htmx) {
      if (window.FOMS_ERP_SHELL && window.FOMS_ERP_SHELL.navigateByShell) {
        window.FOMS_ERP_SHELL.navigateByShell(href);
      } else {
        window.location.href = href;
      }
      return;
    }
    var url = new URL(href, window.location.origin);
    url.searchParams.set("view", "fragment");
    window.htmx
      .ajax("GET", url.toString(), {
        target: "#main-content",
        swap: "innerHTML",
        headers: {
          "X-FOMS-ERP-SHELL": "1",
          "X-Requested-With": "XMLHttpRequest",
        },
      })
      .then(function () {
        activateScripts(target);
        if (window.history && window.history.pushState) {
          window.history.pushState({ fomsBottomNavHtmx: true }, "", href);
        }
        syncMobileChrome(navId, url.pathname);
        dispatchShellSwapped(href);
      })
      .catch(function () {
        window.location.href = href;
      });
  }

  function onBottomNavClick(ev) {
    var shell = document.querySelector("[data-erp-mobile-shell]");
    if (!shell) return;
    var link = ev.target.closest(".erp-mobile-bottom-nav a[href][data-foms-nav-id]");
    if (!link) return;
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || link.target === "_blank") return;

    var htmxEnabled = shell.getAttribute("data-bottom-nav-htmx") === "true";
    if (!htmxEnabled) return;

    ev.preventDefault();
    ev.stopImmediatePropagation();
    navigateBottomNavHtmx(link.getAttribute("href"), link.getAttribute("data-foms-nav-id"));
  }

  function onFragmentSwapped(ev) {
    var shell = document.querySelector("[data-erp-mobile-shell]");
    if (!shell) return;
    var url = (ev && ev.detail && ev.detail.url) || window.location.href;
    var pathname = "";
    try {
      pathname = new URL(url, window.location.origin).pathname;
    } catch (e) {
      pathname = window.location.pathname;
    }
    syncMobileChrome(pathToNavId(pathname), pathname);
  }

  document.addEventListener("click", onBottomNavClick, true);
  document.addEventListener("foms:erp-shell-fragment-swapped", onFragmentSwapped);
  document.addEventListener("DOMContentLoaded", function () {
    syncMobileChrome(pathToNavId(window.location.pathname), window.location.pathname);
  });
  window.addEventListener("popstate", function () {
    syncMobileChrome(pathToNavId(window.location.pathname), window.location.pathname);
  });

  window.fomsSyncMobileBottomNav = syncMobileChrome;
})();
