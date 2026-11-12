/**
 * 회사 지식 '온톨로지' 탭(설계서 2026-11-12 온톨로지 7절 · D187 · D188) — Palantir Ontology Manager 꼴, 읽기만.
 *
 * - 이 탭을 처음 열 때 GET /api/brain/ontology(왼쪽 목록 — 수는 내 보기 범위 안)를 읽는다. 종류를 고르면
 *   GET /api/brain/ontology/types/<유형>(속성 틀 · 채움 · 연결 · 예시)을 한 번 읽어 둔다.
 * - 오른쪽 상세는 작은 탭(속성 · 연결 · 예시 · 능력 질문)으로 나눈다. '지식 표에서 보기'는 'brain:open-table' {type} 을 쏜다.
 * - 그리기는 brain-onto-view.js(FOMS_BRAIN_ONTO_VIEW). 글은 textContent 로만.
 */
(function () {
  'use strict';

  var ctx = window.FOMS_BRAIN_CTX;
  if (!ctx || window.__FOMS_BRAIN_ONTO_BOUND) return;
  window.__FOMS_BRAIN_ONTO_BOUND = true;

  var dom = window.FOMS_BRAIN_DOM;
  var ov = window.FOMS_BRAIN_ONTO_VIEW;
  var root = ctx.root;
  var nav = root.querySelector('[data-brain-onto-nav]');
  var detail = root.querySelector('[data-brain-onto-detail]');
  var status = root.querySelector('[data-brain-onto-status]');
  if (!nav || !detail || !ov || !ctx.urls.onto) return;
  var el = dom.el;

  var summary = null;
  var typeCache = {};
  var started = false;

  function header(title, sub, chip, action) {
    var head = el('div', { cls: 'brain-onto__head' });
    if (chip) head.appendChild(chip);
    head.appendChild(el('h2', { cls: 'h5 mb-0', text: title }));
    if (action) head.appendChild(action);
    if (sub) head.appendChild(el('p', { cls: 'brain-onto__meta', text: sub }));
    return head;
  }

  /** 작은 탭 — panes: [{key, label, node}]. */
  function subTabs(panes) {
    var bar = el('div', { cls: 'brain-onto__tabs', attrs: { role: 'tablist', 'aria-label': '상세 나누기' } });
    var box = el('div');
    panes.forEach(function (pane, index) {
      var btn = el('button', { cls: 'btn btn-sm btn-outline-secondary' + (index === 0 ? ' active' : ''), text: pane.label,
                               attrs: { type: 'button', role: 'tab', 'aria-selected': index === 0 ? 'true' : 'false',
                                        'data-onto-pane': pane.key } });
      var body = el('div', { cls: 'brain-onto__pane', attrs: { 'data-onto-body': pane.key, hidden: index === 0 ? null : '' },
                             children: [pane.node] });
      bar.appendChild(btn);
      box.appendChild(body);
    });
    bar.addEventListener('click', function (event) {
      var btn = event.target.closest('[data-onto-pane]');
      if (!btn) return;
      var key = btn.getAttribute('data-onto-pane');
      bar.querySelectorAll('[data-onto-pane]').forEach(function (b) {
        var on = b === btn;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      box.querySelectorAll('[data-onto-body]').forEach(function (body) {
        body.hidden = body.getAttribute('data-onto-body') !== key;
      });
    });
    return [bar, box];
  }

  function show(nodes) {
    dom.clear(detail);
    nodes.forEach(function (node) { if (node) detail.appendChild(node); });
  }

  function renderType(data) {
    var layers = data.layers.length ? ' · 층 ' + data.layers.join(' · ') : '';
    var sub = data.count + '개 · 표준 ' + data.standard + layers + ' · 능력 질문 ' + data.cq.length + '개가 필요';
    var open = el('button', { cls: 'btn btn-sm btn-outline-primary', text: '지식 표에서 보기',
                              attrs: { type: 'button', 'data-onto-open-table': data.type } });
    var tabs = subTabs([
      { key: 'props', label: '속성 ' + data.props.length, node: ov.propsTable(data) },
      { key: 'links', label: '연결 ' + data.links.length, node: ov.linksTable(ctx, summary.group_labels, data) },
      { key: 'examples', label: '예시', node: ov.examplesList(ctx, data) },
      { key: 'cq', label: '능력 질문 ' + data.cq.length, node: ov.cqTable(summary.cq, data.cq) }
    ]);
    show([header(data.label, sub, dom.typeChip(ctx.display, data.type), open)].concat(tabs));
  }

  async function openType(type) {
    if (!typeCache[type]) {
      dom.setStatus(status, '불러오는 중이에요…');
      var res = await dom.getJson(ctx.urls.onto + '/types/' + encodeURIComponent(type));
      if (!res.ok) {
        dom.setStatus(status, res.error || '읽지 못했어요.', 'error');
        return;
      }
      typeCache[type] = res.data;
      dom.setStatus(status, '');
    }
    renderType(typeCache[type]);
  }

  function openLink(kind) {
    var link = summary.links.filter(function (l) { return l.kind === kind; })[0];
    if (!link) return;
    var rows = [el('tr', { children: [ov.cell(ov.endsText(ctx, summary.group_labels, link.from)),
                                      ov.cell(ov.endsText(ctx, summary.group_labels, link.to)), ov.cell(String(link.count))] })];
    show([header(link.label, '표준 ' + link.standard + (link.open ? '' : ' · 아직 쓰는 짝 없음')),
          ov.table(['시작 종류', '끝 종류', '지금 수'], rows)]);
  }

  function open(kind, value) {
    nav.querySelectorAll('.brain-onto__item.is-active').forEach(function (b) { b.classList.remove('is-active'); });
    var btn = nav.querySelector('[data-onto-kind="' + kind + '"][data-onto-value="' + value + '"]');
    if (btn) btn.classList.add('is-active');
    if (kind === 'type') return openType(value);
    if (kind === 'link') return openLink(value);
    if (kind === 'actions') return show([header('동작 종류', '사람 승인 동작과 AI 에이전트 동작 — 쓰기는 이 동작으로만 해요'),
                                         ov.actionsTable(summary.actions)]);
    if (kind === 'cq') {
      var cq = summary.cq;
      return show([header('능력 질문(시험지)', cq.covered + ' / ' + cq.total + ' 질문에 필요한 종류 · 연결이 있어요. ' +
                          '내용이 맞는지는 평가 단계에서 재요.'), ov.cqTable(cq, null)]);
    }
  }

  function filterNav(text) {
    var q = (text || '').trim().toLowerCase();
    nav.querySelectorAll('.brain-onto__item').forEach(function (btn) {
      btn.hidden = q !== '' && btn.textContent.toLowerCase().indexOf(q) < 0;
    });
  }

  async function start() {
    started = true;
    dom.setStatus(status, '불러오는 중이에요…');
    var res = await dom.getJson(ctx.urls.onto);
    if (!res.ok) {
      started = false;
      dom.setStatus(status, res.error || '읽지 못했어요.', 'error');
      return;
    }
    summary = res.data;
    dom.setStatus(status, '');
    dom.clear(nav);
    ov.renderNav(ctx, summary).forEach(function (node) { nav.appendChild(node); });
    open('type', 'product_line');
  }

  nav.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-onto-kind]');
    if (btn) open(btn.getAttribute('data-onto-kind'), btn.getAttribute('data-onto-value'));
  });
  nav.addEventListener('input', function (event) {
    if (event.target.hasAttribute('data-onto-find')) filterNav(event.target.value);
  });
  detail.addEventListener('click', function (event) {
    var btn = event.target.closest('[data-onto-open-table]');
    if (!btn) return;
    root.dispatchEvent(new CustomEvent('brain:open-table', { detail: { type: btn.getAttribute('data-onto-open-table') } }));
  });
  root.addEventListener('brain:tab', function (event) {
    if (event.detail.tab === 'onto' && !started) start();
  });
})();
