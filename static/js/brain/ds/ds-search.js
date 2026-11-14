/**
 * 새 찾기 · 지식 표(판 ⑦ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.3 · 5.4) — templates/brain/ds/search.html 의
 * [data-ds-search-page]. 옛 찾기 탭(brain-page.js) · 지식 표 탭(brain-table.js)이 하던 일을 한 화면에서 한다(그 둘은 싣지 않는다).
 *
 * - 찾기: 찾는 말 → GET /api/brain/search?q= → 같은 표에 유형별 묶음 줄(앞 몇 개 · 수 · '표에서 모두 보기').
 * - 지식 표: 유형(왼쪽 나무 · 수 칩 · 거르기 '유형' · '표에서 모두 보기') → GET /api/brain/table(거르기 여덟 · 정렬 · 쪽).
 *   주소의 유형이 없으면 지식이 있는 첫 유형. 유형 고르기 칸의 이름 옆에 볼 수 있는 수를 붙인다(옛 표와 같다).
 * - 주소는 history.replaceState 로 맞춘다(?tab=search&q= · ?tab=table&type= — 지금 주소 그대로). 고른 줄 · 펼친 묶음도 맞춘다.
 * - 줄을 누르거나 Enter 면 오른쪽 미리 보기(ds-search-preview.js). 이름 링크는 카드로 간다.
 * 요청은 brain-dom.js getJson 한 곳(try/catch + data.success), 글은 textContent 만, 전역 듣개는 한 번만(__FOMS_DS_SEARCH_BOUND).
 */
(function () {
  'use strict';

  if (window.__FOMS_DS_SEARCH_BOUND) return;
  var root = document.querySelector('[data-ds-search-page]');
  var dom = window.FOMS_BRAIN_DOM;
  var sv = window.FOMS_DS_SEARCH_VIEW;
  var rows = window.FOMS_DS_SEARCH_ROWS;
  var view = window.FOMS_BRAIN_VIEW;
  var preview = window.FOMS_DS_SEARCH_PREVIEW;
  if (!root || !dom || !sv || !rows || !view || !preview) return;
  window.__FOMS_DS_SEARCH_BOUND = true;

  var ctx = {
    display: dom.safeJsonParse(root.getAttribute('data-display'), {}),
    icons: dom.safeJsonParse(root.getAttribute('data-type-icons'), {}),
    counts: dom.safeJsonParse(root.getAttribute('data-type-counts'), {}),
    itemBase: root.getAttribute('data-item-base') || '/brain/items/',
    itemApi: root.getAttribute('data-item-api') || '/api/brain/items/',
    pageUrl: root.getAttribute('data-page-url') || '/brain',
    searchUrl: root.getAttribute('data-search-url'), tableUrl: root.getAttribute('data-table-url'),
    usage: root.hasAttribute('data-usage')
  };
  var input = root.querySelector('[data-ds-search-input]');
  var filters = root.querySelector('[data-ds-search-filters]');
  var status = root.querySelector('[data-ds-search-status]');
  var body = root.querySelector('[data-ds-search-body]');
  var pager = root.querySelector('[data-ds-search-pager]');
  var list = root.querySelector('[data-ds-search-list]');
  var pageText = root.querySelector('[data-ds-page-text]');
  var prev = root.querySelector('[data-ds-page-prev]');
  var next = root.querySelector('[data-ds-page-next]');
  var tree = document.querySelector('[data-ds-search-tree]');
  var state = { mode: root.getAttribute('data-ds-search-mode') === 'table' ? 'table' : 'search',
                query: root.getAttribute('data-start-query') || '', type: '', page: 1, seq: 0 };

  function places() {
    return [root, tree].filter(Boolean);
  }

  function syncUrl() {
    var value = state.mode === 'table' ? state.type : state.query;
    window.history.replaceState(null, '', ctx.pageUrl + sv.pageQuery(state.mode, value));
  }

  /** 고른 유형 · '모든 유형' 표시와 펼친 묶음, 거르기 · 쪽 보이기를 지금 화면에 맞춘다. */
  function markNav() {
    places().forEach(function (place) {
      place.querySelectorAll('[data-ds-type], [data-ds-search-all]').forEach(function (node) {
        var on = node.hasAttribute('data-ds-search-all') ? state.mode === 'search'
          : state.mode === 'table' && node.getAttribute('data-ds-type') === state.type;
        if (node.classList.contains('f-btn')) return;  // 묶음 줄의 '표에서 모두 보기' 단추
        node.classList.toggle('is-selected', on);
        if (on) node.setAttribute('aria-current', 'page');
        else node.removeAttribute('aria-current');
        if (on && node.closest('details')) node.closest('details').open = true;
        if (on && node.hasAttribute('data-ds-chip-more')) node.hidden = false;  // '그 밖' 칩도 고르면 보인다
      });
    });
    filters.hidden = state.mode !== 'table';
    pager.hidden = state.mode !== 'table';
  }

  function setFilter(name, value) {
    var select = filters.querySelector('[data-ds-filter="' + name + '"]');
    if (select) select.value = value;
  }

  function readFilters() {
    var out = { page: state.page };
    filters.querySelectorAll('[data-ds-filter]').forEach(function (select) {
      out[select.getAttribute('data-ds-filter')] = select.value;
    });
    return out;
  }

  /** 유형 고르기 칸의 이름 옆에 수(볼 수 있는 것만 — 표 답의 type_counts). */
  function updateTypeCounts(counts) {
    var select = filters.querySelector('[data-ds-filter="type"]');
    if (!select) return;
    Array.prototype.forEach.call(select.options, function (option) {
      option.textContent = (option.getAttribute('data-label') || option.textContent) + ' (' + sv.num(counts[option.value]) + ')';
    });
  }

  function listKeys() {
    var keys = Array.prototype.map.call(body.querySelectorAll('[data-ds-row-key]'), function (tr) {
      return tr.getAttribute('data-ds-row-key');
    });
    preview.setRows(keys);
  }

  /** index 째 줄을 고른 줄로(표시만 — 미리 보기는 부른 쪽이). */
  function highlight(index) {
    body.querySelectorAll('[data-ds-row-key]').forEach(function (tr, i) {
      tr.classList.toggle('is-selected', i === index);
      tr.setAttribute('aria-selected', i === index ? 'true' : 'false');
      if (i === index && tr.scrollIntoView) tr.scrollIntoView({ block: 'nearest' });
    });
  }

  function pick(tr) {
    var all = Array.prototype.slice.call(body.querySelectorAll('[data-ds-row-key]'));
    var index = all.indexOf(tr);
    if (index < 0) return;
    highlight(index);
    preview.show(index);
  }

  async function runSearch(text) {
    state.query = String(text || '').trim();
    syncUrl();
    dom.clear(body);
    var mine = ++state.seq;
    list.hidden = !state.query;  // 찾을 말이 없으면 빈 표 머리를 보이지 않는다
    if (!state.query) {
      dom.setStatus(status, '찾을 말을 적어 주세요.');
      listKeys();
      return;
    }
    dom.setStatus(status, '찾는 중…');
    var res = await dom.getJson(ctx.searchUrl + '?q=' + encodeURIComponent(state.query));
    if (mine !== state.seq) return;  // 더 늦은 찾기 · 표가 이미 나갔다
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      listKeys();
      return;
    }
    var groups = res.data.groups || [];
    dom.setStatus(status, groups.length ? sv.num(res.data.total) + '개 찾았어요.' : '찾은 지식이 없어요. 다른 말로 찾아 보세요.');
    groups.forEach(function (group) {
      body.appendChild(rows.groupRow(ctx, group));
      (group.items || []).forEach(function (item) { body.appendChild(rows.itemRow(ctx, item)); });
    });
    listKeys();
  }

  async function loadTable() {
    var wanted = readFilters();
    var mine = ++state.seq;
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(ctx.tableUrl + '?' + view.tableParams(wanted));
    if (mine !== state.seq) return;
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    var data = res.data;
    list.hidden = false;
    state.page = data.page;
    updateTypeCounts(data.type_counts || {});
    dom.clear(body);
    data.rows.forEach(function (item) { body.appendChild(rows.itemRow(ctx, item)); });
    if (!data.rows.length) body.appendChild(rows.noteRow('조건에 맞는 지식이 없어요.'));
    var info = view.pager(data.page, data.pages, data.total, data.per_page);
    pageText.textContent = sv.pagerText(data.page, data.per_page, data.total, sv.label(ctx.display, 'sorts', wanted.sort));
    prev.disabled = !info.hasPrev;
    next.disabled = !info.hasNext;
    dom.setStatus(status, '');
    listKeys();
  }

  function openTable(type) {
    state.mode = 'table';
    state.type = sv.pickStartType(type, ctx.counts, ctx.display.type_order);
    state.page = 1;
    setFilter('type', state.type);
    markNav();
    syncUrl();
    loadTable();
  }

  function openSearch(text) {
    state.mode = 'search';
    markNav();
    runSearch(text);
  }

  root.querySelector('[data-ds-search-form]').addEventListener('submit', function (event) {
    event.preventDefault();
    openSearch(input.value);
  });

  places().forEach(function (place) {
    place.addEventListener('click', function (event) {
      var typeLink = event.target.closest('[data-ds-type]');
      var all = event.target.closest('[data-ds-search-all]');
      var toggle = event.target.closest('[data-ds-chip-toggle]');
      if (typeLink) {
        event.preventDefault();
        openTable(typeLink.getAttribute('data-ds-type'));
      } else if (all) {
        event.preventDefault();
        openSearch(input.value);
        input.focus();
      } else if (toggle) {
        var open = toggle.getAttribute('aria-expanded') !== 'true';
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        root.querySelectorAll('[data-ds-chip-more]').forEach(function (chip) { chip.hidden = !open; });
      }
    });
  });

  filters.addEventListener('change', function (event) {
    var select = event.target.closest('[data-ds-filter]');
    if (!select) return;
    state.page = 1;
    if (select.getAttribute('data-ds-filter') === 'type') {
      state.type = select.value;
      markNav();
      syncUrl();
    }
    loadTable();
  });
  prev.addEventListener('click', function () { state.page = Math.max(1, state.page - 1); loadTable(); });
  next.addEventListener('click', function () { state.page += 1; loadTable(); });

  body.addEventListener('click', function (event) {
    if (event.target.closest('a')) return;  // 이름 · '표에서 모두 보기' 링크는 링크대로
    var tr = event.target.closest('[data-ds-row-key]');
    if (tr) pick(tr);
  });
  body.addEventListener('keydown', function (event) {
    var tr = event.target.closest('[data-ds-row-key]');
    if (tr && event.target === tr && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      pick(tr);
    }
  });

  preview.init(ctx, highlight);
  if (state.mode === 'table') {
    openTable(root.getAttribute('data-start-type') || '');
  } else {
    markNav();
    runSearch(state.query);
    if (!state.query && input && window.matchMedia && window.matchMedia('(hover: hover)').matches) input.focus();
  }
})();
