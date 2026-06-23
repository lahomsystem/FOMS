/**
 * ERP 현장 스펙 피커 (erp-spec-calc.js 보조 UI 모듈).
 *
 * 목적: native <datalist>가 모바일에서 신뢰성 있게 열리지 않는 문제를 해결한다.
 *       WDCalculator의 검증된 패턴을 그대로 재사용:
 *        - 단일 선택(openSingle): category-picker(wd-cat-*) — 데스크톱 드롭다운 / 모바일 바텀시트
 *        - 다중 선택(openMulti): multi-add-picker(wd-madd-*) — 데스크톱 모달 / 모바일 바텀시트(검색+체크박스)
 *
 * 설계: 운영 중인 WDCalc JS 모듈은 그 페이지 DOM에 강결합되어 직접 재사용 불가하므로
 *       콜백 기반의 얇은 ERP 전용 피커를 두되, CSS 클래스(wd-cat-*/wd-madd-*)는 그대로 재사용해
 *       룩앤필을 통일한다. 값은 호출측(erp-spec-calc.js)이 입력칸에 써넣어 직접입력/autosize를 보존.
 */
(function () {
  'use strict';

  if (window.__erpSpecPickerBound) return;
  window.__erpSpecPickerBound = true;

  var PANEL_MARGIN = 8;
  var PANEL_GAP = 4;
  var PANEL_MIN_HEIGHT = 120;
  var PANEL_PREFERRED_MAX = 420;

  function isMobile() {
    return !!(window.matchMedia && window.matchMedia('(max-width: 991.98px)').matches);
  }

  // ============================ 단일 선택(wd-cat-*) ============================
  var single = null;

  function ensureSingleOverlay() {
    if (single) return single;
    var backdrop = document.createElement('div');
    backdrop.className = 'wd-cat-backdrop';
    backdrop.addEventListener('click', closeSingle);

    var panel = document.createElement('div');
    panel.className = 'wd-cat-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');

    var head = document.createElement('div');
    head.className = 'wd-cat-panel__head';
    var titleEl = document.createElement('span');
    titleEl.className = 'wd-cat-panel__title';
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'wd-cat-panel__close';
    closeBtn.setAttribute('aria-label', '닫기');
    closeBtn.textContent = '\u2715';
    closeBtn.addEventListener('click', closeSingle);
    head.appendChild(titleEl);
    head.appendChild(closeBtn);

    var body = document.createElement('div');
    body.className = 'wd-cat-panel__body';

    panel.appendChild(head);
    panel.appendChild(body);
    document.body.appendChild(backdrop);
    document.body.appendChild(panel);

    single = { backdrop: backdrop, panel: panel, body: body, titleEl: titleEl, anchor: null, onPick: null };

    window.addEventListener('resize', function () {
      if (!single || !single.panel.classList.contains('is-open')) return;
      single.panel.classList.toggle('wd-cat-panel--sheet', isMobile());
      single.panel.classList.toggle('wd-cat-panel--dropdown', !isMobile());
      positionSingle();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeSingle();
    });
    return single;
  }

  function makeOptRow(text, isSelected, onClick) {
    var row = document.createElement('button');
    row.type = 'button';
    row.className = 'wd-cat-opt' + (isSelected ? ' is-selected' : '');
    row.textContent = text;
    row.addEventListener('click', onClick);
    return row;
  }

  function expandCatGroup(groupEl, listEl, open) {
    groupEl.classList.toggle('is-open', open);
    listEl.style.maxHeight = open ? listEl.scrollHeight + 'px' : '0px';
    if (single && single.panel.classList.contains('is-open')) {
      window.requestAnimationFrame(positionSingle);
    }
  }

  function getScrollParents(el) {
    var parents = [];
    var node = el && el.parentElement;
    while (node && node !== document.documentElement) {
      var style = window.getComputedStyle(node);
      if (/(auto|scroll|overlay)/.test(style.overflowY) || /(auto|scroll|overlay)/.test(style.overflowX)) {
        parents.push(node);
      }
      node = node.parentElement;
    }
    parents.push(window);
    return parents;
  }

  function bindReposition(anchor) {
    unbindReposition();
    if (!single || !anchor) return;
    single._scrollParents = getScrollParents(anchor);
    single._onReposition = function () { positionSingle(); };
    for (var i = 0; i < single._scrollParents.length; i++) {
      single._scrollParents[i].addEventListener('scroll', single._onReposition, { passive: true });
    }
  }

  function unbindReposition() {
    if (!single || !single._scrollParents || !single._onReposition) return;
    for (var i = 0; i < single._scrollParents.length; i++) {
      single._scrollParents[i].removeEventListener('scroll', single._onReposition);
    }
    single._scrollParents = null;
    single._onReposition = null;
  }

  function positionSingle() {
    if (!single || !single.anchor) return;
    var panel = single.panel;
    if (isMobile()) {
      panel.style.left = '';
      panel.style.top = '';
      panel.style.width = '';
      panel.style.maxHeight = '';
      panel.classList.remove('wd-cat-panel--above');
      return;
    }
    var r = single.anchor.getBoundingClientRect();
    var width = Math.max(r.width, 260);
    var left = Math.min(r.left, window.innerWidth - width - PANEL_MARGIN);
    left = Math.max(PANEL_MARGIN, left);
    var viewportH = window.innerHeight;
    var preferredMax = Math.min(viewportH * 0.6, PANEL_PREFERRED_MAX);
    var spaceBelow = viewportH - r.bottom - PANEL_GAP - PANEL_MARGIN;
    var spaceAbove = r.top - PANEL_GAP - PANEL_MARGIN;
    var placeAbove = (spaceBelow < PANEL_MIN_HEIGHT && spaceAbove > spaceBelow) ||
      (spaceAbove > spaceBelow && spaceBelow < preferredMax * 0.45);
    var available = placeAbove ? spaceAbove : spaceBelow;
    var maxHeight = Math.min(preferredMax, Math.max(0, available));
    var top;
    if (placeAbove) {
      top = r.top - PANEL_GAP - maxHeight;
      if (top < PANEL_MARGIN) {
        maxHeight = Math.min(preferredMax, r.top - PANEL_GAP - PANEL_MARGIN);
        top = PANEL_MARGIN;
      }
    } else {
      top = r.bottom + PANEL_GAP;
      if (top + maxHeight > viewportH - PANEL_MARGIN) maxHeight = viewportH - PANEL_MARGIN - top;
      if (maxHeight < PANEL_MIN_HEIGHT && spaceAbove > spaceBelow) {
        placeAbove = true;
        maxHeight = Math.min(preferredMax, spaceAbove);
        top = Math.max(PANEL_MARGIN, r.top - PANEL_GAP - maxHeight);
      }
    }
    panel.style.width = width + 'px';
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
    panel.style.maxHeight = Math.max(0, maxHeight) + 'px';
    panel.classList.toggle('wd-cat-panel--above', placeAbove);
  }

  function closeSingle() {
    if (!single) return;
    unbindReposition();
    single.backdrop.classList.remove('is-open');
    single.panel.classList.remove('is-open');
    single.panel.classList.remove('wd-cat-panel--above');
    document.body.classList.remove('wd-cat-open');
    single.anchor = null;
    single.onPick = null;
  }

  /**
   * 단일 선택 패널을 연다.
   * opts: { title, anchor(트리거 el), current,
   *         topItems:[{value,text}], groups:[{label, items:[{value,text}]}], onPick(value) }
   */
  function openSingle(opts) {
    opts = opts || {};
    var ov = ensureSingleOverlay();
    ov.anchor = opts.anchor || null;
    ov.onPick = typeof opts.onPick === 'function' ? opts.onPick : null;
    ov.titleEl.textContent = opts.title || '선택';
    var current = opts.current == null ? '' : String(opts.current);
    var body = ov.body;
    body.innerHTML = '';

    function commit(value) {
      var cb = ov.onPick;
      closeSingle();
      if (cb) cb(value);
    }

    (opts.topItems || []).forEach(function (it) {
      var row = makeOptRow(it.text, String(it.value) === current, function () { commit(it.value); });
      if (it.value === '') row.classList.add('wd-cat-opt--placeholder');
      body.appendChild(row);
    });

    (opts.groups || []).forEach(function (g) {
      var hasCurrent = (g.items || []).some(function (o) { return String(o.value) === current; });
      var groupEl = document.createElement('div');
      groupEl.className = 'wd-cat-group';
      var header = document.createElement('button');
      header.type = 'button';
      header.className = 'wd-cat-group__head';
      header.innerHTML =
        '<span class="wd-cat-group__name"></span>' +
        '<span class="wd-cat-group__meta"><span class="wd-cat-group__count"></span>' +
        '<span class="wd-cat-group__chev">\u25be</span></span>';
      header.querySelector('.wd-cat-group__name').textContent = g.label || '';
      header.querySelector('.wd-cat-group__count').textContent = (g.items || []).length + '개';
      var list = document.createElement('div');
      list.className = 'wd-cat-group__list';
      (g.items || []).forEach(function (o) {
        list.appendChild(makeOptRow(o.text, String(o.value) === current, function () { commit(o.value); }));
      });
      header.addEventListener('click', function () {
        expandCatGroup(groupEl, list, !groupEl.classList.contains('is-open'));
      });
      groupEl.appendChild(header);
      groupEl.appendChild(list);
      body.appendChild(groupEl);
      expandCatGroup(groupEl, list, hasCurrent);
    });

    ov.backdrop.classList.add('is-open');
    ov.panel.classList.add('is-open');
    ov.panel.classList.toggle('wd-cat-panel--sheet', isMobile());
    ov.panel.classList.toggle('wd-cat-panel--dropdown', !isMobile());
    document.body.classList.add('wd-cat-open');
    bindReposition(ov.anchor);
    positionSingle();
    var openLists = ov.panel.querySelectorAll('.wd-cat-group.is-open .wd-cat-group__list');
    for (var k = 0; k < openLists.length; k++) openLists[k].style.maxHeight = openLists[k].scrollHeight + 'px';
    window.requestAnimationFrame(positionSingle);
  }

  // ============================ 다중 선택(wd-madd-*) ============================
  var multi = null;

  function ensureMultiOverlay() {
    if (multi) return multi;
    var backdrop = document.createElement('div');
    backdrop.className = 'wd-madd-backdrop';
    backdrop.addEventListener('click', closeMulti);

    var panel = document.createElement('div');
    panel.className = 'wd-madd-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');

    var head = document.createElement('div');
    head.className = 'wd-madd-panel__head';
    var titleEl = document.createElement('span');
    titleEl.className = 'wd-madd-panel__title';
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'wd-madd-panel__close';
    closeBtn.setAttribute('aria-label', '닫기');
    closeBtn.textContent = '\u2715';
    closeBtn.addEventListener('click', closeMulti);
    head.appendChild(titleEl);
    head.appendChild(closeBtn);

    var searchWrap = document.createElement('div');
    searchWrap.className = 'wd-madd-panel__search';
    var searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'wd-madd-search-input';
    searchInput.setAttribute('placeholder', '검색…');
    searchInput.addEventListener('input', function () { applyMultiFilter(searchInput.value); });
    searchWrap.appendChild(searchInput);

    var body = document.createElement('div');
    body.className = 'wd-madd-panel__body';

    var footer = document.createElement('div');
    footer.className = 'wd-madd-panel__foot';
    var addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'wd-madd-btn wd-madd-btn--primary';
    addBtn.addEventListener('click', confirmMulti);
    footer.appendChild(addBtn);

    panel.appendChild(head);
    panel.appendChild(searchWrap);
    panel.appendChild(body);
    panel.appendChild(footer);
    document.body.appendChild(backdrop);
    document.body.appendChild(panel);

    multi = { backdrop: backdrop, panel: panel, body: body, titleEl: titleEl, searchInput: searchInput, addBtn: addBtn, selected: null, onConfirm: null };

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && multi && multi.panel.classList.contains('is-open')) closeMulti();
    });
    return multi;
  }

  function makeCheckRow(item) {
    var row = document.createElement('label');
    row.className = 'wd-madd-opt';
    row.setAttribute('data-search', ((item.label || '') + ' ' + (item.meta || '')).toLowerCase());
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'wd-madd-opt__cb';
    cb.checked = multi.selected.has(item.key);
    var text = document.createElement('span');
    text.className = 'wd-madd-opt__label';
    text.textContent = item.label || '';
    var meta = document.createElement('span');
    meta.className = 'wd-madd-opt__meta';
    meta.textContent = item.meta || '';
    cb.addEventListener('change', function () {
      if (cb.checked) { multi.selected.set(item.key, item.payload); row.classList.add('is-checked'); }
      else { multi.selected.delete(item.key); row.classList.remove('is-checked'); }
      updateMultiFooter();
    });
    if (cb.checked) row.classList.add('is-checked');
    row.appendChild(cb);
    row.appendChild(text);
    row.appendChild(meta);
    return row;
  }

  function expandMaddGroup(groupEl, listEl, open) {
    groupEl.classList.toggle('is-open', open);
    listEl.style.maxHeight = open ? listEl.scrollHeight + 'px' : '0px';
  }

  function renderMultiGroups(groups) {
    var body = multi.body;
    body.innerHTML = '';
    if (!groups || !groups.length) {
      var empty = document.createElement('div');
      empty.className = 'wd-madd-empty';
      empty.textContent = '등록된 옵션이 없습니다. 제품 설정에서 추가하세요.';
      body.appendChild(empty);
      return;
    }
    groups.forEach(function (g) {
      var groupEl = document.createElement('div');
      groupEl.className = 'wd-madd-group';
      var header = document.createElement('button');
      header.type = 'button';
      header.className = 'wd-madd-group__head';
      header.innerHTML =
        '<span class="wd-madd-group__name"></span>' +
        '<span class="wd-madd-group__meta"><span class="wd-madd-group__count"></span>' +
        '<span class="wd-madd-group__chev">\u25be</span></span>';
      header.querySelector('.wd-madd-group__name').textContent = g.label || '';
      header.querySelector('.wd-madd-group__count').textContent = (g.items || []).length + '개';
      var list = document.createElement('div');
      list.className = 'wd-madd-group__list';
      (g.items || []).forEach(function (item) { list.appendChild(makeCheckRow(item)); });
      header.addEventListener('click', function () {
        expandMaddGroup(groupEl, list, !groupEl.classList.contains('is-open'));
      });
      groupEl.appendChild(header);
      groupEl.appendChild(list);
      body.appendChild(groupEl);
      // 이미 선택된 항목이 있는 그룹은 펼쳐서 보이게
      var hasChecked = (g.items || []).some(function (it) { return multi.selected.has(it.key); });
      expandMaddGroup(groupEl, list, hasChecked);
    });
  }

  function applyMultiFilter(query) {
    if (!multi) return;
    var q = (query || '').trim().toLowerCase();
    var groups = multi.body.querySelectorAll('.wd-madd-group');
    for (var i = 0; i < groups.length; i++) {
      var group = groups[i];
      var rows = group.querySelectorAll('.wd-madd-opt');
      var visible = 0;
      for (var j = 0; j < rows.length; j++) {
        var match = !q || rows[j].getAttribute('data-search').indexOf(q) !== -1;
        rows[j].style.display = match ? '' : 'none';
        if (match) visible++;
      }
      group.style.display = visible ? '' : 'none';
      var list = group.querySelector('.wd-madd-group__list');
      if (q) expandMaddGroup(group, list, visible > 0);
      else expandMaddGroup(group, list, (group.querySelectorAll('.wd-madd-opt.is-checked').length > 0));
    }
  }

  function updateMultiFooter() {
    if (!multi) return;
    var n = multi.selected.size;
    multi.addBtn.textContent = n > 0 ? ('적용 (' + n + ')') : '적용';
  }

  function confirmMulti() {
    if (!multi) return;
    var payloads = [];
    multi.selected.forEach(function (p) { payloads.push(p); });
    var cb = multi.onConfirm;
    closeMulti();
    if (cb) cb(payloads);
  }

  function closeMulti() {
    if (!multi) return;
    multi.backdrop.classList.remove('is-open');
    multi.panel.classList.remove('is-open');
    document.body.classList.remove('wd-madd-open');
    multi.selected = null;
    multi.onConfirm = null;
  }

  /**
   * 다중 선택 패널을 연다.
   * opts: { title, groups:[{label, items:[{key,label,meta,payload}]}],
   *         selectedKeys:[key...], onConfirm(payloads[]) }
   */
  function openMulti(opts) {
    opts = opts || {};
    var ov = ensureMultiOverlay();
    ov.onConfirm = typeof opts.onConfirm === 'function' ? opts.onConfirm : null;
    ov.selected = new Map();
    (opts.selectedKeys || []).forEach(function (k) { ov.selected.set(k, { __preselect: true, key: k }); });
    // 사전선택 payload는 groups에서 실제 payload로 교체(렌더 전 보정)
    (opts.groups || []).forEach(function (g) {
      (g.items || []).forEach(function (it) {
        if (ov.selected.has(it.key)) ov.selected.set(it.key, it.payload);
      });
    });
    ov.titleEl.textContent = opts.title || '옵션 선택';
    ov.searchInput.value = '';
    renderMultiGroups(opts.groups || []);
    updateMultiFooter();
    ov.backdrop.classList.add('is-open');
    ov.panel.classList.add('is-open');
    ov.panel.classList.toggle('wd-madd-panel--sheet', isMobile());
    ov.panel.classList.toggle('wd-madd-panel--modal', !isMobile());
    document.body.classList.add('wd-madd-open');
  }

  window.ErpSpecPicker = { openSingle: openSingle, openMulti: openMulti, closeSingle: closeSingle, closeMulti: closeMulti };
})();
