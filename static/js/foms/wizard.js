/**
 * 4-step new order wizard (P1-03).
 */
(function () {
  "use strict";

  var MAX_STEP = 4;

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
    };
  }

  function collectProducts(root) {
    var cards = root.querySelectorAll("[data-product-index]");
    var items = [];
    cards.forEach(function (card) {
      var specRow = card.querySelector("[data-spec-row]");
      var spec = {
        spec_width: readValue(specRow && specRow.querySelector('[data-product-field="spec_width"]')),
        spec_depth: readValue(specRow && specRow.querySelector('[data-product-field="spec_depth"]')),
        spec_height: readValue(specRow && specRow.querySelector('[data-product-field="spec_height"]')),
      };
      items.push({
        product_name: readValue(card.querySelector('[data-product-field="product_name"]')),
        spec_rows: [spec],
        internal: readValue(card.querySelector('[data-product-field="internal"]')),
        color: readValue(card.querySelector('[data-product-field="color"]')),
        option_detail: readValue(card.querySelector('[data-product-field="option_detail"]')),
        handle: readValue(card.querySelector('[data-product-field="handle"]')),
        misc: readValue(card.querySelector('[data-product-field="misc"]')),
        price: readValue(card.querySelector('[data-product-field="price"]')),
        measurement_date: "",
        construction_date: "",
        extra_input: "",
        attachments: [],
      });
    });
    return items;
  }

  function buildPayload(root, step) {
    var data = collectBasic(root);
    data.items = collectProducts(root);
    data.schedule = collectSchedule(root);
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
      }
    });
  }

  function applySchedule(root, schedule) {
    if (!schedule) return;
    var map = {
      "#wiz-measurement-date": schedule.measurement_date,
      "#wiz-measurement-time": schedule.measurement_time,
      "#wiz-construction-date": schedule.construction_date,
      "#wiz-construction-time": schedule.construction_time,
    };
    Object.keys(map).forEach(function (sel) {
      var el = root.querySelector(sel);
      if (el && map[sel]) {
        el.value = map[sel];
      }
    });
  }

  function applyProducts(root, items) {
    if (!items || !items.length) return;
    var card = root.querySelector("[data-product-index]");
    if (!card) return;
    var item = items[0];
    var fields = [
      "product_name",
      "internal",
      "color",
      "option_detail",
      "handle",
      "misc",
      "price",
    ];
    fields.forEach(function (name) {
      var el = card.querySelector('[data-product-field="' + name + '"]');
      if (el && item[name]) {
        el.value = item[name];
      }
    });
    var spec = (item.spec_rows && item.spec_rows[0]) || {};
    var specMap = {
      spec_width: spec.spec_width,
      spec_depth: spec.spec_depth,
      spec_height: spec.spec_height,
    };
    Object.keys(specMap).forEach(function (name) {
      var el = card.querySelector('[data-product-field="' + name + '"]');
      if (el && specMap[name]) {
        el.value = specMap[name];
      }
    });
  }

  function validateStep(root, step) {
    if (step === 1) {
      var basic = collectBasic(root);
      if (!basic.customer_name) return "고객명을 입력해주세요.";
      if (!basic.phone) return "연락처를 입력해주세요.";
      if (!basic.address) return "주소를 입력해주세요.";
    }
    if (step === 2) {
      var items = collectProducts(root);
      if (!items.length || !items[0].product_name) {
        return "제품명을 입력해주세요.";
      }
    }
    return "";
  }

  function renderSummary(root) {
    var basic = collectBasic(root);
    var schedule = collectSchedule(root);
    var items = collectProducts(root);
    var basicBody = root.querySelector("#foms-wizard-summary-basic-body");
    if (basicBody) {
      basicBody.innerHTML =
        "<dt>고객</dt><dd>" +
        basic.customer_name +
        " / " +
        basic.phone +
        "</dd>" +
        "<dt>주소</dt><dd>" +
        basic.address +
        "</dd>";
    }
    var schedBody = root.querySelector("#foms-wizard-summary-schedule-body");
    if (schedBody) {
      schedBody.innerHTML =
        "<dt>실측</dt><dd>" +
        (schedule.measurement_date || "-") +
        " " +
        (schedule.measurement_time || "") +
        "</dd>" +
        "<dt>시공</dt><dd>" +
        (schedule.construction_date || "-") +
        " " +
        (schedule.construction_time || "") +
        "</dd>";
    }
    var prodBody = root.querySelector("#foms-wizard-summary-products-body");
    if (prodBody) {
      prodBody.textContent = items.map(function (i) {
        return i.product_name || "(제품)";
      }).join(", ");
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
        var data = payload.data || {};
        applyBasic(root, data);
        applyProducts(root, data.items);
        applySchedule(root, data.schedule);
        if (payload.step) {
          currentStep = payload.step;
          setStep(root, currentStep);
        }
      },
    });

    draftClient.bindAutosave();
    setStep(root, currentStep);

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
        if (action === "remote" && conflict._remote) {
          draftClient.applyRemote(conflict._remote);
        }
        if (action === "mine") {
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
            window.location.href = "/orders/";
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

    var closeBtn = root.querySelector("#foms-wizard-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        draftClient.flush().finally(function () {
          window.location.href = "/orders/";
        });
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
