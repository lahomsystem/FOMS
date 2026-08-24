/**
 * FOMS 모바일 셀렉트 → 바텀시트 피커 (재사용 · additive · 모바일 전용).
 *
 * 네이티브 <select>는 데이터 소스로 그대로 유지(change 계약·폼 제출 보존). 모바일·터치
 * 태블릿(<=991.98px 또는 coarse 포인터)에서 대상 select를 탭하면 네이티브 OS 팝업을 막고
 * 통일된 바텀시트로 옵션을 고른 뒤 value 설정 + input/change 디스패치 → 호스트 로직이 그대로 동작.
 * 동적 추가 행/옵션도 document 위임 + 열 때 live 옵션 읽기로 자동 대응.
 *
 * 입력 경로 2개: 터치는 touchend 취소(합성 mouse/click/focus 미발생 → iOS 네이티브 피커 차단),
 * 마우스/펜은 기존 mousedown 취소. iOS Safari 의 select 피커는 focus 로 뜨므로 시트를 닫을 때
 * 터치 기기에서는 포커스를 되돌리지 않는다(되돌리면 피커가 다시 뜬다).
 *
 * 대상(opt-in): select.foms-select, select[data-sheet]
 * 제외: [multiple], [disabled], [data-no-sheet], 숨김(d-none / offsetParent null)
 * 계산기 자체 selsheet는 .form-select(base-product/category/note)를 대상으로 하므로
 * 클래스가 겹치지 않아 무충돌(이중 바인딩 없음).
 */
(function () {
  "use strict";

  var MQ = window.matchMedia("(max-width: 991.98px), (pointer: coarse)");
  // iOS Safari 의 select 피커는 focus 기반(탭=포커스=피커)이라 합성 mousedown 취소로 막히지
  // 않는다. 터치 경로는 touchend 를 취소해 합성 mouse/click/focus 자체를 막고, 포커스 복원도
  // 건너뛴다(안드로이드/데스크톱 동작은 기존 mousedown 경로 그대로).
  var COARSE = window.matchMedia("(pointer: coarse)");
  var TAP_SLOP_PX = 10; // 이보다 많이 움직이면 스크롤 제스처로 보고 시트를 열지 않는다
  var sheet, backdrop, titleEl, bodyEl, currentSel;
  var touchSel = null,
    touchX = 0,
    touchY = 0,
    touchOpenAt = 0;

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
    // 이미 포커스가 붙었으면(iOS 는 그 순간 네이티브 피커가 뜬다) 떼어내 겹침을 없앤다.
    if (sel.blur) {
      try {
        sel.blur();
      } catch (e) {
        /* blur 미지원 환경 무시 */
      }
    }
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
    // 터치 기기에서 select 포커스 복원 = iOS 네이티브 피커 재오픈("고르면 또 뜬다")이므로 생략.
    if (currentSel && currentSel.focus && !COARSE.matches) {
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
    if (Date.now() - touchOpenAt < 700) return; // 터치 경로가 이미 연 뒤의 합성 mousedown
    var sel = e.target && e.target.closest ? e.target.closest("select") : null;
    if (!isTarget(sel) || !isVisible(sel)) return;
    e.preventDefault(); // 네이티브 OS 팝업 차단(안드로이드/데스크톱: mousedown 기본동작)
    open(sel);
  }
  function onTouchStart(e) {
    touchSel = null;
    if (!MQ.matches || !e.touches || e.touches.length !== 1) return;
    var sel = e.target && e.target.closest ? e.target.closest("select") : null;
    if (!isTarget(sel) || !isVisible(sel)) return;
    touchSel = sel;
    touchX = e.touches[0].clientX;
    touchY = e.touches[0].clientY;
  }
  function onTouchEnd(e) {
    var sel = touchSel;
    touchSel = null;
    if (!sel) return;
    var t = e.changedTouches && e.changedTouches[0];
    if (!t) return;
    if (Math.abs(t.clientX - touchX) > TAP_SLOP_PX || Math.abs(t.clientY - touchY) > TAP_SLOP_PX) return;
    // touchend 취소 = 합성 mouse/click/focus 미발생 → iOS 네이티브 피커 차단.
    // touchstart 는 취소하지 않으므로 select 위에서 시작한 스크롤은 그대로 동작한다.
    e.preventDefault();
    touchOpenAt = Date.now();
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

  // 위임(동적 행 대응). 터치=touchend, 그 외=mousedown 을 preventDefault 해
  // 네이티브 팝업이 열리기 전에 차단한다(touchstart 는 살려 스크롤 보존).
  document.addEventListener("touchstart", onTouchStart, { passive: true });
  document.addEventListener("touchend", onTouchEnd, { passive: false });
  document.addEventListener("mousedown", onPointer);
  document.addEventListener("keydown", onKey);
  document.addEventListener("keydown", onEsc);
})();
