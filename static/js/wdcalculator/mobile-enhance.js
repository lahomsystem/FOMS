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
      // [fix] 저장된 견적 '불러오기'(폴더) 클릭 → 로드되면 시트 자동 닫힘(수동 X 불필요).
      // host load 핸들러가 bubble서 stopPropagation + confirm → capture로 수신하고,
      // 로드 성공(고객명 반영) 시에만 닫음(confirm 취소 시 유지).
      sheet.addEventListener(
        "click",
        function (e) {
          var btn = e.target.closest(".load-estimate-btn");
          if (!btn) return;
          var row = btn.closest(".saved-estimate-row");
          var nameEl = row ? row.querySelector(".saved-estimate-customer-name") : null;
          var expectName = nameEl ? (nameEl.textContent || "").trim() : null;
          setTimeout(function () {
            var cur = document.getElementById("customerName");
            var curName = cur ? (cur.value || "").trim() : "";
            if (!expectName || curName === expectName) closeSheet();
          }, 80);
        },
        true
      );
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

    /* ============================================================
       [v3] 견적 빌더 셸 (master-detail). 리니어 sticky(buildTotalbar) 대체.
       master = 카트(고객칩 + 총액 HERO + 견적 카드 리스트),
       detail = 편집 bottom sheet(구성·옵션·비고 탭 + 할인·배송 + 완료).
       host 노드를 재배치하고 host 버튼을 위임 → 계산/CRUD/계약 로직 무변경.
       ============================================================ */
    var lastHero = null;
    var lastEditorFinal = null;
    var builderEditorWrap = null;

    function buildBuilderMaster() {
      if (document.querySelector(".wd-master")) return;
      var master = document.createElement("div");
      master.className = "wd-master";
      var cust = document.createElement("div");
      cust.className = "wd-cust";
      cust.innerHTML = '<span class="wd-cust__ic">👤</span>';
      var custInput = document.getElementById("customerName");
      if (custInput) cust.appendChild(custInput); // 노드 이동 → ID/핸들러 유지
      master.appendChild(cust);
      var hero = document.createElement("div");
      hero.className = "wd-hero";
      hero.innerHTML =
        '<div class="wd-hero__label">총 견적 (현재)</div>' +
        '<div class="wd-hero__val" data-wd-hero>0원</div>' +
        '<div class="wd-hero__meta">' +
        '<span class="wd-hero__pill" data-wd-hero-count>견적 0건</span>' +
        '<span class="wd-hero__pill" data-wd-hero-coupon>쿠폰가 미적용</span></div>';
      master.appendChild(hero);
      var ewrap = document.createElement("div");
      ewrap.className = "wd-editor-wrap";
      ewrap.innerHTML =
        '<div class="wd-editor"><div class="wd-editor__inner">' +
        '<div class="wd-editor__head"><div><div class="wd-editor__title">새 견적</div>' +
        '<div class="wd-editor__sub" data-wd-esub></div></div>' +
        '<button type="button" class="wd-editor__close" data-wd-eclose aria-label="닫기">✕</button>' +
        '</div></div></div>';
      builderEditorWrap = ewrap;
      master.appendChild(ewrap); // hero ↔ cart-head 사이 인라인 에디터 슬롯
      var ch = document.createElement("div");
      ch.className = "wd-cart-head";
      ch.innerHTML = '<span class="wd-cart-head__t">담은 견적</span>';
      master.appendChild(ch);
      var list = document.getElementById("estimatesListContainer");
      if (list) master.appendChild(list); // 카트로 이동(host가 ID로 렌더)
      var header = document.querySelector(".wd-mhead");
      if (header && header.nextSibling) document.body.insertBefore(master, header.nextSibling);
      else document.body.appendChild(master);
    }

    function moveSectionByContainer(containerId) {
      var c = document.getElementById(containerId);
      return c ? c.closest(".mb-3") : null;
    }

    function buildEsec(iconTitle, section, key) {
      var sec = document.createElement("div");
      sec.className = "wd-esec";
      sec.setAttribute("data-esec", key);
      sec.innerHTML =
        '<div class="wd-esec__head">' + iconTitle +
        '<span class="wd-esec__badge" data-esec-badge="' + key + '"></span></div>';
      if (section) sec.appendChild(section);
      return sec;
    }

    function updateEsecBadges() {
      var b = document.querySelector('[data-esec-badge="base"]');
      if (b) b.textContent = document.querySelectorAll("#baseComponentsContainer .base-component-row").length + "개";
      var o = document.querySelector('[data-esec-badge="opt"]');
      if (o) {
        var on = document.querySelectorAll("#additionalOptionsContainer .additional-option-item").length;
        var sum = (document.getElementById("totalAdditionalPrice") || {}).textContent;
        o.textContent = on ? (sum && sum.trim() !== "0원" ? sum.trim() : on + "개") : "";
      }
      var nb = document.querySelector('[data-esec-badge="note"]');
      if (nb) {
        var nn = document.querySelectorAll("#notesContainer .note-item").length;
        nb.textContent = nn ? nn + "개" : "";
      }
    }

    /* 인라인 에디터: 구성·옵션·비고 전 섹션을 한눈에(탭 없음). host 컨테이너를 섹션으로 이동. */
    function buildEditorPanel() {
      var inner = document.querySelector(".wd-editor__inner");
      if (!inner || inner.querySelector(".wd-esec")) return;
      inner.appendChild(buildEsec("🧱 구성", moveSectionByContainer("baseComponentsContainer"), "base"));
      inner.appendChild(buildEsec("➕ 옵션", moveSectionByContainer("additionalOptionsContainer"), "opt"));
      inner.appendChild(buildEsec("📝 비고", moveSectionByContainer("notesContainer"), "note"));
      var settings = document.createElement("details");
      settings.className = "wd-esheet-settings";
      settings.innerHTML =
        '<summary>⚙ 할인 · 배송 설정<span class="wd-esheet-settings__chev">▾</span></summary>' +
        '<div class="wd-esheet-settings__body"></div>';
      inner.appendChild(settings);
      var sbody = settings.querySelector(".wd-esheet-settings__body");
      var coupon = document.querySelector(".border-left-info");
      var shipping = document.querySelector(".border-left-warning");
      if (coupon) sbody.appendChild(coupon.closest(".col-12") || coupon);
      if (shipping) sbody.appendChild(shipping.closest(".col-12") || shipping);
      var closeBtn = document.querySelector("[data-wd-eclose]");
      if (closeBtn) closeBtn.addEventListener("click", closeEditor);
      var fp = document.getElementById("finalPrice");
      if (fp && window.MutationObserver) {
        new MutationObserver(syncEditorFinal).observe(fp, {
          childList: true, characterData: true, subtree: true,
        });
      }
      syncEditorFinal();
    }

    function getEditorWrap() {
      if (builderEditorWrap) return builderEditorWrap;
      builderEditorWrap = document.querySelector(".wd-editor-wrap");
      return builderEditorWrap;
    }

    function moveEditorHome() {
      var wrap = getEditorWrap();
      var master = document.querySelector(".wd-master");
      if (!wrap || !master) return;
      var cartHead = master.querySelector(".wd-cart-head");
      master.insertBefore(wrap, cartHead || null);
    }

    function cardAnchor(card) {
      if (!card) return null;
      return card.closest("#estimatesListContainer > .row > [class*='col-']") || card;
    }

    function moveEditorAfterCard(card) {
      var wrap = getEditorWrap();
      var anchor = cardAnchor(card);
      if (!wrap || !anchor || !anchor.parentNode) return;
      anchor.parentNode.insertBefore(wrap, anchor.nextSibling);
    }

    function scrollEditorIntoView(target) {
      var wrap = getEditorWrap();
      var scrollTarget = target || wrap;
      if (!scrollTarget || typeof scrollTarget.scrollIntoView !== "function") return;
      setTimeout(function () {
        scrollTarget.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 60);
    }

    function buildFabBar() {
      if (document.querySelector(".wd-fab")) return;
      var fab = document.createElement("div");
      fab.className = "wd-fab";
      fab.innerHTML =
        '<button type="button" class="wd-fab__save wd-fab__cart" data-wd-save aria-label="견적 저장">💾</button>' +
        '<button type="button" class="wd-fab__new wd-fab__cart" data-wd-new>＋ 새 견적 만들기</button>' +
        '<div class="wd-fab__edit"><div class="wd-fab__sum">' +
        '<span class="wd-fab__sum-l">이 견적</span>' +
        '<span class="wd-fab__sum-v" data-wd-efinal>0원</span></div>' +
        '<button type="button" class="wd-fab__done" data-wd-edone>완료</button></div>';
      document.body.appendChild(fab);
      fab.querySelector("[data-wd-save]").addEventListener("click", function () {
        var b = document.getElementById("saveEstimateBtn");
        if (b) b.click();
      });
      fab.querySelector("[data-wd-new]").addEventListener("click", function () {
        resetToNewEstimate();
        moveEditorHome();
        openEditor("새 견적", { scrollTarget: getEditorWrap() });
      });
      fab.querySelector("[data-wd-edone]").addEventListener("click", function () {
        var b = document.getElementById("addEstimateBtn");
        if (b) b.click(); // host: 견적 추가 / 수정 적용
        closeEditor();
      });
    }

    function resetToNewEstimate() {
      var r = window.WdCalculatorResetInputFormKeepCustomer;
      if (r && typeof r.resetInputFormToNewEstimate === "function") {
        try {
          r.resetInputFormToNewEstimate();
        } catch (e) {}
      }
    }

    function openEditor(subText, options) {
      var sub = document.querySelector("[data-wd-esub]");
      if (sub) sub.textContent = subText || "";
      var titleEl = document.querySelector(".wd-editor__title");
      if (titleEl) titleEl.textContent = subText && subText !== "새 견적" ? "견적 편집" : "새 견적";
      document.body.classList.add("wd-editing");
      scrollEditorIntoView(options && options.scrollTarget);
      updateEsecBadges();
      syncEditorFinal();
    }

    function closeEditor() {
      document.body.classList.remove("wd-editing");
      var ec = document.querySelector(".wd-card-editing");
      if (ec) ec.classList.remove("wd-card-editing");
      setTimeout(moveEditorHome, 280);
    }

    function syncEditorFinal() {
      var fp = document.getElementById("finalPrice");
      var out = document.querySelector("[data-wd-efinal]");
      if (!fp || !out) return;
      var v = (fp.textContent || "0원").trim();
      if (lastEditorFinal !== null && v !== lastEditorFinal) {
        out.classList.remove("wd-pulse");
        void out.offsetWidth;
        out.classList.add("wd-pulse");
      }
      out.textContent = v;
      lastEditorFinal = v;
      updateEsecBadges();
    }

    function syncHero() {
      var heroVal = document.querySelector("[data-wd-hero]");
      if (!heroVal) return;
      var countEl = document.querySelector("[data-wd-hero-count]");
      var couponEl = document.querySelector("[data-wd-hero-coupon]");
      var fin = document.getElementById("totalAllFinalPrice");
      var cards = document.querySelectorAll("#estimatesListContainer .card[data-estimate-id]");
      var coupon = document.getElementById("totalAllCouponInfo");
      var v = fin ? (fin.textContent || "0원").trim() : "0원";
      if (lastHero !== null && v !== lastHero) {
        heroVal.classList.remove("wd-pulse");
        void heroVal.offsetWidth;
        heroVal.classList.add("wd-pulse");
      }
      heroVal.textContent = v;
      lastHero = v;
      if (countEl) countEl.textContent = "견적 " + cards.length + "건";
      if (couponEl) couponEl.textContent = coupon ? (coupon.textContent || "").trim() : "쿠폰가 미적용";
    }

    function wireBuilderFlows() {
      var list = document.getElementById("estimatesListContainer");
      if (list) {
        list.addEventListener("click", function (e) {
          // 삭제·이름수정은 host가 처리(시트 안 엶)
          if (
            e.target.closest(".delete-estimate-btn") ||
            e.target.closest(".edit-estimate-name-btn") ||
            e.target.closest(".estimate-display-name-input") ||
            e.target.closest(".estimate-display-name-save-btn") ||
            e.target.closest(".estimate-display-name-cancel-btn")
          ) return;
          var card = e.target.closest(".card[data-estimate-id]");
          if (!card) return;

          e.preventDefault();
          e.stopPropagation();

          var estimateId = card.getAttribute("data-estimate-id");
          var loader =
            window.WdCalculatorLoadEstimateToInputForm &&
            typeof window.WdCalculatorLoadEstimateToInputForm.loadEstimateToInputForm === "function"
              ? window.WdCalculatorLoadEstimateToInputForm.loadEstimateToInputForm
              : null;
          if (loader) {
            loader(estimateId);
          } else {
            var editBtn = card.querySelector(".edit-estimate-btn");
            if (editBtn) editBtn.click();
          }

          var activeId =
            window.WdCalculatorEditingEstimateId &&
            typeof window.WdCalculatorEditingEstimateId.getEditingEstimateId === "function"
              ? window.WdCalculatorEditingEstimateId.getEditingEstimateId()
              : estimateId;
          if (String(activeId) !== String(estimateId)) {
            return;
          }

          var prev = document.querySelector(".wd-card-editing");
          if (prev) prev.classList.remove("wd-card-editing");
          card.classList.add("wd-card-editing");
          var name = (card.querySelector(".estimate-display-name") || {}).textContent || "견적 편집";
          moveEditorAfterCard(card);
          openEditor(name.trim(), { scrollTarget: getEditorWrap() });
        });
        if (window.MutationObserver) {
          new MutationObserver(function () {
            syncHero();
            if (document.body.classList.contains("wd-editing") && !document.body.contains(getEditorWrap())) {
              closeEditor();
            }
          }).observe(list, { childList: true, subtree: true });
        }
      }
      syncHero();
    }

    var lastFinalText = null;
    function syncFinal() {
      var fp = document.getElementById("finalPrice");
      var out = document.querySelector("[data-wd-final]");
      if (!fp || !out) return;
      var v = (fp.textContent || "0원").trim();
      out.textContent = v;
      if (lastFinalText !== null && v !== lastFinalText) {
        out.classList.remove("wd-pulse");
        void out.offsetWidth; // reflow → 애니메이션 재시작
        out.classList.add("wd-pulse");
      }
      lastFinalText = v;
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
      var widthText =
        width > 0 && typeof window.formatBaseWidthDisplay === "function"
          ? window.formatBaseWidthDisplay(row, fmtNum)
          : width > 0
            ? fmtNum(width) + "mm"
            : "";
      var name = "";
      var unitText = "";
      var chipHtml = "";
      if (mode === "manual") {
        var mp = (row && row.manualPricing) || {};
        if (mp.pricing_type === "1m") {
          var p1m = Number(mp.price_1m) || 0;
          name = (row && row.manualName) || "직접입력 (1m)";
          unitText = "1m " + fmtNum(p1m);
          chipHtml = p1m ? "1m <b>" + fmtNum(p1m) + "원</b>" : "";
        } else {
          var p30 = Number(mp.price_30cm) || 0;
          var p1 = Number(mp.price_1cm) || 0;
          name = (row && row.manualName) || "직접입력 (30cm)";
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
      var specParts = [mode === "manual" ? "CUSTOM" : "선택"];
      if (widthText) specParts.push(widthText);
      if (unitText) specParts.push(unitText);
      return { name: name, spec: specParts.join(" · "), chipHtml: chipHtml };
    }

    /* ---- [v3] 현장 영업 리파인 헬퍼 ---- */
    function sectionLabelFor(containerId) {
      var c = document.getElementById(containerId);
      var host = c && c.closest(".mb-3");
      return host ? host.querySelector(".form-label") : null;
    }
    function ensureBadge(label) {
      if (!label) return null;
      var b = label.querySelector(".wd-sec-badge");
      if (!b) {
        b = document.createElement("span");
        b.className = "wd-sec-badge";
        label.appendChild(b);
      }
      return b;
    }
    function updateBaseBadge() {
      var c = document.getElementById("baseComponentsContainer");
      if (!c) return;
      var n = c.querySelectorAll(".base-component-row").length;
      var b = ensureBadge(sectionLabelFor("baseComponentsContainer"));
      if (b) b.textContent = n + "개 구성";
    }
    function updateOptionBadge() {
      var c = document.getElementById("additionalOptionsContainer");
      if (!c) return;
      var n = c.querySelectorAll(".additional-option-item").length;
      var b = ensureBadge(sectionLabelFor("additionalOptionsContainer"));
      if (!b) return;
      if (!n) {
        b.textContent = "";
        return;
      }
      // host가 라이브 계산하는 추가 옵션 합계(#totalAdditionalPrice)를 미러 → 금액 배지
      var sumEl = document.getElementById("totalAdditionalPrice");
      var sum = sumEl ? (sumEl.textContent || "").trim() : "";
      b.textContent = sum && sum !== "0원" ? "합계 " + sum : n + "개";
    }
    function applyNumericInputmode(scope) {
      var root = scope || document;
      forEachNode(root.querySelectorAll('input[type="number"]'), function (inp) {
        if (!inp.getAttribute("inputmode")) inp.setAttribute("inputmode", "numeric");
      });
    }
    function relabelFinalTitle() {
      var t = document.querySelector(".final-summary-card .card-title");
      if (t) t.textContent = "최종 견적";
    }
    function buildBaseToolbar(rowEl) {
      var body = rowEl.querySelector(".card-body");
      if (!body || body.querySelector(".wd-bc-toolbar")) return;
      var seg = rowEl.querySelector(".btn-group");
      var del = rowEl.querySelector(".base-remove-btn");
      if (!seg && !del) return;
      var toolbar = document.createElement("div");
      toolbar.className = "wd-bc-toolbar";
      if (seg) {
        var segCol = seg.closest('[class*="col-"]');
        toolbar.appendChild(seg);
        if (segCol) segCol.classList.add("wd-bc-orphan-col");
      }
      if (del) {
        var delCol = del.closest('[class*="col-"]');
        toolbar.appendChild(del);
        if (delCol) delCol.classList.add("wd-bc-orphan-col");
      }
      body.insertBefore(toolbar, body.firstChild);
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
      buildBaseToolbar(rowEl);
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
        var hasProduct = row.mode === "manual" || !!row.productId;
        var isEmpty = !hasProduct && !(Number(row.widthMm) > 0);
        var summaryBtn = rowEl.querySelector(".wd-bc-summary");
        if (summaryBtn) summaryBtn.classList.toggle("wd-bc-empty", isEmpty);
        var nameEl = rowEl.querySelector(".wd-bc-name");
        if (nameEl) nameEl.textContent = isEmpty ? "탭하여 제품·치수 입력" : info.name;
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
      updateBaseBadge();
      applyNumericInputmode(container);
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

    var autoExpandedOnce = false;
    function maybeAutoExpandFirst() {
      if (autoExpandedOnce) return;
      var container = document.getElementById("baseComponentsContainer");
      if (!container) return;
      var rows = container.querySelectorAll(".base-component-row");
      // 첫 진입 단일 구성은 한 번만 펼쳐 제품 선택을 바로 노출(현장 입력 유도).
      // host가 행을 늦게 렌더해도 observer 경로에서 잡히도록 init+observer 양쪽 호출.
      if (rows.length === 1) {
        autoExpandedOnce = true;
        rows[0].classList.add("wd-open");
      }
    }

    function initBaseEnhancements() {
      var container = document.getElementById("baseComponentsContainer");
      if (!container) return;
      forEachNode(container.querySelectorAll(".base-component-row"), function (rowEl) {
        enhanceBaseRow(rowEl, false);
      });
      refreshBaseSummaries();
      applyNumericInputmode(container);
      maybeAutoExpandFirst();
      if (window.MutationObserver) {
        // 재렌더/행추가 시 새 행을 향상. 신규 행도 항상 collapsed:
        // 추가 후 요약만 보이고, 편집은 탭해서 펼침.
        new MutationObserver(function () {
          forEachNode(container.querySelectorAll(".base-component-row:not(.wd-bc-enh)"), function (rowEl) {
            enhanceBaseRow(rowEl, false);
          });
          scheduleBaseRefresh();
          maybeAutoExpandFirst();
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
        updateOptionBadge();
        applyNumericInputmode(optContainer);
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
      if (optContainer) {
        // 옵션 금액/수량 변경 → 합계 배지 갱신(host 계산 후 읽도록 1tick 지연)
        var deferOptBadge = function () { setTimeout(updateOptionBadge, 0); };
        optContainer.addEventListener("input", deferOptBadge);
        optContainer.addEventListener("change", deferOptBadge);
      }
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
    // [fix] 카트 카드: 추가옵션 합계/비고가 비어 있으면 그 행 숨김(class 기반 → style-strip 무관)
    function hideEmptyCartRows() {
      var container = document.getElementById("estimatesListContainer");
      if (!container) return;
      forEachNode(container.querySelectorAll(".card[data-estimate-id] .estimate-card-item"), function (item) {
        var hide = false;
        if (item.querySelector(".estimate-header-options")) {
          var price = item.querySelector(".estimate-price");
          var detail = item.querySelector(".estimate-detail-options");
          var priceNum = price ? (price.textContent || "").replace(/[^0-9]/g, "") : "";
          var detailTxt = detail ? (detail.textContent || "").trim() : "";
          if ((priceNum === "" || priceNum === "0") && (detailTxt === "" || detailTxt === "없음")) hide = true;
        }
        if (item.querySelector(".estimate-header-notes")) {
          var ndetail = item.querySelector(".estimate-detail-notes");
          var ntxt = ndetail ? (ndetail.textContent || "").trim() : "";
          if (ntxt === "") hide = true;
        }
        item.classList.toggle("wd-hide-empty", hide);
      });
    }
    function mobilizeEstimatesListAfterRender() {
      mobilizeEstimatesList();
      hideEmptyCartRows();
      // renderEstimatesList() reapplies forced inline styles after 10ms; clear them after that pass.
      setTimeout(mobilizeEstimatesList, 30);
      setTimeout(hideEmptyCartRows, 30);
    }
    function initEstimatesListMobile() {
      var container = document.getElementById("estimatesListContainer");
      if (!container) return;
      mobilizeEstimatesListAfterRender();
      observeChildList(container, mobilizeEstimatesListAfterRender);
    }

    function initOptionalSectionDisclosure() {
      var section = document.querySelector('.wd-esec[data-esec="note"]');
      if (!section || section.getAttribute("data-wd-disclosure-ready") === "1") return;
      var head = section.querySelector(".wd-esec__head");
      if (!head) return;
      section.setAttribute("data-wd-disclosure-ready", "1");
      section.classList.add("wd-esec--collapsible", "wd-esec--collapsed");
      head.setAttribute("role", "button");
      head.setAttribute("tabindex", "0");
      head.setAttribute("aria-expanded", "false");
      function toggleSection() {
        var collapsed = section.classList.toggle("wd-esec--collapsed");
        head.setAttribute("aria-expanded", collapsed ? "false" : "true");
      }
      head.addEventListener("click", toggleSection);
      head.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
          e.preventDefault();
          toggleSection();
        }
      });
    }

    /* ---- 비고 섹션 → 기본 접힌 아코디언 (사용자 요청) ----
       비고는 선택 입력이라 기본 접어 화면을 간결하게. 헤더 '📝 비고'만 보이고
       탭하면 펼쳐 입력. 호스트의 #notesContainer / #btnAddNote 노드를 그대로 이동
       (이벤트·렌더링 유지). */
    function buildNotesAccordion() {
      var notesContainer = document.getElementById("notesContainer");
      if (!notesContainer) return;
      var section = notesContainer.closest(".mb-3");
      if (!section || section.querySelector(".wd-nacc")) return;
      section.classList.add("wd-nacc-host");
      var details = document.createElement("details");
      details.className = "wd-nacc";
      details.innerHTML =
        '<summary class="wd-nacc__sum"><span class="wd-nacc__title">📝 비고</span>' +
        '<span class="wd-nacc__chev">▾</span></summary>' +
        '<div class="wd-nacc__body"></div>';
      var body = details.querySelector(".wd-nacc__body");
      while (section.firstChild) {
        body.appendChild(section.firstChild);
      }
      section.appendChild(details);
    }

    function enable() {
      if (built) return;
      built = true;
      document.body.classList.add("wd-calc-mobile"); // field-level mobile.css 재사용
      document.body.classList.add("wd-builder"); // 빌더 셸 IA
      buildHeader();
      buildSheet(); // 저장된 견적 🗂 sheet (재사용)
      buildBuilderMaster(); // 고객칩 + 총액 HERO + 인라인 에디터 슬롯 + 카트
      buildFabBar(); // 하단 액션 바(카트:저장/새견적 ↔ 편집:이견적/완료)
      buildEditorPanel(); // 인라인 에디터: 구성·옵션·비고 전 섹션 + 할인배송
      initOptionalSectionDisclosure(); // 선택 입력(비고)은 기본 접힘
      initBaseEnhancements();
      initToggleEnhancements();
      initMobileSelects();
      initEstimatesListMobile(); // 카트 카드 인라인 스타일 제거
      applyNumericInputmode(document);
      wireBuilderFlows(); // 카드탭→수정 / HERO 미러 / 흐름 배선
    }

    if (mq.matches) enable();
    var onChange = function (e) {
      if (e.matches) enable();
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
    else if (mq.addListener) mq.addListener(onChange);
  });
})();
