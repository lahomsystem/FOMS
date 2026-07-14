/**
 * FOMS 공용 밀도 토글 (태블릿 가로 목업 프레임 공통) — 그리드 행 높이 40/48(기본)/56 전환.
 *
 * 컴포넌트: `.foms-density-toggle`(pcbar 우측 세그먼트, 3버튼 40/48/56). 각 토글은
 *   `data-density-target`(CSS 셀렉터)으로 대상 그리드를 가리키고, 선택 시 그 대상에
 *   `data-foms-density="40|48|56"` 속성을 부착한다. 행 높이 3단은 CSS(foms-tablet-landscape.css)
 *   가 소유하며 기본(속성 없음)=48. 선택값은 localStorage(`foms_tablet_density`)에 저장하고
 *   부트/프래그먼트 스왑마다 복원한다.
 *
 * 표시 게이트는 CSS(coarse landscape 코호트)가 소유한다 — JS는 활성 코호트 여부를 판정하지
 * 않고 위임만 한다(토글이 은닉된 코호트에선 클릭 자체가 발생하지 않음). document 위임이라
 * fragment 스왑으로 토글 DOM이 재삽입돼도 재바인딩이 필요 없고, 스왑 이벤트에는 저장값
 * 재적용 리스너만 건다.
 *
 * idempotent: window.__FOMS_DENSITY_TOGGLE_BOUND 싱글턴 가드(perf 가드 G4 — 전역 listener
 * 중복 바인딩 방지).
 */
(function () {
  "use strict";

  if (window.__FOMS_DENSITY_TOGGLE_BOUND) return;
  window.__FOMS_DENSITY_TOGGLE_BOUND = true;

  var STORAGE_KEY = "foms_tablet_density";
  var ALLOWED = ["40", "48", "56"];
  var DEFAULT_DENSITY = "48";

  function readStored() {
    try {
      var v = window.localStorage.getItem(STORAGE_KEY);
      return ALLOWED.indexOf(v) >= 0 ? v : DEFAULT_DENSITY;
    } catch (e) {
      return DEFAULT_DENSITY;
    }
  }

  function writeStored(value) {
    try {
      window.localStorage.setItem(STORAGE_KEY, value);
    } catch (e) {
      /* 저장 불가(사생활 모드 등) — 세션 내 표시만 유지, 무음 금지 아님(비치명적). */
    }
  }

  // 하나의 토글이 가리키는 대상 그리드(들)에 밀도 속성을 부착한다. 대상 미발견은 우아하게 무시.
  function applyToTargets(toggle, value) {
    var sel = toggle.getAttribute("data-density-target");
    if (!sel) return;
    var targets;
    try {
      targets = document.querySelectorAll(sel);
    } catch (e) {
      console.warn("[foms-density-toggle] 잘못된 data-density-target 셀렉터 — 무시", sel, e);
      return;
    }
    Array.prototype.forEach.call(targets, function (el) {
      el.setAttribute("data-foms-density", value);
    });
  }

  // 토글 세그먼트의 활성 버튼 표시(aria-pressed + is-active 클래스).
  function syncButtons(toggle, value) {
    var btns = toggle.querySelectorAll(".foms-density-toggle__btn");
    Array.prototype.forEach.call(btns, function (btn) {
      var on = btn.getAttribute("data-density") === value;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  // 저장값을 페이지의 모든 토글 + 대상 그리드에 재적용(부트/스왑 복원). idempotent.
  function restoreAll() {
    var value = readStored();
    var toggles = document.querySelectorAll(".foms-density-toggle");
    Array.prototype.forEach.call(toggles, function (toggle) {
      applyToTargets(toggle, value);
      syncButtons(toggle, value);
    });
  }

  // 단일 document 위임: 세그먼트 버튼 클릭 → 저장 + 전 토글/대상 동기화.
  document.addEventListener("click", function (ev) {
    var target = ev.target;
    if (!target || !target.closest) return;
    var btn = target.closest(".foms-density-toggle__btn");
    if (!btn) return;
    var toggle = btn.closest(".foms-density-toggle");
    if (!toggle) return;
    var value = btn.getAttribute("data-density");
    if (ALLOWED.indexOf(value) < 0) return;
    ev.preventDefault();
    writeStored(value);
    // 같은 대상을 가리키는 여러 토글이 있어도 일관 유지 — 전역 복원으로 동기화.
    restoreAll();
  });

  // fragment 스왑(탭 이동 등)으로 토글/그리드 DOM이 재삽입되면 저장값을 재적용.
  document.addEventListener("foms:erp-shell-fragment-swapped", restoreAll);
  document.addEventListener("foms:main-content-swapped", restoreAll);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restoreAll);
  } else {
    restoreAll();
  }
})();
