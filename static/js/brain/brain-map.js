/**
 * 회사 지식 '유형 지도' 탭 그림(HAUD master brain 설계서 7.5 화면 7 · 라이브러리) — 유형 · 링크 종류 전체 한 장을 위에서 아래로.
 *
 * - 그림 라이브러리는 **이 탭을 처음 열 때만** import() 한다: Cytoscape.js 3.34.4(ESM) + cytoscape-dagre 4.0.1(ESM, dagre 묶음).
 *   주소는 서버가 asset_url(내용 해시 ?v=)로 data-cytoscape-url · data-dagre-url 에 싣는다(static/vendor/cytoscape-NOTICE.txt).
 * - 자료는 GET /api/brain/type-map(수는 내 보기 범위 안) → 순수 함수 FOMS_BRAIN_VIEW.mapElements · mapStyle 로 요소 · 모양.
 * - 유형을 누르면 지식 표가 그 유형으로 열린다('brain:open-table'). 진짜 화면은 아래 HTML 목록이고 그림은 돕는 쪽 —
 *   목록 줄에 마우스 · 초점이 오면 그림의 그 유형을 밝히고, 그림의 유형에 마우스가 오면 목록 줄을 밝힌다(맞물림).
 * - 그림을 못 그리면(라이브러리 · 자료 실패) 알림 줄에 까닭을 쓰고 목록은 그대로 쓴다.
 */
(function () {
  'use strict';

  var ctx = window.FOMS_BRAIN_CTX;
  if (!ctx || window.__FOMS_BRAIN_MAP_BOUND) return;
  window.__FOMS_BRAIN_MAP_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var root = ctx.root;
  var canvas = root.querySelector('[data-brain-map-canvas]');
  var status = root.querySelector('[data-brain-map-status]');
  if (!canvas) return;

  var cy = null;
  var started = false;

  /** 라이브러리 둘을 한 번만 읽어 dagre 배치를 등록한다. */
  async function loadLibraries() {
    var mods = await Promise.all([import(ctx.urls.cytoscape), import(ctx.urls.dagre)]);
    var cytoscape = mods[0].default;
    var dagre = mods[1].default;
    if (typeof cytoscape !== 'function' || typeof dagre !== 'function') throw new Error('library shape');
    if (!window.__FOMS_BRAIN_DAGRE_USED) {
      cytoscape.use(dagre);
      window.__FOMS_BRAIN_DAGRE_USED = true;
    }
    return cytoscape;
  }

  function listRow(type) {
    return root.querySelector('[data-brain-map-type="' + type + '"]');
  }

  /** 한 유형과 그 선을 밝히고 나머지를 흐리게(이름표는 밝힌 선에만). */
  function light(type) {
    if (!cy) return;
    cy.elements().removeClass('is-lit is-dim');
    root.querySelectorAll('.brain-map__type.is-lit').forEach(function (row) { row.classList.remove('is-lit'); });
    if (!type) return;
    var node = cy.getElementById('t:' + type);
    if (node.empty()) return;
    var parent = node.parent();
    var edges = node.connectedEdges().union(parent.connectedEdges());
    var keep = node.union(edges).union(edges.connectedNodes()).union(parent);
    cy.elements().difference(keep).difference(keep.ancestors()).addClass('is-dim');
    node.addClass('is-lit');
    edges.addClass('is-lit');
    var row = listRow(type);
    if (row) row.classList.add('is-lit');
  }

  function bindCanvas() {
    cy.on('tap', 'node.brain-map-type', function (event) {
      var data = event.target.data();
      if (data.external) {
        dom.setStatus(status, data.label + ' — brain 은 이 자리를 가리키기만 합니다(값은 그 자리가 정본).');
        return;
      }
      ctx.fire('brain:open-table', { type: data.type });
    });
    cy.on('mouseover', 'node.brain-map-type', function (event) { light(event.target.data('type')); });
    cy.on('mouseout', 'node.brain-map-type', function () { light(null); });
    cy.on('mouseover', 'edge', function (event) { event.target.addClass('is-lit'); });
    cy.on('mouseout', 'edge', function (event) { event.target.removeClass('is-lit'); });
  }

  function bindList() {
    root.querySelectorAll('[data-brain-map-type]').forEach(function (row) {
      var type = row.getAttribute('data-brain-map-type');
      row.addEventListener('mouseenter', function () { light(type); });
      row.addEventListener('mouseleave', function () { light(null); });
      row.addEventListener('focusin', function () { light(type); });
      row.addEventListener('focusout', function () { light(null); });
    });
  }

  async function draw() {
    dom.setStatus(status, '유형 지도를 그리는 중…');
    var results;
    try {
      results = await Promise.all([loadLibraries(), dom.getJson(ctx.urls.typeMap)]);
    } catch (error) {
      started = false;  // 다음에 탭을 열 때 다시 해 본다
      dom.setStatus(status, '그림 라이브러리를 읽지 못했습니다 — 아래 목록으로 보세요.', 'error');
      return;
    }
    var cytoscape = results[0];
    var res = results[1];
    if (!res.ok) {
      started = false;
      dom.setStatus(status, res.error + ' — 아래 목록으로 보세요.', 'error');
      return;
    }
    var display = res.data.display || ctx.display;
    var font = window.getComputedStyle(document.body).fontFamily;
    cy = cytoscape({
      container: canvas,
      elements: view.mapElements(res.data, display),
      style: view.mapStyle(font),
      layout: { name: 'dagre', rankDir: 'TB', nodeSep: 18, rankSep: 70, edgeSep: 8, padding: 16, fit: true },
      minZoom: 0.3, maxZoom: 3, boxSelectionEnabled: false, autoungrabify: true
    });
    bindCanvas();
    dom.setStatus(status, '유형 ' + cy.nodes('.brain-map-type').length + '가지 · 선 ' + cy.edges().length +
                  '개 — 유형을 누르면 지식 표가 열립니다. 마우스를 올리면 그 유형의 선 이름이 보입니다.');
  }

  bindList();
  root.addEventListener('brain:tab', function (event) {
    if (event.detail.tab !== 'map') return;
    if (cy) {
      cy.resize();
      cy.fit(undefined, 16);
      return;
    }
    if (started) return;
    started = true;
    draw();
  });
})();
