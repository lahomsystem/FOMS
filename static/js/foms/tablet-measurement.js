/**
 * FOMS 태블릿 실측 특수형 split 동작 (W12) — 태블릿 가로(코호트)에서 좌측 고객 카드 탭 시
 * 우측 detail 패널에 기존 ERP Order edit fragment 로드. "실측 입력 = 주문 원장 직접 기록".
 * 좌측 큐의 검색창(고객명·주소·초성)·필터칩(전체/오늘/주간/미확정)은 표시 카드만
 * client-side 필터한다(서버 재조회·우측 패널 재로드 없음 — 키 입력마다 fragment 재요청 금지).
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   AND CSS 마커 --foms-tablet-ui:ready(foms-tablet-side-sheet.css 정의, v2 셸 번들 로드
 *   여부에서 파생 — defect 1). 미매치 또는 마커 부재 시 완전 무동작.
 *
 * fragment 로드는 공용 로더(fragment-loader.js) 재사용 — 사이드 시트와 단일 구현 공유.
 * idempotent: window.__FOMS_TABLET_MEASURE_BOUND 싱글턴 가드(perf G4 — document listener
 * (click·input) 중복 바인딩 차단). 필터 상태는 DOM 에서 매번 읽어 리렌더에도 안전.
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_MEASURE_BOUND) return;
  window.__FOMS_TABLET_MEASURE_BOUND = true;

  var MQ = window.matchMedia(
    "(min-width: 992px) and (orientation: landscape) and (pointer: coarse)"
  );

  // 코호트 게이트 = MQ AND CSS 마커(--foms-tablet-ui:ready). 마커는 시트 CSS가
  // body.erp-mobile-v2-layout 에 정의(v2 번들 로드 여부에서 파생 — defect 1, 이중 정의 금지).
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

  var CARD_SELECTOR = ".foms-tablet-measure-card[data-order-id]";
  var LIST_SELECTOR = ".foms-tablet-measure-list";
  var DETAIL_SELECTOR = ".foms-tablet-measure-detail";
  // fragment 주입 타깃 = detail 안의 스크롤 영역만(컨텍스트 바·액션바는 형제라 innerHTML 교체에도 생존).
  var INJECT_SELECTOR = "[data-foms-tablet-measure-detail]";
  var CHIP_SELECTOR = ".foms-tablet-measure-chip[data-measure-bucket]";
  var SEARCH_SELECTOR = "[data-foms-tablet-measure-search]";
  var FILTER_EMPTY_SELECTOR = "[data-foms-tablet-measure-filter-empty]";

  // 컨텍스트 바 / 액션바 앵커·컨트롤(카드 선택 시 채움 / fragment 실 컨트롤 트리거).
  var CONTEXT_SELECTOR = "[data-foms-tablet-measure-context]";
  var CONTEXT_NAME_SELECTOR = "[data-foms-tablet-measure-context-name]";
  var CONTEXT_STAGE_SELECTOR = "[data-foms-tablet-measure-context-stage]";
  var CONTEXT_CALL_SELECTOR = "[data-foms-tablet-measure-context-call]";
  var CONTEXT_NAV_SELECTOR = "[data-foms-tablet-measure-context-nav]";
  var ACTIONS_SELECTOR = "[data-foms-tablet-measure-actions]";
  var SAVE_BTN_SELECTOR = "[data-foms-tablet-measure-save]";
  var COMPLETE_BTN_SELECTOR = "[data-foms-tablet-measure-complete]";
  // 주입된 fragment 의 실 컨트롤(트리거 대상 — DOM/이벤트 계약 재사용, fork 금지).
  var FRAGMENT_SAVE_SELECTOR = "#erp-save-btn";
  var FRAGMENT_STAGE_SELECTOR = "#erp-workflow-stage";

  function fragmentUrl(orderId) {
    return "/api/foms/fragment/order/" + encodeURIComponent(orderId) + "/edit?open=erp-order";
  }

  // 카드 data-* → 컨텍스트 바 채움. 전화=tel: 링크, 내비=naver map 웹 URL(새 탭).
  // 값이 없으면 해당 버튼/배지를 숨긴다.
  function populateContext(card) {
    var section = document.querySelector(DETAIL_SELECTOR);
    if (!section) return;
    var ctx = section.querySelector(CONTEXT_SELECTOR);
    if (!ctx) return;
    var name = card.getAttribute("data-customer-name") || "-";
    var phone = (card.getAttribute("data-phone") || "").trim();
    var addr = (card.getAttribute("data-nav-address") || "").trim();
    var stageLbl = (card.getAttribute("data-stage-label") || "").trim();
    var stageMod = card.getAttribute("data-stage-modifier") || "--received";

    var nameEl = ctx.querySelector(CONTEXT_NAME_SELECTOR);
    if (nameEl) nameEl.textContent = name;

    var stageEl = ctx.querySelector(CONTEXT_STAGE_SELECTOR);
    if (stageEl) {
      stageEl.textContent = stageLbl;
      stageEl.className =
        "foms-stage-badge foms-stage-badge" + stageMod + " foms-tablet-measure-context__stage";
      stageEl.hidden = !stageLbl;
    }

    var callEl = ctx.querySelector(CONTEXT_CALL_SELECTOR);
    if (callEl) {
      if (phone) {
        callEl.href = "tel:" + phone.replace(/[^0-9+]/g, "");
        callEl.hidden = false;
      } else {
        callEl.removeAttribute("href");
        callEl.hidden = true;
      }
    }

    var navEl = ctx.querySelector(CONTEXT_NAV_SELECTOR);
    if (navEl) {
      if (addr) {
        navEl.href = "https://map.naver.com/v5/search/" + encodeURIComponent(addr);
        navEl.hidden = false;
      } else {
        navEl.removeAttribute("href");
        navEl.hidden = true;
      }
    }

    ctx.hidden = false;
    var actions = section.querySelector(ACTIONS_SELECTOR);
    if (actions) actions.hidden = false;
  }

  // [저장] → 주입 fragment 의 실 저장 버튼(#erp-save-btn) 클릭 트리거 + 짧은 "자동저장됨" 상태.
  function triggerSave() {
    var inject = document.querySelector(INJECT_SELECTOR);
    var btn = inject ? inject.querySelector(FRAGMENT_SAVE_SELECTOR) : null;
    if (!btn) {
      console.warn("[foms-tablet-measure] " + FRAGMENT_SAVE_SELECTOR + " 미발견 — 저장 트리거 불가");
      return;
    }
    btn.click();
    flashSaved();
  }

  function flashSaved() {
    var section = document.querySelector(DETAIL_SELECTOR);
    var btn = section ? section.querySelector(SAVE_BTN_SELECTOR) : null;
    var label = btn ? btn.querySelector("span") : null;
    if (!btn || !label) return;
    if (btn.__prevLabel == null) btn.__prevLabel = label.textContent;
    label.textContent = "자동저장됨";
    btn.classList.add("is-saved");
    window.clearTimeout(btn.__savedTimer);
    btn.__savedTimer = window.setTimeout(function () {
      label.textContent = btn.__prevLabel;
      btn.__prevLabel = null;
      btn.classList.remove("is-saved");
    }, 1600);
  }

  // [실측 완료] → 단일 "다음 단계" 컨트롤이 없으므로(위험한 자동 stage 변경 금지) 주입 fragment 의
  // 단계(Workflow) select(#erp-workflow-stage)로 스크롤 + 포커스해 사용자가 직접 전환하게 한다.
  function triggerComplete() {
    var inject = document.querySelector(INJECT_SELECTOR);
    var stage = inject ? inject.querySelector(FRAGMENT_STAGE_SELECTOR) : null;
    if (!stage) {
      console.warn("[foms-tablet-measure] " + FRAGMENT_STAGE_SELECTOR + " 미발견 — 단계 포커스 불가");
      return;
    }
    try {
      stage.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {
      stage.scrollIntoView();
    }
    stage.focus();
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
    // fragment 는 스크롤 영역에만 주입(컨텍스트 바·액션바는 형제 → innerHTML 교체에 생존).
    var injectEl = document.querySelector(INJECT_SELECTOR);
    if (!injectEl) return;
    if (!window.FomsFragmentLoader || typeof window.FomsFragmentLoader.load !== "function") {
      console.error("[foms-tablet-measure] FomsFragmentLoader 미로드 — detail 로드 중단");
      return;
    }
    markActive(card);
    populateContext(card);
    window.FomsFragmentLoader.load(injectEl, fragmentUrl(orderId), {
      requestedWith: "foms-tablet-measure",
      source: "tablet-measure-detail",
      loadingText: "주문 원장 로딩 중…",
    });
  }

  // ── 검색·필터칩(좌측 큐 표시 카드에만 적용; 우측 패널 재로드 없음) ───────────────
  // 한글 초성 자모(음절 → 초성 분해용). 초성 검색 매칭에 사용.
  var CHOSUNG = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
  ];
  function chosungOf(str) {
    var out = "";
    for (var i = 0; i < str.length; i++) {
      var code = str.charCodeAt(i);
      if (code >= 0xac00 && code <= 0xd7a3) {
        out += CHOSUNG[Math.floor((code - 0xac00) / 588)];
      } else {
        out += str.charAt(i);
      }
    }
    return out;
  }
  function isChosungQuery(q) {
    if (!q) return false;
    for (var i = 0; i < q.length; i++) {
      if (CHOSUNG.indexOf(q.charAt(i)) === -1) return false;
    }
    return true;
  }

  function cardMatchesSearch(card, q) {
    if (!q) return true;
    var name = card.getAttribute("data-customer") || "";
    var addr = card.getAttribute("data-address") || "";
    if (name.indexOf(q) !== -1 || addr.indexOf(q) !== -1) return true;
    // 초성 질의(자모만)일 때 고객명 초성 시퀀스로 추가 매칭.
    if (isChosungQuery(q) && chosungOf(name).indexOf(q) !== -1) return true;
    return false;
  }

  function cardMatchesBucket(card, bucket) {
    if (!bucket || bucket === "all") return true;
    var raw = card.getAttribute("data-measure-days");
    var undated = raw === null || raw === "";
    if (bucket === "undated") return undated;
    if (undated) return false;
    var days = parseInt(raw, 10);
    if (isNaN(days)) return false;
    if (bucket === "today") return days === 0;
    if (bucket === "week") return days >= 0 && days <= 6;
    return true;
  }

  function setActiveChip(chip) {
    var chips = document.querySelectorAll(CHIP_SELECTOR);
    Array.prototype.forEach.call(chips, function (el) {
      var on = el === chip;
      el.classList.toggle("is-active", on);
      el.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function applyFilters() {
    var list = document.querySelector(LIST_SELECTOR);
    if (!list) return;
    var searchEl = list.querySelector(SEARCH_SELECTOR);
    var q = searchEl ? searchEl.value.trim().toLowerCase() : "";
    var activeChip = list.querySelector(CHIP_SELECTOR + ".is-active");
    var bucket = activeChip ? activeChip.getAttribute("data-measure-bucket") : "all";
    var cards = list.querySelectorAll(CARD_SELECTOR);
    var visible = 0;
    Array.prototype.forEach.call(cards, function (card) {
      var show = cardMatchesSearch(card, q) && cardMatchesBucket(card, bucket);
      card.classList.toggle("is-filtered-out", !show);
      if (show) visible += 1;
    });
    var emptyEl = list.querySelector(FILTER_EMPTY_SELECTOR);
    if (emptyEl) {
      // 원본 카드가 있으면서 필터 결과 0건일 때만 필터-빈 안내 노출.
      emptyEl.hidden = !(cards.length > 0 && visible === 0);
    }
  }

  // 단일 document 위임: 코호트에서만 동작. 칩 탭 → 필터, 카드 탭 → 우측 detail 로드.
  document.addEventListener("click", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.closest) return;

    var chip = target.closest(CHIP_SELECTOR);
    if (chip && chip.closest(LIST_SELECTOR)) {
      ev.preventDefault();
      setActiveChip(chip);
      applyFilters();
      return;
    }

    // 하단 액션바(주입 영역 밖) — [저장]·[실측 완료]. 컨텍스트 바 전화/내비는 네이티브 <a> 라
    // 여기서 가로채지 않는다(preventDefault 없음 → tel:/새 탭 정상 동작).
    var saveBtn = target.closest(SAVE_BTN_SELECTOR);
    if (saveBtn && saveBtn.closest(DETAIL_SELECTOR)) {
      ev.preventDefault();
      triggerSave();
      return;
    }
    var completeBtn = target.closest(COMPLETE_BTN_SELECTOR);
    if (completeBtn && completeBtn.closest(DETAIL_SELECTOR)) {
      ev.preventDefault();
      triggerComplete();
      return;
    }

    var card = target.closest(CARD_SELECTOR);
    if (!card || !card.closest(LIST_SELECTOR)) return;
    ev.preventDefault();
    selectCard(card);
  });

  // 검색 입력: 코호트에서만. 표시 카드 client-side 필터(고객명·주소·초성).
  document.addEventListener("input", function (ev) {
    if (!cohortActive()) return;
    var target = ev.target;
    if (!target || !target.matches || !target.matches(SEARCH_SELECTOR)) return;
    if (!target.closest(LIST_SELECTOR)) return;
    applyFilters();
  });

  // 최초 진입/리스트 재렌더 시 첫 카드 자동 선택(빈 detail 방지).
  function autoSelect() {
    if (!cohortActive()) return;
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
