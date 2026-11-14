/**
 * 새 온톨로지 화면(판 ⑩ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.8 · 5.4) 그리기 부품 — 표 · 칸 · 작은 탭 · 꼬리표 ·
 * 왼쪽 목록 · 오른쪽 능력 질문 · 정본 자리. 받은 값 → DOM 만(요청 · 고르기는 ds-onto.js, 상세는 ds-onto-detail.js).
 * 고르는 단추는 모두 data-onto-kind · data-onto-id 를 단다(ds-onto.js 가 한 곳에서 받는다). 막대는 <progress> · <meter>(인라인 스타일
 * 없음). 글은 textContent 만(brain-dom.js el). window.FOMS_DS_ONTO_KIT.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var ov = window.FOMS_DS_ONTO_VIEW;
  if (!dom || !ov) return;
  var el = dom.el;

  function icon(name, extra) {
    return el('span', { cls: 'f-i i-' + name + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  /** 꼬리표 — tone '' · primary · success · warning · danger. */
  function tag(text, tone, opts) {
    var o = opts || {};
    var cls = 'f-tag' + (o.solid ? '' : ' f-tag-minimal') + (tone ? ' f-tag-' + tone : '') + (o.extra ? ' ' + o.extra : '');
    return el('span', { cls: cls, children: [o.icon ? icon(o.icon) : null, document.createTextNode(text)] });
  }

  function small(text, extra) {
    return el('span', { cls: 'f-small f-muted' + (extra ? ' ' + extra : ''), text: text });
  }

  function cell(value, cls) {
    var empty = value === null || value === undefined || value === '';
    if (value && value.nodeType) return el('td', { cls: cls || null, children: [value] });
    return el('td', { cls: cls || null, text: empty ? '—' : String(value) });
  }

  /** 표 — rows 는 <tr> 목록. 좁은 화면에서는 옆으로 민다. */
  function table(headers, rows) {
    var head = el('tr', { children: headers.map(function (h) { return el('th', { text: h, attrs: { scope: 'col' } }); }) });
    return el('div', { cls: 'f-section-body-flush f-scroll-x', children: [el('table', { cls: 'f-table f-table-compact',
      children: [el('thead', { children: [head] }), el('tbody', { children: rows })] })] });
  }

  /** 칸 — 머리(제목 · 덧붙일 것) + 몸. */
  function section(title, extras, body) {
    var head = el('div', { cls: 'f-section-head', children: [el('span', { cls: 'f-section-title', text: title })]
      .concat(extras || []) });
    return el('section', { cls: 'f-section', children: [head, body] });
  }

  function emptyLine(text) {
    return el('p', { cls: 'f-small f-muted fb-onto-empty', text: text });
  }

  /** 작은 탭 — panes: [{key, label, nodes}], first = 처음 고를 key. [탭 줄, 몸] 을 돌려준다. */
  function tabs(panes, first) {
    var bar = el('div', { cls: 'f-tabs', attrs: { role: 'tablist', 'aria-label': '상세 나누기' } });
    var box = el('div', { cls: 'f-col f-gap16' });
    panes.forEach(function (pane) {
      var on = pane.key === first;
      bar.appendChild(el('button', { cls: 'f-tab', text: pane.label, attrs: {
        type: 'button', role: 'tab', 'aria-selected': on ? 'true' : 'false', 'data-onto-pane': pane.key } }));
      box.appendChild(el('div', { cls: 'f-col f-gap16', attrs: { role: 'tabpanel', 'data-onto-body': pane.key,
                                                                  hidden: on ? null : 'hidden' }, children: pane.nodes }));
    });
    bar.addEventListener('click', function (event) {
      var btn = event.target.closest('[data-onto-pane]');
      if (!btn) return;
      var key = btn.getAttribute('data-onto-pane');
      bar.querySelectorAll('[data-onto-pane]').forEach(function (b) {
        b.setAttribute('aria-selected', b === btn ? 'true' : 'false');
      });
      box.querySelectorAll('[data-onto-body]').forEach(function (body) { body.hidden = body.getAttribute('data-onto-body') !== key; });
    });
    return [bar, box];
  }

  /** 길 표시 — parts: [{text, kind?, id?}](마지막이 지금 · kind 가 있는 앞 줄만 누를 수 있다 — 'home' = 처음 고를 것). */
  function crumbs(parts) {
    var nav = el('div', { cls: 'f-breadcrumbs', attrs: { 'aria-label': '길' } });
    parts.forEach(function (part, i) {
      if (i) nav.appendChild(icon('chevron-right'));
      if (i === parts.length - 1) nav.appendChild(el('span', { cls: 'f-current', text: part.text }));
      else if (part.kind) nav.appendChild(el('button', { cls: 'fb-onto-crumb', text: part.text, attrs: {
        type: 'button', 'data-onto-kind': part.kind, 'data-onto-id': part.id || 'all' } }));
      else nav.appendChild(el('span', { text: part.text }));
    });
    return nav;
  }

  /** 상세 머리 — {typeText, typeIcon, title, code, tags: [node]}. */
  function header(h) {
    return el('div', { cls: 'f-row', children: [
      el('span', { cls: 'f-type', children: [icon(h.typeIcon), document.createTextNode(h.typeText)] }),
      el('h1', { cls: 'f-h3', text: h.title }), el('span', { cls: 'f-mono f-muted', text: h.code })].concat(h.tags || []) });
  }

  function pickButton(kind, id, children, cls) {
    return el('button', { cls: 'f-nav-item' + (cls ? ' ' + cls : ''), attrs: { type: 'button', 'data-onto-kind': kind,
                                                                                'data-onto-id': id }, children: children });
  }

  function count(text) {
    return el('span', { cls: 'f-count', text: text });
  }

  /** 왼쪽 목록 — model = FOMS_DS_ONTO_VIEW.navModel(summary). */
  function renderNav(box, model) {
    dom.clear(box);
    box.appendChild(el('div', { cls: 'f-nav-heading', text: '지식 유형 ' + model.kinds }));
    model.groups.forEach(function (g) {
      box.appendChild(el('button', { cls: 'f-nav-item fb-onto-group', attrs: { type: 'button', 'data-onto-group': g.key,
        'aria-expanded': 'false' }, children: [icon('folder-close'), el('span', { cls: 'f-grow', text: g.label }), count(String(g.count))] }));
      box.appendChild(el('div', { cls: 'f-col f-gap4 fb-onto-types', attrs: { 'data-onto-group-body': g.key, hidden: 'hidden' },
        children: g.types.map(function (t) {
          return pickButton('type', t.type, [el('span', { cls: 'f-grow', text: t.label }), count(String(t.count))], 'fb-onto-type');
        }) }));
    });
    if (model.erp) {
      box.appendChild(el('div', { cls: 'f-nav-heading f-row-nw', children: [
        document.createTextNode('ERP 물건 종류 ' + model.erp.length), tag('새로 붙음', 'primary', { extra: 'f-push' })] }));
      model.erp.forEach(function (t) {
        box.appendChild(pickButton('erp', t.type, [icon(t.icon), el('span', { text: t.label }),
                                                   t.sub ? el('span', { cls: 'f-small f-push fb-onto-sub', text: t.sub }) : null]));
      });
    }
    box.appendChild(el('div', { cls: 'f-nav-heading', text: '정의' }));
    model.defs.forEach(function (d) {
      box.appendChild(pickButton(d.kind, 'all', [icon(d.icon), el('span', { cls: 'f-grow', text: d.label }), count(d.count)]));
    });
  }

  /** 고른 줄 표시 — 지식 종류면 그 묶음을 펼친다. */
  function markNav(box, pick) {
    box.querySelectorAll('[data-onto-kind]').forEach(function (btn) {
      var on = !!pick && btn.getAttribute('data-onto-kind') === pick.kind && btn.getAttribute('data-onto-id') === pick.id;
      btn.classList.toggle('is-selected', on);
      if (on) btn.setAttribute('aria-current', 'page'); else btn.removeAttribute('aria-current');
      if (on && pick.kind === 'type') {
        var body = btn.closest('[data-onto-group-body]');
        if (body) setGroup(box, body.getAttribute('data-onto-group-body'), true);
      }
    });
  }

  function setGroup(box, key, open) {
    var btn = box.querySelector('[data-onto-group="' + key + '"]');
    var body = box.querySelector('[data-onto-group-body="' + key + '"]');
    if (!btn || !body) return;
    body.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  /** 찾기 칸 — 맞는 줄만. 찾을 말이 있으면 묶음을 펼쳐 맞는 종류를 보인다. */
  function filterNav(box, query) {
    var q = String(query || '').trim();
    box.querySelectorAll('[data-onto-kind]').forEach(function (btn) { btn.hidden = !ov.matches(btn.textContent, q); });
    box.querySelectorAll('[data-onto-group]').forEach(function (btn) {
      var key = btn.getAttribute('data-onto-group');
      var body = box.querySelector('[data-onto-group-body="' + key + '"]');
      var hits = body.querySelectorAll('[data-onto-kind]:not([hidden])').length;
      btn.hidden = !!q && !hits && !ov.matches(btn.textContent, q);
      if (q) setGroup(box, key, hits > 0);
    });
  }

  function failNode(f) {
    var need = el('span', { cls: 'f-row f-gap4 fb-onto-need', children: [small('모자람')].concat(
      f.missing.map(function (m) { return tag(m.label, 'danger'); }),
      f.erpFix ? [tag('ERP 붙으면 풀림', 'primary')] : []) });
    return el('li', { cls: 'f-col f-gap4', children: [
      el('span', { cls: 'f-row-nw f-top', children: [el('span', { cls: 'f-mono f-muted', text: f.id }),
                                                     el('span', { cls: 'f-small', text: f.question })] }), need] });
  }

  /** 오른쪽 능력 질문 — 점수 · 막대 · 켜기 전 → 지금 · ERP 재료 안내 · 아직 못 푸는 질문 다섯 · 모두 보기. */
  function renderScore(box, summary) {
    var sc = ov.score(summary.cq);
    var left = ov.fails(summary.cq, 5);
    dom.clear(box);
    box.appendChild(el('div', { cls: 'f-col', children: [
      el('div', { cls: 'f-row', children: [el('span', { cls: 'f-h2 f-num', text: sc.text }), el('span', { cls: 'f-muted', text: '통과' }),
                                           sc.change ? tag(sc.change, 'success', { extra: 'f-push' }) : null] }),
      el('progress', { cls: 'fb-onto-progress', attrs: { max: Math.max(sc.total, 1), value: sc.covered,
                                                         'aria-label': sc.total + '개 중 ' + sc.covered + '개 통과' } }),
      el('span', { cls: 'f-help', text: '질문에 필요한 종류 · 연결이 있는 수예요. 내용이 맞는지는 평가 단계에서 재요.' })] }));
    if (summary.erp) {
      box.appendChild(el('div', { cls: 'f-callout f-callout-primary', attrs: { 'data-onto-erp-note': '1' }, children: [
        icon('data-lineage'), el('div', { cls: 'f-small', children: [
          el('div', { cls: 'f-callout-title', text: 'ERP 물건이 필요한 질문 ' + summary.erp.cq_erp }),
          document.createTextNode("주문 · 일정을 읽기만 해도 풀리는 질문이에요. 읽기 도구가 있는 재료는 '있음'으로 세요.")] })] }));
    }
    var list = el('section', { cls: 'f-col', attrs: { 'aria-label': '아직 못 푸는 질문' }, children: [
      el('div', { cls: 'f-row', children: [el('h2', { cls: 'f-h6', text: '아직 못 푸는 질문' }),
                                           small(left.total + '개 중 ' + left.rows.length, 'f-push')] })] });
    if (left.rows.length) list.appendChild(el('ul', { cls: 'f-col f-gap12', children: left.rows.map(failNode) }));
    else list.appendChild(small('모두 답 재료가 있어요.'));
    list.appendChild(el('button', { cls: 'fb-onto-link f-small', text: sc.total + '개 모두 보기',
                                    attrs: { type: 'button', 'data-onto-kind': 'cq', 'data-onto-id': 'all' } }));
    box.appendChild(list);
  }

  /** 정본 자리(ERP 물건을 고를 때만) — detail = GET /api/brain/ontology/erp/<종류>. null 이면 숨긴다. */
  function renderSource(box, detail) {
    if (!box) return;
    dom.clear(box);
    box.hidden = !detail;
    if (!detail) return;
    var kv = el('dl', { cls: 'f-kv f-small' });
    [['값', '지금 FOMS 표 그대로 · 새 표 없음'], ['정본', (detail.source || {}).text], ['읽기 도구', detail.read_note],
     ['쓰는 길', detail.actions.length ? '할 일 ' + detail.actions.length + ' → 지금 기능' : '없음']].forEach(function (row) {
      kv.appendChild(el('dt', { text: row[0] }));
      kv.appendChild(el('dd', { cls: row[0] === '정본' ? 'f-mono' : null, text: row[1] || '—' }));
    });
    box.appendChild(el('h2', { cls: 'f-h6', text: '정본 자리 — ' + detail.label }));
    box.appendChild(kv);
  }

  window.FOMS_DS_ONTO_KIT = { icon: icon, tag: tag, small: small, cell: cell, table: table, section: section,
                              emptyLine: emptyLine, tabs: tabs, crumbs: crumbs, header: header, renderNav: renderNav,
                              markNav: markNav, setGroup: setGroup, filterNav: filterNav, renderScore: renderScore,
                              renderSource: renderSource };
})();
