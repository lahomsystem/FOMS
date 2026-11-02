/**
 * 회사 지식 화면 뼈대 · 찾기 탭(HAUD master brain 설계서 7.5 화면 1) — templates/brain/index.html 의 [data-brain-page].
 *
 * - data-* 를 safeJsonParse 로 읽어 window.FOMS_BRAIN_CTX 를 만든다(표시 표 · API 주소 · 항목 주소 머리 · 그림 라이브러리 주소).
 * - 탭: Bootstrap 탭이 바뀌면 'brain:tab' {tab} 를 쏜다(지식 표 · 판 · 유형 지도 스크립트가 받는다). 첫 탭은 서버가 고른다.
 *   주소(?tab=&type=&q=)는 history.replaceState 로 맞춘다 — 새로 고침 · 링크 나눔이 같은 화면을 연다.
 * - 'brain:open-table' {type} 를 받으면 지식 표 탭으로 옮긴다(유형 지도 · 찾기 묶음의 '표에서 모두 보기').
 * - 찾기: GET /api/brain/search?q= → 유형별 묶음. fetch 는 try/catch + data.success 확인(brain-dom.js getJson), 글은 textContent 만.
 */
(function () {
  'use strict';

  if (window.__FOMS_BRAIN_PAGE_BOUND) return;
  var root = document.querySelector('[data-brain-page]');
  if (!root) return;
  window.__FOMS_BRAIN_PAGE_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var ctx = {
    root: root,
    display: dom.safeJsonParse(root.getAttribute('data-display'), {}),
    actions: dom.safeJsonParse(root.getAttribute('data-actions'), []),  // 이름 있는 액션 목록(7.7 — 단추 이름 · 고른 값)
    urls: {
      search: root.getAttribute('data-search-url'), table: root.getAttribute('data-table-url'),
      releases: root.getAttribute('data-releases-url'), typeMap: root.getAttribute('data-type-map-url'),
      page: root.getAttribute('data-page-url'), cytoscape: root.getAttribute('data-cytoscape-url'),
      dagre: root.getAttribute('data-dagre-url')
    },
    itemBase: root.getAttribute('data-item-base') || '/brain/items/',
    startType: root.getAttribute('data-start-type') || '',
    current: root.getAttribute('data-start-tab') || 'search',
    query: root.getAttribute('data-start-query') || ''
  };
  window.FOMS_BRAIN_CTX = ctx;

  /** 지금 상태를 주소에 맞춘다(새 기록을 쌓지 않는다). */
  function syncUrl(extra) {
    var params = new URLSearchParams();
    params.set('tab', ctx.current);
    Object.keys(extra || {}).forEach(function (key) { if (extra[key]) params.set(key, extra[key]); });
    window.history.replaceState(null, '', ctx.urls.page + '?' + params.toString());
  }
  ctx.syncUrl = syncUrl;

  function fire(name, detail) {
    root.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }
  ctx.fire = fire;

  /** 탭 옮기기 — Bootstrap 이 있으면 그 탭 동작으로, 없으면 이벤트만. */
  function showTab(name) {
    var button = root.querySelector('[data-brain-tab="' + name + '"]');
    if (button && window.bootstrap && window.bootstrap.Tab) {
      window.bootstrap.Tab.getOrCreateInstance(button).show();
    } else {
      ctx.current = name;
      fire('brain:tab', { tab: name });
    }
  }
  ctx.showTab = showTab;

  root.querySelectorAll('[data-brain-tab]').forEach(function (button) {
    button.addEventListener('shown.bs.tab', function () {
      ctx.current = button.getAttribute('data-brain-tab');
      fire('brain:tab', { tab: ctx.current });
      if (ctx.current === 'search') syncUrl({ q: ctx.query });
      else if (ctx.current !== 'table') syncUrl();
    });
  });

  root.addEventListener('brain:open-table', function () { showTab('table'); });
  root.addEventListener('click', function (event) {
    var link = event.target.closest('[data-brain-open-table]');
    if (!link || !root.contains(link)) return;
    event.preventDefault();
    fire('brain:open-table', { type: link.getAttribute('data-brain-open-table') });
  });

  // ── 찾기 ──────────────────────────────────────────────────────────────
  var form = root.querySelector('[data-brain-search-form]');
  var input = root.querySelector('[data-brain-search-input]');
  var status = root.querySelector('[data-brain-search-status]');
  var results = root.querySelector('[data-brain-search-results]');
  var searchSeq = 0;

  function renderGroup(group) {
    var section = dom.el('section', { cls: 'brain-group' });
    var head = dom.el('div', { cls: 'brain-group__head' });
    head.appendChild(dom.typeChip(ctx.display, group.type));
    head.appendChild(dom.el('span', { cls: 'brain-group__count', text: group.count + '개' }));
    if (group.count > group.items.length) {
      head.appendChild(dom.el('a', { cls: 'brain-btn', text: '표에서 모두 보기',
                                     attrs: { href: ctx.urls.page + '?tab=table&type=' + encodeURIComponent(group.type),
                                              'data-brain-open-table': group.type } }));
    }
    section.appendChild(head);
    var list = dom.el('ul', { cls: 'brain-group__list' });
    group.items.forEach(function (item) { list.appendChild(dom.itemRow(ctx, item, { tag: 'li' })); });
    section.appendChild(list);
    return section;
  }

  async function runSearch(text) {
    var query = String(text || '').trim();
    ctx.query = query;
    syncUrl({ q: query });
    dom.clear(results);
    if (!query) {
      dom.setStatus(status, '찾을 말을 넣어 주세요.');
      return;
    }
    var seq = ++searchSeq;
    dom.setStatus(status, '찾는 중…');
    var res = await dom.getJson(ctx.urls.search + '?q=' + encodeURIComponent(query));
    if (seq !== searchSeq) return;  // 더 늦은 찾기가 이미 나갔다
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    var groups = res.data.groups || [];
    dom.setStatus(status, groups.length ? ('“' + res.data.query + '” — ' + res.data.total + '개(유형 ' + groups.length + '가지)')
                                        : ('“' + res.data.query + '” — 찾은 항목이 없습니다(내 보기 범위 안).'));
    groups.forEach(function (group) { results.appendChild(renderGroup(group)); });
  }

  if (form) {
    form.addEventListener('submit', function (event) {
      event.preventDefault();
      runSearch(input ? input.value : '');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    fire('brain:tab', { tab: ctx.current });
    if (ctx.current === 'search' && ctx.query) runSearch(ctx.query);
    else if (ctx.current === 'search' && input) input.focus();
  });

  ctx.view = view;
})();
