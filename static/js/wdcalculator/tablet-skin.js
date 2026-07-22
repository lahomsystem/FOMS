/**
 * WDCalculator 태블릿 가로 융합 셸(JS) — 2026-07-15 (목업 frame11 구현).
 *
 * 목업 frame11 을 코호트(coarse landscape ≥992, 비임베디드)에서 재현한다. PC 구조·id·계산엔진
 * DOM 은 일절 건드리지 않고, 기존 노드를 **재부모화(DOM move)**·미러링해 프레임을 구성한다
 * (재부모화는 리스너·id·value 를 보존 → WDCalculator "DOM·이벤트 유지" 계약 내):
 *
 *   (1) 슬림 pcbar (main-scroll 상단 sticky): "WD 계산기" 타이틀 + 기존 #customerName 그룹을
 *       **이동**(계산 JS 는 getElementById 로만 참조 → 위치 무관) + "고객 견적 검색"(저장 견적
 *       오버레이 토글). PC 헤더("가구 견적 계산기")는 코호트에서 은닉(CSS).
 *   (2) 우측 320px "진행 견적" 패널(shell 내 absolute, 상시 노출): "총 견적" hl-tile(#totalAllFinalPrice
 *       **미러**) + 진행 중인 견적 카드(#estimatesListContainer 를 **이동** — 수정/이름/삭제는
 *       document 위임 이벤트라 이동해도 보존) + foot(새 견적=resetEstimateBtn·전체 저장=saveEstimateBtn
 *       **미러 클릭**). 견적 결과 breakdown 카드는 유지(엔진이 동적 주입하는 #backToOrderBtn 복귀
 *       내비 보존 — 은닉하면 회귀). 총 견적·최종가는 hl-tile·하단 바로 병행 미러.
 *   (3) 하단 고정 최종견적 바: #finalPrice 값 + 주 액션(견적 계산/추가) 미러(관찰+클릭 위임).
 *
 * 저장 견적 좌측 레일 접힘 로직은 코호트에서 은퇴 — 저장 사이드바는 오프캔버스로 숨고, pcbar
 * "고객 견적 검색"(재탭·백드롭 탭 = 닫기)으로 기존 오버레이(wdc-saved-open)를 재사용해 연다.
 * 상태는 localStorage 에 기억. rail 요소/CSS 는 하위호환·계약 문자열 보존을 위해 남기되 코호트
 * 레이아웃에서는 표시하지 않는다.
 *
 * 게이트: (min-width:992px) and (orientation:landscape) and (pointer:coarse) 且 비임베디드.
 * PC(fine hover)·모바일(≤991.98)·임베디드(erp-wdc-split.css 가 자체 오버레이 소유)는 matchMedia 로
 * 배타 분리 — 게이트를 벗어나면 이동한 노드를 **원위치로 복원**하고 주입 클래스를 전부 제거해 무회귀.
 *
 * 성능 가드 G4: 전역/문서 리스너는 singleton 가드로 1회만 바인딩(fragment 재실행 무해).
 */
(function () {
  'use strict';

  if (window.__WDC_TABLET_SKIN_BOUND) { return; }
  window.__WDC_TABLET_SKIN_BOUND = true;

  var STORAGE_KEY = 'wdcTabletSavedOpen';   // '1' = 펼침, 그 외/부재 = 접힘(기본)
  var GATE = '(min-width: 992px) and (orientation: landscape) and (pointer: coarse)';

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else {
      fn();
    }
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

    // ============================================================
    // 저장 견적 레일(은퇴): 요소/CSS 는 하위호환·계약 문자열 보존을 위해 남기되, 코호트
    // 레이아웃에서는 CSS 로 숨긴다. 오버레이 토글 트리거는 pcbar "고객 견적 검색"이 담당.
    // ============================================================
    var rail = document.createElement('button');
    rail.type = 'button';
    rail.className = 'wdc-saved-rail';
    rail.setAttribute('aria-label', '저장된 견적 열기');
    rail.setAttribute('aria-expanded', 'false');
    rail.innerHTML =
      '<i class="fas fa-history" aria-hidden="true"></i>' +
      '<span class="wdc-saved-rail-label">저장된 견적</span>';
    sidebar.insertBefore(rail, sidebar.firstChild);

    // --- 백드롭 주입(저장 견적 오버레이 펼침 시 바깥 탭 = 닫힘). ---
    var backdrop = document.createElement('div');
    backdrop.className = 'wdc-saved-backdrop';
    backdrop.hidden = true;
    shell.appendChild(backdrop);

    // ============================================================
    // (1) 슬림 pcbar — main-scroll 상단 sticky. 타이틀 + 고객명 슬롯 + 고객 견적 검색.
    // ============================================================
    var pcbar = document.createElement('div');
    pcbar.className = 'wdc-tablet-pcbar';
    pcbar.innerHTML =
      '<span class="wdc-tablet-pcbar__title">WD 계산기</span>' +
      '<div class="wdc-tablet-pcbar__cust" data-wdc-cust-slot></div>' +
      '<div class="wdc-tablet-pcbar__grow"></div>' +
      '<button type="button" class="wdc-tablet-pcbar__search btn btn-outline-secondary" aria-expanded="false">' +
        '<i class="fas fa-search" aria-hidden="true"></i> <span>고객 견적 검색</span>' +
      '</button>';
    if (mainScroll) { mainScroll.insertBefore(pcbar, mainScroll.firstChild); }
    var custSlot = pcbar.querySelector('[data-wdc-cust-slot]');
    var pcbarSearchBtn = pcbar.querySelector('.wdc-tablet-pcbar__search');

    // 고객명 그룹(.mb-3 = label + #customerName) 이동 북키핑(원위치 복원용).
    var custInputEl = document.getElementById('customerName');
    var custGroup = custInputEl ? custInputEl.closest('.mb-3') : null;
    var custGroupHome = custGroup ? custGroup.parentNode : null;
    var custGroupNext = custGroup ? custGroup.nextSibling : null;

    // ============================================================
    // (2) 우측 "진행 견적" 패널 — shell 내 absolute, 상시 노출.
    // ============================================================
    var panel = document.createElement('aside');
    panel.className = 'wdc-tablet-rightpanel';
    panel.setAttribute('aria-label', '진행 견적');
    panel.innerHTML =
      '<div class="wdc-trp__head"><h4>진행 견적</h4></div>' +
      '<div class="wdc-trp__tile"><b>총 견적</b><span data-wdc-trp-total>0원</span></div>' +
      '<div class="wdc-trp__body" data-wdc-progress-slot></div>' +
      '<div class="wdc-trp__foot">' +
        '<button type="button" class="wdc-trp__new btn btn-light" data-wdc-trp-new>' +
          '<i class="fas fa-undo" aria-hidden="true"></i> 새 견적</button>' +
        '<button type="button" class="wdc-trp__save btn btn-primary" data-wdc-trp-save>' +
          '<i class="fas fa-save" aria-hidden="true"></i> 전체 저장</button>' +
      '</div>';
    shell.appendChild(panel);
    var progressSlot = panel.querySelector('[data-wdc-progress-slot]');
    var trpTotalEl = panel.querySelector('[data-wdc-trp-total]');
    var trpNewBtn = panel.querySelector('[data-wdc-trp-new]');
    var trpSaveBtn = panel.querySelector('[data-wdc-trp-save]');

    // 진행 중인 견적 카드(#estimatesListContainer 의 부모 .card) 이동 북키핑.
    var estContainer = document.getElementById('estimatesListContainer');
    var progressCard = estContainer ? estContainer.closest('.card') : null;
    var progressHome = progressCard ? progressCard.parentNode : null;
    var progressNext = progressCard ? progressCard.nextSibling : null;

    // ============================================================
    // (3) 하단 고정 최종견적 바. #finalPrice 값 + 주 액션(견적 계산/추가) 미러(관찰+클릭 위임).
    // 계산엔진 노드를 이동/복제하지 않고 값·액션만 미러 — enableSkin/disableSkin 이
    // .wdc-actionbar-active 로 노출/은닉(폰 wd-fab 와 MQ 배타).
    // ============================================================
    var actionBar = document.createElement('div');
    actionBar.className = 'wdc-tablet-actionbar';
    actionBar.innerHTML =
      '<div class="wdc-tab-ab__price">' +
        '<span class="wdc-tab-ab__label">최종 견적</span>' +
        '<span class="wdc-tab-ab__val" data-wdc-ab-final>0원</span>' +
      '</div>' +
      '<button type="button" class="wdc-tab-ab__action btn btn-success">' +
        '<i class="fas fa-calculator" aria-hidden="true"></i> ' +
        '<span data-wdc-ab-action-label>견적 계산</span>' +
      '</button>';
    document.body.appendChild(actionBar);

    var abValEl = actionBar.querySelector('[data-wdc-ab-final]');
    var abActionBtn = actionBar.querySelector('.wdc-tab-ab__action');
    var abActionLabel = actionBar.querySelector('[data-wdc-ab-action-label]');
    var finalPriceEl = document.getElementById('finalPrice');
    var calcBtn = document.getElementById('calculateBtn');
    var addBtn = document.getElementById('addEstimateBtn');

    // 값 미러: #finalPrice(현재 견적 최종가) 텍스트를 바에 그대로 반영.
    function syncBarFinal() {
      if (!finalPriceEl || !abValEl) { return; }
      var v = (finalPriceEl.textContent || '0원').trim();
      if (abValEl.textContent !== v) { abValEl.textContent = v; }
    }

    // host 가 인라인 style.display 로 토글하는 계약을 그대로 읽어 노출 여부 판정.
    function isHostBtnShown(btn) {
      return !!(btn && btn.style.display !== 'none');
    }
    // 주 액션: addEstimateBtn 노출 시 '견적 추가/수정 적용'이 다음 액션 → 우선, 아니면 '견적 계산'.
    function currentPrimaryBtn() {
      return isHostBtnShown(addBtn) ? addBtn : calcBtn;
    }
    function syncBarAction() {
      if (!abActionLabel) { return; }
      var target = currentPrimaryBtn();
      var txt = target ? (target.textContent || '').trim() : '';
      abActionLabel.textContent = txt || '견적 계산';
    }

    abActionBtn.addEventListener('click', function () {
      var target = currentPrimaryBtn();
      if (target) { target.click(); }
    });

    // ============================================================
    // 우측 패널 "총 견적" hl-tile 미러(#totalAllFinalPrice) + foot 버튼 활성 상태 동기화.
    // #totalAllFinalPrice 는 renderEstimatesList 가 매번 재생성 → 안정 노드(estContainer)를
    // 관찰해 재렌더마다 값을 읽어 반영(재계산 없음, 순수 미러).
    // ============================================================
    function syncProgressPanel() {
      var el = document.getElementById('totalAllFinalPrice');
      var v = el ? (el.textContent || '0원').trim() : '0원';
      if (trpTotalEl && trpTotalEl.textContent !== v) { trpTotalEl.textContent = v; }
      // 전체 저장: 엔진이 견적 0건이면 saveEstimateBtn 을 display:none 으로 감춤 → 그 의도를 반영.
      if (trpSaveBtn) {
        var sb = document.getElementById('saveEstimateBtn');
        trpSaveBtn.disabled = !(sb && sb.style.display !== 'none');
      }
      // 새 견적: resetEstimateBtn 은 견적이 있을 때만 존재(엔진이 동적 생성/제거).
      if (trpNewBtn) {
        trpNewBtn.disabled = !document.getElementById('resetEstimateBtn');
      }
    }

    trpNewBtn.addEventListener('click', function () {
      var b = document.getElementById('resetEstimateBtn');
      if (b) { b.click(); }
    });
    trpSaveBtn.addEventListener('click', function () {
      var b = document.getElementById('saveEstimateBtn');
      if (b && b.style.display !== 'none') { b.click(); }
    });

    if (window.MutationObserver) {
      if (finalPriceEl) {
        new MutationObserver(syncBarFinal).observe(finalPriceEl, {
          childList: true, characterData: true, subtree: true,
        });
      }
      // addEstimateBtn: 노출 토글(style) + 라벨 변경(견적 추가↔수정 적용) 동시 감지.
      if (addBtn) {
        new MutationObserver(syncBarAction).observe(addBtn, {
          attributes: true, attributeFilter: ['style'],
          childList: true, characterData: true, subtree: true,
        });
      }
      if (calcBtn) {
        new MutationObserver(syncBarAction).observe(calcBtn, {
          attributes: true, attributeFilter: ['style'],
        });
      }
      // 진행 중인 견적 리스트 재렌더 → hl-tile 총 견적 + foot 활성 상태 미러.
      if (estContainer) {
        new MutationObserver(syncProgressPanel).observe(estContainer, {
          childList: true, characterData: true, subtree: true,
        });
      }
    }

    function showActionBar() {
      actionBar.classList.add('wdc-actionbar-active');
      syncBarFinal();
      syncBarAction();
    }
    function hideActionBar() {
      actionBar.classList.remove('wdc-actionbar-active');
    }

    // ============================================================
    // dock / undock — 게이트 진입 시 노드를 프레임으로 이동, 이탈 시 원위치 복원.
    // ============================================================
    function dockFrame() {
      if (custGroup && custSlot && custGroup.parentNode !== custSlot) {
        custSlot.appendChild(custGroup);
      }
      if (progressCard && progressSlot && progressCard.parentNode !== progressSlot) {
        progressSlot.appendChild(progressCard);
      }
      syncProgressPanel();
    }
    function undockFrame() {
      if (custGroup && custGroupHome && custGroup.parentNode !== custGroupHome) {
        if (custGroupNext && custGroupNext.parentNode === custGroupHome) {
          custGroupHome.insertBefore(custGroup, custGroupNext);
        } else {
          custGroupHome.appendChild(custGroup);
        }
      }
      if (progressCard && progressHome && progressCard.parentNode !== progressHome) {
        if (progressNext && progressNext.parentNode === progressHome) {
          progressHome.insertBefore(progressCard, progressNext);
        } else {
          progressHome.appendChild(progressCard);
        }
      }
    }

    // ============================================================
    // 저장 견적 오버레이 open/close (pcbar "고객 견적 검색"·rail·백드롭 공용).
    // ============================================================
    function isOpen() { return shell.classList.contains('wdc-saved-open'); }

    function setOpen(open) {
      shell.classList.toggle('wdc-saved-open', open);
      backdrop.hidden = !open;
      rail.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (pcbarSearchBtn) { pcbarSearchBtn.setAttribute('aria-expanded', open ? 'true' : 'false'); }
      try { localStorage.setItem(STORAGE_KEY, open ? '1' : '0'); } catch (e) { /* private mode */ }
    }

    function enableSkin() {
      shell.classList.add('wdc-tablet-skin');
      dockFrame();              // 고객명 그룹 → pcbar, 진행 중인 견적 카드 → 우측 패널
      setOpen(false);           // frame11: 저장 사이드바 기본 숨김, "고객 견적 검색"으로 오픈
      showActionBar();          // 하단 고정 최종견적 바 노출 + 값/액션 재동기화
      if (window.requestWdCalculatorLayoutSync) { window.requestWdCalculatorLayoutSync(); }
    }

    function disableSkin() {
      // 게이트 이탈(PC/모바일/세로) — 이동 노드 원위치 복원 + 주입 클래스 전부 제거.
      shell.classList.remove('wdc-tablet-skin', 'wdc-saved-open');
      undockFrame();
      backdrop.hidden = true;
      rail.setAttribute('aria-expanded', 'false');
      if (pcbarSearchBtn) { pcbarSearchBtn.setAttribute('aria-expanded', 'false'); }
      hideActionBar();
      if (window.requestWdCalculatorLayoutSync) { window.requestWdCalculatorLayoutSync(); }
    }

    rail.addEventListener('click', function () {
      if (!shell.classList.contains('wdc-tablet-skin')) { return; }
      setOpen(!isOpen());
    });
    if (pcbarSearchBtn) {
      pcbarSearchBtn.addEventListener('click', function () {
        if (!shell.classList.contains('wdc-tablet-skin')) { return; }
        setOpen(!isOpen());
      });
    }
    backdrop.addEventListener('click', function () { setOpen(false); });

    var mql = window.matchMedia(GATE);
    function sync() { if (mql.matches) { enableSkin(); } else { disableSkin(); } }
    // 방향 전환/리사이즈 시 게이트 진입·이탈 반영(addEventListener 우선, 레거시 폴백).
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', sync);
    } else if (typeof mql.addListener === 'function') {
      mql.addListener(sync);
    }
    sync();
  });
})();
