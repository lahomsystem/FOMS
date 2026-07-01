/**
 * ERP Order — 제품 항목 Master-Detail (PC erp_order_tab.html).
 * 좌측 rail + 우측 단일 .erp-item-row 표시. 저장/수집 호환을 위해 모든 행은 #erp-items에 유지.
 */
(function () {
  'use strict';

  if (window.__ERP_ITEMS_MD_BOUND) return;
  window.__ERP_ITEMS_MD_BOUND = true;

  var selectedIdx = 0;
  var searchQuery = '';

  function shell() {
    return document.querySelector('.erp-items-master-detail-shell');
  }

  function isActive() {
    return !!shell() && typeof erpIsMobileFormContext === 'function' && !erpIsMobileFormContext();
  }

  function rows() {
    return typeof erpGetItemRows === 'function' ? erpGetItemRows() : [];
  }

  function railListEl() {
    return document.getElementById('erp-md-rail-list');
  }

  function clampIndex(idx) {
    var list = rows();
    if (!list.length) return 0;
    return Math.max(0, Math.min(idx, list.length - 1));
  }

  function rowSpecText(row) {
    if (!row) return '';
    var firstSpec = row.querySelector('.erp-spec-row');
    if (!firstSpec) return '';
    var w = String(firstSpec.querySelector('[data-erp="spec_width"]')?.value || '').trim();
    var d = String(firstSpec.querySelector('[data-erp="spec_depth"]')?.value || '').trim();
    var h = String(firstSpec.querySelector('[data-erp="spec_height"]')?.value || '').trim();
    return [w, d, h].filter(Boolean).join('×');
  }

  function rowPriceText(row) {
    if (!row) return '';
    var digits = String(row.querySelector('[data-erp="price"]')?.value || '').replace(/[^0-9]/g, '');
    if (!digits) return '';
    return typeof erpFormatMoneyKRW === 'function'
      ? erpFormatMoneyKRW(parseInt(digits, 10))
      : digits + '원';
  }

  function rowStatus(row) {
    if (!row) return 'empty';
    var name = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim();
    var price = String(row.querySelector('[data-erp="price"]')?.value || '').replace(/[^0-9]/g, '');
    var w = String(row.querySelector('[data-erp="spec_width"]')?.value || '').trim();
    if (!name) return 'empty';
    if (name && price && w) return 'done';
    return 'partial';
  }

  function rowIsEmpty(row) {
    if (!row) return true;
    var name = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim();
    if (name) return false;
    if (rowSpecText(row)) return false;
    var price = String(row.querySelector('[data-erp="price"]')?.value || '').replace(/[^0-9]/g, '');
    return !price;
  }

  function shouldShowEmptyState(list) {
    return list.length === 1 && rowIsEmpty(list[0]) && !searchQuery.trim();
  }

  function emptyStateHtml() {
    return (
      '<div class="item-rail__empty" role="presentation">' +
      '<div class="item-rail__empty-icon" aria-hidden="true"><i class="fas fa-couch"></i></div>' +
      '<p class="item-rail__empty-title">첫 항목을 입력하세요</p>' +
      '<p class="item-rail__empty-hint">오른쪽에서 제품명·규격을 입력하거나<br>상단 <strong>+ 항목</strong>으로 추가합니다</p>' +
      '</div>'
    );
  }

  function pipClass(status) {
    if (status === 'done') return 'status-pip--done';
    if (status === 'partial') return 'status-pip--partial';
    return 'status-pip--empty';
  }

  function syncRailHeight() {
    if (!isActive()) return;
    var rail = shell()?.querySelector('.item-rail');
    var detail = shell()?.querySelector('.item-detail');
    if (!rail || !detail) return;
    var h = detail.offsetHeight;
    if (h > 0) rail.style.minHeight = h + 'px';
  }

  function syncRailTotal() {
    var totalEl = document.getElementById('erp-items-total');
    var railTotal = document.getElementById('erp-md-rail-total');
    if (totalEl && railTotal) {
      railTotal.textContent = totalEl.textContent || '0원';
    }
  }

  function syncNavPos() {
    var navPos = document.getElementById('erp-md-nav-pos');
    var list = rows();
    if (navPos) {
      navPos.textContent = list.length ? (selectedIdx + 1) + ' / ' + list.length : '0 / 0';
    }
    var countEl = document.getElementById('erp-md-rail-count');
    if (countEl) countEl.textContent = String(list.length);
  }

  function applyVisibility() {
    if (!isActive()) return;
    var list = rows();
    list.forEach(function (row, i) {
      row.classList.toggle('erp-item-row--md-hidden', i !== selectedIdx);
    });
    var active = list[selectedIdx];
    if (active && typeof erpBindAutosizeTextareas === 'function') {
      erpBindAutosizeTextareas(active);
    }
  }

  function renderRail() {
    if (!isActive()) return;
    var listEl = railListEl();
    if (!listEl) return;
    var list = rows();
    listEl.innerHTML = '';
    var q = searchQuery.trim().toLowerCase();

    if (shouldShowEmptyState(list)) {
      listEl.classList.add('is-empty-state');
      listEl.innerHTML = emptyStateHtml();
      syncNavPos();
      syncRailTotal();
      syncRailHeight();
      return;
    }

    listEl.classList.remove('is-empty-state');

    list.forEach(function (row, i) {
      var nameRaw = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim();
      var isEmpty = rowIsEmpty(row);
      var name = nameRaw || '미입력';
      var spec = rowSpecText(row);
      var price = rowPriceText(row);
      var status = rowStatus(row);
      var filtered = q && nameRaw.toLowerCase().indexOf(q) === -1;

      var el = document.createElement('div');
      el.className =
        'rail-item' +
        (i === selectedIdx ? ' is-selected' : '') +
        (filtered ? ' is-filtered-out' : '') +
        (isEmpty ? ' rail-item--ghost' : '');
      el.setAttribute('role', 'option');
      el.setAttribute('aria-selected', i === selectedIdx ? 'true' : 'false');
      el.dataset.itemIndex = String(i);

      var specHtml = spec ? '<span class="rail-item__spec">' + escapeHtml(spec) + '</span>' : '';
      var pipHtml = isEmpty ? '' : '<span class="status-pip ' + pipClass(status) + '"></span>';
      var priceHtml = price ? '<span class="rail-item__price">' + escapeHtml(price) + '</span>' : '';

      el.innerHTML =
        '<span class="rail-item__index">' + (i + 1) + '</span>' +
        '<div class="rail-item__main">' +
        '<span class="rail-item__name">' + escapeHtml(name) + '</span>' +
        specHtml +
        '</div>' +
        '<div class="rail-item__right">' + pipHtml + priceHtml + '</div>';

      el.addEventListener('click', function () {
        selectItem(i);
      });
      listEl.appendChild(el);
    });

    syncNavPos();
    syncRailTotal();
    syncRailHeight();
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function selectItem(idx) {
    if (!isActive()) return;
    var list = rows();
    if (!list.length) {
      selectedIdx = 0;
      renderRail();
      return;
    }
    selectedIdx = clampIndex(idx);
    applyVisibility();
    renderRail();
    var sel = railListEl()?.querySelector('.rail-item.is-selected');
    if (sel) sel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function refresh() {
    if (!isActive()) return;
    selectedIdx = clampIndex(selectedIdx);
    applyVisibility();
    renderRail();
  }

  function afterRemove(removedIndex) {
    if (!isActive()) return;
    var list = rows();
    if (!list.length) {
      selectedIdx = 0;
    } else if (removedIndex <= selectedIdx) {
      selectedIdx = Math.max(0, selectedIdx - 1);
    }
    refresh();
  }

  function bindHeightSync() {
    if (window.__ERP_ITEMS_MD_HEIGHT_OBS) return;
    var detail = shell()?.querySelector('.item-detail');
    if (!detail || typeof ResizeObserver === 'undefined') return;
    window.__ERP_ITEMS_MD_HEIGHT_OBS = new ResizeObserver(function () {
      syncRailHeight();
    });
    window.__ERP_ITEMS_MD_HEIGHT_OBS.observe(detail);
  }

  function bindControls() {
    var root = shell();
    if (!root || root.dataset.erpMdControlsBound === '1') return;
    root.dataset.erpMdControlsBound = '1';

    document.getElementById('erp-md-rail-add-item')?.addEventListener('click', function () {
      document.getElementById('erp-add-item-btn')?.click();
    });

    document.getElementById('erp-md-rail-search')?.addEventListener('input', function (e) {
      searchQuery = e.target.value || '';
      renderRail();
    });

    document.getElementById('erp-md-btn-prev')?.addEventListener('click', function () {
      selectItem(selectedIdx - 1);
    });

    document.getElementById('erp-md-btn-next')?.addEventListener('click', function () {
      var list = rows();
      if (selectedIdx < list.length - 1) selectItem(selectedIdx + 1);
      else selectItem(0);
    });

    document.getElementById('erp-md-rail-summary-btn')?.addEventListener('click', function () {
      var lines = rows().map(function (row, i) {
        var name = String(row.querySelector('[data-erp="product_name"]')?.value || '').trim() || '(미입력)';
        return (i + 1) + '. ' + name + ' · ' + (rowSpecText(row) || '—') + ' · ' + (rowPriceText(row) || '—');
      });
      if (lines.length && typeof window.alert === 'function') {
        window.alert('전체 항목 요약\n\n' + lines.join('\n'));
      }
    });
  }

  function bindKeyboard() {
    if (window.__ERP_ITEMS_MD_KEYDOWN) return;
    window.__ERP_ITEMS_MD_KEYDOWN = true;
    document.addEventListener('keydown', function (e) {
      if (!isActive()) return;
      var tag = (e.target && e.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) return;
      if (!e.ctrlKey) return;
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectItem(selectedIdx - 1);
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectItem(selectedIdx + 1);
      }
    });
  }

  function init() {
    if (!shell()) return;
    if (typeof erpIsMobileFormContext === 'function' && erpIsMobileFormContext()) return;
    bindControls();
    bindKeyboard();
    bindHeightSync();
    selectedIdx = 0;
    refresh();
  }

  window.ErpItemsMasterDetail = {
    isActive: isActive,
    init: init,
    refresh: refresh,
    selectItem: selectItem,
    afterRemove: afterRemove,
    syncRailTotal: syncRailTotal,
    syncRailHeight: syncRailHeight
  };

  function tryInit() {
    setTimeout(init, 0);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInit);
  } else {
    tryInit();
  }
  document.addEventListener('foms:main-content-swapped', tryInit);
})();
