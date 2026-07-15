/**
 * WDCalculator 태블릿 가로 융합 셸(JS) — 목업 frame11 그라운드업 재구현 (2026-07-15).
 *
 * 이전(도킹판)은 pcbar·우측 패널·하단 바만 만들고 본문은 PC 카드(견적 정보 입력/견적 결과/
 * 쿠폰가/배송비 카드)를 그대로 둬 "이중 구조"가 됐다. 본판은 목업 frame11 의 IA 를 코호트
 * (coarse landscape ≥992, 비임베디드)에서 **전면 재조립**한다. 계산 엔진·저장 API·DOM id 는
 * 일절 재구현하지 않고, 기존 노드를 **재부모화(DOM move)**·미러링으로만 프레임에 끼운다.
 *
 * 엔진 접근 방식 조사 결과(재배치 안전성 근거):
 *   - 입력/컨테이너 노드는 전부 getElementById 로 접근(#baseComponentsContainer 등 97곳) +
 *     컨테이너 위임 이벤트(base container click/input/change) + 문서 위임(estimatesListContainer
 *     클릭 = handleEstimateListClick, container.contains 체크) → 노드를 옮겨도 id·리스너·value
 *     전부 보존된다. 따라서 **이동(move)** 이 안전한 이상적 케이스.
 *   - 예외 2개는 **미러(관찰+위임 클릭)**: (1) #saveEstimateBtn 은 엔진이 initSaveEstimateButton
 *     에서 cloneNode+replaceChild 로 교체 → 옮기면 undock 복원 시 stale 참조가 됨. (2)
 *     #resetEstimateBtn 은 엔진이 .header-primary 에 동적 생성/removeChild → 사전 이동 불가.
 *   - #calculateBtn/#addEstimateBtn 은 직접 addEventListener(clone 없음) → 이동 안전(하단 바로).
 *
 * 프레임(목업 frame11):
 *   (1) 슬림 pcbar(main-scroll sticky): "WD 계산기" + 이동한 #customerName 그룹 + 고객 견적
 *       검색(저장 오버레이 토글) + 이동한 제품 설정 링크.
 *   (2) 본문(.wdc-tf-body): 기본 구성 카드(#baseComponentsContainer+추가 버튼) / 추가 옵션 카드
 *       (#additionalOptionsContainer+추가 버튼) | 쿠폰·배송·비고 카드(#globalCouponValue·
 *       #shippingCost·#shippingIncluded·#notesContainer+추가 버튼) / 견적 결과 요약 스트립
 *       (기본·옵션·총견적·쿠폰 = 이동한 라이브 노드, 정보 무손실).
 *   (3) 우측 320px "진행 견적" 패널(shell 내 absolute 상시): 총 견적 hl-tile(#totalAllFinalPrice
 *       미러) + 이동한 #estimatesListContainer(수정/이름/삭제 = 문서 위임 보존) + foot(새 견적=
 *       #resetEstimateBtn 미러클릭·전체 저장=#saveEstimateBtn 미러클릭).
 *   (4) 하단 고정 최종견적 바: #finalPrice 미러 + 이동한 #calculateBtn/#addEstimateBtn(주 액션).
 *
 * PC 크롬(헤더·카드 래퍼·견적 결과 카드 등)은 코호트에서 CSS 로 은닉 — DOM 에는 남겨(엔진이
 * .header-primary 등을 querySelector 하므로 제거 금지). 잔재 0 = 목업 IA 만 노출.
 *
 * 게이트: (min-width:992px) and (orientation:landscape) and (pointer:coarse) 且 비임베디드.
 * 게이트 이탈(회전/리사이즈)→ 이동 노드를 **원위치 복원**하고 주입 클래스 제거(PC·폰·임베디드
 * 무회귀). 폰 셸(mobile-enhance.js, ≤991.98)이 이미 DOM 을 접수했으면(body.wd-builder) 스킨을
 * 양보(이중 재부모화 방지 — 소형 태블릿 세로→가로 회전 엣지케이스).
 *
 * 성능 가드 G4: 전역/문서 리스너는 singleton 가드로 1회만 바인딩(fragment 재실행 무해).
 */
(function () {
  'use strict';

  if (window.__WDC_TABLET_SKIN_BOUND) { return; }
  window.__WDC_TABLET_SKIN_BOUND = true;

  var STORAGE_KEY = 'wdcTabletSavedOpen';   // '1' = 저장 오버레이 펼침 상태 기억
  var GATE = '(min-width: 992px) and (orientation: landscape) and (pointer: coarse)';

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      fn();
    }
  }

  function el(tag, className, html) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (html != null) { node.innerHTML = html; }
    return node;
  }

  ready(function () {
    var container = document.querySelector('.wdcalculator-container');
    var shell = document.querySelector('.wdcalculator-shell');
    var sidebar = shell ? shell.querySelector('.saved-estimates-sidebar') : null;
    // 임베디드(ERP split)는 자체 저장패널 오버레이를 이미 소유 → 표피 미적용.
    if (!container || !shell || !sidebar ||
        container.classList.contains('wdcalculator-container--embedded')) {
      return;
    }
    var mainScroll = shell.querySelector('.wdcalculator-main-scroll');
    if (!mainScroll) { return; }

    // ============================================================
    // 재부모화 북키핑: 이동한 노드의 (원부모, 원 nextSibling)을 기록해 게이트 이탈 시 원위치
    // 복원한다. 매 dock 마다 원위치에서 다시 기록(복원 후 재도킹 무한 반복 안전).
    // ============================================================
    var relocations = [];
    function moveInto(node, target) {
      if (!node || !target || node.parentNode === target) { return; }
      relocations.push({ node: node, parent: node.parentNode, next: node.nextSibling });
      target.appendChild(node);
    }
    function restoreAll() {
      // 역순 복원: 기록된 nextSibling 이 먼저 제자리로 돌아와 insertBefore 앵커가 유효.
      for (var i = relocations.length - 1; i >= 0; i--) {
        var r = relocations[i];
        if (!r.node || !r.parent) { continue; }
        if (r.next && r.next.parentNode === r.parent) {
          r.parent.insertBefore(r.node, r.next);
        } else {
          r.parent.appendChild(r.node);
        }
      }
      relocations.length = 0;
    }

    function closest(id, sel) {
      var n = document.getElementById(id);
      return n ? n.closest(sel) : null;
    }

    // ============================================================
    // 이동 대상 노드 참조(원위치는 restoreAll 이 관리).
    // ============================================================
    var custGroup = closest('customerName', '.mb-3');
    var settingsLink = container.querySelector('.wdcalculator-main-scroll a[href*="product"]');
    var baseGroup = closest('baseComponentsContainer', '.mb-3');
    var optGroup = closest('additionalOptionsContainer', '.mb-3');
    var couponGroup = closest('globalCouponValue', '.mb-3');
    var shipCostGroup = closest('shippingCost', '.mb-3');
    var shipInclGroup = closest('shippingIncluded', '.mb-3');
    var notesGroup = closest('notesContainer', '.mb-3');
    var breakdownGroup = closest('totalBasePrice', '.mb-3');
    var finalSummary = closest('finalPrice', '.final-summary-card');
    var notesDisplay = document.getElementById('notesDisplaySection');
    var estContainer = document.getElementById('estimatesListContainer');
    var calcBtn = document.getElementById('calculateBtn');
    var addBtn = document.getElementById('addEstimateBtn');
    var finalPriceEl = document.getElementById('finalPrice');
    var custInput = document.getElementById('customerName');

    // ============================================================
    // (1) 슬림 pcbar.
    // ============================================================
    var pcbar = el('div', 'wdc-tablet-pcbar',
      '<span class="wdc-tablet-pcbar__title">WD 계산기</span>' +
      '<div class="wdc-tablet-pcbar__cust" data-slot="cust"></div>' +
      '<div class="wdc-tablet-pcbar__grow"></div>' +
      '<button type="button" class="wdc-tablet-pcbar__search btn btn-outline-secondary" aria-expanded="false">' +
        '<i class="fas fa-search" aria-hidden="true"></i> <span>고객 견적 검색</span>' +
      '</button>' +
      '<div class="wdc-tablet-pcbar__settings" data-slot="settings"></div>');
    mainScroll.insertBefore(pcbar, mainScroll.firstChild);
    var custSlot = pcbar.querySelector('[data-slot="cust"]');
    var settingsSlot = pcbar.querySelector('[data-slot="settings"]');
    var pcbarSearchBtn = pcbar.querySelector('.wdc-tablet-pcbar__search');

    // ============================================================
    // (2) 본문 — 목업 카드 재조립.
    // ============================================================
    var tfBody = el('div', 'wdc-tf-body',
      '<div class="wdc-tf-sub">기본 구성 — 제품 선택 후 W/D/H 입력</div>' +
      '<section class="wdc-tf-card wdc-tf-card--base">' +
        '<h5 class="wdc-tf-card__title">기본 구성</h5>' +
        '<div class="wdc-tf-slot" data-slot="base"></div>' +
      '</section>' +
      '<div class="wdc-tf-row2">' +
        '<section class="wdc-tf-card wdc-tf-card--opt">' +
          '<h5 class="wdc-tf-card__title">추가 옵션</h5>' +
          '<div class="wdc-tf-slot" data-slot="opt"></div>' +
        '</section>' +
        '<section class="wdc-tf-card wdc-tf-card--meta">' +
          '<h5 class="wdc-tf-card__title">쿠폰 · 배송 · 비고</h5>' +
          '<div class="wdc-tf-slot" data-slot="meta"></div>' +
        '</section>' +
      '</div>' +
      '<section class="wdc-tf-summary">' +
        '<div class="wdc-tf-summary__title">견적 결과</div>' +
        '<div class="wdc-tf-slot" data-slot="summary"></div>' +
      '</section>');
    mainScroll.appendChild(tfBody);
    var baseSlot = tfBody.querySelector('[data-slot="base"]');
    var optSlot = tfBody.querySelector('[data-slot="opt"]');
    var metaSlot = tfBody.querySelector('[data-slot="meta"]');
    var summarySlot = tfBody.querySelector('[data-slot="summary"]');

    // ============================================================
    // (3) 우측 "진행 견적" 패널.
    // ============================================================
    var panel = el('aside', 'wdc-tablet-rightpanel',
      '<div class="wdc-trp__head"><h4>진행 견적</h4>' +
        '<span class="wdc-trp__count" data-slot="count"></span></div>' +
      '<div class="wdc-trp__tile"><b>총 견적</b><span data-slot="total">0원</span></div>' +
      '<div class="wdc-trp__body" data-slot="est"></div>' +
      '<div class="wdc-trp__foot">' +
        '<button type="button" class="wdc-trp__new btn btn-light" data-new>' +
          '<i class="fas fa-undo" aria-hidden="true"></i> 새 견적</button>' +
        '<button type="button" class="wdc-trp__save btn btn-primary" data-save>' +
          '<i class="fas fa-save" aria-hidden="true"></i> 전체 저장</button>' +
      '</div>');
    shell.appendChild(panel);
    var estSlot = panel.querySelector('[data-slot="est"]');
    var countEl = panel.querySelector('[data-slot="count"]');
    var totalTileEl = panel.querySelector('[data-slot="total"]');
    var trpNewBtn = panel.querySelector('[data-new]');
    var trpSaveBtn = panel.querySelector('[data-save]');

    // ============================================================
    // (4) 하단 고정 최종견적 바.
    // ============================================================
    var actionBar = el('div', 'wdc-tablet-actionbar',
      '<div class="wdc-tab-ab__price">' +
        '<span class="wdc-tab-ab__label">최종 견적</span>' +
        '<span class="wdc-tab-ab__val" data-slot="final">0원</span>' +
      '</div>' +
      '<div class="wdc-tab-ab__actions" data-slot="actions"></div>');
    document.body.appendChild(actionBar);
    var abValEl = actionBar.querySelector('[data-slot="final"]');
    var abActionsSlot = actionBar.querySelector('[data-slot="actions"]');

    // ============================================================
    // 저장 견적 오버레이(고객 견적 검색): rail + 백드롭. rail 은 코호트 미표시(요소/규칙은
    // 하위호환·계약 문자열 보존). 토글 트리거는 pcbar "고객 견적 검색".
    // ============================================================
    var rail = el('button', 'wdc-saved-rail',
      '<i class="fas fa-history" aria-hidden="true"></i>' +
      '<span class="wdc-saved-rail-label">저장된 견적</span>');
    rail.type = 'button';
    rail.setAttribute('aria-label', '저장된 견적 열기');
    rail.setAttribute('aria-expanded', 'false');
    sidebar.insertBefore(rail, sidebar.firstChild);

    var backdrop = el('div', 'wdc-saved-backdrop');
    backdrop.hidden = true;
    shell.appendChild(backdrop);

    // ============================================================
    // 미러 동기화(관찰만 — 계산엔진 DOM 은 이동/복제 안 함).
    // ============================================================
    function txt(node) { return node ? (node.textContent || '').trim() : ''; }

    function syncBarFinal() {
      var v = txt(finalPriceEl) || '0원';
      if (abValEl.textContent !== v) { abValEl.textContent = v; }
    }

    function syncPanel() {
      // 총 견적: renderEstimatesList 가 estContainer 내부에 #totalAllFinalPrice 를 매번 재생성.
      var totalEl = document.getElementById('totalAllFinalPrice');
      var tv = totalEl ? (txt(totalEl) || '0원') : '0원';
      if (totalTileEl.textContent !== tv) { totalTileEl.textContent = tv; }
      // 진행 견적 카드 수 + 고객명 → head 카운트.
      var cards = estContainer
        ? estContainer.querySelectorAll('.card[data-estimate-id]').length : 0;
      var name = custInput ? (custInput.value || '').trim() : '';
      var label = cards > 0 ? (name ? name + ' · ' + cards + '건' : cards + '건') : '';
      if (countEl.textContent !== label) { countEl.textContent = label; }
      // foot 전체 저장: 엔진이 견적 0건이면 #saveEstimateBtn display:none → 미러 disabled.
      var sb = document.getElementById('saveEstimateBtn');
      trpSaveBtn.disabled = !(sb && sb.style.display !== 'none');
      // foot 새 견적: #resetEstimateBtn 은 편집/로드 시에만 존재.
      trpNewBtn.disabled = !document.getElementById('resetEstimateBtn');
    }

    if (window.MutationObserver) {
      if (finalPriceEl) {
        new MutationObserver(syncBarFinal).observe(finalPriceEl, {
          childList: true, characterData: true, subtree: true,
        });
      }
      if (estContainer) {
        new MutationObserver(syncPanel).observe(estContainer, {
          childList: true, characterData: true, subtree: true,
        });
      }
    }
    if (custInput) {
      custInput.addEventListener('input', syncPanel);
    }

    // 미러 클릭 위임.
    trpNewBtn.addEventListener('click', function () {
      var b = document.getElementById('resetEstimateBtn');
      if (b) { b.click(); }
    });
    trpSaveBtn.addEventListener('click', function () {
      var b = document.getElementById('saveEstimateBtn');
      if (b && b.style.display !== 'none') { b.click(); }
    });

    // ============================================================
    // dock / undock.
    // ============================================================
    function dockFrame() {
      moveInto(custGroup, custSlot);
      moveInto(settingsLink, settingsSlot);
      moveInto(baseGroup, baseSlot);
      moveInto(optGroup, optSlot);
      moveInto(couponGroup, metaSlot);
      moveInto(shipCostGroup, metaSlot);
      moveInto(shipInclGroup, metaSlot);
      moveInto(notesGroup, metaSlot);
      moveInto(breakdownGroup, summarySlot);
      moveInto(finalSummary, summarySlot);
      moveInto(notesDisplay, summarySlot);
      moveInto(estContainer, estSlot);
      moveInto(calcBtn, abActionsSlot);
      moveInto(addBtn, abActionsSlot);
      syncBarFinal();
      syncPanel();
    }
    function undockFrame() {
      restoreAll();
    }

    // ============================================================
    // 저장 견적 오버레이 open/close.
    // ============================================================
    function isOpen() { return shell.classList.contains('wdc-saved-open'); }
    function setOpen(open) {
      shell.classList.toggle('wdc-saved-open', open);
      backdrop.hidden = !open;
      rail.setAttribute('aria-expanded', open ? 'true' : 'false');
      pcbarSearchBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      try { localStorage.setItem(STORAGE_KEY, open ? '1' : '0'); } catch (e) { /* private mode */ }
    }
    rail.addEventListener('click', function () {
      if (shell.classList.contains('wdc-tablet-skin')) { setOpen(!isOpen()); }
    });
    pcbarSearchBtn.addEventListener('click', function () {
      if (shell.classList.contains('wdc-tablet-skin')) { setOpen(!isOpen()); }
    });
    backdrop.addEventListener('click', function () { setOpen(false); });

    // ============================================================
    // enable / disable — 게이트 진입/이탈.
    // ============================================================
    function enableSkin() {
      // 폰 셸(mobile-enhance)이 이미 DOM 을 접수했으면 양보(이중 재부모화 방지).
      if (document.body.classList.contains('wd-builder')) { return; }
      shell.classList.add('wdc-tablet-skin');
      dockFrame();
      setOpen(false);
      actionBar.classList.add('wdc-actionbar-active');
      if (window.requestWdCalculatorLayoutSync) { window.requestWdCalculatorLayoutSync(); }
    }
    function disableSkin() {
      var wasSkinned = shell.classList.contains('wdc-tablet-skin');
      shell.classList.remove('wdc-tablet-skin', 'wdc-saved-open');
      if (wasSkinned) { undockFrame(); }
      backdrop.hidden = true;
      rail.setAttribute('aria-expanded', 'false');
      pcbarSearchBtn.setAttribute('aria-expanded', 'false');
      actionBar.classList.remove('wdc-actionbar-active');
      if (window.requestWdCalculatorLayoutSync) { window.requestWdCalculatorLayoutSync(); }
    }

    var mql = window.matchMedia(GATE);
    function sync() { if (mql.matches) { enableSkin(); } else { disableSkin(); } }
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', sync);
    } else if (typeof mql.addListener === 'function') {
      mql.addListener(sync);
    }
    sync();
  });
})();
