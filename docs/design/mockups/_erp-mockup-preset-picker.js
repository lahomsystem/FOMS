/**
 * ERP 제품 속성 sheet — mockup preset/option picker (운영 ErpSpecPicker UI 재사용).
 * 목업 전용: API 없이 대표 프리셋·옵션 목록으로 드롭다운/다중선택 시연.
 */
(function () {
  "use strict";

  var FIELD_LABELS = {
    color: "색상",
    handle: "손잡이",
    internal: "내부",
    misc: "기타 / 설치위치",
    option_detail: "옵션",
  };

  var MOCK_PRESETS = {
    color: ["화이트", "그레이", "우드", "오크", "매트블랙", "상담"],
    handle: ["히든손잡이", "바형", "노브형", "푸쉬", "J형", "상담"],
    internal: ["서랍", "옷걸이봉", "선반", "거울", "바지걸이", "상담"],
    misc: ["상담", "현장 협의", "시공 후 결정", "없음"],
  };

  function mockItem(key, label, meta) {
    return {
      key: key,
      label: label,
      meta: meta || "",
      payload: { key: key, label: label, name: label },
    };
  }

  var MOCK_INTERNAL_GROUPS = [
    {
      label: "내부구성",
      items: [
        mockItem("내부구성 > 서랍", "서랍"),
        mockItem("내부구성 > 옷걸이봉", "옷걸이봉"),
        mockItem("내부구성 > 선반", "선반"),
        mockItem("내부구성 > 거울", "거울"),
        mockItem("내부구성 > 바지걸이", "바지걸이"),
      ],
    },
  ];

  var MOCK_OPTION_GROUPS = [
    {
      label: "구조·기능",
      items: [
        mockItem("구조 > 높이조절다리", "높이조절다리", "120,000원"),
        mockItem("구조 > 서랍분리형", "서랍분리형", "80,000원"),
        mockItem("구조 > 양쪽끝 라운딩", "양쪽끝 라운딩", "50,000원"),
        mockItem("구조 > 속선반 추가", "속선반 추가", "30,000원"),
      ],
    },
    {
      label: "마감",
      items: [
        mockItem("마감 > 몰딩", "몰딩", "40,000원"),
        mockItem("마감 > LED", "LED", "90,000원"),
      ],
    },
  ];

  function singleItems(values) {
    return (values || [])
      .filter(function (v) { return v != null && v !== ""; })
      .map(function (v) { return { value: String(v), text: String(v) }; });
  }

  function payloadLabel(p) {
    if (!p) return "";
    if (p.label) return String(p.label);
    if (p.name) return String(p.name);
    if (p.key) {
      var parts = String(p.key).split(">");
      return parts[parts.length - 1].trim();
    }
    return "";
  }

  function splitComma(val) {
    return String(val || "")
      .split(/[,，+]/)
      .map(function (s) { return s.trim(); })
      .filter(Boolean);
  }

  function joinComma(parts) {
    return (parts || []).filter(Boolean).join("+");
  }

  function autosizeControl(el) {
    if (!el) return;
    if (typeof window.erpAutosizeTextarea === "function") {
      window.erpAutosizeTextarea(el);
      return;
    }
    if (el.classList.contains("erp-autosize-textarea")) {
      el.style.height = "0";
      var min = el.dataset.erpMinHeight ? Number(el.dataset.erpMinHeight) : 0;
      el.style.height = Math.max(el.scrollHeight, min) + "px";
    }
  }

  function setControlValue(ctrl, value) {
    if (!ctrl) return;
    ctrl.value = value != null ? String(value) : "";
    ctrl.dispatchEvent(new Event("input", { bubbles: true }));
    autosizeControl(ctrl);
  }

  function resolveField(btn) {
    var explicit = btn.getAttribute("data-erp-preset-field");
    if (explicit) return explicit;
    var wrap = btn.closest(".erp-calc-field--sheet");
    var ctrl = wrap && wrap.querySelector("[data-erp]");
    return ctrl ? ctrl.getAttribute("data-erp") : "";
  }

  function resolveControl(row, field) {
    if (!row || !field) return null;
    return row.querySelector('[data-erp="' + field + '"]');
  }

  function currentInternalKeys(ctrl) {
    var names = splitComma(ctrl && ctrl.value);
    var keys = [];
    names.forEach(function (name) {
      keys.push("내부구성 > " + name);
    });
    return keys;
  }

  function currentOptionKeys(ctrl) {
    var names = splitComma(ctrl && ctrl.value);
    var keys = [];
    MOCK_OPTION_GROUPS.forEach(function (group) {
      (group.items || []).forEach(function (item) {
        if (names.indexOf(item.label) >= 0) keys.push(item.key);
      });
    });
    return keys;
  }

  function openPresetPicker(row, field, anchor) {
    if (!window.ErpSpecPicker) return;
    var ctrl = resolveControl(row, field);
    if (field === "internal") {
      window.ErpSpecPicker.openMulti({
        title: "내부 선택",
        anchor: anchor,
        groups: MOCK_INTERNAL_GROUPS,
        selectedKeys: currentInternalKeys(ctrl),
        onConfirm: function (payloads) {
          var names = (payloads || []).map(payloadLabel).filter(Boolean);
          setControlValue(ctrl, joinComma(names.length ? names : ["상담"]));
        },
      });
      return;
    }
    if (field === "option_detail") {
      window.ErpSpecPicker.openMulti({
        title: "옵션 선택",
        anchor: anchor,
        groups: MOCK_OPTION_GROUPS,
        selectedKeys: currentOptionKeys(ctrl),
        onConfirm: function (payloads) {
          var names = (payloads || []).map(payloadLabel).filter(Boolean);
          setControlValue(ctrl, joinComma(names.length ? names : ["상담"]));
        },
      });
      return;
    }
    var values = MOCK_PRESETS[field] || ["상담"];
    window.ErpSpecPicker.openSingle({
      title: (FIELD_LABELS[field] || field) + " 선택",
      anchor: anchor,
      current: ctrl ? ctrl.value : "",
      topItems: singleItems(values),
      onPick: function (value) {
        setControlValue(ctrl, value);
      },
    });
  }

  /**
   * 제품 속성 sheet ▾ 트리거에 mock preset picker 바인딩.
   * @param {ParentNode} root
   */
  function bindPresetSheetPickers(root) {
    if (!window.ErpSpecPicker) return;
    var scope = root || document;
    scope.querySelectorAll(".erp-preset-sheet .erp-calc-trigger").forEach(function (btn) {
      if (btn.dataset.erpMockPickerBound === "1") return;
      btn.dataset.erpMockPickerBound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var field = resolveField(btn);
        var row = btn.closest(".erp-item-row");
        var anchor = btn.closest(".erp-calc-field--sheet") || btn;
        openPresetPicker(row, field, anchor);
      });
    });
  }

  window.erpMockBindPresetSheetPickers = bindPresetSheetPickers;

  function initMockPresetPickers() {
    bindPresetSheetPickers(document);
  }

  if (document.readyState === "complete") {
    initMockPresetPickers();
  } else {
    window.addEventListener("load", initMockPresetPickers);
  }
})();
