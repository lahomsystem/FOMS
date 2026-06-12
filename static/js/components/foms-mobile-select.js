/**
 * FOMS 모바일 셀렉트 → 바텀시트 피커 (재사용 · additive · 모바일 전용).
 *
 * 네이티브 <select>는 데이터 소스로 그대로 유지(change 계약·폼 제출 보존). 모바일
 * (<=991.98px)에서 대상 select를 탭하면 네이티브 OS 팝업을 막고 통일된 바텀시트로
 * 옵션을 고른 뒤 value 설정 + input/change 디스패치 → 호스트 로직이 그대로 동작.
 * 동적 추가 행/옵션도 document 위임 + 열 때 live 옵션 읽기로 자동 대응.
 *
 * 대상(opt-in): select.foms-select, select[data-sheet]
 * 제외: [multiple], [disabled], [data-no-sheet], 숨김(d-none / offsetParent null)
 * 계산기 자체 selsheet는 .form-select(base-product/category/note)를 대상으로 하므로
 * 클래스가 겹치지 않아 무충돌(이중 바인딩 없음).
 */
(function () {
  "use strict";

  var MQ = window.matchMedia("(max-width: 991.98px)");
  var sheet, backdrop, titleEl, bodyEl, currentSel;

  function isTarget(sel) {
    if (!sel || sel.tagName !== "SELECT") return false;
    if (sel.multiple || sel.disabled) return false;
    if (sel.hasAttribute("data-no-sheet")) return false;
    return sel.classList.contains("foms-select") || sel.hasAttribute("data-sheet");
  }
  function isVisible(el) {
    return !!(el && el.offsetParent !== null) && !el.classList.contains("d-none");
  }
  function escId(id) {
    if (window.CSS && CSS.escape) return CSS.escape(id);
    return id.replace(/([^\w-])/g, "\\$1");
  }

  function ensureSheet() {
    if (sheet) return;
    backdrop = document.createElement("div");
    backdrop.className = "foms-msel-backdrop";
    backdrop.hidden = true;
    sheet = document.createElement("div");
    sheet.className = "foms-msel-sheet";
    sheet.hidden = true;
    sheet.innerHTML =
      '<div class="foms-msel-sheet__grip"></div>' +
      '<div class="foms-msel-sheet__head"><span class="foms-msel-sheet__title"></span>' +
      '<button type="button" class="foms-msel-sheet__close" aria-label="닫기">✕</button></div>' +
      '<div class="foms-msel-sheet__body" role="listbox"></div>';
    document.body.appendChild(backdrop);
    document.body.appendChild(sheet);
    titleEl = sheet.querySelector(".foms-msel-sheet__title");
    bodyEl = sheet.querySelector(".foms-msel-sheet__body");
    backdrop.addEventListener("click", close);
    sheet.querySelector(".foms-msel-sheet__close").addEventListener("click", close);
  }

  function labelFor(sel) {
    if (sel.id) {
      var l = document.querySelector('label[for="' + escId(sel.id) + '"]');
      if (l && l.textContent.trim()) return l.textContent.trim();
    }
    var wrap = sel.closest(".foms-field, .mb-3, .form-group, .field, td, [class*='col-']");
    var lab = wrap ? wrap.querySelector("label") : null;
    if (lab && lab.textContent.trim()) return lab.textContent.trim();
    return sel.getAttribute("aria-label") || "선택";
  }

  function open(sel) {
    ensureSheet();
    currentSel = sel;
    titleEl.textContent = labelFor(sel);
    bodyEl.innerHTML = "";
    Array.prototype.forEach.call(sel.options, function (opt) {
      var item = document.createElement("button");
      item.type = "button";
      item.className =
        "foms-msel-opt" + (opt.value === sel.value ? " is-active" : "") + (opt.disabled ? " is-disabled" : "");
      item.setAttribute("role", "option");
      item.textContent = opt.textContent;
      if (!opt.disabled) {
        item.addEventListener("click", function () {
          if (sel.value !== opt.value) {
            sel.value = opt.value;
            sel.dispatchEvent(new Event("input", { bubbles: true }));
            sel.dispatchEvent(new Event("change", { bubbles: true }));
          }
          close();
        });
      }
      bodyEl.appendChild(item);
    });
    sheet.hidden = false;
    backdrop.hidden = false;
    document.body.classList.add("foms-msel-open");
    var active = bodyEl.querySelector(".foms-msel-opt.is-active");
    if (active && active.scrollIntoView) active.scrollIntoView({ block: "center" });
  }

  function close() {
    if (sheet) sheet.hidden = true;
    if (backdrop) backdrop.hidden = true;
    document.body.classList.remove("foms-msel-open");
    if (currentSel && currentSel.focus) {
      try {
        currentSel.focus({ preventScroll: true });
      } catch (e) {
        /* focus 옵션 미지원 환경 무시 */
      }
    }
    currentSel = null;
  }

  function onPointer(e) {
    if (!MQ.matches) return;
    var sel = e.target && e.target.closest ? e.target.closest("select") : null;
    if (!isTarget(sel) || !isVisible(sel)) return;
    e.preventDefault(); // 네이티브 OS 팝업 차단
    open(sel);
  }
  function onKey(e) {
    if (!MQ.matches) return;
    var sel = e.target && e.target.closest ? e.target.closest("select") : null;
    if (!isTarget(sel) || !isVisible(sel)) return;
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      open(sel);
    }
  }
  function onEsc(e) {
    if (e.key === "Escape" && sheet && !sheet.hidden) close();
  }

  // 위임(동적 행 대응). mousedown preventDefault로 네이티브 팝업을 연(open)되기 전에 차단.
  document.addEventListener("mousedown", onPointer);
  document.addEventListener("keydown", onKey);
  document.addEventListener("keydown", onEsc);
})();
