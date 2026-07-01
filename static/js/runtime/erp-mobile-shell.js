(function () {
  function syncMobileShellNavHeight() {
    var nav = document.querySelector('.erp-mobile-bottom-nav');
    if (!nav) {
      return;
    }

    document.documentElement.style.setProperty('--erp-mobile-shell-nav-height', nav.offsetHeight + 'px');
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
