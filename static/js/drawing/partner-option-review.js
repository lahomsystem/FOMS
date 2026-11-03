/**
 * 도면 작업실 "도면 전달" 창 — 협력사 주문 옵션 확인(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.3 · 3단계).
 *
 * - 창이 열리면 GET [data-po-review] data-url(/api/orders/<id>/partner-options)로 품목마다 협력사 옵션(지금 값)을 그린다.
 *   협력사 주문이 아니거나 옵션 줄이 없으면 칸을 숨긴다(지금 전달 그대로).
 * - 도면대로 바뀌면 같은 칸에서 고친다(우리 계산기 여러 개 고르기 창 · 이름 · 수 · 위치 · 커스텀). 협력사가 고른 것과
 *   달라진 품목은 노란 칸에 까닭 한 줄이 꼭 있어야 한다. "상담 후 정함" 품목은 안내만(전달은 막지 않음 — 협력사가 도면 확인 때 고른다).
 * - 전달 스크립트가 FomsPartnerOptionReview.collect() 를 불러 {ok, error, data} 를 받는다. data 는 전달 요청의 partner_options.
 * 글은 textContent 로만 넣는다.
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

  function sig(opt) {
    var lines = (opt.lines || []).map(function (l) { return l.name + '=' + String(l.qty); }).sort();
    var customs = (opt.customs || []).map(function (c) { return (c.text || '').trim(); });
    return opt.state + '|' + lines.join(',') + '|' + customs.join(',');
  }

  function changed(item) {
    return item.partner && sig(item.partner) !== sig(item.edit);
  }

  function units() {
    var map = {};
    (state.catalog || []).forEach(function (g) { (g.items || []).forEach(function (it) { map[it.name] = it.unit || '개'; }); });
    return map;
  }

  function lineRow(item, line, i, unitMap) {
    var row = el('div', 'pp-optline');
    row.appendChild(el('span', 'pp-optline__name', line.name));
    var qty = el('span', 'pp-optline__qty');
    var minus = button(null, '−', line.name + ' 하나 빼기');
    var plus = button(null, '+', line.name + ' 하나 더하기');
    minus.addEventListener('click', function () { line.qty = String(Math.max(1, (parseFloat(line.qty) || 1) - 1)); draw(); });
    plus.addEventListener('click', function () { line.qty = String(Math.min(999, (parseFloat(line.qty) || 1) + 1)); draw(); });
    qty.appendChild(minus);
    qty.appendChild(el('b', null, line.qty));
    qty.appendChild(plus);
    row.appendChild(qty);
    row.appendChild(el('span', 'pp-optline__unit', line.unit || unitMap[line.name] || '개'));
    var memo = el('input', 'pp-optline__memo');
    memo.value = line.memo || '';
    memo.maxLength = 60;
    memo.placeholder = '위치 (선택)';
    memo.addEventListener('input', function () { line.memo = memo.value; });
    row.appendChild(memo);
    var del = button('pp-optline__del', '✕', line.name + ' 빼기');
    del.addEventListener('click', function () { item.edit.lines.splice(i, 1); fixState(item); draw(); });
    row.appendChild(del);
    return row;
  }

  function customRow(item, custom, i) {
    var row = el('div', 'pp-optline pp-optline--custom');
    row.appendChild(el('span', 'pp-optline__name', '커스텀'));
    var text = el('input', 'pp-optline__memo');
    text.value = custom.text || '';
    text.maxLength = 200;
    text.placeholder = '무엇을 어떻게';
    text.addEventListener('input', function () { custom.text = text.value; refreshDiff(item); });
    row.appendChild(text);
    var del = button('pp-optline__del', '✕', '커스텀 빼기');
    del.addEventListener('click', function () { item.edit.customs.splice(i, 1); fixState(item); draw(); });
    row.appendChild(del);
    return row;
  }

  function fixState(item) {
    if (item.edit.state === 'chosen' && !item.edit.lines.length && !item.edit.customs.length) item.edit.state = 'later';
  }

  function pick(item) {
    if (!window.ErpSpecPicker) return;
    var groups = [{ label: '선택 없음', items: [
      { key: 's:none', label: SPECIAL.none, meta: '', payload: { kind: 'none' } },
      { key: 's:later', label: SPECIAL.later, meta: '', payload: { kind: 'later' } }] }];
    (state.catalog || []).forEach(function (g) {
      var items = (g.items || []).filter(function (it) { return !(it.only || []).length || it.only.indexOf(item.title) !== -1; })
        .map(function (it) { return { key: 'o:' + it.name, label: it.name, meta: '단위 ' + (it.unit || '개'), payload: { kind: 'opt', key: it.key, name: it.name, unit: it.unit } }; });
      if (items.length) groups.push({ label: g.label, items: items });
    });
    groups.push({ label: '목록에 없는 것', items: [{ key: 'c:custom', label: '커스텀 (직접 적기)', meta: '', payload: { kind: 'custom' } }] });
    var edit = item.edit;
    var selected = edit.lines.map(function (l) { return 'o:' + l.name; });
    if (edit.customs.length) selected.push('c:custom');
    if (edit.state !== 'chosen') selected.push('s:' + edit.state);
    window.ErpSpecPicker.openMulti({
      title: '옵션 고치기 — 항목 ' + item.no, groups: groups, selectedKeys: selected,
      onConfirm: function (payloads) {
        var chosen = (payloads || []).filter(Boolean);
        var opts = chosen.filter(function (p) { return p.kind === 'opt'; });
        var custom = chosen.some(function (p) { return p.kind === 'custom'; });
        if (opts.length || custom) {
          edit.lines = opts.map(function (p) {
            return edit.lines.filter(function (l) { return l.name === p.name; })[0] || { key: p.key, name: p.name, qty: '1', memo: '', unit: p.unit };
          });
          edit.customs = custom ? (edit.customs.length ? edit.customs : [{ text: '' }]) : [];
          edit.state = 'chosen';
        } else {
          var special = chosen.filter(function (p) { return p.kind === 'none' || p.kind === 'later'; })[0];
          edit.lines = [];
          edit.customs = [];
          edit.state = special ? special.kind : 'later';
        }
        draw();
      }
    });
  }

  function refreshDiff(item) {
    if (!item.diffBox) return;
    item.diffBox.hidden = !changed(item);
  }

  function itemNode(item, unitMap) {
    var wrap = el('div', 'pp-opt-item');
    wrap.appendChild(el('div', 'pp-opt-item__head', '항목 ' + item.no + ' · ' + item.title));
    var box = el('div', 'pp-optbox');
    var edit = item.edit;
    if (edit.state !== 'chosen') {
      var row = el('div', 'pp-optline pp-optline--special');
      row.appendChild(el('span', 'pp-optline__name', SPECIAL[edit.state]));
      box.appendChild(row);
    }
    edit.lines.forEach(function (line, i) { box.appendChild(lineRow(item, line, i, unitMap)); });
    edit.customs.forEach(function (c, i) { box.appendChild(customRow(item, c, i)); });
    var more = button('pp-optmore', '+ 옵션 고치기 · 더 고르기');
    more.addEventListener('click', function () { pick(item); });
    box.appendChild(more);
    wrap.appendChild(box);
    if (edit.state === 'later') wrap.appendChild(el('div', 'pp-opt-note', '협력사가 아직 고르지 않았습니다(상담 후 정함) — 도면 확인 때 협력사가 고릅니다. 정해졌으면 여기서 골라도 됩니다.'));
    var diff = el('div', 'pp-opt-diff');
    diff.appendChild(el('div', null, '협력사가 고른 것과 달라졌습니다 — 협력사가 도면 확인 때 이 까닭을 같이 봅니다.'));
    var reason = el('input');
    reason.maxLength = 200;
    reason.placeholder = '까닭 (예: 가운데 통 폭 900 — 서랍 2단 대신 1단)';
    reason.value = item.reason || '';
    reason.addEventListener('input', function () { item.reason = reason.value; });
    diff.appendChild(reason);
    item.diffBox = diff;
    wrap.appendChild(diff);
    refreshDiff(item);
    return wrap;
  }

  function draw() {
    var root = document.querySelector('[data-po-review]');
    var list = root && root.querySelector('[data-po-review-list]');
    if (!list || !state) return;
    var unitMap = units();
    list.replaceChildren();
    state.items.forEach(function (item) { list.appendChild(itemNode(item, unitMap)); });
  }

  async function load() {
    var root = document.querySelector('[data-po-review]');
    if (!root) return;
    root.hidden = true;
    state = null;
    try {
      var res = await fetch(root.getAttribute('data-url'), { credentials: 'same-origin', headers: { Accept: 'application/json' } });
      var body = await res.json();
      if (!body || !body.success || !body.data) return;
      state = { catalog: body.data.catalog || [], items: (body.data.items || []).map(function (it) {
        var cur = it.current || {};
        return { uid: it.uid, no: it.no, title: it.title, partner: it.partner, reason: ((cur.changes || [])[0] || {}).reason || '',
                 edit: { state: cur.state, lines: (cur.lines || []).map(function (l) { return Object.assign({}, l); }),
                         customs: (cur.customs || []).map(function (c) { return { text: c.text || '' }; }) } };
      }) };
      root.hidden = !state.items.length;
      draw();
    } catch (_) {
      state = null;
    }
  }

  function collect() {
    if (!state) return { ok: true, data: null };
    var data = {};
    for (var i = 0; i < state.items.length; i += 1) {
      var item = state.items[i];
      var edit = item.edit;
      if (edit.customs.some(function (c) { return !(c.text || '').trim(); })) return { ok: false, error: '항목 ' + item.no + ' 커스텀 내용을 적어 주세요.' };
      if (changed(item) && !(item.reason || '').trim()) return { ok: false, error: '항목 ' + item.no + ': 협력사가 고른 것과 달라진 옵션의 까닭을 한 줄 적어 주세요.' };
      data[item.uid] = { state: edit.state, reason: (item.reason || '').trim(),
        lines: edit.lines.map(function (l) { return { key: l.key, name: l.name, qty: l.qty, memo: (l.memo || '').trim() }; }),
        customs: edit.customs.map(function (c) { return { text: (c.text || '').trim() }; }) };
    }
    return { ok: true, data: data };
  }

  document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('dwTransferModal');
    if (modal && document.querySelector('[data-po-review]')) modal.addEventListener('show.bs.modal', load);
  });

  window.FomsPartnerOptionReview = { collect: collect };
})();
