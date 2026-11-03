/**
 * 항목 카드 '뇌 보기' 탭(HAUD master brain 설계서 7.6 · 사장님 D98 · D100) — templates/brain/partials/card_brain3d.html.
 *
 * - **탭을 보일지**: 휴대폰 · WebGL 없음 · 소프트웨어 그리기(WEBGL_debug_renderer_info 이름에 SwiftShader · llvmpipe · Software …)면
 *   숨긴 채 둔다(서버가 숨겨 그린다 — 스크립트가 없어도 숨김). 판정은 순수 함수 FOMS_BRAIN3D_CORE.canShow3d.
 * - **탭을 열 때만** three.js(static/vendor/three-0.187.0 — ?v= 없는 주소: 폴더가 판, OrbitControls 와 같은 인스턴스)와 그리기
 *   파일 넷을 import() 하고, 바탕 점(GET /api/brain/points — 볼 수 있는 것만 · 이름 없음)과 이웃(GET /api/brain/around)을 읽는다.
 * - 뇌 전체는 흐리게, 지금 항목과 이웃만 밝게 · 이름표(SVG). 다른 점을 누르면 그 항목 둘레를 다시 읽는다. 옆 HTML 패널이 정보
 *   정본(고른 항목 · 이웃 목록 · 카드 링크 · 부위 범례) — 목록 단추로도 3D 에서 고른다.
 * - 탭을 닫으면 무대를 dispose(renderer · 문맥 놓기). 움직임 줄이기면 자동 돌기 · 빛 흐름을 끈다.
 * - fetch 는 brain-dom.js requestJson 한 곳(try/catch + data.success), 글은 textContent 만, 인라인 스타일 없음.
 */
(function () {
  'use strict';

  if (window.__FOMS_BRAIN3D_TAB_BOUND) return;
  var root = document.querySelector('[data-brain3d]');
  var card = document.querySelector('[data-brain-card]');
  if (!root || !card) return;
  window.__FOMS_BRAIN3D_TAB_BOUND = true;

  var core = window.FOMS_BRAIN3D_CORE;
  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var graph = window.FOMS_BRAIN_GRAPH;
  var display = dom.safeJsonParse(card.getAttribute('data-display'), {});
  var modules = dom.safeJsonParse(root.getAttribute('data-modules'), {});
  var tabItem = document.querySelector('[data-brain3d-tab-item]');
  var button = document.getElementById('brain-card-brain3d-btn');
  var status = root.querySelector('[data-brain3d-status]');
  var panel = root.querySelector('[data-brain3d-panel]');
  var startKey = card.getAttribute('data-brain-key');
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var stage = null;
  var loading = false;
  var cache = { points: null, around: {} };
  var items = [];
  var index = {};
  var selected = null;

  /** WebGL 을 잠깐 열어 그리는 이 이름을 읽고 바로 놓는다(소프트웨어 그리기 판별). */
  function probe() {
    try {
      var canvas = document.createElement('canvas');
      var gl = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: true }) ||
               canvas.getContext('webgl', { failIfMajorPerformanceCaveat: true });
      if (!gl) return { webgl: false, renderer: '' };
      var ext = gl.getExtension('WEBGL_debug_renderer_info');
      var name = String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER));
      var lose = gl.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
      return { webgl: true, renderer: name };
    } catch (error) {
      return { webgl: false, renderer: '' };
    }
  }

  function decide() {
    var media = function (q) { return !!(window.matchMedia && window.matchMedia(q).matches); };
    var gpu = probe();
    var verdict = core.canShow3d({ width: window.innerWidth, coarse: media('(pointer: coarse)'), hover: media('(hover: hover)'),
                                   webgl: gpu.webgl, renderer: gpu.renderer });
    root.setAttribute('data-brain3d-verdict', verdict.show ? 'show' : verdict.reason);
    if (tabItem) tabItem.hidden = !verdict.show;
    return verdict;
  }

  function hideTab(reason, text) {
    root.setAttribute('data-brain3d-verdict', reason);
    dom.setStatus(status, text, 'error');
  }

  function aroundUrl(key) {
    return root.getAttribute('data-around-url') + '?' + graph.aroundParams({ key: key, depth: 1, limit: 60 });
  }

  async function loadAround(key) {
    if (cache.around[key]) return cache.around[key];
    var res = await dom.getJson(aroundUrl(key));
    if (!res.ok) throw new Error(res.error);
    cache.around[key] = res.data;
    return res.data;
  }

  /** 바탕 점 + (상한에 잘렸으면) 고른 항목 · 이웃을 더한 점 목록 · 키 → 번호. */
  function buildItems(points, around) {
    var list = core.decodePoints(points);
    var seen = {};
    list.forEach(function (it, i) { seen[it.key] = i; });
    [around.start].concat(around.items).forEach(function (it) {
      if (seen[it.key] !== undefined) return;
      seen[it.key] = list.length;
      list.push({ key: it.key, type: it.type, layer: it.layer, flags: core.flagsOf(it), usage: it.usage_count || 0 });
    });
    return { list: list, index: seen };
  }

  function renderPanel(data) {
    dom.clear(panel);
    var head = dom.el('div', { cls: 'brain3d-panel__head' });
    head.appendChild(dom.typeChip(display, data.start.type));
    head.appendChild(dom.el('a', { cls: 'brain3d-panel__name', text: data.start.name,
                                   attrs: { href: view.itemHref(card.getAttribute('data-item-base'), data.start.key) } }));
    panel.appendChild(head);
    var region = core.REGIONS.find(function (r) { return r.code === core.regionOf(data.start.type, data.start.layer); });
    if (region) panel.appendChild(dom.el('p', { cls: 'brain3d-panel__region', text: '자리: ' + region.name + ' — ' + region.layer }));
    if (data.start.key !== startKey) {
      panel.appendChild(dom.el('button', { cls: 'brain-btn', text: '처음 지식으로 돌아가기',
                                           attrs: { type: 'button', 'data-brain3d-pick': startKey } }));
    }
    var direct = data.items.filter(function (it) { return it.depth === 1; });
    panel.appendChild(dom.el('h3', { cls: 'brain3d-panel__title', text: '이어진 지식 ' + direct.length + '개' +
                                     (data.truncated ? ' (앞 ' + data.items.length + '개만)' : '') }));
    var list = dom.el('ul', { cls: 'brain3d-panel__list' });
    direct.forEach(function (it) {
      var row = dom.el('li', { cls: ['brain-item', 'brain-type--' + it.type].concat(view.stateClasses(it)).join(' ') });
      row.appendChild(dom.el('button', { cls: 'brain3d-panel__pick', text: it.name,
                                         attrs: { type: 'button', 'data-brain3d-pick': it.key, title: '그림에서 고르기' } }));
      row.appendChild(dom.el('span', { cls: 'brain3d-panel__via', text: it.via.map(function (k) {
        return view.linkInfo(display, k).label;
      }).join(' · ') }));
      row.appendChild(dom.el('a', { cls: 'brain-btn', text: '열기', attrs: { href: view.itemHref(card.getAttribute('data-item-base'), it.key) } }));
      list.appendChild(row);
    });
    if (!direct.length) list.appendChild(dom.el('li', { cls: 'brain-empty', text: '연결 없음' }));
    panel.appendChild(list);
  }

  async function select(key) {
    if (!stage) return;
    var data;
    try {
      data = await loadAround(key);
    } catch (error) {
      dom.setStatus(status, '연결을 불러오지 못했어요.', 'error');
      return;
    }
    if (!stage) return;
    selected = key;
    var at = index[key];
    var direct = data.items.filter(function (it) { return it.depth === 1 && index[it.key] !== undefined; });
    var links = data.edges.filter(function (e) { return e.from === key || e.to === key; }).map(function (e) {
      var other = e.from === key ? e.to : e.from;
      return { from: at, to: index[other], kind: e.kind };
    }).filter(function (l) { return l.to !== undefined; });
    var named = [{ idx: at, name: data.start.name, type: data.start.type }].concat(direct.map(function (it) {
      return { idx: index[it.key], name: it.name, type: it.type };
    }));
    stage.select(at, direct.map(function (it) { return index[it.key]; }), links, named);
    renderPanel(data);
    root.setAttribute('data-brain3d-selected', key);
    dom.setStatus(status, '“' + data.start.name + '” — 이어진 ' + direct.length + '개를 밝혔어요(전체 ' +
                  items.length.toLocaleString('ko-KR') + '개). 끌면 돌고, 휠로 키우고, 점을 누르면 골라요.' +
                  (reduced ? ' 움직임 줄이기가 켜져 있어 빛 흐름 · 자동 돌기는 꺼요.' : ''));
  }

  async function open() {
    if (stage || loading) return;
    loading = true;
    dom.setStatus(status, '불러오는 중…');
    var deps;
    var points;
    var around;
    try {
      var mods = await Promise.all([import(root.getAttribute('data-three-url')), import(root.getAttribute('data-orbit-url'))]);
      await Promise.all(['layout', 'shell', 'nodes', 'labels', 'scene'].map(function (name) { return import(modules[name]); }));
      deps = { three: mods[0], orbit: mods[1].OrbitControls, core: core, layout: window.FOMS_BRAIN3D_LAYOUT,
               shell: window.FOMS_BRAIN3D_SHELL, nodes: window.FOMS_BRAIN3D_NODES, labels: window.FOMS_BRAIN3D_LABELS };
      if (!cache.points) {
        var res = await dom.getJson(root.getAttribute('data-points-url'));
        if (!res.ok) throw new Error(res.error);
        cache.points = res.data;
      }
      points = cache.points;
      around = await loadAround(startKey);
    } catch (error) {
      loading = false;
      dom.setStatus(status, '뇌 보기를 못 열었어요. 연결된 지식 탭으로 봐 주세요.', 'error');
      return;
    }
    var built = buildItems(points, around);
    items = built.list;
    index = built.index;
    try {
      stage = window.FOMS_BRAIN3D_SCENE.create(deps.three, deps.orbit, deps, root, {
        items: items, display: display, reduced: reduced,
        onPick: function (i) { if (i >= 0 && items[i].key !== selected) select(items[i].key); },
        onFps: function (fps) { root.setAttribute('data-brain3d-fps', String(Math.round(fps))); }
      });
    } catch (error) {
      loading = false;
      hideTab('no_webgl', '이 기기는 3D 를 못 그려요. 연결된 지식 탭으로 봐 주세요.');
      return;
    }
    loading = false;
    if (core.isSoftwareRenderer(stage.rendererName())) {
      close();
      hideTab('software', '그래픽 장치가 없는 기기라 뇌 보기를 꺼요. 연결된 지식 탭으로 봐 주세요.');
      return;
    }
    if (points.capped) dom.setStatus(status, '많이 쓰인 앞 ' + points.rows.length + '개만 그려요.');
    select(selected || startKey);
  }

  function close() {
    if (stage) stage.dispose();
    stage = null;
    root.removeAttribute('data-brain3d-fps');
  }

  panel.addEventListener('click', function (event) {
    var pick = event.target.closest('[data-brain3d-pick]');
    if (pick) select(pick.getAttribute('data-brain3d-pick'));
  });
  root.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && selected !== startKey) select(startKey);
  });
  if (button) {
    button.addEventListener('shown.bs.tab', open);
    button.addEventListener('hidden.bs.tab', close);
  }
  window.addEventListener('pagehide', close);
  if (decide().show && window.location.hash === '#brain3d' && button && window.bootstrap && window.bootstrap.Tab) {
    window.bootstrap.Tab.getOrCreateInstance(button).show();
  }
})();
