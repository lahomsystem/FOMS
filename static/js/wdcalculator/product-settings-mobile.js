/**
 * WDCalculator 제품 설정 모바일 향상 (additive · 모바일 전용).
 * docs/design/mockups/mobile-wdcalculator-product-settings.html 구현.
 * 기존 마크업/ID/CRUD JS는 일절 변경하지 않는다. 모바일(<=991.98px)에서만:
 *   - 모바일 헤더(뒤로 · 제품 설정 · 견적계산기)
 *   - 도메인 세그먼트 탭(제품 / 추가옵션 / 비고, 카운트 배지) → 한 번에 한 도메인
 *   - 테이블 → 카드 리스트(initial-* JSON 데이터 기반 렌더, 추가옵션/비고는 카테고리 그룹)
 *   - 추가/수정: 기존 <form>을 bottom sheet로 relocate(노드 이동 → ID/submit 핸들러 유지)
 *   - 카드 수정/삭제: 서버 렌더 버튼 .click() 위임 → CRUD/검증 로직은 호스트가 그대로 소유
 * 데스크톱(>=992px)에서는 enable()을 호출하지 않으므로 완전 무영향.
 */
(function () {
  "use strict";

  function onReady(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  onReady(function () {
    if (!document.getElementById("productForm")) return; // 제품 설정 페이지에서만
    var mq = window.matchMedia("(max-width: 991.98px)");
    var built = false;

    var TABS = [
      { key: "product", label: "제품" },
      { key: "option", label: "추가옵션" },
      { key: "note", label: "비고" },
    ];
    var ADD_LABEL = { product: "＋ 제품 추가", option: "＋ 옵션 추가", note: "＋ 비고 추가" };
    var ADD_TITLE = { product: "제품 추가", option: "추가 옵션 추가", note: "비고 추가" };
    var RESET_ID = { product: "resetFormBtn", option: "resetAdditionalOptionFormBtn", note: "resetNotesCategoryFormBtn" };
    var activeTab = sessionStorage.getItem("wdpsMobileTab") || "product";

    /* ---- 유틸 ---- */
    function parseData(id) {
      var el = document.getElementById(id);
      if (!el) return [];
      try {
        return JSON.parse(el.textContent) || [];
      } catch (e) {
        return [];
      }
    }
    function fmt(n) {
      return (Number(n) || 0).toLocaleString("ko-KR");
    }
    function esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    }
    function clickHost(selector) {
      var btn = document.querySelector(selector);
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    }

    /* ---- 헤더 ---- */
    function buildHeader() {
      if (document.querySelector(".wdps-head")) return;
      var calcLink = document.querySelector(".container-fluid a.btn-info[href]");
      var calcHref = calcLink ? calcLink.getAttribute("href") : "/wdcalculator";
      var h = document.createElement("header");
      h.className = "wdps-head";
      h.innerHTML =
        '<button type="button" class="wdps-icon" data-ps-back aria-label="뒤로">‹</button>' +
        '<div class="wdps-head__title">제품 설정</div>' +
        '<a class="wdps-icon" data-ps-calc aria-label="견적 계산기" href="' + calcHref + '">🧮</a>';
      document.body.insertBefore(h, document.body.firstChild);
      h.querySelector("[data-ps-back]").addEventListener("click", function () {
        if (window.history.length > 1) window.history.back();
        else window.location.href = calcHref;
      });
    }

    /* ---- 셸: 탭 + 본문 + 하단 추가바 ---- */
    function buildShell() {
      if (document.querySelector(".wdps-shell")) return;
      var shell = document.createElement("div");
      shell.className = "wdps-shell";
      shell.innerHTML =
        '<div class="wdps-tabs" role="tablist"></div>' +
        '<div class="wdps-body"></div>' +
        '<div class="wdps-addbar"><button type="button" class="wdps-btn wdps-btn--primary wdps-btn--full" data-ps-add></button></div>';
      document.body.appendChild(shell);
      var tabsEl = shell.querySelector(".wdps-tabs");
      TABS.forEach(function (t) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "wdps-tab";
        b.setAttribute("data-ps-tab", t.key);
        b.innerHTML = t.label + ' <span class="wdps-tab__n" data-ps-count="' + t.key + '">0</span>';
        b.addEventListener("click", function () {
          setTab(t.key);
        });
        tabsEl.appendChild(b);
      });
      shell.querySelector("[data-ps-add]").addEventListener("click", function () {
        openAdd(activeTab);
      });
    }

    function setTab(key) {
      activeTab = key;
      try {
        sessionStorage.setItem("wdpsMobileTab", key);
      } catch (e) {
        /* sessionStorage 비활성 환경: 탭 유지만 포기, 동작은 정상 */
      }
      var tabs = document.querySelectorAll(".wdps-tab");
      Array.prototype.forEach.call(tabs, function (b) {
        b.classList.toggle("is-active", b.getAttribute("data-ps-tab") === key);
      });
      var panels = document.querySelectorAll(".wdps-panel");
      Array.prototype.forEach.call(panels, function (p) {
        p.classList.toggle("is-active", p.getAttribute("data-ps-panel") === key);
      });
      var addBtn = document.querySelector("[data-ps-add]");
      if (addBtn) addBtn.textContent = ADD_LABEL[key];
    }

    function setCount(key, n) {
      var el = document.querySelector('[data-ps-count="' + key + '"]');
      if (el) el.textContent = n;
    }

    /* ---- 렌더 ---- */
    function panelEl(key) {
      var p = document.createElement("div");
      p.className = "wdps-panel";
      p.setAttribute("data-ps-panel", key);
      return p;
    }
    function emptyEl(msg) {
      var d = document.createElement("div");
      d.className = "wdps-empty";
      d.textContent = msg;
      return d;
    }

    function renderAll() {
      var body = document.querySelector(".wdps-body");
      if (!body) return;
      body.innerHTML = "";
      body.appendChild(renderProductPanel());
      body.appendChild(renderOptionPanel());
      body.appendChild(renderNotePanel());
      setTab(activeTab);
    }

    function renderProductPanel() {
      var p = panelEl("product");
      var products = parseData("initial-products");
      setCount("product", products.length);
      if (!products.length) {
        p.appendChild(emptyEl("등록된 제품이 없습니다. 하단 '제품 추가'를 눌러주세요."));
        return p;
      }
      products.forEach(function (pr) {
        p.appendChild(productCard(pr));
      });
      return p;
    }

    function productCard(pr) {
      var card = document.createElement("div");
      card.className = "wdps-card";
      var chips = "";
      if (pr.category) chips += '<span class="wdps-chip">' + esc(pr.category) + "</span>";
      if (pr.pricing_type === "1m") {
        chips += '<span class="wdps-chip">1m</span>';
        chips += '<span class="wdps-chip wdps-chip--price">1m <b>' + fmt(pr.price_1m) + "원</b></span>";
      } else {
        chips += '<span class="wdps-chip">30cm</span>';
        chips +=
          '<span class="wdps-chip wdps-chip--price">30cm <b>' +
          fmt(pr.price_30cm) +
          "원</b> · 1cm <b>" +
          fmt(pr.price_1cm) +
          "원</b></span>";
      }
      var coupon = "";
      if (pr.coupon_type === "percentage" && Number(pr.coupon_value) > 0) coupon = "쿠폰 할인율 " + pr.coupon_value + "%";
      else if (pr.coupon_type === "fixed" && Number(pr.coupon_value) > 0) coupon = "쿠폰 고정 " + fmt(pr.coupon_value) + "원";
      if (coupon) chips += '<span class="wdps-chip wdps-chip--coupon">' + coupon + "</span>";
      card.innerHTML =
        '<div class="wdps-card__top">' +
        '<div class="wdps-card__name">' +
        esc(pr.name) +
        "</div>" +
        '<div class="wdps-card__acts">' +
        '<button type="button" class="wdps-act" data-ps-edit-product="' + pr.id + '" aria-label="수정">✏</button>' +
        '<button type="button" class="wdps-act wdps-act--del" data-ps-del-product="' + pr.id + '" aria-label="삭제">🗑</button>' +
        "</div>" +
        "</div>" +
        '<div class="wdps-chips">' + chips + "</div>";
      card.querySelector("[data-ps-edit-product]").addEventListener("click", function () {
        if (clickHost('.edit-product-btn[data-product-id="' + pr.id + '"]')) openSheet("product", "제품 수정");
      });
      card.querySelector("[data-ps-del-product]").addEventListener("click", function () {
        clickHost('.delete-product-btn[data-product-id="' + pr.id + '"]');
      });
      return card;
    }

    function renderOptionPanel() {
      var p = panelEl("option");
      var cats = parseData("initial-categories");
      var total = 0;
      var frag = document.createDocumentFragment();
      cats.forEach(function (cat) {
        if (!cat || !cat.options) return;
        var opts = cat.options.filter(function (o) {
          return o && o.id;
        });
        if (!opts.length) return;
        total += opts.length;
        frag.appendChild(optionGroup(cat, opts));
      });
      setCount("option", total);
      if (!total) {
        p.appendChild(emptyEl("등록된 추가 옵션이 없습니다. 하단 '옵션 추가'를 눌러주세요."));
        return p;
      }
      p.appendChild(frag);
      return p;
    }

    function optionGroup(cat, opts) {
      var g = document.createElement("div");
      g.className = "wdps-group";
      var rows = opts
        .map(function (o) {
          return (
            '<div class="wdps-row">' +
            '<span class="wdps-row__name">' + esc(o.name) + "</span>" +
            '<span class="wdps-row__price">' + fmt(o.price) + "원</span>" +
            '<span class="wdps-row__acts">' +
            '<button type="button" class="wdps-act" data-ps-edit-option data-cat="' + cat.id + '" data-opt="' + o.id + '" aria-label="수정">✏</button>' +
            '<button type="button" class="wdps-act wdps-act--del" data-ps-del-option data-cat="' + cat.id + '" data-opt="' + o.id + '" aria-label="삭제">🗑</button>' +
            "</span>" +
            "</div>"
          );
        })
        .join("");
      g.innerHTML =
        '<div class="wdps-group__head"><span class="wdps-group__name">📂 ' +
        esc(cat.name) +
        ' <span class="wdps-group__n">' + opts.length + "</span></span></div>" +
        rows;
      Array.prototype.forEach.call(g.querySelectorAll("[data-ps-edit-option]"), function (b) {
        b.addEventListener("click", function () {
          if (clickHost('.edit-additional-option-btn[data-category-id="' + b.dataset.cat + '"][data-option-id="' + b.dataset.opt + '"]'))
            openSheet("option", "추가 옵션 수정");
        });
      });
      Array.prototype.forEach.call(g.querySelectorAll("[data-ps-del-option]"), function (b) {
        b.addEventListener("click", function () {
          clickHost('.delete-additional-option-btn[data-category-id="' + b.dataset.cat + '"][data-option-id="' + b.dataset.opt + '"]');
        });
      });
      return g;
    }

    function renderNotePanel() {
      var p = panelEl("note");
      var cats = parseData("initial-notes-categories");
      var total = 0;
      var frag = document.createDocumentFragment();
      cats.forEach(function (cat) {
        if (!cat || !cat.options) return;
        // 서버 렌더와 동일하게: 이름 있는 옵션만 노출하되 data-option-index는 원본 배열 인덱스 유지
        var named = [];
        cat.options.forEach(function (o, idx) {
          if (o && o.name) named.push({ o: o, idx: idx });
        });
        if (!named.length) return;
        total += named.length;
        frag.appendChild(noteGroup(cat, named));
      });
      setCount("note", total);
      if (!total) {
        p.appendChild(emptyEl("등록된 비고 카테고리가 없습니다. 하단 '비고 추가'를 눌러주세요."));
        return p;
      }
      p.appendChild(frag);
      return p;
    }

    function noteGroup(cat, named) {
      var g = document.createElement("div");
      g.className = "wdps-group";
      var rows = named
        .map(function (it) {
          var o = it.o;
          return (
            '<div class="wdps-row wdps-row--note">' +
            '<span class="wdps-row__name">' + esc(o.name) + "</span>" +
            '<span class="wdps-row__acts">' +
            '<button type="button" class="wdps-act" data-ps-edit-note data-cat="' + cat.id + '" data-opt="' + (o.id || "") + '" data-idx="' + it.idx + '" aria-label="수정">✏</button>' +
            '<button type="button" class="wdps-act wdps-act--del" data-ps-del-note data-cat="' + cat.id + '" data-opt="' + (o.id || "") + '" data-idx="' + it.idx + '" aria-label="삭제">🗑</button>' +
            "</span>" +
            "</div>"
          );
        })
        .join("");
      g.innerHTML =
        '<div class="wdps-group__head"><span class="wdps-group__name">📝 ' +
        esc(cat.name) +
        ' <span class="wdps-group__n">' + named.length + "</span></span></div>" +
        rows;
      function noteSelector(b) {
        var cat = b.dataset.cat,
          opt = b.dataset.opt,
          idx = b.dataset.idx;
        if (opt) return '[data-category-id="' + cat + '"][data-option-id="' + opt + '"]';
        return '[data-category-id="' + cat + '"][data-option-index="' + idx + '"]';
      }
      Array.prototype.forEach.call(g.querySelectorAll("[data-ps-edit-note]"), function (b) {
        b.addEventListener("click", function () {
          if (clickHost(".edit-notes-option-btn" + noteSelector(b))) openSheet("note", "비고 수정");
        });
      });
      Array.prototype.forEach.call(g.querySelectorAll("[data-ps-del-note]"), function (b) {
        b.addEventListener("click", function () {
          clickHost(".delete-notes-option-btn" + noteSelector(b));
        });
      });
      return g;
    }

    /* ---- 시트: 기존 <form> 노드를 그대로 이동(ID·submit 핸들러 유지) ---- */
    function relocateForm(formId, key, label) {
      var form = document.getElementById(formId);
      if (!form || document.querySelector('.wdps-sheet[data-ps-sheet="' + key + '"]')) return;
      var backdrop = document.createElement("div");
      backdrop.className = "wdps-backdrop";
      backdrop.setAttribute("data-ps-backdrop", key);
      backdrop.hidden = true;
      var sheet = document.createElement("div");
      sheet.className = "wdps-sheet";
      sheet.setAttribute("data-ps-sheet", key);
      sheet.hidden = true;
      sheet.innerHTML =
        '<div class="wdps-sheet__grip"></div>' +
        '<div class="wdps-sheet__head"><span class="wdps-sheet__title">' + label + ' 추가</span>' +
        '<button type="button" class="wdps-icon" data-ps-sheet-close aria-label="닫기">✕</button></div>' +
        '<div class="wdps-sheet__body"></div>';
      document.body.appendChild(backdrop);
      document.body.appendChild(sheet);
      sheet.querySelector(".wdps-sheet__body").appendChild(form);
      backdrop.addEventListener("click", function () {
        closeSheet(key);
      });
      sheet.querySelector("[data-ps-sheet-close]").addEventListener("click", function () {
        closeSheet(key);
      });
      // 제출 성공 시 호스트가 location.reload() → 별도 닫기 불필요.
    }
    function buildSheets() {
      relocateForm("productForm", "product", "제품");
      relocateForm("additionalOptionForm", "option", "추가 옵션");
      relocateForm("notesCategoryForm", "note", "비고");
    }

    function openSheet(key, title) {
      var sheet = document.querySelector('.wdps-sheet[data-ps-sheet="' + key + '"]');
      var backdrop = document.querySelector('[data-ps-backdrop="' + key + '"]');
      if (!sheet || !backdrop) return;
      if (title) sheet.querySelector(".wdps-sheet__title").textContent = title;
      sheet.hidden = false;
      backdrop.hidden = false;
      document.body.classList.add("wdps-sheet-open");
      var firstInput = sheet.querySelector("input:not([type=hidden]), select, textarea");
      if (firstInput && firstInput.focus) {
        setTimeout(function () {
          firstInput.focus();
        }, 60);
      }
    }
    function closeSheet(key) {
      var sheet = document.querySelector('.wdps-sheet[data-ps-sheet="' + key + '"]');
      var backdrop = document.querySelector('[data-ps-backdrop="' + key + '"]');
      if (sheet) sheet.hidden = true;
      if (backdrop) backdrop.hidden = true;
      document.body.classList.remove("wdps-sheet-open");
    }
    function openAdd(key) {
      var rb = document.getElementById(RESET_ID[key]); // 폼 리셋 + 편집상태 해제(호스트 소유)
      if (rb) rb.click();
      openSheet(key, ADD_TITLE[key]);
    }

    function enable() {
      if (built) return;
      built = true;
      document.body.classList.add("ps-mobile");
      buildHeader();
      buildShell();
      buildSheets();
      renderAll();
    }

    if (mq.matches) enable();
    var onChange = function (e) {
      if (e.matches) enable();
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  });
})();
