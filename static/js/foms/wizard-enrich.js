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
  });
})();
