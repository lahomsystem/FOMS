/**
 * 새 찾기 · 지식 표(판 ⑦) 줄 그리기 — templates/brain/ds/search.html 의 표 몸통 · 미리 보기가 같이 쓰는 작은 부품.
 *
 * - 지식 줄: 이름(카드로 가는 링크) + 유형 표시 + '확인 필요' · 쓰는 팀 · 브랜드 · 상태 꼬리표 · 확실한 정도 · 등급 꼬리표 ·
 *   쓰인 횟수 · 마지막 확인 · 다시 볼 날(지났으면 주황 꼬리표). 줄을 누르거나 Enter 면 미리 보기(ds-search.js).
 * - 유형 묶음 줄(찾기): 유형 아이콘 · 이름 · 수 · '표에서 모두 보기'(그 유형 지식 표로 — data-ds-type).
 * 모양 판정은 FOMS_DS_SEARCH_VIEW(순수), 요소는 brain-dom.js el(글은 textContent 만 · 인라인 스타일 없음).
 * window.FOMS_DS_SEARCH_ROWS 로 내놓는다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var sv = window.FOMS_DS_SEARCH_VIEW;
  var view = window.FOMS_BRAIN_VIEW;
  if (!dom || !sv || !view) return;

  var COLUMNS = 9;

  /** 아이콘(장식) — Blueprint 이름 + 더할 class. */
  function icon(name, extra) {
    return dom.el('span', { cls: 'f-i i-' + name + (extra ? ' ' + extra : ''), attrs: { 'aria-hidden': 'true' } });
  }

  /** 꼬리표. */
  function tag(text, cls) {
    return dom.el('span', { cls: 'f-tag' + (cls ? ' ' + cls : ''), text: text });
  }

  /** 아이콘 + 글 한 덩어리(f-type — 작은 회색 글). */
  function typeMark(name, text) {
    var node = dom.el('span', { cls: 'f-type' });
    node.appendChild(icon(name));
    node.appendChild(document.createTextNode(text));
    return node;
  }

  function cell(child, cls) {
    var td = dom.el('td', { cls: cls || null });
    if (typeof child === 'string') td.textContent = child;
    else if (child) td.appendChild(child);
    return td;
  }

  /** 지식 줄 하나 — ctx: {display, icons, itemBase}. */
  function itemRow(ctx, item) {
    var m = sv.rowModel(item, ctx.display, ctx.icons);
    var tr = dom.el('tr', { cls: 'fb-row', attrs: { 'data-ds-row-key': m.key, tabindex: '0' } });
    var name = dom.el('td', { cls: 'fb-row__name' });
    name.appendChild(dom.el('a', { cls: 'f-strong', text: m.name, attrs: { href: view.itemHref(ctx.itemBase, m.key) } }));
    var under = dom.el('span', { cls: 'f-row-nw f-gap4' });
    under.appendChild(typeMark(m.icon, m.typeLabel));
    m.flags.forEach(function (f) { under.appendChild(tag(f.text, f.cls + ' fb-flag')); });
    name.appendChild(under);
    tr.appendChild(name);
    tr.appendChild(cell(m.team, 'f-td-nw'));
    tr.appendChild(cell(m.brand, 'f-td-nw'));
    tr.appendChild(cell(tag(m.status, m.statusCls), 'f-td-nw'));
    var conf = dom.el('span', { cls: 'f-row-nw f-gap4' });
    conf.appendChild(icon(m.confIcon, m.confCls));
    conf.appendChild(document.createTextNode(m.conf));
    tr.appendChild(cell(conf, 'f-td-nw'));
    tr.appendChild(cell(m.gradeCls ? tag(m.grade, m.gradeCls) : m.grade, 'f-td-nw'));
    tr.appendChild(cell(m.used, 'f-td-num'));
    tr.appendChild(cell(m.checked, 'f-td-nw f-num'));
    tr.appendChild(cell(m.due.warn ? tag(m.due.text, 'f-tag-minimal f-tag-warning') : m.due.text, 'f-td-nw f-num'));
    return tr;
  }

  /** 유형 묶음 머리 줄(찾기) — 앞 몇 개만 왔으면 '표에서 모두 보기'. */
  function groupRow(ctx, group) {
    var tr = dom.el('tr', { cls: 'fb-group-row' });
    var th = dom.el('th', { attrs: { colspan: String(COLUMNS), scope: 'colgroup' } });
    var head = dom.el('span', { cls: 'f-row-nw' });
    var info = (ctx.display.types || {})[group.type];
    var title = dom.el('span', { cls: 'f-row-nw f-gap4 f-strong' });
    title.appendChild(icon((ctx.icons || {})[group.type] || 'circle', 'f-i-muted'));
    title.appendChild(document.createTextNode(info ? info.label : group.type));
    head.appendChild(title);
    head.appendChild(dom.el('span', { cls: 'f-count', text: sv.num(group.count) }));
    if (group.count > (group.items || []).length) {
      head.appendChild(dom.el('a', { cls: 'f-btn f-btn-minimal f-btn-small f-push', text: '표에서 모두 보기',
                                     attrs: { href: ctx.pageUrl + sv.pageQuery('table', group.type),
                                              'data-ds-type': group.type } }));
    }
    th.appendChild(head);
    tr.appendChild(th);
    return tr;
  }

  /** 빈 줄 하나(글만). */
  function noteRow(text) {
    var tr = dom.el('tr', { cls: 'fb-note-row' });
    tr.appendChild(dom.el('td', { cls: 'f-muted', text: text, attrs: { colspan: String(COLUMNS) } }));
    return tr;
  }

  window.FOMS_DS_SEARCH_ROWS = { icon: icon, tag: tag, typeMark: typeMark, itemRow: itemRow, groupRow: groupRow,
                                 noteRow: noteRow };
})();
