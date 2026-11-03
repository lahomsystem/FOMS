/**
 * 협력사 거래명세서 한 장 — 우리 CS(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.5).
 *
 * - GET {api}/<id> 로 묶음 · 줄 · 합계를 그린다. 금액은 서버 값 그대로(저장하면 서버가 다시 낸다).
 * - 초안: 커스텀 줄만 금액 칸, 자동 줄은 "단가 고치기"(이유 필수 — 협력사에게 보인다). 저장 · 다시 계산 · 발행 · 지우기.
 * - 발행본: 인쇄 · 수정본 만들기 · 취소(이유 필수). 취소본: 인쇄만. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-pse-root]');
  if (!root) return;
  var api = root.getAttribute('data-api');
  var id = root.getAttribute('data-id');
  var stmt = null;
  var edits = {};

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function won(n) { return n == null ? '' : Number(n).toLocaleString('ko-KR'); }

  function status(text) { root.querySelector('[data-pse-status]').textContent = text || ''; }

  async function call(path, body) {
    var res;
    try {
      res = await fetch(api + path, { method: body ? 'POST' : 'GET', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    } catch (_) {
      return { ok: false, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!data || !data.success) return { ok: false, error: (data && data.error) || '처리하지 못했습니다. 잠시 뒤 다시 해 주세요.' };
    return { ok: true, data: data.data || {} };
  }

  function input(className, value, label) {
    var node = el('input', 'foms-pse__input ' + className);
    node.value = value == null ? '' : String(value);
    node.setAttribute('aria-label', label);
    return node;
  }

  function priceCell(line, td) {
    var edit = edits[line.ref] || null;
    if (line.source === 'custom' && stmt.status === 'DRAFT') {
      var amount = input('foms-pse__amount', edit ? edit.amount : line.amount, line.name + ' 금액');
      amount.inputMode = 'numeric';
      amount.placeholder = '금액';
      amount.addEventListener('input', function () { edits[line.ref] = { ref: line.ref, amount: amount.value }; });
      td.appendChild(amount);
      return;
    }
    if (!edit) {
      td.appendChild(el('span', null, won(line.unit_price)));
      if (line.source === 'custom') return;
      if (line.source === 'edited') td.appendChild(el('div', 'foms-pse__orig', '원래 ' + won(line.orig_unit_price) + ' · ' + (line.reason || '')));
      if (stmt.status !== 'DRAFT') return;
      var fix = el('button', 'foms-ps__btn foms-ps__btn--link', '단가 고치기');
      fix.type = 'button';
      fix.addEventListener('click', function () {
        edits[line.ref] = { ref: line.ref, unit_price: line.unit_price, reason: line.reason || '' };
        draw();
      });
      td.appendChild(fix);
      return;
    }
    var price = input('foms-pse__amount', edit.unit_price, line.name + ' 단가');
    price.inputMode = 'numeric';
    var reason = input('foms-pse__reason', edit.reason, line.name + ' 단가를 바꾼 이유');
    reason.placeholder = '바꾼 이유 (협력사에게 보임)';
    price.addEventListener('input', function () { edit.unit_price = price.value; });
    reason.addEventListener('input', function () { edit.reason = reason.value; });
    td.appendChild(price);
    td.appendChild(reason);
  }

  function drawGroups() {
    var box = root.querySelector('[data-pse-groups]');
    box.replaceChildren();
    stmt.groups.forEach(function (group) {
      var card = box.appendChild(el('section', 'foms-pse__group'));
      card.appendChild(el('h2', 'foms-pse__group-title', group.ref + '. ' + group.title + ' · 소계 ' + won(group.subtotal) + '원'));
      var t = card.appendChild(el('table', 'foms-ps__table'));
      var head = t.appendChild(el('thead')).appendChild(el('tr'));
      ['품목', '규격', '수량', '단가', '금액', '계산 근거 · 비고'].forEach(function (h) { head.appendChild(el('th', null, h)); });
      var body = t.appendChild(el('tbody'));
      group.lines.forEach(function (line) {
        var tr = body.appendChild(el('tr', line.source === 'custom' ? 'foms-pse__custom' : null));
        tr.appendChild(el('td', null, line.name));
        tr.appendChild(el('td', null, line.spec || ''));
        tr.appendChild(el('td', 'foms-ps__num', line.qty + ' ' + (line.unit || '')));
        priceCell(line, tr.appendChild(el('td', 'foms-ps__num')));
        tr.appendChild(el('td', 'foms-ps__num', won(line.amount)));
        tr.appendChild(el('td', 'small text-muted', [line.note, line.source === 'custom' ? '' : line.basis].filter(Boolean).join(' · ')));
      });
    });
  }

  function drawHead() {
    root.querySelector('[data-pse-title]').textContent = '협력사 명세서 · ' + (stmt.doc_no ? stmt.doc_no + ' · ' : '') + stmt.status_text;
    var meta = ['주문 ' + stmt.order_id, '일자 ' + (stmt.date || '출고일 없음')];
    if (stmt.revision_of) meta.push('수정본 — 옛 명세서 ' + stmt.revision_of + (stmt.reason ? ' · ' + stmt.reason : ''));
    if (stmt.status === 'VOID' && stmt.reason) meta.push('취소 이유: ' + stmt.reason);
    if (stmt.issued_at) meta.push('발행 ' + stmt.issued_at + (stmt.issued_by ? ' · ' + stmt.issued_by : ''));
    if (stmt.partner_ack_at) meta.push('협력사 확인 ' + stmt.partner_ack_at);
    root.querySelector('[data-pse-meta]').textContent = meta.join(' · ');
    var list = root.querySelector('[data-pse-drawings]');
    list.replaceChildren();
    (stmt.drawings || []).forEach(function (d) {
      var a = list.appendChild(el('li', d.is_image ? 'foms-pse__thumb' : null)).appendChild(el('a', null, d.is_image ? null : d.name));
      a.href = d.url;
      a.target = '_blank';
      a.rel = 'noopener';
      if (!d.is_image) return;
      var img = a.appendChild(el('img'));
      img.src = d.url;
      img.alt = d.name;
      img.loading = 'lazy';
      a.appendChild(el('span', null, d.name));
    });
    if (!(stmt.drawings || []).length) list.appendChild(el('li', 'text-muted', '도면 파일이 없습니다.'));
    var needs = root.querySelector('[data-pse-needs]');
    needs.replaceChildren();
    needs.hidden = !stmt.needs.length;
    stmt.needs.forEach(function (n) { needs.appendChild(el('div', null, n)); });
    var totals = root.querySelector('[data-pse-totals]');
    totals.replaceChildren(el('b', null, '합계 ' + won(stmt.total) + '원'),
      el('span', null, ' · 공급가액 ' + won(stmt.supply) + ' · 세액 ' + won(stmt.vat)),
      el('span', null, stmt.prev_balance != null ? ' · 전일 잔액 ' + won(stmt.prev_balance) + ' → 금일 잔액 ' + won(stmt.after_balance) : ''));
  }

  function button(text, className, handler) {
    var b = el('button', 'foms-ps__btn ' + (className || ''), text);
    b.type = 'button';
    b.addEventListener('click', async function () {
      b.disabled = true;
      try { await handler(); } finally { b.disabled = false; }
    });
    return b;
  }

  async function act(path, body, done) {
    var res = await call('/' + id + path, Object.assign({ version: stmt.version }, body || {}));
    if (!res.ok) { status(res.error); return null; }
    if (done) { done(res.data); return res.data; }
    edits = {};
    stmt = res.data;
    draw();
    return res.data;
  }

  function editList() { return Object.keys(edits).map(function (k) { return edits[k]; }); }

  function drawActions() {
    var box = root.querySelector('[data-pse-actions]');
    box.replaceChildren();
    var print = el('a', 'foms-ps__btn', '양식 보기 · 인쇄');
    print.href = root.getAttribute('data-print');
    print.target = '_blank';
    print.rel = 'noopener';
    if (stmt.status === 'DRAFT') {
      var date = input('foms-pse__date', stmt.date, '명세서 일자');
      date.type = 'date';
      box.appendChild(button('저장', null, function () { return act('/save', { edits: editList() }).then(function (d) { if (d) status('저장했습니다.'); }); }));
      if (!stmt.revision_of) box.appendChild(button('다시 계산', null, function () { return act('/recalc'); }));
      box.appendChild(print);
      box.appendChild(el('label', 'small ms-auto', '일자'));
      box.appendChild(date);
      box.appendChild(button('발행', 'foms-ps__btn--primary', async function () {
        if (editList().length) { status('고친 값을 먼저 저장해 주세요.'); return; }
        if (!window.confirm('발행하면 잠기고 협력사 화면에 보입니다. 발행할까요?')) return;
        var d = await act('/issue', { date: date.value });
        if (d) status(d.doc_no + ' 발행했습니다.');
      }));
      box.appendChild(button('초안 지우기', 'foms-ps__btn--danger', async function () {
        if (!window.confirm('이 초안을 지울까요? 확정 옵션은 그대로라 다시 만들 수 있습니다.')) return;
        await act('/discard', null, function () { window.location.href = root.getAttribute('data-list'); });
      }));
      return;
    }
    box.appendChild(print);
    if (stmt.status !== 'ISSUED') return;
    box.appendChild(button('수정본 만들기', null, async function () {
      var reason = window.prompt('수정본을 만드는 이유를 적어 주세요. 협력사에게 보입니다.');
      if (!reason) return;
      await act('/revise', { reason: reason }, function (d) { window.location.href = root.getAttribute('data-list') + '/' + d.id; });
    }));
    box.appendChild(button('취소', 'foms-ps__btn--danger', async function () {
      var reason = window.prompt('취소하는 이유를 적어 주세요. 협력사에게 보입니다.');
      if (!reason) return;
      await act('/void', { reason: reason });
    }));
  }

  function drawQuestions() {
    var box = root.querySelector('[data-pse-questions]');
    box.replaceChildren();
    box.hidden = !(stmt.questions || []).length;
    if (box.hidden) return;
    box.appendChild(el('h2', 'h6', '협력사 금액 문의'));
    stmt.questions.forEach(function (q) {
      var item = box.appendChild(el('div', 'foms-pse__question'));
      item.appendChild(el('div', 'small text-muted', q.line + ' · ' + q.asked_by + ' · ' + q.asked_at));
      item.appendChild(el('div', null, q.text));
      var reply = input('foms-pse__reason', q.answer, '문의 답');
      reply.placeholder = '답 (협력사에게 보임)';
      item.appendChild(reply);
      item.appendChild(button(q.answer ? '답 고치기' : '답 보내기', null, function () {
        return act('/questions/' + q.id + '/answer', { text: reply.value }).then(function (d) { if (d) status('답을 보냈습니다.'); });
      }));
    });
  }

  function draw() {
    drawHead();
    drawGroups();
    drawQuestions();
    drawActions();
  }

  (async function load() {
    var res = await call('/' + id);
    if (!res.ok) { status(res.error); return; }
    stmt = res.data;
    draw();
  })();
})();
