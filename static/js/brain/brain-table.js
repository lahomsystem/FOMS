/**
 * 회사 지식 '지식 표' 탭(HAUD master brain 설계서 7.5 화면 2) — 유형 하나를 표로. 거르기(층 · 브랜드 · 상태 · 등급 · 확신 ·
 * 확인 필요/낡음) · 정렬(쓰인 횟수 · 마지막 확인 · 이름) · 쪽. GET /api/brain/table(보기 범위로 거른 줄 · 수만 온다).
 * 줄은 textContent 로만 그리고, 유형 색 · 상태 모양은 클래스로(인라인 스타일 없음). 탭이 처음 보일 때 읽는다.
 */
(function () {
  'use strict';

  var ctx = window.FOMS_BRAIN_CTX;
  if (!ctx || window.__FOMS_BRAIN_TABLE_BOUND) return;
  window.__FOMS_BRAIN_TABLE_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var root = ctx.root;
  var form = root.querySelector('[data-brain-table-form]');
  var body = root.querySelector('[data-brain-table-body]');
  var status = root.querySelector('[data-brain-table-status]');
  var prev = root.querySelector('[data-brain-page-prev]');
  var next = root.querySelector('[data-brain-page-next]');
  var pageText = root.querySelector('[data-brain-page-text]');
  if (!form || !body) return;

  var state = { page: 1 };
  var loaded = false;
  var seq = 0;

  function readForm() {
    form.querySelectorAll('[data-brain-filter]').forEach(function (select) {
      state[select.getAttribute('data-brain-filter')] = select.value;
    });
  }

  function setFilter(name, value) {
    var select = form.querySelector('[data-brain-filter="' + name + '"]');
    if (select) select.value = value;
  }

  /** 유형 고르기 칸의 이름 옆에 수(볼 수 있는 것만)를 붙인다. */
  function updateTypeCounts(counts) {
    var select = form.querySelector('[data-brain-filter="type"]');
    if (!select) return;
    Array.prototype.forEach.call(select.options, function (option) {
      var label = option.getAttribute('data-label') || option.textContent;
      option.textContent = label + ' (' + (counts[option.value] || 0) + ')';
    });
  }

  /** 처음 고를 유형 — 주소의 유형, 없으면 항목이 있는 첫 유형. */
  function pickStartType(counts) {
    if (ctx.startType) return ctx.startType;
    var order = (ctx.display && ctx.display.type_order) || [];
    for (var i = 0; i < order.length; i += 1) if ((counts || {})[order[i]]) return order[i];
    return order[0] || '';
  }

  function cell(text, cls) {
    return dom.el('td', { cls: cls || null, text: text === null || text === undefined || text === '' ? '—' : text });
  }

  function renderRow(item) {
    var labels = ctx.display;
    var classes = ['brain-row', 'brain-type--' + item.type].concat(view.stateClasses(item));
    var tr = dom.el('tr', { cls: classes.join(' ') });
    var nameCell = dom.el('td');
    nameCell.appendChild(dom.el('a', { cls: 'brain-item__name', text: item.name,
                                       attrs: { href: view.itemHref(ctx.itemBase, item.key) } }));
    if (item.stale) nameCell.appendChild(dom.el('span', { cls: 'brain-badge brain-badge--stale ms-1', text: '낡음' }));
    if (item.needs_check) nameCell.appendChild(dom.el('span', { cls: 'brain-badge brain-badge--check ms-1', text: '확인 필요' }));
    tr.appendChild(nameCell);
    tr.appendChild(cell((labels.layers || {})[item.layer] || item.layer));
    tr.appendChild(cell((labels.brands || {})[item.brand] || item.brand));
    tr.appendChild(cell((labels.statuses || {})[item.status] || item.status));
    tr.appendChild(cell((labels.confidences || {})[item.confidence] || item.confidence));
    tr.appendChild(cell(item.grade ? ((labels.grades || {})[item.grade] || item.grade) : ''));
    tr.appendChild(cell(String(item.usage_count || 0), 'brain-num'));
    tr.appendChild(cell(item.checked_at));
    tr.appendChild(cell(item.stale_after));
    return tr;
  }

  async function load() {
    readForm();
    var mySeq = ++seq;
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(ctx.urls.table + '?' + view.tableParams(state));
    if (mySeq !== seq) return;
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    var data = res.data;
    loaded = true;
    state.page = data.page;
    updateTypeCounts(data.type_counts || {});
    dom.clear(body);
    data.rows.forEach(function (item) { body.appendChild(renderRow(item)); });
    var info = view.pager(data.page, data.pages, data.total, data.per_page);
    if (pageText) pageText.textContent = info.text;
    if (prev) prev.disabled = !info.hasPrev;
    if (next) next.disabled = !info.hasNext;
    dom.setStatus(status, data.total ? (data.total + '개') : '조건에 맞는 지식이 없어요.');  // 유형 이름은 위 고르기 칸에
    ctx.syncUrl({ type: data.type });
  }

  /** 처음 열 때 — 유형 수를 먼저 알아야 '항목이 있는 첫 유형'을 고른다(지도 자료의 수를 쓴다). */
  async function firstLoad() {
    if (!ctx.startType) {
      var map = await dom.getJson(ctx.urls.typeMap);
      var counts = {};
      if (map.ok) map.data.groups.forEach(function (g) { g.types.forEach(function (t) { counts[t.type] = t.count; }); });
      setFilter('type', pickStartType(counts));
    } else {
      setFilter('type', ctx.startType);
    }
    state.page = 1;
    await load();
  }

  form.addEventListener('change', function (event) {
    if (!event.target.closest('[data-brain-filter]')) return;
    state.page = 1;
    load();
  });
  if (prev) prev.addEventListener('click', function () { state.page = Math.max(1, (state.page || 1) - 1); load(); });
  if (next) next.addEventListener('click', function () { state.page = (state.page || 1) + 1; load(); });

  root.addEventListener('brain:tab', function (event) {
    if (event.detail.tab !== 'table') return;
    if (!loaded) firstLoad();
    else ctx.syncUrl({ type: state.type });
  });
  root.addEventListener('brain:open-table', function (event) {
    var type = event.detail.type;
    if (!type) return;
    ctx.startType = type;
    setFilter('type', type);
    state.page = 1;
    loaded = true;  // 아래 load 가 그린다 — 탭 이벤트가 firstLoad 를 겹쳐 부르지 않게
    load();
  });
})();
