/**
 * 출고 패킹 체크리스트 (B6).
 * 카드의 [data-foms-packing-trigger] 클릭 → 바텀시트 열고 GET 로드 →
 * 체크/항목 추가는 POST → 카운터·배지 갱신.
 * fragment 재실행 시 리스너 중복 바인딩 방지: window.__FOMS_PACKING_BOUND 싱글톤.
 */
(function () {
  'use strict';

  if (window.__FOMS_PACKING_BOUND) return;
  window.__FOMS_PACKING_BOUND = true;

  var state = { orderId: null, trigger: null, items: [] };

  function sheetEl() {
    return document.querySelector('[data-foms-packing-sheet]');
  }

  function q(root, sel) {
    return root ? root.querySelector(sel) : null;
  }

  function getSheetInstance(el) {
    if (!el || typeof bootstrap === 'undefined' || !bootstrap.Offcanvas) return null;
    return bootstrap.Offcanvas.getOrCreateInstance(el);
  }

  function setError(el, message) {
    var box = q(el, '[data-foms-packing-error]');
    if (!box) return;
    box.textContent = message || '';
    box.classList.toggle('d-none', !message);
  }

  function setLoading(el, isLoading) {
    var loader = q(el, '[data-foms-packing-loading]');
    if (loader) loader.hidden = !isLoading;
  }

  function apiUrl(orderId) {
    return '/api/erp/shipment/packing/' + encodeURIComponent(orderId);
  }

  function updateBadge(trigger, checked, total) {
    if (!trigger) return;
    var badge = trigger.querySelector('[data-foms-packing-badge]');
    if (!badge) return;
    badge.textContent = checked + '/' + total;
    badge.hidden = total === 0;
    badge.classList.toggle('foms-packing-badge--done', total > 0 && checked === total);
  }

  function renderSummary(el, checked, total) {
    var count = q(el, '[data-foms-packing-count]');
    if (count) count.textContent = checked + ' / ' + total;
    var done = q(el, '[data-foms-packing-done]');
    if (done) done.hidden = !(total > 0 && checked === total);
  }

  function rowMeta(item) {
    if (!item.checked || !item.by_name) return '';
    var when = '';
    if (item.at) {
      var d = new Date(item.at);
      if (!isNaN(d.getTime())) {
        when = ' · ' + d.toLocaleDateString('ko-KR') + ' ' +
          d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
      }
    }
    return item.by_name + when;
  }

  function renderRows(el, items) {
    var list = q(el, '[data-foms-packing-list]');
    if (!list) return;
    list.textContent = '';
    items.forEach(function (item) {
      var li = document.createElement('li');
      li.className = 'foms-packing-row' + (item.checked ? ' foms-packing-row--checked' : '');
      li.dataset.key = item.key;

      var input = document.createElement('input');
      input.type = 'checkbox';
      input.className = 'foms-packing-row__check';
      input.checked = !!item.checked;
      input.setAttribute('data-foms-packing-check', '');
      input.setAttribute('aria-label', item.label);

      var body = document.createElement('div');
      body.className = 'foms-packing-row__body';
      var label = document.createElement('span');
      label.className = 'foms-packing-row__label';
      label.textContent = item.label;
      body.appendChild(label);
      var metaText = rowMeta(item);
      if (metaText) {
        var meta = document.createElement('span');
        meta.className = 'foms-packing-row__meta';
        meta.textContent = metaText;
        body.appendChild(meta);
      }

      var qty = document.createElement('span');
      qty.className = 'foms-packing-row__qty';
      qty.textContent = '×' + (item.qty || 1);

      li.appendChild(input);
      li.appendChild(body);
      li.appendChild(qty);
      list.appendChild(li);
    });
  }

  function applyData(el, data) {
    state.items = Array.isArray(data.items) ? data.items : [];
    var total = typeof data.total === 'number' ? data.total : state.items.length;
    var checked = typeof data.checked_count === 'number'
      ? data.checked_count
      : state.items.filter(function (it) { return it.checked; }).length;
    renderRows(el, state.items);
    renderSummary(el, checked, total);
    updateBadge(state.trigger, checked, total);
  }

  async function request(orderId, options) {
    var res = await fetch(apiUrl(orderId), Object.assign({
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }, options || {}));
    var data = await res.json().catch(function () { return {}; });
    if (!res.ok || !data.success) {
      throw new Error(data.error || data.message || '요청에 실패했습니다.');
    }
    return data.data || {};
  }

  async function loadPacking(orderId) {
    var el = sheetEl();
    if (!el) return;
    setError(el, '');
    setLoading(el, true);
    try {
      var data = await request(orderId, { method: 'GET' });
      applyData(el, data);
    } catch (error) {
      setError(el, String((error && error.message) || error));
    } finally {
      setLoading(el, false);
    }
  }

  async function postPacking(payload) {
    var el = sheetEl();
    if (!el || !state.orderId) return;
    setError(el, '');
    try {
      var data = await request(state.orderId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify(payload)
      });
      applyData(el, data);
      return true;
    } catch (error) {
      setError(el, String((error && error.message) || error));
      return false;
    }
  }

  function openSheet(trigger) {
    var orderId = trigger.dataset.orderId;
    if (!orderId) return;
    state.orderId = orderId;
    state.trigger = trigger;
    var el = sheetEl();
    if (el) {
      var sub = q(el, '[data-foms-packing-subtitle]');
      if (sub) sub.textContent = '주문 #' + orderId + ' · 제품별 패킹 항목을 체크하세요.';
      var list = q(el, '[data-foms-packing-list]');
      if (list) list.textContent = '';
      var instance = getSheetInstance(el);
      if (instance) instance.show();
    }
    loadPacking(orderId);
  }

  document.addEventListener('click', function (event) {
    var trigger = event.target.closest('[data-foms-packing-trigger]');
    if (trigger) {
      event.preventDefault();
      openSheet(trigger);
    }
  });

  document.addEventListener('change', function (event) {
    var check = event.target.closest('[data-foms-packing-check]');
    if (!check) return;
    var row = check.closest('.foms-packing-row');
    if (!row) return;
    var key = row.dataset.key;
    var checked = check.checked;
    row.classList.toggle('foms-packing-row--checked', checked);
    postPacking({ updates: [{ key: key, checked: checked }] }).then(function (ok) {
      if (!ok) check.checked = !checked;
    });
  });

  document.addEventListener('submit', function (event) {
    var form = event.target.closest('[data-foms-packing-add]');
    if (!form) return;
    event.preventDefault();
    var labelInput = form.querySelector('[name="label"]');
    var qtyInput = form.querySelector('[name="qty"]');
    var label = labelInput ? labelInput.value.trim() : '';
    if (!label) {
      if (labelInput) labelInput.focus();
      return;
    }
    var qty = qtyInput ? parseInt(qtyInput.value, 10) : 1;
    if (!qty || qty < 1) qty = 1;
    postPacking({ add: { label: label, qty: qty } }).then(function (ok) {
      if (ok && labelInput) {
        labelInput.value = '';
        if (qtyInput) qtyInput.value = '1';
        labelInput.focus();
      }
    });
  });
})();
