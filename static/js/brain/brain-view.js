/**
 * 회사 지식 화면 순수 함수(HAUD master brain 설계서 7.5 '앱 코드' — 받은 자료 → 그림 요소, 유형 → 색). DOM 을 만지지 않는다.
 *
 * 표시 표(display)는 서버 foms/services/brain/display.py 가 data-display 로 싣는다 — 유형 색 · 아이콘 · 이름이 모든 화면에서 같다.
 * 상태는 모양 클래스로(은퇴 회색 · 초안 점선 · 낡음 주황 테두리 — brain.css). 유형 지도 그림 요소는 묶음(공통 바탕 · 상담 층 …)을
 * 겹 노드로 두고, 링크 끝이 묶음 전체면 묶음 하나로 줄이고(관찰 → 정체 항목 전체 같은 실뭉치를 막는다) 같은 두 끝의 선은 하나로
 * 합친다. window.FOMS_BRAIN_VIEW 로 내놓고 node 에서는 module.exports — tests/domains/test_brain_screens_js.py.
 */
(function (root) {
  'use strict';

  var FALLBACK_COLOR = '#475569';

  /** 유형 → {label, color, icon}. 모르는 유형은 키 그대로 · 회청색. */
  function typeInfo(display, type) {
    var t = display && display.types && display.types[type];
    return t ? { label: t.label, color: t.color, icon: t.icon } : { label: String(type || ''), color: FALLBACK_COLOR, icon: 'fa-circle' };
  }

  /** 링크 종류 → {label, color, out, in}. */
  function linkInfo(display, kind) {
    var l = display && display.links && display.links[kind];
    return l ? l : { label: String(kind || ''), color: FALLBACK_COLOR, out: String(kind || ''), in: String(kind || '') };
  }

  /** 상태 모양 클래스 — 초안 점선 · 은퇴 회색 · 낡음 주황 테두리(겹칠 수 있다). */
  function stateClasses(item) {
    var out = [];
    if (item && item.status === 'draft') out.push('brain-state--draft');
    if (item && item.status === 'retired') out.push('brain-state--retired');
    if (item && item.stale) out.push('brain-state--stale');
    return out;
  }

  /** 줄 옆 작은 표 — 상태(반영 아니면) · 확신 · 낡음 · 확인 필요. [{text, cls}] */
  function badges(item, display) {
    var out = [];
    var labels = display || {};
    if (item.status && item.status !== 'active') {
      out.push({ text: (labels.statuses || {})[item.status] || item.status, cls: 'brain-badge--' + item.status });
    }
    if (item.confidence) {
      out.push({ text: (labels.confidences || {})[item.confidence] || item.confidence, cls: 'brain-badge--' + item.confidence });
    }
    if (item.stale) out.push({ text: '낡음', cls: 'brain-badge--stale' });
    if (item.needs_check) out.push({ text: '확인 필요', cls: 'brain-badge--check' });
    return out;
  }

  var TABLE_KEYS = ['type', 'layer', 'brand', 'status', 'grade', 'confidence', 'check', 'sort'];

  /** 지식 표 물음 글(정한 차례 · 빈 값 빼고 · 쪽은 2 이상만). */
  function tableParams(state) {
    var parts = [];
    TABLE_KEYS.forEach(function (key) {
      var value = state && state[key];
      if (value) parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(String(value)));
    });
    if (state && Number(state.page) > 1) parts.push('page=' + Math.floor(Number(state.page)));
    return parts.join('&');
  }

  /** 쪽 안내 — {hasPrev, hasNext, text}. */
  function pager(page, pages, total, perPage) {
    var p = Math.max(1, Number(page) || 1);
    var last = Math.max(1, Number(pages) || 1);
    var size = Math.max(1, Number(perPage) || 1);
    var count = Math.max(0, Number(total) || 0);
    var from = count ? (p - 1) * size + 1 : 0;
    var to = Math.min(count, p * size);
    return { hasPrev: p > 1, hasNext: p < last,
             text: count ? (from + '–' + to + ' / 모두 ' + count + '개 (' + p + '/' + last + '쪽)') : '0개' };
  }

  /** 항목 카드 주소 — 키의 '/' 마디는 그대로, 마디 안 글자는 이스케이프. */
  function itemHref(base, key) {
    return String(base || '') + String(key || '').split('/').map(encodeURIComponent).join('/');
  }

  /** 판 한 층의 동작 수 → '새로 만듦 3 · 고침 1'. */
  function countsText(counts, display) {
    var ops = (display && display.ops) || {};
    return Object.keys(counts || {}).sort().map(function (op) {
      return (ops[op] || op) + ' ' + counts[op];
    }).join(' · ');
  }

  /** 유형 목록을 줄인다 — 묶음을 통째로 덮으면 묶음 노드 id 하나('g:키'), 나머지는 유형 노드 id('t:유형'). */
  function compressEnds(types, groups) {
    var wanted = {};
    types.forEach(function (t) { wanted[t] = true; });
    var out = [];
    (groups || []).forEach(function (g) {
      var members = (g.types || []).map(function (t) { return t.type || t; });
      var all = members.length > 1 && members.every(function (t) { return wanted[t]; });
      if (!all) return;
      out.push('g:' + g.key);
      members.forEach(function (t) { delete wanted[t]; });
    });
    types.forEach(function (t) { if (wanted[t]) out.push('t:' + t); });
    return out;
  }

  function uniq(list) {
    var seen = {};
    return list.filter(function (x) { if (seen[x]) return false; seen[x] = true; return true; });
  }

  /** 유형 지도 자료(GET /api/brain/type-map) → Cytoscape 요소 배열(묶음 겹 노드 · 유형 노드 · 합친 선). */
  function mapElements(map, display) {
    var els = [];
    var groups = (map && map.groups) || [];
    groups.forEach(function (g) {
      els.push({ group: 'nodes', data: { id: 'g:' + g.key, label: g.label, kind: 'group' }, classes: 'brain-map-group' });
      (g.types || []).forEach(function (t) {
        var info = typeInfo(display, t.type);
        var label = t.external ? info.label : info.label + '\n' + (t.count || 0) + '개';
        els.push({ group: 'nodes', classes: 'brain-map-type' + (t.external ? ' is-external' : '') + (t.count ? '' : ' is-empty'),
                   data: { id: 't:' + t.type, parent: 'g:' + g.key, type: t.type, label: label, color: info.color,
                           count: t.count || 0, external: !!t.external, kind: 'type' } });
      });
    });
    var merged = {};
    var order = [];
    ((map && map.links) || []).forEach(function (link) {
      var pairs = link.pairs || [];
      if (!pairs.length) return;
      var starts = compressEnds(uniq(pairs.map(function (p) { return p[0]; })), groups);
      var ends = compressEnds(uniq(pairs.map(function (p) { return p[1]; })), groups);
      starts.forEach(function (s) {
        ends.forEach(function (d) {
          var key = s + '>' + d;
          if (!merged[key]) { merged[key] = { source: s, target: d, kinds: [] }; order.push(key); }
          if (merged[key].kinds.indexOf(link.kind) < 0) merged[key].kinds.push(link.kind);
        });
      });
    });
    order.forEach(function (key) {
      var e = merged[key];
      var first = linkInfo(display, e.kinds[0]);
      els.push({ group: 'edges', classes: 'brain-map-edge',
                 data: { id: 'e:' + key, source: e.source, target: e.target, kinds: e.kinds.slice(), color: first.color,
                         label: e.kinds.map(function (k) { return linkInfo(display, k).label; }).join(' · ') } });
    });
    return els;
  }

  /** 유형 지도 그림 모양(Cytoscape stylesheet — 자료만). 글꼴은 화면 본문 글꼴을 받아 한글이 비지 않게. */
  function mapStyle(fontFamily) {
    var font = fontFamily || "'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif";
    return [
      { selector: 'node.brain-map-type', style: {
        shape: 'round-rectangle', width: 118, height: 48, 'background-color': 'data(color)', label: 'data(label)',
        color: '#ffffff', 'font-family': font, 'font-size': 13, 'font-weight': 600, 'text-wrap': 'wrap',
        'text-max-width': 110, 'text-valign': 'center', 'text-halign': 'center', 'line-height': 1.25 } },
      { selector: 'node.is-empty', style: { 'background-opacity': 0.55 } },
      { selector: 'node.is-external', style: { shape: 'cut-rectangle' } },
      { selector: 'node.brain-map-group', style: {
        shape: 'round-rectangle', 'background-color': '#f8fafc', 'border-color': '#cbd5e1', 'border-width': 1,
        label: 'data(label)', 'text-valign': 'top', 'text-halign': 'center', color: '#334155', 'font-family': font,
        'font-size': 14, 'font-weight': 700, padding: 16, 'text-margin-y': -4 } },
      { selector: 'edge', style: {
        width: 1.6, 'line-color': 'data(color)', 'target-arrow-color': 'data(color)', 'target-arrow-shape': 'triangle',
        'curve-style': 'bezier', 'arrow-scale': 0.9, opacity: 0.7, 'font-family': font } },
      { selector: 'edge:loop', style: {  // 제품 → 제품 같은 같은 유형 짝(필요 · 제외)
        'curve-style': 'unbundled-bezier', 'loop-direction': '0deg', 'loop-sweep': '-70deg',
        'control-point-step-size': 46 } },
      { selector: 'edge.is-lit', style: {
        label: 'data(label)', width: 3, opacity: 1, 'z-index': 10, 'font-size': 12, color: '#111827',
        'text-background-color': '#ffffff', 'text-background-opacity': 1, 'text-background-padding': 2 } },
      { selector: 'node.is-lit', style: { 'border-width': 3, 'border-color': '#111827' } },
      { selector: '.is-dim', style: { opacity: 0.2 } }
    ];
  }

  var api = { typeInfo: typeInfo, linkInfo: linkInfo, stateClasses: stateClasses, badges: badges, tableParams: tableParams,
              pager: pager, itemHref: itemHref, countsText: countsText, compressEnds: compressEnds, mapElements: mapElements,
              mapStyle: mapStyle };
  root.FOMS_BRAIN_VIEW = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
