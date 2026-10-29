/** Rebuild persistent header links against the current ERP shell location. */
(function () {
  'use strict';
  if (window.__FOMS_PARTNER_FILTER_BOUND) return;
  window.__FOMS_PARTNER_FILTER_BOUND = true;

  var paths = ['/', '/erp/dashboard', '/erp/dashboard/', '/erp/measurement', '/erp/drawing-workbench',
    '/erp/production/dashboard', '/erp/shipment', '/erp/as', '/erp/construction/dashboard',
    '/erp/completion', '/erp/settlement', '/erp/history/'];
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
    if (event.target.closest('[data-foms-partner-open]')) openMobileSheet();
  }, true);

  function openMobileSheet() {
    refreshLinks();
    var sheet = document.getElementById('foms-partner-filter-sheet');
    if (!sheet) {
      sheet = document.createElement('div');
      sheet.id = 'foms-partner-filter-sheet';
      sheet.className = 'offcanvas offcanvas-bottom foms-partner-filter-sheet';
      sheet.tabIndex = -1;
      sheet.setAttribute('aria-labelledby', 'foms-partner-filter-sheet-title');
      var header = document.createElement('div');
      header.className = 'offcanvas-header';
      var title = document.createElement('h2');
      title.id = 'foms-partner-filter-sheet-title';
      title.className = 'offcanvas-title h5';
      title.textContent = '협력사 주문 보기';
      var close = document.createElement('button');
      close.type = 'button';
      close.className = 'btn-close';
      close.setAttribute('data-bs-dismiss', 'offcanvas');
      close.setAttribute('aria-label', '닫기');
      header.append(title, close);
      var body = document.createElement('div');
      body.className = 'offcanvas-body';
      var list = document.createElement('div');
      list.className = 'list-group';
      document.querySelectorAll('header.layout-header [data-foms-partner-choice]').forEach(function (link) {
        var choice = link.cloneNode(true);
        choice.className = 'list-group-item list-group-item-action' + (link.classList.contains('active') ? ' active' : '');
        list.appendChild(choice);
      });
      body.appendChild(list);
      sheet.append(header, body);
      document.body.appendChild(sheet);
    }
    window.bootstrap.Offcanvas.getOrCreateInstance(sheet).show();
  }
})();
