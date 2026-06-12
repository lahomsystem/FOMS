/**
 * 신규 주문 wizard 보강 (additive · 모바일 친화).
 *   - 주소 🔍: Daum 우편번호 검색 → #wiz-address 자동 채움 + input 디스패치
 *   - 연락처 📇: Contacts Picker API 지원 기기에서만 노출 → 전화/이름 채움
 *   - 헤더 ?: 간단 도움말 토스트
 * 기존 wizard.js(draft/검증/스텝)는 건드리지 않는다.
 */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var root = document.getElementById("foms-wizard-root");
    if (!root) return;

    /* 주소 검색 (Daum 우편번호) */
    var addrBtn = root.querySelector("[data-wizard-postcode]");
    var addrInput = root.querySelector("#wiz-address");
    if (addrBtn) {
      addrBtn.addEventListener("click", function () {
        if (!window.daum || !window.daum.Postcode) {
          if (addrInput) addrInput.focus();
          return;
        }
        new window.daum.Postcode({
          oncomplete: function (data) {
            var addr = data.roadAddress || data.jibunAddress || data.address || "";
            if (addr && addrInput) {
              addrInput.value = addr;
              addrInput.dispatchEvent(new Event("input", { bubbles: true }));
              addrInput.focus();
            }
          },
        }).open();
      });
    }

    /* 전화부 가져오기 (Contacts Picker API · 지원 기기에서만 노출) */
    var contactsBtn = root.querySelector("[data-wizard-contacts]");
    var contactsHint = root.querySelector("#wiz-contacts-hint");
    var phoneInput = root.querySelector("#wiz-phone");
    var nameInput = root.querySelector("#wiz-customer-name");
    var supportsContacts =
      "contacts" in navigator && navigator.contacts && typeof navigator.contacts.select === "function";
    if (contactsBtn && supportsContacts) {
      contactsBtn.hidden = false;
      if (contactsHint) contactsHint.hidden = false;
      contactsBtn.addEventListener("click", function () {
        navigator.contacts
          .select(["name", "tel"], { multiple: false })
          .then(function (list) {
            var c = list && list[0];
            if (!c) return;
            if (phoneInput && c.tel && c.tel[0]) {
              phoneInput.value = c.tel[0];
              phoneInput.dispatchEvent(new Event("input", { bubbles: true }));
            }
            if (nameInput && !nameInput.value && c.name && c.name[0]) {
              nameInput.value = c.name[0];
              nameInput.dispatchEvent(new Event("input", { bubbles: true }));
            }
          })
          .catch(function () {
            /* 사용자 취소/권한 거부 무시 */
          });
      });
    }

    /* 헤더 도움말 */
    var helpBtn = root.querySelector("[data-wizard-help]");
    if (helpBtn) {
      helpBtn.addEventListener("click", function () {
        var msg = "필수 항목(*)을 입력하고 '다음'으로 진행하세요. 입력 내용은 자동 저장됩니다.";
        if (window.fomsShowToast) window.fomsShowToast(msg);
        else window.alert(msg);
      });
    }

    /* 콤보 필드: 프리셋 select + '직접 입력' → custom 입력. 실제 값은 canonical hidden에 동기화.
       data-combo="time"이면 08:30~17:00 30분 옵션을 주입. data-combo-for=canonical id,
       custom 입력 id = <canonical id>-custom. */
    function pad2(n) {
      return (n < 10 ? "0" : "") + n;
    }
    function injectTimeOptions(sel) {
      var custOpt = sel.querySelector('option[value="__custom__"]');
      for (var t = 8 * 60 + 30; t <= 17 * 60; t += 30) {
        var v = pad2(Math.floor(t / 60)) + ":" + pad2(t % 60);
        var o = document.createElement("option");
        o.value = v;
        o.textContent = v;
        sel.insertBefore(o, custOpt || null);
      }
    }
    function bindCombo(sel) {
      var canonical = document.getElementById(sel.getAttribute("data-combo-for"));
      if (!canonical) return;
      var custom = document.getElementById(sel.getAttribute("data-combo-for") + "-custom");
      if (sel.getAttribute("data-combo") === "time") injectTimeOptions(sel);

      function showCustom(on) {
        if (custom) custom.hidden = !on;
      }
      function fromCanonical() {
        var v = (canonical.value || "").trim();
        var isPreset =
          v &&
          Array.prototype.some.call(sel.options, function (o) {
            return o.value === v && o.value !== "__custom__";
          });
        if (isPreset) {
          sel.value = v;
          showCustom(false);
        } else if (v) {
          sel.value = "__custom__";
          if (custom) custom.value = v;
          showCustom(true);
        } else {
          sel.value = "";
          showCustom(false);
        }
      }
      function pushCanonical() {
        if (sel.value === "__custom__") {
          showCustom(true);
          canonical.value = custom ? custom.value : "";
        } else {
          showCustom(false);
          canonical.value = sel.value;
        }
        canonical.dispatchEvent(new Event("input", { bubbles: true }));
      }
      sel.addEventListener("change", function () {
        pushCanonical();
        if (sel.value === "__custom__" && custom) custom.focus();
      });
      if (custom) {
        custom.addEventListener("input", function () {
          if (sel.value === "__custom__") {
            canonical.value = custom.value;
            canonical.dispatchEvent(new Event("input", { bubbles: true }));
          }
        });
      }
      // 복구/프로그램적 적용(wizard.js apply*가 canonical에 change 디스패치) → 표시 재동기화.
      canonical.addEventListener("change", fromCanonical);
      fromCanonical();
    }
    Array.prototype.forEach.call(root.querySelectorAll("[data-combo]"), bindCombo);

    /* autosize textarea (ERP 폼 방식: 내부/옵션/기타/추가입력 자동 높이) */
    function sizeTextarea(ta) {
      ta.style.height = "auto";
      ta.style.height = Math.max(ta.scrollHeight, 44) + "px";
    }
    function sizeAll() {
      Array.prototype.forEach.call(root.querySelectorAll("textarea.foms-wizard__autosize"), sizeTextarea);
    }
    root.addEventListener("input", function (e) {
      if (e.target && e.target.matches && e.target.matches("textarea.foms-wizard__autosize")) {
        sizeTextarea(e.target);
      }
    });
    if (window.MutationObserver) {
      new MutationObserver(sizeAll).observe(root, { childList: true, subtree: true });
    }
    sizeAll();
  });
})();
