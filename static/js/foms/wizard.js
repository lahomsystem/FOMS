/**
 * 4-step new order wizard (P1-03).
 */
(function () {
  "use strict";

  var MAX_STEP = 4;
  var DEFAULT_EXIT_HREF = "/erp/dashboard";

  function readWizardExitHref(root) {
    var href = root && root.getAttribute("data-exit-href");
    href = (href || "").trim();
    return href || DEFAULT_EXIT_HREF;
  }

  function readValue(el) {
    return (el && el.value ? el.value : "").trim();
  }

  function collectBasic(root) {
    return {
      customer_name: readValue(root.querySelector("#wiz-customer-name")),
      phone: readValue(root.querySelector("#wiz-phone")),
      orderer: readValue(root.querySelector("#wiz-orderer")),
      address: readValue(root.querySelector("#wiz-address")),
      received_date: readValue(root.querySelector("#wiz-received-date")),
    };
  }

  function collectSchedule(root) {
    return {
      measurement_date: readValue(root.querySelector("#wiz-measurement-date")),
      measurement_time: readValue(root.querySelector("#wiz-measurement-time")),
      construction_date: readValue(root.querySelector("#wiz-construction-date")),
      construction_time: readValue(root.querySelector("#wiz-construction-time")),
      sales_manager: readValue(root.querySelector("#wiz-sales-manager")),
      construction_manager: readValue(root.querySelector("#wiz-construction-manager")),
      // 상차일은 지방주문 전용 — 체크가 꺼지면 값이 남아도 전송하지 않는다.
      load_date: readChecked(root.querySelector("#wiz-flag-regional"))
        ? readValue(root.querySelector("#wiz-load-date"))
        : "",
      notes: readValue(root.querySelector("#wiz-notes")),
    };
  }

  function collectPayment(root) {
    return {
      deposit: readValue(root.querySelector("#wiz-deposit-amount")),
    };
  }

  function readChecked(el) {
    return !!(el && el.checked);
  }

  // 주문 구분 플래그: 지방주문(=Order.is_regional 컬럼)·라홈시스템/긴급(=structured_data.flags).
  function collectFlags(root) {
    var regional = readChecked(root.querySelector("#wiz-flag-regional"));
    var urgent = readChecked(root.querySelector("#wiz-flag-urgent"));
    return {
      regional_order: regional,
      regional_construction_type: regional
        ? readValue(root.querySelector("#wiz-regional-construction-type"))
        : "",
      factory2: readChecked(root.querySelector("#wiz-flag-factory2")),
      urgent: urgent,
      urgent_reason: urgent ? readValue(root.querySelector("#wiz-urgent-reason")) : "",
    };
  }

  // 하위 입력(지방주문 구분·긴급 사유)은 상위 체크가 켜졌을 때만 노출한다.
  function syncFlagFieldVisibility(root) {
    var regional = readChecked(root.querySelector("#wiz-flag-regional"));
    var regionalField = root.querySelector("#wiz-regional-type-field");
    if (regionalField) {
      regionalField.hidden = !regional;
    }
    if (!regional) {
      var typeEl = root.querySelector("#wiz-regional-construction-type");
      if (typeEl) typeEl.value = "";
      var loadEl = root.querySelector("#wiz-load-date");
      if (loadEl) loadEl.value = "";
    }
    var urgent = readChecked(root.querySelector("#wiz-flag-urgent"));
    var urgentField = root.querySelector("#wiz-urgent-reason-field");
    if (urgentField) {
      urgentField.hidden = !urgent;
    }
    if (!urgent) {
      var reasonEl = root.querySelector("#wiz-urgent-reason");
      if (reasonEl) reasonEl.value = "";
    }
  }

  function applyFlags(root, flags) {
    if (!flags) {
      return;
    }
    var map = {
      "#wiz-flag-regional": !!flags.regional_order,
      "#wiz-flag-factory2": !!flags.factory2,
      "#wiz-flag-urgent": !!flags.urgent,
    };
    Object.keys(map).forEach(function (sel) {
      var el = root.querySelector(sel);
      if (el) el.checked = map[sel];
    });
    var typeEl = root.querySelector("#wiz-regional-construction-type");
    if (typeEl && flags.regional_construction_type) {
      typeEl.value = flags.regional_construction_type;
    }
    var reasonEl = root.querySelector("#wiz-urgent-reason");
    if (reasonEl && flags.urgent_reason) {
      reasonEl.value = flags.urgent_reason;
    }
    syncFlagFieldVisibility(root);
  }

  function collectProducts(root) {
    var cards = root.querySelectorAll("[data-product-index]");
    var items = [];
    var readAtt = window.FomsWizardAttachments && window.FomsWizardAttachments.readAttachments;
    cards.forEach(function (card) {
      var specRows = [];
      card.querySelectorAll("[data-spec-row]").forEach(function (sr) {
        specRows.push({
          spec_width: readValue(sr.querySelector('[data-product-field="spec_width"]')),
          spec_depth: readValue(sr.querySelector('[data-product-field="spec_depth"]')),
          spec_height: readValue(sr.querySelector('[data-product-field="spec_height"]')),
        });
      });
      if (!specRows.length) {
        specRows = [{ spec_width: "", spec_depth: "", spec_height: "" }];
      }
      items.push({
        product_name: readValue(card.querySelector('[data-product-field="product_name"]')),
        spec_rows: specRows,
        internal: readValue(card.querySelector('[data-product-field="internal"]')),
        color: readValue(card.querySelector('[data-product-field="color"]')),
        option_detail: readValue(card.querySelector('[data-product-field="option_detail"]')),
        handle: readValue(card.querySelector('[data-product-field="handle"]')),
        misc: readValue(card.querySelector('[data-product-field="misc"]')),
        price: readValue(card.querySelector('[data-product-field="price"]')),
        measurement_date: readValue(card.querySelector('[data-product-field="measurement_date"]')),
        construction_date: readValue(card.querySelector('[data-product-field="construction_date"]')),
        extra_input: readValue(card.querySelector('[data-product-field="extra_input"]')),
        attachments: readAtt ? readAtt(card) : [],
      });
    });
    return items;
  }

  function preferNonEmpty(localVal, remoteVal) {
    var local = (localVal || "").trim();
    if (local) {
      return local;
    }
    return (remoteVal || "").trim();
  }

  function mergeAttachmentLists(localList, remoteList) {
    var merged = [];
    var seen = {};
    [remoteList, localList].forEach(function (list) {
      if (!Array.isArray(list)) {
        return;
      }
      list.forEach(function (raw) {
        if (!raw || !raw.tmp_key || seen[raw.tmp_key]) {
          return;
        }
        seen[raw.tmp_key] = true;
        merged.push({ tmp_key: raw.tmp_key, filename: raw.filename || "" });
      });
    });
    return merged;
  }

  function mergeProductItem(localItem, remoteItem) {
    var local = localItem || {};
    var remote = remoteItem || {};
    var localSpec = (local.spec_rows && local.spec_rows[0]) || {};
    var remoteSpec = (remote.spec_rows && remote.spec_rows[0]) || {};
    return {
      product_name: preferNonEmpty(local.product_name, remote.product_name),
      spec_rows: [
        {
          spec_width: preferNonEmpty(localSpec.spec_width, remoteSpec.spec_width),
          spec_depth: preferNonEmpty(localSpec.spec_depth, remoteSpec.spec_depth),
          spec_height: preferNonEmpty(localSpec.spec_height, remoteSpec.spec_height),
        },
      ],
      internal: preferNonEmpty(local.internal, remote.internal),
      color: preferNonEmpty(local.color, remote.color),
      option_detail: preferNonEmpty(local.option_detail, remote.option_detail),
      handle: preferNonEmpty(local.handle, remote.handle),
      misc: preferNonEmpty(local.misc, remote.misc),
      price: preferNonEmpty(local.price, remote.price),
      measurement_date: preferNonEmpty(local.measurement_date, remote.measurement_date),
      construction_date: preferNonEmpty(local.construction_date, remote.construction_date),
      extra_input: preferNonEmpty(local.extra_input, remote.extra_input),
      attachments: mergeAttachmentLists(local.attachments, remote.attachments),
    };
  }

  function mergeSchedule(localSchedule, remoteSchedule) {
    var local = localSchedule || {};
    var remote = remoteSchedule || {};
    return {
      measurement_date: preferNonEmpty(local.measurement_date, remote.measurement_date),
      measurement_time: preferNonEmpty(local.measurement_time, remote.measurement_time),
      construction_date: preferNonEmpty(local.construction_date, remote.construction_date),
      construction_time: preferNonEmpty(local.construction_time, remote.construction_time),
    };
  }

  function mergeDraftPayload(localPayload, remotePayload) {
    var local = (localPayload && localPayload.data) || {};
    var remote = (remotePayload && remotePayload.data) || {};
    var mergedData = {
      customer_name: preferNonEmpty(local.customer_name, remote.customer_name),
      phone: preferNonEmpty(local.phone, remote.phone),
      orderer: preferNonEmpty(local.orderer, remote.orderer),
      address: preferNonEmpty(local.address, remote.address),
      received_date: preferNonEmpty(local.received_date, remote.received_date),
      deposit: preferNonEmpty(local.deposit, remote.deposit),
      items: [],
      schedule: mergeSchedule(local.schedule, remote.schedule),
    };
    var localItems = Array.isArray(local.items) ? local.items : [];
    var remoteItems = Array.isArray(remote.items) ? remote.items : [];
    var maxLen = Math.max(localItems.length, remoteItems.length, 1);
    for (var i = 0; i < maxLen; i += 1) {
      mergedData.items.push(mergeProductItem(localItems[i], remoteItems[i]));
    }
    return {
      schema_version: 1,
      step: Math.max(localPayload.step || 1, remotePayload.step || 1),
      data: mergedData,
    };
  }

  function applyPayload(root, payload, draftKey, scheduleSave) {
    var data = (payload && payload.data) || {};
    applyBasic(root, data);
    applyProducts(root, data.items, draftKey, scheduleSave);
    applySchedule(root, data.schedule);
    applyFlags(root, data.flags);
    applyPayment(root, data);
  }

  function buildPayload(root, step) {
    var data = collectBasic(root);
    data.items = collectProducts(root);
    data.schedule = collectSchedule(root);
    data.flags = collectFlags(root);
    data.deposit = collectPayment(root).deposit;
    return {
      schema_version: 1,
      step: step,
      data: data,
    };
  }

  function applyBasic(root, data) {
    if (!data) return;
    var map = {
      "#wiz-customer-name": data.customer_name,
      "#wiz-phone": data.phone,
      "#wiz-orderer": data.orderer,
      "#wiz-address": data.address,
      "#wiz-received-date": data.received_date,
    };
    Object.keys(map).forEach(function (sel) {
      var el = root.querySelector(sel);
      if (el && map[sel]) {
        el.value = map[sel];
        // combo(발주사 등) 표시 컨트롤이 canonical 값으로 재동기화되도록 알림.
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  function applyPayment(root, data) {
    if (!data) return;
    var depositEl = root.querySelector("#wiz-deposit-amount");
    if (depositEl) {
      var depositRaw = data.deposit != null ? String(data.deposit).trim() : "";
      depositEl.value = depositRaw ? formatDepositDisplay(parseAmount(depositRaw)) : "";
    }
    recalcWizardAmounts(root);
  }

  function applySchedule(root, schedule) {
    if (!schedule) return;
    var map = {
      "#wiz-measurement-date": schedule.measurement_date,
      "#wiz-measurement-time": schedule.measurement_time,
      "#wiz-construction-date": schedule.construction_date,
      "#wiz-construction-time": schedule.construction_time,
      "#wiz-sales-manager": schedule.sales_manager,
      "#wiz-construction-manager": schedule.construction_manager,
      "#wiz-load-date": schedule.load_date,
      "#wiz-notes": schedule.notes,
    };
    Object.keys(map).forEach(function (sel) {
      var el = root.querySelector(sel);
      if (el && map[sel]) {
        el.value = map[sel];
        // 시간 combo의 표시 select/custom이 canonical 값으로 재동기화되도록 알림.
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  function applyAlpineErrors(root, errorMap) {
    if (!window.Alpine || typeof Alpine.$data !== "function") {
      return;
    }
    var data = Alpine.$data(root);
    if (!data || typeof data.errors !== "object") {
      return;
    }
    data.errors = errorMap || {};
  }

  function clearAlpineErrors(root) {
    applyAlpineErrors(root, {});
  }

  // 카드 순번은 DOM 순서가 정본이다. 복제/삭제 후 인덱스·헤더 라벨·첨부 input id를
  // 한 곳에서 다시 매긴다(복제본이 "#1 제품 1"로 고정되던 결함의 근본 수정).
  function renumberProductCards(container) {
    if (!container) {
      return;
    }
    var cards = container.querySelectorAll("[data-product-index]");
    var multi = cards.length > 1;
    Array.prototype.forEach.call(cards, function (card, idx) {
      card.setAttribute("data-product-index", String(idx));
      var indexEl = card.querySelector(".foms-product-item__index");
      if (indexEl) {
        indexEl.textContent = "#" + (idx + 1);
      }
      var titleEl = card.querySelector("[data-foms-product-title]");
      if (titleEl) {
        titleEl.textContent =
          readValue(card.querySelector('[data-product-field="product_name"]')) || "제품 " + (idx + 1);
      }
      var input = card.querySelector("[data-wizard-attachment-input]");
      if (input) {
        input.id = "wiz-attach-input-" + idx;
      }
      var widget = card.querySelector("[data-foms-photo-capture]");
      if (widget) {
        widget.setAttribute("data-target-input", "wiz-attach-input-" + idx);
      }
      var removeBtn = card.querySelector("[data-foms-product-remove]");
      if (removeBtn) {
        removeBtn.hidden = !multi;
      }
    });
  }

  function cloneProductCard(container, draftKey, scheduleSave) {
    var cards = container.querySelectorAll("[data-product-index]");
    var template = cards[0];
    if (!template) {
      return null;
    }
    var clone = template.cloneNode(true);
    var nextIndex = cards.length;
    clone.setAttribute("data-product-index", String(nextIndex));
    clone.querySelectorAll("input, textarea").forEach(function (input) {
      input.value = "";
      input.removeAttribute("data-foms-wizard-amount-bound");
    });
    // 규격은 1행으로 리셋(템플릿이 다중 행 상태였을 수 있음).
    var specRowsWrap = clone.querySelector("[data-spec-rows]");
    if (specRowsWrap) {
      var srows = specRowsWrap.querySelectorAll("[data-spec-row]");
      for (var si = srows.length - 1; si >= 1; si -= 1) {
        srows[si].remove();
      }
    }
    // ERP 폼 방식: 내부/색상/옵션/손잡이/기타 신규 항목 기본값 '상담'.
    clone.querySelectorAll("[data-default-consult]").forEach(function (el) {
      el.value = "상담";
    });
    // 음성 입력 마이크는 첫 카드에서 바인딩된 것이라 복제되면 리스너가 없는 죽은 버튼이다.
    // 복제본의 마이크 버튼/바인딩 표식을 제거(래퍼는 재사용)하고 아래에서 새로 부착한다.
    clone.querySelectorAll(".foms-voice-btn").forEach(function (b) {
      b.remove();
    });
    clone.querySelectorAll("[data-foms-voice-bound]").forEach(function (el) {
      el.removeAttribute("data-foms-voice-bound");
    });
    updateSpecDelVisibility(clone);
    var input = clone.querySelector("[data-wizard-attachment-input]");
    if (input) {
      input.id = "wiz-attach-input-" + nextIndex;
    }
    var widget = clone.querySelector("[data-foms-photo-capture]");
    if (widget) {
      widget.setAttribute("data-target-input", "wiz-attach-input-" + nextIndex);
    }
    clone._wizardAttachmentsBound = false;
    container.appendChild(clone);
    renumberProductCards(container);
    if (window.FomsWizardAttachments) {
      window.FomsWizardAttachments.resetCard(clone);
      window.FomsWizardAttachments.bindCard(clone, draftKey, scheduleSave);
    }
    clone.dataset.fomsWizardProductBound = "";
    if (window.fomsProductItem && typeof window.fomsProductItem.initWizardProducts === "function") {
      window.fomsProductItem.initWizardProducts(container);
    }
    bindWizardPriceInputs(container, scheduleSave);
    if (window.FomsVoiceInput && typeof window.FomsVoiceInput.attachWizard === "function") {
      window.FomsVoiceInput.attachWizard(clone);
    }
    return clone;
  }

  /* ---- 규격 다중 행 (ERP 모바일 폼 방식) ---- */
  function updateSpecDelVisibility(card) {
    var rowsWrap = card.querySelector("[data-spec-rows]");
    if (!rowsWrap) return;
    var rows = rowsWrap.querySelectorAll("[data-spec-row]");
    rows.forEach(function (r) {
      var del = r.querySelector("[data-spec-del]");
      if (del) del.hidden = rows.length <= 1;
    });
  }
  function addSpecRow(card) {
    var rowsWrap = card.querySelector("[data-spec-rows]");
    if (!rowsWrap) return null;
    var first = rowsWrap.querySelector("[data-spec-row]");
    if (!first) return null;
    var clone = first.cloneNode(true);
    clone.querySelectorAll("input").forEach(function (i) {
      i.value = "";
    });
    // 규격칸도 음성 입력 대상이라 복제된 죽은 마이크를 제거하고 새 행에 재부착한다.
    clone.querySelectorAll(".foms-voice-btn").forEach(function (b) {
      b.remove();
    });
    clone.querySelectorAll("[data-foms-voice-bound]").forEach(function (el) {
      el.removeAttribute("data-foms-voice-bound");
    });
    rowsWrap.appendChild(clone);
    if (window.FomsVoiceInput && typeof window.FomsVoiceInput.attachWizard === "function") {
      window.FomsVoiceInput.attachWizard(clone);
    }
    updateSpecDelVisibility(card);
    return clone;
  }
  function setSpecRowCount(card, n) {
    var rowsWrap = card.querySelector("[data-spec-rows]");
    if (!rowsWrap) return;
    var rows = rowsWrap.querySelectorAll("[data-spec-row]");
    while (rows.length < n) {
      addSpecRow(card);
      rows = rowsWrap.querySelectorAll("[data-spec-row]");
    }
    while (rows.length > n && rows.length > 1) {
      rows[rows.length - 1].remove();
      rows = rowsWrap.querySelectorAll("[data-spec-row]");
    }
    updateSpecDelVisibility(card);
  }

  function fillProductCard(card, item) {
    if (!card || !item) {
      return;
    }
    var fields = [
      "product_name",
      "internal",
      "color",
      "option_detail",
      "handle",
      "misc",
      "price",
      "extra_input",
    ];
    fields.forEach(function (name) {
      var el = card.querySelector('[data-product-field="' + name + '"]');
      if (!el || item[name] == null || item[name] === "") {
        return;
      }
      if (name === "price") {
        var amt = parseAmount(item[name]);
        el.value = amt > 0 ? formatDepositDisplay(amt) : "";
        return;
      }
      el.value = item[name];
    });
    var specRows = item.spec_rows && item.spec_rows.length ? item.spec_rows : [{}];
    setSpecRowCount(card, specRows.length);
    var rowEls = card.querySelectorAll("[data-spec-row]");
    specRows.forEach(function (sr, i) {
      var rowEl = rowEls[i];
      if (!rowEl) return;
      ["spec_width", "spec_depth", "spec_height"].forEach(function (name) {
        var inp = rowEl.querySelector('[data-product-field="' + name + '"]');
        if (inp) inp.value = sr[name] != null ? sr[name] : "";
      });
    });
    if (window.FomsWizardAttachments) {
      window.FomsWizardAttachments.applyAttachments(card, item.attachments);
    }
  }

  function expandWizardCard(card) {
    if (!card) return;
    card.classList.remove("foms-product-item--collapsed");
    var head = card.querySelector("[data-foms-product-toggle], .foms-product-item__head");
    if (head) head.setAttribute("aria-expanded", "true");
    var expand = card.querySelector(".foms-product-item__expand");
    if (expand) expand.textContent = "▴";
  }

  // 미입력 제품 카드가 접혀 있거나 화면 밖이면 사용자가 인지하지 못해
  // "제품명을 입력했는데도 계속 입력하라고" 보인다. 실제 빈 카드를 펼쳐 노출·포커스한다.
  function revealEmptyProductCard(card) {
    expandWizardCard(card);
    var nameEl = card.querySelector('[data-product-field="product_name"]');
    if (!nameEl) return;
    try {
      nameEl.scrollIntoView({ block: "center", behavior: "smooth" });
    } catch (e) {
      nameEl.scrollIntoView();
    }
    window.setTimeout(function () {
      try {
        nameEl.focus({ preventScroll: true });
      } catch (e2) {
        nameEl.focus();
      }
    }, 50);
  }

  function findFirstEmptyProductCard(root) {
    var container = root.querySelector("#foms-wizard-products");
    var cards = container ? container.querySelectorAll("[data-product-index]") : [];
    var firstEmpty = null;
    Array.prototype.forEach.call(cards, function (card) {
      if (firstEmpty) return;
      var nameEl = card.querySelector('[data-product-field="product_name"]');
      if (!nameEl || !readValue(nameEl)) {
        firstEmpty = card;
      }
    });
    return { count: cards.length, firstEmpty: firstEmpty };
  }

  function validateStep(root, step) {
    var errors = {};
    if (step === 1) {
      var basic = collectBasic(root);
      if (!basic.customer_name) {
        errors.customer_name = "고객명을 입력해주세요.";
      }
      if (!basic.phone) {
        errors.phone = "연락처를 입력해주세요.";
      }
      if (!basic.address) {
        errors.address = "주소를 입력해주세요.";
      }
    }
    if (step === 2) {
      var scan = findFirstEmptyProductCard(root);
      if (!scan.count || scan.firstEmpty) {
        errors.product_name = "제품명을 입력해주세요.";
        if (scan.firstEmpty) {
          revealEmptyProductCard(scan.firstEmpty);
        }
      }
    }
    if (step === 3) {
      var flags = collectFlags(root);
      if (flags.regional_order && !flags.regional_construction_type) {
        errors.regional_construction_type = "지방주문 구분(하우드/협력사)을 선택해주세요.";
        var typeEl = root.querySelector("#wiz-regional-construction-type");
        if (typeEl) {
          try {
            typeEl.scrollIntoView({ block: "center", behavior: "smooth" });
          } catch (e) {
            typeEl.scrollIntoView();
          }
        }
      }
    }
    if (Object.keys(errors).length) {
      applyAlpineErrors(root, errors);
      return errors[Object.keys(errors)[0]];
    }
    clearAlpineErrors(root);
    return "";
  }

  function applyProducts(root, items, draftKey, scheduleSave) {
    if (!items || !items.length) {
      return;
    }
    var container = root.querySelector("#foms-wizard-products");
    if (!container) {
      return;
    }
    while (container.querySelectorAll("[data-product-index]").length < items.length) {
      cloneProductCard(container, draftKey, scheduleSave);
    }
    items.forEach(function (item, idx) {
      var card = container.querySelector('[data-product-index="' + idx + '"]');
      fillProductCard(card, item);
    });
    renumberProductCards(container);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function parseAmount(s) {
    var n = parseInt(String(s || "").replace(/[^\d]/g, ""), 10);
    return isNaN(n) ? 0 : n;
  }
  function formatMoneyKRW(num) {
    var n = Number(num);
    if (!Number.isFinite(n)) return "0원";
    return Math.round(n).toLocaleString("ko-KR") + "원";
  }
  function formatDepositDisplay(num) {
    if (num == null || !Number.isFinite(num) || num < 0) return "0원";
    return num === 0 ? "0원" : num.toLocaleString("ko-KR") + "원";
  }
  function buildWizardTotals(items, depositRaw) {
    var itemsTotal = 0;
    (items || []).forEach(function (item) {
      itemsTotal += parseAmount(item && item.price);
    });
    // 제품 가격 입력 전(itemsTotal=0)에는 예약금 상한이 없다. 0으로 clamp 하면
    // 최초 입력한 예약금이 통째로 사라진다(placeholder "0원"과 구분 불가).
    var deposit = parseAmount(depositRaw);
    if (itemsTotal > 0) {
      deposit = Math.min(deposit, itemsTotal);
    }
    var balance = Math.max(0, itemsTotal - deposit);
    return {
      items_total: itemsTotal,
      deposit_amount: deposit,
      balance_amount: balance,
    };
  }
  function recalcWizardAmounts(root) {
    var items = collectProducts(root);
    var depositRaw = readValue(root.querySelector("#wiz-deposit-amount"));
    var totals = buildWizardTotals(items, depositRaw);
    var totalEl = root.querySelector("#foms-wizard-items-total");
    if (totalEl) {
      totalEl.textContent = formatMoneyKRW(totals.items_total);
    }
    var balanceRow = root.querySelector("#foms-wizard-balance-row");
    var balanceEl = root.querySelector("#foms-wizard-balance-amount");
    var showAmountRows = totals.items_total > 0;
    if (balanceRow) {
      balanceRow.hidden = !showAmountRows;
    }
    if (balanceEl) {
      balanceEl.textContent = formatMoneyKRW(totals.balance_amount);
    }
    return totals;
  }
  function bindWizardAmountInput(inputEl, root, scheduleSave, onRecalc) {
    if (!inputEl || inputEl.dataset.fomsWizardAmountBound === "1") {
      return;
    }
    inputEl.dataset.fomsWizardAmountBound = "1";
    // caret 을 실제로 옮긴다. iOS Safari 는 값 재대입 직후 caret 을 끝으로 되돌리는 경우가
    // 있어(접미사 "원" 뒤로 밀림) 다음 프레임에 한 번 더 확인해 바로잡는다.
    function applyAmountCaret(el, pos) {
      if (!el || typeof el.setSelectionRange !== "function") return;
      try {
        el.setSelectionRange(pos, pos);
      } catch (_e) {
        return; /* 포커스 밖 — caret 복원 실패는 무해 */
      }
      if (typeof window.requestAnimationFrame !== "function") return;
      window.requestAnimationFrame(function () {
        if (document.activeElement !== el || el.selectionStart === pos) return;
        try {
          el.setSelectionRange(pos, pos);
        } catch (_e2) {
          /* 무해 */
        }
      });
    }
    function setAmountCaretBeforeSuffix(el) {
      if (!el || typeof el.setSelectionRange !== "function" || !String(el.value || "").endsWith("원")) return;
      applyAmountCaret(el, Math.max(0, String(el.value || "").length - 1));
    }
    // 재포맷 후 caret 을 "끝에서부터의 오프셋"으로 보존한다(중간 자릿수 수정 시 끝으로
    // 튀지 않게). 접미사 "원" 뒤로는 절대 두지 않는다.
    function restoreAmountCaret(el, prevValue, prevCaret, formatted) {
      var caret = prevCaret == null ? prevValue.length : prevCaret;
      var fromEnd = Math.max(1, prevValue.length - caret);
      applyAmountCaret(el, Math.max(0, formatted.length - fromEnd));
    }
    function deleteAmountDigitBeforeSuffix(el) {
      var value = String(el.value || "");
      var start = el.selectionStart;
      var end = el.selectionEnd;
      if (!value.endsWith("원") || start == null || end == null || start !== end || start !== value.length) {
        return false;
      }
      var raw = value.replace(/[^0-9]/g, "");
      if (!raw) return false;
      var nextRaw = raw.slice(0, -1);
      el.value = nextRaw ? formatDepositDisplay(parseInt(nextRaw, 10)) : "";
      setAmountCaretBeforeSuffix(el);
      if (onRecalc) onRecalc();
      return true;
    }
    inputEl.addEventListener("keydown", function (event) {
      if (event.key !== "Backspace") return;
      if (deleteAmountDigitBeforeSuffix(this)) event.preventDefault();
    });
    inputEl.addEventListener("beforeinput", function (event) {
      if (event.inputType !== "deleteContentBackward") return;
      if (deleteAmountDigitBeforeSuffix(this)) event.preventDefault();
    });
    inputEl.addEventListener("input", function () {
      var prevValue = String(this.value || "");
      var prevCaret = this.selectionStart;
      var raw = prevValue.replace(/[^0-9]/g, "");
      if (!raw) {
        this.value = "";
        if (onRecalc) onRecalc();
        if (scheduleSave) scheduleSave();
        return;
      }
      var num = parseInt(raw, 10);
      var formatted = formatDepositDisplay(num);
      this.value = formatted;
      restoreAmountCaret(this, prevValue, prevCaret, formatted);
      if (onRecalc) onRecalc();
      if (scheduleSave) scheduleSave();
    });
  }
  function bindWizardDepositInput(root, scheduleSave) {
    var depositEl = root.querySelector("#wiz-deposit-amount");
    if (!depositEl) {
      return;
    }
    bindWizardAmountInput(depositEl, root, scheduleSave, function () {
      recalcWizardAmounts(root);
    });
    if (depositEl.dataset.fomsWizardDepositBlurBound === "1") {
      return;
    }
    depositEl.dataset.fomsWizardDepositBlurBound = "1";
    depositEl.addEventListener("blur", function () {
      var items = collectProducts(root);
      var itemsTotal = 0;
      items.forEach(function (item) {
        itemsTotal += parseAmount(item && item.price);
      });
      var num = parseAmount(this.value);
      // 상한(출고가)이 아직 0이면 clamp 하지 않는다 — 최초 입력 시 값 증발 방지.
      if (itemsTotal > 0) {
        num = Math.min(num, itemsTotal);
      }
      this.value = num ? formatDepositDisplay(num) : "";
      recalcWizardAmounts(root);
    });
  }
  function bindWizardPriceInputs(root, scheduleSave) {
    root.querySelectorAll('[data-product-field="price"]').forEach(function (priceEl) {
      bindWizardAmountInput(priceEl, root, scheduleSave, function () {
        recalcWizardAmounts(root);
      });
    });
  }
  function sumRow(dt, ddHtml) {
    return '<div class="foms-wizard__summary-row"><dt>' + esc(dt) + "</dt><dd>" + ddHtml + "</dd></div>";
  }

  function renderFlagsSummaryRow(root) {
    var flags = collectFlags(root);
    var chips = [];
    if (flags.regional_order) {
      var label = "지방주문";
      if (flags.regional_construction_type) {
        label += " · " + flags.regional_construction_type.replace(" 시공", "");
      }
      chips.push('<span class="foms-wizard__summary-flag">' + esc(label) + "</span>");
    }
    if (flags.factory2) {
      chips.push('<span class="foms-wizard__summary-flag">라홈시스템</span>');
    }
    if (flags.urgent) {
      chips.push('<span class="foms-wizard__summary-flag foms-wizard__summary-flag--urgent">긴급</span>');
    }
    if (!chips.length) {
      return "";
    }
    var body = '<span class="foms-wizard__summary-flags">' + chips.join("") + "</span>";
    if (flags.urgent && flags.urgent_reason) {
      body += '<div class="foms-wizard__summary-flag-reason">' + esc(flags.urgent_reason) + "</div>";
    }
    return sumRow("주문 구분", body);
  }

  function renderSummary(root) {
    var basic = collectBasic(root);
    var schedule = collectSchedule(root);
    var items = collectProducts(root);

    var basicBody = root.querySelector("#foms-wizard-summary-basic-body");
    if (basicBody) {
      basicBody.innerHTML =
        sumRow("고객", esc(basic.customer_name) || "-") +
        sumRow("연락처", '<span class="foms-tabular">' + (esc(basic.phone) || "-") + "</span>") +
        sumRow("주소", esc(basic.address) || "-") +
        (basic.orderer ? sumRow("발주사", esc(basic.orderer)) : "");
    }

    var total = 0;
    var prodBody = root.querySelector("#foms-wizard-summary-products-body");
    if (prodBody) {
      prodBody.innerHTML = items
        .map(function (i, idx) {
          var spec = (i.spec_rows && i.spec_rows[0]) || {};
          var dims = [spec.spec_width, spec.spec_depth, spec.spec_height].filter(Boolean).join(" × ");
          var amt = parseAmount(i.price);
          total += amt;
          return (
            '<div class="foms-wizard__summary-product">' +
            '<span class="foms-wizard__summary-product-name">' +
            (esc(i.product_name) || "(제품 " + (idx + 1) + ")") +
            "</span>" +
            (dims ? '<span class="foms-wizard__summary-product-spec foms-tabular">' + esc(dims) + "</span>" : "") +
            (amt ? '<span class="foms-wizard__summary-product-amt foms-tabular">' + amt.toLocaleString("ko-KR") + "원</span>" : "") +
            "</div>"
          );
        })
        .join("");
    }

    var payment = collectPayment(root);
    var totals = buildWizardTotals(items, payment.deposit);

    var totalEl = root.querySelector("#foms-wizard-summary-total");
    if (totalEl) {
      totalEl.textContent = totals.items_total.toLocaleString("ko-KR") + "원";
    }
    var depositRow = root.querySelector("#foms-wizard-summary-deposit-row");
    var depositEl = root.querySelector("#foms-wizard-summary-deposit");
    if (depositRow && depositEl) {
      if (totals.deposit_amount > 0) {
        depositRow.hidden = false;
        depositEl.textContent = totals.deposit_amount.toLocaleString("ko-KR") + "원";
      } else {
        depositRow.hidden = true;
        depositEl.textContent = "0원";
      }
    }
    var balanceRow = root.querySelector("#foms-wizard-summary-balance-row");
    var balanceEl = root.querySelector("#foms-wizard-summary-balance");
    if (balanceRow && balanceEl) {
      if (totals.items_total > 0) {
        balanceRow.hidden = false;
        balanceEl.textContent = totals.balance_amount.toLocaleString("ko-KR") + "원";
      } else {
        balanceRow.hidden = true;
        balanceEl.textContent = "0원";
      }
    }

    var schedBody = root.querySelector("#foms-wizard-summary-schedule-body");
    if (schedBody) {
      var meas = [schedule.measurement_date, schedule.measurement_time].filter(Boolean).join(" ");
      var cons = [schedule.construction_date, schedule.construction_time].filter(Boolean).join(" ");
      schedBody.innerHTML =
        sumRow("실측", '<span class="foms-tabular">' + (esc(meas) || "-") + "</span>") +
        sumRow("시공", '<span class="foms-tabular">' + (esc(cons) || "-") + "</span>") +
        (schedule.load_date ? sumRow("상차", '<span class="foms-tabular">' + esc(schedule.load_date) + "</span>") : "") +
        (schedule.sales_manager ? sumRow("영업", esc(schedule.sales_manager)) : "") +
        (schedule.construction_manager ? sumRow("시공담당", esc(schedule.construction_manager)) : "") +
        (schedule.notes ? sumRow("비고", esc(schedule.notes)) : "") +
        renderFlagsSummaryRow(root);
    }
  }

  function setStep(root, step) {
    var panels = root.querySelectorAll("[data-wizard-step]");
    panels.forEach(function (panel) {
      var n = parseInt(panel.getAttribute("data-wizard-step"), 10);
      panel.classList.toggle("is-active", n === step);
    });
    var counter = root.querySelector("#foms-wizard-counter");
    if (counter) {
      counter.textContent = step + " / " + MAX_STEP;
    }
    var segs = root.querySelectorAll(".foms-wizard__progress-seg");
    segs.forEach(function (seg, idx) {
      seg.classList.remove("is-done", "is-current");
      if (idx + 1 < step) {
        seg.classList.add("is-done");
      } else if (idx + 1 === step) {
        seg.classList.add("is-current");
      }
    });
    var prev = root.querySelector("#foms-wizard-prev");
    if (prev) {
      prev.disabled = step <= 1;
      prev.style.opacity = step <= 1 ? "0.5" : "1";
    }
    var next = root.querySelector("#foms-wizard-next");
    if (next) {
      next.textContent = step >= MAX_STEP ? "주문 등록" : "다음 →";
    }
    if (step === MAX_STEP) {
      renderSummary(root);
    }
    root.setAttribute("data-current-step", String(step));
  }

  function init() {
    var root = document.getElementById("foms-wizard-root");
    if (!root || !window.FomsDraftClient) {
      return;
    }

    var currentStep = parseInt(root.getAttribute("data-initial-step") || "1", 10);
    if (isNaN(currentStep) || currentStep < 1) {
      currentStep = 1;
    }
    if (currentStep > MAX_STEP) {
      currentStep = MAX_STEP;
    }

    var draftKey = root.getAttribute("data-draft-key") || "";

    var draftClient = new window.FomsDraftClient(root, {
      getStep: function () {
        return currentStep;
      },
      getPayload: function () {
        return buildPayload(root, currentStep);
      },
      onConflict: function (remote) {
        var dialog = root.querySelector("#foms-wizard-conflict");
        if (!dialog) return;
        dialog.classList.add("is-open");
        dialog._remote = remote;
      },
      onRecovered: function (remote) {
        var payload = remote.payload || {};
        applyPayload(root, payload, draftKey, function () {
          draftClient.scheduleSave();
        });
        if (payload.step) {
          currentStep = payload.step;
          setStep(root, currentStep);
        }
      },
    });

    window.fomsWizardDraftClient = draftClient; // 4단계 발송(wizard-send.js) 강제 flush 진입점
    draftClient.bindAutosave();
    setStep(root, currentStep);

    if (window.FomsWizardAttachments) {
      window.FomsWizardAttachments.bindAll(root, draftKey, function () {
        draftClient.scheduleSave();
      });
    }
    if (window.fomsProductItem && typeof window.fomsProductItem.initWizardProducts === "function") {
      window.fomsProductItem.initWizardProducts(root);
    }
    bindWizardDepositInput(root, function () {
      draftClient.scheduleSave();
    });
    bindWizardPriceInputs(root, function () {
      draftClient.scheduleSave();
    });
    recalcWizardAmounts(root);

    var addProductBtn = root.querySelector("#foms-wizard-add-product");
    if (addProductBtn) {
      addProductBtn.addEventListener("click", function () {
        var container = root.querySelector("#foms-wizard-products");
        if (!container) {
          return;
        }
        var addedCard = cloneProductCard(container, draftKey, function () {
          draftClient.scheduleSave();
        });
        // 사용자가 방금 만든 카드는 바로 입력할 수 있어야 한다(초안 복원 경로는 접힘 유지).
        if (addedCard) {
          revealEmptyProductCard(addedCard);
        }
        draftClient.scheduleSave();
      });
    }

    // 제품명 에러는 전역 키(errors.product_name)라 모든 카드를 함께 검사해야 한다.
    // 개별 카드 @input 즉시해제는 (1) 다른 카드가 비어도 조기 해제되어 다음 단계에서
    // 다시 뜨고 (2) 복제 카드에서 Alpine 디렉티브 바인딩이 누락될 수 있다.
    // 위임 리스너로 '모든 카드가 채워졌을 때만' 해제한다(복제 카드 포함 안정 동작).
    var productsContainer = root.querySelector("#foms-wizard-products");
    if (productsContainer) {
      productsContainer.addEventListener("input", function (e) {
        var target = e.target;
        if (target && target.matches && target.matches('[data-product-field="price"]')) {
          recalcWizardAmounts(root);
        }
        if (!target || !target.matches || !target.matches('[data-product-field="product_name"]')) {
          return;
        }
        var scan = findFirstEmptyProductCard(root);
        if (scan.count && !scan.firstEmpty) {
          clearAlpineErrors(root);
        }
      });
    }

    // 주문 구분 체크 → 하위 입력 노출 동기화(+ 초안 저장).
    syncFlagFieldVisibility(root);
    ["#wiz-flag-regional", "#wiz-flag-urgent"].forEach(function (sel) {
      var el = root.querySelector(sel);
      if (!el) {
        return;
      }
      el.addEventListener("change", function () {
        syncFlagFieldVisibility(root);
        draftClient.scheduleSave();
      });
    });
    var regionalTypeEl = root.querySelector("#wiz-regional-construction-type");
    if (regionalTypeEl) {
      regionalTypeEl.addEventListener("change", function () {
        if (readValue(regionalTypeEl)) {
          clearAlpineErrors(root);
        }
        draftClient.scheduleSave();
      });
    }

    // 규격 행 추가/삭제(위임 → 동적 카드/행 대응).
    root.querySelectorAll("[data-product-index]").forEach(updateSpecDelVisibility);
    renumberProductCards(root.querySelector("#foms-wizard-products"));
    root.addEventListener("click", function (e) {
      var removeProductBtn = e.target.closest("[data-foms-product-remove]");
      if (removeProductBtn) {
        e.preventDefault();
        e.stopPropagation();
        var pContainer = root.querySelector("#foms-wizard-products");
        var pCard = removeProductBtn.closest("[data-product-index]");
        if (!pContainer || !pCard) {
          return;
        }
        if (pContainer.querySelectorAll("[data-product-index]").length <= 1) {
          return;
        }
        var pName = readValue(pCard.querySelector('[data-product-field="product_name"]'));
        var pLabel = pName || "제품 " + (parseInt(pCard.getAttribute("data-product-index") || "0", 10) + 1);
        if (!window.confirm(pLabel + " 항목을 삭제할까요?")) {
          return;
        }
        pCard.remove();
        renumberProductCards(pContainer);
        recalcWizardAmounts(root);
        var afterScan = findFirstEmptyProductCard(root);
        if (afterScan.count && !afterScan.firstEmpty) {
          clearAlpineErrors(root);
        }
        draftClient.scheduleSave();
        return;
      }
      var addBtn = e.target.closest("[data-spec-add]");
      if (addBtn) {
        var card = addBtn.closest("[data-product-index]");
        if (card) {
          var newRow = addSpecRow(card);
          if (newRow) {
            var f = newRow.querySelector("input");
            if (f && f.focus) f.focus();
          }
          draftClient.scheduleSave();
        }
        return;
      }
      var delBtn = e.target.closest("[data-spec-del]");
      if (delBtn) {
        var rowEl = delBtn.closest("[data-spec-row]");
        var delCard = delBtn.closest("[data-product-index]");
        if (rowEl) rowEl.remove();
        if (delCard) updateSpecDelVisibility(delCard);
        draftClient.scheduleSave();
        return;
      }
    });

    draftClient.load().then(function (remote) {
      if (!remote || !remote.payload) {
        return;
      }
      var toast = root.querySelector("#foms-wizard-recover");
      if (!toast) return;
      toast.classList.add("is-visible");
      toast._remote = remote;
    });

    var recoverBtn = root.querySelector("#foms-wizard-recover-btn");
    if (recoverBtn) {
      recoverBtn.addEventListener("click", function () {
        var toast = root.querySelector("#foms-wizard-recover");
        if (toast && toast._remote) {
          draftClient.applyRemote(toast._remote);
        }
        toast.classList.remove("is-visible");
      });
    }

    var conflict = root.querySelector("#foms-wizard-conflict");
    if (conflict) {
      conflict.addEventListener("click", function (ev) {
        var btn = ev.target.closest("[data-conflict]");
        if (!btn) return;
        var action = btn.getAttribute("data-conflict");
        var remoteRow = conflict._remote || {};
        var remotePayload = remoteRow.payload || {};
        if (action === "remote" && remoteRow) {
          draftClient.applyRemote(remoteRow);
        }
        if (action === "mine" && remoteRow.updated_at) {
          draftClient.updatedAt = remoteRow.updated_at;
          draftClient.flush();
        }
        if (action === "merge" && remotePayload) {
          var merged = mergeDraftPayload(buildPayload(root, currentStep), remotePayload);
          applyPayload(root, merged, draftKey, function () {
            draftClient.scheduleSave();
          });
          currentStep = merged.step || currentStep;
          setStep(root, currentStep);
          draftClient.updatedAt = remoteRow.updated_at || draftClient.updatedAt;
          draftClient.flush();
        }
        conflict.classList.remove("is-open");
      });
    }

    root.querySelector("#foms-wizard-prev").addEventListener("click", function () {
      if (currentStep <= 1) return;
      currentStep -= 1;
      setStep(root, currentStep);
      draftClient.scheduleSave();
    });

    root.querySelector("#foms-wizard-next").addEventListener("click", function () {
      var err = validateStep(root, currentStep);
      if (err) {
        if (window.fomsShowToast) {
          window.fomsShowToast(err);
        } else {
          window.alert(err);
        }
        return;
      }
      if (currentStep >= MAX_STEP) {
        draftClient.submitOrder().then(function (result) {
          if (result.data && result.data.success) {
            window.location.href = readWizardExitHref(root);
            return;
          }
          var msg =
            (result.data && result.data.error) ||
            "주문 등록에 실패했습니다.";
          window.alert(msg);
        });
        return;
      }
      currentStep += 1;
      setStep(root, currentStep);
      draftClient.scheduleSave();
    });

    root.querySelectorAll("[data-wizard-goto]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = parseInt(btn.getAttribute("data-wizard-goto"), 10);
        if (isNaN(target) || target < 1 || target > MAX_STEP) {
          return;
        }
        currentStep = target;
        setStep(root, currentStep);
        draftClient.scheduleSave();
      });
    });

    var closeBtn = root.querySelector("#foms-wizard-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        var exitHref = readWizardExitHref(root);
        draftClient.flush().finally(function () {
          window.location.href = exitHref;
        });
      });
    }
  }

  window.FomsWizardMergeDraftPayload = mergeDraftPayload;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
