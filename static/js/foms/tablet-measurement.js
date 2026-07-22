/**
 * FOMS 태블릿 실측 특수형 split 동작 (W12 → W-MEASURE-FORM) — 태블릿 가로(코호트)에서 좌측
 * 고객 카드 탭 시 우측 detail 패널에 "실측 전용 터치 폼"을 로드한다(목업 frame02).
 * 이전(W12)의 PC ERP Order edit fragment 주입은 폐기하고, 전용 폼 모듈(tablet-measure-form.js,
 * window.FomsTabletMeasureForm)에 위임한다. 데이터는 동일 구조화 API(GET/PUT /structured)로
 * 읽고 쓴다(신규 백엔드 없음). "실측 입력 = 주문 원장 직접 기록"은 유지.
 *
 * 이 파일의 책임은 좌측 큐(검색·필터칩·카드 선택·자동선택)와 컨텍스트 바(전화/내비/이름/단계)이며,
 * 우측 폼의 렌더·저장·단계전환은 전적으로 FomsTabletMeasureForm 이 담당한다(관심사 분리).
 * 좌측 큐의 검색창(고객명·주소·초성)·필터칩(전체/오늘/주간/미확정)은 표시 카드만 client-side
 * 필터한다(서버 재조회·우측 패널 재로드 없음).
 *
 * 활성 게이트(SSOT): MQ (min-width: 992px) and (orientation: landscape) and (pointer: coarse)
 *   AND CSS 마커 --foms-tablet-ui:ready(foms-tablet-side-sheet.css 정의, v2 셸 번들 로드
 *   여부에서 파생 — defect 1). 미매치 또는 마커 부재 시 완전 무동작.
 *
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
  var CHIP_SELECTOR = ".foms-tablet-measure-chip[data-measure-bucket]";
  var SEARCH_SELECTOR = "[data-foms-tablet-measure-search]";
  var FILTER_EMPTY_SELECTOR = "[data-foms-tablet-measure-filter-empty]";

  // 컨텍스트 바 / 액션바 앵커·컨트롤(카드 선택 시 채움 / 전용 폼 모듈 트리거).
  var CONTEXT_SELECTOR = "[data-foms-tablet-measure-context]";
  var CONTEXT_NAME_SELECTOR = "[data-foms-tablet-measure-context-name]";
  var CONTEXT_STAGE_SELECTOR = "[data-foms-tablet-measure-context-stage]";
  var CONTEXT_CALL_SELECTOR = "[data-foms-tablet-measure-context-call]";
  var CONTEXT_NAV_SELECTOR = "[data-foms-tablet-measure-context-nav]";
  var ACTIONS_SELECTOR = "[data-foms-tablet-measure-actions]";
  var SAVE_BTN_SELECTOR = "[data-foms-tablet-measure-save]";
  var COMPLETE_BTN_SELECTOR = "[data-foms-tablet-measure-complete]";
  // 목업 frame13 크롬(상단 바 탭 / 하단 채널톡·임시저장) — 폼 공개 API 로 위임.
  var TABS_NAV_SELECTOR = "[data-foms-tmf-tabs]";
  var TAB_SELECTOR = "[data-foms-tmf-tab]";
  var CHANNEL_SELECTOR = "[data-foms-tmf-channel]";
  var DRAFT_SELECTOR = "[data-foms-tmf-draft]";

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
    // 외부 탭(주문/계산기/견적서) 크롬 노출 — 탭 활성 상태·계산기 토글 표시는 폼 모듈이 소유.
    var tabs = section.querySelector(TABS_NAV_SELECTOR);
    if (tabs) tabs.hidden = false;
  }

  // [저장] → 전용 폼 모듈의 명시 저장(read-merge-write PUT + 충돌 가드). 상태 표시는 폼 모듈 소유.
  function triggerSave() {
    if (window.FomsTabletMeasureForm && typeof window.FomsTabletMeasureForm.requestSave === "function") {
      window.FomsTabletMeasureForm.requestSave();
    } else {
      console.warn("[foms-tablet-measure] FomsTabletMeasureForm 미로드 — 저장 트리거 불가");
    }
  }

  // [실측 완료] → 전용 폼 모듈이 2-tap 확인 후 저장 → MEASURE 퀘스트 승인 API 호출(서버가 단계 전환).
  function triggerComplete() {
    if (window.FomsTabletMeasureForm && typeof window.FomsTabletMeasureForm.requestComplete === "function") {
      window.FomsTabletMeasureForm.requestComplete();
    } else {
      console.warn("[foms-tablet-measure] FomsTabletMeasureForm 미로드 — 실측 완료 트리거 불가");
    }
  }

  // 목업 frame13 크롬 → 폼 공개 API 위임(폼 모듈이 렌더·데이터·상태 소유). 미로드 시 무동작(방어).
  function formApi(name) {
    return window.FomsTabletMeasureForm && typeof window.FomsTabletMeasureForm[name] === "function"
      ? window.FomsTabletMeasureForm[name]
      : null;
  }
  function triggerDraft() {
    var fn = formApi("requestDraft");
    if (fn) fn();
  }
  function triggerChannel() {
    var fn = formApi("requestChannelPush");
    if (fn) fn();
  }
  function triggerTab(tab) {
    var fn = formApi("switchTab");
    if (fn) fn(tab);
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
    if (!window.FomsTabletMeasureForm || typeof window.FomsTabletMeasureForm.load !== "function") {
      console.error("[foms-tablet-measure] FomsTabletMeasureForm 미로드 — 실측 폼 로드 중단");
      return;
    }
    markActive(card);
    populateContext(card);
    // 전용 폼 모듈이 detail 스크롤 영역에 GET /structured 로 폼을 렌더한다(컨텍스트 바·액션바는 형제라 생존).
    window.FomsTabletMeasureForm.load(orderId, {
      editUrl: card.getAttribute("data-edit-url") || "",
      customerName: card.getAttribute("data-customer-name") || "",
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

    // 상단/하단 크롬(주입 영역 밖) — [탭][저장][실측 완료][임시 저장][채널톡].
    // 컨텍스트 바 전화/내비는 네이티브 <a> 라 여기서 가로채지 않는다(tel:/새 탭 정상 동작).
    var tabBtn = target.closest(TAB_SELECTOR);
    if (tabBtn && tabBtn.closest(DETAIL_SELECTOR)) {
      ev.preventDefault();
      triggerTab(tabBtn.getAttribute("data-foms-tmf-tab"));
      return;
    }
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
    var draftBtn = target.closest(DRAFT_SELECTOR);
    if (draftBtn && draftBtn.closest(DETAIL_SELECTOR)) {
      ev.preventDefault();
      triggerDraft();
      return;
    }
    var channelBtn = target.closest(CHANNEL_SELECTOR);
    if (channelBtn && channelBtn.closest(DETAIL_SELECTOR)) {
      ev.preventDefault();
      triggerChannel();
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

  // 키보드 1급(목업 note 3): Ctrl/Cmd+S → 명시 저장(브라우저 저장 대화상자 억제).
  // 코호트 + 폼 로드(우측 주입 영역에 [data-foms-tmf] 존재) 상태에서만 가로챈다.
  document.addEventListener(
    "keydown",
    function (ev) {
      if (!cohortActive()) return;
      var key = ev.key || "";
      if (!(ev.ctrlKey || ev.metaKey) || (key !== "s" && key !== "S")) return;
      var detail = document.querySelector(DETAIL_SELECTOR);
      if (!detail || !detail.querySelector("[data-foms-tmf]")) return;
      ev.preventDefault();
      triggerSave();
    },
    true
  );

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

  // 셸 탭 스왑 등으로 리스트가 재렌더되면 다시 자동 선택(이미 활성 카드가 있으면 no-op).
  // 전용 폼 모듈은 plain fetch 로 렌더하므로 이 이벤트를 디스패치하지 않는다(무한 루프 없음);
  // source 가드는 방어적으로 유지한다.
  document.addEventListener("foms:erp-shell-fragment-swapped", function (ev) {
    if (ev && ev.detail && ev.detail.source === "tablet-measure-detail") return;
    autoSelect();
  });
})();
