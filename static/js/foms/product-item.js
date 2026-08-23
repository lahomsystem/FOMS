/**
 * C14 foms-product-item-accordion — ERP order item rows (P1-04).
 */
(function () {
  "use strict";

  function productTitle(row) {
    var nameEl = row.querySelector('[data-erp="product_name"]');
    var name = nameEl && nameEl.value ? String(nameEl.value).trim() : "";
    return name || "제품명 미입력";
  }

  function formatPriceSummaryDisplay(priceEl) {
    if (!priceEl || !priceEl.value) return "";
    var raw = String(priceEl.value).trim();
    if (raw.endsWith("원")) return raw;
    var digits = raw.replace(/[^0-9]/g, "");
    if (!digits) return "";
    var n = parseInt(digits, 10);
    if (typeof window.erpFormatDepositDisplay === "function") {
      return window.erpFormatDepositDisplay(n);
    }
    return n.toLocaleString("ko-KR") + "원";
  }

  function buildSummary(row) {
    var specs = [];
    var rawSpecEl = row.querySelector('[data-erp="spec"]');
    var rawSpec = rawSpecEl && rawSpecEl.value ? String(rawSpecEl.value).trim() : "";
    if (rawSpec) {
      specs.push(rawSpec.replace(/\s+/g, " "));
    } else {
      row.querySelectorAll(".erp-spec-row").forEach(function (specRow) {
        var w = specRow.querySelector('[data-erp="spec_width"]');
        var d = specRow.querySelector('[data-erp="spec_depth"]');
        var h = specRow.querySelector('[data-erp="spec_height"]');
        var parts = [w, d, h]
          .map(function (el) {
            return el && el.value ? String(el.value).trim() : "";
          })
          .filter(Boolean);
        if (parts.length) specs.push(parts.join("×"));
      });
    }
    var priceEl = row.querySelector('[data-erp="price"]');
    var priceDisplay = formatPriceSummaryDisplay(priceEl);
    var chunks = [];
    if (specs.length) chunks.push(specs.join(" / "));
    if (priceDisplay) chunks.push(priceDisplay);
    return chunks.join(" · ") || productTitle(row);
  }

  function ensureAutosave(row) {
    var el = row.querySelector(".foms-product-item__autosave");
    if (el) return el;
    el = document.createElement("div");
    el.className = "foms-product-item__autosave";
    el.setAttribute("aria-live", "polite");
    el.innerHTML =
      '<span class="foms-product-item__autosave-dot"></span>' +
      '<span class="foms-product-item__autosave-text">실측 변경 즉시 저장됨</span>';
    row.appendChild(el);
    return el;
  }

  function ensureSummary(row) {
    var el = row.querySelector(".foms-product-item__summary");
    if (el) return el;
    el = document.createElement("div");
    el.className = "foms-product-item__summary";
    row.appendChild(el);
    return el;
  }

  function toggleRow(row, collapsed) {
    row.classList.toggle("foms-product-item--collapsed", collapsed);
    var head = row.querySelector(".foms-product-item__head");
    if (head) {
      head.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    var expand = row.querySelector(".foms-product-item__expand");
    if (expand) {
      expand.textContent = collapsed ? "⌄" : "⌃";
      expand.setAttribute("aria-label", collapsed ? "펼치기" : "접기");
    }
    ensureSummary(row).textContent = buildSummary(row);
  }

  function wrapRowBodies(row) {
    row.querySelectorAll(
      ":scope > .row, :scope > .col-12, :scope > div:not(.foms-product-item__head):not(.foms-product-item__summary):not(.foms-product-item__autosave)"
    ).forEach(function (el) {
      el.classList.add("foms-product-item__body");
    });
  }

  function enhanceHead(row, idx) {
    var headBar = row.querySelector(".foms-product-item__head");
    if (!headBar) {
      headBar = row.querySelector(".d-flex.justify-content-between");
    }
    if (!headBar) return;

    headBar.classList.add("foms-product-item__head");
    headBar.setAttribute("role", "button");
    headBar.setAttribute("tabindex", "0");

    var removeBtn = headBar.querySelector(".erp-remove-item-btn");
    var titleLegacy = headBar.querySelector(".erp-item-title");

    if (!headBar.querySelector(".foms-product-item__index")) {
      var indexEl = document.createElement("span");
      indexEl.className = "foms-product-item__index";
      headBar.insertBefore(indexEl, headBar.firstChild);
    }
    if (!headBar.querySelector(".foms-product-item__title")) {
      var titleEl = document.createElement("span");
      titleEl.className = "foms-product-item__title";
      if (titleLegacy) {
        titleLegacy.replaceWith(titleEl);
      } else {
        headBar.insertBefore(titleEl, removeBtn || null);
      }
    }
    if (!headBar.querySelector(".foms-product-item__expand")) {
      var expandBtn = document.createElement("button");
      expandBtn.type = "button";
      expandBtn.className = "foms-product-item__expand";
      expandBtn.textContent = "⌃";
      expandBtn.setAttribute("aria-label", "접기");
      if (removeBtn) {
        headBar.insertBefore(expandBtn, removeBtn);
      } else {
        headBar.appendChild(expandBtn);
      }
    }

    if (!headBar.dataset.fomsAccordionBound) {
      headBar.dataset.fomsAccordionBound = "1";
      headBar.addEventListener("click", function (ev) {
        if (ev.target.closest(".erp-remove-item-btn")) return;
        if (ev.target.closest(".foms-product-item__expand")) {
          ev.stopPropagation();
        }
        toggleRow(row, !row.classList.contains("foms-product-item--collapsed"));
      });
      headBar.addEventListener("keydown", function (ev) {
        if (ev.key !== "Enter" && ev.key !== " ") return;
        ev.preventDefault();
        toggleRow(row, !row.classList.contains("foms-product-item--collapsed"));
      });
    }

    row.querySelector(".foms-product-item__index").textContent = "항목 " + (idx + 1);
    row.querySelector(".foms-product-item__title").textContent = productTitle(row);
  }

  function enhanceRow(row, idx, collapseDefault) {
    if (!row.classList.contains("erp-item-row")) return;
    row.classList.add("foms-product-item");
    row.dataset.fomsProductItem = "1";
    row.dataset.itemIndex = String(idx);
    enhanceHead(row, idx);
    wrapRowBodies(row);
    ensureSummary(row);
    ensureAutosave(row);
    toggleRow(row, !!collapseDefault);
  }

  // 마법사 카드 순번은 DOM 속성이 정본(삭제/복제 후 wizard.js가 다시 매긴다).
  function wizardCardNumber(row) {
    var idx = parseInt(row.getAttribute("data-product-index") || "0", 10);
    return (isNaN(idx) ? 0 : idx) + 1;
  }

  function toggleWizardRow(row, collapsed) {
    row.classList.toggle("foms-product-item--collapsed", collapsed);
    var head = row.querySelector("[data-foms-product-toggle], .foms-product-item__head");
    if (head) {
      head.setAttribute("aria-expanded", collapsed ? "false" : "true");
    }
    var expand = row.querySelector(".foms-product-item__expand");
    if (expand) {
      expand.textContent = collapsed ? "▾" : "▴";
      expand.setAttribute("aria-label", collapsed ? "펼치기" : "접기");
    }
    var summary = row.querySelector("[data-foms-product-summary]");
    if (summary) {
      summary.textContent = buildWizardSummary(row);
    }
  }

  function initWizardProducts(root) {
    var scope = root || document;
    scope.querySelectorAll(".foms-wizard__product-card[data-product-index]").forEach(function (row, idx) {
      if (row.dataset.fomsWizardProductBound === "1") {
        return;
      }
      row.dataset.fomsWizardProductBound = "1";
      var collapsed = idx > 0;
      row.classList.toggle("foms-product-item--collapsed", collapsed);
      var head = row.querySelector("[data-foms-product-toggle]");
      if (head) {
        head.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
      var expand = row.querySelector(".foms-product-item__expand");
      if (expand) {
        expand.textContent = collapsed ? "▾" : "▴";
      }
      var summary = row.querySelector("[data-foms-product-summary]");
      if (summary) {
        summary.textContent = readValue(row.querySelector('[data-product-field="product_name"]')) || "제품명을 입력하세요";
      }
      if (head) {
        head.addEventListener("click", function (ev) {
          // 삭제 버튼 클릭은 접기/펴기가 아니다(wizard.js 위임 핸들러가 처리).
          if (ev.target.closest && ev.target.closest("[data-foms-product-remove]")) {
            return;
          }
          toggleWizardRow(row, !row.classList.contains("foms-product-item--collapsed"));
        });
      }
      row.querySelectorAll("[data-product-field]").forEach(function (input) {
        input.addEventListener("input", function () {
          var titleEl = row.querySelector("[data-foms-product-title]");
          if (titleEl && input.getAttribute("data-product-field") === "product_name") {
            titleEl.textContent = readValue(input) || "제품 " + wizardCardNumber(row);
          }
          if (summary) {
            summary.textContent = buildWizardSummary(row);
          }
        });
      });
    });
  }

  function readValue(el) {
    return el && el.value ? String(el.value).trim() : "";
  }

  function buildWizardSummary(row) {
    var specRow = row.querySelector("[data-spec-row]");
    var parts = ["spec_width", "spec_depth", "spec_height"].map(function (field) {
      return readValue(specRow && specRow.querySelector('[data-product-field="' + field + '"]'));
    }).filter(Boolean);
    var chunks = [];
    if (parts.length) chunks.push(parts.join("×"));
    var priceDisplay = formatPriceSummaryDisplay(row.querySelector('[data-product-field="price"]'));
    if (priceDisplay) chunks.push(priceDisplay);
    return chunks.join(" · ") || readValue(row.querySelector('[data-product-field="product_name"]')) || "제품명 미입력";
  }

  function enhanceAll(root) {
    var wrap = (root || document).querySelector("#erp-items");
    if (!wrap) return;
    var rows = wrap.querySelectorAll(".erp-item-row");
    rows.forEach(function (row, idx) {
      var collapsed = idx > 0;
      if (row.dataset.fomsProductItem === "1") {
        enhanceHead(row, idx);
        ensureSummary(row).textContent = buildSummary(row);
        return;
      }
      enhanceRow(row, idx, collapsed);
    });
  }

  function bindTitleSync(root) {
    var wrap = (root || document).querySelector("#erp-items");
    if (!wrap || wrap.dataset.fomsProductItemBound) return;
    wrap.dataset.fomsProductItemBound = "1";
    wrap.addEventListener("input", function (ev) {
      var target = ev.target;
      if (!target || !target.dataset) return;
      var row = target.closest(".erp-item-row");
      if (!row) return;
      if (target.dataset.erp === "product_name") {
        var titleEl = row.querySelector(".foms-product-item__title");
        if (titleEl) titleEl.textContent = productTitle(row);
      }
      if (
        target.dataset.erp === "product_name" ||
        target.dataset.erp === "spec" ||
        target.dataset.erp === "spec_width" ||
        target.dataset.erp === "spec_depth" ||
        target.dataset.erp === "spec_height" ||
        target.dataset.erp === "price"
      ) {
        ensureSummary(row).textContent = buildSummary(row);
      }
    });
  }

  function showAutosave(row) {
    if (!row) return;
    ensureAutosave(row).classList.add("is-visible");
    window.setTimeout(function () {
      var autosave = row.querySelector(".foms-product-item__autosave");
      if (autosave) autosave.classList.remove("is-visible");
    }, 2200);
  }

  window.fomsProductItem = {
    enhance: enhanceAll,
    showAutosave: showAutosave,
    initWizardProducts: initWizardProducts,
    init: function (root) {
      root = root || document;
      enhanceAll(root);
      bindTitleSync(root);
      var wrap = root.querySelector("#erp-items");
      if (wrap && window.MutationObserver && !wrap.dataset.fomsProductItemObserver) {
        wrap.dataset.fomsProductItemObserver = "1";
        new MutationObserver(function () {
          enhanceAll(root);
        }).observe(wrap, { childList: true, subtree: false });
      }
    },
  };

  document.addEventListener("foms-inline-saved", function (ev) {
    var detail = ev.detail || {};
    if (detail.itemIndex == null) return;
    var rows = document.querySelectorAll("#erp-items .erp-item-row");
    showAutosave(rows[detail.itemIndex]);
  });

  document.addEventListener("DOMContentLoaded", function () {
    initWizardProducts(document);
  });
  document.addEventListener("foms:wizard-product-added", function (ev) {
    var row = ev.detail && ev.detail.row;
    if (row) initWizardProducts(row.parentElement || document);
  });
})();
