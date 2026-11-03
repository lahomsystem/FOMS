/**
 * 협력사 입금 장부 — 우리 CS(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.7 — 5단계).
 * GET {api}?org_id= → 잔액 · 최근 입금 · 덜 받은 명세서. 기록 = POST {api}, 지우기 = POST {api}/<id>/void(이유 필수).
 * 명세서를 고르지 않은 입금은 서버가 오래된 명세서부터 채운다. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function won(n) { return Number(n || 0).toLocaleString('ko-KR') + '원'; }

  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
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
    if (!data || !data.success) return { ok: false, error: (data && data.error) || '저장하지 못했습니다. 잠시 뒤 다시 해 주세요.' };
    return { ok: true, data: data.data || {} };
  }

  function init() {
    var root = document.querySelector('[data-pay-root]');
    if (!root || root.dataset.payReady) return;
    root.dataset.payReady = '1';
    var api = root.getAttribute('data-api');
    var form = root.querySelector('[data-pay-form]');
    var orgSel = root.querySelector('[data-pay-org]');
    var state = null;

    function status(text) { root.querySelector('[data-pay-status]').textContent = text || ''; }

    function drawList(data) {
      var list = root.querySelector('[data-pay-list]');
      list.replaceChildren();
      if (!data.payments.length) { list.appendChild(el('p', 'text-muted small', '아직 기록한 입금이 없습니다.')); return; }
      var t = list.appendChild(el('table', 'foms-ps__table'));
      var head = t.appendChild(el('thead')).appendChild(el('tr'));
      ['입금일', '금액', '명세서', '메모', ''].forEach(function (h) { head.appendChild(el('th', null, h)); });
      var body = t.appendChild(el('tbody'));
      data.payments.forEach(function (p) {
        var tr = body.appendChild(el('tr', p.voided ? 'foms-ps__void' : null));
        tr.appendChild(el('td', null, p.paid_on));
        tr.appendChild(el('td', 'foms-ps__num', won(p.amount)));
        tr.appendChild(el('td', null, p.doc_no || '-'));
        tr.appendChild(el('td', null, p.memo + (p.voided ? ' · 지움: ' + p.void_reason : '')));
        var cell = tr.appendChild(el('td'));
        if (p.voided) return;
        var del = cell.appendChild(el('button', 'foms-ps__btn foms-ps__btn--danger', '지우기'));
        del.type = 'button';
        del.addEventListener('click', async function () {
          var reason = window.prompt('입금을 지우는 이유를 적어 주세요.');
          if (!reason) return;
          var res = await call(api + '/' + p.id + '/void', { reason: reason });
          if (!res.ok) { status(res.error); return; }
          draw(res.data);
          status('입금을 지웠습니다.');
        });
      });
    }

    function draw(data) {
      state = data;
      orgSel.replaceChildren();
      data.orgs.forEach(function (o) {
        var opt = orgSel.appendChild(el('option', null, o.name));
        opt.value = o.id;
        opt.selected = o.id === data.org_id;
      });
      root.querySelector('[data-pay-balance]').textContent = data.org_id ? '지금 잔액 ' + won(data.balance) : '';
      root.querySelector('[data-pay-export]').href = api + '/export.csv?org_id=' + (data.org_id || '') + '&month=' + today().slice(0, 7);
      var sel = root.querySelector('[data-pay-statements]');
      sel.replaceChildren(el('option', null, '고르지 않음 (오래된 명세서부터 채움)'));
      sel.options[0].value = '';
      data.statements.forEach(function (s) {
        var opt = sel.appendChild(el('option', null, s.date + ' · ' + s.doc_no + ' · 남은 ' + won(s.left)));
        opt.value = s.id;
      });
      drawList(data);
    }

    async function load(orgId) {
      var res = await call(api + (orgId ? '?org_id=' + orgId : ''));
      if (!res.ok) { status(res.error); return; }
      draw(res.data);
    }

    orgSel.addEventListener('change', function () { load(orgSel.value); });
    form.elements.paid_on.value = today();
    form.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (!state || !state.org_id) return;
      var btn = form.querySelector('button[type=submit]');
      btn.disabled = true;
      var res = await call(api, { org_id: state.org_id, paid_on: form.elements.paid_on.value, amount: form.elements.amount.value,
        statement_id: form.elements.statement_id.value || null, memo: form.elements.memo.value });
      btn.disabled = false;
      if (!res.ok) { status(res.error); return; }
      form.elements.amount.value = '';
      form.elements.memo.value = '';
      draw(res.data);
      status('입금을 기록했습니다.');
    });
    load(null);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  document.addEventListener('foms:erp-shell-fragment-swapped', init);
})();
