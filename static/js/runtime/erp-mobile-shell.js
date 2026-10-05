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

  function syncMobileShellNavHeight() {
    var nav = document.querySelector('.erp-mobile-bottom-nav');
    if (!nav) {
      return;
    }

    // 광폭 마우스 PC 에서는 하단 탭을 감싼 .erp-mobile-shell-chrome 이 늘 숨어 있어
    // (10-erp-mobile-v2-shell.css 의 992+ fine/none 규칙 display:none) 높이가 0 이다.
    // offsetHeight 를 읽으면 그 값을 얻으려고 레이아웃을 강제로 한 번 더 돌리므로 0px 을 바로 쓴다
    // (2026-10-01 성능 원장 P3-8). 값이 같으면 다시 쓰지 않는다 — :root 변수를 쓰면 문서 전체 스타일이 다시 계산된다.
    var value = isWideMousePc() ? '0px' : nav.offsetHeight + 'px';
    var rootStyle = document.documentElement.style;
    if (rootStyle.getPropertyValue(NAV_HEIGHT_VAR) === value) {
      return;
    }
    rootStyle.setProperty(NAV_HEIGHT_VAR, value);
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

  function initMobileShellBackButtons() {
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
    syncMobileShellNavHeight();
    initMobileDrawerLinks();
    initMobileShellBackButtons();
  }

  if (window.__ERP_MOBILE_SHELL_BOUND) return;
  window.__ERP_MOBILE_SHELL_BOUND = true;

  document.addEventListener('DOMContentLoaded', initMobileShell);
  document.addEventListener('foms:main-content-swapped', initMobileShell);
  window.addEventListener('resize', syncMobileShellNavHeight);
})();
