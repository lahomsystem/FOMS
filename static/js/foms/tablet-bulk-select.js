/**
 * FOMS 태블릿 벌크 선택 (프레임 12) — 태블릿 가로 코호트에서 주문 대시보드 그리드 행을
 * long-press(~500ms) 하면 선택 모드에 진입한다. 선택 모드에서 행 탭 = 선택 토글(사이드
 * 시트 억제), 상단에 contextual bar("N건 선택됨" + 상태 일괄 변경 + 선택 해제)를 띄운다.
 *
 * 중복 구현 금지: 실제 선택 상태는 기존 PC 벌크 체크박스(.erp-grid-order-check)를, 일괄
 * 실행은 기존 벌크 바(#erp-grid-bulk-bar: 상태 select + 적용 + 복사, count>0 시 자동 표시)를
 * 그대로 재사용한다. 이 모듈은 (1) long-press 진입, (2) 선택 모드 chrome(contextual bar),
 * (3) 시트 억제만 신규로 얹으며, 선택 변경은 기존 체크박스의 change 이벤트로 반영한다.
 * contextual bar 의 "상태 일괄 변경" 버튼은 기존 #erp-grid-bulk-status 로 포커스만 이동한다
 * (액션 UI 중복 생성 금지 — 기존 벌크 바가 소유).
 *
 * 게이트(SSOT): tablet-side-sheet.js 와 동일 — MQ (min-width: 992px) and
 *   (orientation: landscape) and (pointer: coarse) AND CSS 마커 --foms-tablet-ui:ready
 *   (foms-tablet-side-sheet.css 가 body.erp-mobile-v2-layout 에 정의). 비-코호트(PC/폰/세로)
 *   에선 완전 무동작(모든 진입점이 cohortActive() 로 early-return).
 *
 * 시트 충돌 회피(수정 금지 tablet-side-sheet.js): 시트 JS 는 document 클릭 **버블** 위임으로
 *   행 탭 → 시트를 연다. 선택 모드에서는 이 모듈이 document 클릭을 **capture 단계**(3번째
 *   인자 true)에서 가로채 stopPropagation() 하여 버블 시트 리스너 도달 자체를 차단하고 행
 *   탭을 선택 토글로 바꾼다. 인터랙티브 요소(a/button/input/select/label/textarea/
 *   [role=button])는 그대로 통과 — 기존 액션·체크박스 동작 보존, 시트도 이들을 제외하므로
 *   미발화. 비선택 모드에서는 아무것도 가로채지 않아 시트 기존 동작이 온전히 보존된다.
 *
 * idempotent: window.__FOMS_TABLET_BULK_SELECT_BOUND 싱글턴 가드(perf 가드 G4 — 전역 listener
 *   중복 바인딩 방지). 로드: erp-dashboard-entry.js CHAIN 동적 주입(async=false) — 렌더 비차단
 *   (perf 가드 G1, 동기 <script> 아님), 대시보드 프래그먼트 스왑마다 재kick 되나 위 싱글턴이 흡수.
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_BULK_SELECT_BOUND) return;
  window.__FOMS_TABLET_BULK_SELECT_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );
  var LONG_PRESS_MS = 500;
  var MOVE_CANCEL_PX = 10;
  var GRID_SELECTOR = "#erp-grid";
  var ROW_SELECTOR = "#erp-grid tr.erp-main-row[data-order-id]";
  var CHECK_SELECTOR = ".erp-grid-order-check";
  var SELECT_ALL_ID = "erp-grid-select-all";
  var INTERACTIVE = 'a, button, input, select, label, textarea, [role="button"]';

  // 코호트 게이트 = MQ 매치 AND CSS 마커(--foms-tablet-ui:ready). tablet-side-sheet.js 와 동일
  // 파생 규칙(이중 정의 금지). CSS 로드 상태는 페이지 수명 내 불변이라 positive 결과만 캐시.
  var _uiReady = false;
  function tabletUiReady() {
    if (_uiReady) return true;
    var body = document.body;
    if (!body) return false;
    var v = window.getComputedStyle(body).getPropertyValue("--foms-tablet-ui");
    if (v && v.trim() === "ready") _uiReady = true;
    return _uiReady;
  }
  function cohortActive() {
    return MQ.matches && tabletUiReady();
  }

  var selectionActive = false;
  var bar = null;
  var barCount = null;
  var pressTimer = null;
  var pressRow = null;
  var pressX = 0;
  var pressY = 0;
  var consumeNextClick = false;

  function grid() {
    return document.querySelector(GRID_SELECTOR);
  }

  // contextual bar DOM 은 1회만 생성(<body> 하위, 싱글턴). 표시/은닉은 hidden 속성 + CSS 게이트.
  function ensureBar() {
    if (bar) return;
    bar = document.createElement("div");
    bar.className = "foms-tablet-bulk-bar";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "선택 작업");
    bar.hidden = true;
    bar.innerHTML =
      '<span class="foms-tablet-bulk-bar__count"><strong>0</strong>건 선택됨</span>' +
      '<button type="button" class="foms-tablet-bulk-bar__action">상태 일괄 변경</button>' +
      '<button type="button" class="foms-tablet-bulk-bar__clear">선택 해제</button>';
    document.body.appendChild(bar);
    barCount = bar.querySelector(".foms-tablet-bulk-bar__count strong");
    bar.querySelector(".foms-tablet-bulk-bar__action").addEventListener("click", onActionClick);
    bar.querySelector(".foms-tablet-bulk-bar__clear").addEventListener("click", clearSelection);
  }

  // "상태 일괄 변경" = 기존 벌크 바의 상태 select 로 포커스 이동(액션 UI 재사용, 중복 생성 금지).
  function onActionClick() {
    var sel = document.getElementById("erp-grid-bulk-status");
    if (!sel) return;
    if (typeof sel.scrollIntoView === "function") sel.scrollIntoView({ block: "nearest" });
    try {
      sel.focus();
    } catch (e) {
      /* focus 미지원 무시 */
    }
  }

  // 그리드 전체 체크박스를 훑어 카운트/행 강조/모드 활성을 동기화(기존 detail-dom 카운트와
  // 병행 — 각자 자기 UI만 갱신, 중복 아님). count>0 = 선택 모드 활성.
  function syncSelection() {
    var g = grid();
    if (!g) {
      deactivate();
      return;
    }
    var boxes = g.querySelectorAll(CHECK_SELECTOR);
    var n = 0;
    Array.prototype.forEach.call(boxes, function (cb) {
      if (cb.checked) n++;
      var row = cb.closest("tr.erp-main-row");
      if (row) row.classList.toggle("foms-tablet-bulk-selected", cb.checked);
    });
    if (n > 0) activate(n);
    else deactivate();
  }

  function activate(n) {
    ensureBar();
    selectionActive = true;
    document.body.classList.add("foms-tablet-bulk-mode");
    if (barCount) barCount.textContent = String(n);
    bar.hidden = false;
  }

  function deactivate() {
    selectionActive = false;
    document.body.classList.remove("foms-tablet-bulk-mode");
    if (bar) bar.hidden = true;
  }

  // 선택 해제 = 기존 체크박스를 모두 끄고 change 를 발화(기존 벌크 바도 함께 숨김) + 모드 종료.
  function clearSelection() {
    var g = grid();
    if (g) {
      Array.prototype.forEach.call(g.querySelectorAll(CHECK_SELECTOR), function (cb) {
        if (cb.checked) {
          cb.checked = false;
          cb.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
      var all = document.getElementById(SELECT_ALL_ID);
      if (all) all.checked = false;
    }
    deactivate();
  }

  // 행의 기존 체크박스를 켜고 change 를 발화(기존 벌크 메커니즘이 카운트/바를 갱신).
  function selectRow(row) {
    var cb = row.querySelector(CHECK_SELECTOR);
    if (!cb) return;
    if (!cb.checked) {
      cb.checked = true;
      cb.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      syncSelection();
    }
  }

  function clearPress() {
    if (pressTimer) {
      clearTimeout(pressTimer);
      pressTimer = null;
    }
    pressRow = null;
  }

  // ---- long-press(pointer) → 선택 모드 진입 + 눌린 행 선택. 스크롤(이동)은 취소. ----
  document.addEventListener(
    "pointerdown",
    function (ev) {
      consumeNextClick = false; // 새 상호작용 시작 — 이전 소비 플래그 초기화(staleness 방지)
      if (!cohortActive()) return;
      if (ev.pointerType === "mouse" && ev.button !== 0) return;
      var t = ev.target;
      if (!t || !t.closest) return;
      var row = t.closest(ROW_SELECTOR);
      var g = grid();
      if (!row || !g || !g.contains(row)) return;
      // 인터랙티브 요소 위에서 시작한 long-press 는 무시(버튼/입력/체크박스 조작 보존).
      if (t.closest(INTERACTIVE)) return;
      // 체크박스 없는 행(비편집 권한)은 벌크 대상이 아님.
      if (!row.querySelector(CHECK_SELECTOR)) return;
      pressRow = row;
      pressX = ev.clientX;
      pressY = ev.clientY;
      if (pressTimer) clearTimeout(pressTimer);
      pressTimer = setTimeout(function () {
        pressTimer = null;
        if (!pressRow) return;
        selectRow(pressRow);
        consumeNextClick = true; // long-press 뒤 따라오는 click(시트 트리거)을 1회 소비
        pressRow = null;
      }, LONG_PRESS_MS);
    },
    true
  );
  document.addEventListener(
    "pointermove",
    function (ev) {
      if (!pressTimer) return;
      if (
        Math.abs(ev.clientX - pressX) > MOVE_CANCEL_PX ||
        Math.abs(ev.clientY - pressY) > MOVE_CANCEL_PX
      ) {
        clearPress(); // 스크롤/드래그 → long-press 취소
      }
    },
    true
  );
  document.addEventListener("pointerup", clearPress, true);
  document.addEventListener("pointercancel", clearPress, true);

  // ---- 선택 모드 클릭 가로채기(capture — 버블 시트 리스너보다 먼저, stopPropagation 로 시트 억제) ----
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    var row = t.closest(ROW_SELECTOR);
    // long-press 직후 따라오는 click 1회 소비(행 위에서만) — 이미 long-press 가 선택했으므로
    // 이 click 이 토글을 되돌리거나 시트를 열지 않도록 차단.
    if (consumeNextClick && row) {
      consumeNextClick = false;
      ev.preventDefault();
      ev.stopPropagation();
      return;
    }
    if (!selectionActive) return; // 비선택 모드 — 시트 기존 동작 온전히 보존
    if (!row) return; // 그리드 밖(contextual bar 등) 통과
    if (t.closest(INTERACTIVE)) return; // 체크박스/버튼/링크 등은 그대로(시트도 제외 → 미발화)
    // 비인터랙티브 행 영역 탭 = 선택 토글 + 시트 억제(capture stopPropagation).
    ev.preventDefault();
    ev.stopPropagation();
    var cb = row.querySelector(CHECK_SELECTOR);
    if (cb) {
      cb.checked = !cb.checked;
      cb.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }, true);

  // ---- 체크박스/전체선택 change → 선택 상태 동기화(직접 체크박스 탭·select-all 경로 커버) ----
  document.addEventListener("change", function (ev) {
    var t = ev.target;
    if (!t) return;
    var isCheck = t.classList && t.classList.contains("erp-grid-order-check");
    if (isCheck || t.id === SELECT_ALL_ID) syncSelection();
  });

  // ---- 코호트 이탈(회전/포인터 변화) 시 모드 정리 ----
  function onMqChange() {
    if (!cohortActive()) deactivate();
  }
  if (typeof MQ.addEventListener === "function") {
    MQ.addEventListener("change", onMqChange);
  } else if (typeof MQ.addListener === "function") {
    MQ.addListener(onMqChange);
  }

  // ---- 프래그먼트 스왑(탭 이동 등)으로 그리드 재삽입 시 상태 재동기화 ----
  function onSwap() {
    clearPress();
    consumeNextClick = false;
    syncSelection();
  }
  document.addEventListener("foms:erp-shell-fragment-swapped", onSwap);
  document.addEventListener("foms:main-content-swapped", onSwap);
})();
