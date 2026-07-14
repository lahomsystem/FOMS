/**
 * WDCalculator 태블릿 가로 표피(JS) — 2026-07-13.
 *
 * 목적(2): 태블릿 가로(coarse landscape ≥992)에서
 *   (1) 좌측 "저장된 견적" 패널을 기본 접힘(48px 세로 레일 토글)으로 두어 "견적 정보 입력"
 *       폼이 잔여 폭 전부를 쓰게 한다. 레일 탭 → 오버레이 펼침(재탭·백드롭 탭 = 접힘),
 *       상태는 localStorage 에 기억.
 *   (2) 하단에 고정 최종견적 바(.wdc-tablet-actionbar)를 두어 결과 카드의 최종가(#finalPrice)
 *       와 주 액션(견적 계산/추가)을 상시 노출한다(목업 frame11 "최종 견적은 하단 고정 바").
 *
 * 계약 무변경: 계산 엔진·DOM id·기존 이벤트 리스너를 일절 건드리지 않는다. 오직
 * `.wdcalculator-shell` 에 클래스(wdc-tablet-skin / wdc-saved-open)를 토글하고, 레일
 * 토글 버튼·백드롭·하단 바 요소만 주입한다(표피 전용). 하단 바는 계산엔진 노드를 이동/복제
 * 하지 않고 값(#finalPrice)·주 액션(calculateBtn/addEstimateBtn)만 MIRROR(관찰+클릭 위임)
 * 한다. 실제 레이아웃 전환·바 스타일은 tablet-skin.css 소관.
 *
 * 게이트: (min-width:992px) and (orientation:landscape) and (pointer:coarse) 且 비임베디드.
 * PC(fine hover)·모바일(≤991.98)·임베디드(erp-wdc-split.css 가 자체 오버레이 소유)는
 * matchMedia 로 배타 분리 — 게이트를 벗어나면 주입 클래스를 전부 제거해 무회귀.
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

    // --- 레일 토글 버튼 주입(사이드바 첫 자식). 접힘 시 노출되는 세로 탭. ---
    var rail = document.createElement('button');
    rail.type = 'button';
    rail.className = 'wdc-saved-rail';
    rail.setAttribute('aria-label', '저장된 견적 열기');
    rail.setAttribute('aria-expanded', 'false');
    rail.innerHTML =
      '<i class="fas fa-history" aria-hidden="true"></i>' +
      '<span class="wdc-saved-rail-label">저장된 견적</span>';
    sidebar.insertBefore(rail, sidebar.firstChild);

    // --- 백드롭 주입(펼침 시 바깥 탭 = 접힘). ---
    var backdrop = document.createElement('div');
    backdrop.className = 'wdc-saved-backdrop';
    backdrop.hidden = true;
    shell.appendChild(backdrop);

    // ============================================================
    // 하단 고정 최종견적 바(coarse-landscape 전용). 계산엔진 DOM 은 이동/복제하지 않고
    // #finalPrice 값과 주 액션(견적 계산/추가)만 MIRROR 한다(모바일 sticky mirror 패턴 재사용).
    // 실제 계산·CRUD 는 host 버튼 위임(.click()). 노출/은닉은 enableSkin/disableSkin 이
    // .wdc-actionbar-active 로 게이트(폰 wd-fab 와 MQ 배타 → 상호 배제).
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
    }

    function showActionBar() {
      actionBar.classList.add('wdc-actionbar-active');
      syncBarFinal();
      syncBarAction();
    }
    function hideActionBar() {
      actionBar.classList.remove('wdc-actionbar-active');
    }

    function isOpen() { return shell.classList.contains('wdc-saved-open'); }

    function setOpen(open) {
      shell.classList.toggle('wdc-saved-open', open);
      backdrop.hidden = !open;
      rail.setAttribute('aria-expanded', open ? 'true' : 'false');
      rail.setAttribute('aria-label', open ? '저장된 견적 닫기' : '저장된 견적 열기');
      try { localStorage.setItem(STORAGE_KEY, open ? '1' : '0'); } catch (e) { /* private mode */ }
    }

    function prefersOpen() {
      try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { return false; }
    }

    function enableSkin() {
      shell.classList.add('wdc-tablet-skin');
      setOpen(prefersOpen());   // 기본 접힘(저장값 없으면 collapsed)
      showActionBar();          // 하단 고정 최종견적 바 노출 + 값/액션 재동기화
    }

    function disableSkin() {
      // 게이트 이탈(PC/모바일/세로) — 주입 클래스 전부 제거해 원래 그리드 복원.
      shell.classList.remove('wdc-tablet-skin', 'wdc-saved-open');
      backdrop.hidden = true;
      rail.setAttribute('aria-expanded', 'false');
      hideActionBar();          // 게이트 이탈 시 바 은닉(PC/폰/세로 무영향)
    }

    rail.addEventListener('click', function () {
      if (!shell.classList.contains('wdc-tablet-skin')) { return; }
      setOpen(!isOpen());
    });
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
