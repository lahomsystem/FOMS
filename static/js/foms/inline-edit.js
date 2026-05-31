/**
 * ERP order inline field save (P1-04).
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 400;
  var UNDO_MS = 5000;
  var updatedAt = null;
  var orderId = null;
  var undoTimer = null;
  var undoSnapshot = null;

  var FIELD_MAP = {
    "erp-customer-phone": { path: "parties.customer.phone", critical: true },
    "erp-address": { path: "site.address_full", critical: true },
    "erp-measurement-date": { path: "schedule.measurement.date", critical: true },
    "erp-construction-date": { path: "schedule.construction.date", critical: true },
  };

  var ITEM_FIELDS = {
    internal: { critical: false },
    color: { critical: false },
    option_detail: { critical: false },
    handle: { critical: false },
    misc: { critical: false },
    extra_input: { critical: false },
    price: { critical: true },
    measurement_date: { critical: true },
    construction_date: { critical: true },
  };

  function toast(message, undoFn) {
    var el = document.getElementById("foms-inline-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "foms-inline-toast";
      el.className = "foms-inline-toast";
      document.body.appendChild(el);
    }
    el.innerHTML = "";
    el.appendChild(document.createTextNode(message));
    if (undoFn) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "foms-inline-toast__undo";
      btn.textContent = "실행 취소";
      btn.addEventListener("click", function () {
        undoFn();
        el.classList.remove("is-visible");
      });
      el.appendChild(btn);
    }
    el.classList.add("is-visible");
    setTimeout(function () {
      el.classList.remove("is-visible");
    }, undoFn ? UNDO_MS : 2200);
  }

  function patchField(fieldPath, value, previousValue, critical) {
    return fetch("/api/orders/" + orderId + "/structured/fields", {
      method: "PATCH",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-If-Match": updatedAt || "",
      },
      body: JSON.stringify({ field: fieldPath, value: value }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { status: res.status, data: data };
        });
      })
      .then(function (result) {
        if (result.status === 409) {
          window.alert("다른 기기에서 변경되었습니다. 새로고침 후 다시 시도해주세요.");
          return false;
        }
        if (!result.data || !result.data.success) {
          toast("저장 실패");
          return false;
        }
        updatedAt = result.data.structured_updated_at || updatedAt;
        if (critical && previousValue !== undefined) {
          if (undoTimer) clearTimeout(undoTimer);
          undoSnapshot = { field: fieldPath, value: previousValue };
          toast("저장됨", function () {
            patchField(fieldPath, previousValue, undefined, false);
          });
        } else {
          toast("저장됨");
        }
        return true;
      })
      .catch(function () {
        toast("저장 실패");
        return false;
      });
  }

  function itemIndexFromRow(row) {
    var rows = Array.prototype.slice.call(
      document.querySelectorAll("#erp-items .card, #erp-items .erp-item-row, #erp-items > div")
    );
    return Math.max(0, rows.indexOf(row));
  }

  function bindHeaderFields(root) {
    Object.keys(FIELD_MAP).forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      var meta = FIELD_MAP[id];
      el.setAttribute("data-foms-inline", meta.path);
      if (meta.critical) {
        el.setAttribute("data-foms-inline-critical", "1");
        var wrap = el.closest(".col-md-6, .col-md-4, .col-12") || el.parentElement;
        if (wrap && !wrap.querySelector(".foms-inline-save-btn")) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "foms-btn foms-btn--sm foms-inline-save-btn";
          btn.textContent = "저장";
          btn.addEventListener("click", function () {
            patchField(meta.path, el.value, el.dataset.fomsInlinePrev || el.defaultValue, true);
          });
          wrap.appendChild(btn);
        }
        el.addEventListener("focus", function () {
          el.dataset.fomsInlinePrev = el.value;
        });
      } else {
        el.addEventListener("blur", function () {
          patchField(meta.path, el.value);
        });
      }
    });
  }

  function bindItemDelegation() {
    var wrap = document.getElementById("erp-items");
    if (!wrap) return;
    var debounceMap = {};
    wrap.addEventListener("blur", function (ev) {
      var target = ev.target;
      if (!target || !target.dataset || !target.dataset.erp) return;
      var key = target.dataset.erp;
      if (!ITEM_FIELDS[key]) return;
      var row =
        target.closest(".card") ||
        target.closest(".erp-item-row") ||
        target.closest("[data-item-index]") ||
        target.closest("#erp-items > div");
      if (!row) return;
      var idx = itemIndexFromRow(row);
      var path = "items." + idx + "." + key;
      target.setAttribute("data-foms-inline", path);
      if (ITEM_FIELDS[key].critical) {
        target.setAttribute("data-foms-inline-critical", "1");
        return;
      }
      var timerKey = path;
      if (debounceMap[timerKey]) clearTimeout(debounceMap[timerKey]);
      debounceMap[timerKey] = setTimeout(function () {
        patchField(path, target.value);
      }, DEBOUNCE_MS);
    }, true);

    wrap.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-foms-inline-save-item]");
      if (!btn) return;
      var row = btn.closest(".card, .erp-item-row, #erp-items > div");
      if (!row) return;
      var idx = itemIndexFromRow(row);
      row.querySelectorAll("[data-erp]").forEach(function (input) {
        var key = input.dataset.erp;
        if (!ITEM_FIELDS[key] || !ITEM_FIELDS[key].critical) return;
        var prev = input.dataset.fomsInlinePrev || "";
        patchField("items." + idx + "." + key, input.value, prev, true);
      });
    });

    wrap.addEventListener("focusin", function (ev) {
      var target = ev.target;
      if (!target || !target.dataset || !target.dataset.erp) return;
      if (ITEM_FIELDS[target.dataset.erp] && ITEM_FIELDS[target.dataset.erp].critical) {
        target.dataset.fomsInlinePrev = target.value;
      }
    });
  }

  function loadUpdatedAt() {
    return fetch("/api/orders/" + orderId + "/structured", { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        if (body && body.success) {
          updatedAt = body.structured_updated_at || null;
        }
      })
      .catch(function () {
        /* optional */
      });
  }

  function wrapAccordions(root) {
    var wrap = root.querySelector("#erp-items");
    if (!wrap) return;
    wrap.querySelectorAll(".erp-item-row").forEach(function (row) {
      if (row.dataset.fomsAccordion === "1") return;
      row.dataset.fomsAccordion = "1";
      row.classList.add("foms-product-item");
      var headBar = row.querySelector(".d-flex.justify-content-between");
      if (headBar) {
        headBar.classList.add("foms-product-item__head");
        headBar.setAttribute("role", "button");
        headBar.setAttribute("aria-expanded", "true");
        headBar.addEventListener("click", function (ev) {
          if (ev.target.closest(".erp-remove-item-btn")) return;
          row.classList.toggle("foms-product-item--collapsed");
          headBar.setAttribute(
            "aria-expanded",
            row.classList.contains("foms-product-item--collapsed") ? "false" : "true"
          );
        });
      }
      row.querySelectorAll(":scope > .row, :scope > .col-12, :scope > div:not(.foms-product-item__head)").forEach(function (el) {
        el.classList.add("foms-product-item__body");
      });
    });
  }

  function init() {
    var config = document.getElementById("erp-order-config");
    if (!config || config.getAttribute("data-foms-inline-enabled") !== "true") {
      return;
    }
    orderId = Number(config.getAttribute("data-order-id") || 0);
    if (!orderId) return;

    document.body.classList.add("foms-inline-enabled");
    var root = document.getElementById("erp-order") || document;
    var onboarding = document.getElementById("foms-inline-onboarding");
    if (!onboarding) {
      onboarding = document.createElement("div");
      onboarding.id = "foms-inline-onboarding";
      onboarding.className = "foms-inline-onboarding";
      onboarding.textContent =
        "일반 필드는 입력 후 자동 저장됩니다. 금액·일정·연락처·주소는 저장 버튼을 눌러주세요.";
      var formPane = root.querySelector("#erp-form");
      if (formPane) formPane.prepend(onboarding);
    }

    loadUpdatedAt().then(function () {
      bindHeaderFields(root);
      bindItemDelegation();
      wrapAccordions(root);
      var items = document.getElementById("erp-items");
      if (items && window.MutationObserver) {
        new MutationObserver(function () {
          wrapAccordions(root);
        }).observe(items, { childList: true, subtree: false });
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
