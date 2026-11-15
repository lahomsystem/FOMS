/**
 * 온톨로지 화면의 '유형 지도' 보기(설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 5.2 · 5.3) — 옛 그림 스크립트 brain-map.js 를
 * 고치지 않고 그대로 돌리는 이음새. brain-map.js 보다 먼저 실린다.
 *
 * - brain-map.js 가 읽는 window.FOMS_BRAIN_CTX(뿌리 · 표시 표 · 유형 지도 · 그림 라이브러리 주소 · fire)를 [data-ds-onto-map] 으로 만든다.
 * - 문서가 다 읽히면 'brain:tab' {tab: 'map'} 을 한 번 쏜다 — 그때서야 brain-map.js 가 그림 라이브러리를 import() 한다.
 * - 그림의 유형을 누르면(brain:open-table) 지식 표(?tab=table&type=)로 간다. 목록 줄은 서버가 그린 링크 그대로.
 * 전역 듣개는 한 번만(window.__FOMS_DS_ONTO_MAP_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var page = document.querySelector('[data-ds-onto]');
  var root = document.querySelector('[data-ds-onto-map]');
  if (!dom || !page || !root || window.__FOMS_DS_ONTO_MAP_BOUND || window.FOMS_BRAIN_CTX) return;
  window.__FOMS_DS_ONTO_MAP_BOUND = true;

  var pageUrl = page.getAttribute('data-page-url') || '/brain';

  function fire(name, detail) {
    root.dispatchEvent(new CustomEvent(name, { detail: detail || {} }));
  }

  window.FOMS_BRAIN_CTX = {
    root: root,
    display: dom.safeJsonParse(page.getAttribute('data-display'), {}),
    urls: { typeMap: root.getAttribute('data-type-map-url'), cytoscape: root.getAttribute('data-cytoscape-url'),
            dagre: root.getAttribute('data-dagre-url'), page: pageUrl },
    itemBase: page.getAttribute('data-item-base') || '/brain/items/',
    current: 'map',
    fire: fire
  };

  root.addEventListener('brain:open-table', function (event) {
    var type = (event.detail && event.detail.type) || '';
    window.location.href = pageUrl + '?tab=table' + (type ? '&type=' + encodeURIComponent(type) : '');
  });

  document.addEventListener('DOMContentLoaded', function () { fire('brain:tab', { tab: 'map' }); }, { once: true });
})();
