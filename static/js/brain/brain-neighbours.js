/**
 * 항목 카드 '이웃 지도' 탭(HAUD master brain 설계서 7.5 화면 9 · 7.7 이웃 찾기) — templates/brain/partials/card_neighbours.html.
 *
 * - **진짜 화면은 HTML 이웃 목록**(서버가 1걸음을 그려 둔다 — 키보드 · 화면 읽기). 그림은 돕는 쪽이고 둘이 맞물린다: 그림의 점을
 *   누르면 목록 줄이 골라지고(스크롤), 목록의 '고르기'를 누르면 그림의 점이 골라진다. 고른 항목과 이어지지 않은 것은 숨기지
 *   않고 흐리게.
 * - 걸음 1(기본) · 2, 링크 종류별 펼치기 칩(수 표시 — 모든 종류로 센 수). 바꾸면 GET /api/brain/around 를 다시 읽는다
 *   (보기 범위는 서버가 점 · 선 · 수 모두에 건다).
 * - 그림 라이브러리(Cytoscape.js 3.34.4 — static/vendor)는 **이 탭을 처음 열 때만** import(). 못 읽으면 목록만으로 모든 동작.
 * - fetch 는 brain-dom.js requestJson 한 곳(try/catch + data.success), 글은 textContent 만, 인라인 스타일 없음.
 */
(function () {
  'use strict';

  if (window.__FOMS_BRAIN_NB_BOUND) return;
  var root = document.querySelector('[data-brain-nb]');
  var card = document.querySelector('[data-brain-card]');
  if (!root || !card) return;
  window.__FOMS_BRAIN_NB_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var graph = window.FOMS_BRAIN_GRAPH;
  var display = dom.safeJsonParse(card.getAttribute('data-display'), {});
  var order = dom.safeJsonParse(root.getAttribute('data-link-order'), []);
  var button = document.getElementById('brain-card-neighbours-btn');
  var canvas = root.querySelector('[data-brain-nb-canvas]');
  var list = root.querySelector('[data-brain-nb-list]');
  var chips = root.querySelector('[data-brain-nb-chips]');
  var status = root.querySelector('[data-brain-nb-status]');
  var startKey = card.getAttribute('data-brain-key');
  var itemBase = card.getAttribute('data-item-base');
  var state = { depth: 1, kinds: [], data: null, counts: {}, selected: null };
  var cy = null;
  var started = false;
  var seq = 0;

  function fetchAround(depth, kinds) {
    return dom.getJson(root.getAttribute('data-around-url') + '?' +
                       graph.aroundParams({ key: startKey, depth: depth, kinds: kinds, limit: 120 }));
  }

  function renderChips() {
    dom.clear(chips);
    graph.chipModel(state.counts[state.depth] || {}, display, state.kinds, order).forEach(function (chip) {
      var b = dom.el('button', { cls: 'brain-nb__chip brain-link--' + chip.kind, attrs: {
        type: 'button', 'data-brain-nb-kind': chip.kind, 'aria-pressed': chip.on ? 'true' : 'false' } });
      b.appendChild(dom.el('span', { cls: 'brain-swatch', attrs: { 'aria-hidden': 'true' } }));
      b.appendChild(document.createTextNode(chip.label + ' ' + chip.count));
      chips.appendChild(b);
    });
  }

  function renderList(data) {
    dom.clear(list);
    var rows = graph.listRows(data);
    rows.forEach(function (it) {
      var row = dom.el('li', { cls: ['brain-item', 'brain-type--' + it.type].concat(view.stateClasses(it)).join(' '),
                               attrs: { 'data-brain-nb-key': it.key } });
      row.appendChild(dom.typeChip(display, it.type));
      row.appendChild(dom.el('button', { cls: 'brain-nb__pick', text: it.name, attrs: {
        type: 'button', 'data-brain-nb-select': it.key, 'aria-pressed': 'false', title: '그림에서 고르기' } }));
      row.appendChild(dom.el('span', { cls: 'brain-nb__via', text: it.depth + '걸음 · ' + it.via.map(function (k) {
        return view.linkInfo(display, k).label;
      }).join(' · ') }));
      row.appendChild(dom.el('a', { cls: 'brain-btn', text: '카드', attrs: { href: view.itemHref(itemBase, it.key) } }));
      list.appendChild(row);
    });
    if (!rows.length) list.appendChild(dom.el('li', { cls: 'brain-empty', text: '이어진 항목이 없습니다(내 보기 범위 안).' }));
  }

  function layout() {
    return { name: 'concentric', animate: false, fit: true, padding: 24, minNodeSpacing: 46, startAngle: Math.PI / 2,
             concentric: function (node) { return 3 - node.data('depth'); }, levelWidth: function () { return 1; } };
  }

  function renderGraph(data) {
    if (!cy) return;
    cy.elements().remove();
    cy.add(graph.aroundElements(data, display));
    cy.layout(layout()).run();
  }

  /** 고르기 — 그림 · 목록 둘 다. 고른 것과 이어지지 않은 점 · 선은 흐리게(숨기지 않음). */
  function select(key, from) {
    state.selected = key;
    var keep = key ? graph.related(state.data ? state.data.edges : [], key) : [];
    list.querySelectorAll('[data-brain-nb-key]').forEach(function (row) {
      var on = row.getAttribute('data-brain-nb-key') === key;
      row.classList.toggle('is-selected', on);
      row.classList.toggle('is-dim', !!key && keep.indexOf(row.getAttribute('data-brain-nb-key')) < 0);
      var pick = row.querySelector('[data-brain-nb-select]');
      if (pick) pick.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on && from === 'graph') row.scrollIntoView({ block: 'nearest' });
    });
    if (cy) {
      cy.elements().removeClass('is-dim is-selected is-lit');
      if (key) {
        cy.nodes().forEach(function (n) { if (keep.indexOf(n.id()) < 0) n.addClass('is-dim'); });
        cy.edges().forEach(function (e) {
          var touch = e.data('source') === key || e.data('target') === key;
          e.addClass(touch ? 'is-lit' : 'is-dim');
        });
        cy.getElementById(key).addClass('is-selected');
      }
    }
    var name = key && cy && !cy.getElementById(key).empty() ? cy.getElementById(key).data('label') : '';
    if (key && from !== 'refresh') {
      dom.setStatus(status, '고른 항목: ' + (name || key) + ' — 이어진 ' + (keep.length - 1) + '개를 밝히고 나머지는 흐리게 했습니다.');
    }
  }

  function summary(data) {
    return state.depth + '걸음 이웃 ' + data.total + '개' + (data.truncated ? '(앞 ' + data.items.length + '개만)' : '') +
           ' · 선 ' + data.edges.length + '개 — 점이나 목록의 이름을 누르면 그 항목과 이어진 것만 밝힙니다.';
  }

  async function refresh() {
    var mine = ++seq;
    dom.setStatus(status, '이웃을 읽는 중…');
    var wants = [fetchAround(state.depth, state.kinds)];
    if (state.kinds.length && !state.counts[state.depth]) wants.push(fetchAround(state.depth, []));
    var results = await Promise.all(wants);
    if (mine !== seq) return;  // 더 늦은 바꿈이 이미 나갔다
    var failed = results.find(function (r) { return !r.ok; });
    if (failed) {
      dom.setStatus(status, failed.error, 'error');
      return;
    }
    var data = results[0].data;
    if (!state.kinds.length) state.counts[state.depth] = data.counts;
    else if (results[1]) state.counts[state.depth] = results[1].data.counts;
    state.data = data;
    renderChips();
    renderList(data);
    renderGraph(data);
    dom.setStatus(status, summary(data));
    if (state.selected && (state.selected === startKey || data.items.some(function (i) { return i.key === state.selected; }))) {
      select(state.selected, 'refresh');  // 다시 읽어도 고른 것은 그대로(알림 줄은 새 요약)
    } else {
      state.selected = null;
    }
  }

  async function loadGraph() {
    try {
      var mod = await import(root.getAttribute('data-cytoscape-url'));
      var cytoscape = mod.default;
      if (typeof cytoscape !== 'function') throw new Error('library shape');
      cy = cytoscape({ container: canvas, elements: [], style: graph.graphStyle(window.getComputedStyle(document.body).fontFamily),
                       minZoom: 0.3, maxZoom: 3, boxSelectionEnabled: false, autoungrabify: false });
      cy.on('tap', 'node', function (event) { select(event.target.id(), 'graph'); });
      cy.on('tap', function (event) { if (event.target === cy) select(null); });
      cy.on('dbltap', 'node', function (event) {
        if (event.target.id() !== startKey) window.location.href = view.itemHref(itemBase, event.target.id());
      });
    } catch (error) {
      cy = null;
      canvas.classList.add('is-failed');
      dom.setStatus(status, '그림 라이브러리를 읽지 못했습니다 — 옆 목록으로 모두 할 수 있어요.', 'error');
    }
  }

  async function open() {
    if (started) {
      if (cy) { cy.resize(); cy.fit(undefined, 24); }
      return;
    }
    started = true;
    await loadGraph();
    await refresh();
  }

  root.addEventListener('click', function (event) {
    var depth = event.target.closest('[data-brain-nb-depth]');
    if (depth) {
      state.depth = Number(depth.getAttribute('data-brain-nb-depth')) === 2 ? 2 : 1;
      root.querySelectorAll('[data-brain-nb-depth]').forEach(function (b) {
        b.setAttribute('aria-pressed', b === depth ? 'true' : 'false');
      });
      refresh();
      return;
    }
    var chip = event.target.closest('[data-brain-nb-kind]');
    if (chip) {
      var available = graph.chipModel(state.counts[state.depth] || {}, display, [], order).map(function (c) { return c.kind; });
      state.kinds = graph.toggleKind(state.kinds, chip.getAttribute('data-brain-nb-kind'), available);
      refresh();
      return;
    }
    var pick = event.target.closest('[data-brain-nb-select]');
    if (pick) select(pick.getAttribute('data-brain-nb-select'), 'list');
  });
  if (button) button.addEventListener('shown.bs.tab', open);
  if (window.location.hash === '#neighbours' && button && window.bootstrap && window.bootstrap.Tab) {
    window.bootstrap.Tab.getOrCreateInstance(button).show();
  }
})();
