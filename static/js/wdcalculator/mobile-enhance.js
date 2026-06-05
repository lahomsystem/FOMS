/**
 * WDCalculator 모바일 향상 (additive · 모바일 전용).
 * 기존 마크업/ID/계산 JS는 일절 변경하지 않는다. 모바일(<=991.98px)에서만:
 *   - 모바일 툴 헤더 생성(뒤로 · 견적 계산기 · 저장견적 · 제품설정)
 *   - 저장된 견적 사이드바를 bottom sheet로 relocate(노드 이동 → ID/이벤트 유지)
 *   - 하단 sticky 총액바 생성(#finalPrice 라이브 미러, +견적추가/저장은 기존 버튼 위임)
 * 데스크톱(>=992px)에서는 enable()을 호출하지 않으므로 완전 무영향.
 */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  onReady(function () {
    var root = document.querySelector(".wdcalculator-container");
    if (!root) return; // 계산기 페이지에서만
    var mq = window.matchMedia("(max-width: 991.98px)");
    var built = false;

    function buildHeader() {
      if (document.querySelector(".wd-mhead")) return;
      var h = document.createElement("header");
      h.className = "wd-mhead";
      h.innerHTML =
        '<button type="button" class="wd-mhead__btn" data-wd-back aria-label="뒤로">‹</button>' +
        '<div class="wd-mhead__title">견적 계산기</div>' +
        '<div class="wd-mhead__actions">' +
        '<button type="button" class="wd-mhead__btn" data-wd-saved aria-label="저장된 견적">🗂<span class="wd-mhead__dot" data-wd-saved-count></span></button>' +
        '<a class="wd-mhead__btn" data-wd-settings aria-label="제품 설정">⚙</a>' +
        "</div>";
      document.body.insertBefore(h, document.body.firstChild);
      h.querySelector("[data-wd-back]").addEventListener("click", function () {
        if (window.history.length > 1) window.history.back();
        else window.location.href = "/erp/dashboard";
      });
      var pcLink = document.querySelector('a[href*="product-settings"]');
      h.querySelector("[data-wd-settings]").setAttribute(
        "href",
        pcLink ? pcLink.getAttribute("href") : "/wdcalculator/product-settings"
      );
      h.querySelector("[data-wd-saved]").addEventListener("click", openSheet);
    }

    function buildSheet() {
      if (document.querySelector(".wd-msheet")) return;
      var sidebar = document.querySelector(".saved-estimates-sidebar");
      if (!sidebar) return;
      var backdrop = document.createElement("div");
      backdrop.className = "wd-msheet-backdrop";
      backdrop.hidden = true;
      var sheet = document.createElement("div");
      sheet.className = "wd-msheet";
      sheet.hidden = true;
      sheet.innerHTML =
        '<div class="wd-msheet__grip"></div>' +
        '<div class="wd-msheet__head"><span class="wd-msheet__title">저장된 견적</span>' +
        '<button type="button" class="wd-mhead__btn" data-wd-close aria-label="닫기">✕</button></div>' +
        '<div class="wd-msheet__body"></div>';
      document.body.appendChild(backdrop);
      document.body.appendChild(sheet);
      // 사이드바 노드를 그대로 sheet로 이동 → #savedEstimatesList 등 ID·바인딩 유지
      sheet.querySelector(".wd-msheet__body").appendChild(sidebar);
      backdrop.addEventListener("click", closeSheet);
      sheet.querySelector("[data-wd-close]").addEventListener("click", closeSheet);
    }

    function openSheet() {
      var s = document.querySelector(".wd-msheet");
      var b = document.querySelector(".wd-msheet-backdrop");
      if (s && b) {
        s.hidden = false;
        b.hidden = false;
        document.body.classList.add("wd-msheet-open");
      }
    }
    function closeSheet() {
      var s = document.querySelector(".wd-msheet");
      var b = document.querySelector(".wd-msheet-backdrop");
      if (s && b) {
        s.hidden = true;
        b.hidden = true;
        document.body.classList.remove("wd-msheet-open");
      }
    }

    function buildTotalbar() {
      if (document.querySelector(".wd-mtotal")) return;
      var bar = document.createElement("div");
      bar.className = "wd-mtotal";
      bar.innerHTML =
        '<div class="wd-mtotal__sum"><span class="wd-mtotal__label">최종 견적 (현재)</span>' +
        '<span class="wd-mtotal__val" data-wd-final>0원</span></div>' +
        '<div class="wd-mtotal__acts">' +
        '<button type="button" class="wd-mtotal__save" data-wd-save aria-label="견적 저장">💾</button>' +
        '<button type="button" class="wd-mtotal__add" data-wd-add>＋ 견적 추가</button>' +
        "</div>";
      document.body.appendChild(bar);
      bar.querySelector("[data-wd-add]").addEventListener("click", function () {
        var b = document.getElementById("addEstimateBtn");
        if (b) b.click();
      });
      bar.querySelector("[data-wd-save]").addEventListener("click", function () {
        var b = document.getElementById("saveEstimateBtn");
        if (b) b.click();
      });
      syncFinal();
      var fp = document.getElementById("finalPrice");
      if (fp && window.MutationObserver) {
        new MutationObserver(syncFinal).observe(fp, {
          childList: true,
          characterData: true,
          subtree: true,
        });
      }
    }

    function syncFinal() {
      var fp = document.getElementById("finalPrice");
      var out = document.querySelector("[data-wd-final]");
      if (fp && out) out.textContent = (fp.textContent || "0원").trim();
    }

    /* ---- 기본 구성 카드: collapsed accordion 요약 + 라이브 단가칩 + 구성 소계 ----
       공유 렌더러(renderBaseComponentRow)는 건드리지 않고, 렌더된 행을 모바일에서만
       progressive-disclosure 카드로 향상. 소계는 기존 가격 엔진을 단일 행으로
       재호출(wdcComputeCurrentEstimateMath([row]...))해 계산 → 가격 로직 중복 없음. */
    function forEachNode(list, fn) {
      if (!list) return;
      Array.prototype.forEach.call(list, fn);
    }
    function getProductList() {
      var st = window.WdCalculatorProductsState;
      return (st && typeof st.getProducts === "function" && st.getProducts()) || [];
    }
    function readBaseRows() {
      var ui = window.WdCalculatorBaseComponentsUI;
      return (ui && typeof ui.readBaseComponentsFromUI === "function" && ui.readBaseComponentsFromUI()) || [];
    }
    function fmtNum(n) {
      var v = Number(n) || 0;
      if (typeof window.formatNumber === "function") return window.formatNumber(v);
      return v.toLocaleString("ko-KR");
    }
    function computeRowSubtotal(row) {
      var fn = window.wdcComputeCurrentEstimateMath;
      if (typeof fn !== "function") return 0;
      try {
        var math = fn([row], getProductList(), []);
        return (math && Number(math.basePriceCalculate)) || 0;
      } catch (e) {
        return 0;
      }
    }
    function describeBaseRow(row) {
      var products = getProductList();
      var mode = (row && row.mode) || "select";
      var width = Number(row && row.widthMm) || 0;
      var name = "";
      var unitText = "";
      var chipHtml = "";
      if (mode === "manual") {
        var mp = (row && row.manualPricing) || {};
        if (mp.pricing_type === "1m") {
          var p1m = Number(mp.price_1m) || 0;
          name = "직접입력 (1m)";
          unitText = "1m " + fmtNum(p1m);
          chipHtml = p1m ? "1m <b>" + fmtNum(p1m) + "원</b>" : "";
        } else {
          var p30 = Number(mp.price_30cm) || 0;
          var p1 = Number(mp.price_1cm) || 0;
          name = "직접입력 (30cm)";
          unitText = "30cm " + fmtNum(p30);
          chipHtml = p30 ? "30cm <b>" + fmtNum(p30) + "원</b> · 1cm <b>" + fmtNum(p1) + "원</b>" : "";
        }
      } else {
        var prod = products.filter(function (p) {
          return String(p.id) === String(row && row.productId);
        })[0];
        if (prod) {
          name = prod.name || "제품";
          if (prod.pricing_type === "1m") {
            var pp1m = Number(prod.price_1m) || 0;
            unitText = "1m " + fmtNum(pp1m);
            chipHtml = pp1m ? "1m <b>" + fmtNum(pp1m) + "원</b>" : "";
          } else {
            var pp30 = Number(prod.price_30cm) || 0;
            var pp1 = Number(prod.price_1cm) || 0;
            unitText = "30cm " + fmtNum(pp30);
            chipHtml = pp30 ? "30cm <b>" + fmtNum(pp30) + "원</b> · 1cm <b>" + fmtNum(pp1) + "원</b>" : "";
          }
        } else {
          name = "제품 미선택";
        }
      }
      var specParts = [mode === "manual" ? "직접" : "선택"];
      if (width > 0) specParts.push(fmtNum(width) + "mm");
      if (unitText) specParts.push(unitText);
      return { name: name, spec: specParts.join(" · "), chipHtml: chipHtml };
    }

    function enhanceBaseRow(rowEl, expand) {
      if (!rowEl || rowEl.classList.contains("wd-bc-enh")) return;
      rowEl.classList.add("wd-bc-enh");
      var summary = document.createElement("button");
      summary.type = "button";
      summary.className = "wd-bc-summary";
      summary.innerHTML =
        '<span class="wd-bc-idx"></span>' +
        '<span class="wd-bc-text"><span class="wd-bc-name"></span><span class="wd-bc-spec"></span></span>' +
        '<span class="wd-bc-price"></span>' +
        '<span class="wd-bc-chev">▾</span>';
      rowEl.insertBefore(summary, rowEl.firstChild);
      summary.addEventListener("click", function () {
        rowEl.classList.toggle("wd-open");
      });
      var body = rowEl.querySelector(".card-body");
      if (body) {
        var chip = document.createElement("div");
        chip.className = "wd-bc-chip";
        var feesList = body.querySelector(".base-additional-fees-list");
        var feeWrap = feesList ? feesList.closest(".mt-2") : null;
        body.insertBefore(chip, feeWrap || null);
        var sub = document.createElement("div");
        sub.className = "wd-bc-sub";
        sub.innerHTML = '<span>구성 소계</span><span class="wd-bc-subval">0원</span>';
        body.appendChild(sub);
      }
      if (expand) rowEl.classList.add("wd-open");
    }

    function refreshBaseSummaries() {
      var container = document.getElementById("baseComponentsContainer");
      if (!container) return;
      var rowEls = container.querySelectorAll(".base-component-row");
      var data = readBaseRows();
      forEachNode(rowEls, function (rowEl, i) {
        var row = data[i] || {};
        var info = describeBaseRow(row);
        var price = computeRowSubtotal(row);
        var idxEl = rowEl.querySelector(".wd-bc-idx");
        if (idxEl) idxEl.textContent = String(i + 1);
        var nameEl = rowEl.querySelector(".wd-bc-name");
        if (nameEl) nameEl.textContent = info.name;
        var specEl = rowEl.querySelector(".wd-bc-spec");
        if (specEl) specEl.textContent = info.spec;
        var priceEl = rowEl.querySelector(".wd-bc-price");
        if (priceEl) priceEl.textContent = fmtNum(price) + "원";
        var chipEl = rowEl.querySelector(".wd-bc-chip");
        if (chipEl) {
          chipEl.innerHTML = info.chipHtml;
          chipEl.style.display = info.chipHtml ? "" : "none";
        }
        var subValEl = rowEl.querySelector(".wd-bc-subval");
        if (subValEl) subValEl.textContent = fmtNum(price) + "원";
      });
    }

    var refreshScheduled = false;
    function scheduleBaseRefresh() {
      if (refreshScheduled) return;
      refreshScheduled = true;
      setTimeout(function () {
        refreshScheduled = false;
        refreshBaseSummaries();
      }, 0);
    }

    function initBaseEnhancements() {
      var container = document.getElementById("baseComponentsContainer");
      if (!container) return;
      forEachNode(container.querySelectorAll(".base-component-row"), function (rowEl) {
        enhanceBaseRow(rowEl, false);
      });
      refreshBaseSummaries();
      if (window.MutationObserver) {
        // 재렌더/행추가 시 새 행을 향상. 신규 행도 항상 collapsed(사용자 요청):
        // 추가 후 요약만 보이고, 편집은 탭해서 펼침.
        new MutationObserver(function () {
          forEachNode(container.querySelectorAll(".base-component-row:not(.wd-bc-enh)"), function (rowEl) {
            enhanceBaseRow(rowEl, false);
          });
          scheduleBaseRefresh();
        }).observe(container, { childList: true });
      }
      container.addEventListener("input", scheduleBaseRefresh);
      container.addEventListener("change", scheduleBaseRefresh);
    }

    /* ---- 할인·배송 → 하단 collapsed accordion (고급/선택 설정) ---- */
    function buildAdvancedAccordion() {
      var scroll = document.querySelector(".wdcalculator-main-scroll");
      if (!scroll || document.querySelector(".wd-macc")) return;
      var rows = Array.prototype.slice.call(scroll.children).filter(function (el) {
        return (
          el.classList &&
          el.classList.contains("row") &&
          el.classList.contains("mt-4") &&
          (el.querySelector("#globalCouponValue") || el.querySelector("#shippingCost"))
        );
      });
      if (!rows.length) return;
      var details = document.createElement("details");
      details.className = "wd-macc";
      details.innerHTML =
        '<summary class="wd-macc__sum"><span class="wd-macc__title">⚙ 할인 · 배송 설정</span>' +
        '<span class="wd-macc__chev">▾</span></summary>' +
        '<div class="wd-macc__body"></div>';
      scroll.appendChild(details);
      var body = details.querySelector(".wd-macc__body");
      rows.forEach(function (r) {
        body.appendChild(r);
      });
    }

    /* ---- 추가 옵션 / 비고: 아이콘 토글 → 불러오기|직접 세그먼트 (목업 동일) ----
       공유 렌더러는 그대로 두고, 모바일에서만 각 행 상단에 세그먼트를 주입.
       세그먼트 버튼은 기존 토글 버튼(.toggle-note-type / [data-toggle-direct-input])을
       대신 click 해 동작 → 계산/모드 전환 로직은 호스트 코드가 그대로 소유. */
    function observeChildList(container, cb) {
      if (!container || !window.MutationObserver) return;
      new MutationObserver(function () {
        cb();
      }).observe(container, { childList: true });
    }
    function buildSegment() {
      var seg = document.createElement("div");
      seg.className = "wd-seg";
      seg.innerHTML =
        '<button type="button" class="wd-seg__btn" data-seg="select">불러오기</button>' +
        '<button type="button" class="wd-seg__btn" data-seg="input">직접</button>';
      return seg;
    }
    function setSegActive(seg, mode) {
      forEachNode(seg.querySelectorAll(".wd-seg__btn"), function (b) {
        if (b.getAttribute("data-seg") === mode) b.classList.add("is-active");
        else b.classList.remove("is-active");
      });
    }
    function enhanceToggleItem(item, cfg) {
      if (!item || item.classList.contains("wd-seg-enh")) return;
      var toggleBtn = item.querySelector(cfg.toggleSelector);
      var probe = item.querySelector(cfg.probeSelector);
      if (!toggleBtn || !probe) return;
      item.classList.add("wd-seg-enh");
      toggleBtn.classList.add("wd-seg-src");
      var seg = buildSegment();
      item.insertBefore(seg, item.firstChild);
      function currentMode() {
        return probe.style.display !== "none" ? "select" : "input";
      }
      function sync() {
        setSegActive(seg, currentMode());
      }
      sync();
      seg.addEventListener("click", function (e) {
        var btn = e.target.closest(".wd-seg__btn");
        if (!btn) return;
        if (btn.getAttribute("data-seg") !== currentMode()) {
          toggleBtn.click();
        }
        sync(); // 옵션: 호스트가 동기 전환 → 즉시 반영
        setTimeout(sync, 0); // 비고: 노드 재생성 대비(옵저버가 재향상도 수행)
      });
      var selChange = item.querySelector(cfg.probeSelector);
      if (selChange) {
        selChange.addEventListener("change", function () {
          setTimeout(sync, 0);
        });
      }
    }
    function initToggleEnhancements() {
      var optContainer = document.getElementById("additionalOptionsContainer");
      var noteContainer = document.getElementById("notesContainer");
      var optCfg = { toggleSelector: "[data-toggle-direct-input]", probeSelector: "[data-category-option-select]" };
      var noteCfg = { toggleSelector: ".toggle-note-type", probeSelector: ".note-select" };
      function enhanceOpts() {
        if (!optContainer) return;
        forEachNode(optContainer.querySelectorAll(".additional-option-item"), function (it) {
          enhanceToggleItem(it, optCfg);
        });
      }
      function enhanceNotes() {
        if (!noteContainer) return;
        forEachNode(noteContainer.querySelectorAll(".note-item"), function (it) {
          enhanceToggleItem(it, noteCfg);
        });
      }
      enhanceOpts();
      enhanceNotes();
      observeChildList(optContainer, enhanceOpts);
      observeChildList(noteContainer, enhanceNotes);
    }

    /* ---- 모바일 select 피커: PC 드롭다운 → bottom sheet (목업 톤) ----
       native <select>는 데이터 소스로 유지(호스트 change 위임·계약 보존).
       모바일에서 select 탭 시 native 팝업을 막고 sheet로 옵션 선택 → value 설정 +
       change 디스패치. 동적 행/옵션은 body 위임 + 열 때 live 옵션 읽기로 자동 대응. */
    function isMobileSelect(sel) {
      if (!sel || sel.tagName !== "SELECT") return false;
      return (
        sel.classList.contains("base-product-select") ||
        sel.hasAttribute("data-category-option-select") ||
        sel.classList.contains("note-select")
      );
    }
    function ensureSelectSheet() {
      if (document.querySelector(".wd-selsheet")) return;
      var backdrop = document.createElement("div");
      backdrop.className = "wd-selsheet-backdrop";
      backdrop.hidden = true;
      var sheet = document.createElement("div");
      sheet.className = "wd-selsheet";
      sheet.hidden = true;
      sheet.innerHTML =
        '<div class="wd-msheet__grip"></div>' +
        '<div class="wd-msheet__head"><span class="wd-selsheet__title">선택</span>' +
        '<button type="button" class="wd-mhead__btn" data-wd-selclose aria-label="닫기">✕</button></div>' +
        '<div class="wd-selsheet__body"></div>';
      document.body.appendChild(backdrop);
      document.body.appendChild(sheet);
      backdrop.addEventListener("click", closeSelectSheet);
      sheet.querySelector("[data-wd-selclose]").addEventListener("click", closeSelectSheet);
    }
    function closeSelectSheet() {
      var sheet = document.querySelector(".wd-selsheet");
      var backdrop = document.querySelector(".wd-selsheet-backdrop");
      if (sheet) sheet.hidden = true;
      if (backdrop) backdrop.hidden = true;
    }
    function selectFieldLabel(sel) {
      var wrap = sel.closest(".field, .mb-3, .col-md-5, .base-select-area, .base-component-row");
      var label = wrap ? wrap.querySelector("label") : null;
      var txt = label ? (label.textContent || "").trim() : "";
      return txt || "선택";
    }
    function openSelectSheet(sel) {
      ensureSelectSheet();
      var sheet = document.querySelector(".wd-selsheet");
      var backdrop = document.querySelector(".wd-selsheet-backdrop");
      var body = sheet.querySelector(".wd-selsheet__body");
      sheet.querySelector(".wd-selsheet__title").textContent = selectFieldLabel(sel);
      body.innerHTML = "";
      forEachNode(sel.options, function (opt) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "wd-selsheet__opt" + (opt.value === sel.value ? " is-active" : "");
        item.textContent = opt.textContent;
        item.addEventListener("click", function () {
          if (sel.value !== opt.value) {
            sel.value = opt.value;
            sel.dispatchEvent(new Event("change", { bubbles: true }));
          }
          closeSelectSheet();
        });
        body.appendChild(item);
      });
      sheet.hidden = false;
      backdrop.hidden = false;
      var active = body.querySelector(".wd-selsheet__opt.is-active");
      if (active && active.scrollIntoView) active.scrollIntoView({ block: "center" });
    }
    function initMobileSelects() {
      // mousedown preventDefault → native 팝업 차단 후 sheet 오픈(위임 → 동적 행 대응)
      document.body.addEventListener("mousedown", function (e) {
        var sel = e.target && e.target.closest ? e.target.closest("select") : null;
        if (!isMobileSelect(sel)) return;
        e.preventDefault();
        openSelectSheet(sel);
      });
      // 키보드 접근성: 포커스 후 Enter/Space로도 오픈
      document.body.addEventListener("keydown", function (e) {
        var sel = e.target && e.target.closest ? e.target.closest("select") : null;
        if (!isMobileSelect(sel)) return;
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
          e.preventDefault();
          openSelectSheet(sel);
        }
      });
    }

    /* ---- 진행 중인 견적 리스트: PC 카드 → 모바일 컴팩트 톤 ----
       renderEstimatesList()가 인라인 !important 스타일을 박아넣어 CSS로 못 덮음.
       모바일에서만 견적 카드 내부의 인라인 스타일을 제거해 모바일 CSS가 적용되게 함.
       수정/삭제/이름수정 버튼은 document 위임(handleEstimateListClick)이라
       클래스·data-estimate-id만 보존되면 동작 유지 → 마크업 구조는 건드리지 않음. */
    function mobilizeEstimatesList() {
      var container = document.getElementById("estimatesListContainer");
      if (!container) return;
      forEachNode(container.querySelectorAll(".card[data-estimate-id] [style]"), function (el) {
        el.removeAttribute("style");
      });
      var summary = document.getElementById("totalEstimatesSummary");
      if (summary) {
        forEachNode(summary.querySelectorAll("[style]"), function (el) {
          el.removeAttribute("style");
        });
      }
    }
    function initEstimatesListMobile() {
      var container = document.getElementById("estimatesListContainer");
      if (!container) return;
      mobilizeEstimatesList();
      observeChildList(container, mobilizeEstimatesList);
    }

    function enable() {
      if (built) return;
      built = true;
      document.body.classList.add("wd-calc-mobile");
      buildHeader();
      buildSheet();
      buildTotalbar();
      initBaseEnhancements();
      initToggleEnhancements();
      initMobileSelects();
      initEstimatesListMobile();
      buildAdvancedAccordion();
    }

    if (mq.matches) enable();
    var onChange = function (e) {
      if (e.matches) enable();
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  });
})();
