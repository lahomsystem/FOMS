/**
 * 새 온톨로지 화면(판 ⑩ — 설계서 docs/specs/2026-11-14-foms-graft_SPEC.md 3.2 · 3.8 · 5.4 · 9절) 가운데 상세 — 받은 값 → DOM 노드 목록.
 *
 * - 지식 종류(GET /api/brain/ontology/types/<유형>): 머리 · 수 · 표준 · 층 · '지식 표에서 보기' · 작은 탭(속성 틀 · 채움 · 연결 ·
 *   예시 · 능력 질문) — 옛 온톨로지 탭과 같은 내용.
 * - ERP 물건(GET /api/brain/ontology/erp/<종류>): 머리 · 정본 자리 한 줄 · 이어진 것 · 작은 탭(개요 · 속성 ↔ 지금 칸 · 연결 · 할 일 ·
 *   질문). '지금 칸'은 API 값 그대로(목업의 orders.status 같은 옛 칸이 아니다 — 설계서 3.2 · 9절).
 * - 정의: 연결 종류 · 할 일 종류(ERP) · 동작 종류 · 능력 질문 전체 표.
 * 고르는 단추는 data-onto-kind · data-onto-id(ds-onto.js 가 받는다). 글은 textContent 만. window.FOMS_DS_ONTO_DETAIL.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var ov = window.FOMS_DS_ONTO_VIEW;
  var kit = window.FOMS_DS_ONTO_KIT;
  if (!dom || !ov || !kit) return;
  var el = dom.el;
  var cell = kit.cell;
  var NEW = function () { return kit.tag('새로 붙음', 'primary'); };

  /** 흰 칸에 담기(표 · 빈 줄 · 목록). */
  function boxed(node) {
    return el('section', { cls: 'f-section', children: [node] });
  }

  function tr(cells, attrs) {
    return el('tr', { attrs: attrs || null, children: cells });
  }

  function crumbs(group, label) {
    return kit.crumbs([{ text: '온톨로지', kind: 'home' }, { text: group }, { text: label }]);
  }

  function needChip(need) {
    if (need.have) return kit.tag(need.label + ' 있음', 'success');
    return need.erp ? kit.tag(need.label + ' · ERP 붙으면 풀림', 'primary') : kit.tag(need.label + ' 없음', 'danger');
  }

  /** 능력 질문 표 — ids 를 주면 그 질문만. */
  function cqTable(cq, ids) {
    var rows = (cq.rows || []).filter(function (row) { return !ids || ids.indexOf(row.id) >= 0; });
    if (!rows.length) return kit.emptyLine('이 종류가 필요한 능력 질문이 없어요.');
    return kit.table(['번호', '영역', '질문', '근거', '필요한 것', '답 재료'], rows.map(function (row) {
      return tr([cell(row.id, 'f-mono'), cell(row.domain), cell(row.question), cell(ov.BASIS[row.basis] || row.basis),
                 el('td', { children: [el('span', { cls: 'f-row f-gap4', children: row.needs.concat(row.links).map(needChip) })] }),
                 cell(kit.tag(row.covered ? '있음' : '모자람', row.covered ? 'success' : 'danger'))]);
    }));
  }

  function fill(prop) {
    return el('td', { cls: 'f-td-nw', children: [
      el('meter', { cls: 'fb-onto-meter', attrs: { min: 0, max: Math.max(prop.total, 1), value: prop.filled,
                                                   'aria-label': prop.label + ' 채움' } }),
      kit.small(' ' + prop.filled + ' / ' + prop.total)] });
  }

  function typePropsTable(data) {
    if (!data.props.length) return kit.emptyLine('이 종류는 아직 속성 틀이 없어요(꼴 검사만).');
    return kit.table(['칸', '자료형', '꼭', '단위 · 범위', '고를 값', '표준', '채움'], data.props.map(function (p) {
      return tr([cell(p.label, 'f-td-nw f-strong'), cell(ov.DATATYPES[p.datatype] || p.datatype), cell(ov.requiredText(p)),
                 cell(ov.rangeText(p)), cell(p.choices.map(function (c) { return c.label; }).join(' · ')),
                 cell(p.standard, 'f-mono'), fill(p)]);
    }));
  }

  function typeLinksTable(ctx, data) {
    if (!data.links.length) return kit.emptyLine('이 종류에 허용된 연결이 없어요.');
    return kit.table(['방향', '연결', '상대 종류', '개수 규칙', '지금 수', '표준'], data.links.map(function (link) {
      return tr([cell(link.direction === 'out' ? '나감 →' : '← 들어옴', 'f-td-nw'), cell(link.label + ' · ' + link.phrase),
                 cell(ov.endsText(ctx.display, ctx.summary.group_labels, link.ends)), cell(ov.cardinalityText(link)),
                 cell(String(link.count), 'f-td-num'), cell(link.standard, 'f-mono')]);
    }));
  }

  function examplesList(ctx, data) {
    if (!data.examples.length) return kit.emptyLine('아직 이 종류의 항목이 없어요.');
    return el('ul', { cls: 'f-col f-gap4 fb-onto-list', children: data.examples.map(function (item) {
      return el('li', { children: [el('a', { text: item.name, attrs: {
        href: ctx.itemBase + String(item.key).split('/').map(encodeURIComponent).join('/') } })] });
    }) });
  }

  /** 지식 종류 상세. ctx = {display, summary, itemBase, pageUrl}. */
  function knowledgeType(ctx, data) {
    var open = el('a', { cls: 'f-btn f-btn-small', attrs: { href: ctx.pageUrl + '?tab=table&type=' + encodeURIComponent(data.type) },
                         children: [kit.icon('th'), document.createTextNode('지식 표에서 보기')] });
    var head = el('header', { cls: 'f-col', children: [
      kit.header({ typeText: '지식 유형', typeIcon: 'lightbulb', title: data.label, code: data.type,
                   tags: [kit.tag('표준 ' + data.standard, ''), el('span', { cls: 'f-push', children: [open] })] }),
      el('div', { cls: 'f-row f-small f-muted', text: ov.typeSub(data) })] });
    return [crumbs('지식 유형', data.label), head].concat(kit.tabs([
      { key: 'props', label: '속성 ' + data.props.length, nodes: [boxed(typePropsTable(data))] },
      { key: 'links', label: '연결 ' + data.links.length, nodes: [boxed(typeLinksTable(ctx, data))] },
      { key: 'examples', label: '예시', nodes: [boxed(examplesList(ctx, data))] },
      { key: 'cq', label: '질문 ' + data.cq.length, nodes: [boxed(cqTable(ctx.summary.cq, data.cq))] }], 'props'));
  }

  function erpPropsSection(detail) {
    var body = detail.props.length ? kit.table(['속성 이름', '지금 칸', '값 모양', '읽기 · 쓰기'], detail.props.map(function (p) {
      return tr([cell(p.name, 'f-td-nw f-strong'), cell(p.column, 'f-mono'), cell(p.shape), el('td', { children: [
        el('span', { cls: 'f-row f-gap4', children: [kit.tag(p.access_label, ov.accessTone(p.access)),
                                                     p.via ? kit.small(p.via) : null, p.note ? kit.small(p.note) : null] })] })],
        { 'data-onto-prop': p.key });
    })) : el('div', { cls: 'f-section-body', children: [kit.emptyLine('판 1 에서는 속성 표 없이 정본 자리만 가리켜요 — ' +
                                                                       ((detail.source || {}).text || ''))] });
    return kit.section('속성 ↔ 지금 칸', [el('span', { cls: 'f-section-sub', text: '지금 FOMS 칸에 이름만 붙여 읽어요' })], body);
  }

  function erpActionRows(actions, withTarget) {
    return actions.map(function (a) {
      var cells = [cell(a.label, 'f-td-nw f-strong')];
      if (withTarget) cells.push(cell(a.target_label));
      return tr(cells.concat([
        el('td', { children: [el('span', { cls: 'f-row-nw', children: [el('span', { text: a.wraps }),
                                                                         el('span', { cls: 'f-mono f-muted', text: a.name })] })] }),
        cell(kit.tag(a.level_label, ov.levelTone(a))),
        el('td', { cls: 'f-td-nw', children: [el('span', { cls: 'f-row-nw f-small', children: [
          kit.icon(ov.whereIcon(a.where), 'f-i-muted'), document.createTextNode(a.where)] })] })]));
    });
  }

  function erpActionsSection(actions, withTarget) {
    var legend = [NEW(), el('span', { cls: 'f-section-sub', text: '새 API 없이 지금 기능을 이름 붙여 감싸요' }),
                  kit.small('0 읽기만 · 1 초안 · 2 제안 · 사람만', 'f-push')];
    var heads = ['할 일'].concat(withTarget ? ['대상'] : [], ['감싸는 지금 기능', 'AI 자율 수준', '승인 자리']);
    var body = actions.length ? kit.table(heads, erpActionRows(actions, withTarget))
                              : el('div', { cls: 'f-section-body', children: [kit.emptyLine('이 물건에 붙은 할 일이 없어요.')] });
    return kit.section('할 일 종류', legend, body);
  }

  function erpLinksTable(detail) {
    if (!detail.links.length) return kit.emptyLine('이어진 물건이 없어요.');
    return kit.table(['방향', '연결', '상대 종류'], detail.links.map(function (l) {
      return tr([cell(l.direction === 'out' ? '나감 →' : '← 들어옴', 'f-td-nw'), cell(l.rel),
                 el('td', { children: [el('button', { cls: 'fb-onto-link', text: l.label,
                                                      attrs: { type: 'button', 'data-onto-kind': 'erp', 'data-onto-id': l.type } })] })]);
    }));
  }

  function erpHead(ctx, detail) {
    var tags = [NEW(), kit.tag('정본 = 지금 FOMS ' + (detail.source || {}).table + ' 표', '', { icon: 'th' })];
    if (detail.actions.length) tags.push(kit.tag('쓰기는 할 일로만', 'warning', { icon: 'lock' }));
    if (detail.hidden) tags.push(kit.tag('AI 에 안 감', 'warning', { icon: 'eye-off' }));
    var meta = el('div', { cls: 'f-row f-small f-muted' });
    ov.erpMeta(detail).forEach(function (part, i) {
      if (i) meta.appendChild(el('span', { text: '·', attrs: { 'aria-hidden': 'true' } }));
      meta.appendChild(el('span', { text: part }));
    });
    meta.appendChild(el('span', { text: '· 읽기 도구 ' + detail.read_note }));
    var types = {};
    ((ctx.summary.erp || {}).types || []).forEach(function (t) { types[t.type] = String(t.icon || '').replace(/^i-/, ''); });
    var chips = detail.links.map(function (l) {
      return el('button', { cls: 'f-chip fb-onto-chip', attrs: { type: 'button', 'data-onto-kind': 'erp', 'data-onto-id': l.type },
                            children: [kit.icon(types[l.type] || 'cube'), document.createTextNode(l.label)] });
    });
    var rows = [kit.header({ typeText: 'ERP 물건 종류', typeIcon: detail.icon.replace(/^i-/, '') || 'cube', title: detail.label,
                             code: detail.type, tags: tags }), meta];
    if (chips.length) rows.push(el('div', { cls: 'f-row f-gap4', children: [kit.small('이어진 것')].concat(chips) }));
    return el('header', { cls: 'f-col', children: rows });
  }

  /** ERP 물건 상세. */
  function erpType(ctx, detail) {
    return [crumbs('ERP 물건 종류', detail.label), erpHead(ctx, detail)].concat(kit.tabs([
      { key: 'overview', label: '개요', nodes: [erpPropsSection(detail), erpActionsSection(detail.actions, false)] },
      { key: 'props', label: '속성 ' + detail.props.length, nodes: [erpPropsSection(detail)] },
      { key: 'links', label: '연결 ' + detail.links.length, nodes: [boxed(erpLinksTable(detail))] },
      { key: 'actions', label: '할 일 ' + detail.actions.length, nodes: [erpActionsSection(detail.actions, false)] },
      { key: 'cq', label: '질문 ' + detail.cq.length, nodes: [boxed(cqTable(ctx.summary.cq, detail.cq))] }], 'overview'));
  }

  function plainHead(title, sub) {
    return el('header', { cls: 'f-col', children: [el('h1', { cls: 'f-h3', text: title }), sub ? kit.small(sub) : null] });
  }

  /** 정의 — 연결 종류 · 할 일 종류 · 동작 종류 · 능력 질문 전체. */
  function definition(ctx, kind) {
    var s = ctx.summary;
    if (kind === 'links') {
      return [kit.crumbs([{ text: '온톨로지', kind: 'home' }, { text: '연결 종류' }]), plainHead('연결 종류', '지식 사이를 잇는 선 — 허용된 짝만 이어요'),
              boxed(kit.table(['연결', '시작 종류', '끝 종류', '지금 수', '표준'], s.links.map(function (link) {
                return tr([cell(link.label + (link.open ? '' : ' · 아직 쓰는 짝 없음'), 'f-strong'),
                           cell(ov.endsText(ctx.display, s.group_labels, link.from)),
                           cell(ov.endsText(ctx.display, s.group_labels, link.to)), cell(String(link.count), 'f-td-num'),
                           cell(link.standard, 'f-mono')], { 'data-onto-link': link.kind });
              })))];
    }
    if (kind === 'erp_actions' && s.erp) {
      return [kit.crumbs([{ text: '온톨로지', kind: 'home' }, { text: '할 일 종류' }]), plainHead('할 일 종류', '주문을 바꾸는 일은 이 할 일로만 해요'),
              erpActionsSection(s.erp.actions, true)];
    }
    if (kind === 'actions') {
      return [kit.crumbs([{ text: '온톨로지', kind: 'home' }, { text: '동작 종류' }]),
              plainHead('동작 종류', '사람 승인 동작과 AI 에이전트 동작 — 쓰기는 이 동작으로만 해요'),
              boxed(kit.table(['동작', '단계', '누가', '하는 일'], s.actions.map(function (a) {
                return tr([cell(a.label, 'f-strong'), cell(ov.STAGES[a.stage] || a.stage), cell(a.agent ? 'AI 에이전트' : '사람'),
                           cell(a.summary)]);
              })))];
    }
    return [kit.crumbs([{ text: '온톨로지', kind: 'home' }, { text: '능력 질문' }]),
            plainHead('능력 질문(시험지)', s.cq.covered + ' / ' + s.cq.total + ' 질문에 필요한 종류 · 연결이 있어요. 내용이 맞는지는 평가 단계에서 재요.'),
            boxed(cqTable(s.cq, null))];
  }

  window.FOMS_DS_ONTO_DETAIL = { knowledgeType: knowledgeType, erpType: erpType, definition: definition, cqTable: cqTable };
})();
