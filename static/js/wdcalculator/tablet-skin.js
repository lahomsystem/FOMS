/**
 * WDCalculator 태블릿 가로 표피(JS) — 2026-07-13.
 *
 * 목적: 태블릿 가로(coarse landscape ≥992)에서 좌측 "저장된 견적" 패널을 기본 접힘
 * (48px 세로 레일 토글)으로 두어 "견적 정보 입력" 폼이 잔여 폭 전부를 쓰게 한다.
 * 레일을 탭하면 패널이 오버레이로 펼쳐지고(재탭·백드롭 탭 = 접힘), 상태는 localStorage
 * 에 기억한다.
 *
 * 계약 무변경: 계산 엔진·DOM id·기존 이벤트 리스너를 일절 건드리지 않는다. 오직
 * `.wdcalculator-shell` 에 클래스(wdc-tablet-skin / wdc-saved-open)를 토글하고, 레일
 * 토글 버튼·백드롭 요소만 주입한다(표피 전용). 실제 레이아웃 전환은 tablet-skin.css 소관.
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
    }

    function disableSkin() {
      // 게이트 이탈(PC/모바일/세로) — 주입 클래스 전부 제거해 원래 그리드 복원.
      shell.classList.remove('wdc-tablet-skin', 'wdc-saved-open');
      backdrop.hidden = true;
      rail.setAttribute('aria-expanded', 'false');
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
