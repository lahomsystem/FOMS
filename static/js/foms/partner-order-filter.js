/** Rebuild persistent header links against the current ERP shell location. */
(function () {
  'use strict';
  if (window.__FOMS_PARTNER_FILTER_BOUND) return;
  window.__FOMS_PARTNER_FILTER_BOUND = true;

  var paths = ['/', '/erp/dashboard', '/erp/dashboard/', '/erp/history/'];
  var resetKeys = ['page', 'order', 'focus_order', 'view', 'mobile_chunk', 'from_history', 'from_dashboard'];

  function refreshLinks() {
    var supported = paths.indexOf(window.location.pathname) !== -1;
    var path = supported ? window.location.pathname : '/erp/dashboard';
    var params = new URLSearchParams(supported ? window.location.search : '');
    resetKeys.forEach(function (key) { params.delete(key); });
    document.querySelectorAll('[data-foms-partner-choice]').forEach(function (link) {
      params.set('partner_org', link.getAttribute('data-foms-partner-choice'));
      link.setAttribute('href', path + '?' + params.toString());
    });
  }

  document.addEventListener('show.bs.dropdown', function (event) {
    if (event.target.id === 'global-partner-filter-btn') refreshLinks();
  });
  document.addEventListener('click', function (event) {
    if (event.target.closest('[data-foms-partner-choice]')) refreshLinks();
  }, true);
})();
