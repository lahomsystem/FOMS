/**
 * FOMS 태블릿 도면 작업실 갤러리 컨트롤 (목업 v8 프레임 03, 2026-07-13 · W-DRAWING).
 *
 * document 위임 싱글턴(perf 가드 G4 — 전역 listener 중복 바인딩 방지). 카드 탭 → 시트 로드는
 * 공용 tablet-side-sheet.js(data-foms-sheet-url)가 소유하므로 여기서 재구현하지 않는다.
 *
 *   1) 갤러리 카드 크기 토글(작게 220 / 보통 260 / 크게 320) — .foms-drawing-gallery 에
 *      is-size-sm|md|lg 클래스 적용 + localStorage 지속(fragment swap 시 재적용).
 *   2) long-press(~500ms) 다중 선택(프레임 03 note2) → 공용 벌크 배정 모달. 카드를 길게
 *      누르거나 "도면공 일괄 배정" 버튼으로 선택 모드에 진입한다. 선택 모드에서 카드 탭 =
 *      선택 토글(사이드 시트 억제 — capture 단계 stopPropagation 로 버블 시트 리스너 차단),
 *      공용 .foms-tablet-bulk-bar(foms-tablet-landscape.css 소유) 로 "N건 선택됨"+[일괄 배정]/
 *      [선택 해제] 를 띄운다. 선택 상태는 기존 PC 벌크 체크박스(.order-checkbox)를 구동해
 *      window.openBatchAssignModal(workbench-dashboard.js)과 /api/orders/batch-assign-draftsman
 *      저장 경로를 그대로 재사용한다(신규 배정 UI·엔드포인트·쿼리 없음 — tablet-bulk-select.js
 *      가 오더 그리드에서 쓰는 "기존 체크박스+모달 재사용" 패턴을 갤러리 카드에 이식).
 *   3) 관리 시트 "시트 전달" 버튼 → 기존 transfer-pending API(신규 엔드포인트 없음).
 *
 * 선택/포인터 배선은 코호트 게이트(MQ (min-width:992px) and (orientation:landscape) and
 * (pointer:coarse) AND CSS 마커 --foms-tablet-ui:ready — tablet-side-sheet.js 파생 규칙과 동일,
 * 이중 정의 금지) 안에서만 동작. 비코호트(PC/폰/세로)에선 완전 무동작(모든 포인터/선택 진입점이
 * cohortActive() 로 early-return). 크기 토글/전달/필터는 코호트 DOM 에만 요소가 존재하므로
 * 기존대로 게이트 없이 위임한다(off-cohort 무해).
 *
 * defer 로드(perf G1). idempotent 싱글턴(window.__FOMS_DRAWING_GALLERY_BOUND).
 */
(function () {
  "use strict";

  if (window.__FOMS_DRAWING_GALLERY_BOUND) return;
  window.__FOMS_DRAWING_GALLERY_BOUND = true;

  var SIZE_KEY = "foms:drawing-gallery-size";
  var SIZES = ["sm", "md", "lg"];
  var LONG_PRESS_MS = 500;
  var MOVE_CANCEL_PX = 10;
  var CARD_SELECTOR = ".foms-drawing-gallery-card[data-order-id]";
  var CHECK_SELECTOR = ".order-checkbox";

  // ── 코호트 게이트(SSOT 파생 — tablet-side-sheet.js/tablet-bulk-select.js 동일) ──────────
  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );
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

  // ── 카드 크기 토글 ─────────────────────────────────────────────────────────────────────
  function readSize() {
    var v = null;
    try {
      v = window.localStorage.getItem(SIZE_KEY);
    } catch (e) {
      v = null;
    }
    return SIZES.indexOf(v) >= 0 ? v : "md";
  }

  function writeSize(size) {
    try {
      window.localStorage.setItem(SIZE_KEY, size);
    } catch (e) {
      /* private mode 등 localStorage 불가 — 세션 내 적용만, 무음 금지 아님(치명 아님) */
    }
  }

  function applySize(size) {
    var gallery = document.querySelector(".foms-drawing-gallery");
    if (gallery) {
      SIZES.forEach(function (s) {
        gallery.classList.toggle("is-size-" + s, s === size);
      });
    }
    document.querySelectorAll("[data-foms-gallery-size]").forEach(function (btn) {
      var on = btn.getAttribute("data-foms-gallery-size") === size;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function syncSize() {
    applySize(readSize());
  }

  function submitFilterForm(el) {
    var form = el.closest("form");
    if (form) form.submit();
  }

  async function transferPending(orderId, btn) {
    if (!orderId) return;
    if (!window.confirm("전달 대기 중인 저장 시트를 담당자에게 전달할까요?")) return;
    btn.disabled = true;
    try {
      var res = await fetch(
        "/api/orders/" + encodeURIComponent(orderId) + "/drawing-wizard/transfer-pending",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: "", mode: "APPEND" }),
        }
      );
      var data = await res.json();
      if (data && data.success) {
        window.alert((data.data && data.data.message) || "전달되었습니다.");
        window.location.reload();
      } else {
        btn.disabled = false;
        window.alert("오류: " + ((data && data.message) || "전달 실패"));
      }
    } catch (err) {
      btn.disabled = false;
      console.error("[tablet-drawing-gallery] 시트 전달 실패", err);
      window.alert("전달 중 오류가 발생했습니다.");
    }
  }

  // ── long-press 다중 선택 ───────────────────────────────────────────────────────────────
  // 선택 상태(주문 id) 는 이 모듈이 소유하되, 카드 클래스(.is-selected)와 기존 PC 벌크
  // 체크박스(.order-checkbox — 갤러리와 동일 rows 로 렌더된 숨김 legacy 테이블)를 함께 구동한다.
  // 모달/저장이 .order-checkbox:checked 를 읽으므로 체크박스가 곧 배정 대상이다.
  var selectMode = false;
  var selectedIds = new Set();
  var bar = null;
  var barCount = null;
  var pressTimer = null;
  var pressCard = null;
  var pressX = 0;
  var pressY = 0;
  var consumeNextClick = false;

  function gallery() {
    return document.querySelector(".foms-drawing-gallery");
  }

  // contextual bar = 공용 .foms-tablet-bulk-bar 재사용(foms-tablet-landscape.css 가 코호트에서만
  // 표시). <body> 하위 싱글턴 — 표시/은닉은 hidden 속성으로 토글.
  function ensureBar() {
    if (bar) return;
    bar = document.createElement("div");
    bar.className = "foms-tablet-bulk-bar";
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "도면 선택 작업");
    bar.hidden = true;
    bar.innerHTML =
      '<span class="foms-tablet-bulk-bar__count"><strong>0</strong>건 선택됨</span>' +
      '<button type="button" class="foms-tablet-bulk-bar__action" data-foms-drawing-select-assign>일괄 배정</button>' +
      '<button type="button" class="foms-tablet-bulk-bar__clear" data-foms-drawing-select-clear>선택 해제</button>';
    document.body.appendChild(bar);
    barCount = bar.querySelector(".foms-tablet-bulk-bar__count strong");
    bar.querySelector("[data-foms-drawing-select-assign]").addEventListener("click", onBarAssign);
    bar.querySelector("[data-foms-drawing-select-clear]").addEventListener("click", exitSelectMode);
  }

  function updateBar() {
    if (barCount) barCount.textContent = String(selectedIds.size);
  }

  function findCheckbox(id) {
    return document.querySelector('.order-checkbox[value="' + id + '"]');
  }

  // 카드 하나의 선택 상태를 설정(카드 클래스 + 매칭 체크박스 동기). 체크박스 change 를 발화해
  // 기존 updateBatchBar(숨김 PC 바)와도 일관 유지(무해).
  function syncCheckbox(id, checked) {
    var cb = findCheckbox(id);
    if (!cb || cb.checked === checked) return;
    cb.checked = checked;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function setCardSelected(card, selected) {
    var id = card.getAttribute("data-order-id");
    if (!id) return;
    if (selected === selectedIds.has(id)) return;
    if (selected) selectedIds.add(id);
    else selectedIds.delete(id);
    card.classList.toggle("is-selected", selected);
    card.setAttribute("aria-pressed", selected ? "true" : "false");
    syncCheckbox(id, selected);
    updateBar();
  }

  function toggleCard(card) {
    setCardSelected(card, !selectedIds.has(card.getAttribute("data-order-id")));
  }

  // 모달 열기 직전: 모든 PC 체크박스를 현재 선택 집합에 강제 정합(모달·저장이 읽는 SSOT 확정).
  function syncAllCheckboxesToSelection() {
    Array.prototype.forEach.call(document.querySelectorAll(CHECK_SELECTOR), function (cb) {
      var want = selectedIds.has(cb.value);
      if (cb.checked !== want) {
        cb.checked = want;
        cb.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  function enterSelectMode() {
    if (!selectMode) {
      selectMode = true;
      var g = gallery();
      if (g) g.classList.add("is-selecting");
      ensureBar();
      bar.hidden = false;
    }
    updateBar();
  }

  function exitSelectMode() {
    selectMode = false;
    Array.prototype.forEach.call(
      document.querySelectorAll(CARD_SELECTOR + ".is-selected"),
      function (card) {
        card.classList.remove("is-selected");
        card.setAttribute("aria-pressed", "false");
      }
    );
    Array.prototype.forEach.call(document.querySelectorAll(CHECK_SELECTOR), function (cb) {
      if (cb.checked) {
        cb.checked = false;
        cb.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    selectedIds.clear();
    var g = gallery();
    if (g) g.classList.remove("is-selecting");
    if (bar) bar.hidden = true;
  }

  // 선택 → 기존 벌크 배정 모달(window.openBatchAssignModal, workbench-dashboard.js). 배정 대상은
  // syncAllCheckboxesToSelection 이 .order-checkbox:checked 로 확정한다.
  function onBarAssign() {
    if (selectedIds.size === 0) {
      window.alert("카드를 눌러 주문을 선택하세요.");
      return;
    }
    syncAllCheckboxesToSelection();
    if (typeof window.openBatchAssignModal === "function") {
      window.openBatchAssignModal();
    } else {
      window.alert("일괄 배정을 사용할 수 없습니다. 페이지를 새로고침해 주세요.");
    }
  }

  function clearPress() {
    if (pressTimer) {
      clearTimeout(pressTimer);
      pressTimer = null;
    }
    pressCard = null;
  }

  // long-press(pointer) → 선택 모드 진입 + 눌린 카드 선택. 스크롤(이동)은 취소.
  document.addEventListener(
    "pointerdown",
    function (ev) {
      consumeNextClick = false; // 새 상호작용 시작 — 이전 소비 플래그 초기화(staleness 방지)
      if (!cohortActive()) return;
      if (ev.pointerType === "mouse" && ev.button !== 0) return;
      var t = ev.target;
      if (!t || !t.closest) return;
      var card = t.closest(CARD_SELECTOR);
      if (!card) return;
      pressCard = card;
      pressX = ev.clientX;
      pressY = ev.clientY;
      if (pressTimer) clearTimeout(pressTimer);
      pressTimer = setTimeout(function () {
        pressTimer = null;
        if (!pressCard) return;
        enterSelectMode();
        setCardSelected(pressCard, true);
        consumeNextClick = true; // long-press 뒤 따라오는 click(시트 트리거)을 1회 소비
        pressCard = null;
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

  // 선택 모드 클릭 가로채기(capture — 버블 시트 리스너보다 먼저, stopPropagation 로 시트 억제).
  document.addEventListener(
    "click",
    function (ev) {
      if (!cohortActive()) return;
      var t = ev.target;
      if (!t || !t.closest) return;
      var card = t.closest(CARD_SELECTOR);
      // long-press 직후 따라오는 click 1회 소비(카드 위에서만) — 이미 long-press 가 선택했으므로
      // 이 click 이 토글을 되돌리거나 시트를 열지 않도록 차단.
      if (consumeNextClick && card) {
        consumeNextClick = false;
        ev.preventDefault();
        ev.stopPropagation();
        return;
      }
      if (!selectMode) return; // 비선택 모드 — 시트 기존 동작 온전 보존
      if (!card) return; // 카드 밖(바/버튼 등) 통과 → 각자 핸들러
      // 선택 모드 카드 탭 = 선택 토글 + 앵커 네비/시트 억제.
      ev.preventDefault();
      ev.stopPropagation();
      toggleCard(card);
    },
    true
  );

  // long-press 컨텍스트 메뉴 억제(카드가 <a> — 안드/데스크톱 우클릭 콜아웃 차단; iOS 콜아웃은 CSS).
  document.addEventListener("contextmenu", function (ev) {
    if (!cohortActive()) return;
    var t = ev.target;
    if (t && t.closest && t.closest(CARD_SELECTOR)) ev.preventDefault();
  });

  // ── 공용 클릭 위임(크기 토글 / 일괄 배정 진입 / 시트 전달) — 버블 ─────────────────────────
  document.addEventListener("click", function (ev) {
    var target = ev.target;
    if (!target || !target.closest) return;

    var sizeBtn = target.closest("[data-foms-gallery-size]");
    if (sizeBtn) {
      ev.preventDefault();
      var size = sizeBtn.getAttribute("data-foms-gallery-size");
      if (SIZES.indexOf(size) < 0) size = "md";
      writeSize(size);
      applySize(size);
      return;
    }

    // "도면공 일괄 배정" 버튼 = 선택 모드 진입 토글. 이미 선택 모드면 선택 있음 → 모달,
    // 선택 없음 → 선택 모드 종료(long-press 진입과 동일한 선택 UI 로 수렴).
    var bulkBtn = target.closest("[data-foms-drawing-bulk-assign]");
    if (bulkBtn) {
      ev.preventDefault();
      if (!selectMode) {
        enterSelectMode();
      } else if (selectedIds.size > 0) {
        onBarAssign();
      } else {
        exitSelectMode();
      }
      return;
    }

    var transferBtn = target.closest("[data-foms-drawing-transfer]");
    if (transferBtn && !transferBtn.disabled) {
      ev.preventDefault();
      transferPending(transferBtn.getAttribute("data-order-id"), transferBtn);
      return;
    }
  });

  // 정렬 셀렉트 / 체크박스 변경 = 필터 폼 즉시 제출(GET).
  document.addEventListener("change", function (ev) {
    var target = ev.target;
    if (target && target.closest && target.closest(".foms-drawing-workshop__autofilter")) {
      submitFilterForm(target);
    }
  });

  // 코호트 이탈(회전/포인터 변화) 시 선택 모드 정리.
  function onMqChange() {
    if (!cohortActive()) exitSelectMode();
  }
  if (typeof MQ.addEventListener === "function") {
    MQ.addEventListener("change", onMqChange);
  } else if (typeof MQ.addListener === "function") {
    MQ.addListener(onMqChange);
  }

  function init() {
    syncSize();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // ERP 셸 fragment swap 시 갤러리 DOM 교체 → 저장된 크기 재적용 + 선택 상태 리셋(stale 방지).
  document.addEventListener("foms:erp-shell-fragment-swapped", function () {
    clearPress();
    consumeNextClick = false;
    exitSelectMode();
    syncSize();
  });
})();
