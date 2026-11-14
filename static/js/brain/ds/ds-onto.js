/**
 * 새 온톨로지 화면(판 ⑩ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.8 · 5.4) — templates/brain/ds/onto.html 의 [data-ds-onto].
 *
 * - 첫 값 GET /api/brain/ontology(수는 내 보기 범위 안 · ERP 읽기가 켜진 사람에게만 erp 칸) → 왼쪽 목록 · 오른쪽 능력 질문.
 * - 고르기(왼쪽 줄 · 길 표시 · 이어진 것 · '모두 보기' — 모두 data-onto-kind · data-onto-id): 지식 종류는
 *   GET /api/brain/ontology/types/<유형>, ERP 물건은 GET /api/brain/ontology/erp/<종류> 를 한 번 읽어 둔다. 고른 것은 주소
 *   (?tab=onto&kind=&id=)에 남긴다(새로 고침 · 링크 나눔이 같은 상세를 연다). 처음 고를 것은 ERP 칸이 있으면 주문, 없으면 제품 라인.
 * - 유형 지도 보기(data-ds-onto-view="map")에서는 목록 · 점수만 그리고, 줄을 누르면 온톨로지 보기의 그 상세로 간다.
 * fetch 는 brain-dom.js 한 곳 · 글은 textContent 만 · 전역 듣개는 한 번만(window.__FOMS_DS_ONTO_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var ov = window.FOMS_DS_ONTO_VIEW;
  var kit = window.FOMS_DS_ONTO_KIT;
  var root = document.querySelector('[data-ds-onto]');
  if (!root || !dom || !ov || !kit || window.__FOMS_DS_ONTO_BOUND) return;
  window.__FOMS_DS_ONTO_BOUND = true;

  var details = window.FOMS_DS_ONTO_DETAIL;
  var mapView = root.getAttribute('data-ds-onto-view') === 'map';
  var ctx = { display: dom.safeJsonParse(root.getAttribute('data-display'), {}), summary: null,
              itemBase: root.getAttribute('data-item-base') || '/brain/items/', pageUrl: root.getAttribute('data-page-url') || '/brain' };
  var ontoUrl = root.getAttribute('data-onto-url');
  var status = root.querySelector('[data-ds-onto-status]');
  var detail = root.querySelector('[data-ds-onto-detail]');
  var side = document.querySelector('[data-ds-onto-side]');
  var nav = side && side.querySelector('[data-ds-onto-nav]');
  var find = side && side.querySelector('[data-ds-onto-find]');
  var toggle = side && side.querySelector('[data-ds-onto-side-toggle]');
  var aside = document.querySelector('[data-ds-onto-aside]');
  var scoreBox = aside && aside.querySelector('[data-ds-onto-cq]');
  var sourceBox = aside && aside.querySelector('[data-ds-onto-source]');
  var cache = { type: {}, erp: {} };
  var seq = 0;

  function show(nodes) {
    if (!detail) return;
    dom.clear(detail);
    nodes.forEach(function (node) { if (node) detail.appendChild(node); });
  }

  function detailUrl(pick) {
    return pick.kind === 'erp' ? ontoUrl + '/erp/' + encodeURIComponent(String(pick.id).replace(/^erp:/, ''))
                               : ontoUrl + '/types/' + encodeURIComponent(pick.id);
  }

  /** 상세 값(한 번 읽으면 기억) — 못 읽으면 null(알림 줄에 까닭). */
  async function loadDetail(pick) {
    var box = cache[pick.kind];
    if (box[pick.id]) return box[pick.id];
    dom.setStatus(status, '불러오는 중이에요…');
    var res = await dom.getJson(detailUrl(pick));
    if (!res.ok) {
      dom.setStatus(status, res.error || '읽지 못했어요.', 'error');
      return null;
    }
    dom.setStatus(status, '');
    box[pick.id] = res.data;
    return res.data;
  }

  function normal(pick) {
    var s = ctx.summary;
    if (!pick || pick.kind === 'home') return ov.defaultPick(s);
    if ((pick.kind === 'erp' || pick.kind === 'erp_actions') && !s.erp) return ov.defaultPick(s);
    return pick;
  }

  async function open(asked) {
    if (!ctx.summary) return;
    var pick = normal(asked);
    if (mapView || !details) {
      window.location.href = ctx.pageUrl + '?' + ov.pickQuery(pick);
      return;
    }
    if (nav) kit.markNav(nav, pick);
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, '', ctx.pageUrl + '?' + ov.pickQuery(pick));
    }
    var mine = ++seq;
    if (pick.kind !== 'type' && pick.kind !== 'erp') {
      kit.renderSource(sourceBox, null);
      show(details.definition(ctx, pick.kind));
      return;
    }
    var data = await loadDetail(pick);
    if (mine !== seq || !data) return;  // 더 늦은 고르기가 이미 나갔다 · 못 읽음
    kit.renderSource(sourceBox, pick.kind === 'erp' ? data : null);
    show(pick.kind === 'erp' ? details.erpType(ctx, data) : details.knowledgeType(ctx, data));
  }

  /** 폰 목록 접기 · 펴기(PC 에서는 단추가 안 보이고 목록이 늘 펴져 있다). */
  function setSide(open) {
    if (!side || !toggle) return;
    side.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  function pickOf(node) {
    return { kind: node.getAttribute('data-onto-kind'), id: node.getAttribute('data-onto-id') };
  }

  function onPick(event) {
    var group = event.target.closest('[data-onto-group]');
    if (group && nav) {
      kit.setGroup(nav, group.getAttribute('data-onto-group'), group.getAttribute('aria-expanded') !== 'true');
      return;
    }
    var btn = event.target.closest('[data-onto-kind]');
    if (!btn) return;
    setSide(false);
    open(pickOf(btn));
  }

  async function start() {
    dom.setStatus(status, '불러오는 중이에요…');
    var res = await dom.getJson(ontoUrl);
    if (!res.ok) {
      dom.setStatus(status, res.error || '읽지 못했어요.', 'error');
      return;
    }
    ctx.summary = res.data;
    dom.setStatus(status, '');
    if (nav) kit.renderNav(nav, ov.navModel(ctx.summary));
    if (scoreBox) kit.renderScore(scoreBox, ctx.summary);
    if (!mapView) open(ov.pickFromQuery(window.location.search));
  }

  if (nav) nav.addEventListener('click', onPick);
  if (detail) detail.addEventListener('click', onPick);
  if (aside) aside.addEventListener('click', onPick);
  if (find && nav) find.addEventListener('input', function () { kit.filterNav(nav, find.value); });
  if (toggle) toggle.addEventListener('click', function () { setSide(!side.classList.contains('is-open')); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
