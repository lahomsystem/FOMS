(function () {
  var NAV_HEIGHT_VAR = '--erp-mobile-shell-nav-height';
  var wideMq = window.matchMedia ? window.matchMedia('(min-width: 992px)') : null;
  var coarseMq = window.matchMedia ? window.matchMedia('(pointer: coarse)') : null;

  // 광폭 마우스 PC 인가 — shipment-dashboard.js 의 isWideMousePc 와 같은 식(서버
  // feature_flags.wants_mobile_width_surfaces 가 False 를 내는 조건). matchMedia 가 없으면 아니라고 본다.
  function isWideMousePc() {
    if (!wideMq || !coarseMq) return false;
    return !coarseMq.matches && wideMq.matches;
  }

  // 값이 같으면 다시 쓰지 않는다 — :root 변수를 쓰면 문서 전체 스타일이 다시 계산된다.
  function writeNavHeight(value) {
    var rootStyle = document.documentElement.style;
    if (rootStyle.getPropertyValue(NAV_HEIGHT_VAR) === value) {
      return;
    }
    rootStyle.setProperty(NAV_HEIGHT_VAR, value);
  }

  // ResizeObserver 가 없는 브라우저만 쓰는 옛 길 — 부를 때마다 offsetHeight 로 잰다.
  function syncMobileShellNavHeight() {
    var nav = document.querySelector('.erp-mobile-bottom-nav');
    if (!nav) {
      return;
    }

    // 광폭 마우스 PC 에서는 하단 탭을 감싼 .erp-mobile-shell-chrome 이 늘 숨어 있어
    // (10-erp-mobile-v2-shell.css 의 992+ fine/none 규칙 display:none) 높이가 0 이다.
    // offsetHeight 를 읽으면 그 값을 얻으려고 레이아웃을 강제로 한 번 더 돌리므로 0px 을 바로 쓴다
    // (2026-10-01 성능 원장 P3-8).
    writeNavHeight(isWideMousePc() ? '0px' : nav.offsetHeight + 'px');
  }

  // 아래 탭 높이는 ResizeObserver 가 높이가 바뀔 때만 알려 준다(11-16). 예전엔 조각 교체마다 offsetHeight 를 읽어
  // 큰 조각(AS 814KB)을 끼운 직후 강제 레이아웃이 4배 CPU 0.98초 걸렸다. 교체로 아래 탭 요소가 바뀌면 관찰 대상만 바꾼다 —
  // 새 대상의 첫 알림이 첫 값을 쓴다(첫 그림 전, 레이아웃이 끝난 뒤라 따로 재지 않는다).
  var navObserver = null;
  var observedNav = null;

  function onNavResize(entries) {
    var entry = entries[entries.length - 1];
    if (!entry || entry.target !== observedNav) {
      return;
    }
    if (isWideMousePc()) {
      writeNavHeight('0px');
      return;
    }
    var box = entry.borderBoxSize && entry.borderBoxSize[0];
    var height = box ? box.blockSize : entry.target.offsetHeight;
    writeNavHeight(Math.round(height) + 'px');
  }

  function observeMobileShellNav() {
    var nav = document.querySelector('.erp-mobile-bottom-nav');
    if (nav === observedNav) {
      return;
    }
    if (observedNav) {
      navObserver.unobserve(observedNav);
    }
    observedNav = nav;
    if (nav) {
      navObserver.observe(nav);
    }
  }

  function initMobileDrawerLinks() {
    var drawer = document.getElementById('erp-mobile-menu-drawer');
    if (!drawer || !window.bootstrap || !window.bootstrap.Offcanvas) {
      return;
    }
    if (drawer.dataset.fomsDrawerLinksBound === '1') {
      return;
    }
    drawer.dataset.fomsDrawerLinksBound = '1';

    var offcanvas = window.bootstrap.Offcanvas.getOrCreateInstance(drawer);
    drawer.querySelectorAll('a[href]').forEach(function (link) {
      link.addEventListener('click', function () {
        offcanvas.hide();
      });
    });
  }

  // 뒤로 단추는 셸 첫 누름 스크립트(erp_mobile_early_tap.html)가 문서 위임으로 맡는다 — 화면이 보이자마자 먹게(11-16).
  // 그 스크립트가 없는 문서(배포 직후 옛 HTML)에서만 여기서 단추마다 묶는다.
  function initMobileShellBackButtons() {
    if (window.__FOMS_EARLY_TAP_BOUND) {
      return;
    }
    document.querySelectorAll('[data-foms-shell-back]').forEach(function (btn) {
      if (btn.dataset.fomsShellBackBound === '1') {
        return;
      }
      btn.dataset.fomsShellBackBound = '1';
      btn.addEventListener('click', function () {
        var fallbackHref = (btn.getAttribute('data-foms-shell-back-href') || '').trim();
        if (window.history && window.history.length > 1) {
          window.history.back();
          return;
        }
        if (fallbackHref) {
          window.location.href = fallbackHref;
          return;
        }
        if (document.referrer) {
          window.location.href = document.referrer;
          return;
        }
        window.location.href = '/erp/dashboard';
      });
    });
  }

  function initMobileShell() {
    if (navObserver) {
      observeMobileShellNav();
    } else {
      syncMobileShellNavHeight();
    }
    initMobileDrawerLinks();
    initMobileShellBackButtons();
  }

  if (window.__ERP_MOBILE_SHELL_BOUND) return;
  window.__ERP_MOBILE_SHELL_BOUND = true;

  if (typeof window.ResizeObserver === 'function') {
    navObserver = new window.ResizeObserver(onNavResize);
  }

  document.addEventListener('DOMContentLoaded', initMobileShell);
  document.addEventListener('foms:main-content-swapped', initMobileShell);
  if (!navObserver) {
    window.addEventListener('resize', syncMobileShellNavHeight);
  }
})();
