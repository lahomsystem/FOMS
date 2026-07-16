/**
 * WDCalculator 태블릿 가로 융합 셸(JS) — 목업 frame11(P11) "표형 UI" 그라운드업 (2026-07-16).
 *
 * 배경: 직전 판(d6757fd4)은 pcbar·우측 진행 견적 패널·하단 최종견적 바까지는 목업 정합이었으나,
 * **본문이 PC 위젯 이동판**(엔진의 .base-component-row 카드를 그대로 옮겨 방식 세그·가로(mm) 1필드·
 * 추가금 리스트가 노출)이라 목업의 "표형 그리드"가 아니었다. 본판은 **본문을 신규 표형 DOM 으로
 * 재제작**한다:
 *   - 기본 구성: `제품 구성(선택 ▾=시트) | W | D | H | 단가 | ✕` 행 그리드 + [+ 구성 행 추가].
 *   - 추가 옵션: `옵션(선택 ▾) | 금액 | ✕` 행 그리드 + [+ 옵션 추가].
 *   - 쿠폰·배송·비고: 엔진 입력을 컴팩트 카드로 이동(단순 설정 — 표형 대상 아님).
 *
 * 엔진 READ-ONLY 원칙: 계산·저장 엔진(primary-form/pricing-core/estimate-lifecycle)은 일절
 * 수정하지 않는다. 표형 그리드는 **신규 DOM**이고, 엔진 노드(#baseComponentsContainer 등)는
 * PC 카드에 **은닉 상태로 유지**(엔진이 querySelector·delegated listener·save read 로 계속 소유)한다.
 * 표형 셀은 은닉 엔진 위젯에 **양방향 미러**한다(아래 미러 계약):
 *
 *   | 표형 셀 | 미러 대상(은닉 엔진 위젯)            | 방향/트리거                                   |
 *   |--------|------------------------------------|----------------------------------------------|
 *   | 제품    | .base-product-select (select 모드) | 시트 pick → value 설정 + change 디스패치      |
 *   | (직접)  | .base-manual-price30 / -price1m    | 입력 → value 설정 + input 디스패치            |
 *   | W      | .base-width-input                  | 입력 → value 설정 + input(엔진 preview·재계산)|
 *   | D / H  | .base-additional-fee-name (센티넬)  | 입력 → 센티넬 추가금(금액 0, 무가격) upsert    |
 *   | 단가    | window.wdcComputeCurrentEstimateMath([row]) | 관찰(READ-ONLY 순수 계산 재호출)      |
 *   | ✕      | .base-remove-btn                   | 클릭 위임                                     |
 *   | 옵션    | [data-category-option-select]      | 시트 pick → value 설정 + change(엔진 name·price)|
 *   | 금액    | [data-option-price]                | 입력 ↔ value 미러                             |
 *
 * D/H 데이터 계약(조사 결과): PC 엔진의 base component 계약은 { mode, widthInput, widthMm,
 * additionalFees, productId | manualPricing } 으로 **깊이(D)·높이(H) 필드가 없다**. 엔진이 save 시
 * 재읽기(readBaseComponentsFromUI)하는 자유 텍스트 채널은 additionalFee.name 뿐이므로, D/H 는
 * 행별 **센티넬 추가금**(name='[규격] D{d} H{h}', amount 0)으로 직렬화한다 → 저장→검색→재로드
 * 라운드트립에서 ensureBaseComponentsUI 가 센티넬을 재렌더하고 표형이 파싱해 복원한다. 금액 0
 * 추가금은 pricing-core 에서 detailLine/displayPart/가격 모두 skip(무가격·무표시) → 저장 견적
 * 카드·총액에 영향 없음. 단, PC 뷰 추가금 편집기에는 0원 행으로 노출된다(FLAG: §보고).
 *
 * 시트 피커: 자체 바텀시트(.wdc-tf-sheet). 엔진 select 의 live <option> 을 열 때 복제 → 목업
 * num-box 룩(버튼 라벨 + ▾, 자유텍스트 옵션명도 라벨 표시)을 완전 제어. foms-mobile-select 는
 * native select 대상이라 표형 버튼 UX 와 맞지 않아 미사용(무충돌).
 *
 * 게이트: (min-width:992px) and (orientation:landscape) and (pointer:coarse) 且 비임베디드.
 * 게이트 이탈(회전/리사이즈)→ 이동 노드 원위치 복원 + 표형 그리드 파기 + 옵저버 해제(PC·폰·임베디드
 * 무회귀). 폰 셸(mobile-enhance.js ≤991.98, body.wd-builder)이 DOM 을 접수했으면 스킨 양보.
 *
 * 성능 가드 G4: 전역/문서 리스너는 singleton 가드로 1회만 바인딩(fragment 재실행 무해).
 */
(function () {
  'use strict';

  if (window.__WDC_TABLET_SKIN_BOUND) { return; }
  window.__WDC_TABLET_SKIN_BOUND = true;

  var STORAGE_KEY = 'wdcTabletSavedOpen';   // '1' = 저장 오버레이 펼침 상태 기억
  var GATE = '(min-width: 992px) and (orientation: landscape) and (pointer: coarse)';
  var DH_PREFIX = '[규격]';                 // D/H 센티넬 추가금 name 접두어

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

  function fmtNum(n) {
    var v = Number(n) || 0;
    if (typeof window.formatNumber === 'function') { return window.formatNumber(v); }
    return v.toLocaleString('ko-KR');
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

  // ============================================================
  // D/H 센티넬 추가금 직렬화.
  // ============================================================
  function encodeDH(d, h) {
    d = String(d == null ? '' : d).trim();
    h = String(h == null ? '' : h).trim();
    if (!d && !h) { return ''; }
    var parts = [DH_PREFIX];
    if (d) { parts.push('D' + d); }
    if (h) { parts.push('H' + h); }
    return parts.join(' ');
  }
  function parseDH(name) {
    name = String(name || '');
    if (name.indexOf(DH_PREFIX) !== 0) { return null; }
    var dm = name.match(/D(\d+)/);
    var hm = name.match(/H(\d+)/);
    return { d: (dm && dm[1]) || '', h: (hm && hm[1]) || '' };
  }
  function readRowDH(engineRow) {
    var names = engineRow.querySelectorAll('.base-additional-fee-name');
    for (var i = 0; i < names.length; i++) {
      var dh = parseDH(names[i].value);
      if (dh) { return dh; }
    }
    return { d: '', h: '' };
  }
  function feeItemHtml() {
    return (
      '<div class="col-12 col-md-5"><input type="text" class="form-control form-control-sm base-additional-fee-name" value=""></div>' +
      '<div class="col-12 col-md-4"><input type="number" class="form-control form-control-sm base-additional-fee-amount" min="0" step="1" value=""></div>' +
      '<div class="col-12 col-md-3 text-end"><button type="button" class="btn btn-sm btn-outline-danger base-remove-fee-btn" title="삭제"><i class="fas fa-times"></i></button></div>'
    );
  }
  function writeRowDH(engineRow, d, h) {
    var feesList = engineRow.querySelector('.base-additional-fees-list');
    if (!feesList) { return; }
    var sentinel = null;
    var names = feesList.querySelectorAll('.base-additional-fee-name');
    for (var i = 0; i < names.length; i++) {
      if (parseDH(names[i].value)) { sentinel = names[i].closest('.base-additional-fee-item'); break; }
    }
    var encoded = encodeDH(d, h);
    if (!encoded) {
      if (sentinel) {
        var host = sentinel.parentNode;
        sentinel.remove();
        fireInput(host || feesList);  // 엔진 재계산(무가격이라 총액 불변)
      }
      return;
    }
    if (!sentinel) {
      sentinel = document.createElement('div');
      sentinel.className = 'row g-2 align-items-end mb-2 base-additional-fee-item';
      sentinel.innerHTML = feeItemHtml();
      feesList.appendChild(sentinel);
    }
    var nameInput = sentinel.querySelector('.base-additional-fee-name');
    if (nameInput) { nameInput.value = encoded; fireInput(nameInput); }
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
    // 재부모화 북키핑(쿠폰·배송·비고·고객명·설정·견적리스트·주 액션 버튼만 이동).
    // 표형 대상(base/opt)은 이동하지 않고 은닉 유지 → 그리드가 미러.
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
    function closest(id, sel) {
      var n = document.getElementById(id);
      return n ? n.closest(sel) : null;
    }

    // 이동 대상.
    var custGroup = closest('customerName', '.mb-3');
    var settingsLink = container.querySelector('.wdcalculator-main-scroll a[href*="product"]');
    var couponGroup = closest('globalCouponValue', '.mb-3');
    var shipCostGroup = closest('shippingCost', '.mb-3');
    var shipInclGroup = closest('shippingIncluded', '.mb-3');
    var notesGroup = closest('notesContainer', '.mb-3');
    var estContainer = document.getElementById('estimatesListContainer');
    var calcBtn = document.getElementById('calculateBtn');
    var addBtn = document.getElementById('addEstimateBtn');
    var finalPriceEl = document.getElementById('finalPrice');
    var custInput = document.getElementById('customerName');
    // 표형이 미러할 은닉 엔진 컨테이너.
    var baseContainer = document.getElementById('baseComponentsContainer');
    var optContainer = document.getElementById('additionalOptionsContainer');
    var addBaseBtn = document.getElementById('addBaseComponentBtn');
    var addOptBtn = document.getElementById('addOptionBtn');

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
    // (2) 본문 — 목업 표형 카드.
    // ============================================================
    var tfBody = el('div', 'wdc-tf-body',
      '<div class="wdc-tf-toolbar">' +
        '<div class="wdc-tf-toggle" role="tablist" aria-label="입력 방식">' +
          '<button type="button" class="wdc-tf-toggle__btn is-active" data-mode="select" role="tab" aria-selected="true">선택 입력</button>' +
          '<button type="button" class="wdc-tf-toggle__btn" data-mode="manual" role="tab" aria-selected="false">직접 입력</button>' +
        '</div>' +
        '<span class="wdc-tf-hint">기본 구성 — 제품 선택 후 W/D/H 입력</span>' +
      '</div>' +
      '<section class="wdc-tf-card wdc-tf-card--base">' +
        '<h5 class="wdc-tf-card__title">기본 구성 <span class="wdc-tf-count" data-slot="basecount"></span></h5>' +
        '<div class="wdc-tf-grid" data-slot="basegrid"></div>' +
        '<div class="wdc-tf-addwrap">' +
          '<button type="button" class="wdc-tf-addrow" data-add="base"><i class="fas fa-plus" aria-hidden="true"></i> 구성 행 추가</button>' +
        '</div>' +
      '</section>' +
      '<div class="wdc-tf-row2">' +
        '<section class="wdc-tf-card wdc-tf-card--opt">' +
          '<h5 class="wdc-tf-card__title">추가 옵션 <span class="wdc-tf-count" data-slot="optcount"></span></h5>' +
          '<div class="wdc-tf-grid wdc-tf-grid--opt" data-slot="optgrid"></div>' +
          '<div class="wdc-tf-addwrap">' +
            '<button type="button" class="wdc-tf-addrow" data-add="opt"><i class="fas fa-plus" aria-hidden="true"></i> 옵션 추가</button>' +
          '</div>' +
        '</section>' +
        '<section class="wdc-tf-card wdc-tf-card--meta">' +
          '<h5 class="wdc-tf-card__title">쿠폰 · 배송 · 비고</h5>' +
          '<div class="wdc-tf-slot" data-slot="meta"></div>' +
        '</section>' +
      '</div>');
    mainScroll.appendChild(tfBody);
    var baseGridEl = tfBody.querySelector('[data-slot="basegrid"]');
    var optGridEl = tfBody.querySelector('[data-slot="optgrid"]');
    var metaSlot = tfBody.querySelector('[data-slot="meta"]');
    var baseCountEl = tfBody.querySelector('[data-slot="basecount"]');
    var optCountEl = tfBody.querySelector('[data-slot="optcount"]');
    var toggleBtns = tfBody.querySelectorAll('.wdc-tf-toggle__btn');
    var currentMode = 'select';   // 신규 base 행 기본 모드(토글 상태)

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
    // 저장 견적 오버레이(고객 견적 검색): rail + 백드롭.
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
    // 바텀시트 피커(제품·옵션 공용). 엔진 select 의 live <option> 복제.
    // ============================================================
    var sheet = el('div', 'wdc-tf-sheet',
      '<div class="wdc-tf-sheet__grip"></div>' +
      '<div class="wdc-tf-sheet__head"><span class="wdc-tf-sheet__title"></span>' +
        '<button type="button" class="wdc-tf-sheet__close" aria-label="닫기">✕</button></div>' +
      '<div class="wdc-tf-sheet__body" role="listbox"></div>');
    sheet.hidden = true;
    var sheetBackdrop = el('div', 'wdc-tf-sheet-backdrop');
    sheetBackdrop.hidden = true;
    document.body.appendChild(sheetBackdrop);
    document.body.appendChild(sheet);
    var sheetTitle = sheet.querySelector('.wdc-tf-sheet__title');
    var sheetBody = sheet.querySelector('.wdc-tf-sheet__body');

    function closeSheet() {
      sheet.hidden = true;
      sheetBackdrop.hidden = true;
      document.body.classList.remove('wdc-tf-sheet-open');
    }
    // 시트: title, 옵션[{value,label}], 현재값, pick 콜백.
    function openSheet(title, options, curValue, onPick) {
      sheetTitle.textContent = title || '선택';
      sheetBody.innerHTML = '';
      options.forEach(function (o) {
        var btn = el('button', 'wdc-tf-sheet__opt');
        btn.type = 'button';
        btn.setAttribute('role', 'option');
        btn.textContent = o.label;
        if (String(o.value) === String(curValue)) {
          btn.classList.add('is-selected');
          btn.setAttribute('aria-selected', 'true');
        }
        btn.addEventListener('click', function () {
          closeSheet();
          onPick(o.value, o.label);
        });
        sheetBody.appendChild(btn);
      });
      sheet.hidden = false;
      sheetBackdrop.hidden = false;
      document.body.classList.add('wdc-tf-sheet-open');
    }
    sheetBackdrop.addEventListener('click', closeSheet);
    sheet.querySelector('.wdc-tf-sheet__close').addEventListener('click', closeSheet);

    function optionsFromSelect(selectEl) {
      var out = [];
      if (!selectEl) { return out; }
      Array.prototype.forEach.call(selectEl.options, function (o) {
        out.push({ value: o.value, label: o.textContent });
      });
      return out;
    }

    // ============================================================
    // 표형 기본 구성 그리드 — 은닉 엔진 .base-component-row 와 1:1 미러.
    // ============================================================
    function engineBaseRows() {
      return baseContainer ? baseContainer.querySelectorAll('.base-component-row') : [];
    }
    function engineOptItems() {
      return optContainer ? optContainer.querySelectorAll('.additional-option-item') : [];
    }

    // 헤더(1회) — 그리드 재빌드 시 유지.
    function baseHeaderHtml() {
      return (
        '<div class="wdc-tf-grid__head" role="row">' +
          '<span class="wdc-tf-hcell wdc-tf-hcell--prod">제품 구성</span>' +
          '<span class="wdc-tf-hcell">W</span>' +
          '<span class="wdc-tf-hcell">D</span>' +
          '<span class="wdc-tf-hcell">H</span>' +
          '<span class="wdc-tf-hcell wdc-tf-hcell--price">단가</span>' +
          '<span class="wdc-tf-hcell wdc-tf-hcell--del"></span>' +
        '</div>'
      );
    }

    function productLabelFor(engineRow) {
      var sel = engineRow.querySelector('.base-product-select');
      if (sel && sel.value) {
        var opt = sel.options[sel.selectedIndex];
        if (opt && opt.textContent.trim()) { return opt.textContent.trim(); }
      }
      return '제품 선택';
    }

    function buildBaseRow(engineRow, idx) {
      var mode = engineRow.dataset.mode || 'select';
      var row = el('div', 'wdc-tf-grid__row');
      row.setAttribute('role', 'row');

      // (a) 제품/직접 셀.
      var prodCell;
      if (mode === 'manual') {
        var ptEl = engineRow.querySelector('.base-manual-pricing-type');
        var pt = (ptEl && ptEl.value) || '30cm';
        var priceSrc = engineRow.querySelector(pt === '1m' ? '.base-manual-price1m' : '.base-manual-price30');
        prodCell = el('input', 'wdc-tf-cell wdc-tf-cell--prodmanual');
        prodCell.type = 'text';
        prodCell.setAttribute('inputmode', 'numeric');
        prodCell.placeholder = (pt === '1m' ? '1m' : '30cm') + ' 단가';
        prodCell.value = (priceSrc && priceSrc.value) || '';
        prodCell.addEventListener('input', function () {
          if (priceSrc) { priceSrc.value = prodCell.value; fireInput(priceSrc); }
          refreshBasePrices();
        });
      } else {
        prodCell = el('button', 'wdc-tf-cell wdc-tf-cell--prod');
        prodCell.type = 'button';
        prodCell.innerHTML = '<span class="wdc-tf-prodlabel">' + escapeText(productLabelFor(engineRow)) +
          '</span><span class="wdc-tf-caret">▾</span>';
        prodCell.addEventListener('click', function () {
          var sel = engineRow.querySelector('.base-product-select');
          if (!sel) { return; }
          openSheet('제품 선택', optionsFromSelect(sel), sel.value, function (value) {
            sel.value = value;
            fireChange(sel);
            var lbl = prodCell.querySelector('.wdc-tf-prodlabel');
            if (lbl) { lbl.textContent = productLabelFor(engineRow); }
            refreshBasePrices();
          });
        });
      }
      row.appendChild(prodCell);

      // (b) W 셀 — 엔진 .base-width-input 그대로 미러(복합 규격 4120+4121 보존, 콤마 미변형).
      var widthInput = engineRow.querySelector('.base-width-input');
      var wCell = el('input', 'wdc-tf-cell wdc-tf-cell--num');
      wCell.type = 'text';
      wCell.setAttribute('inputmode', 'numeric');
      wCell.placeholder = 'W';
      wCell.value = (widthInput && widthInput.value) || '';
      wCell.addEventListener('input', function () {
        if (widthInput) { widthInput.value = wCell.value; fireInput(widthInput); }
        refreshBasePrices();
      });
      row.appendChild(wCell);

      // (c) D / H 셀 — 센티넬 추가금 미러.
      var dh = readRowDH(engineRow);
      var dCell = el('input', 'wdc-tf-cell wdc-tf-cell--num');
      dCell.type = 'text'; dCell.setAttribute('inputmode', 'numeric'); dCell.placeholder = 'D';
      dCell.value = dh.d;
      var hCell = el('input', 'wdc-tf-cell wdc-tf-cell--num');
      hCell.type = 'text'; hCell.setAttribute('inputmode', 'numeric'); hCell.placeholder = 'H';
      hCell.value = dh.h;
      function commitDH() {
        writeRowDH(engineRow, dCell.value.replace(/\D/g, ''), hCell.value.replace(/\D/g, ''));
      }
      dCell.addEventListener('input', commitDH);
      hCell.addEventListener('input', commitDH);
      row.appendChild(dCell);
      row.appendChild(hCell);

      // (d) 단가 셀 — READ-ONLY 계산 미러.
      var priceCell = el('span', 'wdc-tf-cell wdc-tf-cell--price');
      priceCell.setAttribute('data-price-idx', String(idx));
      priceCell.textContent = '0';
      row.appendChild(priceCell);

      // (e) ✕ 셀 — 엔진 삭제 위임.
      var delCell = el('button', 'wdc-tf-cell wdc-tf-cell--del');
      delCell.type = 'button';
      delCell.setAttribute('aria-label', '구성 행 삭제');
      delCell.textContent = '✕';
      delCell.addEventListener('click', function () {
        var rm = engineRow.querySelector('.base-remove-btn');
        if (rm) { rm.click(); }   // 엔진: 행 1개면 무시 → 옵저버가 재빌드
      });
      row.appendChild(delCell);

      return row;
    }

    function rebuildBaseGrid() {
      if (!baseGridEl) { return; }
      var rows = engineBaseRows();
      baseGridEl.innerHTML = baseHeaderHtml();
      Array.prototype.forEach.call(rows, function (engineRow, idx) {
        baseGridEl.appendChild(buildBaseRow(engineRow, idx));
      });
      if (baseCountEl) { baseCountEl.textContent = rows.length ? String(rows.length) : ''; }
      refreshBasePrices();
    }

    function refreshBasePrices() {
      if (!baseGridEl) { return; }
      var comps = readBaseComps();
      var cells = baseGridEl.querySelectorAll('[data-price-idx]');
      Array.prototype.forEach.call(cells, function (cell) {
        var i = Number(cell.getAttribute('data-price-idx'));
        var comp = comps[i];
        cell.textContent = comp ? fmtNum(computeCompPrice(comp)) : '0';
      });
    }

    // ============================================================
    // 표형 추가 옵션 그리드 — 은닉 .additional-option-item 와 1:1 미러.
    // ============================================================
    function optLabelFor(engineItem) {
      var nameInput = engineItem.querySelector('[data-option-name]');
      var nm = nameInput && (nameInput.value || '').trim();
      if (nm) { return nm; }
      var sel = engineItem.querySelector('[data-category-option-select]');
      if (sel && sel.value) {
        var opt = sel.options[sel.selectedIndex];
        if (opt && opt.textContent.trim()) { return opt.textContent.trim(); }
      }
      return '옵션 선택';
    }

    function buildOptRow(engineItem) {
      var row = el('div', 'wdc-tf-grid__row wdc-tf-grid__row--opt');
      row.setAttribute('role', 'row');

      // 옵션 셀(버튼 → 시트).
      var optCell = el('button', 'wdc-tf-cell wdc-tf-cell--prod');
      optCell.type = 'button';
      optCell.innerHTML = '<span class="wdc-tf-prodlabel">' + escapeText(optLabelFor(engineItem)) +
        '</span><span class="wdc-tf-caret">▾</span>';
      optCell.addEventListener('click', function () {
        var sel = engineItem.querySelector('[data-category-option-select]');
        if (!sel) { return; }
        openSheet('옵션 선택', optionsFromSelect(sel), sel.value, function (value) {
          sel.value = value;
          fireChange(sel);   // 엔진: name·price 자동 채움 + select 모드 전환
          setTimeout(function () {
            var lbl = optCell.querySelector('.wdc-tf-prodlabel');
            if (lbl) { lbl.textContent = optLabelFor(engineItem); }
            var priceSrc = engineItem.querySelector('[data-option-price]');
            if (priceSrc) { priceCell.value = priceSrc.value; }
          }, 0);
        });
      });
      row.appendChild(optCell);

      // 금액 셀 ↔ [data-option-price].
      var priceSrc = engineItem.querySelector('[data-option-price]');
      var priceCell = el('input', 'wdc-tf-cell wdc-tf-cell--num wdc-tf-cell--optprice');
      priceCell.type = 'text';
      priceCell.setAttribute('inputmode', 'numeric');
      priceCell.placeholder = '금액';
      priceCell.value = (priceSrc && priceSrc.value) || '';
      priceCell.addEventListener('input', function () {
        if (priceSrc) { priceSrc.value = priceCell.value; fireInput(priceSrc); }
      });
      row.appendChild(priceCell);

      // ✕ 셀.
      var delCell = el('button', 'wdc-tf-cell wdc-tf-cell--del');
      delCell.type = 'button';
      delCell.setAttribute('aria-label', '옵션 삭제');
      delCell.textContent = '✕';
      delCell.addEventListener('click', function () {
        var rm = engineItem.querySelector('.remove-option-btn');
        if (rm) { rm.click(); }
      });
      row.appendChild(delCell);

      return row;
    }

    function rebuildOptGrid() {
      if (!optGridEl) { return; }
      var items = engineOptItems();
      optGridEl.innerHTML = '';
      Array.prototype.forEach.call(items, function (engineItem) {
        optGridEl.appendChild(buildOptRow(engineItem));
      });
      if (optCountEl) { optCountEl.textContent = items.length ? String(items.length) : ''; }
    }

    function escapeText(s) {
      var d = document.createElement('div');
      d.textContent = String(s == null ? '' : s);
      return d.innerHTML;
    }

    // ============================================================
    // 방식 토글(선택/직접) — 전 base 행 모드 일괄 전환 + 신규 행 기본 모드.
    // ============================================================
    function setRowMode(engineRow, mode) {
      if ((engineRow.dataset.mode || 'select') === mode) { return; }
      var btn = engineRow.querySelector('.base-mode-btn[data-mode="' + mode + '"]');
      if (btn) { btn.click(); }   // 엔진 delegated 핸들러가 area 토글 + 재계산
    }
    function applyToggle(mode) {
      currentMode = mode;
      Array.prototype.forEach.call(toggleBtns, function (b) {
        var active = b.getAttribute('data-mode') === mode;
        b.classList.toggle('is-active', active);
        b.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      Array.prototype.forEach.call(engineBaseRows(), function (engineRow) {
        setRowMode(engineRow, mode);
      });
      // 모드 전환은 컨테이너 childList 변화가 아니므로 옵저버 미발화 → 명시 재빌드.
      rebuildBaseGrid();
    }
    Array.prototype.forEach.call(toggleBtns, function (b) {
      b.addEventListener('click', function () {
        applyToggle(b.getAttribute('data-mode'));
      });
    });

    // ============================================================
    // + 구성 행 추가 / + 옵션 추가.
    // ============================================================
    tfBody.addEventListener('click', function (e) {
      var addBtnEl = e.target.closest('.wdc-tf-addrow');
      if (!addBtnEl) { return; }
      var kind = addBtnEl.getAttribute('data-add');
      if (kind === 'base' && addBaseBtn) {
        addBaseBtn.click();   // 엔진 append(select 모드) → 옵저버 재빌드
        if (currentMode === 'manual') {
          setTimeout(function () {
            var rows = engineBaseRows();
            var last = rows.length ? rows[rows.length - 1] : null;
            if (last) { setRowMode(last, 'manual'); }
            rebuildBaseGrid();
          }, 0);
        }
      } else if (kind === 'opt' && addOptBtn) {
        addOptBtn.click();
      }
    });

    // ============================================================
    // 구조 변화 옵저버(행 추가/삭제/견적 로드 시 재빌드). childList 만 —
    // D/H 센티넬 등 서브트리 편집은 미발화(재빌드 클로버 방지).
    // ============================================================
    var baseObs = null;
    var optObs = null;
    function connectObservers() {
      if (window.MutationObserver) {
        if (baseContainer && !baseObs) {
          baseObs = new MutationObserver(function () { rebuildBaseGrid(); });
        }
        if (baseObs) { baseObs.observe(baseContainer, { childList: true }); }
        if (optContainer && !optObs) {
          optObs = new MutationObserver(function () { rebuildOptGrid(); });
        }
        if (optObs) { optObs.observe(optContainer, { childList: true }); }
      }
    }
    function disconnectObservers() {
      if (baseObs) { baseObs.disconnect(); }
      if (optObs) { optObs.disconnect(); }
    }

    // ============================================================
    // 미러 동기화(우측 패널 / 하단 바).
    // ============================================================
    function syncBarFinal() {
      var v = txt(finalPriceEl) || '0원';
      if (abValEl.textContent !== v) { abValEl.textContent = v; }
    }
    function syncPanel() {
      var totalEl = document.getElementById('totalAllFinalPrice');
      var tv = totalEl ? (txt(totalEl) || '0원') : '0원';
      if (totalTileEl.textContent !== tv) { totalTileEl.textContent = tv; }
      var cards = estContainer
        ? estContainer.querySelectorAll('.card[data-estimate-id]').length : 0;
      var name = custInput ? (custInput.value || '').trim() : '';
      var label = cards > 0 ? (name ? name + ' · ' + cards + '건' : cards + '건') : '';
      if (countEl.textContent !== label) { countEl.textContent = label; }
      var sb = document.getElementById('saveEstimateBtn');
      trpSaveBtn.disabled = !(sb && sb.style.display !== 'none');
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
    if (custInput) { custInput.addEventListener('input', syncPanel); }

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
      moveInto(couponGroup, metaSlot);
      moveInto(shipCostGroup, metaSlot);
      moveInto(shipInclGroup, metaSlot);
      moveInto(notesGroup, metaSlot);
      moveInto(estContainer, estSlot);
      moveInto(calcBtn, abActionsSlot);
      moveInto(addBtn, abActionsSlot);
      rebuildBaseGrid();
      rebuildOptGrid();
      connectObservers();
      syncBarFinal();
      syncPanel();
    }
    function undockFrame() {
      disconnectObservers();
      if (baseGridEl) { baseGridEl.innerHTML = ''; }
      if (optGridEl) { optGridEl.innerHTML = ''; }
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
      if (document.body.classList.contains('wd-builder')) { return; }
      if (shell.classList.contains('wdc-tablet-skin')) { return; }
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
      closeSheet();
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
