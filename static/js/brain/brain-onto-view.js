/**
 * 회사 지식 '온톨로지' 탭 그리기 도구(설계서 2026-11-12 온톨로지 7절 · D187 · D188) — Palantir Ontology Manager 꼴.
 *
 * - 왼쪽 목록(물건 종류 · 연결 종류 · 동작 · 능력 질문)과 오른쪽 상세의 표 · 줄을 만든다. 글은 textContent 로만(brain-dom.js el).
 * - 채움은 <meter>(min 0 · max 전체 · value 값 있는 수) — 인라인 스타일 없이 막대가 된다.
 * - 상태 · 자료 읽기는 brain-onto.js 가 한다. 이 파일은 받은 자료 → DOM 만.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  if (!dom || !view) return;
  var el = dom.el;

  var DATATYPES = { text: '글', int: '정수', number: '수', date: '날짜', datetime: '때', enum: '하나 고름', list: '목록' };
  var BASIS = { rule: '규칙', calculator: '계산기', order_data: '주문 자료', photo: '사진', human_judgment: '사람 판단' };
  var STAGES = { propose: '제안', decide: '결정' };

  /** 종류 이름(묶음 줄임 포함) — {type} · {group}. */
  function endText(ctx, groupLabels, end) {
    if (end.group) return (groupLabels[end.group] || end.group) + ' 전체';
    return view.typeInfo(ctx.display, end.type).label;
  }

  function endsText(ctx, groupLabels, ends) {
    return (ends || []).map(function (end) { return endText(ctx, groupLabels, end); }).join(' · ') || '없음';
  }

  /** 왼쪽 목록 단추 한 줄. */
  function navButton(kind, value, label, count, extra) {
    var btn = el('button', { cls: 'brain-onto__item', attrs: { type: 'button', 'data-onto-kind': kind,
                                                                 'data-onto-value': value } });
    if (extra) btn.appendChild(extra);
    btn.appendChild(el('span', { cls: 'brain-onto__label', text: label }));
    if (count !== null && count !== undefined) btn.appendChild(el('span', { cls: 'brain-onto__count', text: count }));
    return btn;
  }

  function navSection(title, children) {
    var section = el('section', { cls: 'brain-onto__group' });
    section.appendChild(el('h2', { cls: 'brain-onto__title', text: title }));
    children.forEach(function (child) { section.appendChild(child); });
    return section;
  }

  /** 왼쪽 목록 전체. */
  function renderNav(ctx, data) {
    var nodes = [];
    nodes.push(el('input', { cls: 'form-control form-control-sm brain-onto__find',
                             attrs: { type: 'search', placeholder: '종류 · 연결 찾기', 'aria-label': '목록에서 찾기',
                                      'data-onto-find': '1' } }));
    var types = [];
    data.groups.forEach(function (group) {
      types.push(el('p', { cls: 'brain-onto__sub', text: group.label }));
      group.types.forEach(function (t) {
        types.push(navButton('type', t.type, t.label, t.count, dom.icon(t.icon)));
      });
    });
    nodes.push(navSection('물건 종류 · ' + data.total + '개', types));
    nodes.push(navSection('연결 종류', data.links.map(function (link) {
      return navButton('link', link.kind, link.label, link.count, el('span', { cls: 'brain-swatch brain-link--' + link.kind,
                                                                                 attrs: { 'aria-hidden': 'true' } }));
    })));
    nodes.push(navSection('동작', [navButton('actions', 'all', '동작 종류', data.actions.length, dom.icon('fa-bolt'))]));
    nodes.push(navSection('능력 질문(시험지)', [navButton('cq', 'all', '답 재료 있음',
                                                       data.cq.covered + ' / ' + data.cq.total, dom.icon('fa-clipboard-check'))]));
    return nodes;
  }

  function table(headers, rows) {
    var head = el('tr', { children: headers.map(function (h) { return el('th', { text: h, attrs: { scope: 'col' } }); }) });
    var body = el('tbody', { children: rows });
    return el('div', { cls: 'table-responsive', children: [
      el('table', { cls: 'table table-sm brain-onto__table', children: [el('thead', { children: [head] }), body] })] });
  }

  function cell(text) { return el('td', { text: text === null || text === undefined || text === '' ? '—' : text }); }

  function fill(prop) {
    var td = el('td', { cls: 'brain-onto__fill' });
    td.appendChild(el('meter', { attrs: { min: 0, max: Math.max(prop.total, 1), value: prop.filled,
                                          'aria-label': prop.label + ' 채움' } }));
    td.appendChild(el('span', { text: prop.filled + ' / ' + prop.total }));
    return td;
  }

  function range(prop) {
    var parts = [];
    if (prop.low !== null && prop.low !== undefined) parts.push(prop.low + ' 이상');
    if (prop.high !== null && prop.high !== undefined) parts.push(prop.high + ' 이하');
    return [prop.unit || '', parts.join(' · ')].filter(Boolean).join(' · ');
  }

  /** 속성 표. */
  function propsTable(detail) {
    if (!detail.props.length) return el('p', { cls: 'brain-empty', text: '이 종류는 아직 속성 틀이 없어요(꼴 검사만).' });
    return table(['칸', '자료형', '꼭', '단위 · 범위', '고를 값', '표준', '채움'], detail.props.map(function (p) {
      return el('tr', { children: [
        cell(p.label), cell(DATATYPES[p.datatype] || p.datatype),
        cell(p.required === 'always' ? '꼭' : p.required === 'active' ? '반영 때 꼭' : ''), cell(range(p)),
        cell(p.choices.map(function (c) { return c.label; }).join(' · ')), el('td', { cls: 'brain-onto__std', text: p.standard }),
        fill(p)] });
    }));
  }

  function cardinalityText(link) {
    if (link.direction === 'in') return '';
    var max = link.max === null || link.max === undefined ? '여럿' : link.max;
    return link.min + ' ~ ' + max;
  }

  /** 연결 표(나감 · 들어옴). */
  function linksTable(ctx, groupLabels, detail) {
    if (!detail.links.length) return el('p', { cls: 'brain-empty', text: '이 종류에 허용된 연결이 없어요.' });
    return table(['방향', '연결', '상대 종류', '개수 규칙', '지금 수', '표준'], detail.links.map(function (link) {
      return el('tr', { cls: 'brain-link--' + link.kind, children: [
        cell(link.direction === 'out' ? '나감 →' : '← 들어옴'), cell(link.label + ' · ' + link.phrase),
        cell(endsText(ctx, groupLabels, link.ends)), cell(cardinalityText(link)), cell(String(link.count)),
        el('td', { cls: 'brain-onto__std', text: link.standard })] });
    }));
  }

  function examplesList(ctx, detail) {
    if (!detail.examples.length) return el('p', { cls: 'brain-empty', text: '아직 이 종류의 항목이 없어요.' });
    return el('ul', { cls: 'brain-onto__examples', children: detail.examples.map(function (item) {
      return el('li', { children: [el('a', { text: item.name, attrs: { href: view.itemHref(ctx.itemBase, item.key) } })] });
    }) });
  }

  function needChip(need) {
    var cls = 'brain-badge ' + (need.have ? 'brain-onto__have' : need.erp ? 'brain-badge--check' : 'brain-badge--missing');
    var mark = need.have ? '있음' : need.erp ? '승인 대기' : '없음';
    return el('span', { cls: cls, text: need.label + ' ' + mark });
  }

  /** 능력 질문 표 — ids 를 주면 그 질문만. */
  function cqTable(cq, ids) {
    var rows = cq.rows.filter(function (row) { return !ids || ids.indexOf(row.id) >= 0; });
    if (!rows.length) return el('p', { cls: 'brain-empty', text: '이 종류가 필요한 능력 질문이 없어요.' });
    return table(['번호', '영역', '질문', '근거', '필요한 것', '답 재료'], rows.map(function (row) {
      return el('tr', { children: [
        cell(row.id), cell(row.domain), cell(row.question), cell(BASIS[row.basis] || row.basis),
        el('td', { cls: 'brain-onto__needs', children: row.needs.concat(row.links).map(needChip) }),
        cell(row.covered ? '있음' : '모자람')] });
    }));
  }

  function actionsTable(actions) {
    return table(['동작', '단계', '누가', '하는 일'], actions.map(function (a) {
      return el('tr', { children: [cell(a.label), cell(STAGES[a.stage] || a.stage), cell(a.agent ? 'AI 에이전트' : '사람'),
                                   cell(a.summary)] });
    }));
  }

  window.FOMS_BRAIN_ONTO_VIEW = { renderNav: renderNav, propsTable: propsTable, linksTable: linksTable,
                                  examplesList: examplesList, cqTable: cqTable, actionsTable: actionsTable,
                                  endsText: endsText, table: table, cell: cell };
})();
