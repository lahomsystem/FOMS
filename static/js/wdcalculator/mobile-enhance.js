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

    function enable() {
      if (built) return;
      built = true;
      document.body.classList.add("wd-calc-mobile");
      buildHeader();
      buildSheet();
      buildTotalbar();
    }

    if (mq.matches) enable();
    var onChange = function (e) {
      if (e.matches) enable();
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  });
})();
