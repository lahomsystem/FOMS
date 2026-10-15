/**
 * ERP 주문 편집 — 할인 항목(이름 + 금액) 여러 줄.
 *
 * 정본은 structured_data.payment.discounts. 기존 잔금·견적·자동저장 코드는
 * 숨은 #erp-discount-amount(합계) 만 읽으므로, 줄이 바뀔 때마다 합계를 그 칸에 쓴다.
 * 옛 주문(discount 숫자만)은 "할인" 한 줄로 보여 준다.
 */
(function () {
  "use strict";

  var DEFAULT_LABEL = "할인";
  var MAX_ROWS = 20;
  var rows = [];

  function coerce(value) {
    if (typeof window.erpCoerceAmount === "function") return window.erpCoerceAmount(value);
    var n = parseInt(String(value == null ? "" : value).replace(/[^0-9]/g, ""), 10);
    return Number.isFinite(n) && n > 0 ? n : 0;
  }

  function formatWon(n) {
    if (typeof window.erpFormatDepositDisplay === "function") return window.erpFormatDepositDisplay(n);
    return n > 0 ? n.toLocaleString("ko-KR") + "원" : "0원";
  }

  function totalOf(list) {
    return list.reduce(function (sum, row) { return sum + coerce(row.amount); }, 0);
  }

  function syncTotal() {
    var sum = totalOf(rows);
    var hidden = document.getElementById("erp-discount-amount");
    if (hidden) hidden.value = formatWon(sum);
    var sumEl = document.getElementById("erp-discount-sum");
    if (sumEl) {
      // 합계는 두 줄 이상일 때만 — 한 줄이면 그 줄 금액이 곧 합계다.
      sumEl.textContent = "합계 −" + formatWon(sum);
      sumEl.hidden = rows.length < 2 || sum <= 0;
    }
    if (typeof window.erpCalculateRemaining === "function") window.erpCalculateRemaining();
  }

  function buildRow(row, index) {
    var wrap = document.createElement("div");
    wrap.className = "erp-discount-row";

    var label = document.createElement("input");
    label.type = "text";
    label.className = "erp-discount-row__label";
    label.maxLength = 64;
    label.placeholder = "할인 이름";
    label.value = row.label || "";
    label.setAttribute("aria-label", "할인 이름");
    label.addEventListener("input", function () { row.label = label.value; });

    var amount = document.createElement("input");
    amount.type = "text";
    amount.inputMode = "numeric";
    amount.maxLength = 24;
    amount.placeholder = "0원";
    amount.className = "erp-amount-value erp-amount-value--discount erp-discount-row__amount";
    amount.value = row.amount > 0 ? formatWon(row.amount) : "";
    amount.setAttribute("aria-label", "할인 금액");
    var parse = function () { return coerce(amount.value); };
    var onRecalc = function () { row.amount = parse(); syncTotal(); };
    if (typeof window.erpBindAmountInput === "function") {
      window.erpBindAmountInput(amount, parse, onRecalc);
    } else {
      amount.addEventListener("input", onRecalc);
    }

    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "erp-discount-row__remove";
    remove.textContent = "×";
    remove.title = "이 할인 지우기";
    remove.setAttribute("aria-label", "이 할인 지우기");
    remove.addEventListener("click", function () {
      rows.splice(index, 1);
      render();
      // 자동저장은 폼의 input 이벤트로 변경을 감지한다.
      var hidden = document.getElementById("erp-discount-amount");
      if (hidden) hidden.dispatchEvent(new Event("input", { bubbles: true }));
    });

    wrap.appendChild(label);
    wrap.appendChild(amount);
    wrap.appendChild(remove);
    return wrap;
  }

  function render() {
    var list = document.getElementById("erp-discount-list");
    if (list) {
      list.textContent = "";
      rows.forEach(function (row, i) { list.appendChild(buildRow(row, i)); });
    }
    var add = document.getElementById("erp-discount-add");
    if (add) add.hidden = rows.length >= MAX_ROWS;
    syncTotal();
  }

  /** 저장용 목록 — 금액 0 줄은 뺀다(서버도 다시 정리한다). */
  function getItems() {
    return rows
      .map(function (row) {
        return { label: String(row.label || "").trim() || DEFAULT_LABEL, amount: coerce(row.amount) };
      })
      .filter(function (row) { return row.amount > 0; });
  }

  /**
   * 서버 값으로 줄을 채운다.
   * @param {Array|undefined} items payment.discounts
   * @param {number} legacyAmount payment.discount (목록이 없을 때 한 줄로)
   */
  function setItems(items, legacyAmount) {
    if (Array.isArray(items)) {
      rows = items
        .filter(function (row) { return row && typeof row === "object"; })
        .map(function (row) { return { label: String(row.label || ""), amount: coerce(row.amount) }; })
        .filter(function (row) { return row.amount > 0; });
    } else {
      var legacy = coerce(legacyAmount);
      rows = legacy > 0 ? [{ label: DEFAULT_LABEL, amount: legacy }] : [];
    }
    render();
  }

  function bindAddButton() {
    var add = document.getElementById("erp-discount-add");
    if (!add || add.dataset.erpDiscountBound === "1") return;
    add.dataset.erpDiscountBound = "1";
    add.addEventListener("click", function () {
      if (rows.length >= MAX_ROWS) return;
      rows.push({ label: "", amount: 0 });
      render();
      var inputs = document.querySelectorAll("#erp-discount-list .erp-discount-row__label");
      if (inputs.length) inputs[inputs.length - 1].focus();
    });
  }

  window.erpGetDiscountItems = getItems;
  window.erpSetDiscountItems = setItems;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAddButton);
  } else {
    bindAddButton();
  }
})();
