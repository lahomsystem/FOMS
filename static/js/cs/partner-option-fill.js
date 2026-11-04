/**
 * 단가표 전 협력사 주문 — 우리 CS 옵션 채우기(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md 결정 12).
 *
 * - GET {api}/orders/<id>/options 로 품목마다 예전 글 칸 · 고를 목록(이름만)을 받아 그린다.
 * - 품목마다 "단가표 제품"(제품명 ▾ 와 같은 목록 — ErpSpecPicker.openSingle)과 옵션(같은 여러 개 고르기 창 openMulti ·
 *   이름 · 수 · 위치 · 커스텀 · 옵션 없음)을 고른다. 이미 옵션이 있는 품목은 건드리지 않는다.
 * - "저장" = POST 같은 주소 {items: {uid: {base, state, lines, customs}}}. 검사는 서버가 다시 한다. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var SPECIAL = { none: '옵션 없음', later: '상담 후 정함' };
  var state = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function button(className, text, label) {
    var b = el('button', className, text);
    b.type = 'button';
    if (label) b.setAttribute('aria-label', label);
    return b;
  }

  async function call(url, body) {
    var res;
    try {
      res = await fetch(url, { method: body ? 'POST' : 'GET', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    } catch (_) {
      return { ok: false, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!data || !data.success) return { ok: false, error: (data && data.error) || '처리하지 못했습니다. 잠시 뒤 다시 해 주세요.' };
    return { ok: true, data: data.data || {} };
  }

  function lineRow(item, line, i) {
    var row = el('div', 'pp-optline');
    row.appendChild(el('span', 'pp-optline__name', line.name));
    var qty = el('span', 'pp-optline__qty');
    var minus = button(null, '−', line.name + ' 수 줄이기');
    var plus = button(null, '+', line.name + ' 수 늘리기');
    minus.addEventListener('click', function () { line.qty = String(Math.max(1, (parseFloat(line.qty) || 1) - 1)); draw(); });
    plus.addEventListener('click', function () { line.qty = String(Math.min(999, (parseFloat(line.qty) || 1) + 1)); draw(); });
    qty.appendChild(minus);
    qty.appendChild(el('b', null, line.qty));
    qty.appendChild(plus);
    row.appendChild(qty);
    row.appendChild(el('span', 'pp-optline__unit', line.unit || '개'));
    var memo = el('input', 'pp-optline__memo');
    memo.value = line.memo || '';
    memo.maxLength = 60;
    memo.placeholder = '위치(선택)';
    memo.addEventListener('input', function () { line.memo = memo.value; });
    row.appendChild(memo);
    var del = button('pp-optline__del', '✕', line.name + ' 지우기');
    del.addEventListener('click', function () { item.lines.splice(i, 1); fixState(item); draw(); });
    row.appendChild(del);
    return row;
  }

  function customRow(item, custom, i) {
    var row = el('div', 'pp-optline pp-optline--custom');
    row.appendChild(el('span', 'pp-optline__name', '커스텀'));
    var text = el('input', 'pp-optline__memo');
    text.value = custom.text || '';
    text.maxLength = 200;
    text.placeholder = '무엇을 어떻게 할지 적어 주세요';
    text.addEventListener('input', function () { custom.text = text.value; });
    row.appendChild(text);
    var del = button('pp-optline__del', '✕', '커스텀 지우기');
    del.addEventListener('click', function () { item.customs.splice(i, 1); fixState(item); draw(); });
    row.appendChild(del);
    return row;
  }

  function fixState(item) {
    if (item.state === 'chosen' && !item.lines.length && !item.customs.length) item.state = '';
  }

  function pickBase(item, anchor) {
    if (!window.ErpSpecPicker) return;
    window.ErpSpecPicker.openSingle({
      title: '단가표 제품 — 항목 ' + item.no, anchor: anchor, current: item.base,
      groups: (state.products || []).map(function (g) {
        return { label: g.label, items: (g.items || []).map(function (n) { return { value: n, text: n }; }) };
      }),
      onPick: function (value) {
        item.base = value;
        item.lines = item.lines.filter(function (l) { return !(l.only || []).length || l.only.indexOf(value) !== -1; });
        fixState(item);
        draw();
      }
    });
  }

  function pickOptions(item) {
    if (!window.ErpSpecPicker) return;
    var special = [{ key: 's:none', label: SPECIAL.none, meta: '', payload: { kind: 'none' } }];
    if (!state.confirmed) special.push({ key: 's:later', label: SPECIAL.later, meta: '협력사가 도면 확인 때 고름', payload: { kind: 'later' } });
    var groups = [{ label: '없거나 아직 모를 때', items: special }];
    (state.catalog || []).forEach(function (g) {
      var items = (g.items || []).filter(function (it) { return !(it.only || []).length || it.only.indexOf(item.base) !== -1; })
        .map(function (it) { return { key: 'o:' + it.name, label: it.name, meta: '단위 ' + (it.unit || '개'), payload: { kind: 'opt', key: it.key, name: it.name, unit: it.unit, only: it.only } }; });
      if (items.length) groups.push({ label: g.label, items: items });
    });
    groups.push({ label: '목록에 없는 것', items: [{ key: 'c:custom', label: '커스텀(직접 적기)', meta: '', payload: { kind: 'custom' } }] });
    var selected = item.lines.map(function (l) { return 'o:' + l.name; });
    if (item.customs.length) selected.push('c:custom');
    if (item.state === 'none' || item.state === 'later') selected.push('s:' + item.state);
    window.ErpSpecPicker.openMulti({
      title: '옵션 고르기 — 항목 ' + item.no, groups: groups, selectedKeys: selected,
      onConfirm: function (payloads) {
        var chosen = (payloads || []).filter(Boolean);
        var opts = chosen.filter(function (p) { return p.kind === 'opt'; });
        var custom = chosen.some(function (p) { return p.kind === 'custom'; });
        if (opts.length || custom) {
          item.lines = opts.map(function (p) {
            return item.lines.filter(function (l) { return l.name === p.name; })[0] || { key: p.key, name: p.name, qty: '1', memo: '', unit: p.unit, only: p.only };
          });
          item.customs = custom ? (item.customs.length ? item.customs : [{ text: '' }]) : [];
          item.state = 'chosen';
        } else {
          var sp = chosen.filter(function (p) { return p.kind === 'none' || p.kind === 'later'; })[0];
          item.lines = [];
          item.customs = [];
          item.state = sp ? sp.kind : '';
        }
        draw();
      }
    });
  }

  function itemNode(item) {
    var wrap = el('div', 'pp-opt-item foms-pof__item');
    var head = [item.title || '(제품명 없음)', item.spec, item.quantity ? item.quantity + '개' : ''].filter(Boolean).join(' · ');
    wrap.appendChild(el('div', 'pp-opt-item__head', '항목 ' + item.no + ' · ' + head));
    (item.texts || []).forEach(function (t) { wrap.appendChild(el('div', 'pp-opt-legacy', t[0] + ': ' + t[1])); });
    if (item.filled) { wrap.appendChild(el('div', 'pp-opt-note', '이미 옵션이 있는 품목입니다(그대로 둡니다).')); return wrap; }
    var base = button('foms-pof__base' + (item.base ? '' : ' is-empty'), '단가표 제품: ' + (item.base || '골라 주세요 ▾'));
    base.addEventListener('click', function () { pickBase(item, base); });
    wrap.appendChild(base);
    var box = el('div', 'pp-optbox');
    if (SPECIAL[item.state]) {
      var row = el('div', 'pp-optline pp-optline--special');
      row.appendChild(el('span', 'pp-optline__name', SPECIAL[item.state]));
      box.appendChild(row);
    }
    item.lines.forEach(function (line, i) { box.appendChild(lineRow(item, line, i)); });
    item.customs.forEach(function (c, i) { box.appendChild(customRow(item, c, i)); });
    var more = button('pp-optmore', item.state ? '+ 옵션 더 고르기' : '+ 옵션 고르기');
    more.addEventListener('click', function () { pickOptions(item); });
    box.appendChild(more);
    wrap.appendChild(box);
    return wrap;
  }

  function draw() {
    var list = document.querySelector('[data-pof-items]');
    if (!list || !state) return;
    list.replaceChildren();
    state.items.forEach(function (item) { list.appendChild(itemNode(item)); });
  }

  function status(text) { document.querySelector('[data-pof-status]').textContent = text || ''; }

  function collect() {
    var data = {};
    var todo = state.items.filter(function (it) { return !it.filled; });
    for (var i = 0; i < todo.length; i += 1) {
      var item = todo[i];
      if (!item.base) return { error: '항목 ' + item.no + ': 단가표 제품을 골라 주세요.' };
      if (!item.state) return { error: '항목 ' + item.no + ' 옵션을 골라 주세요. 없으면 "옵션 없음"을 고르면 됩니다.' };
      if (item.customs.some(function (c) { return !(c.text || '').trim(); })) return { error: '항목 ' + item.no + ' 커스텀 내용을 적어 주세요.' };
      data[item.uid] = { base: item.base, state: item.state,
        lines: item.lines.map(function (l) { return { key: l.key, name: l.name, qty: l.qty, memo: (l.memo || '').trim() }; }),
        customs: item.customs.map(function (c) { return { text: (c.text || '').trim() }; }) };
    }
    return { data: data };
  }

  async function init() {
    var root = document.querySelector('[data-pof-root]');
    if (!root) return;
    var url = root.getAttribute('data-api') + '/orders/' + root.getAttribute('data-order') + '/options';
    var res = await call(url);
    if (!res.ok) { status(res.error); return; }
    state = res.data;
    state.items.forEach(function (it) { Object.assign(it, { state: '', lines: [], customs: [] }); });
    root.querySelector('[data-pof-meta]').textContent = (state.customer_name || '') + ' · ' + state.stage + ' 단계 · ' + (state.confirmed
      ? '협력사가 이미 도면을 확정한 주문입니다. 저장하면 바로 발행 대기에 뜹니다.'
      : '저장하면 도면팀 전달 · 협력사 도면 확인 때 이 값을 이어서 씁니다(확정은 협력사가).');
    draw();
    var save = root.querySelector('[data-pof-save]');
    save.hidden = !state.items.some(function (it) { return !it.filled; });
    save.addEventListener('click', async function () {
      var picked = collect();
      if (picked.error) { status(picked.error); return; }
      save.disabled = true;
      var out = await call(url, { items: picked.data });
      save.disabled = false;
      if (!out.ok) { status(out.error); return; }
      window.location.href = root.getAttribute('data-list');
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
