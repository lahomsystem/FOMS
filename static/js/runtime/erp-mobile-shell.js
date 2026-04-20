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

    var offcanvas = window.bootstrap.Offcanvas.getOrCreateInstance(drawer);
    drawer.querySelectorAll('a[href]').forEach(function (link) {
      link.addEventListener('click', function () {
        offcanvas.hide();
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    syncMobileShellNavHeight();
    initMobileDrawerLinks();
  });

  window.addEventListener('resize', syncMobileShellNavHeight);
})();
