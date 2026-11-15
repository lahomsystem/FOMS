/**
 * 새 승인 대기 화면 — ① 이름 · ④ 표시 · ⑤ 계산기 제품 · 옵션 · ⑥ 규칙 잇기 묶음의 표 한 장(설계서 2026-11-14-foms-graft 5.4 ·
 * 옛 brain-inbox-table.js 와 같은 규칙 — D151 · D191 · D194 · F24). 표는 등급과 상관없이 한꺼번에 승인하는 묶음(서버
 * wide_bins)을 PC 로 열 때만 그린다.
 * - 줄은 처음에 체크를 끈 채(F24) · 쓸 수 없는 줄(한꺼번에 안 됨 · 기준 판 바뀜)은 disabled · 머리 '모두 고르기'는 줄을 따라간다.
 * - ① 은 새 한글 이름 칸을 고칠 수 있고, 고친 줄은 하나씩 '고쳐서 승인'으로 간다(ds-inbox-act.js).
 * 카드가 없으면 아무것도 안 그린다(F27). 글은 textContent 만 · 인라인 스타일 없음.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !kit) return;
  var el = dom.el;
  var PREF = 'payload.pref_label';
  var ALIASES = 'payload.aliases';
  var SHOWN_WORDS = 3;
  var KINDS = { product_line: '제품', option: '옵션' };
  var BRANDS = { LAHOM: '라홈', HAUD: '하우드', COMMON: '공통' };

  function rowOf(view, field) {
    var rows = (view && view.fields) || [];
    for (var i = 0; i < rows.length; i += 1) if (rows[i].field === field) return rows[i];
    return null;
  }

  /** 비슷한 말 — 앞 세 개만 「」로, 나머지는 +수. */
  function words(list) {
    var all = Array.isArray(list) ? list : [];
    var out = all.slice(0, SHOWN_WORDS).map(function (w) { return '「' + w + '」'; }).join(' ');
    return all.length > SHOWN_WORDS ? out + ' 「+' + (all.length - SHOWN_WORDS) + '」' : (out || '(없음)');
  }

  function usable(view) {
    return !!view.bulk_ok && !(view.base && view.base.changed);
  }

  function check(view, label) {
    var box = el('input', { attrs: { type: 'checkbox', 'data-ds-row-check': view.id, 'aria-label': label + ' 승인' } });
    box.checked = false;  // 고른 줄만 승인(F24) — 쓸 수 있는지는 disabled 로만
    box.disabled = !usable(view);
    return el('td', { children: [el('span', { cls: 'f-check', children: [box] })] });
  }

  function head(titles, ready) {
    var all = el('input', { attrs: { type: 'checkbox', 'data-ds-check-all': '1', 'aria-label': '모두 고르기' } });
    all.checked = false;
    all.disabled = !ready;
    var tr = el('tr', { children: [el('th', { attrs: { scope: 'col' }, children: [el('span', { cls: 'f-check', children: [all] })] })] });
    titles.forEach(function (t) { tr.appendChild(el('th', { text: t, attrs: { scope: 'col' } })); });
    return el('thead', { children: [tr] });
  }

  function rowBoxes(table) {
    return Array.prototype.slice.call(table.querySelectorAll('[data-ds-row-check]')).filter(function (b) { return !b.disabled; });
  }

  /** 머리 상자가 줄을 따라간다 — 모두 체크면 체크 · 일부면 반쯤 · 없으면 꺼짐. */
  function syncAll(table) {
    var all = table.querySelector('[data-ds-check-all]');
    var boxes = rowBoxes(table);
    var on = boxes.filter(function (b) { return b.checked; }).length;
    all.checked = !!boxes.length && on === boxes.length;
    all.indeterminate = on > 0 && on < boxes.length;
  }

  function onChange(table, target) {
    var isHead = target.hasAttribute('data-ds-check-all');
    if (isHead) rowBoxes(table).forEach(function (b) { b.checked = target.checked; });
    if (isHead || target.hasAttribute('data-ds-row-check')) syncAll(table);
  }

  function tr(view, cells) {
    return el('tr', { attrs: { 'data-change-id': view.id }, children: cells });
  }

  function nameRow(card) {
    var view = card.main;
    var pref = rowOf(view, PREF);
    var aliases = rowOf(view, ALIASES);
    var after = pref && pref.after !== null && pref.after !== undefined ? String(pref.after) : (card.title || '');
    var input = el('input', { cls: 'f-input', attrs: { type: 'text', maxlength: 60, 'data-ds-row-name': view.id,
                                                        'data-ds-row-was': after, 'aria-label': card.name + ' 새 한글 이름' } });
    input.value = after;
    input.disabled = !usable(view);
    return tr(view, [check(view, card.name), el('td', { cls: 'f-muted', text: card.name }), el('td', { children: [input] }),
                     el('td', { text: words(aliases ? aliases.after : []) })]);
  }

  function calcRow(card) {
    var view = card.main;
    var kind = view.link ? '계산기 값 잇기' : (KINDS[card.type] || card.type || '');
    return tr(view, [check(view, card.title || card.name), el('td', { text: card.title || card.name }), el('td', { text: kind }),
                     el('td', { text: BRANDS[card.brand] || card.brand || '' })]);
  }

  function rulesRow(card) {
    var link = card.main.link || {};
    var rule = link.from_label || link.from || '';
    return tr(card.main, [check(card.main, rule), el('td', { text: rule }), el('td', { text: link.to_label || link.to || '' })]);
  }

  function markRow(card) {
    var link = card.main.link || {};
    return tr(card.main, [check(card.main, card.title || card.name), el('td', { text: card.title || card.name }),
                          el('td', { text: link.to_label || link.to || '' })]);
  }

  var SHAPES = {
    names: { caption: '한글 이름 붙이기', titles: ['지금 이름', '새 한글 이름', '비슷한 말'], row: nameRow,
             help: '이름 칸을 눌러 고칠 수 있어요. 비슷한 말로 물어도 이 지식을 찾아요. 체크한 줄만 승인해요.' },
    calc: { caption: '계산기 제품 · 옵션', titles: ['지식', '종류', '브랜드'], row: calcRow,
            help: '목록을 훑어보고 맞으면 모두 고르기 → 체크한 줄 승인. 금액은 계산기에 그대로 있어요.' },
    rules: { caption: '규칙 잇기', titles: ['규칙', '걸리는 제품 · 옵션 · 공정 단계'], row: rulesRow,
             help: '규칙마다 걸리는 제품 · 옵션이 맞는지 보고 맞는 줄만 체크해 승인해요. 글 · 금액은 그대로예요.' },
    mark: { caption: '같은 값이 적힌 곳 표시', titles: ['지식', '같은 값이 적힌 곳'], row: markRow,
            help: '값을 바꿀 때 같이 고칠 곳을 알려 줘요. 체크한 줄만 승인해요.' }
  };

  /** 표 한 장 + 안내 + '체크한 줄 승인' — 카드가 없으면 아무것도 안 그린다(F27). */
  function render(list, cards, bin) {
    dom.clear(list);
    if (!cards || !cards.length) return;
    var shape = SHAPES[bin] || SHAPES.mark;
    var ready = cards.filter(function (card) { return usable(card.main); }).length;
    var table = el('table', { cls: 'f-table f-table-compact fb-rows' });
    table.appendChild(el('caption', { cls: 'f-sr', text: shape.caption }));
    table.appendChild(head(shape.titles, ready));
    var body = el('tbody');
    cards.forEach(function (card) { body.appendChild(shape.row(card)); });
    table.appendChild(body);
    table.addEventListener('change', function (event) { onChange(table, event.target); });
    var li = el('li', { cls: 'f-card f-card-compact f-col fb-icard' });
    li.appendChild(el('div', { cls: 'f-scroll-x', children: [table] }));
    li.appendChild(el('p', { cls: 'f-help', text: shape.help }));
    var apply = kit.button('체크한 줄 승인', null, 'f-btn-primary', 'tick');
    apply.setAttribute('data-ds-table-apply', bin);
    apply.disabled = !ready;
    li.appendChild(el('div', { cls: 'f-actions', children: [apply] }));
    li.appendChild(kit.statusLine('data-ds-table-status'));
    list.appendChild(li);
  }

  /** 체크한 줄 — 이름을 안 고친 줄은 한꺼번에(ids), 고친 줄은 하나씩(edits: [{id, name}]). */
  function collect(list) {
    var out = { ids: [], edits: [] };
    Array.prototype.slice.call(list.querySelectorAll('[data-ds-row-check]')).forEach(function (box) {
      if (!box.checked || box.disabled) return;
      var id = Number(box.getAttribute('data-ds-row-check'));
      var input = list.querySelector('[data-ds-row-name="' + id + '"]');
      var name = input ? input.value.trim() : '';
      if (input && name && name !== input.getAttribute('data-ds-row-was')) out.edits.push({ id: id, name: name });
      else out.ids.push(id);
    });
    return out;
  }

  window.FOMS_DS_INBOX_TABLE = { render: render, collect: collect, prefField: PREF };
})();
