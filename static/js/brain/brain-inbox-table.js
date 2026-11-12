/**
 * '승인 대기' ① 이름 표 · ④ 표시 표 · ⑤ 계산기 제품 · 옵션 표(HAUD master brain 설계서 7.9 단계 2 · D151 · 온톨로지 4.1
 * D191) — 그 묶음 카드를 표 한 장으로 그린다. ⑤ 는 지식 이름 · 종류 · 브랜드(브랜드 → 이름 순 — brain-inbox-bins.js).
 * ① 은 줄마다 체크 · 지금 이름 · 새 한글 이름(눌러 고침) · 비슷한 말, ④ 는 지식 · 같은 값이 적힌 곳. 글은 textContent 만 · 인라인
 * 스타일 없음. 누름(체크한 것 승인)은 brain-inbox.js 가 받고, 이 파일은 그리기와 고른 줄 모으기만 한다.
 * 줄은 처음에 체크를 끈 채로 그린다 — 단추 한 번에 묶음 전체가 승인되던 사고(F24)를 막는다. 카드가 없으면 표를 안 그린다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  if (!dom) return;
  var el = dom.el;
  var PREF = 'payload.pref_label';
  var ALIASES = 'payload.aliases';
  var SHOWN_WORDS = 3;

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
    var box = el('input', { cls: 'form-check-input', attrs: { type: 'checkbox', 'data-brain-row-check': view.id,
                                                                 'aria-label': label + ' 승인' } });
    box.checked = false;  // 고른 줄만 승인(F24) — 쓸 수 있는지는 disabled 로만
    box.disabled = !usable(view);
    return el('td', { children: [box] });
  }

  /** 머리 — 첫 칸은 '모두 고르기' 체크 상자(사장님 11-08 · 처음엔 꺼짐), 나머지는 칸 이름. */
  function head(titles, ready) {
    var all = el('input', { cls: 'form-check-input', attrs: { type: 'checkbox', 'data-brain-check-all': '1',
                                                              'aria-label': '모두 고르기' } });
    all.checked = false;
    all.disabled = !ready;
    var tr = el('tr', { children: [el('th', { attrs: { scope: 'col' }, children: [all] })] });
    titles.forEach(function (t) { tr.appendChild(el('th', { text: t, attrs: { scope: 'col' } })); });
    return el('thead', { children: [tr] });
  }

  /** 쓸 수 있는(disabled 아닌) 줄 상자. */
  function rowBoxes(table) {
    return Array.prototype.slice.call(table.querySelectorAll('[data-brain-row-check]'))
      .filter(function (box) { return !box.disabled; });
  }

  /** 머리 상자가 줄을 따라간다 — 모두 체크면 체크 · 일부면 반쯤(indeterminate) · 없으면 꺼짐. */
  function syncAll(table) {
    var all = table.querySelector('[data-brain-check-all]');
    var boxes = rowBoxes(table);
    var on = boxes.filter(function (box) { return box.checked; }).length;
    all.checked = !!boxes.length && on === boxes.length;
    all.indeterminate = on > 0 && on < boxes.length;
  }

  /** 머리 상자를 누르면 쓸 수 있는 줄을 모두 켜거나 끈다 — 승인은 여전히 '체크한 줄 승인' → 확인 창 뒤에만. */
  function onChange(table, target) {
    var head = target.hasAttribute('data-brain-check-all');
    if (head) rowBoxes(table).forEach(function (box) { box.checked = target.checked; });
    if (head || target.hasAttribute('data-brain-row-check')) syncAll(table);
  }

  function nameRow(card) {
    var view = card.main;
    var pref = rowOf(view, PREF);
    var aliases = rowOf(view, ALIASES);
    var after = pref && pref.after !== null && pref.after !== undefined ? String(pref.after) : (card.title || '');
    var input = el('input', { cls: 'form-control form-control-sm', attrs: {
      type: 'text', maxlength: 60, 'data-brain-row-name': view.id, 'data-brain-row-was': after,
      'aria-label': card.name + ' 새 한글 이름' } });
    input.value = after;
    input.disabled = !usable(view);
    return el('tr', { attrs: { 'data-change-id': view.id }, children: [
      check(view, card.name), el('td', { cls: 'brain-empty', text: card.name }), el('td', { children: [input] }),
      el('td', { text: words(aliases ? aliases.after : []) })] });
  }

  /** ⑤ 줄 — 지식 이름 · 종류 · 브랜드(만들기) 또는 계산기 값 링크. */
  var KINDS = { product_line: '제품', option: '옵션' };
  var BRANDS = { LAHOM: '라홈', HAUD: '하우드', COMMON: '공통' };

  function calcRow(card) {
    var view = card.main;
    var kind = view.link ? '계산기 값 잇기' : (KINDS[card.type] || card.type || '');
    return el('tr', { attrs: { 'data-change-id': view.id }, children: [
      check(view, card.title || card.name), el('td', { text: card.title || card.name }), el('td', { text: kind }),
      el('td', { text: BRANDS[card.brand] || card.brand || '' })] });
  }

  function markRow(card) {
    var view = card.main;
    var link = view.link || {};
    return el('tr', { attrs: { 'data-change-id': view.id }, children: [
      check(view, card.title || card.name), el('td', { text: card.title || card.name }),
      el('td', { text: link.to_label || link.to || '' })] });
  }

  /** 표 한 장 + 안내 + 승인 단추 — 카드가 없으면 아무것도 안 그린다(F27). */
  function render(list, cards, bin) {
    dom.clear(list);
    if (!cards || !cards.length) return;
    var names = bin === 'names';
    var calc = bin === 'calc';
    var ready = cards.filter(function (card) { return usable(card.main); }).length;
    var table = el('table', { cls: 'brain-diff' });
    table.appendChild(el('caption', { cls: 'visually-hidden',
                                      text: names ? '한글 이름 붙이기' : calc ? '계산기 제품 · 옵션' : '같은 값이 적힌 곳 표시' }));
    table.appendChild(head(names ? ['지금 이름', '새 한글 이름', '비슷한 말']
      : calc ? ['지식', '종류', '브랜드'] : ['지식', '같은 값이 적힌 곳'], ready));
    var body = el('tbody');
    cards.forEach(function (card) { body.appendChild(names ? nameRow(card) : calc ? calcRow(card) : markRow(card)); });
    table.appendChild(body);
    table.addEventListener('change', function (event) { onChange(table, event.target); });
    var li = el('li', { cls: 'brain-icard', children: [el('div', { cls: 'brain-table-wrap', children: [table] })] });
    li.appendChild(el('p', { cls: 'brain-icard__summary', text: names
      ? '이름 칸을 눌러 고칠 수 있어요. 비슷한 말로 물어도 이 지식을 찾아요. 체크한 줄만 승인해요.'
      : calc ? '목록을 훑어보고 맞으면 모두 고르기 → 체크한 줄 승인. 금액은 계산기에 그대로 있어요.'
        : '값을 바꿀 때 같이 고칠 곳을 알려 줘요. 체크한 줄만 승인해요.' }));
    var apply = el('button', { cls: 'brain-btn brain-btn--primary', attrs: { type: 'button', 'data-brain-table-apply': bin },
                               text: '체크한 줄 승인' });
    apply.disabled = !ready;
    li.appendChild(el('div', { cls: 'brain-prop__actions', children: [apply] }));
    li.appendChild(el('p', { cls: 'brain-status-line', attrs: { 'data-brain-table-status': '1', role: 'status',
                                                               'aria-live': 'polite' } }));
    list.appendChild(li);
  }

  /** 체크한 줄 — 이름을 안 고친 줄은 한꺼번에(ids), 고친 줄은 하나씩(edits: [{id, name}]). */
  function collect(list) {
    var out = { ids: [], edits: [] };
    list.querySelectorAll('[data-brain-row-check]').forEach(function (box) {
      if (!box.checked || box.disabled) return;
      var id = Number(box.getAttribute('data-brain-row-check'));
      var input = list.querySelector('[data-brain-row-name="' + id + '"]');
      var name = input ? input.value.trim() : '';
      if (input && name && name !== input.getAttribute('data-brain-row-was')) out.edits.push({ id: id, name: name });
      else out.ids.push(id);
    });
    return out;
  }

  /** '체크한 줄 승인' 확인 창 글 — 한 번 누름에 여러 줄이 바로 바뀐다(F24). */
  function confirmText(n) {
    return '체크한 ' + n + '줄을 승인할까요? 승인하면 바로 바뀌어요(수정 기록은 남아요).';
  }

  window.FOMS_BRAIN_INBOX_TABLE = { render: render, collect: collect, confirmText: confirmText, prefField: PREF };
})();
