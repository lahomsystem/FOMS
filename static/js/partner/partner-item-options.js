/**
 * 협력사 품목 "옵션" 칸 — 단가표 옵션 이름에서 고르기(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.2).
 *
 * - 협력사에 단가표 지금 판이 있을 때만 서버가 [data-pp-option-catalog](이름 · 단위 · '이 제품일 때만', 금액 없음)를 싣고,
 *   품목 카드의 옵션 칸을 [data-pp-optfield] 로 그린다. 나머지 칸(내부 · 색상 · 손잡이 · 기타)은 지금 글 칸 그대로.
 * - 칸을 누르면 우리 계산기 여러 개 고르기 창(ErpSpecPicker.openMulti). 맨 위 "옵션 없음" · "상담 후 정함", 맨 아래 "커스텀".
 * - 고른 줄 = 이름 · 수(−/+) · 단위 · 위치(선택) · ×. 커스텀은 글 한 줄. 끝에 "+ 옵션 더 고르기".
 * - 꼭 넣을 칸: 저장(새 주문 submit · 품목 저장 단추)보다 먼저 검사해 빈 칸은 빨간 테두리 + 그 품목으로 옮긴다.
 * - partner-items.js 가 품목을 모을 때 PartnerItemOptions.read(card) 를 options 로 싣는다(서버가 다시 검사한다).
 * 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var SPECIAL = { none: '옵션 없음', later: '상담 후 정함' };
  var CUSTOM = '커스텀 (직접 적기)';

  function readJson(selector, attr, fallback) {
    var node = document.querySelector(selector);
    if (!node) return fallback;
    try { return JSON.parse(node.getAttribute(attr) || '') || fallback; } catch (_) { return fallback; }
  }

  var catalog = readJson('[data-pp-option-catalog]', 'data-pp-option-catalog', null);
  if (!Array.isArray(catalog)) return;
  var saved = readJson('[data-pp-item-options]', 'data-pp-item-options', {});
  var UNIT = {};
  catalog.forEach(function (g) { (g.items || []).forEach(function (it) { UNIT[it.name] = it.unit || '개'; }); });

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

  function stateOf(field) {
    if (!field._ppOpt) {
      var card = field.closest('.pp-item');
      var uid = card && card.getAttribute('data-pp-uid');
      var old = uid && saved[uid];
      field._ppOpt = old ? { state: old.state, lines: (old.lines || []).map(function (l) { return Object.assign({}, l); }),
                             customs: (old.customs || []).map(function (c) { return { text: c.text || '' }; }) }
                         : { state: null, lines: [], customs: [] };
      var legacy = card && card.querySelector('[data-pp-opt-legacy]');
      if (legacy && old) legacy.remove();
    }
    return field._ppOpt;
  }

  function productOf(field) {
    var card = field.closest('.pp-item');
    var input = card && card.querySelector('[data-k="product_name"]');
    return input ? input.value.trim() : '';
  }

  // ── 그리기 ────────────────────────────────────────────────────────────
  function lineNode(field, st, line, i) {
    var row = el('div', 'pp-optline');
    row.appendChild(el('span', 'pp-optline__name', line.name));
    var qty = el('span', 'pp-optline__qty');
    var minus = button(null, '−', line.name + ' 하나 빼기');
    var plus = button(null, '+', line.name + ' 하나 더하기');
    qty.appendChild(minus);
    qty.appendChild(el('b', null, line.qty));
    qty.appendChild(plus);
    minus.addEventListener('click', function () { line.qty = String(Math.max(1, (parseFloat(line.qty) || 1) - 1)); render(field); });
    plus.addEventListener('click', function () { line.qty = String(Math.min(999, (parseFloat(line.qty) || 1) + 1)); render(field); });
    row.appendChild(qty);
    row.appendChild(el('span', 'pp-optline__unit', UNIT[line.name] || '개'));
    var memo = el('input', 'pp-optline__memo');
    memo.value = line.memo || '';
    memo.maxLength = 60;
    memo.placeholder = '위치 (선택)';
    memo.setAttribute('aria-label', line.name + ' 위치');
    memo.addEventListener('input', function () { line.memo = memo.value; });
    row.appendChild(memo);
    var del = button('pp-optline__del', '✕', line.name + ' 빼기');
    del.addEventListener('click', function () { st.lines.splice(i, 1); if (!st.lines.length && !st.customs.length) st.state = null; render(field); });
    row.appendChild(del);
    return row;
  }

  function customNode(field, st, custom, i) {
    var row = el('div', 'pp-optline pp-optline--custom');
    row.appendChild(el('span', 'pp-optline__name', '커스텀'));
    var text = el('input', 'pp-optline__memo');
    text.value = custom.text || '';
    text.maxLength = 200;
    text.placeholder = '무엇을 어떻게 (저희가 따로 견적)';
    text.setAttribute('aria-label', '커스텀 내용');
    text.addEventListener('input', function () { custom.text = text.value; });
    row.appendChild(text);
    var del = button('pp-optline__del', '✕', '커스텀 빼기');
    del.addEventListener('click', function () { st.customs.splice(i, 1); if (!st.lines.length && !st.customs.length) st.state = null; render(field); });
    row.appendChild(del);
    return row;
  }

  function render(field) {
    var st = stateOf(field);
    var error = field.querySelector('.pp-optbox.is-error');
    var box = el('div', 'pp-optbox' + (error ? ' is-error' : ''));
    if (st.state === 'none' || st.state === 'later') {
      var row = el('div', 'pp-optline pp-optline--special');
      row.appendChild(el('span', 'pp-optline__name', SPECIAL[st.state]));
      var del = button('pp-optline__del ms-auto', '✕', SPECIAL[st.state] + ' 빼기');
      del.addEventListener('click', function () { st.state = null; render(field); });
      row.appendChild(del);
      box.appendChild(row);
    } else if (st.lines.length || st.customs.length) {
      st.lines.forEach(function (line, i) { box.appendChild(lineNode(field, st, line, i)); });
      st.customs.forEach(function (c, i) { box.appendChild(customNode(field, st, c, i)); });
      var more = button('pp-optmore', '+ 옵션 더 고르기');
      more.addEventListener('click', function () { pick(field); });
      box.appendChild(more);
    } else {
      var empty = button('pp-optempty', null, '옵션 고르기');
      empty.appendChild(el('span', null, '옵션 고르기 — 없으면 "옵션 없음"'));
      empty.appendChild(el('span', null, '▾'));
      empty.addEventListener('click', function () { pick(field); });
      box.appendChild(empty);
    }
    Array.prototype.forEach.call(field.querySelectorAll('.pp-optbox'), function (old) { old.remove(); });
    field.appendChild(box);
  }

  // ── 고르기 창 ─────────────────────────────────────────────────────────
  function pick(field) {
    if (!window.ErpSpecPicker) return;
    var st = stateOf(field);
    var product = productOf(field);
    var groups = [{ label: '선택 없음', items: [
      { key: 's:none', label: SPECIAL.none, meta: '', payload: { kind: 'none' } },
      { key: 's:later', label: SPECIAL.later, meta: '', payload: { kind: 'later' } }] }];
    catalog.forEach(function (g) {
      var items = (g.items || []).filter(function (it) { return !(it.only || []).length || it.only.indexOf(product) !== -1; })
        .map(function (it) { return { key: 'o:' + it.name, label: it.name, meta: '단위 ' + (it.unit || '개'), payload: { kind: 'opt', key: it.key, name: it.name } }; });
      if (items.length) groups.push({ label: g.label, items: items });
    });
    groups.push({ label: '목록에 없는 것', items: [{ key: 'c:custom', label: CUSTOM, meta: '', payload: { kind: 'custom' } }] });
    var selected = st.lines.map(function (l) { return 'o:' + l.name; });
    if (st.customs.length) selected.push('c:custom');
    if (st.state === 'none' || st.state === 'later') selected.push('s:' + st.state);
    window.ErpSpecPicker.openMulti({
      title: '옵션 고르기',
      groups: groups,
      selectedKeys: selected,
      onConfirm: function (payloads) {
        var chosen = (payloads || []).filter(Boolean);
        var opts = chosen.filter(function (p) { return p.kind === 'opt'; });
        var custom = chosen.some(function (p) { return p.kind === 'custom'; });
        if (opts.length || custom) {
          st.lines = opts.map(function (p) {
            return st.lines.filter(function (l) { return l.name === p.name; })[0] || { key: p.key, name: p.name, qty: '1', memo: '' };
          });
          st.customs = custom ? (st.customs.length ? st.customs : [{ text: '' }]) : [];
          st.state = 'chosen';
        } else {
          var special = chosen.filter(function (p) { return p.kind === 'none' || p.kind === 'later'; })[0];
          st.lines = [];
          st.customs = [];
          st.state = special ? special.kind : null;
        }
        var box = field.querySelector('.pp-optbox');
        if (box && box.classList.contains('is-error')) showStatus('');  // 고쳤으면 빨간 안내를 지운다
        if (box) box.classList.remove('is-error');
        render(field);
      }
    });
  }

  // ── 읽기 · 검사 ───────────────────────────────────────────────────────
  function read(card) {
    var field = card.querySelector('[data-pp-optfield]');
    if (!field) return null;
    var st = stateOf(field);
    return {
      state: st.state,
      lines: st.lines.map(function (l) { return { key: l.key, name: l.name, qty: l.qty, memo: (l.memo || '').trim() }; }),
      customs: st.customs.map(function (c) { return { text: (c.text || '').trim() }; })
    };
  }

  function missing(card) {
    var field = card.querySelector('[data-pp-optfield]');
    var name = card.querySelector('[data-k="product_name"]');
    if (!field || !name || !name.value.trim()) return false;
    var st = stateOf(field);
    if (st.state === 'none' || st.state === 'later') return false;
    if (st.customs.some(function (c) { return !(c.text || '').trim(); })) return true;
    return !(st.lines.length || st.customs.length);
  }

  function showStatus(text) {
    if (window.PartnerPortal && window.PartnerPortal.setStatus) { window.PartnerPortal.setStatus(text, !!text); return; }
    var node = document.getElementById('ppStatus');
    if (node) node.textContent = text;
  }

  /** 빈 옵션 칸이 있으면 true — 빨간 테두리 · 그 품목으로 옮기기 · 안내 글. */
  function blockIfMissing() {
    var cards = Array.prototype.slice.call(document.querySelectorAll('[data-pp-items] .pp-item'));
    var bad = cards.filter(missing);
    cards.forEach(function (card) {
      var box = card.querySelector('[data-pp-optfield] .pp-optbox');
      if (box) box.classList.toggle('is-error', bad.indexOf(card) !== -1);
    });
    if (!bad.length) return false;
    var index = cards.indexOf(bad[0]);
    var railItem = document.querySelectorAll('[data-pp-rail-list] .rail-item')[index];
    if (railItem && window.matchMedia('(min-width: 768px)').matches) railItem.click();
    var box = bad[0].querySelector('[data-pp-optfield]');
    if (box) box.scrollIntoView({ block: 'center', behavior: 'smooth' });
    showStatus('항목 ' + (index + 1) + ' 옵션을 골라 주세요. 없으면 "옵션 없음"을 고르면 됩니다. 커스텀은 내용을 적어 주세요.');
    return true;
  }

  // 저장(새 주문 submit · 품목 저장 단추 [data-pp-items-url])보다 먼저 — 캡처 단계라 저장 스크립트보다 앞선다.
  document.addEventListener('submit', function (ev) {
    if (ev.target && ev.target.id === 'ppNewOrder' && blockIfMissing()) { ev.preventDefault(); ev.stopImmediatePropagation(); }
  }, true);
  document.addEventListener('click', function (ev) {
    if (ev.target.closest && ev.target.closest('[data-pp-items-url]') && blockIfMissing()) { ev.preventDefault(); ev.stopImmediatePropagation(); }
  }, true);

  function renderAll() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-pp-optfield]'), function (field) {
      if (!field.querySelector('.pp-optbox')) render(field);
    });
  }
  document.addEventListener('DOMContentLoaded', function () {
    renderAll();
    var items = document.querySelector('[data-pp-items]');
    if (items) items.addEventListener('pp:items-changed', renderAll);
  });

  window.PartnerItemOptions = { read: read };
})();
