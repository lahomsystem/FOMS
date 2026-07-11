/**
 * FOMS 태블릿 실측 특수형 split 동작 (W12) — 태블릿 가로(코호트)에서 좌측 고객 카드 탭 시
 * 우측 detail 패널에 기존 ERP Order edit fragment 로드. "실측 입력 = 주문 원장 직접 기록".
 *
 * 활성 코호트: (min-width: 992px) and (orientation: landscape) and (pointer: coarse).
 *   미매치(폰/세로/데스크톱) 시 완전 무동작(모든 작업이 MQ.matches 게이트 하위).
 *
 * fragment 로드는 공용 로더(fragment-loader.js) 재사용 — 사이드 시트와 단일 구현 공유.
 * idempotent: window.__FOMS_TABLET_MEASURE_BOUND 싱글턴 가드(perf G4 — 단일 document listener).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_MEASURE_BOUND) return;
  window.__FOMS_TABLET_MEASURE_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );
  var CARD_SELECTOR = ".foms-tablet-measure-card[data-order-id]";
  var LIST_SELECTOR = ".foms-tablet-measure-list";
  var DETAIL_SELECTOR = ".foms-tablet-measure-detail";

  function fragmentUrl(orderId) {
    return "/api/foms/fragment/order/" + encodeURIComponent(orderId) + "/edit?open=erp-order";
  }

  function markActive(card) {
    var cards = document.querySelectorAll(CARD_SELECTOR);
    Array.prototype.forEach.call(cards, function (el) {
      el.classList.remove("is-active");
    });
    if (card) card.classList.add("is-active");
  }

  function selectCard(card) {
    if (!card) return;
    var orderId = card.getAttribute("data-order-id");
    if (!orderId) return;
    var detailEl = document.querySelector(DETAIL_SELECTOR);
    if (!detailEl) return;
    if (!window.FomsFragmentLoader || typeof window.FomsFragmentLoader.load !== "function") {
      console.error("[foms-tablet-measure] FomsFragmentLoader 미로드 — detail 로드 중단");
      return;
    }
    markActive(card);
    window.FomsFragmentLoader.load(detailEl, fragmentUrl(orderId), {
      requestedWith: "foms-tablet-measure",
      source: "tablet-measure-detail",
      loadingText: "주문 원장 로딩 중…",
    });
  }

  // 단일 document 위임: 코호트에서만 동작. 좌측 카드 탭 → 우측 detail 로드.
  document.addEventListener("click", function (ev) {
    if (!MQ.matches) return;
    var target = ev.target;
    if (!target || !target.closest) return;
    var card = target.closest(CARD_SELECTOR);
    if (!card || !card.closest(LIST_SELECTOR)) return;
    ev.preventDefault();
    selectCard(card);
  });

  // 최초 진입/리스트 재렌더 시 첫 카드 자동 선택(빈 detail 방지).
  function autoSelect() {
    if (!MQ.matches) return;
    var list = document.querySelector(LIST_SELECTOR);
    if (!list) return;
    if (document.querySelector(CARD_SELECTOR + ".is-active")) return; // 이미 선택됨
    var first = document.querySelector(CARD_SELECTOR);
    if (first) selectCard(first);
  }

  // defer 이므로 DOM 파싱 후 실행 → 초기 1회 자동 선택.
  autoSelect();

  // 셸 탭 스왑 등으로 리스트가 재렌더되면 다시 자동 선택. 단, 이 모듈이 detail 을 로드하며
  // 스스로 디스패치하는 이벤트(source==='tablet-measure-detail')는 무한 루프 방지 위해 무시.
  document.addEventListener("foms:erp-shell-fragment-swapped", function (ev) {
    if (ev && ev.detail && ev.detail.source === "tablet-measure-detail") return;
    autoSelect();
  });
})();
