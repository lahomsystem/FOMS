/**
 * 협력사 거래명세서 — 우리 CS 발행 대기 · 발행함(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.5).
 *
 * - GET {api}/pending · {api}/issued 를 받아 갈래(내일까지 출고 · 다음 출고 · 출고일 없음)별 표로 그린다. 금액은 서버 값 그대로.
 * - "열기" = POST {api}/orders/<id>/draft(없으면 초안을 만든다) → 명세서 화면으로 간다.
 * - "자동 완성만 한꺼번에 발행" = POST {api}/issue-complete. 글은 textContent 로만 넣는다.
 */
(function () {
  'use strict';

  var BUCKETS = [['soon', '내일까지 출고'], ['later', '다음 출고'], ['none', '출고일 없음']];

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function won(n) { return n == null ? '' : Number(n).toLocaleString('ko-KR') + '원'; }

  async function call(url, method) {
    var res;
    try {
      res = await fetch(url, { method: method || 'GET', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: method === 'POST' ? '{}' : undefined });
    } catch (_) {
      return { ok: false, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!data || !data.success) return { ok: false, error: (data && data.error) || '처리하지 못했습니다. 잠시 뒤 다시 해 주세요.' };
    return { ok: true, data: data.data || {} };
  }

  function table(heads) {
    var t = el('table', 'foms-ps__table');
    var tr = t.appendChild(el('thead')).appendChild(el('tr'));
    heads.forEach(function (h) { tr.appendChild(el('th', null, h)); });
    t.appendChild(el('tbody'));
    return t;
  }

  function cell(tr, text, className) { return tr.appendChild(el('td', className, text)); }

  function drawPending(root, rows, api) {
    var box = root.querySelector('[data-ps-pending]');
    box.replaceChildren();
    if (!rows.length) { box.appendChild(el('p', 'text-muted small', '발행할 주문이 없습니다.')); return; }
    BUCKETS.forEach(function (b) {
      var list = rows.filter(function (r) { return r.bucket === b[0]; });
      if (!list.length) return;
      box.appendChild(el('h3', 'foms-ps__bucket', b[1] + ' · ' + list.length + '건'));
      var t = table(['출고일', '협력사', '고객', '제품', '합계', '상태', '']);
      list.forEach(function (r) {
        var tr = t.tBodies[0].appendChild(el('tr'));
        cell(tr, r.date || '-');
        cell(tr, r.org_name);
        cell(tr, r.customer_name);
        cell(tr, r.products + '개');
        cell(tr, won(r.total), 'foms-ps__num');
        var state = r.complete ? '자동 완성' : (r.custom_open ? '금액 필요 ' + r.custom_open + '줄' : '확인 필요');
        var badge = cell(tr, state, r.complete ? 'foms-ps__ok' : 'foms-ps__need');
        if (r.revision) badge.textContent += ' · 수정본';
        if (r.needs && r.needs.length) badge.title = r.needs.join('\n');
        var open = el('button', 'foms-ps__btn', r.draft_id ? '초안 열기' : '명세서 만들기');
        open.type = 'button';
        open.addEventListener('click', async function () {
          open.disabled = true;
          var res = await call(api + '/orders/' + r.order_id + '/draft', 'POST');
          if (!res.ok) { open.disabled = false; status(root, res.error); return; }
          window.location.href = root.getAttribute('data-page') + '/' + res.data.id;
        });
        tr.appendChild(el('td')).appendChild(open);
      });
      box.appendChild(t);
    });
  }

  function drawIssued(root, rows) {
    var box = root.querySelector('[data-ps-issued]');
    box.replaceChildren();
    if (!rows.length) { box.appendChild(el('p', 'text-muted small', '아직 발행한 명세서가 없습니다.')); return; }
    var t = table(['일자', '문서번호', '협력사', '고객', '합계', '상태', '']);
    rows.forEach(function (r) {
      var tr = t.tBodies[0].appendChild(el('tr', r.status === 'VOID' ? 'foms-ps__void' : null));
      cell(tr, r.date);
      cell(tr, r.doc_no);
      cell(tr, r.org_name);
      cell(tr, r.customer_name);
      cell(tr, won(r.total), 'foms-ps__num');
      cell(tr, r.status_text + (r.acked ? ' · 협력사 확인함' : '') + (r.open_questions ? ' · 답할 문의 ' + r.open_questions : '') + (r.reason ? ' · ' + r.reason : ''));
      var a = el('a', 'foms-ps__btn', '보기');
      a.href = root.getAttribute('data-page') + '/' + r.id;
      tr.appendChild(el('td')).appendChild(a);
    });
    box.appendChild(t);
  }

  function status(root, text) { root.querySelector('[data-ps-status]').textContent = text || ''; }

  async function load(root) {
    var api = root.getAttribute('data-api');
    var pending = await call(api + '/pending');
    if (pending.ok) drawPending(root, pending.data.rows || [], api); else status(root, pending.error);
    var issued = await call(api + '/issued');
    if (issued.ok) drawIssued(root, issued.data.rows || []);
  }

  function init() {
    var root = document.querySelector('[data-ps-root]');
    if (!root || root.dataset.psReady) return;
    root.dataset.psReady = '1';
    root.querySelector('[data-ps-bulk]').addEventListener('click', async function (ev) {
      var btn = ev.currentTarget;
      if (!window.confirm('금액이 다 찬 대기 주문을 모두 발행할까요? 발행하면 협력사 화면에 보입니다.')) return;
      btn.disabled = true;
      var res = await call(root.getAttribute('data-api') + '/issue-complete', 'POST');
      btn.disabled = false;
      if (!res.ok) { status(root, res.error); return; }
      status(root, res.data.issued.length + '건 발행했습니다.' + (res.data.skipped.length ? ' ' + res.data.skipped.length + '건은 막혔습니다: ' +
        res.data.skipped.map(function (s) { return s.error; }).join(' / ') : ''));
      load(root);
    });
    load(root);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  document.addEventListener('foms:erp-shell-fragment-swapped', init);
})();
