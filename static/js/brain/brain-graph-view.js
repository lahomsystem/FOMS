/**
 * 항목 카드 '이웃 지도' 순수 함수(HAUD master brain 설계서 7.5 화면 9 · 7.7 이웃 찾기) — DOM 을 만지지 않는다(node 시험).
 *
 * - 이웃 찾기 물음 글(aroundParams) · 받은 자료 → Cytoscape 요소(aroundElements — 시작 항목 · 이웃 · 선, 색은 표시 표 하나)
 * - 종류 칩(chipModel — 종류마다 이름 · 수 · 켜짐, 링크 종류 차례) · 켜진 종류 바꾸기(toggleKind — 하나는 늘 켜진 채)
 * - 고른 항목과 이어진 키(related — 나머지는 숨기지 않고 흐리게) · 목록 줄 차례(listRows — 걸음 → 이름)
 * - 그림 모양(graphStyle — 자료만, 화면 글꼴을 받아 한글이 비지 않게)
 * window.FOMS_BRAIN_GRAPH 로 내놓고 node 에서는 module.exports — tests/domains/test_brain_graph_js.py.
 */
(function (root) {
  'use strict';

  var FALLBACK = '#475569';

  function typeColor(display, type) {
    var t = display && display.types && display.types[type];
    return t ? t.color : FALLBACK;
  }

  function linkMeta(display, kind) {
    var l = display && display.links && display.links[kind];
    return l ? { label: l.label, color: l.color } : { label: String(kind || ''), color: FALLBACK };
  }

  /** 이웃 찾기 물음 글 — key · kinds(쉼표, 모두면 뺌) · depth · limit. */
  function aroundParams(q) {
    var parts = ['key=' + encodeURIComponent(String(q.key || ''))];
    if (q.kinds && q.kinds.length) parts.push('kinds=' + q.kinds.map(encodeURIComponent).join(','));
    parts.push('depth=' + (Number(q.depth) === 2 ? 2 : 1));
    if (q.limit) parts.push('limit=' + Math.max(1, Math.floor(Number(q.limit))));
    return parts.join('&');
  }

  function stateClass(item) {
    var out = [];
    if (item.status === 'draft') out.push('is-draft');
    if (item.status === 'retired') out.push('is-retired');
    if (item.stale) out.push('is-stale');
    return out;
  }

  /** 이웃 찾기 답 → Cytoscape 요소 배열(시작 항목 is-start · 이웃 is-depth1 · is-depth2 · 선은 종류 색). */
  function aroundElements(data, display) {
    var els = [];
    var start = data.start;
    els.push({ group: 'nodes', classes: ['is-start'].concat(stateClass(start)).join(' '),
               data: { id: start.key, label: start.name, type: start.type, color: typeColor(display, start.type), depth: 0 } });
    (data.items || []).forEach(function (it) {
      els.push({ group: 'nodes', classes: ['is-depth' + it.depth].concat(stateClass(it)).join(' '),
                 data: { id: it.key, label: it.name, type: it.type, color: typeColor(display, it.type), depth: it.depth } });
    });
    (data.edges || []).forEach(function (e) {
      var meta = linkMeta(display, e.kind);
      els.push({ group: 'edges', classes: 'brain-nb-edge',
                 data: { id: e.kind + ':' + e.from + '>' + e.to, source: e.from, target: e.to, kind: e.kind,
                         color: meta.color, label: meta.label } });
    });
    return els;
  }

  /** 종류 칩 — 링크 종류 차례, 수가 있거나 켜진 종류만. active 가 비면 모두 켜짐. */
  function chipModel(counts, display, active, order) {
    var on = active && active.length ? active : null;
    return (order || Object.keys(counts || {})).filter(function (kind) {
      return (counts && counts[kind]) || (on && on.indexOf(kind) >= 0);
    }).map(function (kind) {
      var meta = linkMeta(display, kind);
      return { kind: kind, label: meta.label, color: meta.color, count: (counts && counts[kind]) || 0,
               on: !on || on.indexOf(kind) >= 0 };
    });
  }

  /** 켜진 종류 바꾸기 — 모두 켜짐(빈 목록)에서 누르면 그 종류만 끄고, 마지막 하나는 끌 수 없다. 모두 켜지면 빈 목록. */
  function toggleKind(active, kind, available) {
    var all = available.slice();
    var on = active && active.length ? active.slice() : all.slice();
    var at = on.indexOf(kind);
    if (at >= 0) {
      if (on.length === 1) return active ? active.slice() : [];
      on.splice(at, 1);
    } else {
      on.push(kind);
    }
    var ordered = all.filter(function (k) { return on.indexOf(k) >= 0; });
    return ordered.length === all.length ? [] : ordered;
  }

  /** 고른 키와 선으로 바로 이어진 키들(고른 키 포함) — 나머지는 흐리게. */
  function related(edges, key) {
    var out = {};
    out[key] = true;
    (edges || []).forEach(function (e) {
      if (e.from === key) out[e.to] = true;
      if (e.to === key) out[e.from] = true;
    });
    return Object.keys(out).sort();
  }

  /** 목록 줄 차례 — 걸음 → 이름 → 키. */
  function listRows(data) {
    return (data.items || []).slice().sort(function (a, b) {
      return (a.depth - b.depth) || String(a.name).localeCompare(String(b.name), 'ko') || (a.key < b.key ? -1 : 1);
    });
  }

  /** 그림 모양(Cytoscape stylesheet — 자료만). */
  function graphStyle(fontFamily) {
    var font = fontFamily || "'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif";
    return [
      { selector: 'node', style: {
        width: 18, height: 18, 'background-color': 'data(color)', label: 'data(label)', 'font-family': font,
        'font-size': 12, color: '#1f2937', 'text-valign': 'bottom', 'text-margin-y': 4, 'text-wrap': 'ellipsis',
        'text-max-width': 140, 'border-width': 2, 'border-color': '#ffffff' } },
      { selector: 'node.is-start', style: { width: 30, height: 30, 'font-size': 14, 'font-weight': 700,
                                            'border-color': '#111827', 'border-width': 3 } },
      { selector: 'node.is-depth2', style: { width: 13, height: 13, 'font-size': 11, color: '#4b5563' } },
      { selector: 'node.is-draft', style: { 'border-style': 'dashed', 'border-color': '#6b7280' } },
      { selector: 'node.is-retired', style: { 'background-color': '#9ca3af', color: '#6b7280' } },
      { selector: 'node.is-stale', style: { 'border-color': '#ea580c', 'border-width': 3 } },
      { selector: 'edge', style: {
        width: 1.6, 'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle',
        'arrow-scale': 0.8, 'curve-style': 'bezier', opacity: 0.75, 'font-family': font } },
      { selector: 'node.is-selected', style: { 'border-color': '#1d4ed8', 'border-width': 4, 'z-index': 10 } },
      { selector: 'edge.is-lit', style: { width: 3, opacity: 1, label: 'data(label)', 'font-size': 11, color: '#111827',
                                          'text-background-color': '#ffffff', 'text-background-opacity': 1,
                                          'text-background-padding': 2, 'z-index': 9 } },
      { selector: '.is-dim', style: { opacity: 0.18 } }
    ];
  }

  var api = { aroundParams: aroundParams, aroundElements: aroundElements, chipModel: chipModel, toggleKind: toggleKind,
              related: related, listRows: listRows, graphStyle: graphStyle };
  root.FOMS_BRAIN_GRAPH = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
