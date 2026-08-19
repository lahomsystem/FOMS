/**
 * AS 첨부 올리기 전 순서 지정 (AS-SORT-01).
 * 미리보기 배열이 정본이고, 드래그/▲▼/삭제로 순서를 바꾼다.
 */
(function (global) {
  'use strict';
  if (global.__AS_ATTACH_ORDER_BOUND) return;
  global.__AS_ATTACH_ORDER_BOUND = true;

  function escapeHtml(value) {
    if (typeof global.escapeHtml === 'function') return global.escapeHtml(value);
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function revokeUrls(items) {
    (items || []).forEach(function (item) {
      if (item && item.url) {
        try { global.URL.revokeObjectURL(item.url); } catch (_) { /* ignore */ }
      }
    });
  }

  function toItem(file) {
    var url = '';
    if (file && file.type && file.type.indexOf('image/') === 0) {
      try { url = URL.createObjectURL(file); } catch (_) { url = ''; }
    }
    return { file: file, url: url };
  }

  function moveItem(list, from, to) {
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) {
      return list;
    }
    var next = list.slice();
    var taken = next.splice(from, 1)[0];
    next.splice(to, 0, taken);
    return next;
  }

  function mount(container, options) {
    options = options || {};
    var items = [];
    var dragFrom = -1;

    function emit() {
      if (typeof options.onChange === 'function') {
        options.onChange(items.map(function (item) { return item.file; }));
      }
    }

    function paint() {
      if (!container) return;
      if (!items.length) {
        container.innerHTML = '';
        container.hidden = true;
        return;
      }
      container.hidden = false;
      container.innerHTML = items.map(function (item, idx) {
        var name = escapeHtml(item.file && item.file.name ? item.file.name : 'file');
        var media = item.url
          ? '<img src="' + item.url + '" alt="' + name + '">'
          : '<span class="as-attach-order__name">' + name + '</span>';
        return '<div class="as-attach-order__item" draggable="true" data-idx="' + idx + '">'
          + '<span class="as-attach-order__ord">' + (idx + 1) + '</span>'
          + media
          + '<div class="as-attach-order__tools">'
          + '<button type="button" class="as-attach-order__nudge" data-dir="-1" aria-label="앞으로">▲</button>'
          + '<button type="button" class="as-attach-order__nudge" data-dir="1" aria-label="뒤로">▼</button>'
          + '<button type="button" class="as-attach-order__remove" aria-label="삭제"><i class="fas fa-times" aria-hidden="true"></i></button>'
          + '</div></div>';
      }).join('');
    }

    container.addEventListener('click', function (e) {
      var itemEl = e.target.closest && e.target.closest('.as-attach-order__item');
      if (!itemEl || !container.contains(itemEl)) return;
      var idx = Number(itemEl.getAttribute('data-idx'));
      var remove = e.target.closest && e.target.closest('.as-attach-order__remove');
      if (remove) {
        revokeUrls([items[idx]]);
        items.splice(idx, 1);
        paint();
        emit();
        return;
      }
      var nudge = e.target.closest && e.target.closest('.as-attach-order__nudge');
      if (!nudge) return;
      var dir = Number(nudge.getAttribute('data-dir'));
      items = moveItem(items, idx, idx + dir);
      paint();
      emit();
    });

    container.addEventListener('dragstart', function (e) {
      var itemEl = e.target.closest && e.target.closest('.as-attach-order__item');
      if (!itemEl) return;
      dragFrom = Number(itemEl.getAttribute('data-idx'));
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
    });
    container.addEventListener('dragover', function (e) {
      if (dragFrom < 0) return;
      e.preventDefault();
    });
    container.addEventListener('drop', function (e) {
      var itemEl = e.target.closest && e.target.closest('.as-attach-order__item');
      if (!itemEl || dragFrom < 0) return;
      e.preventDefault();
      var to = Number(itemEl.getAttribute('data-idx'));
      items = moveItem(items, dragFrom, to);
      dragFrom = -1;
      paint();
      emit();
    });
    container.addEventListener('dragend', function () { dragFrom = -1; });

    return {
      setFiles: function (files) {
        revokeUrls(items);
        items = (files || []).map(toItem);
        paint();
        emit();
      },
      addFiles: function (files) {
        items = items.concat((files || []).map(toItem));
        paint();
        emit();
      },
      getFiles: function () {
        return items.map(function (item) { return item.file; });
      },
      clear: function () {
        revokeUrls(items);
        items = [];
        paint();
        emit();
      },
    };
  }

  global.fomsAsAttachmentOrder = { mount: mount, moveItem: moveItem };
})(typeof window !== 'undefined' ? window : globalThis);
