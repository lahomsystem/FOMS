/**
 * 협력사 명세서 — 확정한 옵션 고치기(설계서 docs/specs/2026-11-11-partner-confirmed-option-fix_SPEC.md §2.1).
 *
 * - partner-statement-edit.js 가 초안 묶음 머리의 "옵션 고치기"를 누르면 FomsStatementOptions.open({...}) 을 부른다.
 * - GET {api}/<id>/options 로 그 품목의 확정 옵션 · 협력사 원문 · 고를 목록(이름 · 단위만)을 받아 묶음 표 자리에 고치기 칸을 그린다.
 *   고르기 창은 도면팀 전달 창 · CS 옵션 채우기와 같은 부품(ErpSpecPicker.openMulti). "상담 후 정함"은 없다(이미 확정).
 * - 저장 = POST 같은 주소 {version, items: {uid: {state, lines, customs, reason}}}. 바뀐 품목은 이유가 꼭 있어야 하고 협력사에게 보인다.
 *   서버가 같은 트랜잭션에서 명세서를 다시 세어 돌려주면 onSaved(명세서) 로 넘긴다. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var NONE = '옵션 없음';

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

  function summary(opt) {
    if (!opt) return '';
    if (opt.state === 'none') return NONE;
    var parts = (opt.lines || []).map(function (l) { return l.name + ' ' + l.qty + (l.unit || '개'); });
    (opt.customs || []).forEach(function (c) { parts.push('커스텀: ' + c.text); });
    return parts.join(' · ');
  }

  function Editor(opts, view, item) {
    this.opts = opts;
    this.view = view;
    this.item = item;
    var cur = item.current || {};
    this.edit = { state: cur.state, customs: (cur.customs || []).map(function (c) { return { text: c.text }; }),
      lines: (cur.lines || []).map(function (l) { return { key: l.key, name: l.name, qty: String(l.qty), memo: l.memo || '', unit: l.unit }; }) };
    this.box = el('div', 'foms-pse__optfix');
    this.reason = el('input', 'foms-pse__input foms-pse__reason');
    this.reason.maxLength = 200;
    this.reason.placeholder = '바꾼 이유 (협력사에게 보임)';
    this.reason.setAttribute('aria-label', '옵션을 바꾼 이유');
    this.list = el('div', 'pp-optbox');
  }

  Editor.prototype.fixState = function () {
    if (this.edit.state === 'chosen' && !this.edit.lines.length && !this.edit.customs.length) this.edit.state = '';
  };

  Editor.prototype.lineRow = function (line, i) {
    var self = this;
    var row = el('div', 'pp-optline');
    row.appendChild(el('span', 'pp-optline__name', line.name));
    var qty = el('span', 'pp-optline__qty');
    var minus = button(null, '−', line.name + ' 수 줄이기');
    var plus = button(null, '+', line.name + ' 수 늘리기');
    minus.addEventListener('click', function () { line.qty = String(Math.max(1, (parseFloat(line.qty) || 1) - 1)); self.draw(); });
    plus.addEventListener('click', function () { line.qty = String(Math.min(999, (parseFloat(line.qty) || 1) + 1)); self.draw(); });
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
    del.addEventListener('click', function () { self.edit.lines.splice(i, 1); self.fixState(); self.draw(); });
    row.appendChild(del);
    return row;
  };

  Editor.prototype.customRow = function (custom, i) {
    var self = this;
    var row = el('div', 'pp-optline pp-optline--custom');
    row.appendChild(el('span', 'pp-optline__name', '커스텀'));
    var text = el('input', 'pp-optline__memo');
    text.value = custom.text || '';
    text.maxLength = 200;
    text.placeholder = '무엇을 어떻게 할지 적어 주세요';
    text.addEventListener('input', function () { custom.text = text.value; });
    row.appendChild(text);
    var del = button('pp-optline__del', '✕', '커스텀 지우기');
    del.addEventListener('click', function () { self.edit.customs.splice(i, 1); self.fixState(); self.draw(); });
    row.appendChild(del);
    return row;
  };

  Editor.prototype.pick = function () {
    var self = this;
    if (!window.ErpSpecPicker) { self.opts.status('고르기 창을 불러오지 못했습니다. 화면을 새로 고쳐 주세요.'); return; }
    var groups = [{ label: '없을 때', items: [{ key: 's:none', label: NONE, meta: '', payload: { kind: 'none' } }] }];
    (self.view.catalog || []).forEach(function (g) {
      var items = (g.items || []).filter(function (it) { return !(it.only || []).length || it.only.indexOf(self.item.title) !== -1; })
        .map(function (it) { return { key: 'o:' + it.name, label: it.name, meta: '단위 ' + (it.unit || '개'), payload: { kind: 'opt', key: it.key, name: it.name, unit: it.unit } }; });
      if (items.length) groups.push({ label: g.label, items: items });
    });
    groups.push({ label: '목록에 없는 것', items: [{ key: 'c:custom', label: '커스텀(직접 적기)', meta: '', payload: { kind: 'custom' } }] });
    var selected = self.edit.lines.map(function (l) { return 'o:' + l.name; });
    if (self.edit.customs.length) selected.push('c:custom');
    if (self.edit.state === 'none') selected.push('s:none');
    window.ErpSpecPicker.openMulti({
      title: '옵션 고르기 — 항목 ' + self.item.no, groups: groups, selectedKeys: selected,
      onConfirm: function (payloads) {
        var chosen = (payloads || []).filter(Boolean);
        var picked = chosen.filter(function (p) { return p.kind === 'opt'; });
        var custom = chosen.some(function (p) { return p.kind === 'custom'; });
        if (picked.length || custom) {
          self.edit.lines = picked.map(function (p) {
            return self.edit.lines.filter(function (l) { return l.name === p.name; })[0] || { key: p.key, name: p.name, qty: '1', memo: '', unit: p.unit };
          });
          self.edit.customs = custom ? (self.edit.customs.length ? self.edit.customs : [{ text: '' }]) : [];
          self.edit.state = 'chosen';
        } else {
          self.edit.lines = [];
          self.edit.customs = [];
          self.edit.state = chosen.some(function (p) { return p.kind === 'none'; }) ? 'none' : '';
        }
        self.draw();
      }
    });
  };

  Editor.prototype.draw = function () {
    var self = this;
    self.list.replaceChildren();
    if (self.edit.state === 'none') {
      var row = el('div', 'pp-optline pp-optline--special');
      row.appendChild(el('span', 'pp-optline__name', NONE));
      self.list.appendChild(row);
    }
    self.edit.lines.forEach(function (line, i) { self.list.appendChild(self.lineRow(line, i)); });
    self.edit.customs.forEach(function (c, i) { self.list.appendChild(self.customRow(c, i)); });
    var more = button('pp-optmore', self.edit.state ? '+ 옵션 더 고르기' : '+ 옵션 고르기');
    more.addEventListener('click', function () { self.pick(); });
    self.list.appendChild(more);
  };

  Editor.prototype.payload = function () {
    var e = this.edit;
    if (!e.state) return { error: '옵션을 골라 주세요. 없으면 "옵션 없음"을 고르면 됩니다.' };
    if (e.customs.some(function (c) { return !(c.text || '').trim(); })) return { error: '커스텀 내용을 적어 주세요.' };
    var data = {};
    data[this.item.uid] = { state: e.state, reason: this.reason.value.trim(),
      lines: e.lines.map(function (l) { return { key: l.key, name: l.name, qty: l.qty, memo: (l.memo || '').trim() }; }),
      customs: e.customs.map(function (c) { return { text: (c.text || '').trim() }; }) };
    return { data: data };
  };

  Editor.prototype.mount = function () {
    var self = this;
    var opts = self.opts;
    var table = opts.card.querySelector('table');
    if (table) table.hidden = true;
    self.box.appendChild(el('div', 'small text-muted', '협력사가 처음 고른 것: ' + (summary(self.item.partner) || '없음')));
    self.box.appendChild(self.list);
    self.box.appendChild(self.reason);
    var actions = self.box.appendChild(el('div', 'foms-pse__optfix-actions'));
    var save = actions.appendChild(button('foms-ps__btn foms-ps__btn--primary', '옵션 저장 · 다시 계산'));
    var cancel = actions.appendChild(button('foms-ps__btn', '그만두기'));
    cancel.addEventListener('click', function () { self.box.remove(); if (table) table.hidden = false; opts.status(''); });
    save.addEventListener('click', async function () {
      var out = self.payload();
      if (out.error) { opts.status(out.error); return; }
      save.disabled = true;
      var res = await call(opts.api + '/' + opts.id + '/options', { version: opts.version, items: out.data });
      save.disabled = false;
      if (!res.ok) { opts.status(res.error); return; }
      opts.onSaved(res.data);
      opts.status('옵션을 고치고 다시 계산했습니다.');
    });
    opts.card.appendChild(self.box);
    self.draw();
  };

  async function open(opts) {
    if (opts.card.querySelector('.foms-pse__optfix')) return;
    var res = await call(opts.api + '/' + opts.id + '/options');
    if (!res.ok) { opts.status(res.error); return; }
    var item = (res.data.items || []).filter(function (it) { return it.uid === opts.uid; })[0];
    if (!item) { opts.status('이 제품의 확정 옵션을 찾지 못했습니다. 화면을 새로 고쳐 주세요.'); return; }
    new Editor(opts, res.data, item).mount();
  }

  window.FomsStatementOptions = { open: open };
})();
