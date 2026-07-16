/**
 * WDCalculator 태블릿 가로 v2 표면(JS) — 목업 tablet-wdcalculator-v2.html Frame 1~3 그라운드업.
 *
 * 배경: 구판(표형 D/H 그리드)은 D/H 열·48px saved-rail·센티넬 추가금 직렬화를 썼으나,
 * v2 스펙은 (1) D/H 열 전면 삭제(W 기준 가격), (2) 단가 셀 금액만, (3) CUSTOM(구 직접) 행 제품명
 * 전폭·방식/단가 서브행 분리, (4) 행별 직접입력(구 추가금) 이름만 표기, (5) 비고 정식 섹션 승격,
 * (6) [견적 계산] 버튼 삭제(전 입력 경로 자동 계산)를 요구한다. 본판은 신규 v2 DOM(워크시트 +
 * 라이브 진행 견적 패널 + 호출형 저장 오버레이)을 구성하고, 은닉 엔진 위젯에 양방향 미러한다.
 *
 * 엔진 READ-ONLY 원칙: 계산·저장 엔진(primary-form/pricing-core/estimate-lifecycle/composition)은
 * 일절 수정하지 않는다. v2 셀은 **신규 DOM**이고 엔진 노드(#baseComponentsContainer 등)는 PC
 * 스캐폴딩에 은닉 유지(엔진이 querySelector·delegated listener·save read 로 계속 소유)한다.
 *
 *   | v2 셀              | 미러 대상(은닉 엔진 위젯)                 | 방향/트리거                              |
 *   |--------------------|------------------------------------------|------------------------------------------|
 *   | 모드 드롭다운(제품선택/커스텀/직접) | .base-mode-btn[data-mode]     | 시트 pick → click 위임 + 재빌드 |
 *   | 제품(선택)          | .base-product-select                     | 시트 pick → value + change               |
 *   | 제품명(CUSTOM)      | .base-manual-name                        | 입력 → value + input                     |
 *   | 방식(CUSTOM 서브)   | .base-manual-pricing-type                | 시트 pick(30cm/1m) → value + change·재빌드|
 *   | 단가입력(CUSTOM 서브)| .base-manual-price30 / -price1m         | 입력 → value + input                     |
 *   | W                  | .base-width-input                        | 입력 → value + input                     |
 *   | 단가(read-only)     | wdcComputeCurrentEstimateMath([comp])    | 관찰(순수 계산 재호출)                   |
 *   | 직접입력 서브행     | .base-additional-fee-name/-amount        | 입력 → value + input / ✕=remove          |
 *   | ＋직접입력          | .base-add-fee-btn                        | 클릭 위임 + 재빌드                        |
 *   | 옵션 배지/셀        | [data-toggle-direct-input]/-option-select| 배지=토글 / 시트 pick / 직접명 입력      |
 *   | 옵션 금액           | [data-option-price]                      | 입력 ↔ value 미러                        |
 *   | 비고 배지/셀        | .toggle-note-type / .note-select/.note-input| 배지=토글 / 시트 pick / 직접입력      |
 *   | 총견적/브레이크다운 | #finalPrice/#totalBasePrice/#totalAdditionalPrice | MutationObserver 미러          |
 *   | 진행/전체합계       | #estimatesListContainer/#totalAllFinalPrice | 노드 이동 + 관찰                      |
 *   | 진행 추가/저장/새   | #addEstimateBtn/#saveEstimateBtn/#resetEstimateBtn | 클릭 시 live lookup 미러        |
 *
 * 노드 이동(재부모화, 게이트 이탈 시 역순 복원): #customerName·제품설정 링크·쿠폰·배송·비고 조정 아님
 * — estimatesListContainer·단가토글·쿠폰/배송 입력·고객명·설정 링크·저장 사이드바 카드만 이동한다.
 * 기본 구성/옵션/비고는 미러(이동하지 않음)이며 은닉 엔진 컨테이너의 childList 변화를 옵저버로
 * 감지해 재빌드하되, 입력 타이핑(값 변경) 중에는 재빌드하지 않아 클로버를 막는다.
 *
 * 게이트: (min-width:992px) and (orientation:landscape) and (pointer:coarse) 且 비임베디드.
 * 게이트 이탈(회전/리사이즈)→ 이동 노드 원위치 복원 + 미러 그리드 파기 + 옵저버 해제 + body 발현
 * 클래스 제거(PC·폰·임베디드·태블릿 세로 무회귀). 폰 셸(mobile-enhance.js ≤991.98, body.wd-builder)이
 * DOM 을 접수했으면 스킨 양보. body.wdc-tablet-v2 가 CSS 발현 키(게이트 + 이 클래스 이중 조건).
 *
 * 성능 가드 G4: 전역/문서 리스너는 singleton 가드로 1회만 바인딩(fragment 재실행 무해).
 */
(function () {
  'use strict';

  if (window.__WDC_TABLET_SKIN_BOUND) { return; }
  window.__WDC_TABLET_SKIN_BOUND = true;

  var GATE = '(min-width: 992px) and (orientation: landscape) and (pointer: coarse)';
  var BODY_CLASS = 'wdc-tablet-v2';
  var PENDING_CLASS = 'wdc-tablet-pending';   // 인라인 부트(calculator.html)가 파싱 시점에 부여

  // FOUC 선제 은닉 해제 — 스킨 발현/미발현 판정 즉시 호출(fail-open 3s 애니메이션보다 빠른 정상 경로).
  function clearPending() {
    document.documentElement.classList.remove(PENDING_CLASS);
  }

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

  function fireInput(node) {
    if (node) { node.dispatchEvent(new Event('input', { bubbles: true })); }
  }
  function fireChange(node) {
    if (node) { node.dispatchEvent(new Event('change', { bubbles: true })); }
  }
  function txt(node) { return node ? (node.textContent || '').trim() : ''; }

  // W textarea auto-grow(단일행→복합식 다행 확장). height=auto→scrollHeight; CSS min-height 가 하한.
  function autoGrow(ta) {
    if (!ta) { return; }
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  }

  function escapeText(s) {
    var d = document.createElement('div');
    d.textContent = String(s == null ? '' : s);
    return d.innerHTML;
  }

  function fmtNum(n) {
    var v = Number(n) || 0;
    if (typeof window.formatNumber === 'function') { return window.formatNumber(v); }
    return v.toLocaleString('ko-KR');
  }

  function numFrom(node) {
    if (!node) { return 0; }
    return Number(String(node.value).replace(/[^\d.-]/g, '')) || 0;
  }

  // ============================================================
  // 엔진 READ-ONLY 헬퍼(순수 조회/계산 — DOM 이동·복제·수정 없음).
  // ============================================================
  function getProducts() {
    var st = window.WdCalculatorProductsState;
    return (st && typeof st.getProducts === 'function' && st.getProducts()) || [];
  }
  function readBaseComps() {
    var ui = window.WdCalculatorBaseComponentsUI;
    return (ui && typeof ui.readBaseComponentsFromUI === 'function'
      && ui.readBaseComponentsFromUI()) || [];
  }
  function computeCompPrice(comp) {
    var fn = window.wdcComputeCurrentEstimateMath;
    if (typeof fn !== 'function' || !comp) { return 0; }
    try {
      var math = fn([comp], getProducts(), []);
      return (math && Number(math.basePriceCalculate)) || 0;
    } catch (e) {
      return 0;
    }
  }

  ready(function () {
    var container = document.querySelector('.wdcalculator-container');
    var shell = document.querySelector('.wdcalculator-shell');
    var sidebar = shell ? shell.querySelector('.saved-estimates-sidebar') : null;
    // 임베디드(erp-wdc-split)는 자체 저장패널 오버레이를 이미 소유 → 표면 미적용.
    if (!container || !shell || !sidebar ||
        container.classList.contains('wdcalculator-container--embedded')) {
      clearPending();   // 표면 미적용 경로 — 선제 은닉 즉시 해제
      return;
    }
    var mainScroll = shell.querySelector('.wdcalculator-main-scroll');
    if (!mainScroll) { clearPending(); return; }
    var mainColumn = mainScroll.closest('.wdcalculator-main-column') || shell;

    // ============================================================
    // 재부모화 북키핑(역순 복원). nextSibling 앵커로 원위치 보존.
    // ============================================================
    var relocations = [];
    function moveInto(node, target) {
      if (!node || !target || node.parentNode === target) { return; }
      relocations.push({ node: node, parent: node.parentNode, next: node.nextSibling });
      target.appendChild(node);
    }
    function restoreAll() {
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
    function closestOf(id, sel) {
      var n = document.getElementById(id);
      return n ? n.closest(sel) : null;
    }

    // 이동 대상(재부모화).
    var custGroup = closestOf('customerName', '.mb-3');
    var settingsLink = container.querySelector('.wdcalculator-main-scroll a[href*="product"]');
    var couponGroup = closestOf('globalCouponValue', '.mb-3');
    var shipCostGroup = closestOf('shippingCost', '.mb-3');
    var shipInclGroup = closestOf('shippingIncluded', '.mb-3');
    var estContainer = document.getElementById('estimatesListContainer');
    var unitToggleWrap = closestOf('wdUnitPriceMetaToggle', '.wd-unit-price-toggle-wrap');
    var savedCard = sidebar.querySelector('.saved-estimates-card');
    var custInput = document.getElementById('customerName');

    // 미러 소스(은닉 엔진 — 이동하지 않음).
    var baseContainer = document.getElementById('baseComponentsContainer');
    var optContainer = document.getElementById('additionalOptionsContainer');
    var notesContainer = document.getElementById('notesContainer');
    var addBaseBtn = document.getElementById('addBaseComponentBtn');
    var addOptBtn = document.getElementById('addOptionBtn');
    var addNoteBtn = document.getElementById('btnAddNote');
    var finalPriceEl = document.getElementById('finalPrice');
    var totalBaseEl = document.getElementById('totalBasePrice');
    var totalAddEl = document.getElementById('totalAdditionalPrice');
    var couponInput = document.getElementById('globalCouponValue');
    var shipCostInput = document.getElementById('shippingCost');
    var shipInclInput = document.getElementById('shippingIncluded');

    // ============================================================
    // (1) 탑바.
    // ============================================================
    var topbar = el('div', 'wdc2-topbar',
      '<span class="wdc2-topbar__title">WD 계산기</span>' +
      '<div class="wdc2-topbar__cust" data-slot="cust"></div>' +
      '<div class="wdc2-topbar__grow"></div>' +
      '<button type="button" class="wdc2-topbar__search" aria-expanded="false">' +
        '<i class="fas fa-search" aria-hidden="true"></i> <span>견적 검색</span>' +
      '</button>' +
      '<div class="wdc2-topbar__settings" data-slot="settings"></div>');
    mainScroll.insertBefore(topbar, mainScroll.firstChild);
    var custSlot = topbar.querySelector('[data-slot="cust"]');
    var settingsSlot = topbar.querySelector('[data-slot="settings"]');
    var searchBtn = topbar.querySelector('.wdc2-topbar__search');

    // ============================================================
    // (2) 시트(워크시트 본문): 구성·옵션·비고 섹션 + 조정 스트립.
    // ============================================================
    var sheet = el('div', 'wdc2-sheet',
      '<section class="wdc2-sec wdc2-sec--base">' +
        '<div class="wdc2-sec__hd"><span class="wdc2-sec__t">기본 구성</span>' +
          '<span class="wdc2-sec__c" data-slot="basecount"></span></div>' +
        '<div class="wdc2-colhead wdc2-colhead--base">' +
          '<span>모드</span><span>제품 구성</span><span class="r">W (mm)</span>' +
          '<span class="r">단가</span><span></span></div>' +
        '<div class="wdc2-basegrid" data-slot="basegrid"></div>' +
        '<div class="wdc2-addrow">' +
          '<button type="button" class="wdc2-addrow__a" data-add="base">＋ 구성 추가</button>' +
          '<button type="button" class="wdc2-addrow__a wdc2-addrow__a--mine" data-add="mine">✎ CUSTOM 추가</button>' +
        '</div>' +
      '</section>' +
      '<section class="wdc2-sec wdc2-sec--opt">' +
        '<div class="wdc2-sec__hd"><span class="wdc2-sec__t">추가 옵션</span>' +
          '<span class="wdc2-sec__c" data-slot="optcount"></span></div>' +
        '<div class="wdc2-optgrid" data-slot="optgrid"></div>' +
        '<div class="wdc2-addrow">' +
          '<button type="button" class="wdc2-addrow__a" data-add="opt">＋ 옵션 추가</button>' +
        '</div>' +
      '</section>' +
      '<section class="wdc2-sec wdc2-sec--note">' +
        '<div class="wdc2-sec__hd"><span class="wdc2-sec__t">비고</span>' +
          '<span class="wdc2-sec__c" data-slot="notecount"></span></div>' +
        '<div class="wdc2-notegrid" data-slot="notegrid"></div>' +
        '<div class="wdc2-addrow">' +
          '<button type="button" class="wdc2-addrow__a" data-add="note">＋ 비고 추가</button>' +
        '</div>' +
      '</section>' +
      '<div class="wdc2-strip">' +
        '<div class="wdc2-pill">' +
          '<span class="wdc2-pill__l">할인</span>' +
          '<span class="wdc2-pill__sign">−</span>' +
          '<div class="wdc2-pill__field" data-slot="disc"></div>' +
        '</div>' +
        '<div class="wdc2-pill">' +
          '<span class="wdc2-pill__l">배송비</span>' +
          '<span class="wdc2-pill__sign wdc2-pill__sign--plus">＋</span>' +
          '<div class="wdc2-pill__field" data-slot="shipcost"></div>' +
          '<div class="wdc2-pill__chk" data-slot="shipincl"></div>' +
        '</div>' +
      '</div>');
    mainScroll.appendChild(sheet);
    var baseGridEl = sheet.querySelector('[data-slot="basegrid"]');
    var optGridEl = sheet.querySelector('[data-slot="optgrid"]');
    var noteGridEl = sheet.querySelector('[data-slot="notegrid"]');
    var baseCountEl = sheet.querySelector('[data-slot="basecount"]');
    var optCountEl = sheet.querySelector('[data-slot="optcount"]');
    var noteCountEl = sheet.querySelector('[data-slot="notecount"]');
    var discSlot = sheet.querySelector('[data-slot="disc"]');
    var shipCostSlot = sheet.querySelector('[data-slot="shipcost"]');
    var shipInclSlot = sheet.querySelector('[data-slot="shipincl"]');

    // ============================================================
    // (3) 하단 액션바(고정): 총견적 미러 + [진행 견적에 추가].
    // ============================================================
    var abar = el('div', 'wdc2-abar',
      '<div class="wdc2-abar__total">' +
        '<span class="wdc2-abar__label">최종 견적</span>' +
        '<span class="wdc2-abar__row"><span class="wdc2-abar__val" data-slot="final">0원</span>' +
          '<span class="wdc2-abar__live">실시간 · 할인/배송 반영</span></span>' +
      '</div>' +
      '<div class="wdc2-abar__grow"></div>' +
      '<button type="button" class="wdc2-abar__add" data-add-estimate>진행 견적에 추가 <span aria-hidden="true">→</span></button>');
    // in-flow 도킹(main-column flex 하단): fixed 좌표가 전역 레일(72px)과 겹치던 결함의 구조적 제거.
    mainColumn.appendChild(abar);
    var abarValEl = abar.querySelector('[data-slot="final"]');
    var abarAddBtn = abar.querySelector('[data-add-estimate]');

    // ============================================================
    // (4) 우측 진행 견적 패널(shell 내 absolute, 상시).
    // ============================================================
    var panel = el('aside', 'wdc2-panel',
      '<div class="wdc2-panel__cur">' +
        '<div class="wdc2-panel__curhd"><span class="wdc2-dot"></span><b>현재 견적</b></div>' +
        '<div class="wdc2-bl"><span>기본 구성 <span data-slot="curbasecnt"></span></span>' +
          '<b data-slot="baseval">0원</b></div>' +
        '<div class="wdc2-bl"><span>추가 옵션 <span data-slot="curoptcnt"></span></span>' +
          '<b data-slot="optval">+0원</b></div>' +
        '<div class="wdc2-bl wdc2-bl--minus"><span>할인</span><b data-slot="discval">−0원</b></div>' +
        '<div class="wdc2-bl"><span>배송비 <span class="wdc2-mut" data-slot="shipnote"></span></span>' +
          '<b data-slot="shipval">+0원</b></div>' +
        '<div class="wdc2-bl wdc2-bl--total"><span>최종 견적</span>' +
          '<b data-slot="curtotal">0원</b></div>' +
      '</div>' +
      '<div class="wdc2-panel__list">' +
        '<div class="wdc2-panel__lh"><b>진행 견적</b>' +
          '<span class="wdc2-panel__cnt" data-slot="listcount"></span>' +
          '<span class="wdc2-panel__grow"></span>' +
          '<span class="wdc2-panel__toggle" data-slot="unittoggle"></span></div>' +
        '<div class="wdc2-panel__body" data-slot="est"></div>' +
      '</div>' +
      '<div class="wdc2-panel__foot">' +
        '<div class="wdc2-panel__sum"><span class="wdc2-panel__suml">전체 합계 ' +
          '<span data-slot="footcount"></span></span>' +
          '<span class="wdc2-panel__sumv" data-slot="alltotal">0원</span></div>' +
        '<div class="wdc2-panel__btns">' +
          '<button type="button" class="wdc2-panel__new" data-reset>새 견적</button>' +
          '<button type="button" class="wdc2-panel__save" data-save>전체 저장</button>' +
        '</div>' +
      '</div>');
    shell.appendChild(panel);
    var estSlot = panel.querySelector('[data-slot="est"]');
    // v2 컴팩트 진행 견적 카드 컨테이너(은닉 estimatesListContainer 를 스크레이프해 렌더).
    var qcardsEl = el('div', 'wdc2-qcards');
    if (estSlot) { estSlot.appendChild(qcardsEl); }
    var unitToggleSlot = panel.querySelector('[data-slot="unittoggle"]');
    var baseValEl = panel.querySelector('[data-slot="baseval"]');
    var optValEl = panel.querySelector('[data-slot="optval"]');
    var discValEl = panel.querySelector('[data-slot="discval"]');
    var shipValEl = panel.querySelector('[data-slot="shipval"]');
    var shipNoteEl = panel.querySelector('[data-slot="shipnote"]');
    var curTotalEl = panel.querySelector('[data-slot="curtotal"]');
    var curBaseCntEl = panel.querySelector('[data-slot="curbasecnt"]');
    var curOptCntEl = panel.querySelector('[data-slot="curoptcnt"]');
    var listCountEl = panel.querySelector('[data-slot="listcount"]');
    var footCountEl = panel.querySelector('[data-slot="footcount"]');
    var allTotalEl = panel.querySelector('[data-slot="alltotal"]');
    var panelNewBtn = panel.querySelector('[data-reset]');
    var panelSaveBtn = panel.querySelector('[data-save]');

    // ============================================================
    // (5) 저장 견적 오버레이(견적 검색): 사이드바 카드 이동 + 슬라이드.
    // ============================================================
    var overlay = el('aside', 'wdc2-saved-overlay',
      '<div class="wdc2-saved-overlay__hd"><b>저장된 견적</b>' +
        '<button type="button" class="wdc2-saved-overlay__close" aria-label="닫기">✕</button></div>' +
      '<div class="wdc2-saved-overlay__body" data-slot="saved"></div>');
    shell.appendChild(overlay);
    var savedSlot = overlay.querySelector('[data-slot="saved"]');
    var backdrop = el('div', 'wdc2-saved-backdrop');
    backdrop.hidden = true;
    shell.appendChild(backdrop);

    // ============================================================
    // (6) 공용 바텀시트 피커(제품·옵션·비고·방식). 엔진 select 옵션 복제.
    // ============================================================
    var picker = el('div', 'wdc2-sheetpicker',
      '<div class="wdc2-sheetpicker__grip"></div>' +
      '<div class="wdc2-sheetpicker__hd"><span class="wdc2-sheetpicker__title"></span>' +
        '<button type="button" class="wdc2-sheetpicker__close" aria-label="닫기">✕</button></div>' +
      '<div class="wdc2-sheetpicker__body" role="listbox"></div>');
    picker.hidden = true;
    var pickerBackdrop = el('div', 'wdc2-sheetpicker-backdrop');
    pickerBackdrop.hidden = true;
    document.body.appendChild(pickerBackdrop);
    document.body.appendChild(picker);
    var pickerTitle = picker.querySelector('.wdc2-sheetpicker__title');
    var pickerBody = picker.querySelector('.wdc2-sheetpicker__body');

    function closePicker() {
      picker.hidden = true;
      pickerBackdrop.hidden = true;
      picker.classList.remove('wdc2-sheetpicker--product');
      document.body.classList.remove('wdc2-sheetpicker-open');
    }
    function openSheet(title, options, curValue, onPick) {
      pickerTitle.textContent = title || '선택';
      pickerBody.innerHTML = '';
      options.forEach(function (o) {
        var btn = el('button', 'wdc2-sheetpicker__opt');
        btn.type = 'button';
        btn.setAttribute('role', 'option');
        if (o.meta) {
          btn.innerHTML = '<span class="wdc2-sheetpicker__optnm">' + escapeText(o.label) +
            '</span><span class="wdc2-sheetpicker__optmeta">' + escapeText(o.meta) + '</span>';
        } else {
          btn.textContent = o.label;
        }
        if (String(o.value) === String(curValue)) {
          btn.classList.add('is-selected');
          btn.setAttribute('aria-selected', 'true');
        }
        btn.addEventListener('click', function () {
          closePicker();
          onPick(o.value, o.label);
        });
        pickerBody.appendChild(btn);
      });
      picker.hidden = false;
      pickerBackdrop.hidden = false;
      document.body.classList.add('wdc2-sheetpicker-open');
    }
    pickerBackdrop.addEventListener('click', closePicker);
    picker.querySelector('.wdc2-sheetpicker__close').addEventListener('click', closePicker);

    function optionsFromSelect(selectEl) {
      var out = [];
      if (!selectEl) { return out; }
      Array.prototype.forEach.call(selectEl.options, function (o) {
        if (o.value === '') { return; }   // placeholder 제외
        out.push({ value: o.value, label: (o.textContent || '').trim() });
      });
      return out;
    }
    function makeTie() { return el('span', 'wdc2-tie'); }

    // 제품 시트 전용(목업 Frame 2): option value(제품 id) ↔ getProducts() 매칭으로
    // 30cm(또는 1m) 단가 서브라벨을 병기한다. 옵션/비고/방식 시트에는 미적용.
    function productSheetOptions(sel) {
      var opts = optionsFromSelect(sel);
      var products = getProducts();
      var byId = {};
      for (var i = 0; i < products.length; i++) {
        var p = products[i];
        if (p && p.id != null) { byId[String(p.id)] = p; }
      }
      opts.forEach(function (o) {
        var prod = byId[String(o.value)];
        if (!prod) { return; }
        o.meta = prod.pricing_type === '1m'
          ? fmtNum(prod.price_1m || 0) + ' / 1m'
          : fmtNum(prod.price_30cm || 0) + ' / 30cm';
      });
      return opts;
    }

    // 엔진 행에 직접입력 fee 1건(이름+금액)을 추가하고 v2 그리드 재빌드.
    // 호출측이 .base-mode-btn[data-mode=direct] click 으로 행을 명시 direct 모드로 전환(T4 일원화).
    function addDirectInputFee(engineRow, name, amount) {
      var b = engineRow.querySelector('.base-add-fee-btn');
      if (b) { b.click(); }
      window.setTimeout(function () {
        var items = engineRow.querySelectorAll('.base-additional-fee-item');
        var last = items.length ? items[items.length - 1] : null;
        if (last) {
          var nm = last.querySelector('.base-additional-fee-name');
          var amt = last.querySelector('.base-additional-fee-amount');
          if (nm) { nm.value = name; fireInput(nm); }
          if (amt) { amt.value = amount; fireInput(amt); }
        }
        rebuildBaseGrid();
      }, 0);
    }

    // 제품 선택 시트(3-세그): [선택(카탈로그)] [CUSTOM] [직접입력].
    //  - 선택: 카탈로그 그리드(단가 병기) pick → sel.value + change.
    //  - CUSTOM: 행을 manual 모드로 전환 → 시트 닫고 행 제품명 입력 포커스.
    //  - 직접입력: [항목명][금액][추가] → fee 추가 + 행을 direct 모드로 명시 전환(T4 일원화).
    function openProductSheet(engineRow, idx, prodBtn) {
      var sel = engineRow.querySelector('.base-product-select');
      if (!sel) { return; }
      pickerTitle.textContent = '제품 선택';
      pickerBody.innerHTML = '';
      picker.classList.add('wdc2-sheetpicker--product');

      var tabs = el('div', 'wdc2-psheet__tabs');
      var tabCatalog = el('button', 'wdc2-psheet__tab is-active');
      tabCatalog.type = 'button';
      tabCatalog.textContent = '선택';
      var tabCustom = el('button', 'wdc2-psheet__tab');
      tabCustom.type = 'button';
      tabCustom.textContent = 'CUSTOM';
      var tabDirect = el('button', 'wdc2-psheet__tab');
      tabDirect.type = 'button';
      tabDirect.textContent = '직접입력';
      tabs.appendChild(tabCatalog);
      tabs.appendChild(tabCustom);
      tabs.appendChild(tabDirect);
      pickerBody.appendChild(tabs);

      var catalog = el('div', 'wdc2-psheet__grid');
      productSheetOptions(sel).forEach(function (o) {
        var btn = el('button', 'wdc2-sheetpicker__opt');
        btn.type = 'button';
        btn.setAttribute('role', 'option');
        if (o.meta) {
          btn.innerHTML = '<span class="wdc2-sheetpicker__optnm">' + escapeText(o.label) +
            '</span><span class="wdc2-sheetpicker__optmeta">' + escapeText(o.meta) + '</span>';
        } else {
          btn.textContent = o.label;
        }
        if (String(o.value) === String(sel.value)) {
          btn.classList.add('is-selected');
          btn.setAttribute('aria-selected', 'true');
        }
        btn.addEventListener('click', function () {
          sel.value = o.value;
          fireChange(sel);
          var lbl = prodBtn && prodBtn.querySelector('.wdc2-prodbtn__nm');
          if (lbl) { lbl.textContent = baseProductLabel(engineRow); }
          closePicker();
          refreshBasePrices();
        });
        catalog.appendChild(btn);
      });
      pickerBody.appendChild(catalog);

      var direct = el('div', 'wdc2-psheet__direct');
      direct.hidden = true;
      var dName = el('input', 'wdc2-psheet__in');
      dName.type = 'text';
      dName.placeholder = '항목명';
      var dAmt = el('input', 'wdc2-psheet__in');
      dAmt.type = 'text';
      dAmt.setAttribute('inputmode', 'numeric');
      dAmt.placeholder = '금액';
      var dAdd = el('button', 'wdc2-psheet__addbtn');
      dAdd.type = 'button';
      dAdd.textContent = '추가';
      dAdd.addEventListener('click', function () {
        var nm = (dName.value || '').trim();
        var amt = (dAmt.value || '').replace(/[^\d.-]/g, '');
        if (!nm && !amt) { return; }
        closePicker();
        // fee 를 먼저 동기 append(모드 클릭의 0건 자동시드와 중복 방지) → direct 모드 명시 전환.
        addDirectInputFee(engineRow, nm, amt);
        var mb = engineRow.querySelector('.base-mode-btn[data-mode="direct"]');
        if (mb) { mb.click(); }
      });
      direct.appendChild(dName);
      direct.appendChild(dAmt);
      direct.appendChild(dAdd);
      pickerBody.appendChild(direct);

      function activate(which) {
        tabCatalog.classList.toggle('is-active', which === 'catalog');
        tabDirect.classList.toggle('is-active', which === 'direct');
        catalog.hidden = which !== 'catalog';
        direct.hidden = which !== 'direct';
      }
      tabCatalog.addEventListener('click', function () { activate('catalog'); });
      tabDirect.addEventListener('click', function () { activate('direct'); });
      tabCustom.addEventListener('click', function () {
        closePicker();
        var b = engineRow.querySelector('.base-mode-btn[data-mode="manual"]');
        if (b) { b.click(); }
        window.setTimeout(function () {
          rebuildBaseGrid();
          var w = baseGridEl ? baseGridEl.children[idx] : null;
          var nmIn = w && w.querySelector('.wdc2-dname');
          if (nmIn) { nmIn.focus(); }
        }, 0);
      });

      picker.hidden = false;
      pickerBackdrop.hidden = false;
      document.body.classList.add('wdc2-sheetpicker-open');
    }

    // ============================================================
    // 기본 구성 미러 그리드.
    // ============================================================
    function engineBaseRows() {
      return baseContainer ? baseContainer.querySelectorAll('.base-component-row') : [];
    }
    function engineOptItems() {
      return optContainer ? optContainer.querySelectorAll('.additional-option-item') : [];
    }
    function engineNoteItems() {
      return notesContainer ? notesContainer.querySelectorAll('.note-item') : [];
    }

    function baseModeLabel(mode) {
      if (mode === 'direct') { return '직접'; }
      if (mode === 'manual') { return '커스텀'; }
      return '제품선택';
    }

    function setBaseMode(engineRow, targetMode, idx) {
      var cur = engineRow.dataset.mode || 'select';
      if (targetMode === cur) { return; }
      var b = engineRow.querySelector('.base-mode-btn[data-mode="' + targetMode + '"]');
      if (b) { b.click(); }
      rebuildBaseGrid();
      if (targetMode === 'manual') {
        window.setTimeout(function () {
          var w = baseGridEl ? baseGridEl.children[idx] : null;
          var nmIn = w && w.querySelector('.wdc2-dname');
          if (nmIn) { nmIn.focus(); }
        }, 0);
      }
    }

    function openBaseModeSheet(engineRow, idx) {
      var cur = engineRow.dataset.mode || 'select';
      openSheet('모드', [
        { value: 'select', label: '제품선택' },
        { value: 'manual', label: '커스텀' },
        { value: 'direct', label: '직접' },
      ], cur, function (value) {
        setBaseMode(engineRow, value, idx);
      });
    }

    function baseProductLabel(engineRow) {
      var sel = engineRow.querySelector('.base-product-select');
      if (sel && sel.value) {
        var opt = sel.options[sel.selectedIndex];
        if (opt && opt.textContent.trim()) { return opt.textContent.trim(); }
      }
      return '제품 선택';
    }

    function buildManualSub(engineRow) {
      var sub = el('div', 'wdc2-subrow wdc2-msub');
      sub.appendChild(makeTie());
      var ptEl = engineRow.querySelector('.base-manual-pricing-type');
      var pt = (ptEl && ptEl.value) || '30cm';
      var ddrop = el('button', 'wdc2-ddrop');
      ddrop.type = 'button';
      ddrop.innerHTML = '<span class="wdc2-ddrop__v">' + (pt === '1m' ? '1m' : '30cm') +
        '</span><span class="wdc2-caret">▾</span>';
      ddrop.addEventListener('click', function () {
        openSheet('단가 방식', [
          { value: '30cm', label: '30cm / 1cm' },
          { value: '1m', label: '1m' },
        ], pt, function (value) {
          if (ptEl) { ptEl.value = value; fireChange(ptEl); }
          rebuildBaseGrid();
        });
      });
      sub.appendChild(ddrop);
      var src = engineRow.querySelector(pt === '1m' ? '.base-manual-price1m' : '.base-manual-price30');
      var priceIn = el('input', 'wdc2-dinput');
      priceIn.type = 'text';
      priceIn.setAttribute('inputmode', 'numeric');
      priceIn.placeholder = '단가';
      priceIn.value = (src && src.value) || '';
      priceIn.addEventListener('input', function () {
        if (src) { src.value = priceIn.value; fireInput(src); }
        refreshBasePrices();
      });
      sub.appendChild(priceIn);
      var hint = el('span', 'wdc2-subhint');
      hint.textContent = '단가 — 방식 × W로 자동 계산';
      sub.appendChild(hint);
      return sub;
    }

    function buildFeeSubs(engineRow, wrap, startIdx) {
      var items = engineRow.querySelectorAll('.base-additional-fee-item');
      var start = startIdx || 0;
      Array.prototype.forEach.call(items, function (item, i) {
        if (i < start) { return; }   // 직접입력 전용 행: 첫 fee 는 상세 셀 인라인 → 서브행에서 제외.
        var sub = el('div', 'wdc2-subrow wdc2-subfee');
        sub.appendChild(makeTie());
        var nameSrc = item.querySelector('.base-additional-fee-name');
        var amtSrc = item.querySelector('.base-additional-fee-amount');
        var nameIn = el('input', 'wdc2-subfee__nm');
        nameIn.type = 'text';
        nameIn.placeholder = '항목명 입력';
        nameIn.value = (nameSrc && nameSrc.value) || '';
        nameIn.addEventListener('input', function () {
          if (nameSrc) { nameSrc.value = nameIn.value; fireInput(nameSrc); }
        });
        var amtIn = el('input', 'wdc2-subfee__amt');
        amtIn.type = 'text';
        amtIn.setAttribute('inputmode', 'numeric');
        amtIn.placeholder = '금액';
        amtIn.value = (amtSrc && amtSrc.value) || '';
        amtIn.addEventListener('input', function () {
          if (amtSrc) { amtSrc.value = amtIn.value; fireInput(amtSrc); }
          refreshBasePrices();
        });
        var x = el('button', 'wdc2-subfee__x');
        x.type = 'button';
        x.setAttribute('aria-label', '직접입력 삭제');
        x.textContent = '✕';
        x.addEventListener('click', function () {
          var rm = item.querySelector('.base-remove-fee-btn');
          if (rm) { rm.click(); }
          window.setTimeout(rebuildBaseGrid, 0);
        });
        sub.appendChild(nameIn);
        sub.appendChild(amtIn);
        sub.appendChild(x);
        wrap.appendChild(sub);
      });
      var addWrap = el('div', 'wdc2-addfee');
      var addFee = el('button', 'wdc2-addfee__btn');
      addFee.type = 'button';
      addFee.innerHTML = '＋ 직접입력';
      addFee.addEventListener('click', function () {
        var b = engineRow.querySelector('.base-add-fee-btn');
        if (b) { b.click(); }
        window.setTimeout(rebuildBaseGrid, 0);
      });
      addWrap.appendChild(addFee);
      wrap.appendChild(addWrap);
    }

    // W 셀 — 엔진 .base-width-input 미러. 복합식('4500+1200') 입력 위해 textarea auto-grow
    // (아이패드 숫자패드에 '+' 없음, 결함1). Enter=blur(폼 submit 오조작 방지). inputmode numeric 없음.
    function buildWidthCell(engineRow) {
      var widthInput = engineRow.querySelector('.base-width-input');
      var wCell = el('textarea', 'wdc2-win');
      wCell.rows = 1;
      wCell.placeholder = 'W';
      wCell.value = (widthInput && widthInput.value) || '';
      wCell.addEventListener('input', function () {
        if (widthInput) { widthInput.value = wCell.value; fireInput(widthInput); }
        autoGrow(wCell);
        refreshBasePrices();
      });
      wCell.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); wCell.blur(); }
      });
      window.setTimeout(function () { autoGrow(wCell); }, 0);   // 초기 다행값 높이 반영.
      return wCell;
    }

    function buildBaseRow(engineRow, idx) {
      var mode = engineRow.dataset.mode || 'select';
      var feeItems = engineRow.querySelectorAll('.base-additional-fee-item');
      var isDirect = mode === 'direct';

      var wrap = el('div', 'wdc2-brow-wrap' + (mode === 'manual' ? ' is-mine' : '') +
        (isDirect ? ' is-direct' : ''));
      var row = el('div', 'wdc2-brow' + (isDirect ? ' wdc2-brow--direct' : ''));
      wrap.appendChild(row);

      // (a) 모드 드롭다운 — 제품선택 / 커스텀 / 직접 (3-모드 사이클 토글 제거).
      var modeDrop = el('button', 'wdc2-modedrop' +
        (mode === 'manual' ? ' wdc2-modedrop--mine' : '') +
        (isDirect ? ' wdc2-modedrop--direct' : ''));
      modeDrop.type = 'button';
      modeDrop.setAttribute('aria-label', '모드 선택');
      modeDrop.innerHTML = '<span class="wdc2-modechip__n">' + (idx + 1) + '</span>' +
        '<span class="wdc2-modedrop__v">' + baseModeLabel(mode) + '</span>' +
        '<span class="wdc2-caret">▾</span>';
      modeDrop.addEventListener('click', function () {
        openBaseModeSheet(engineRow, idx);
      });
      row.appendChild(modeDrop);

      // (b) 상세 셀 + (c) W 셀.
      if (isDirect) {
        // 직접입력: 제품선택과 동일 그리드 — 상세=항목명(0.7fr), W=금액(0.5fr).
        var first = feeItems.length ? feeItems[0] : null;
        if (first) {
          var dNameSrc = first.querySelector('.base-additional-fee-name');
          var dAmtSrc = first.querySelector('.base-additional-fee-amount');
          var dName = el('input', 'wdc2-dname');
          dName.type = 'text';
          dName.placeholder = '항목명 입력';
          dName.value = (dNameSrc && dNameSrc.value) || '';
          dName.addEventListener('input', function () {
            if (dNameSrc) { dNameSrc.value = dName.value; fireInput(dNameSrc); }
          });
          var dAmt = el('input', 'wdc2-win wdc2-direct-amt');
          dAmt.type = 'text';
          dAmt.setAttribute('inputmode', 'numeric');
          dAmt.placeholder = '금액';
          dAmt.value = (dAmtSrc && dAmtSrc.value) || '';
          dAmt.addEventListener('input', function () {
            if (dAmtSrc) { dAmtSrc.value = dAmt.value; fireInput(dAmtSrc); }
            refreshBasePrices();
          });
          row.appendChild(dName);
          row.appendChild(dAmt);
        } else {
          var dEmpty = el('span', 'wdc2-direct-empty');
          dEmpty.textContent = '—';
          row.appendChild(dEmpty);
          var wEmpty = el('span', 'wdc2-win-empty');
          wEmpty.textContent = '—';
          row.appendChild(wEmpty);
        }
      } else if (mode === 'manual') {
        // 제품명(CUSTOM) — 전폭 입력.
        var nameEl = engineRow.querySelector('.base-manual-name');
        var nameCell = el('input', 'wdc2-dname');
        nameCell.type = 'text';
        nameCell.placeholder = '제품명 입력';
        nameCell.value = (nameEl && nameEl.value) || '';
        nameCell.addEventListener('input', function () {
          var live = engineRow.querySelector('.base-manual-name');
          if (live) { live.value = nameCell.value; fireInput(live); }
        });
        row.appendChild(nameCell);
        row.appendChild(buildWidthCell(engineRow));
      } else {
        // 제품(선택) — 시트 3-세그.
        var prodBtn = el('button', 'wdc2-prodbtn');
        prodBtn.type = 'button';
        prodBtn.innerHTML = '<span class="wdc2-prodbtn__nm">' + escapeText(baseProductLabel(engineRow)) +
          '</span><span class="wdc2-caret">▾</span>';
        prodBtn.addEventListener('click', function () {
          openProductSheet(engineRow, idx, prodBtn);
        });
        row.appendChild(prodBtn);
        row.appendChild(buildWidthCell(engineRow));
      }

      // (d) 단가 — READ-ONLY 계산 미러(금액만).
      var priceCell = el('span', 'wdc2-price');
      priceCell.setAttribute('data-price-idx', String(idx));
      priceCell.innerHTML = '<span class="wdc2-price__v">0</span>';
      row.appendChild(priceCell);

      // (e) ✕ — 엔진 삭제 위임.
      var del = el('button', 'wdc2-del');
      del.type = 'button';
      del.setAttribute('aria-label', '구성 행 삭제');
      del.textContent = '✕';
      del.addEventListener('click', function () {
        var rm = engineRow.querySelector('.base-remove-btn');
        if (rm) { rm.click(); }   // 행 1개면 엔진이 무시 → 옵저버가 재빌드
      });
      row.appendChild(del);

      // 서브행 — 직접입력 fee·＋직접입력은 사용자가 추가할 때만 표시.
      if (isDirect) {
        if (feeItems.length > 1) {
          buildFeeSubs(engineRow, wrap, 1);
        } else {
          buildFeeSubs(engineRow, wrap, feeItems.length);
        }
      } else if (mode === 'manual') {
        wrap.appendChild(buildManualSub(engineRow));
        if (feeItems.length > 0) {
          buildFeeSubs(engineRow, wrap, 0);
        } else {
          var addWrapOnly = el('div', 'wdc2-addfee');
          var addFeeOnly = el('button', 'wdc2-addfee__btn');
          addFeeOnly.type = 'button';
          addFeeOnly.innerHTML = '＋ 직접입력';
          addFeeOnly.addEventListener('click', function () {
            var b = engineRow.querySelector('.base-add-fee-btn');
            if (b) { b.click(); }
            window.setTimeout(rebuildBaseGrid, 0);
          });
          addWrapOnly.appendChild(addFeeOnly);
          wrap.appendChild(addWrapOnly);
        }
      } else if (feeItems.length > 0) {
        buildFeeSubs(engineRow, wrap, 0);
      } else {
        var addWrapSel = el('div', 'wdc2-addfee');
        var addFeeSel = el('button', 'wdc2-addfee__btn');
        addFeeSel.type = 'button';
        addFeeSel.innerHTML = '＋ 직접입력';
        addFeeSel.addEventListener('click', function () {
          var b = engineRow.querySelector('.base-add-fee-btn');
          if (b) { b.click(); }
          window.setTimeout(rebuildBaseGrid, 0);
        });
        addWrapSel.appendChild(addFeeSel);
        wrap.appendChild(addWrapSel);
      }
      return wrap;
    }

    function rebuildBaseGrid() {
      if (!baseGridEl) { return; }
      var rows = engineBaseRows();
      baseGridEl.innerHTML = '';
      Array.prototype.forEach.call(rows, function (r, i) {
        baseGridEl.appendChild(buildBaseRow(r, i));
      });
      refreshBasePrices();
      syncCounts();
    }

    function refreshBasePrices() {
      if (!baseGridEl) { return; }
      var comps = readBaseComps();
      var cells = baseGridEl.querySelectorAll('[data-price-idx]');
      Array.prototype.forEach.call(cells, function (cell) {
        var i = Number(cell.getAttribute('data-price-idx'));
        var v = comps[i] ? fmtNum(computeCompPrice(comps[i])) : '0';
        var span = cell.querySelector('.wdc2-price__v') || cell;
        span.textContent = v;
      });
    }

    // ============================================================
    // 추가 옵션 미러 그리드.
    // ============================================================
    function optIsSelectMode(item) {
      var sel = item.querySelector('[data-category-option-select]');
      return !!(sel && sel.style.display !== 'none' && sel.value);
    }
    function optLabel(item) {
      var nameEl = item.querySelector('[data-option-name]');
      var nm = nameEl && (nameEl.value || '').trim();
      if (nm) { return nm; }
      var sel = item.querySelector('[data-category-option-select]');
      if (sel && sel.value) {
        var opt = sel.options[sel.selectedIndex];
        if (opt && opt.textContent.trim()) { return opt.textContent.trim(); }
      }
      return '옵션 선택';
    }

    function buildOptRow(item) {
      var row = el('div', 'wdc2-orow');
      var isSel = optIsSelectMode(item);
      var badge = el('button', 'wdc2-obadge' + (isSel ? '' : ' wdc2-obadge--mine'));
      badge.type = 'button';
      badge.textContent = isSel ? '옵션' : 'CUSTOM';
      badge.addEventListener('click', function () {
        var t = item.querySelector('[data-toggle-direct-input]');
        if (t) { t.click(); }
        window.setTimeout(rebuildOptGrid, 0);
      });
      row.appendChild(badge);

      var amt = el('input', 'wdc2-oamt');
      if (isSel) {
        var btn = el('button', 'wdc2-optbtn');
        btn.type = 'button';
        btn.innerHTML = '<span class="wdc2-optbtn__nm">' + escapeText(optLabel(item)) +
          '</span><span class="wdc2-caret">▾</span>';
        btn.addEventListener('click', function () {
          var sel = item.querySelector('[data-category-option-select]');
          if (!sel) { return; }
          openSheet('옵션 선택', optionsFromSelect(sel), sel.value, function (value) {
            sel.value = value;
            fireChange(sel);   // 엔진: name·price 자동 채움 + select 모드 전환
            window.setTimeout(function () {
              var lbl = btn.querySelector('.wdc2-optbtn__nm');
              if (lbl) { lbl.textContent = optLabel(item); }
              var ps = item.querySelector('[data-option-price]');
              if (ps) { amt.value = ps.value; }
            }, 0);
          });
        });
        row.appendChild(btn);
      } else {
        var nameSrc = item.querySelector('[data-option-name]');
        var nameIn = el('input', 'wdc2-optname');
        nameIn.type = 'text';
        nameIn.placeholder = '옵션명 직접 입력';
        nameIn.value = (nameSrc && nameSrc.value) || '';
        nameIn.addEventListener('input', function () {
          if (nameSrc) { nameSrc.value = nameIn.value; fireInput(nameSrc); }
        });
        row.appendChild(nameIn);
      }

      var priceSrc = item.querySelector('[data-option-price]');
      amt.className = 'wdc2-oamt';
      amt.type = 'text';
      amt.setAttribute('inputmode', 'numeric');
      amt.placeholder = '금액';
      amt.value = (priceSrc && priceSrc.value) || '';
      amt.addEventListener('input', function () {
        if (priceSrc) { priceSrc.value = amt.value; fireInput(priceSrc); }
      });
      row.appendChild(amt);

      var del = el('button', 'wdc2-del');
      del.type = 'button';
      del.setAttribute('aria-label', '옵션 삭제');
      del.textContent = '✕';
      del.addEventListener('click', function () {
        var rm = item.querySelector('.remove-option-btn');
        if (rm) { rm.click(); }
      });
      row.appendChild(del);
      return row;
    }

    function rebuildOptGrid() {
      if (!optGridEl) { return; }
      var items = engineOptItems();
      optGridEl.innerHTML = '';
      Array.prototype.forEach.call(items, function (item) {
        optGridEl.appendChild(buildOptRow(item));
      });
      syncCounts();
    }

    // ============================================================
    // 비고 정식 섹션 미러 그리드.
    // ============================================================
    function noteIsSelectMode(item) {
      var sel = item.querySelector('.note-select');
      return !!(sel && sel.style.display !== 'none');
    }
    function noteLabel(item) {
      var sel = item.querySelector('.note-select');
      if (sel && sel.value) {
        var opt = sel.options[sel.selectedIndex];
        if (opt && opt.textContent.trim()) { return opt.textContent.trim(); }
      }
      return '문구 선택';
    }

    function buildNoteRow(item) {
      var row = el('div', 'wdc2-nrow');
      var isSel = noteIsSelectMode(item);
      var badge = el('button', 'wdc2-obadge' + (isSel ? '' : ' wdc2-obadge--mine'));
      badge.type = 'button';
      badge.textContent = isSel ? '문구' : 'CUSTOM';
      badge.addEventListener('click', function () {
        var t = item.querySelector('.toggle-note-type');
        if (t) { t.click(); }   // 엔진 renderNoteItem 재렌더 → notesContainer childList → 옵저버 재빌드
      });
      row.appendChild(badge);

      if (isSel) {
        var sel = item.querySelector('.note-select');
        var btn = el('button', 'wdc2-optbtn');
        btn.type = 'button';
        btn.innerHTML = '<span class="wdc2-optbtn__nm">' + escapeText(noteLabel(item)) +
          '</span><span class="wdc2-caret">▾</span>';
        btn.addEventListener('click', function () {
          if (!sel) { return; }
          openSheet('비고 문구', optionsFromSelect(sel), sel.value, function (value) {
            sel.value = value;
            fireChange(sel);
            var lbl = btn.querySelector('.wdc2-optbtn__nm');
            if (lbl) { lbl.textContent = noteLabel(item); }
          });
        });
        row.appendChild(btn);
      } else {
        var ta = item.querySelector('.note-input');
        var inp = el('input', 'wdc2-optname');
        inp.type = 'text';
        inp.placeholder = '비고 직접 입력';
        inp.value = (ta && ta.value) || '';
        inp.addEventListener('input', function () {
          if (ta) { ta.value = inp.value; fireInput(ta); }
        });
        row.appendChild(inp);
      }

      var del = el('button', 'wdc2-del');
      del.type = 'button';
      del.setAttribute('aria-label', '비고 삭제');
      del.textContent = '✕';
      del.addEventListener('click', function () {
        var rm = item.querySelector('.remove-note');
        if (rm) { rm.click(); }
      });
      row.appendChild(del);
      return row;
    }

    function rebuildNoteGrid() {
      if (!noteGridEl) { return; }
      var items = engineNoteItems();
      noteGridEl.innerHTML = '';
      Array.prototype.forEach.call(items, function (item) {
        noteGridEl.appendChild(buildNoteRow(item));
      });
      syncCounts();
    }

    // ============================================================
    // 행/옵션/비고 추가.
    // ============================================================
    sheet.addEventListener('click', function (e) {
      var addEl = e.target.closest('.wdc2-addrow__a');
      if (!addEl) { return; }
      var kind = addEl.getAttribute('data-add');
      if (kind === 'base' && addBaseBtn) {
        addBaseBtn.click();   // 엔진 append(select) → 옵저버 재빌드
      } else if (kind === 'mine' && addBaseBtn) {
        addBaseBtn.click();
        window.setTimeout(function () {
          var rows = engineBaseRows();
          var last = rows.length ? rows[rows.length - 1] : null;
          if (last) {
            var mb = last.querySelector('.base-mode-btn[data-mode="manual"]');
            if (mb) { mb.click(); }
          }
          rebuildBaseGrid();
        }, 0);
      } else if (kind === 'opt' && addOptBtn) {
        addOptBtn.click();
      } else if (kind === 'note' && addNoteBtn) {
        addNoteBtn.click();
      }
    });

    // ============================================================
    // 구조 변화 옵저버(행 추가/삭제/견적 로드). childList 만(서브트리 값 변경 미발화 → 타이핑 클로버 방지).
    // ============================================================
    var baseObs = null;
    var optObs = null;
    var noteObs = null;
    function connectObservers() {
      if (!window.MutationObserver) { return; }
      if (baseContainer) {
        if (!baseObs) { baseObs = new MutationObserver(function () { rebuildBaseGrid(); }); }
        baseObs.observe(baseContainer, { childList: true });
      }
      if (optContainer) {
        if (!optObs) { optObs = new MutationObserver(function () { rebuildOptGrid(); }); }
        optObs.observe(optContainer, { childList: true });
      }
      if (notesContainer) {
        if (!noteObs) { noteObs = new MutationObserver(function () { rebuildNoteGrid(); }); }
        noteObs.observe(notesContainer, { childList: true });
      }
    }
    function disconnectObservers() {
      if (baseObs) { baseObs.disconnect(); }
      if (optObs) { optObs.disconnect(); }
      if (noteObs) { noteObs.disconnect(); }
    }

    // ============================================================
    // 라이브 미러(패널 브레이크다운 / 액션바 / 조정 스트립).
    // ============================================================
    function syncCounts() {
      var nb = engineBaseRows().length;
      var no = engineOptItems().length;
      var nn = engineNoteItems().length;
      if (baseCountEl) { baseCountEl.textContent = (nb ? nb + '행 · ' : '') + '필수'; }
      if (optCountEl) { optCountEl.textContent = no ? no + '건' : ''; }
      if (noteCountEl) { noteCountEl.textContent = nn ? nn + '건 · 견적서 표기' : '견적서 표기'; }
      if (curBaseCntEl) { curBaseCntEl.textContent = nb ? nb + '행' : ''; }
      if (curOptCntEl) { curOptCntEl.textContent = no ? no + '건' : ''; }
    }
    function syncFinal() {
      var v = txt(finalPriceEl) || '0원';
      if (abarValEl && abarValEl.textContent !== v) { abarValEl.textContent = v; }
      if (curTotalEl && curTotalEl.textContent !== v) { curTotalEl.textContent = v; }
    }
    function syncBreakdown() {
      if (baseValEl) { baseValEl.textContent = txt(totalBaseEl) || '0원'; }
      if (optValEl) { optValEl.textContent = '+' + (txt(totalAddEl) || '0원'); }
    }
    function syncStrip() {
      if (discValEl) { discValEl.textContent = '−' + fmtNum(numFrom(couponInput)) + '원'; }
      if (shipValEl) { shipValEl.textContent = '+' + fmtNum(numFrom(shipCostInput)) + '원'; }
      if (shipNoteEl) {
        shipNoteEl.textContent = (shipInclInput && shipInclInput.checked) ? '포함' : '별도';
      }
    }
    function syncEstimates() {
      var cards = estContainer
        ? estContainer.querySelectorAll('.card[data-estimate-id]').length : 0;
      var label = cards ? cards + '건' : '';
      if (listCountEl) { listCountEl.textContent = label; }
      if (footCountEl) { footCountEl.textContent = label ? '· ' + label : ''; }
      var allEl = document.getElementById('totalAllFinalPrice');
      if (allTotalEl) { allTotalEl.textContent = allEl ? (txt(allEl) || '0원') : '0원'; }
      var sb = document.getElementById('saveEstimateBtn');
      if (panelSaveBtn) { panelSaveBtn.disabled = !(sb && sb.style.display !== 'none'); }
      if (panelNewBtn) { panelNewBtn.disabled = !document.getElementById('resetEstimateBtn'); }
    }

    // 단가 표시 토글(SSOT=엔진 체크박스) 미러. display:none 컨테이너라 offsetParent 불가 → 체크상태 직접 읽음.
    function unitMetaVisible() {
      var t = document.getElementById('wdUnitPriceMetaToggle');
      return t ? !!t.checked : true;
    }

    // qcard 라인 스크레이프: 엔진은 옵션/비고를 라인당 <div> 로 렌더(buildOptionsDetailHtml
    // :687~ / buildNotesHtml :708~ 실사) — 자식 요소가 있으면 그대로 라인 분해. 자식 없는
    // 결합 문자열은 "…원)" 경계 폴백(lookbehind 미사용 — 구 Safari 정규식 파스 에러 방지).
    function scrapeLines(node) {
      var out = [];
      if (!node) { return out; }
      var kids = node.children;
      if (kids && kids.length) {
        for (var i = 0; i < kids.length; i++) {
          var t = txt(kids[i]);
          if (t) { out.push(t); }
        }
        return out;
      }
      var whole = txt(node);
      if (!whole || whole === '없음') { return out; }
      var m = whole.match(/.+?원\)/g);
      if (m && m.length > 1) {
        for (var j = 0; j < m.length; j++) { out.push(m[j].replace(/^\s+|\s+$/g, '')); }
        return out;
      }
      out.push(whole);
      return out;
    }

    // 진행 견적 v2 컴팩트 카드 재스크레이프(엔진 estimatesListContainer → .wdc2-qcards).
    // r1=[견적N][금액(flex:none — 절대 불잘림)] / r2=이름 전폭 줄바꿈+연필 / 구성·옵션·비고
    // 라인당 1줄 전부 표시(클램프·ellipsis 없음 — 스택 스크롤이 흡수) / 단가 메타 토글 연동.
    function buildQCards() {
      if (!qcardsEl) { return; }
      qcardsEl.innerHTML = '';
      if (!estContainer) { return; }
      var cards = estContainer.querySelectorAll('.card[data-estimate-id]');
      var showUnit = unitMetaVisible();
      Array.prototype.forEach.call(cards, function (card, i) {
        var noNode = card.querySelector('.card-header strong');
        var noText = noNode ? txt(noNode) : ('견적 ' + (i + 1));
        var nameNode = card.querySelector('.estimate-display-name');
        var name = nameNode ? (nameNode.getAttribute('title') || txt(nameNode)) : '';
        var totalNode = card.querySelector('.estimate-total-price');
        var total = totalNode ? txt(totalNode) : '';
        var baseLines = scrapeLines(card.querySelector('.estimate-detail-base'));
        var optLines = scrapeLines(card.querySelector('.estimate-detail-options'));
        var noteLines = scrapeLines(card.querySelector('.estimate-detail-notes'));
        var unitNode = card.querySelector('.wd-estimate-unit-meta');
        var unitText = unitNode ? txt(unitNode) : '';

        var qc = el('div', 'wdc2-qcard');

        // r1: [견적 N] ---- [금액] (금액 flex:none — 좌측이 아니라 이름이 양보).
        var r1 = el('div', 'wdc2-qcard__r1');
        var no = el('span', 'wdc2-qcard__no');
        no.textContent = noText;
        var grow = el('span', 'wdc2-qcard__grow');
        var amt = el('span', 'wdc2-qcard__amt');
        amt.textContent = total;
        r1.appendChild(no);
        r1.appendChild(grow);
        r1.appendChild(amt);
        qc.appendChild(r1);

        // r2: 제품명/구성명 전폭 — 줄바꿈 허용(ellipsis 금지) + 이름수정 연필.
        var r2 = el('div', 'wdc2-qcard__r2');
        var nm = el('span', 'wdc2-qcard__nm');
        nm.textContent = name;
        var pen = el('button', 'wdc2-qcard__pen');
        pen.type = 'button';
        pen.setAttribute('aria-label', '이름 수정');
        pen.innerHTML = '<i class="fas fa-pen" aria-hidden="true"></i>';
        pen.addEventListener('click', function () {
          var b = card.querySelector('.edit-estimate-name-btn');
          if (b) { b.click(); }
        });
        r2.appendChild(nm);
        r2.appendChild(pen);
        qc.appendChild(r2);

        var k;
        for (k = 0; k < baseLines.length; k++) {
          // 헤더 이름과 동일한 단일 구성 라인은 중복 소음 — 생략.
          if (baseLines.length === 1 && baseLines[k] === name) { break; }
          var ln = el('div', 'wdc2-qcard__ln');
          ln.textContent = baseLines[k];
          qc.appendChild(ln);
        }
        if (showUnit && unitText) {
          var um = el('div', 'wdc2-qcard__unit');
          um.textContent = unitText;
          qc.appendChild(um);
        }
        for (k = 0; k < optLines.length; k++) {
          var op = el('div', 'wdc2-qcard__opt');
          op.textContent = '+ ' + optLines[k];
          qc.appendChild(op);
        }
        for (k = 0; k < noteLines.length; k++) {
          var nt = el('div', 'wdc2-qcard__note');
          nt.textContent = noteLines[k];
          qc.appendChild(nt);
        }

        var acts = el('div', 'wdc2-qcard__acts');
        var edit = el('button', 'wdc2-qcard__act');
        edit.type = 'button';
        edit.textContent = '수정';
        edit.addEventListener('click', function () {
          var b = card.querySelector('.edit-estimate-btn');
          if (b) { b.click(); }
        });
        var del = el('button', 'wdc2-qcard__act wdc2-qcard__act--danger');
        del.type = 'button';
        del.textContent = '삭제';
        del.addEventListener('click', function () {
          var b = card.querySelector('.delete-estimate-btn');
          if (b) { b.click(); }
        });
        acts.appendChild(edit);
        acts.appendChild(del);
        qc.appendChild(acts);

        qcardsEl.appendChild(qc);
      });
    }

    if (window.MutationObserver) {
      if (finalPriceEl) {
        new MutationObserver(syncFinal).observe(finalPriceEl,
          { childList: true, characterData: true, subtree: true });
      }
      if (totalBaseEl) {
        new MutationObserver(syncBreakdown).observe(totalBaseEl,
          { childList: true, characterData: true, subtree: true });
      }
      if (totalAddEl) {
        new MutationObserver(syncBreakdown).observe(totalAddEl,
          { childList: true, characterData: true, subtree: true });
      }
      if (estContainer) {
        new MutationObserver(function () { syncEstimates(); buildQCards(); }).observe(estContainer,
          { childList: true, characterData: true, subtree: true });
      }
    }
    if (couponInput) { couponInput.addEventListener('input', syncStrip); }
    if (shipCostInput) { shipCostInput.addEventListener('input', syncStrip); }
    if (shipInclInput) { shipInclInput.addEventListener('change', syncStrip); }
    // 단가 토글 변경 → qcard 단가메타 가시성 재반영(엔진이 childList 를 안 바꿀 수 있어 직접 구독).
    var unitToggleInput = document.getElementById('wdUnitPriceMetaToggle');
    if (unitToggleInput) { unitToggleInput.addEventListener('change', buildQCards); }

    // 액션/패널 버튼 — cloneNode/동적생성 함정 회피 위해 클릭 시 live lookup.
    if (abarAddBtn) {
      abarAddBtn.addEventListener('click', function () {
        var b = document.getElementById('addEstimateBtn');
        if (b) { b.click(); }
      });
    }
    if (panelSaveBtn) {
      panelSaveBtn.addEventListener('click', function () {
        var b = document.getElementById('saveEstimateBtn');
        if (b && b.style.display !== 'none') { b.click(); }
      });
    }
    if (panelNewBtn) {
      panelNewBtn.addEventListener('click', function () {
        var b = document.getElementById('resetEstimateBtn');
        if (b) { b.click(); }
      });
    }

    // ============================================================
    // 저장 견적 오버레이 open/close.
    // ============================================================
    function isOpen() { return shell.classList.contains('wdc2-saved-open'); }
    function setOpen(open) {
      shell.classList.toggle('wdc2-saved-open', open);
      backdrop.hidden = !open;
      if (searchBtn) { searchBtn.setAttribute('aria-expanded', open ? 'true' : 'false'); }
    }
    if (searchBtn) {
      searchBtn.addEventListener('click', function () {
        if (document.body.classList.contains(BODY_CLASS)) { setOpen(!isOpen()); }
      });
    }
    overlay.querySelector('.wdc2-saved-overlay__close').addEventListener('click', function () {
      setOpen(false);
    });
    backdrop.addEventListener('click', function () { setOpen(false); });

    // ============================================================
    // dock / undock.
    // ============================================================
    function dockFrame() {
      moveInto(custGroup, custSlot);
      moveInto(settingsLink, settingsSlot);
      moveInto(couponGroup, discSlot);
      moveInto(shipCostGroup, shipCostSlot);
      moveInto(shipInclGroup, shipInclSlot);
      moveInto(estContainer, estSlot);
      moveInto(unitToggleWrap, unitToggleSlot);
      moveInto(savedCard, savedSlot);
      rebuildBaseGrid();
      rebuildOptGrid();
      rebuildNoteGrid();
      connectObservers();
      syncFinal();
      syncBreakdown();
      syncStrip();
      syncEstimates();
      buildQCards();
    }
    function undockFrame() {
      disconnectObservers();
      if (baseGridEl) { baseGridEl.innerHTML = ''; }
      if (optGridEl) { optGridEl.innerHTML = ''; }
      if (noteGridEl) { noteGridEl.innerHTML = ''; }
      if (qcardsEl) { qcardsEl.innerHTML = ''; }
      restoreAll();
    }

    // ============================================================
    // enable / disable — 게이트 진입/이탈.
    // ============================================================
    function enableSkin() {
      if (document.body.classList.contains('wd-builder')) { clearPending(); return; }   // 폰 셸 우선
      if (document.body.classList.contains(BODY_CLASS)) { clearPending(); return; }
      document.body.classList.add(BODY_CLASS);
      dockFrame();
      setOpen(false);
      clearPending();   // v2 발현 완료 — 선제 은닉을 v2 표면이 이어받음
      if (window.requestWdCalculatorLayoutSync) { window.requestWdCalculatorLayoutSync(); }
    }
    function disableSkin() {
      clearPending();   // 게이트 미매치/이탈 — PC 표시 즉시 복귀
      var wasOn = document.body.classList.contains(BODY_CLASS);
      document.body.classList.remove(BODY_CLASS);
      shell.classList.remove('wdc2-saved-open');
      if (wasOn) { undockFrame(); }
      closePicker();
      backdrop.hidden = true;
      if (searchBtn) { searchBtn.setAttribute('aria-expanded', 'false'); }
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
