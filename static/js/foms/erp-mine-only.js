/**
 * ERP global "내 담당/내 작업" filter — cookie SSOT + shell navigation decoration.
 * Loaded before erp-shell.js on /erp/* pages.
 */
(function () {
  'use strict';

  var COOKIE_NAME = 'erp_mine_only';
  var ERP_PREFIX = '/erp/';
  var ORDERS_DASHBOARD = '/erp/dashboard';

  function getCookie() {
    var match = document.cookie.match(/\berp_mine_only=([^;]*)/);
    return match ? (match[1] || '').trim() : '';
  }

  function setCookie(on) {
    var value = on ? '1' : '';
    var maxAge = on ? 60 * 60 * 24 * 30 : 0;
    document.cookie = COOKIE_NAME + '=' + value + '; path=/; max-age=' + maxAge + '; SameSite=Lax';
  }

  function isActive() {
    return getCookie() === '1';
  }

  function isErpPath(pathname) {
    return (pathname || '').indexOf(ERP_PREFIX) === 0;
  }

  /** True when orders dashboard URL is in drill/queue mode (mine must stay in query). */
  function ordersDashboardHasDrill(params) {
    return !!(
      params.get('q') ||
      params.get('stage') ||
      params.get('urgent') === '1' ||
      params.get('has_alert') === '1' ||
      params.get('alert_type') ||
      params.get('team') ||
      params.get('mine') === '1' ||
      params.get('today') === '1' ||
      params.get('date') ||
      params.get('risk') ||
      params.get('view') === 'queue' ||
      params.get('focus_order')
    );
  }

  /**
   * Apply global mine params to a same-origin ERP navigation URL.
   * @param {string} href
   * @returns {string}
   */
  function decorateShellUrl(href) {
    if (!href) {
      return href;
    }
    var u;
    try {
      u = new URL(href, window.location.origin);
    } catch (e) {
      return href;
    }
    if (u.origin !== window.location.origin || !isErpPath(u.pathname)) {
      return href;
    }
    if (u.searchParams.has('mine') && u.searchParams.get('mine') !== '1') {
      return href;
    }
    if (u.searchParams.has('tower_mine') && u.searchParams.get('tower_mine') !== '1') {
      return href;
    }
    if (isActive()) {
      if (u.pathname === ORDERS_DASHBOARD || u.pathname === ORDERS_DASHBOARD + '/') {
        if (ordersDashboardHasDrill(u.searchParams)) {
          u.searchParams.set('mine', '1');
        } else {
          u.searchParams.delete('mine');
          u.searchParams.set('tower_mine', '1');
        }
      } else {
        u.searchParams.set('mine', '1');
        u.searchParams.delete('tower_mine');
      }
    } else {
      u.searchParams.delete('mine');
      u.searchParams.delete('tower_mine');
    }
    return u.pathname + u.search + u.hash;
  }

  function updateGlobalButton(on) {
    var btn = document.getElementById('global-mine-only-btn');
    var icon = document.getElementById('global-mine-only-icon');
    if (btn) {
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    if (icon) {
      icon.style.color = on ? '#0d6efd' : '#6c757d';
    }
  }

  function updateMobileMytasksButton(on) {
    document.querySelectorAll('[data-foms-mytasks-toggle]').forEach(function (el) {
      el.classList.toggle('is-active', on);
      el.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  function syncChrome(on) {
    updateGlobalButton(on);
    updateMobileMytasksButton(on);
  }

  function dispatchChanged(on) {
    try {
      document.dispatchEvent(
        new CustomEvent('foms:erp-mine-only-changed', { detail: { active: !!on } })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function invalidateErpFragmentCache() {
    if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache === 'function') {
      window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache();
    }
    if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidateFragmentCache === 'function') {
      window.FOMS_ERP_SHELL.invalidateFragmentCache(true);
    }
  }

  function buildToggleUrl(on) {
    var path = window.location.pathname || '';
    var params = new URLSearchParams(window.location.search);
    if (on) {
      if (path === ORDERS_DASHBOARD || path === ORDERS_DASHBOARD + '/') {
        if (ordersDashboardHasDrill(params)) {
          params.set('mine', '1');
          params.delete('tower_mine');
        } else {
          params.delete('mine');
          params.set('tower_mine', '1');
        }
      } else if (isErpPath(path)) {
        params.set('mine', '1');
        params.delete('tower_mine');
      }
    } else {
      params.delete('mine');
      params.delete('tower_mine');
    }
    var qs = params.toString();
    return path + (qs ? '?' + qs : '') + (window.location.hash || '');
  }

  function refreshCurrentErpPage(on) {
    var path = window.location.pathname || '';
    if (!isErpPath(path)) {
      return;
    }
    var targetUrl = buildToggleUrl(on);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(window.history.state, '', targetUrl);
    }
    invalidateErpFragmentCache();
    if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.navigateByShell === 'function') {
      window.FOMS_ERP_SHELL.navigateByShell(targetUrl, { bypassCache: true });
      return;
    }
    window.location.href = targetUrl;
  }

  function toggleGlobalMineOnly() {
    var on = !isActive();
    setCookie(on);
    syncChrome(on);
    dispatchChanged(on);
    refreshCurrentErpPage(on);
  }

  function syncUrlFromCookieWithoutReload() {
    var path = window.location.pathname || '';
    if (!isErpPath(path)) {
      syncChrome(isActive());
      return;
    }
    var params = new URLSearchParams(window.location.search);
    var active = isActive();
    var needsMine = active && (
      (path !== ORDERS_DASHBOARD && path !== ORDERS_DASHBOARD + '/') ||
      ordersDashboardHasDrill(params)
    );
    var needsTower = active && (path === ORDERS_DASHBOARD || path === ORDERS_DASHBOARD + '/') && !ordersDashboardHasDrill(params);
    var hasMine = params.get('mine') === '1';
    var hasTower = params.get('tower_mine') === '1';
    if ((needsMine && !hasMine) || (needsTower && !hasTower) || (!active && (hasMine || hasTower))) {
      var synced = buildToggleUrl(active);
      if (window.history && window.history.replaceState) {
        window.history.replaceState(window.history.state, '', synced);
      }
    }
    syncChrome(active);
  }

  function installShellHooks() {
    if (!window.FOMS_ERP_SHELL || window.FOMS_ERP_SHELL._mineHookInstalled) {
      return;
    }
    var shell = window.FOMS_ERP_SHELL;
    var origNavigate = shell.navigateByShell;
    if (typeof origNavigate === 'function') {
      shell.navigateByShell = function (url, opts) {
        return origNavigate.call(this, decorateShellUrl(url), opts);
      };
    }
    var origPrefetch = shell.prefetchShellFragment;
    if (typeof origPrefetch === 'function') {
      shell.prefetchShellFragment = function (url) {
        return origPrefetch.call(this, decorateShellUrl(url));
      };
    }
    shell._mineHookInstalled = true;
  }

  function onAnchorMineSync(ev) {
    var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
    if (!a || a.hasAttribute('data-foms-erp-no-shell')) {
      return;
    }
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#') {
      return;
    }
    var u;
    try {
      u = new URL(href, window.location.origin);
    } catch (e) {
      return;
    }
    if (!isErpPath(u.pathname)) {
      return;
    }
    var nextActive = null;
    if (u.searchParams.get('mine') === '1' || u.searchParams.get('tower_mine') === '1') {
      nextActive = true;
    } else if (
      (u.searchParams.has('mine') && u.searchParams.get('mine') !== '1') ||
      (u.searchParams.has('tower_mine') && u.searchParams.get('tower_mine') !== '1')
    ) {
      nextActive = false;
    }
    if (nextActive === null || nextActive === isActive()) {
      return;
    }
    setCookie(nextActive);
    syncChrome(nextActive);
    dispatchChanged(nextActive);
    invalidateErpFragmentCache();
  }

  function onMytasksClick(ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest('[data-foms-mytasks-toggle]') : null;
    if (!el) {
      return;
    }
    ev.preventDefault();
    toggleGlobalMineOnly();
  }

  function boot() {
    syncUrlFromCookieWithoutReload();
    installShellHooks();
    document.addEventListener('click', onAnchorMineSync, true);
    document.addEventListener('click', onMytasksClick, true);
    window.setTimeout(installShellHooks, 0);
  }

  window.getErpMineOnlyCookie = getCookie;
  window.setErpMineOnlyCookie = setCookie;
  window.toggleGlobalMineOnly = toggleGlobalMineOnly;

  window.FOMS_ERP_MINE_ONLY = {
    COOKIE_NAME: COOKIE_NAME,
    getCookie: getCookie,
    setCookie: setCookie,
    isActive: isActive,
    decorateShellUrl: decorateShellUrl,
    toggle: toggleGlobalMineOnly,
    syncChrome: syncChrome,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
