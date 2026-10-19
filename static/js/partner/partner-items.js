/**
 * PARTNER-FOMS 1단계: 협력사 새 주문의 제품 항목 입력 — 우리 주문 화면과 같은 칸.
 *
 * - 제품마다 규격 여러 줄(spec_rows), 복합 폭은 글자 그대로(예: 5700(2402+1864+1434)).
 * - 가로 칸에 W*D*H(또는 ×)를 붙여넣으면 가로 · 깊이 · 높이로 나눈다(erp-order-shared.js 와 같은 규칙).
 * - 제품 속성 다섯 칸(internal · color · option_detail · handle · misc) + 추가 입력(extra_input).
 * - 제품마다 실측 사진 — 보내기 뒤 item_index 를 붙여 올린다(partner-portal.js).
 * 설계서: docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.4 · §4.3 · §4.5
 */
(function () {
  'use strict';

  var MAX_ITEMS = 30;
  var MAX_SPEC_ROWS = 20;

  function cloneTemplate(id) {
    var tpl = document.getElementById(id);
    return tpl ? tpl.content.firstElementChild.cloneNode(true) : null;
  }

  function renumber(container, rowSelector, labelSelector, prefix) {
    var rows = container.querySelectorAll(rowSelector);
    Array.prototype.forEach.call(rows, function (row, i) {
      var label = row.querySelector(labelSelector);
      if (label) label.textContent = prefix + ' ' + (i + 1);
    });
    return rows.length;
  }

  function refreshSpecs(item) {
    var box = item.querySelector('[data-pp-specs]');
    var count = renumber(box, '.pp-spec', '[data-pp-spec-no]', '규격');
    Array.prototype.forEach.call(box.querySelectorAll('[data-pp-remove-spec]'), function (btn) {
      btn.hidden = count <= 1;
    });
    var add = item.querySelector('[data-pp-add-spec]');
    if (add) add.disabled = count >= MAX_SPEC_ROWS;
  }

  function refreshItems(container) {
    var count = renumber(container, '.pp-item', '[data-pp-item-no]', '항목');
    Array.prototype.forEach.call(container.querySelectorAll('[data-pp-remove-item]'), function (btn) {
      btn.hidden = count <= 1;
    });
    return count;
  }

  /** 가로 칸에 'W*D*H' 를 붙여넣으면 같은 줄의 깊이 · 높이까지 채운다. */
  function onWidthPaste(ev) {
    var input = ev.target;
    if (!input.matches || !input.matches('[data-s="spec_width"]')) return;
    var raw = ((ev.clipboardData && ev.clipboardData.getData('text/plain')) || '').trim();
    if (!/[*×]/.test(raw)) return;
    var parts = raw.split(/[*×]/).map(function (s) { return s.trim(); });
    if (parts.length < 2 || !parts[0]) return;
    ev.preventDefault();
    var row = input.closest('.pp-spec');
    var keys = ['spec_width', 'spec_depth', 'spec_height'];
    keys.forEach(function (key, i) {
      var field = row && row.querySelector('[data-s="' + key + '"]');
      if (field && parts[i]) field.value = parts[i];
    });
  }

  function addSpecRow(item) {
    var box = item.querySelector('[data-pp-specs]');
    if (!box || box.querySelectorAll('.pp-spec').length >= MAX_SPEC_ROWS) return;
    var row = cloneTemplate('ppSpecRow');
    if (!row) return;
    box.appendChild(row);
    refreshSpecs(item);
  }

  function addItem(container) {
    if (container.querySelectorAll('.pp-item').length >= MAX_ITEMS) return null;
    var item = cloneTemplate('ppItemRow');
    if (!item) return null;
    container.appendChild(item);
    addSpecRow(item);
    refreshItems(container);
    return item;
  }

  function onClick(container, ev) {
    var target = ev.target;
    var item = target.closest('.pp-item');
    if (target.closest('[data-pp-add-spec]') && item) {
      addSpecRow(item);
    } else if (target.closest('[data-pp-remove-spec]') && item) {
      var specs = item.querySelectorAll('.pp-spec');
      if (specs.length > 1) target.closest('.pp-spec').remove();
      refreshSpecs(item);
    } else if (target.closest('[data-pp-remove-item]') && item) {
      if (container.querySelectorAll('.pp-item').length > 1) item.remove();
      refreshItems(container);
    }
  }

  function readSpecRows(item) {
    var rows = [];
    Array.prototype.forEach.call(item.querySelectorAll('.pp-spec'), function (row) {
      var spec = {};
      Array.prototype.forEach.call(row.querySelectorAll('[data-s]'), function (input) {
        spec[input.getAttribute('data-s')] = input.value.trim();
      });
      rows.push(spec);
    });
    return rows;
  }

  function readItem(item) {
    var data = { spec_rows: readSpecRows(item) };
    Array.prototype.forEach.call(item.querySelectorAll('[data-k]'), function (input) {
      data[input.getAttribute('data-k')] = input.value.trim();
    });
    return data;
  }

  /**
   * 이름이 있는 제품만 서버 순서대로 모은다. photoJobs[i].index 는 서버 items 의 위치(= item_index)다.
   * 서버도 이름 없는 품목을 버리므로 같은 순서가 된다(foms/services/partners/orders.py _clean_items).
   */
  function collect(container) {
    var items = [];
    var photoJobs = [];
    Array.prototype.forEach.call(container.querySelectorAll('.pp-item'), function (item) {
      var data = readItem(item);
      if (!data.product_name) return;
      var photos = item.querySelector('[data-pp-item-photos]');
      var files = Array.prototype.slice.call((photos && photos.files) || []);
      if (files.length) photoJobs.push({ index: items.length, name: data.product_name, files: files });
      items.push(data);
    });
    return { items: items, photoJobs: photoJobs };
  }

  function init(container, addButton) {
    if (!container) return;
    addItem(container);
    container.addEventListener('click', function (ev) { onClick(container, ev); });
    container.addEventListener('paste', onWidthPaste);
    if (addButton) addButton.addEventListener('click', function () { addItem(container); });
  }

  window.PartnerItems = { init: init, collect: collect };
})();
